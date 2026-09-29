"""lab-barrier: poll lab-slot --check until exit 0 or timeout. Never proceeds degraded."""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def poll_wait(seconds: float) -> None:
    """Bounded wait between polls. Not a guessed catch-up interval; --check is the predicate."""
    select.select([], [], [], seconds)


def main(argv: list[str]) -> int:
    timeout_s = os.environ.get("BARRIER_TIMEOUT_S", "")
    if not timeout_s:
        die(EXIT_PRECOND, "precondition failed: BARRIER_TIMEOUT_S missing from lab.env")
    timeout = float(timeout_s)
    i = 0
    while i < len(argv):
        if argv[i] == "--timeout" and i + 1 < len(argv):
            timeout = float(argv[i + 1])
            i += 2
            continue
        die(EXIT_USAGE, "usage: lab-barrier [--timeout <s>]")
    root = Path(os.environ["LAB_ROOT"])
    slot = root / "bin" / "lab-slot"
    started = time.monotonic()
    deadline = started + timeout
    attempts = 0
    last_stdout = ""
    last_stderr = ""
    last_code = 1
    while True:
        attempts += 1
        proc = subprocess.run(
            [str(slot), "--check"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        last_code = proc.returncode
        last_stdout = proc.stdout.strip()
        last_stderr = proc.stderr.strip()
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if proc.returncode == 0:
            slot_state = json.loads(last_stdout) if last_stdout else {}
            print(
                json.dumps(
                    {
                        "ok": True,
                        "changed": False,
                        "attempts": attempts,
                        "elapsed_ms": elapsed_ms,
                        "slot": slot_state,
                        "timed_out": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if time.monotonic() >= deadline:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "changed": False,
                        "attempts": attempts,
                        "elapsed_ms": elapsed_ms,
                        "timed_out": True,
                        "check_exit": last_code,
                        "check_stderr": last_stderr,
                    },
                    sort_keys=True,
                )
            )
            print(
                f"lab-barrier: timed out after {elapsed_ms} ms waiting for lab-slot --check",
                file=sys.stderr,
            )
            return EXIT_ASSERT
        remaining = deadline - time.monotonic()
        poll_wait(min(0.5, max(0.05, remaining)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
