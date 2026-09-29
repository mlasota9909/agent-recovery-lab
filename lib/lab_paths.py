"""Incident evidence paths. Existing collectors use EVIDENCE_ROOT/<scenario>/<incident>/."""
from __future__ import annotations

import os
from pathlib import Path


def env(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        raise SystemExit(f"precondition failed: {key} missing from lab.env")
    return v


def lab_root() -> Path:
    return Path(env("LAB_ROOT"))


def bin_path(name: str) -> Path:
    return lab_root() / "bin" / name


def incident_scenario(incident: str) -> str:
    if "_" not in incident or not incident.startswith("SC-"):
        raise SystemExit(f"usage: incident id must be SC-NN_YYYYMMDDTHHMMSSZ, got {incident!r}")
    return incident.split("_", 1)[0]


def evidence_dir(incident: str) -> Path:
    return Path(env("EVIDENCE_ROOT")) / incident_scenario(incident) / incident


def current_incident() -> str:
    current = Path(env("ARCHIVE_CURRENT"))
    target = current.resolve()
    archive_root = Path(env("ARCHIVE_ROOT")).resolve()
    try:
        target.relative_to(archive_root)
    except ValueError as exc:
        raise SystemExit("precondition failed: archive/current escapes ARCHIVE_ROOT") from exc
    name = target.name
    if not name.startswith("SC-"):
        raise SystemExit(f"precondition failed: invalid current incident {name!r}")
    return name
