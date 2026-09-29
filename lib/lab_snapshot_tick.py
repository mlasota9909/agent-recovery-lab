"""C003: one LSN-anchored ZFS snapshot tick appended to the incident ledger."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from lab_paths import env, evidence_dir
from lsn import lsn_int, lsn_norm


def _ssh(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", env("VM_SSH"), script],
        text=True, capture_output=True, check=False,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def capture_lsn() -> tuple[str, str]:
    """Return (recorded_lsn, switch_lsn). Switch bounds the WAL segment (ADR-P2-3)."""
    port = env("PG_PORT")
    db = env("DB_NAME")
    proc = _ssh(
        "sudo -n -u postgres psql -X -v ON_ERROR_STOP=1 -At -F $'\\t' "
        f"-p {port} -d {db} -c \""
        "WITH captured AS MATERIALIZED ("
        "  SELECT pg_current_wal_lsn() AS lsn, clock_timestamp() AS captured_at"
        ") SELECT lsn::text, pg_switch_wal()::text FROM captured;\""
    )
    if proc.returncode != 0:
        raise SystemExit(f"assertion failed: cannot capture WAL LSN: {proc.stderr.strip()}")
    parts = proc.stdout.strip().split("\t")
    if len(parts) != 2:
        raise SystemExit(f"assertion failed: unexpected LSN capture output {proc.stdout!r}")
    recorded, switched = parts[0].upper(), parts[1].upper()
    lsn_norm(recorded)
    lsn_norm(switched)
    return recorded, switched


def unique_snapshot_name() -> str:
    prefix = env("SNAP_PREFIX")
    parent = env("DS_PARENT")
    while True:
        name = prefix + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        proc = _ssh(f"sudo -n zfs list -H -t snapshot -o name '{parent}@{name}' 2>/dev/null || true")
        if not proc.stdout.strip():
            return name
        time.sleep(1)


def zfs_snapshot(name: str) -> None:
    parent = env("DS_PARENT")
    proc = _ssh(f"sudo -n zfs snapshot -r '{parent}@{name}'")
    if proc.returncode != 0:
        raise SystemExit(f"assertion failed: zfs snapshot failed: {proc.stderr.strip()}")


def ledger_path(incident: str) -> Path:
    return evidence_dir(incident) / "snapshots.json"


def load_array(path: Path) -> list:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("assertion failed: snapshots.json is not an array")
    return data


def save_array(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".snapshots.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(records, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


_CAPTURE = object()


def append_anchored_snapshot(incident: str, lsn: str | None | object = _CAPTURE) -> dict:
    """Append one {snapshot, wall_clock, lsn} record. A null lsn is recorded as JSON null (C003 negative)."""
    name = unique_snapshot_name()
    if lsn is _CAPTURE:
        recorded, _switched = capture_lsn()
        lsn = lsn_norm(recorded)
    elif lsn is not None:
        lsn = lsn_norm(str(lsn))
    wall = utc_now()
    zfs_snapshot(name)
    path = ledger_path(incident)
    records = load_array(path)
    rec = {"snapshot": name, "wall_clock": wall, "lsn": lsn}
    records.append(rec)
    save_array(path, records)
    return rec


def null_lsn_scan(path: Path) -> list:
    records = load_array(path)
    return [r for r in records if r.get("lsn") is None]


def lsns_monotonic(path: Path) -> bool:
    records = load_array(path)
    prev = None
    for r in records:
        n = lsn_int(r["lsn"])
        if prev is not None and n < prev:
            return False
        prev = n
    return True
