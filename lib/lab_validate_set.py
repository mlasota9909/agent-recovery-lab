"""Ground-truth set-and-earliest scorer for SC-03/SC-04."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab_paths import evidence_dir
from lsn import lsn_int, lsn_norm


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def key(item: dict) -> tuple[int | None, int]:
    return (int(item["row_id"]) if item.get("row_id") is not None else None, int(item["xid"]))


def truth_for(incident: str) -> tuple[str, list[dict], str]:
    ev = evidence_dir(incident)
    meta = json.loads((ev / "incident.json").read_text(encoding="utf-8"))
    scenario = meta["scenario_id"]
    injection = json.loads((ev / "injection.json").read_text(encoding="utf-8"))
    if scenario == "SC-04":
        truth = injection["malicious_set"]
        earliest = injection["earliest_malicious_commit_lsn"]
    elif scenario == "SC-03":
        truth = [{"xid": op["xid"]} for op in injection["ops"]]
        earliest = injection["ops"][0]["commit_lsn"]
    else:
        raise SystemExit("precondition failed: set validation supports SC-03/SC-04 only")
    return scenario, truth, lsn_norm(earliest)


def validate_set(incident: str, identified: list[dict], chosen_lsn: str) -> dict:
    scenario, truth, earliest = truth_for(incident)
    truth_keys = {key(x) for x in truth}
    pred_keys = {key(x) for x in identified}
    tp, fp, fn = len(truth_keys & pred_keys), len(pred_keys - truth_keys), len(truth_keys - pred_keys)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    chosen = lsn_norm(chosen_lsn)
    bounded = lsn_int(chosen) <= lsn_int(earliest)
    sacrificed = 0
    for rec in load_jsonl(evidence_dir(incident) / "workload-manifest.jsonl"):
        raw = rec.get("commit_lsn")
        if raw and lsn_int(lsn_norm(raw)) > lsn_int(chosen):
            sacrificed += int(rec.get("row_count") or len(rec.get("row_ids") or []) or 1)
    verdict = "set_correct" if precision == 1.0 and recall == 1.0 and bounded else (
        "set_partial" if tp else "set_incorrect"
    )
    return {
        "incident": incident,
        "scenario_id": scenario,
        "verdict": verdict,
        "precision": precision,
        "recall": recall,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "n_truth": len(truth_keys),
        "n_identified": len(pred_keys),
        "chosen_lsn": chosen,
        "earliest_malicious_commit_lsn": earliest,
        "earliest_safe_bound": chosen,
        "earliest_correctly_bounded": bounded,
        "legitimate_dml_sacrificed": sacrificed,
        "scorer_reads_ground_truth": True,
        "detection_reads_ground_truth": False,
        "restore_verdict": verdict,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lab-validate-set")
    p.add_argument("--incident", required=True)
    p.add_argument("--identified", required=True, help="JSON array or file containing an array")
    p.add_argument("--chosen-lsn", required=True)
    args = p.parse_args(argv)
    raw = Path(args.identified).read_text(encoding="utf-8") if Path(args.identified).is_file() else args.identified
    identified = json.loads(raw)
    if not isinstance(identified, list):
        raise SystemExit("usage: --identified must be a JSON array")
    print(json.dumps(validate_set(args.incident, identified, args.chosen_lsn), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
