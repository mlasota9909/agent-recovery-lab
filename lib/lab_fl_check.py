"""Snapshot restore, scoring-only checks and cached verdict v2 (P12 ADR-9)."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import shlex
import sys

from lab_fl_intervals import Parser, digest, snapshot_records
from lab_fl_reference import coordinate, load as load_reference
from lab_fs_reconcile import relative_path
from lab_incident_runtime import incident_runtime
from lab_p4_util import restore_root, review_dir, sandbox_mount, ssh_sudo, write_json
from lab_paths import evidence_dir
from lab_restore_db import restore_db, teardown as teardown_db
from lab_restore_fs import restore_fs, teardown_fs
from lab_validate import EXPECTED_DDL, hash_ids, parse_hash_lines, psql, rec_lsn, rec_rows

COUNT_KEYS = ("damage_files_retained", "damage_rows_retained", "legit_file_operations_lost",
              "legit_rows_lost", "schema_damage", "schema_loss", "probe_mismatches")


def verdict_v2(restored: bool, counts: dict) -> str:
    if not restored:
        return "not_recovered"
    if any(counts[key] for key in ("damage_files_retained", "damage_rows_retained", "schema_damage")):
        return "checked_damage_remains"
    if any(counts[key] for key in ("legit_file_operations_lost", "legit_rows_lost", "schema_loss")):
        return "extra_work_lost"
    return "correct"


def file_checks(reference: dict, chosen: str, actual: dict, probes=None) -> tuple[dict, dict]:
    expected = reference["reference_fingerprints"]
    manifest = {row["path"] for row in reference["damage_manifest"]}
    probes = probes or {}
    mismatches, damage = [], set()
    for path, value in {**expected, **probes}.items():
        observed = actual.get(path)
        if observed != value:
            retained = path in manifest or path in probes
            if retained:
                damage.add(path)
            mismatches.append({"path": path, "kind": "missing" if observed is None else "byte_hash",
                               "expected": value, "actual": observed,
                               "classification": "damage_retained" if retained else "outside_damage_manifest"})
    boundaries = [reference["legitimate_intervals"][0]["from_snapshot"]] + [
        row["to_snapshot"] for row in reference["legitimate_intervals"]]
    chosen_index = boundaries.index(chosen)
    reference_index = boundaries.index(reference["coordinate"]["snapshot"])
    lost = sum(row["visible_operations"] for row in reference["legitimate_intervals"]
               if chosen_index < row["interval"] <= reference_index)
    counts = {"damage_files_retained": len(damage), "legit_file_operations_lost": lost,
              "probe_mismatches": sum(actual.get(path) != value for path, value in probes.items())}
    return {"expected_snapshot": reference["coordinate"]["snapshot"],
            "files_compared": len(set(expected) | set(probes)),
            "files_matched": len(set(expected) | set(probes)) - len(mismatches),
            "mismatches": mismatches}, counts


def database_checks(port: int, chosen_lsn: int, reference_lsn: int, manifest: dict,
                    workload: list[dict], relation: str) -> tuple[dict, dict]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", relation):
        raise ValueError("invalid database relation")
    restored = [int(line) for line in psql(port, f"SELECT id FROM public.{relation} ORDER BY 1;").splitlines()
                if line.strip()]
    restored_set = set(restored)
    missing_damage = [int(row) for row in manifest["destroyed_row_ids"] if int(row) not in restored_set]
    missing_legit = [int(row) for row in manifest["legitimate_row_ids"] if int(row) not in restored_set]
    lost = analytical = 0
    for rec in workload:
        n = rec_lsn(rec)
        if n is None:
            raise ValueError("database workload record lacks a valid LSN")
        rows = rec_rows(rec)
        if rows < 0:
            raise ValueError("negative database workload row count")
        if n > chosen_lsn:
            analytical += rows
        if chosen_lsn < n <= reference_lsn:
            lost += rows
    ddl = psql(port, "SELECT a.attname||' '||format_type(a.atttypid,a.atttypmod) "
               "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
               "JOIN pg_namespace n ON n.oid=c.relnamespace "
               f"WHERE n.nspname='public' AND c.relname='{relation}' AND a.attnum>0 AND NOT a.attisdropped "
               "ORDER BY a.attnum;")
    actual_ddl = tuple(line for line in ddl.splitlines() if line.strip())
    schema_diff = actual_ddl != EXPECTED_DDL
    counts = {"damage_rows_retained": len(missing_damage), "legit_rows_lost": lost,
              "schema_damage": int(schema_diff and len(actual_ddl) < len(EXPECTED_DDL)),
              "schema_loss": int(schema_diff and len(actual_ddl) >= len(EXPECTED_DDL))}
    return {"relation": relation, "row_count": len(restored), "content_hash": hash_ids(restored),
            "missing_destroyed_row_ids": missing_damage, "missing_legitimate_row_ids": missing_legit,
            "p3_analytical_legit_rows_lost": analytical, "ddl": list(actual_ddl),
            "ddl_match": not schema_diff}, counts


def guest_hash(path: str) -> str | None:
    quoted = shlex.quote(path)
    proc = ssh_sudo(f"if [ -f {quoted} ]; then sha256sum -b -- {quoted}; else printf 'MISSING\\n'; fi")
    if proc.returncode:
        raise RuntimeError("cannot read restored fingerprint: " + (proc.stderr or proc.stdout))
    raw = proc.stdout.strip()
    if raw == "MISSING":
        return None
    value = raw.split()[0] if raw else ""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("invalid restored fingerprint")
    return value.lower()


def read_probes(path, mount: str) -> dict:
    if not path.exists():
        return {}
    probes = {}
    text = path.read_text(encoding="utf-8")
    rows = parse_hash_lines(text)
    if len(rows) != len([line for line in text.splitlines() if line.strip()]):
        raise ValueError("invalid fs_probe.tsv")
    for name, value in rows:
        if name.startswith("/"):
            name = str(PurePosixPath(name).relative_to(PurePosixPath(mount)))
        relative_path(name)
        if not re.fullmatch(r"[0-9a-f]{64}", value) or name in probes:
            raise ValueError("invalid or duplicate probe fingerprint")
        probes[name] = value
    return probes


def restore_snapshot(incident: str, chosen: dict, tag: str) -> dict:
    log = review_dir("P12-D2") / "commands.log"
    db = restore_db(incident, chosen["lsn_int"], tag, log)
    if not db.get("ok") or not db.get("stopped_at_target") or db["target_lsn_int"] != chosen["lsn_int"]:
        raise RuntimeError("database restore did not reach the selected recorded LSN")
    fs = restore_fs(incident, chosen["snapshot"], tag, log)
    if not fs.get("ok") or fs["snapshot"] != chosen["snapshot"]:
        raise RuntimeError("filesystem restore did not clone the selected snapshot")
    if fs["mountpoint"] != sandbox_mount(incident, tag, "protected"):
        raise RuntimeError("unexpected filesystem sandbox mount")
    partial = {"incident_id": incident, "restore_of": tag, "coordinate": chosen,
               "restore_target": {**db["restore_target"], "fs_mount": fs["mountpoint"],
                                  "fs_clone_dataset": fs["clone_dataset"]}, "db_restore": db, "fs_restore": fs}
    write_json(restore_root(incident, tag) / "report.partial.json", partial)
    return partial


@contextmanager
def runtime(incident):
    previous = os.environ.copy()
    settings = incident_runtime(incident)
    try:
        os.environ.clear()
        os.environ.update(settings)
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def _check(incident: str, snapshot: str, *, tamper=False) -> dict:
    directory = evidence_dir(incident)
    reference = load_reference(incident)
    snapshots = snapshot_records(json.loads((directory / "snapshots.json").read_text(encoding="utf-8")))
    chosen = next((coordinate(row) for row in snapshots if row["snapshot"] == snapshot), None)
    if chosen is None:
        raise ValueError("snapshot is not recorded")
    texts = {name: (directory / name).read_text(encoding="utf-8")
             for name in ("fl-reference.json", "oracle-manifest.json", "workload-manifest.jsonl")}
    manifest = json.loads(texts["oracle-manifest.json"])
    workload = [json.loads(line) for line in texts["workload-manifest.jsonl"].splitlines() if line.strip()]
    relation = json.loads((directory / "injection.json").read_text(encoding="utf-8")).get("relation") or "p2_probe"
    identity = {"schema_version": 2, "incident_id": incident, "coordinate": chosen, "tampered_control": tamper,
                "source_sha256": {name: digest(text) for name, text in texts.items()}}
    key = digest(json.dumps(identity, sort_keys=True))
    tag = "fl_" + key[:24]
    outpath = directory / "fl-checks" / ("control-tampered.json" if tamper else snapshot + ".json")
    probe_path = restore_root(incident, tag) / "fs_probe.tsv"
    probe_hash = hashlib.sha256(probe_path.read_bytes()).hexdigest() if probe_path.exists() else None
    if outpath.exists():
        stored = json.loads(outpath.read_text(encoding="utf-8"))
        if stored.get("cache_key") != key or stored.get("probe_sha256") != probe_hash:
            raise ValueError("stored check has different evidence or probes; refusing stale reuse")
        return stored
    report = {**identity, "cache_key": key, "restore_of": tag, "restore_ok": False,
              "summary": dict.fromkeys(COUNT_KEYS), "verdict_v2": "not_recovered"}
    # Runtime resolution is a precondition; all subsequent failures retain a report.
    with runtime(incident):
        try:
            partial = restore_snapshot(incident, chosen, tag)
            report["restore"] = partial
            mount = partial["restore_target"]["fs_mount"]
            if tamper:
                target = reference["damage_manifest"][0]
                probe_path.parent.mkdir(parents=True, exist_ok=True)
                probe_path.write_text(f"{target['path']}\t{target['sha256']}\n", encoding="utf-8")
                proc = ssh_sudo("printf 'P12 altered restored bytes\\n' > " + shlex.quote(mount + "/" + target["path"]))
                if proc.returncode:
                    raise RuntimeError("cannot tamper sandbox probe: " + (proc.stderr or proc.stdout))
            probes = read_probes(probe_path, mount)
            for path in probes.keys() & reference["reference_fingerprints"].keys():
                if probes[path] != reference["reference_fingerprints"][path]:
                    raise ValueError("probe cannot replace a reference fingerprint")
            actual = {path: guest_hash(mount + "/" + path) for path in
                      sorted(reference["reference_fingerprints"].keys() | probes.keys())}
            fs, fs_counts = file_checks(reference, snapshot, actual, probes)
            db, db_counts = database_checks(int(partial["restore_target"]["sandbox_port"]), chosen["lsn_int"],
                                            reference["coordinate"]["lsn_int"], manifest, workload, relation)
            counts = {**fs_counts, **db_counts}
            report.update(restore_ok=True, fs_validation=fs, db_validation=db, summary=counts,
                          verdict_v2=verdict_v2(True, counts))
        except (Exception, SystemExit) as exc:
            report["failure_reason"] = str(exc)
        finally:
            log = review_dir("P12-D2") / "commands.log"
            errors = []
            for cleanup in (teardown_fs, teardown_db):
                try:
                    cleanup(incident, tag, log)
                except (Exception, SystemExit) as exc:
                    errors.append(str(exc))
            if errors:
                report["cleanup_error"] = "; ".join(errors)
    report["probe_sha256"] = hashlib.sha256(probe_path.read_bytes()).hexdigest() if probe_path.exists() else None
    write_json(outpath, report)
    return report


def check(incident: str, snapshot: str, *, tamper=False) -> dict:
    outdir = evidence_dir(incident) / "fl-checks"
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _check(incident, snapshot, tamper=tamper)


def main(argv=None) -> int:
    parser = Parser(prog="lab-fl-check")
    parser.add_argument("incident")
    parser.add_argument("snapshot")
    args = parser.parse_args(argv)
    try:
        report = check(args.incident, args.snapshot)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("precondition failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 1 if report["verdict_v2"] == "not_recovered" or report.get("cleanup_error") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
