"""lab-gate-readonly-check: evidence manifest before/after a named gate."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from lab_evidence_manifest import first_diff, write_manifest

EXIT_ASSERT = 1
EXIT_USAGE = 3


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parents[1])


def review() -> Path:
    path = root() / "logs" / "review" / "Z002"
    path.mkdir(parents=True, exist_ok=True)
    return path


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: lab-gate-readonly-check <gate> [gate-args...]", file=sys.stderr)
        return EXIT_USAGE
    gate = argv[0]
    args = argv[1:]
    cmd = [gate, *args] if os.path.isabs(gate) or "/" in gate else [str(root() / "bin" / gate), *args]
    before_path = review() / "manifest.before"
    after_path = review() / "manifest.after"
    before = write_manifest(before_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["LAB_READONLY_CHECK"] = "1"
    proc = subprocess.run(cmd, cwd=str(root()), text=True, capture_output=True, check=False, env=env, timeout=1800)
    after = write_manifest(after_path)
    changed = first_diff(before, after)
    sys.stdout.write(proc.stdout or "")
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if changed is not None:
        print(f"assertion failed: evidence mutated: first changed path {changed}", file=sys.stderr)
        return EXIT_ASSERT
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
