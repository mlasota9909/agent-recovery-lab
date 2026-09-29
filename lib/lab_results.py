"""CLI implementation for bin/lab-results. Invoked by the bash wrapper."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

from results_schema import canonical_json, load_schema, validate_row

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def usage() -> None:
    die(EXIT_USAGE, "usage: lab-results append|validate|close --file <path> [--row <json|->]")


def is_closed(path: Path) -> bool:
    if not path.exists():
        return False
    mode = path.stat().st_mode & 0o777
    return mode == 0o444


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
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


def load_row_arg(raw: str) -> dict:
    if raw == "-":
        text = sys.stdin.read()
    else:
        text = raw
        p = Path(raw)
        if p.is_file():
            text = p.read_text(encoding="utf-8")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        die(EXIT_USAGE, f"usage: --row is not JSON: {exc}")
    if not isinstance(obj, dict):
        die(EXIT_USAGE, "usage: --row must be a JSON object")
    return obj


def cmd_append(path: Path, row: dict) -> None:
    schema = load_schema()
    errors = validate_row(schema, row)
    if errors:
        die(EXIT_ASSERT, "assertion failed: row rejected: " + "; ".join(errors))
    if is_closed(path):
        die(
            EXIT_ASSERT,
            f"assertion failed: results file is closed (mode 0444): {path}",
        )
    existing = read_rows(path)
    run_id = row["run_id"]
    for prev in existing:
        if prev.get("run_id") == run_id:
            die(EXIT_ASSERT, f"assertion failed: duplicate run_id {run_id}")
        if prev.get("incident_id") == row.get("incident_id"):
            prev_gt = canonical_json(prev.get("ground_truth_coordinate"))
            new_gt = canonical_json(row.get("ground_truth_coordinate"))
            if prev_gt != new_gt:
                die(
                    EXIT_ASSERT,
                    "assertion failed: ground_truth_coordinate is not byte-identical "
                    f"for incident_id {row.get('incident_id')}",
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())
    print(json.dumps({"ok": True, "changed": True, "run_id": run_id, "file": str(path)}, sort_keys=True))


def cmd_validate(path: Path) -> None:
    schema = load_schema()
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: results file {path} is absent")
    rows = read_rows(path)
    results = []
    fails = 0
    seen_gt: dict[str, str] = {}
    seen_ids: set[str] = set()
    for i, row in enumerate(rows):
        errors = validate_row(schema, row)
        run_id = row.get("run_id")
        if isinstance(run_id, str):
            if run_id in seen_ids:
                errors.append(f"duplicate run_id {run_id}")
            seen_ids.add(run_id)
        inc = row.get("incident_id")
        if isinstance(inc, str) and "ground_truth_coordinate" in row:
            canon = canonical_json(row.get("ground_truth_coordinate"))
            prev = seen_gt.get(inc)
            if prev is None:
                seen_gt[inc] = canon
            elif prev != canon:
                errors.append("ground_truth_coordinate mismatch for incident_id")
        ok = not errors
        if not ok:
            fails += 1
        results.append({"index": i, "run_id": run_id, "ok": ok, "errors": errors})
    payload = {
        "ok": fails == 0,
        "changed": False,
        "file": str(path),
        "rows": len(rows),
        "passed": len(rows) - fails,
        "failed": fails,
        "results": results,
    }
    print(json.dumps(payload, sort_keys=True))
    if fails:
        raise SystemExit(EXIT_ASSERT)


def cmd_close(path: Path) -> None:
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: results file {path} is absent")
    mode = path.stat().st_mode & 0o777
    if mode == 0o444:
        print(json.dumps({"ok": True, "changed": False, "file": str(path), "mode": "444"}, sort_keys=True))
        return
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    print(json.dumps({"ok": True, "changed": True, "file": str(path), "mode": "444"}, sort_keys=True))


def main(argv: list[str]) -> int:
    if len(argv) < 1:
        usage()
    action = argv[0]
    file_path = None
    row_raw = None
    i = 1
    while i < len(argv):
        if argv[i] == "--file" and i + 1 < len(argv):
            file_path = Path(argv[i + 1])
            i += 2
            continue
        if argv[i] == "--row" and i + 1 < len(argv):
            row_raw = argv[i + 1]
            i += 2
            continue
        usage()
    if file_path is None:
        usage()
    if action == "append":
        if row_raw is None:
            die(EXIT_USAGE, "usage: lab-results append --file <path> --row <json|->")
        cmd_append(file_path, load_row_arg(row_raw))
        return 0
    if action == "validate":
        cmd_validate(file_path)
        return 0
    if action == "close":
        cmd_close(file_path)
        return 0
    usage()
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
