"""Fixed-cadence snapshot loop with a durable completion/failure record."""
from __future__ import annotations

import json
import math
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from lab_paths import evidence_dir
from lab_snapshot_tick import append_anchored_snapshot, utc_now


def pid_file(incident: str) -> Path:
    return evidence_dir(incident) / ".snapshot-loop.pid"


def alive_file(incident: str) -> Path:
    return evidence_dir(incident) / ".snapshot-loop.alive"


def status_file(incident: str) -> Path:
    return evidence_dir(incident) / "snapshot-loop-status.json"


def ledger_snapshots(incident: str) -> Path:
    return evidence_dir(incident) / "snapshots.json"


def interval_s() -> float:
    value = float(os.environ.get("SNAP_INTERVAL_S") or "2")
    if not math.isfinite(value) or value <= 0:
        raise ValueError("precondition failed: SNAP_INTERVAL_S must be positive and finite")
    return value


def write_status(incident: str, status: dict) -> None:
    path = status_file(incident)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_status(incident: str) -> dict:
    path = status_file(incident)
    return json.loads(path.read_text()) if path.is_file() else {}


def take_snapshot_tick(incident: str) -> dict:
    record = append_anchored_snapshot(incident)
    alive_file(incident).write_text(record["created_at"] + "\n", encoding="utf-8")
    return record


def check_gap(gap: float, interval: float) -> None:
    if gap > 2 * interval:
        raise RuntimeError(f"snapshot loop missed an interval by more than one period: gap={gap:.3f}s, period={interval:g}s")


def run_loop(incident: str) -> int:
    evidence_dir(incident).mkdir(parents=True, exist_ok=True)
    stop = {"flag": False}

    def _stop(_signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    status = {"state": "running", "ok": False, "ticks": 0, "started_at": utc_now(), "max_gap_s": 0.0}
    pid_file(incident).write_text(str(os.getpid()) + "\n", encoding="utf-8")
    write_status(incident, status)
    try:
        interval = interval_s()
        status["interval_s"] = interval
        deadline = previous = time.monotonic()
        previous_snapshot = None
        while not stop["flag"]:
            record = take_snapshot_tick(incident)
            now = time.monotonic()
            gap = now - previous
            status["max_gap_s"] = max(status["max_gap_s"], gap)
            check_gap(gap, interval)
            snapshot_at = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
            if previous_snapshot is not None:
                snapshot_gap = (snapshot_at - previous_snapshot).total_seconds()
                status["max_gap_s"] = max(status["max_gap_s"], snapshot_gap)
                check_gap(snapshot_gap, interval)
            previous_snapshot = snapshot_at
            status["ticks"] += 1
            status.setdefault("first_snapshot_at", record["created_at"])
            status["last_snapshot_at"] = record["created_at"]
            write_status(incident, status)
            previous = now
            # Fixed-rate schedule. A tick delayed by the snapshot lock moves the
            # schedule instead of carrying its lag into every later deadline;
            # check_gap still fails any gap longer than two periods.
            deadline = max(deadline + interval, now)
            while not stop["flag"] and time.monotonic() < deadline:
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        gap = time.monotonic() - previous
        status["max_gap_s"] = max(status["max_gap_s"], gap)
        check_gap(gap, interval)
        status.update(state="stopped", ok=status["ticks"] > 0)
    except BaseException as exc:
        status.update(state="failed", ok=False, error=str(exc))
        print(str(exc), file=sys.stderr)
    finally:
        status["stopped_at"] = utc_now()
        write_status(incident, status)
        pid_file(incident).unlink(missing_ok=True)
    return 0 if status["ok"] else 1


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--incident":
        print("usage: lab-snapshot-loop --incident <id>", file=sys.stderr)
        return 3
    return run_loop(argv[1])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
