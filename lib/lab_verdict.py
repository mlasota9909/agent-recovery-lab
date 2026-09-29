"""E006: 4-level consistency verdict + full restore-report assembly."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lab_p4_util import (
    EXIT_ASSERT,
    die,
    git_head,
    restore_root,
    review_dir,
    tree_clean,
    victim_plus_evidence_manifest,
    write_json,
)

VERDICTS = ("correct", "incorrect-safe", "incorrect-corrupt", "not-recovered")
REQUIRED = (
    "incident_id", "restore_of", "coordinate", "db_validation", "fs_validation",
    "schema_validation", "summary", "consistency_verdict", "promotion",
    "restore_target", "safety", "selector_provenance", "harness_commit",
)


def verdict_of(validation: dict, usable: bool = True) -> str:
    if not usable:
        return "not-recovered"
    summary = validation.get("summary") or {}
    db_mis = (validation.get("db_validation") or {}).get("mismatches") or []
    classes = {m.get("classification") for m in db_mis}
    damage = int(summary.get("damage_rows_retained") or 0)
    legit = int(summary.get("legit_rows_lost") or 0)
    files = int(summary.get("files_mismatched") or 0)
    schema = int(summary.get("schema_diffs") or 0)
    if damage > 0 or "damage_retained" in classes:
        return "incorrect-corrupt"
    if legit > 0 or files > 0 or schema > 0 or "legit_lost" in classes:
        return "incorrect-safe"
    return "correct"


def assemble(incident: str, restore_of: str, task: str = "E006") -> dict:
    root = restore_root(incident, restore_of)
    partial = json.loads((root / "report.partial.json").read_text())
    validation = json.loads((root / "validation.json").read_text())
    usable = bool(partial.get("db_restore", {}).get("stopped_at_target", True))
    v = verdict_of(validation, usable=usable)
    after = victim_plus_evidence_manifest()
    before = (partial.get("safety") or {}).get("manifest_before")
    untouched = before == after["combined_sha256"]
    if not tree_clean():
        die(EXIT_ASSERT, "assertion failed: dirty tree; refusing to write restore report (Article XIV)")
    report = {
        "incident_id": partial["incident_id"],
        "restore_of": restore_of,
        "coordinate": partial["coordinate"],
        "db_validation": validation["db_validation"],
        "fs_validation": validation["fs_validation"],
        "schema_validation": validation["schema_validation"],
        "summary": validation["summary"],
        "consistency_verdict": v,
        "promotion": {
            "decision": "withheld",
            "clean_verdict": v == "correct",
            "authorized_by": None,
            "simulated": False,
        },
        "restore_target": partial["restore_target"],
        "safety": {
            "victim_untouched": untouched,
            "evidence_untouched": untouched,
            "manifest_before": before,
            "manifest_after": after["combined_sha256"],
        },
        "selector_provenance": partial["selector_provenance"],
        "harness_commit": git_head(),
    }
    missing = [k for k in REQUIRED if k not in report]
    if missing:
        die(EXIT_ASSERT, f"assertion failed: report missing {missing}")
    if v not in VERDICTS:
        die(EXIT_ASSERT, f"assertion failed: bad verdict {v}")
    write_json(root / "report.json", report)
    return report


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-verdict")
    p.add_argument("incident")
    p.add_argument("restore_of")
    p.add_argument("--task", default="E006")
    p.add_argument("--from-validation", default=None, help="optional JSON file of a validation block (unit cases)")
    args = p.parse_args(argv)
    if args.from_validation:
        val = json.loads(Path(args.from_validation).read_text())
        usable = bool(val.get("usable", True))
        print(json.dumps({"consistency_verdict": verdict_of(val, usable=usable)}, sort_keys=True))
        return 0
    out = assemble(args.incident, args.restore_of, args.task)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
