"""lab-anomaly: mean+3σ against the declared pre-injection baseline window."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from lab_analytics import p3_dir
from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, load_jsonl, require_lab, scenario_config,
    write_json, write_jsonl,
)
from lab_paths import evidence_dir
from lsn import lsn_int, lsn_norm


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mu = sum(values) / len(values)
    if len(values) == 1:
        return mu, 0.0
    var = sum((x - mu) ** 2 for x in values) / len(values)
    return mu, math.sqrt(var)


def zscore(x: float, mu: float, sigma: float) -> float:
    if sigma == 0:
        return 0.0 if x == mu else (99.0 if x > mu else -99.0)
    return (x - mu) / sigma


def anomaly(incident: str, allow_overlap: bool = False) -> dict:
    require_lab()
    ed = evidence_dir(incident)
    meta = json.loads((ed / "incident.json").read_text(encoding="utf-8"))
    inj = json.loads((ed / "injection_log.json").read_text(encoding="utf-8"))
    windows = load_jsonl(p3_dir(incident) / "analytics.jsonl")
    if not windows:
        die(EXIT_PRECOND, "precondition failed: analytics.jsonl missing; run lab-analytics first")
    baseline = meta["quiescent_baseline"]
    base_end = lsn_int(lsn_norm(baseline["lsn_end_exclusive"]))
    inj_start = lsn_int(lsn_norm(inj["lsn_start"]))
    if not allow_overlap and base_end > inj_start:
        die(EXIT_ASSERT, "assertion failed: baseline window overlaps injection damage window")
    base_rows = []
    for w in windows:
        end = w.get("lsn_end_int")
        if end is not None and end < inj_start:
            # Predates injection: candidate baseline window.
            if w.get("lsn_start_int") is not None:
                base_rows.append(w)
    if not base_rows:
        die(EXIT_ASSERT, "assertion failed: no analytics windows predating injection")
    metrics = {
        "change_burst_density": [float(w["change_burst_density"]) for w in base_rows],
        "n_deletes": [float(w["n_deletes"]) for w in base_rows],
        "n_changes": [float(w["n_changes"]) for w in base_rows],
    }
    stats = {name: {"mu": mean_std(vals)[0], "sigma": mean_std(vals)[1]} for name, vals in metrics.items()}
    scored = []
    for w in windows:
        zs = []
        for name in metrics:
            zs.append(zscore(float(w[name]), stats[name]["mu"], stats[name]["sigma"]))
        score = max(zs) if zs else 0.0
        rec = dict(w)
        rec["anomaly_score"] = score
        rec["anomalous"] = bool(score >= 3.0)
        rec["z_burst"] = zs[0]
        rec["z_deletes"] = zs[1]
        rec["z_changes"] = zs[2]
        scored.append(rec)
    out = p3_dir(incident)
    write_jsonl(out / "anomaly.jsonl", scored)
    proof = {
        "incident": incident,
        "baseline_t_start": baseline.get("t_start"),
        "baseline_t_end": baseline.get("t_end"),
        "baseline_lsn_end_exclusive": baseline["lsn_end_exclusive"],
        "injection_lsn_start": inj["lsn_start"],
        "predates_injection": base_end <= inj_start,
        "n_baseline_windows": len(base_rows),
        "stats": stats,
    }
    write_json(out / "baseline-window.json", proof)
    print(json.dumps({"ok": True, "changed": True, "incident": incident,
                      "windows": len(scored), "anomalous": sum(1 for r in scored if r["anomalous"]),
                      "predates_injection": proof["predates_injection"]}, sort_keys=True))
    return proof


def main(argv: list[str]) -> int:
    allow = False
    incident = None
    i = 0
    while i < len(argv):
        if argv[i] == "--allow-overlap":
            allow = True; i += 1; continue
        if incident is None and not argv[i].startswith("--"):
            incident = argv[i]; i += 1; continue
        die(EXIT_USAGE, "usage: lab-anomaly <incident> [--allow-overlap]")
    if not incident:
        die(EXIT_USAGE, "usage: lab-anomaly <incident>")
    try:
        anomaly(incident, allow_overlap=allow)
    except SystemExit:
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
