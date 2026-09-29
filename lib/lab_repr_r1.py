"""lab-repr-r1: per-window aggregates over R0, reusing C5 anomaly scores."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from lab_p3_util import EXIT_PRECOND, EXIT_USAGE, die
from lab_repr import (
    artefact_blind, assign_window, emit, events_by_window, fidelity_manifest,
    load_c5_windows, load_r0, parse_incident, repr_dir, windowing_params,
    write_json_0444, write_jsonl_0444,
)

BUILDER = "p5-repr-r1-1"


def build_r1(incident: str, dest: Path | None = None) -> dict:
    try:
        events, r0 = load_r0(incident, dest)
    except FileNotFoundError:
        die(EXIT_PRECOND, "precondition failed: R0 missing; run lab-repr-r0 first")
    if not r0.get("provenance_blind") or not r0.get("reconciles"):
        die(EXIT_PRECOND, "precondition failed: R0 is not admissible")
    c5 = load_c5_windows(incident)
    params = windowing_params(incident)
    grouped = events_by_window(events, c5, params["window_s"])
    windows = []
    offending = []
    for w in c5:
        idx = int(w["window_id"])
        bucket = grouped.get(idx, [])
        actions = Counter(e["action"] for e in bucket)
        deletes = [e for e in bucket if e["action"] == "D"]
        delete_count = len(deletes)
        actual_deletes = sum(1 for e in bucket if e["action"] == "D")
        if delete_count != actual_deletes:
            offending.append(idx)
        file_churn = int(sum((w.get("churn_by_path") or {}).values()))
        first_lsn = min((e["lsn_int"] for e in bucket), default=int(w["lsn_start_int"]))
        last_lsn = max((e["lsn_int"] for e in bucket), default=int(w["lsn_end_int"]))
        windows.append({
            "window_index": idx,
            "first_lsn_int": int(first_lsn),
            "last_lsn_int": int(last_lsn),
            "event_count": len(bucket),
            "delete_count": delete_count,
            "file_churn": file_churn,
            "anomaly_score": float(w["anomaly_score"]),
            "anomalous": bool(w.get("anomalous")),
            "action_counts": dict(sorted(actions.items())),
            "lsn_start_text": w.get("lsn_start"),
            "lsn_end_text": w.get("lsn_end"),
        })
    windows.sort(key=lambda r: int(r["window_index"]))
    event_sum = sum(r["event_count"] for r in windows)
    reconciles = (event_sum == int(r0["event_count"])) and not offending
    out = repr_dir(incident, "R1", dest)
    windows_path = out / "windows.jsonl"
    content_hash = write_jsonl_0444(windows_path, windows)
    blind, _hits = artefact_blind([windows_path])
    manifest = fidelity_manifest(
        incident, "R1", BUILDER, r0["source_ledger_hash"], content_hash,
        event_count=event_sum, ledger_event_count=int(r0["ledger_event_count"]),
        reconciles=reconciles, provenance_blind=blind,
        extra={
            "window_s": params["window_s"],
            "origin_ts": params["origin_ts"],
            "analytics_version": params["analytics_version"],
        },
    )
    write_json_0444(out / "manifest.json", manifest)
    return {
        "ok": True,
        "changed": False,
        "incident": incident,
        "representation": "R1",
        "event_count": event_sum,
        "ledger_event_count": int(r0["ledger_event_count"]),
        "content_hash": content_hash,
        "reconciles": reconciles,
        "provenance_blind": blind,
        "built_by_model": False,
        "n_windows": len(windows),
        "window_s": params["window_s"],
        "windows": str(windows_path),
        "manifest": str(out / "manifest.json"),
    }


def main(argv: list[str]) -> int:
    incident, dest = parse_incident(argv)
    first = build_r1(incident, dest)
    second = build_r1(incident, dest)
    second["prior_content_hash"] = first["content_hash"]
    second["changed"] = False
    emit(second)
    return 0


if __name__ == "__main__":
    if not sys.argv[1:]:
        die(EXIT_USAGE, "usage: lab-repr-r1 <incident> [--dest DIR]")
    raise SystemExit(main(sys.argv[1:]))
