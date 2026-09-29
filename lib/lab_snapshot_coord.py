"""Host-side coordinate resolution from an incident's snapshots.json.

lab-coordinate --lsn/--time queries the live guest heartbeat table. After T2
on a shared DS_PARENT, that table belongs to whichever incident was rolled
back last, so using it for a sibling incident maps the wrong WAL. P7 therefore
resolves coordinates from the frozen archive manifest (same snapshot_first
shape as lab-coordinate --snapshot). Archive snapshots are the T2-equivalent
set: post-capture ticks newer than the restore target would be destroyed by
`zfs rollback -r`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lab_paths import env, evidence_dir
from lsn import lsn_int, lsn_norm

COORD_FIELDS = ("wall_clock", "lsn", "snapshot", "skew_ms", "skew_bytes", "resolved_by")


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def rec_lsn(rec: dict) -> str | None:
    raw = rec.get("recorded_lsn") or rec.get("lsn")
    return str(raw) if raw else None


def rec_time(rec: dict) -> str | None:
    return rec.get("created_at") or rec.get("lsn_recorded_at") or rec.get("wall_clock")


def load_incident_snapshots(incident: str) -> list[dict]:
    archive = Path(env("ARCHIVE_ROOT")) / incident / "snapshots.json"
    ev = evidence_dir(incident) / "snapshots.json"
    path = archive if archive.is_file() else ev
    if not path.is_file():
        raise SystemExit(f"precondition failed: {path} is absent")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"assertion failed: {path} is not an array")
    out = []
    for rec in rows:
        if rec.get("invalidated"):
            continue
        if rec.get("incident") and rec.get("incident") != incident:
            continue
        if not rec_lsn(rec) or not rec.get("snapshot"):
            continue
        out.append(rec)
    if not out:
        raise SystemExit(f"precondition failed: no usable snapshots for {incident}")
    return out


def _coord(rec: dict, lsn: str) -> dict:
    wall = rec_time(rec) or rec.get("wall_clock")
    return {
        "wall_clock": wall,
        "lsn": lsn_norm(lsn),
        "snapshot": rec["snapshot"],
        "skew_ms": 0,
        "skew_bytes": 0,
        "resolved_by": "snapshot_first",
    }


def resolve_lsn_from_manifest(incident: str, lsn: str) -> dict:
    target = lsn_norm(lsn)
    target_n = lsn_int(target)
    eligible = []
    for rec in load_incident_snapshots(incident):
        raw = rec_lsn(rec)
        if raw is None:
            continue
        if lsn_int(lsn_norm(raw)) <= target_n:
            eligible.append(rec)
    if not eligible:
        raise SystemExit(f"assertion failed: no snapshot at or below {target} in {incident}")
    rec = max(eligible, key=lambda r: (lsn_int(lsn_norm(rec_lsn(r))), rec_time(r) or ""))
    return _coord(rec, target)


def resolve_time_from_manifest(incident: str, ts: str) -> dict:
    cutoff = _parse_ts(ts)
    eligible = []
    for rec in load_incident_snapshots(incident):
        created = rec_time(rec)
        if not created:
            continue
        if _parse_ts(created) <= cutoff:
            eligible.append(rec)
    if not eligible:
        raise SystemExit(f"assertion failed: no snapshot at or before {ts} in {incident}")
    rec = max(eligible, key=lambda r: (lsn_int(lsn_norm(rec_lsn(r))), rec_time(r) or ""))
    return _coord(rec, rec_lsn(rec))


def naive_from_manifest(incident: str, approx_incident_time: str, error_seconds: int) -> dict:
    cutoff = _parse_ts(approx_incident_time) + timedelta(seconds=int(error_seconds))
    cutoff_iso = cutoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return resolve_time_from_manifest(incident, cutoff_iso)
