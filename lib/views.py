"""Ledger views. scoring retains provenance; analysis does not (ADR-P1-3)."""
from __future__ import annotations

import json
from pathlib import Path

import provenance_fields


def load_ledger(path: str | Path) -> list[dict]:
    rows = []
    p = Path(path)
    if not p.is_file():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def scoring_view(records: list[dict]) -> list[dict]:
    """Full ledger, including provenance. Oracle only."""
    return list(records)


def analysis_view(records: list[dict]) -> list[dict]:
    """Ledger without provenance columns or marker tables."""
    return provenance_fields.strip(records)
