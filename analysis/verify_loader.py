#!/usr/bin/env python3
"""Mechanical negative tests for the P8 analysis loader."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from loader import Frame, comparison_view, load_active  # noqa: E402


def verify() -> dict:
    base = load_active()
    checks = {}
    try:
        comparison_view(Frame(({**base.rows[0], "principal": "lab_agent"},), base.metadata))
        checks["principal_guard"] = {"caught": False}
    except ValueError as exc:
        checks["principal_guard"] = {"caught": True, "message": str(exc)}
    try:
        load_active(ROOT / "results/fixtures/SC-01.jsonl")
        checks["fixtures_guard"] = {"caught": False}
    except ValueError as exc:
        checks["fixtures_guard"] = {"caught": True, "message": str(exc)}
    manifest = json.loads((ROOT / "results/superseded_manifest.json").read_text(encoding="utf-8"))
    predecessor = manifest["recoverable"][0]["predecessor"]
    rows = [json.loads(line) for line in (ROOT / "results/matrix.jsonl").read_text(encoding="utf-8").splitlines()]
    row = next(item for item in rows if item.get("run_id") == predecessor)
    try:
        load_active(injected_rows=[row])
        checks["superseded_guard"] = {"caught": False}
    except ValueError as exc:
        checks["superseded_guard"] = {"caught": True, "message": str(exc)}
    return {"ok": all(v["caught"] for v in checks.values()), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = verify()
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
