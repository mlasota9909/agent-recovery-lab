"""Stamp wal2json envelope xid onto change/ddl records. Heartbeats are exempt.

Reads plugin JSON from a child pg_recvlogical writing to stdout (-f -).
Not a WAL parser: it only forwards wal2json objects and copies xid from action=B.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from typing import IO

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def stamp_record(rec: dict, current_xid: int | None, heartbeat_table: str) -> tuple[dict, int | None]:
    action = rec.get("action")
    table = rec.get("table")
    if action == "B":
        xid = rec.get("xid")
        if xid is None:
            die(EXIT_ASSERT, "assertion failed: wal2json begin record has no xid; envelope xid is unrecoverable")
        return rec, int(xid) & 0xFFFFFFFF
    if action == "C":
        return rec, None
    if action in {"I", "U", "D", "T"}:
        if table == heartbeat_table:
            return rec, current_xid
        if current_xid is None:
            die(EXIT_ASSERT, "assertion failed: change/ddl record with no enclosing begin xid")
        existing = rec.get("xid")
        if existing is not None and (int(existing) & 0xFFFFFFFF) != current_xid:
            die(EXIT_ASSERT, f"assertion failed: change xid {existing} != envelope xid {current_xid}")
        rec = dict(rec)
        rec["xid"] = current_xid
        return rec, current_xid
    return rec, current_xid


def pump(src: IO[str], dest: IO[str], heartbeat_table: str) -> None:
    current_xid: int | None = None
    for raw in src:
        line = raw.strip()
        if not line:
            continue
        rec = json.loads(line)
        rec, current_xid = stamp_record(rec, current_xid, heartbeat_table)
        dest.write(json.dumps(rec, separators=(",", ":")) + "\n")
        dest.flush()


def main(argv: list[str]) -> int:
    output = None
    heartbeat_table = os.environ.get("HEARTBEAT_TABLE", "lab_heartbeat")
    child: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--output" and i + 1 < len(argv):
            output = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--heartbeat-table" and i + 1 < len(argv):
            heartbeat_table = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--":
            child = argv[i + 1 :]
            break
        die(EXIT_USAGE, "usage: lab_wal2json_xid.py --output PATH [--heartbeat-table NAME] -- pg_recvlogical ...")
    if not output or not child:
        die(EXIT_USAGE, "usage: lab_wal2json_xid.py --output PATH -- pg_recvlogical ...")
    dest_path = output
    proc = subprocess.Popen(
        child,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
    )

    def _forward(signum: int, _frame: object) -> None:
        if proc.poll() is None:
            proc.send_signal(signum)

    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT, _forward)
    assert proc.stdout is not None
    try:
        with open(dest_path, "a", encoding="utf-8") as dest:
            pump(proc.stdout, dest, heartbeat_table)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
