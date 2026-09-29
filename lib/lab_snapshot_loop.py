"""Host-side snapshot loop process launched by lab-capture.

C002: keep the process alive and stamp liveness. C003 fills in LSN-anchored
ZFS snapshots into the incident ledger snapshots.json.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lab_paths import env, evidence_dir


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def pid_file(incident: str) -> Path:
    return evidence_dir(incident) / ".snapshot-loop.pid"


def alive_file(incident: str) -> Path:
    return evidence_dir(incident) / ".snapshot-loop.alive"


def ledger_snapshots(incident: str) -> Path:
    return evidence_dir(incident) / "snapshots.json"


def interval_s() -> float:
    raw = os.environ.get("SNAP_INTERVAL_S", "")
    if not raw:
        print("precondition failed: SNAP_INTERVAL_S missing from lab.env", file=sys.stderr)
        raise SystemExit(2)
    try:
        value = float(raw)
    except ValueError as exc:
        raise SystemExit("precondition failed: SNAP_INTERVAL_S is not a number") from exc
    if value <= 0:
        raise SystemExit("precondition failed: SNAP_INTERVAL_S must be positive")
    return value


def stamp_alive(incident: str) -> None:
    path = alive_file(incident)
    path.write_text(utc_now() + "\n", encoding="utf-8")


def take_snapshot_tick(incident: str) -> None:
    """C003 replaces the no-op with LSN-anchored zfs snapshot + ledger append.

    C002 only stamps liveness so lab-capture status can see a living process.
    """
    stamp_alive(incident)
    # LSN anchoring is owned by C003 (lab_snapshot_loop_tick).
    hook = os.environ.get("LAB_SNAPSHOT_LOOP_HOOK", "")
    if hook == "lsn":
        from lab_snapshot_tick import append_anchored_snapshot  # type: ignore

        append_anchored_snapshot(incident)


def run_loop(incident: str) -> int:
    evidence_dir(incident).mkdir(parents=True, exist_ok=True)
    pid_file(incident).write_text(str(os.getpid()) + "\n", encoding="utf-8")
    stop = {"flag": False}

    def _stop(_signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    interval = interval_s()
    while not stop["flag"]:
        take_snapshot_tick(incident)
        deadline = time.monotonic() + interval
        while not stop["flag"] and time.monotonic() < deadline:
            time.sleep(min(0.2, deadline - time.monotonic()))
    try:
        pid_file(incident).unlink()
    except FileNotFoundError:
        pass
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--incident":
        print("usage: lab-snapshot-loop --incident <id>", file=sys.stderr)
        return 3
    return run_loop(argv[1])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
