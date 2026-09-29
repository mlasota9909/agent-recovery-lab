"""Capture every recorded file interval and snapshot, failing on missing evidence."""
from __future__ import annotations

from lab_p3_util import die, run_bin
from lab_snapshot_tick import merge_snapshot_records


def capture_file_evidence(incident: str, log: list[dict], runner=None) -> None:
    runner = runner or run_bin
    records = merge_snapshot_records(incident)
    if len(records) < 2 or any(not r.get("lsn") or r.get("invalidated") for r in records):
        die(1, "assertion failed: file capture requires at least two valid anchored snapshots")
    names = [r["snapshot"] for r in records]
    commands = [["diff", a, b] for a, b in zip(names, names[1:])]
    commands.extend(["hash", name] for name in names)
    for args in commands:
        args += ["--incident", incident]
        proc = runner("lab-fs-capture", args, timeout=120)
        log.append({"step": "fs_capture", "args": args, "exit": proc.returncode,
                    "stdout": (proc.stdout or "")[-800:], "stderr": (proc.stderr or "")[-800:]})
        if proc.returncode:
            die(proc.returncode, proc.stderr.strip() or proc.stdout.strip() or
                f"assertion failed: file capture exited {proc.returncode}")
