#!/usr/bin/env python3
"""Return the P7.1 active matrix partition; never aggregate superseded rows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from lab_p71_l004 import derive, matrix_outcome  # noqa: E402


def query(matrix: Path, injected_ids: list[str] | None = None) -> dict:
    report, active, mappings = derive(matrix)
    if not report["ok"]:
        raise ValueError("active-partition derivation failed: " + "; ".join(report["errors"]))
    active_ids = {row["run_id"] for row in active}
    superseded_ids = {m["predecessor"] for m in mappings}
    injected = sorted(set(injected_ids or []))
    admitted_injected = sorted(active_ids.intersection(injected))
    excluded_injected = sorted(set(injected).intersection(superseded_ids))
    unknown_injected = sorted(set(injected) - active_ids - superseded_ids)
    if admitted_injected or unknown_injected:
        raise ValueError(f"injected ids are not known superseded rows: {admitted_injected + unknown_injected}")
    return {
        "ok": True,
        "physical_rows": report["physical_rows"],
        "active_total": len(active),
        "partition": {
            "determinations": sum(matrix_outcome(r) == "determination" for r in active),
            "refusals": sum(matrix_outcome(r) == "refusal" for r in active),
            "run_failures": sum(matrix_outcome(r) == "run_failure" for r in active),
        },
        "superseded_excluded": report["partition"]["superseded"],
        "source_row_ids": sorted(active_ids),
        "negative_probe": {
            "injected": injected,
            "excluded_as_superseded": excluded_injected,
            "active_total_after_injection": len(active),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=ROOT / "results/matrix.jsonl")
    parser.add_argument("--inject-superseded-id", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = query(args.matrix, args.inject_superseded_id)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"assertion failed: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
