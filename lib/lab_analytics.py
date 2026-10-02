"""lab-analytics: provenance-blind derived window metrics over lab-query views."""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from provenance_fields import KEYS
from lab_p3_util import (
    EXIT_ASSERT, EXIT_USAGE, canonical_json, die, load_jsonl, require_lab,
    scenario_config, write_json, write_jsonl, write_text,
)
from lab_paths import evidence_dir
from lab_query import run_sql
from lsn import lsn_int, lsn_norm


def parse_ts(ts: str) -> datetime:
    text = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def p3_dir(incident: str) -> Path:
    path = evidence_dir(incident) / "p3"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch(incident: str, sql: str) -> list[dict]:
    if any(k in sql for k in KEYS):
        die(EXIT_ASSERT, "assertion failed: analytics SQL references a provenance field")
    raw = run_sql(incident, sql)
    raw = raw.strip()
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        return [data]
    return data


def by_position(rows: list[dict]) -> list[dict]:
    """Order rows by numeric log position. The views hold positions as text, and text order breaks where the low
    part gains a hex digit (0/FFFFFFF to 0/10000000): the first heartbeat, which anchors the windows, was then taken
    from the middle of the incident and earlier windows were numbered below zero."""
    return sorted(rows, key=lambda r: lsn_int(lsn_norm(str(r["lsn"]))))


