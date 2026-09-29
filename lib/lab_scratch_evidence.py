"""Copy an incident evidence tree into logs/review/<id>/scratch/ (Article XVI)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def lab_root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parents[1])


def evidence_src(incident: str) -> Path:
    scenario = incident.split("_", 1)[0]
    return Path(os.environ["EVIDENCE_ROOT"]) / scenario / incident


def scratch_evidence(review_id: str, incident: str) -> Path:
    """Return scratch evidence dir for incident, copying once if absent."""
    scenario = incident.split("_", 1)[0]
    dest = lab_root() / "logs" / "review" / review_id / "scratch" / "evidence" / scenario / incident
    src = evidence_src(incident)
    if dest.is_dir() and (dest / "db.jsonl").is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        dest.mkdir(parents=True, exist_ok=True)
    return dest


def overlay_frozen_ledger(dest: Path, frozen: Path) -> None:
    if not frozen.is_file():
        return
    target = dest / "db.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        os.chmod(target, 0o644)
    target.write_bytes(frozen.read_bytes())
    os.chmod(target, 0o644)
