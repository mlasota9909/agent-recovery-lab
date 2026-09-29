"""lab-ledger-account: exactly-once coverage. Mapping does not read principal."""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from lab_db_integrity import verify as db_verify
from lab_paths import current_incident, env, evidence_dir, lab_root
from lab_snapshot_tick import lsns_monotonic, null_lsn_scan
from lsn import lsn_int

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def emit(obj: dict) -> None:
    print(json.dumps(obj, sort_keys=True))


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: missing {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def col_map(rec: dict, field: str) -> dict:
    out = {}
    for item in rec.get(field) or []:
        if isinstance(item, dict) and "name" in item:
            out[item["name"]] = item.get("value")
    return out


def as_xid(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return None


def rec_key(rec: dict) -> tuple | None:
    action = rec.get("action")
    table = rec.get("table")
    xid = as_xid(rec.get("xid"))
    if table == env("DDL_AUDIT_TABLE") and action == "I":
        if xid is None:
            return None
        cols = col_map(rec, "columns")
        tag, ident = cols.get("command_tag"), cols.get("object_identity")
        if tag and ident:
            return ("DDL", xid, tag, ident)
        return None
    if action in {"I", "U", "D"} and table not in {env("HEARTBEAT_TABLE"), env("DDL_AUDIT_TABLE")}:
        if xid is None:
            return None
        cols = col_map(rec, "columns")
        ident = col_map(rec, "identity")
        pk = col_map(rec, "pk")
        kid = cols.get("id", ident.get("id", pk.get("id")))
        if kid is None:
            return None
        return ("DML", xid, table, action, kid)
    return None


def op_key(op: dict) -> tuple | None:
    xid = as_xid(op.get("xid"))
    if xid is None:
        return None
    if op.get("action") in {"CREATE", "ALTER", "DROP"}:
        return ("DDL", xid, op.get("command_tag"), op.get("object_identity"))
    if op.get("action") in {"I", "U", "D"}:
        return ("DML", xid, op.get("table"), op.get("action"), op.get("natural_key"))
    return None


def map_ops(ops: list[dict], ledger: list[dict]) -> dict:
    # Bijection on (xid, table, action, natural_key) / (xid, command_tag, object_identity).
    # Does not read principal. Same full key may repeat only if two identical
    # actions share one transaction; assignment is then by remaining multiplicity.
    unused: dict[tuple, list[int]] = defaultdict(list)
    for i, rec in enumerate(ledger):
        k = rec_key(rec)
        if k is None:
            continue
        unused[k].append(i)
    gaps = []
    mapped = []
    for op in ops:
        k = op_key(op)
        if k is None:
            gaps.append({"op_index": op.get("op_index"), "reason": "unkeyed"})
            continue
        queue = unused.get(k) or []
        if not queue:
            gaps.append({"op_index": op.get("op_index"), "key": list(k)})
            continue
        idx = queue.pop(0)
        rec = ledger[idx]
        mapped.append({
            "op_index": op["op_index"],
            "key": list(k),
            "lsn": rec.get("lsn"),
            "table": rec.get("table"),
            "action": rec.get("action"),
            "xid": k[1],
        })
    op_keys = {op_key(o) for o in ops if op_key(o) is not None}
    duplicates = []
    for k, leftover in unused.items():
        if leftover and k in op_keys:
            duplicates.append({"key": list(k), "extra_records": len(leftover)})
    return {
        "ops": len(ops),
        "mapped": len(mapped),
        "gaps": gaps,
        "duplicates": duplicates,
        "mapping": mapped,
    }


def heartbeat_ok(incident: str) -> dict:
    """C-5: nearest heartbeat resolves an LSN within 1 s (lab-coordinate --time)."""
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", env("VM_SSH"),
         f"sudo -n -u postgres psql -X -qAt -p {env('PG_PORT')} -d {env('DB_NAME')} "
         f"-c \"SELECT to_char(at AT TIME ZONE 'UTC', 'YYYY-MM-DD\\\"T\\\"HH24:MI:SS.US\\\"Z\\\"') "
         f"FROM public.{env('HEARTBEAT_TABLE')} ORDER BY id DESC LIMIT 5\""],
        text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip(), "rule": "C-5"}
    times = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    samples = []
    ok = True
    for iso in times:
        coord = subprocess.run(
            [str(lab_root() / "bin" / "lab-coordinate"), "--time", iso],
            text=True, capture_output=True, check=False, cwd=str(lab_root()),
        )
        samples.append({"time": iso, "exit": coord.returncode})
        if coord.returncode != 0:
            ok = False
    return {"ok": ok and bool(samples), "n": len(samples), "rule": "C-5", "failed": [s for s in samples if s["exit"] != 0][:5]}


