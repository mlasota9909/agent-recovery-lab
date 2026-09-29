"""lab-oracle: known-optimal recovery coordinate for a scripted incident.

Article II / ADR-P1-3: the oracle MAY read provenance fields. It is the only
component permitted to. Do not "fix" this by pointing it at the analysis view.
Analysis, ranking and restore consume the analysis view, never this path.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from lsn import lsn_cmp, lsn_int, lsn_norm
from results_schema import canonical_json

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3

COORDINATE_FIELDS = (
    "wall_clock",
    "lsn",
    "snapshot",
    "skew_ms",
    "skew_bytes",
    "resolved_by",
)


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def env(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        die(EXIT_PRECOND, f"precondition failed: {key} missing from lab.env")
    return v


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def evidence_dir(incident: str) -> Path:
    scenario = incident.split("_", 1)[0]
    return Path(env("EVIDENCE_ROOT")) / scenario / incident


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            die(EXIT_ASSERT, f"assertion failed: {path}:{lineno} is not JSON: {exc}")
        if not isinstance(obj, dict):
            die(EXIT_ASSERT, f"assertion failed: {path}:{lineno} is not an object")
        rows.append(obj)
    return rows


def write_immutable(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(path)
    os.chmod(path, 0o444)


def resolve_coordinate(lsn: str) -> dict:
    cli = Path(os.environ["LAB_ROOT"]) / "bin" / "lab-coordinate"
    p = subprocess.run(
        [str(cli), "--lsn", lsn],
        text=True,
        capture_output=True,
        check=False,
        env=os.environ,
    )
    if p.returncode != 0:
        err = (p.stderr or p.stdout).strip()
        if "no snapshot at or below" in err:
            die(EXIT_ASSERT, f"precondition failed: no snapshot at or below {lsn}: {err}")
        die(EXIT_PRECOND, f"precondition failed: lab-coordinate: {err}")
    try:
        raw = json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        die(EXIT_ASSERT, f"assertion failed: lab-coordinate stdout is not JSON: {exc}")
    coord = {k: raw[k] for k in COORDINATE_FIELDS}
    if coord["resolved_by"] not in {"lsn_first", "snapshot_first", "time_first"}:
        die(EXIT_ASSERT, f"assertion failed: resolved_by {coord['resolved_by']!r}")
    if not isinstance(coord["skew_ms"], int) or coord["skew_ms"] < 0:
        die(EXIT_ASSERT, "assertion failed: skew_ms is not a non-negative integer")
    if not isinstance(coord["skew_bytes"], int) or coord["skew_bytes"] < 0:
        die(EXIT_ASSERT, "assertion failed: skew_bytes is not a non-negative integer")
    return coord


def select_optimum(manifest: list[dict], inject_lsn: str) -> dict:
    before = []
    for rec in manifest:
        try:
            rec_lsn = lsn_norm(rec["commit_lsn"])
        except (KeyError, ValueError) as exc:
            die(EXIT_ASSERT, f"assertion failed: manifest LSN: {exc}")
        if lsn_cmp(rec_lsn, inject_lsn) < 0:
            before.append(rec)
    if not before:
        die(EXIT_ASSERT, "precondition failed: no legitimate commit precedes the injection")
    chosen = max(before, key=lambda r: lsn_int(r["commit_lsn"]))
    if lsn_cmp(lsn_norm(chosen["commit_lsn"]), inject_lsn) >= 0:
        die(EXIT_ASSERT, "assertion failed: optimum is not strictly less than the malicious LSN")
    return chosen


def replay_legit_ids(manifest: list[dict], optimum_lsn: str, seed: dict | None) -> tuple[list[int], int]:
    present: dict[int, int] = {}
    if seed and seed.get("id_min") is not None and seed.get("id_max") is not None:
        for i in range(int(seed["id_min"]), int(seed["id_max"]) + 1):
            present[i] = 64
    for rec in manifest:
        if lsn_cmp(lsn_norm(rec["commit_lsn"]), optimum_lsn) > 0:
            continue
        op = rec.get("operation")
        ids = rec.get("row_ids") or []
        for rid in ids:
            rid = int(rid)
            if op == "insert":
                present[rid] = 64
            elif op == "delete":
                present.pop(rid, None)
    return sorted(present), sum(present.values())


def build_manifest_doc(optimum: dict, inject: dict, manifest: list[dict], seed: dict | None) -> dict:
    opt_lsn = lsn_norm(optimum["commit_lsn"])
    destroyed = [int(x) for x in inject["row_ids"]]
    destroyed_bytes = int(inject.get("destroyed_bytes") or sum(inject.get("row_bytes") or []))
    if destroyed_bytes == 0:
        destroyed_bytes = len(destroyed) * 64
    legit_ids, legit_bytes = replay_legit_ids(manifest, opt_lsn, seed)
    return {
        "optimum_lsn": opt_lsn,
        "malicious_lsn": lsn_norm(inject["commit_lsn"]),
        "legitimate_row_ids": legit_ids,
        "legitimate_row_count": len(legit_ids),
        "legitimate_bytes": legit_bytes,
        "destroyed_row_ids": destroyed,
        "destroyed_row_count": len(destroyed),
        "destroyed_bytes": destroyed_bytes,
        "legitimate_commits_at_or_before": sum(
            1 for r in manifest if lsn_cmp(lsn_norm(r["commit_lsn"]), opt_lsn) <= 0
        ),
    }


def score_chosen(incident: str, chosen_lsn: str) -> dict:
    """Oracle-computed recovery-point error. May read provenance / injection log."""
    ev = evidence_dir(incident)
    inject = json.loads((ev / "injection.json").read_text(encoding="utf-8"))
    manifest = load_jsonl(ev / "workload-manifest.jsonl")
    gt = json.loads((ev / "oracle.json").read_text(encoding="utf-8"))["coordinate"]
    inj_lsn = lsn_norm(inject["commit_lsn"])
    chosen_n = lsn_int(chosen_lsn)
    inj_n = lsn_int(inj_lsn)
    destroyed = [int(x) for x in inject.get("row_ids") or []]
    destroyed_bytes = int(inject.get("destroyed_bytes") or len(destroyed) * 64)
    if chosen_n < inj_n:
        damage_rows = 0
        damage_bytes = 0
    else:
        damage_rows = len(destroyed)
        damage_bytes = destroyed_bytes
    legit_after = 0
    legit_bytes = 0
    for rec in manifest:
        if lsn_int(lsn_norm(rec["commit_lsn"])) > chosen_n:
            n = int(rec.get("row_count") or len(rec.get("row_ids") or []))
            legit_after += n
            legit_bytes += n * 64
    err_bytes = abs(chosen_n - lsn_int(gt["lsn"]))
    cmp = lsn_cmp(chosen_lsn, gt["lsn"])
    direction = "exact" if cmp == 0 else ("before" if cmp < 0 else "after")
    return {
        "coord_error_bytes": err_bytes,
        "coord_error_ms": None,
        "coord_direction": direction,
        "legit_rows_lost": legit_after,
        "legit_bytes_lost": legit_bytes,
        "damage_rows_retained": damage_rows,
        "damage_bytes_retained": damage_bytes,
        "ground_truth_lsn": gt["lsn"],
        "chosen_lsn": lsn_norm(chosen_lsn),
        "inject_lsn": inj_lsn,
    }


def oracle(incident: str) -> dict:
    ev = evidence_dir(incident)
    inj_path = ev / "injection.json"
    man_path = ev / "workload-manifest.jsonl"
    out_oracle = ev / "oracle.json"
    out_man = ev / "oracle-manifest.json"
    if not inj_path.is_file():
        die(EXIT_PRECOND, f"precondition failed: {inj_path} is absent")
    if not man_path.is_file():
        die(EXIT_PRECOND, f"precondition failed: {man_path} is absent")
    try:
        inject = json.loads(inj_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(EXIT_ASSERT, f"assertion failed: injection.json is malformed: {exc}")
    if "commit_lsn" not in inject:
        die(EXIT_ASSERT, "assertion failed: injection.json lacks commit_lsn")
    manifest = load_jsonl(man_path)
    if not manifest:
        die(EXIT_PRECOND, f"precondition failed: {man_path} is empty")
    inject_lsn = lsn_norm(inject["commit_lsn"])
    chosen = select_optimum(manifest, inject_lsn)
    opt_lsn = lsn_norm(chosen["commit_lsn"])
    inputs = {
        "injection.json": {
            "path": str(inj_path),
            "sha256": sha256_file(inj_path),
            "commit_lsn": inject_lsn,
            "rows_destroyed": inject.get("rows_destroyed"),
        },
        "workload-manifest.jsonl": {
            "path": str(man_path),
            "sha256": sha256_file(man_path),
            "records": len(manifest),
            "selected_record": {
                "commit_lsn": opt_lsn,
                "commit_ts": chosen.get("commit_ts"),
                "operation": chosen.get("operation"),
                "row_ids": chosen.get("row_ids"),
            },
        },
    }
    if out_oracle.is_file() and out_man.is_file():
        prev = json.loads(out_oracle.read_text(encoding="utf-8"))
        prev_in = prev.get("inputs") or {}
        same = (
            prev_in.get("injection.json", {}).get("sha256") == inputs["injection.json"]["sha256"]
            and prev_in.get("workload-manifest.jsonl", {}).get("sha256")
            == inputs["workload-manifest.jsonl"]["sha256"]
        )
        if same:
            print(json.dumps({
                "ok": True,
                "changed": False,
                "incident": incident,
                "coordinate": prev["coordinate"],
                "oracle": str(out_oracle),
            }, sort_keys=True))
            return prev
    coord = resolve_coordinate(opt_lsn)
    seed_path = ev / "seed-manifest.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8")) if seed_path.is_file() else None
    if seed_path.is_file():
        inputs["seed-manifest.json"] = {"path": str(seed_path), "sha256": sha256_file(seed_path)}
    scoring = build_manifest_doc(chosen, inject, manifest, seed)
    doc = {
        "incident": incident,
        "coordinate": coord,
        "inputs": inputs,
    }
    write_immutable(out_oracle, json.dumps(doc, indent=2, sort_keys=True) + "\n")
    write_immutable(out_man, json.dumps(scoring, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "ok": True,
        "changed": True,
        "incident": incident,
        "coordinate": coord,
        "oracle": str(out_oracle),
        "oracle_manifest": str(out_man),
    }, sort_keys=True))
    return doc


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--incident":
        die(EXIT_USAGE, "usage: lab-oracle --incident <id>")
    oracle(argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
