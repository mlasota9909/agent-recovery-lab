"""lab-repr-admit: re-derive determinism, completeness, reconciliation, blindness."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, canonical_json, die, load_jsonl, write_json, write_text
from lab_paths import lab_root
from lab_repr import (
    PROBE_IDS, REPR_IDS, artefact_blind, events_by_window, load_c5_windows, load_r0, load_r1,
    load_r2, probe_params_for, repr_root, token_scan, windowing_params,
)
from lab_repr_query import query, response_bytes
from lab_repr_r0 import build_r0
from lab_repr_r1 import build_r1
from lab_repr_r2 import dangling_edges, reconcile_summaries, build_r2


def _artefact_paths(incident: str, dest: Path | None, name: str) -> list[Path]:
    base = repr_root(incident, dest) / name
    if name == "R0":
        return [base / "events.jsonl", base / "manifest.json"]
    if name == "R1":
        return [base / "windows.jsonl", base / "manifest.json"]
    return [base / "graph.json", base / "summaries.jsonl", base / "manifest.json"]


def rebuild_scratch(incident: str) -> dict[str, str]:
    scratch = Path(tempfile.mkdtemp(prefix="repr-admit-", dir="/tmp"))
    build_r0(incident, scratch)
    build_r1(incident, scratch)
    build_r2(incident, scratch)
    hashes = {}
    for name in REPR_IDS:
        man = json.loads((scratch / name / "manifest.json").read_text(encoding="utf-8"))
        hashes[name] = man["content_hash"]
    hashes["_scratch"] = str(scratch)
    return hashes


def check_one(incident: str, name: str, scratch_hash: str) -> dict:
    if name == "R0":
        events, man = load_r0(incident)
        complete = int(man["event_count"]) == int(man["ledger_event_count"]) == len(events)
        rec = complete
        rec_notes = []
    elif name == "R1":
        events, r0 = load_r0(incident)
        windows, man = load_r1(incident)
        c5 = load_c5_windows(incident)
        params = windowing_params(incident)
        grouped = events_by_window(events, c5, params["window_s"])
        rec_notes = []
        rec = True
        if sum(int(w["event_count"]) for w in windows) != int(r0["event_count"]):
            rec = False
            rec_notes.append("window sum != R0")
        for w in windows:
            idx = int(w["window_index"])
            bucket = grouped.get(idx, [])
            actual_del = sum(1 for e in bucket if e["action"] == "D")
            if int(w["event_count"]) != len(bucket):
                rec = False
                rec_notes.append(f"window {idx} event_count")
            if int(w["delete_count"]) != actual_del:
                rec = False
                rec_notes.append(f"window {idx} delete_count")
        complete = int(man["event_count"]) == int(man["ledger_event_count"])
        rec = rec and complete
    else:
        events, r0 = load_r0(incident)
        graph, summaries, man = load_r2(incident)
        c5 = load_c5_windows(incident)
        params = windowing_params(incident)
        rec_ok, rec_notes = reconcile_summaries(summaries, events, c5, params["window_s"])
        dang = dangling_edges(graph)
        rec = rec_ok and not dang and int(man["event_count"]) == int(r0["event_count"])
        complete = int(man["event_count"]) == int(man["ledger_event_count"])
        rec = rec and complete
        if dang:
            rec_notes = list(rec_notes) + [f"dangling {len(dang)}"]

    paths = _artefact_paths(incident, None, name)
    blind, hits = artefact_blind(paths)
    # Probe sweep blindness for this incident (once, cheap enough).
    sweep_hits = []
    if name == "R0":
        for probe in PROBE_IDS:
            params = probe_params_for(incident, probe)
            for rep in REPR_IDS:
                payload = query(incident, rep, probe, params)
                sweep_hits.extend(token_scan(response_bytes(payload), roles=True))
        blind = blind and not sweep_hits
        hits = list(hits) + sweep_hits

    deterministic = man["content_hash"] == scratch_hash
    incident_ok = man.get("incident_id") == incident
    admissible = (
        deterministic and complete and rec and blind
        and man.get("built_by_model") is False and incident_ok
    )
    return {
        "representation": name,
        "deterministic": deterministic,
        "complete": complete,
        "reconciles": rec,
        "provenance_blind": blind,
        "incident_id": man.get("incident_id"),
        "admissible": admissible,
        "content_hash": man.get("content_hash"),
        "scratch_hash": scratch_hash,
        "notes": rec_notes,
        "hits": hits[:10],
        "built_by_model": man.get("built_by_model"),
    }


def admit(incident: str) -> dict:
    scratch = rebuild_scratch(incident)
    scratch_dir = Path(scratch.pop("_scratch"))
    try:
        verdicts = [check_one(incident, name, scratch[name]) for name in REPR_IDS]
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    ok = all(v["admissible"] for v in verdicts)
    return {"ok": ok, "incident": incident, "verdicts": verdicts}


def main(argv: list[str]) -> int:
    if not argv:
        die(3, "usage: lab-repr-admit <incident>")
    rec = admit(argv[0])
    print(json.dumps(rec, indent=2, sort_keys=True))
    return 0 if rec["ok"] else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
