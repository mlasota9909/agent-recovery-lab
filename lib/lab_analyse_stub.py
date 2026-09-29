"""lab-analyse-stub: last snapshot at or before the incident close coordinate.

P3 will replace this file. The strategy is trivial and does not rank, score
anomalies, or inspect who caused a change.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from lsn import lsn_int
from views import analysis_view, load_ledger

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3

STRATEGY = "last_snapshot_at_or_before_close"


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def env(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        die(EXIT_PRECOND, f"precondition failed: {key} missing from lab.env")
    return v


def coordinate_from_snapshot(name: str) -> dict:
    cli = Path(os.environ["LAB_ROOT"]) / "bin" / "lab-coordinate"
    p = subprocess.run([str(cli), "--snapshot", name], text=True, capture_output=True, check=False)
    if p.returncode != 0:
        die(EXIT_PRECOND, f"precondition failed: lab-coordinate --snapshot: {p.stderr.strip()}")
    raw = json.loads(p.stdout)
    return {k: raw[k] for k in ("wall_clock", "lsn", "snapshot", "skew_ms", "skew_bytes", "resolved_by")}


def select_snapshot(incident: str, close_lsn: str, view: list[dict]) -> str:
    # view is accepted so the interface matches P3; the trivial strategy does
    # not inspect record bodies.
    _ = view
    archive = Path(env("ARCHIVE_ROOT")) / incident / "snapshots.json"
    if not archive.is_file():
        die(EXIT_PRECOND, f"precondition failed: {archive} is absent")
    rows = json.loads(archive.read_text(encoding="utf-8"))
    close_n = lsn_int(close_lsn)
    eligible = []
    for rec in rows:
        if rec.get("incident") != incident or rec.get("invalidated"):
            continue
        lsn = rec.get("recorded_lsn")
        if not isinstance(lsn, str):
            continue
        if lsn_int(lsn) <= close_n:
            eligible.append(rec)
    if not eligible:
        die(EXIT_ASSERT, "assertion failed: no snapshot at or before close coordinate")
    chosen = max(eligible, key=lambda r: (lsn_int(r["recorded_lsn"]), r.get("created_at", ""), r["snapshot"]))
    return chosen["snapshot"]


def main(argv: list[str]) -> int:
    incident = None
    view_path = None
    i = 0
    while i < len(argv):
        if argv[i] == "--incident" and i + 1 < len(argv):
            incident = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--view" and i + 1 < len(argv):
            view_path = Path(argv[i + 1])
            i += 2
            continue
        die(EXIT_USAGE, "usage: lab-analyse-stub --incident <id> [--view <analysis.json>]")
    if not incident:
        die(EXIT_USAGE, "usage: lab-analyse-stub --incident <id> [--view <analysis.json>]")
    scenario = incident.split("_", 1)[0]
    ev = Path(env("EVIDENCE_ROOT")) / scenario / incident
    meta = ev / "incident.json"
    if not meta.is_file():
        die(EXIT_PRECOND, f"precondition failed: {meta} is absent")
    doc = json.loads(meta.read_text(encoding="utf-8"))
    close_lsn = doc["close_coordinate"]["lsn"]
    if view_path is not None:
        view = json.loads(view_path.read_text(encoding="utf-8"))
        if not isinstance(view, list):
            die(EXIT_ASSERT, "assertion failed: view is not a list")
    else:
        view = analysis_view(load_ledger(ev / "db.jsonl"))
    snap = select_snapshot(incident, close_lsn, view)
    coord = coordinate_from_snapshot(snap)
    print(json.dumps({
        "ok": True,
        "changed": False,
        "strategy": STRATEGY,
        "coordinate": coord,
        "snapshot": snap,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
