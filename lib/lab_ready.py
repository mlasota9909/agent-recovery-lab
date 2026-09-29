"""lab-ready: read-only P2-readiness gate. JSON on stdout. Never mutates state."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3
GROWTH_WINDOW_S = 2.0


def env(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        print(f"precondition failed: {key} missing from lab.env", file=sys.stderr)
        raise SystemExit(EXIT_PRECOND)
    return v


def bin_path(name: str) -> str:
    return str(Path(env("LAB_ROOT")) / "bin" / name)


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, env=os.environ)


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    if not proc.stdout.strip():
        return {"stderr": proc.stderr.strip(), "exit": proc.returncode}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"stdout": proc.stdout, "stderr": proc.stderr, "exit": proc.returncode}


def resolve_incident() -> str | None:
    current = Path(env("ARCHIVE_CURRENT"))
    if not current.is_symlink() and not current.exists():
        return None
    try:
        target = current.resolve()
    except OSError:
        return None
    archive_root = Path(env("ARCHIVE_ROOT")).resolve()
    try:
        target.relative_to(archive_root)
    except ValueError:
        return None
    name = target.name
    if not name.startswith("SC-"):
        return None
    return name


def evidence_ledger(incident: str) -> Path:
    scenario = incident.split("_", 1)[0]
    return Path(env("EVIDENCE_ROOT")) / scenario / incident / "db.jsonl"


def main(argv: list[str]) -> int:
    if argv:
        print("usage: lab-ready", file=sys.stderr)
        return EXIT_USAGE

    failed: list[str] = []
    incident = resolve_incident()
    consumer: dict = {}
    slot_check: dict = {}
    slot_before: dict = {}
    slot_after: dict = {}
    check_exit = None
    consumer_state = None
    slot_active = None
    invalidation_reason = None
    db_present = False
    db_path = None
    bytes_before = None
    bytes_after = None
    growth_signal = "none"
    db_growing = False
    retention_below_warn = False
    slot_check_ok = False

    if not incident:
        failed.append("incident")
    else:
        db_path = str(evidence_ledger(incident))
        ledger = Path(db_path)
        db_present = ledger.is_file()
        if not db_present:
            failed.append("db_jsonl_present")

        consumer_proc = run([bin_path("lab-consumer"), "status", incident])
        consumer = load_json(consumer_proc)
        consumer_state = consumer.get("unit_state")
        if isinstance(consumer_state, str):
            consumer_state = consumer_state.splitlines()[0]
        if consumer_state != "active":
            failed.append("consumer_unit_state")

        status_proc = run([bin_path("lab-slot"), "--status"])
        slot_check = load_json(status_proc)
        check_proc = run([bin_path("lab-slot"), "--check"])
        check_exit = check_proc.returncode
        slot_active = slot_check.get("active")
        invalidation_reason = slot_check.get("invalidation_reason")
        if invalidation_reason in ("", None):
            invalidation_reason = None
        if slot_active is not True:
            failed.append("slot_active")
        if invalidation_reason is not None:
            failed.append("invalidation_reason")
        over = bool(slot_check.get("over_threshold"))
        retention_below_warn = not over
        slot_check_ok = check_exit == 0 and not over
        if not slot_check_ok:
            failed.append("slot_check")

        if db_present:
            bytes_before = ledger.stat().st_size
            slot_before = {
                "confirmed_flush_lsn": slot_check.get("confirmed_flush_lsn"),
            }
            time.sleep(GROWTH_WINDOW_S)
            bytes_after = ledger.stat().st_size
            status_proc = run([bin_path("lab-slot"), "--status"])
            slot_after = load_json(status_proc)
            flush_before = slot_before.get("confirmed_flush_lsn")
            flush_after = slot_after.get("confirmed_flush_lsn")
            size_grew = bytes_after > bytes_before
            flush_moved = (
                isinstance(flush_before, str)
                and isinstance(flush_after, str)
                and flush_after != flush_before
            )
            if size_grew and flush_moved:
                growth_signal = "both"
            elif size_grew:
                growth_signal = "size"
            elif flush_moved:
                growth_signal = "flush_lsn"
            else:
                growth_signal = "none"
            db_growing = size_grew or flush_moved
            if not db_growing:
                failed.append("db_jsonl_growing")

    # de-duplicate while preserving order
    seen: set[str] = set()
    failed_unique = []
    for name in failed:
        if name not in seen:
            seen.add(name)
            failed_unique.append(name)
    failed = failed_unique

    ready = incident is not None and not failed
    payload = {
        "ok": ready,
        "changed": False,
        "ready": ready,
        "incident": incident,
        "consumer_unit_state": consumer_state,
        "slot_active": slot_active,
        "invalidation_reason": invalidation_reason,
        "slot_check": "ok" if slot_check_ok else "fail",
        "slot_check_exit": check_exit,
        "retention_below_warn": retention_below_warn,
        "retained_bytes": slot_check.get("retained_bytes") if slot_check else None,
        "warn_threshold_bytes": slot_check.get("warn_threshold_bytes") if slot_check else None,
        "slot_name": slot_check.get("slot_name") if slot_check else None,
        "db_jsonl_present": db_present,
        "db_jsonl_path": db_path,
        "db_jsonl_bytes_before": bytes_before,
        "db_jsonl_bytes_after": bytes_after,
        "db_jsonl_growing": db_growing,
        "growth_signal": growth_signal,
        "growth_window_s": GROWTH_WINDOW_S,
        "failed": failed,
        "consumer": consumer,
        "slot_after": {
            "confirmed_flush_lsn": slot_after.get("confirmed_flush_lsn") if slot_after else None,
        },
    }
    print(json.dumps(payload, sort_keys=True))
    if ready:
        return 0
    if "incident" in failed and incident is None:
        return EXIT_PRECOND
    return EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