def analytics(incident: str) -> dict:
    require_lab()
    cfg = scenario_config()
    window_s = int(cfg.get("SC01_WINDOW_S", "2"))
    version = cfg.get("SC01_ANALYTICS_VERSION", "p3-analytics-1")
    hbs = by_position(fetch(incident, """
        SELECT lsn, timestamp FROM heartbeats
        WHERE lsn IS NOT NULL AND timestamp IS NOT NULL
        ORDER BY lsn
    """))
    changes = by_position(fetch(incident, """
        SELECT action, lsn, timestamp, "table" FROM db_changes
        WHERE lsn IS NOT NULL
        ORDER BY lsn
    """))
    ddl = fetch(incident, """
        SELECT lsn, timestamp FROM ddl_events
        WHERE lsn IS NOT NULL
        ORDER BY lsn
    """)
    fs = fetch(incident, """
        SELECT snap_from, snap_to, change_type, path FROM fs_diff
        ORDER BY snap_from, snap_to, path
    """)
    snaps = fetch(incident, "SELECT snapshot, wall_clock, lsn FROM snapshots ORDER BY lsn")

    if not hbs:
        die(EXIT_ASSERT, "assertion failed: no heartbeats to bucket windows")

    def rec_time(rec: dict) -> datetime | None:
        ts = rec.get("timestamp") or rec.get("wall_clock")
        if not ts:
            return None
        return parse_ts(str(ts))

    t0 = rec_time(hbs[0])
    if t0 is None:
        die(EXIT_ASSERT, "assertion failed: heartbeat timestamp missing")

    def bucket(ts: datetime) -> int:
        return int((ts - t0).total_seconds() // window_s)

    windows: dict[int, dict] = {}

    def win(idx: int) -> dict:
        if idx not in windows:
            windows[idx] = {
                "window_id": idx,
                "t_start": None,
                "t_end": None,
                "lsn_start": None,
                "lsn_end": None,
                "n_changes": 0,
                "n_deletes": 0,
                "deletes_by_relation": {},
                "churn_by_relation": {},
                "churn_by_path": {},
                "ddl": False,
                "heartbeat_count": 0,
            }
        return windows[idx]

    for hb in hbs:
        ts = rec_time(hb)
        if ts is None:
            continue
        w = win(bucket(ts))
        w["heartbeat_count"] += 1
        lsn = lsn_norm(hb["lsn"])
        iso = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if w["lsn_start"] is None or lsn_int(lsn) < lsn_int(w["lsn_start"]):
            w["lsn_start"] = lsn
            w["t_start"] = iso
        if w["lsn_end"] is None or lsn_int(lsn) >= lsn_int(w["lsn_end"]):
            w["lsn_end"] = lsn
            w["t_end"] = iso

    def assign_lsn(lsn: str, ts: datetime | None) -> dict | None:
        if ts is not None:
            return win(bucket(ts))
        # Fall back: nearest window by LSN.
        n = lsn_int(lsn)
        chosen = None
        for w in windows.values():
            if w["lsn_start"] and w["lsn_end"] and lsn_int(w["lsn_start"]) <= n <= lsn_int(w["lsn_end"]):
                chosen = w
                break
        return chosen

    for rec in changes:
        lsn = lsn_norm(rec["lsn"])
        w = assign_lsn(lsn, rec_time(rec))
        if w is None:
            continue
        w["n_changes"] += 1
        table = rec.get("table") or ""
        w["churn_by_relation"][table] = w["churn_by_relation"].get(table, 0) + 1
        if rec.get("action") == "D":
            w["n_deletes"] += 1
            w["deletes_by_relation"][table] = w["deletes_by_relation"].get(table, 0) + 1

    for rec in ddl:
        w = assign_lsn(lsn_norm(rec["lsn"]), rec_time(rec))
        if w is not None:
            w["ddl"] = True

    snap_lsn = {s.get("snapshot"): s.get("lsn") for s in snaps if s.get("snapshot")}
    for rec in fs:
        # Attribute filesystem churn to the destination snapshot's window.
        lsn = snap_lsn.get(rec.get("snap_to"))
        if not lsn:
            continue
        w = assign_lsn(lsn_norm(lsn), None)
        if w is None:
            continue
        path = rec.get("path") or ""
        w["churn_by_path"][path] = w["churn_by_path"].get(path, 0) + 1

    rows = []
    for idx in sorted(windows):
        w = windows[idx]
        duration = window_s
        if w["t_start"] and w["t_end"]:
            duration = max((parse_ts(w["t_end"]) - parse_ts(w["t_start"])).total_seconds(), 1e-9)
        burst = w["n_changes"] / duration
        rows.append({
            "incident_id": incident,
            "window_id": w["window_id"],
            "t_start": w["t_start"],
            "t_end": w["t_end"],
            "lsn_start": w["lsn_start"],
            "lsn_end": w["lsn_end"],
            "lsn_start_int": lsn_int(w["lsn_start"]) if w["lsn_start"] else None,
            "lsn_end_int": lsn_int(w["lsn_end"]) if w["lsn_end"] else None,
            "change_burst_density": burst,
            "n_changes": w["n_changes"],
            "n_deletes": w["n_deletes"],
            "churn_by_relation": dict(sorted(w["churn_by_relation"].items())),
            "churn_by_path": dict(sorted(w["churn_by_path"].items())),
            "deletes_by_relation": dict(sorted(w["deletes_by_relation"].items())),
            "ddl": w["ddl"],
            "heartbeat_count": w["heartbeat_count"],
            "analytics_version": version,
        })
    last_active = max((r["window_id"] for r in rows if r["n_changes"] or r["ddl"] or r["n_deletes"]), default=None)
    if last_active is not None:
        rows = [r for r in rows if r["window_id"] <= last_active]
    header = {
        "incident_id": incident,
        "window_s": window_s,
        "analytics_version": version,
        "n_windows": len(rows),
        "windows": [{"window_id": r["window_id"], "t_start": r["t_start"], "t_end": r["t_end"],
                     "lsn_start": r["lsn_start"], "lsn_end": r["lsn_end"]} for r in rows],
    }
    out = p3_dir(incident)
    write_jsonl(out / "analytics.jsonl", rows)
    write_json(out / "windows.json", header)
    print(json.dumps({"ok": True, "changed": True, "incident": incident,
                      "windows": len(rows), "output": str(out / "analytics.jsonl")}, sort_keys=True))
    return header


def main(argv: list[str]) -> int:
    if not argv:
        die(EXIT_USAGE, "usage: lab-analytics <incident>")
    analytics(argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
