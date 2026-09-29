"""lab-ledger-verify implementation."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from lsn import lsn_int, lsn_norm

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3
CAP = 20


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def usage() -> None:
    die(
        EXIT_USAGE,
        "usage: lab-ledger-verify --incident <id> | "
        "--ledger <path> --open-lsn <lsn> --close-lsn <lsn>",
    )


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


def commit_records(rows: list[dict]) -> list[tuple[str, int, int]]:
    """Return (norm_lsn, lsn_int, index) for each commit (action C, or bare lsn)."""
    out = []
    for i, rec in enumerate(rows):
        action = rec.get("action")
        if action in {"B", "I", "U", "D", "T"}:
            continue
        if "lsn" not in rec:
            continue
        if action not in {None, "C"}:
            continue
        try:
            norm = lsn_norm(rec["lsn"])
            n = lsn_int(rec["lsn"])
        except ValueError as exc:
            die(EXIT_ASSERT, f"assertion failed: record {i}: {exc}")
        out.append((norm, n, i))
    return out


def verify(rows: list[dict], open_lsn: str, close_lsn: str, incident_id: str) -> dict:
    commits = commit_records(rows)
    open_n = lsn_int(open_lsn)
    close_n = lsn_int(close_lsn)
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    out_of_range: list[str] = []
    monotonic = True
    prev_n = None
    for norm, n, _idx in commits:
        if norm in seen:
            if norm not in duplicates:
                duplicates.append(norm)
        else:
            seen[norm] = 1
        if n < open_n or n > close_n:
            if norm not in out_of_range:
                out_of_range.append(norm)
        if prev_n is not None and n < prev_n:
            monotonic = False
        prev_n = n
    ok = not duplicates and not out_of_range and monotonic
    return {
        "incident_id": incident_id,
        "records": len(commits),
        "distinct_lsns": len(seen),
        "duplicate_lsns": duplicates[:CAP],
        "duplicate_lsns_count": len(duplicates),
        "open_lsn": lsn_norm(open_lsn),
        "close_lsn": lsn_norm(close_lsn),
        "out_of_range": out_of_range[:CAP],
        "out_of_range_count": len(out_of_range),
        "monotonic": monotonic,
        "ok": ok,
        "changed": False,
    }


def incident_paths(incident: str) -> tuple[Path, Path]:
    root = Path(os.environ["EVIDENCE_ROOT"])
    scenario = incident.split("_", 1)[0]
    evidence = root / scenario / incident
    ledger = evidence / "db.jsonl"
    meta = evidence / "incident.json"
    return ledger, meta


def main(argv: list[str]) -> int:
    incident = None
    ledger = None
    open_lsn = None
    close_lsn = None
    i = 0
    while i < len(argv):
        if argv[i] == "--incident" and i + 1 < len(argv):
            incident = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--ledger" and i + 1 < len(argv):
            ledger = Path(argv[i + 1])
            i += 2
            continue
        if argv[i] == "--open-lsn" and i + 1 < len(argv):
            open_lsn = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--close-lsn" and i + 1 < len(argv):
            close_lsn = argv[i + 1]
            i += 2
            continue
        usage()
    if incident:
        led_path, meta = incident_paths(incident)
        if not led_path.is_file():
            die(EXIT_PRECOND, f"precondition failed: ledger {led_path} is absent")
        if meta.is_file():
            doc = json.loads(meta.read_text(encoding="utf-8"))
            open_lsn = doc["open_coordinate"]["lsn"]
            close_lsn = doc["close_coordinate"]["lsn"]
        elif open_lsn is None or close_lsn is None:
            die(
                EXIT_PRECOND,
                "precondition failed: incident.json absent; pass --open-lsn and --close-lsn (test-only)",
            )
        ledger = led_path
        inc_id = incident
    else:
        if ledger is None or open_lsn is None or close_lsn is None:
            usage()
        inc_id = "test"
    if not ledger.is_file():
        die(EXIT_PRECOND, f"precondition failed: ledger {ledger} is absent")
    rows = load_jsonl(ledger)
    result = verify(rows, open_lsn, close_lsn, inc_id)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
