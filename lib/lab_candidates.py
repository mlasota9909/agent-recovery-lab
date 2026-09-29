"""lab-candidates: frozen candidate-coordinate records from anomaly windows."""
from __future__ import annotations

import json
import os
from pathlib import Path

from lab_analytics import p3_dir
from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, load_jsonl, require_lab, run_json,
    scenario_config, validate_candidate, write_jsonl,
)
from lab_paths import evidence_dir
from lsn import lsn_int, lsn_norm, parse_lsn
from views import analysis_view, load_ledger


def lsn_order_fixture() -> dict:
    a_text, a_int = parse_lsn("3/9")
    b_text, b_int = parse_lsn("3/10")
    int_ok = a_int < b_int
    str_wrong = a_text > b_text  # string compare gets this wrong
    return {
        "a": {"lsn_text": a_text, "lsn_int": a_int},
        "b": {"lsn_text": b_text, "lsn_int": b_int},
        "integer_orders_lt": int_ok,
        "string_compare_would_fail": str_wrong and int_ok,
    }


def resolve(lsn: str, incident: str | None = None) -> dict:
    if os.environ.get("LAB_P7_HOST_COORD") == "1" and incident:
        from lab_snapshot_coord import resolve_lsn_from_manifest
        return resolve_lsn_from_manifest(incident, lsn)
    return run_json("lab-coordinate", ["--lsn", lsn_norm(lsn)])


def candidates(incident: str) -> list[dict]:
    require_lab()
    cfg = scenario_config()
    version = cfg.get("SC01_ANALYTICS_VERSION", "p3-analytics-1")
    meta = json.loads((evidence_dir(incident) / "incident.json").read_text(encoding="utf-8"))
    rows = load_jsonl(p3_dir(incident) / "anomaly.jsonl")
    if not rows:
        die(EXIT_PRECOND, "precondition failed: anomaly.jsonl missing; run lab-anomaly first")
    first = next((w for w in rows if w.get("anomalous")), None)
    if first is None:
        die(EXIT_ASSERT, "assertion failed: no anomalous window; cannot propose candidates")
    first_start = int(first["lsn_start_int"])
    # Windows neighbouring the first anomalous window.
    neighbour_ids = {first["window_id"] - 1, first["window_id"], first["window_id"] + 1}
    neighbour = [w for w in rows if w["window_id"] in neighbour_ids]
    ledger = analysis_view(load_ledger(evidence_dir(incident) / "db.jsonl"))
    lsns: list[str] = []
    for w in neighbour:
        lo = w.get("lsn_start_int")
        hi = w.get("lsn_end_int")
        if lo is None:
            continue
        for rec in ledger:
            lsn = rec.get("lsn")
            if not lsn or rec.get("action") not in {"I", "U", "D", "C"}:
                continue
            n = lsn_int(lsn)
            if lo <= n <= (hi or lo):
                lsns.append(lsn_norm(lsn))
        if w.get("lsn_start"):
            lsns.append(lsn_norm(w["lsn_start"]))
    # Always include the last LSN of the last pre-anomalous window (safe frontier).
    pre = [w for w in rows if w.get("lsn_end_int") is not None and w["lsn_end_int"] < first_start]
    if pre:
        last_pre = max(pre, key=lambda w: w["lsn_end_int"])
        lsns.append(lsn_norm(last_pre["lsn_end"]))
    uniq = sorted(set(lsns), key=lsn_int)
    out_rows = []
    for lsn in uniq:
        n = lsn_int(lsn)
        coord = resolve(lsn, incident)
        containing = None
        for w in rows:
            if w.get("lsn_start_int") is not None and w.get("lsn_end_int") is not None:
                if w["lsn_start_int"] <= n <= w["lsn_end_int"]:
                    containing = w
                    break
        data_loss = sum(1 for rec in ledger
                        if rec.get("lsn") and rec.get("action") in {"I", "U", "D"}
                        and n < lsn_int(rec["lsn"]) < first_start)
        skew_ms = int(coord.get("skew_ms") or 0)
        rec = {
            "incident_id": meta["incident_id"],
            "candidate_id": f"{meta['incident_id']}:{n}",
            "lsn_text": lsn,
            "lsn_int": n,
            "wall_clock": coord["wall_clock"],
            "snapshot": coord["snapshot"],
            "skew_seconds": skew_ms / 1000.0,
            "skew_rows": int(coord.get("skew_bytes") or 0),
            "features": {
                "proximity_to_first_suspicious": abs(n - first_start),
                "data_loss_rows": data_loss,
                "consistency_risk": 1.0 if skew_ms > 0 else 0.0,
                "anomaly_score": float(containing["anomaly_score"]) if containing else 0.0,
                "ddl_in_window": bool(containing["ddl"]) if containing else False,
            },
            "analytics_version": version,
        }
        errs = validate_candidate(rec)
        if errs:
            die(EXIT_ASSERT, f"assertion failed: candidate schema: {errs}")
        out_rows.append(rec)
    if not out_rows:
        die(EXIT_ASSERT, "assertion failed: no candidates generated")
    write_jsonl(p3_dir(incident) / "candidates.jsonl", out_rows)
    print(json.dumps({"ok": True, "changed": True, "incident": incident, "n": len(out_rows),
                      "first_anomalous_window": first["window_id"]}, sort_keys=True))
    return out_rows


def main(argv: list[str]) -> int:
    if argv == ["--lsn-order-fixture"]:
        print(json.dumps(lsn_order_fixture(), sort_keys=True))
        return 0
    if not argv:
        die(EXIT_USAGE, "usage: lab-candidates <incident> | --lsn-order-fixture")
    candidates(argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
