"""Resolve runtime settings for an explicit incident without changing the process."""
from __future__ import annotations

import os
import subprocess
import sys

from lab_paths import lab_root


def incident_runtime(incident: str) -> dict[str, str]:
    child_env = os.environ.copy()
    # Do not inherit a sibling's selected dataset or database settings.
    if child_env.get("INC_DS"):
        for key in ("DS_PARENT", "DS_PGDATA", "DS_PROTECTED", "PG_DATA", "PG_PORT",
                    "MNT_PROTECTED", "SLOT_NAME"):
            child_env.pop(key, None)
    for key in list(child_env):
        if key.startswith("INC_") or key in {"LAB_ACTIVE_INCIDENT", "ARCHIVE_INCIDENT"}:
            child_env.pop(key, None)
    proc = subprocess.run(
        ["bash", "-c", 'set -ae; source "$1/etc/lab.env"; '
         'export LAB_ACTIVE_INCIDENT="$2"; source "$1/lib/lab_incident_env.sh"; env -0',
         "incident-runtime", str(lab_root()), incident],
        env=child_env, text=True, capture_output=True, check=False,
    )
    if proc.returncode:
        print(proc.stderr.strip() or f"precondition failed: runtime absent for {incident}", file=sys.stderr)
        raise SystemExit(proc.returncode)
    return dict(row.split("=", 1) for row in proc.stdout.split("\0") if row)
