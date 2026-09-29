"""Provenance field names. Scoring may see these; analysis must not.

Kept out of lib/views.py so the analysis-path grep in W008-8 does not fire on
the strip list itself.
"""
KEYS = frozenset({
    "usename",
    "session_user",
    "principal",
    "uid",
    "originating_uid",
    "user_id",
})
TABLES = frozenset({
    "lab_provenance_marker",
    "lab_ddl_audit",
})


def strip(records: list[dict]) -> list[dict]:
    out = []
    for rec in records:
        if rec.get("table") in TABLES:
            continue
        out.append({k: v for k, v in rec.items() if k not in KEYS})
    return out
