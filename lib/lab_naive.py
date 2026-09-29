"""lab-naive: last checkpoint before approx_incident_time + declared error."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lab_analytics import p3_dir
from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, require_lab, run_json, scenario_config,
    validate_arm, write_json,
)
from lab_paths import evidence_dir
from lsn import lsn_int


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def naive(incident: str, error_override: int | None = None) -> dict:
    require_lab()
    cfg = scenario_config()
    meta = json.loads((evidence_dir(incident) / "incident.json").read_text(encoding="utf-8"))
    error = int(error_override if error_override is not None else cfg["SC01_NAIVE_TIME_ERROR_SECONDS"])
    approx = meta.get("approx_incident_time")
    if not approx:
        die(EXIT_PRECOND, "precondition failed: incident.json lacks approx_incident_time")
    cutoff = parse_ts(approx) + timedelta(seconds=error)
    cutoff_iso = iso(cutoff)
    # Resolve last heartbeat/checkpoint at or below cutoff via lab-coordinate --time.
    coord = run_json("lab-coordinate", ["--time", cutoff_iso[:26].rstrip("0") + "Z" if False else cutoff_iso])
    rec = {
        "incident_id": meta["incident_id"],
        "arm": "naive",
        "selector_version": cfg.get("SC01_NAIVE_SELECTOR_VERSION", "p3-naive-1"),
        "representation": "n/a",
        "lsn_text": coord["lsn"],
        "lsn_int": lsn_int(coord["lsn"]),
        "wall_clock": coord["wall_clock"],
        "snapshot": coord["snapshot"],
        "chosen_candidate_id": None,
        "rationale": "last checkpoint before operator-estimated incident time + declared error",
        "selection_inputs": {
            "ledger_view": "db_changes",
            "approx_incident_time": approx,
            "incident_time_error_seconds": error,
            "read_injection_log": False,
            "read_oracle_optimum": False,
            "read_provenance": False,
        },
    }
    errs = validate_arm(rec)
    if errs:
        die(EXIT_ASSERT, f"assertion failed: arm-coordinate: {errs}")
    write_json(p3_dir(incident) / "naive-coordinate.json", rec)
    print(json.dumps({"ok": True, "changed": True, "incident": incident, "coordinate": rec,
                      "cutoff": cutoff_iso, "declared_error_seconds": error}, sort_keys=True))
    return rec


def main(argv: list[str]) -> int:
    incident = None
    error = None
    i = 0
    while i < len(argv):
        if argv[i] == "--error-seconds" and i + 1 < len(argv):
            error = int(argv[i + 1]); i += 2; continue
        if incident is None and not argv[i].startswith("--"):
            incident = argv[i]; i += 1; continue
        die(EXIT_USAGE, "usage: lab-naive <incident> [--error-seconds N]")
    if not incident:
        die(EXIT_USAGE, "usage: lab-naive <incident>")
    naive(incident, error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
