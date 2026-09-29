"""Q007 step 3 (mutating, deliberately OUTSIDE the read-only gate): run bin/lab-regression
so every prior tranche passes against its pinned fixture. The P0-live regression reconciles
etc/lab.env from live state; as in P9, snapshot it and restore it, recording any drift.
Result -> logs/review/Q007/regression.json (read by lab-verify-p10)."""
from __future__ import annotations

import difflib
import json
import os
import subprocess
import sys

from lab_p10 import root, utc


def main(argv: list[str]) -> int:
    lab_env = root() / "etc" / "lab.env"
    before = lab_env.read_bytes()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + os.pathsep + str(root() / "analysis")
    t0 = utc()
    p = subprocess.run([str(root() / "bin" / "lab-regression")], cwd=str(root()), text=True, capture_output=True,
                       env=env, timeout=7200)
    after = lab_env.read_bytes()
    drift = None
    if after != before:
        drift = "".join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                             "lab.env.before", "lab.env.after"))
        lab_env.write_bytes(before)
    tail = [l for l in (p.stdout or "").strip().splitlines() if l.strip()][-3:]
    rec = {"started_utc": t0, "finished_utc": utc(), "exit": p.returncode, "ok": p.returncode == 0,
           "tail": tail, "lab_env_drift_reverted": drift, "stderr_tail": (p.stderr or "")[-600:]}
    out = root() / "logs" / "review" / "Q007" / "regression.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: rec[k] for k in ("exit", "ok", "tail")}, indent=1))
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
