"""Durable file intentions, separate from the database workload ledger."""
from __future__ import annotations

import json
import os

from lab_paths import evidence_dir
from lab_snapshot_tick import utc_now


def record_operations(incident: str, operations: list[dict], source: str) -> list[dict]:
    """Call under snapshot_lock; timestamps precede mutations in that same lock."""
    path = evidence_dir(incident) / "fs-workload.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{**op, "source": source, "ts": utc_now()} for op in operations]
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return rows