def fs_coverage(incident: str, ops: list[dict]) -> dict:
    fs_ops = [o for o in ops if str(o.get("action", "")).startswith("FS")]
    if not fs_ops:
        return {"ok": True, "fs_ops": 0, "vacuous": True, "rule": "C-7"}
    diff = evidence_dir(incident) / "fs_diff.tsv"
    text = diff.read_text(encoding="utf-8") if diff.is_file() else ""
    missing = []
    for op in fs_ops:
        path = op.get("path")
        if path and path not in text:
            missing.append(path)
    return {"ok": not missing, "fs_ops": len(fs_ops), "missing": missing, "vacuous": False, "rule": "C-7"}


def main(argv: list[str]) -> int:
    incident = argv[0] if argv else current_incident()
    if argv and argv[0].startswith("--"):
        die(EXIT_USAGE, "usage: lab-ledger-account <incident>")
    ed = evidence_dir(incident)
    ops = load_jsonl(ed / "workload.jsonl")
    ledger = load_jsonl(ed / "db.jsonl")
    coverage = map_ops(ops, ledger)
    snap = ed / "snapshots.json"
    c6 = {"ok": snap.is_file() and not null_lsn_scan(snap) and lsns_monotonic(snap), "rule": "C-6"}
    lsns = [m["lsn"] for m in coverage["mapping"] if m.get("lsn")]
    from_lsn = min(lsns, key=lsn_int) if lsns else None
    integ = db_verify(ledger, from_lsn=from_lsn) if from_lsn else {"ok": False}
    c2 = {"ok": integ.get("key_only_count", 1) == 0 and integ.get("missing_identity_count", 1) == 0, "rule": "C-2"}
    c4 = {"ok": bool(integ.get("monotonic")), "rule": "C-4"}
    ddl_ops = [o for o in ops if o.get("action") in {"CREATE", "ALTER", "DROP"}]
    ddl_mapped = [m for m in coverage["mapping"] if m["key"][0] == "DDL"]
    c3 = {"ok": len(ddl_mapped) == len(ddl_ops) and bool(ddl_ops), "rule": "C-3",
          "ddl_ops": len(ddl_ops), "ddl_mapped": len(ddl_mapped)}
    c5 = heartbeat_ok(incident)
    c7 = fs_coverage(incident, ops)
    c1_ok = coverage["mapped"] == coverage["ops"] and not coverage["gaps"] and not coverage["duplicates"]
    rules = {
        "C-1": {"ok": c1_ok, **{k: coverage[k] for k in ("ops", "mapped", "gaps", "duplicates")}},
        "C-2": c2,
        "C-3": c3,
        "C-4": c4,
        "C-5": c5,
        "C-6": c6,
        "C-7": c7,
    }
    # do not include mapping principal; mapping sample is provenance-blind keys only
    ok = all(r.get("ok") for r in rules.values())
    report = {
        "ok": ok,
        "changed": False,
        "incident": incident,
        "ops": coverage["ops"],
        "mapped": coverage["mapped"],
        "gaps": len(coverage["gaps"]),
        "duplicates": len(coverage["duplicates"]),
        "gap_detail": coverage["gaps"][:20],
        "duplicate_detail": coverage["duplicates"][:20],
        "rules": {k: {ik: iv for ik, iv in v.items() if ik != "samples"} for k, v in rules.items()},
        "mapping_sample": coverage["mapping"][:3],
        "principal_read": False,
    }
    emit(report)
    return 0 if ok else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
