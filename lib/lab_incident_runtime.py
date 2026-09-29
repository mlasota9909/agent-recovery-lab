"""Resolve runtime settings for an explicit incident without changing the process."""
from __future__ import annotations

import json
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


def stop_finished_incident_clusters() -> list[dict]:
    """Stop every isolated incident cluster before a new incident is prepared.

    All clusters archive through the host channel into whatever archive/current
    names, and a fresh cluster's WAL segment names repeat an earlier cluster's, so
    a finished cluster that keeps archiving would take the new incident's segment
    names. Datasets, snapshots and archived WAL stay in place for restores.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("LAB_SITE_SCOPE", "LAB_ACTIVE_INCIDENT")}
    stopped = []
    for record in sorted((lab_root() / "runtime" / "incidents").glob("*.env")):
        name = next((line.split("=", 1)[1] for line in record.read_text(encoding="utf-8").splitlines()
                     if line.startswith("ARCHIVE_INCIDENT=")), None)
        if not name:
            continue
        proc = subprocess.run([str(lab_root() / "bin" / "lab-incident-dataset"), "stop", "--incident", name],
                              env=env, text=True, capture_output=True, check=False, timeout=180)
        if proc.returncode:
            raise RuntimeError(f"cannot stop incident cluster {name}: {proc.stderr.strip() or proc.stdout.strip()}")
        stopped.append(json.loads(proc.stdout.strip().splitlines()[-1]))
    return stopped
