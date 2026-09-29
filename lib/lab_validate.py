"""E005: compare sandbox restore to the P1 oracle manifest (row / byte / schema)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from lab_p4_util import EXIT_ASSERT, die, env, restore_root, review_dir, ssh_sudo, write_json
from lab_paths import evidence_dir
from lab_restore_db import PG_BIN
from lsn import lsn_int, lsn_norm

# SC-01 p2_probe as captured in the sandbox (not the live victim).
EXPECTED_DDL = ("id bigint", "v text")


def psql(port: int, sql: str) -> str:
    proc = ssh_sudo(
        f"sudo -n -u postgres {PG_BIN}/psql -X -qAt -h 127.0.0.1 -p {port} "
        f"-d {env('DB_NAME')} -c \"{sql}\""
    )
    if proc.returncode != 0:
        die(EXIT_ASSERT, "assertion failed: sandbox psql: " + (proc.stderr or proc.stdout or ""))
    return proc.stdout.strip()


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def hash_ids(ids: list[int]) -> str:
    h = hashlib.sha256()
    h.update((",".join(str(i) for i in ids)).encode("ascii"))
    return h.hexdigest()


def rec_lsn(rec: dict) -> int | None:
    raw = rec.get("commit_lsn") or rec.get("lsn")
    if not raw:
        return None
    try:
        return lsn_int(lsn_norm(str(raw)))
    except ValueError:
        return None


def rec_rows(rec: dict) -> int:
    return int(rec.get("row_count") or len(rec.get("row_ids") or []))


def parse_hash_lines(text: str, snapshot: str | None = None) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "\t" in line:
            columns = line.split("\t")
            if len(columns) == 3:
                snap, path, digest = columns
                if snapshot is None:
                    raise ValueError("snapshot is required for three-column file fingerprints")
                if snap == snapshot:
                    out.append((path, digest.lower()))
                continue
            left, right = line.split("\t", 1)
            if len(left) == 64 and all(c in "0123456789abcdef" for c in left.lower()):
                out.append((right.strip(), left.strip().lower()))
            else:
                out.append((left.strip(), right.strip().lower()))
        else:
            parts = line.split()
            if len(parts) >= 2 and len(parts[0]) == 64:
                out.append((parts[1], parts[0].lower()))
    return out


def guest_sha256(path: str) -> str | None:
    proc = ssh_sudo(f"if [ -f '{path}' ]; then sha256sum -b '{path}'; fi")
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.split()[0].lower()


def expected_fingerprints(ev: Path) -> tuple[str, list[tuple[str, str]]]:
    """Expected file state = fingerprints captured at the reference snapshot (oracle.json), never the
    snapshot being restored, which would make the comparison vacuous."""
    reference = json.loads((ev / "oracle.json").read_text())["coordinate"]["snapshot"]
    text = (ev / "fs_hashes.tsv").read_text() if (ev / "fs_hashes.tsv").is_file() else ""
    return reference, parse_hash_lines(text, snapshot=reference)


def validate(incident: str, restore_of: str, task: str = "E005") -> dict:
    partial = json.loads((restore_root(incident, restore_of) / "report.partial.json").read_text())
    port = int(partial["restore_target"]["sandbox_port"])
    ev = evidence_dir(incident)
    man = json.loads((ev / "oracle-manifest.json").read_text())
    inj = json.loads((ev / "injection.json").read_text())
    rel = inj.get("relation") or os.environ.get("SC01_RELATION") or "p2_probe"
    destroyed = [int(x) for x in man.get("destroyed_row_ids") or []]
    legit = [int(x) for x in man.get("legitimate_row_ids") or []]
    raw_ids = psql(port, f"SELECT id FROM public.{rel} ORDER BY 1;")
    restored_ids = [int(x) for x in raw_ids.splitlines() if x.strip()]
    restored_set = set(restored_ids)
    count = len(restored_ids)
    content = hash_ids(restored_ids)

    mismatches = []
    damage_rows = 0
    for rid in destroyed:
        if rid not in restored_set:
            damage_rows += 1
            mismatches.append({
                "object": f"public.{rel}",
                "kind": "row_count",
                "expected": "present_at_optimum",
                "actual": f"missing:{rid}",
                "classification": "damage_retained",
            })
    chosen = int(partial["coordinate"]["lsn_int"])
    opt_n = lsn_int(lsn_norm(str(man.get("optimum_lsn") or "1/E1000000")))
    workload = load_jsonl(ev / "workload-manifest.jsonl")
    legit_vs_optimum = 0
    p3_analytical = 0
    for rec in workload:
        n = rec_lsn(rec)
        if n is None:
            continue
        rows = rec_rows(rec)
        if n > chosen:
            p3_analytical += rows
        if chosen < n <= opt_n:
            legit_vs_optimum += rows
    for rid in legit:
        if rid not in restored_set:
            mismatches.append({
                "object": f"public.{rel}",
                "kind": "content_hash",
                "expected": str(rid),
                "actual": "missing",
                "classification": "legit_lost",
            })

    db_block = {
        "relations_checked": 1,
        "relations_matched": 0 if mismatches else 1,
        "mismatches": [m for m in mismatches if m["object"].startswith("public.")],
        "relations": {rel: {"row_count": count, "content_hash": content}},
        "p3_analytical_legit_rows_lost": p3_analytical,
    }

    fs_mnt = partial["restore_target"].get("fs_mount") or ""
    fs_mismatches = []
    files_checked = 0
    if fs_mnt:
        listing = ssh_sudo(f"find '{fs_mnt}' -type f ! -path '*/.zfs/*' | sort")
        paths = [ln for ln in listing.stdout.splitlines() if ln.strip()]
        files_checked = len(paths)
    reference_snapshot, expected_files = expected_fingerprints(ev)
    files_compared = len(expected_files)
    probe = restore_root(incident, restore_of) / "fs_probe.tsv"
    if probe.is_file():
        expected_files.extend(parse_hash_lines(probe.read_text()))
        files_compared = len(expected_files)
    for rel_or_abs, expected_hash in expected_files:
        path = rel_or_abs if rel_or_abs.startswith("/") else (fs_mnt.rstrip("/") + "/" + rel_or_abs.lstrip("/"))
        actual = guest_sha256(path)
        files_checked = max(files_checked, 1)
        if actual is None:
            fs_mismatches.append({
                "object": path,
                "kind": "missing",
                "expected": expected_hash,
                "actual": "missing",
                "classification": "legit_lost",
            })
        elif actual != expected_hash:
            fs_mismatches.append({
                "object": path,
                "kind": "byte_hash",
                "expected": expected_hash,
                "actual": actual,
                "classification": "damage_retained",
            })
    fs_block = {
        "files_checked": files_checked,
        "expected_snapshot": reference_snapshot,
        "files_compared": files_compared,
        "files_matched": files_checked - len(fs_mismatches) if files_checked else 0,
        "mismatches": fs_mismatches,
    }

    ddl = psql(
        port,
        "SELECT a.attname||' '||format_type(a.atttypid,a.atttypmod) "
        f"FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        f"JOIN pg_namespace n ON n.oid=c.relnamespace "
        f"WHERE n.nspname='public' AND c.relname='{rel}' AND a.attnum>0 AND NOT a.attisdropped "
        "ORDER BY a.attnum;",
    )
    actual_ddl = tuple(x for x in ddl.splitlines() if x.strip())
    schema_diffs = []
    if actual_ddl != EXPECTED_DDL:
        schema_diffs.append({
            "object": f"public.{rel}",
            "kind": "schema",
            "expected": " | ".join(EXPECTED_DDL),
            "actual": " | ".join(actual_ddl),
            "classification": "damage_retained" if len(actual_ddl) < len(EXPECTED_DDL) else "legit_lost",
        })
    schema_block = {
        "ddl_match": actual_ddl == EXPECTED_DDL,
        "diffs": schema_diffs,
        "ddl": "\n".join(actual_ddl),
    }

    summary = {
        "damage_rows_retained": damage_rows,
        "legit_rows_lost": legit_vs_optimum,
        "files_mismatched": len(fs_mismatches),
        "schema_diffs": len(schema_diffs),
        "p3_analytical_legit_rows_lost": p3_analytical,
    }
    out = {
        "db_validation": db_block,
        "fs_validation": fs_block,
        "schema_validation": schema_block,
        "summary": summary,
    }
    write_json(restore_root(incident, restore_of) / "validation.json", out)
    if task == "E005":
        write_json(review_dir("E005") / "validation-sample.json", out)
    return out


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-validate")
    p.add_argument("incident")
    p.add_argument("restore_of")
    p.add_argument("--task", default="E005")
    args = p.parse_args(argv)
    out = validate(args.incident, args.restore_of, args.task)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
