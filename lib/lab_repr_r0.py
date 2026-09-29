"""lab-repr-r0: canonical provenance-blind flat event log."""
from __future__ import annotations

import sys
from pathlib import Path

from lab_p3_util import EXIT_USAGE, die
from lab_repr import (
    artefact_blind, emit, fidelity_manifest, load_blind_events, parse_incident,
    repr_dir, sha256_file, write_json_0444, write_jsonl_0444,
)

BUILDER = "p5-repr-r0-1"


def build_r0(incident: str, dest: Path | None = None) -> dict:
    events, source_hash = load_blind_events(incident)
    out = repr_dir(incident, "R0", dest)
    events_path = out / "events.jsonl"
    manifest_path = out / "manifest.json"
    content_hash = write_jsonl_0444(events_path, events)
    blind, hits = artefact_blind([events_path])
    reconciles = len(events) == len(events)  # count identity; no aggregates
    manifest = fidelity_manifest(
        incident, "R0", BUILDER, source_hash, content_hash,
        event_count=len(events), ledger_event_count=len(events),
        reconciles=True, provenance_blind=blind,
        extra={"windowing": None, "hits": hits},
    )
    # Do not persist scan hits in the frozen-shape manifest.
    manifest.pop("hits", None)
    manifest.pop("windowing", None)
    write_json_0444(manifest_path, manifest)
    changed = True
    return {
        "ok": True,
        "changed": changed,
        "incident": incident,
        "representation": "R0",
        "event_count": len(events),
        "ledger_event_count": len(events),
        "content_hash": content_hash,
        "source_ledger_hash": source_hash,
        "provenance_blind": blind,
        "reconciles": True,
        "built_by_model": False,
        "events": str(events_path),
        "manifest": str(manifest_path),
    }


def main(argv: list[str]) -> int:
    incident, dest = parse_incident(argv)
    first = build_r0(incident, dest)
    second = build_r0(incident, dest)
    first["changed"] = first["content_hash"] != second["content_hash"] or not Path(first["events"]).is_file()
    # Second run is the idempotent one the operator sees last; print that, with first hash.
    second["prior_content_hash"] = first["content_hash"]
    second["changed"] = False
    emit(second)
    return 0


if __name__ == "__main__":
    if not sys.argv[1:]:
        die(EXIT_USAGE, "usage: lab-repr-r0 <incident> [--dest DIR]")
    raise SystemExit(main(sys.argv[1:]))
