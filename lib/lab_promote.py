"""E007: promotion gate. Lab simulation only. Never authorized, never destructive."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lab_p4_util import (
    EXIT_ASSERT,
    EXIT_USAGE,
    die,
    restore_root,
    review_dir,
    victim_plus_evidence_manifest,
    write_json,
)


def promote(incident: str, restore_of: str, token: str | None, task: str = "E007") -> dict:
    report_path = restore_root(incident, restore_of) / "report.json"
    if not report_path.is_file():
        die(EXIT_USAGE, f"usage: missing {report_path}")
    report = json.loads(report_path.read_text())
    verdict = report.get("consistency_verdict")
    before = victim_plus_evidence_manifest()
    decision = "withheld"
    reason = None
    if verdict != "correct":
        reason = "verdict not correct"
    elif not token:
        reason = "no authorization token"
    else:
        decision = "simulated"
    if decision == "authorized":
        die(EXIT_ASSERT, "assertion failed: lab must never emit decision=authorized")
    rec = {
        "incident_id": incident,
        "requested_of": restore_of,
        "consistency_verdict": verdict,
        "authorization": {
            "token_supplied": bool(token),
            "authorized_by": "operator:token" if token else None,
            "token_ref": str(token) if token else None,
        },
        "decision": decision,
        "simulation": {
            "would_replace": "labpool/victim/protected + labdb cluster",
            "action_taken": "logged only; victim untouched",
        },
        "safety": {
            "victim_untouched": True,
            "evidence_untouched": True,
        },
        "reason": reason,
    }
    after = victim_plus_evidence_manifest()
    rec["safety"]["victim_untouched"] = before["combined_sha256"] == after["combined_sha256"]
    rec["safety"]["evidence_untouched"] = rec["safety"]["victim_untouched"]
    rec["safety"]["manifest_before"] = before["combined_sha256"]
    rec["safety"]["manifest_after"] = after["combined_sha256"]
    write_json(restore_root(incident, restore_of) / "promotion.json", rec)
    if decision == "simulated":
        report["promotion"] = {
            "decision": "simulated",
            "clean_verdict": True,
            "authorized_by": rec["authorization"]["authorized_by"],
            "simulated": True,
        }
        write_json(report_path, report)
    if reason:
        print(json.dumps(rec, sort_keys=True))
        die(EXIT_ASSERT, f"assertion failed: {reason}")
    print(json.dumps(rec, sort_keys=True))
    return rec


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-promote")
    p.add_argument("incident")
    p.add_argument("restore_of")
    p.add_argument("--authorize", default=None)
    p.add_argument("--task", default="E007")
    args = p.parse_args(argv)
    promote(args.incident, args.restore_of, args.authorize, args.task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
