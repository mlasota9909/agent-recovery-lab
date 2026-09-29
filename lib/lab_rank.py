"""lab-rank: Arm A deterministic ranker. Candidates only; no injection/oracle/provenance."""
from __future__ import annotations

import json
from pathlib import Path

from lab_analytics import p3_dir
from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, load_jsonl, require_lab, validate_arm,
    write_json,
)
from lab_paths import evidence_dir, lab_root


def load_weights(path: Path | None = None) -> dict:
    p = path or (lab_root() / "etc" / "rank-weights.json")
    if not p.is_file():
        die(EXIT_PRECOND, f"precondition failed: rank weights missing {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def feature_value(feat: dict, name: str) -> float:
    val = feat[name]
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    return float(val)


def score_candidate(cand: dict, weights: dict) -> float:
    feat = cand["features"]
    total = 0.0
    for name, w in weights["weights"].items():
        total += float(w) * feature_value(feat, name)
    return total


def first_anomalous_start(incident: str) -> int:
    rows = load_jsonl(p3_dir(incident) / "anomaly.jsonl")
    first = next((w for w in rows if w.get("anomalous")), None)
    if first is None:
        die(EXIT_ASSERT, "assertion failed: no anomalous window")
    return int(first["lsn_start_int"])


def is_safe(cand: dict, frontier: int) -> bool:
    return cand["lsn_int"] < frontier and float(cand["features"]["anomaly_score"]) < 3.0


def rank(incident: str, weights_path: Path | None = None) -> dict:
    require_lab()
    weights = load_weights(weights_path)
    cands = load_jsonl(p3_dir(incident) / "candidates.jsonl")
    if not cands:
        die(EXIT_PRECOND, "precondition failed: candidates.jsonl missing; run lab-candidates first")
    frontier = first_anomalous_start(incident)
    scored = []
    for cand in cands:
        scored.append((score_candidate(cand, weights), cand["lsn_int"], cand))
    safe = [s for s in scored if is_safe(s[2], frontier)]
    pool = safe or scored
    # Max score; tie-break latest safe integer LSN.
    pool.sort(key=lambda t: (t[0], t[1]))
    _score, _lsn, chosen = pool[-1]
    rationale = (
        f"latest_safe_lsn_int tie-break after score={_score:.6f}; "
        f"proximity={chosen['features']['proximity_to_first_suspicious']}; "
        f"data_loss_rows={chosen['features']['data_loss_rows']}; "
        f"consistency_risk={chosen['features']['consistency_risk']}; "
        f"anomaly_score={chosen['features']['anomaly_score']}; "
        f"ddl_in_window={chosen['features']['ddl_in_window']}"
    )
    rec = {
        "incident_id": chosen["incident_id"],
        "arm": "arm_a",
        "selector_version": weights["version"],
        "representation": "n/a",
        "lsn_text": chosen["lsn_text"],
        "lsn_int": chosen["lsn_int"],
        "wall_clock": chosen["wall_clock"],
        "snapshot": chosen["snapshot"],
        "chosen_candidate_id": chosen["candidate_id"],
        "rationale": rationale,
        "selection_inputs": {
            "ledger_view": weights.get("ledger_view", "db_changes"),
            "approx_incident_time": None,
            "incident_time_error_seconds": None,
            "read_injection_log": False,
            "read_oracle_optimum": False,
            "read_provenance": False,
        },
    }
    errs = validate_arm(rec)
    if errs:
        die(EXIT_ASSERT, f"assertion failed: arm-coordinate: {errs}")
    write_json(p3_dir(incident) / "arm-a-coordinate.json", rec)
    print(json.dumps({"ok": True, "changed": True, "incident": incident, "coordinate": rec}, sort_keys=True))
    return rec


def main(argv: list[str]) -> int:
    weights = None
    incident = None
    i = 0
    while i < len(argv):
        if argv[i] == "--weights" and i + 1 < len(argv):
            weights = Path(argv[i + 1]); i += 2; continue
        if incident is None and not argv[i].startswith("--"):
            incident = argv[i]; i += 1; continue
        die(EXIT_USAGE, "usage: lab-rank <incident> [--weights PATH]")
    if not incident:
        die(EXIT_USAGE, "usage: lab-rank <incident>")
    rank(incident, weights)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
