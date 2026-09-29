"""lab-arm-b-score: wire a determination through the unchanged P4 path."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from lab_evaluate_arm import COORD_FIELDS, coord_errors, harness_commit_at_production, next_replicate
from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, write_json
from lab_p4_util import no_peek_ok, restore_root
from lab_paths import env, evidence_dir, lab_root
from lab_tokenize import evidence_bytes
from lsn import lsn_int

VERDICT_MAP = {
    "correct": "correct",
    "incorrect-safe": "incorrect_safe",
    "incorrect-corrupt": "incorrect_corrupt",
    "not-recovered": "not_recovered",
}


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or lab_root())


def run_bin(name: str, argv: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    envp = os.environ.copy()
    envp["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + envp["PYTHONPATH"] if envp.get("PYTHONPATH") else "")
    return subprocess.run(
        [str(root() / "bin" / name), *argv],
        cwd=str(root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=envp,
    )


def reject_peek(rec: dict) -> None:
    if rec.get("arm_coordinate"):
        rec = rec["arm_coordinate"]
    inputs = rec.get("selection_inputs") or {}
    for flag in ("read_injection_log", "read_oracle_optimum", "read_provenance"):
        if inputs.get(flag) is True:
            die(EXIT_ASSERT, f"assertion failed: arm coordinate peek flag {flag}=true; scorer refused")
    if rec.get("selection_inputs") is not None and not no_peek_ok(rec):
        die(EXIT_ASSERT, "assertion failed: arm coordinate failed no-peek; score refused")


def p4_score(archive_incident: str, arm_coord: dict) -> dict:
    reject_peek(arm_coord)
    lsn = int(arm_coord["lsn_int"])
    tag = f"ab-{lsn}"
    report_path = restore_root(archive_incident, tag) / "report.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return score_from_report(report, cached=True)
    coord_path = restore_root(archive_incident, tag) / "arm-coordinate.json"
    coord_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(coord_path, arm_coord)
    proc = run_bin("lab-restore", [archive_incident, str(coord_path), "--restore-of", tag])
    if proc.returncode != 0:
        die(EXIT_ASSERT, proc.stderr.strip() or "lab-restore failed")
    try:
        proc = run_bin("lab-validate", [archive_incident, tag])
        if proc.returncode != 0:
            die(EXIT_ASSERT, proc.stderr.strip() or "lab-validate failed")
        proc = run_bin("lab-verdict", [archive_incident, tag])
        if proc.returncode != 0:
            die(EXIT_ASSERT, proc.stderr.strip() or "lab-verdict failed")
        report = json.loads((restore_root(archive_incident, tag) / "report.json").read_text(encoding="utf-8"))
        return score_from_report(report, cached=False)
    finally:
        run_bin("lab-restore", [archive_incident, str(coord_path), "--restore-of", tag, "--teardown"])


def score_from_report(report: dict, cached: bool) -> dict:
    summary = report.get("summary") or {}
    v = report.get("consistency_verdict")
    restore_verdict = VERDICT_MAP.get(v, v)
    files = int(summary.get("files_mismatched") or 0)
    schema = int(summary.get("schema_diffs") or 0)
    consistency = "inconsistent" if files or schema else "consistent"
    return {
        "restore_verdict": restore_verdict,
        "consistency_verdict": consistency,
        "p4_consistency_verdict": v,
        "damage_rows_retained": int(summary.get("damage_rows_retained") or 0),
        "legit_rows_lost": int(summary.get("legit_rows_lost") or 0),
        "damage_bytes_retained": summary.get("damage_bytes_retained"),
        "legit_bytes_lost": summary.get("legit_bytes_lost"),
        "cached": cached,
        "report": report,
    }


def chosen_from_arm(arm: dict) -> dict:
    raw = {
        "lsn": arm["lsn_text"],
        "wall_clock": arm["wall_clock"],
        "snapshot": arm["snapshot"],
        "resolved_by": "lsn_first",
        "skew_bytes": 0,
        "skew_ms": 0,
    }
    # fill skew from lab-coordinate if present on the arm via a stored resolve
    return {k: raw[k] for k in COORD_FIELDS}


def first_arm_a_row(incident_id: str) -> dict:
    path = Path(env("RESULTS_ROOT")) / "SC-01.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("incident_id") == incident_id:
            return row
    die(EXIT_PRECOND, f"precondition failed: no Arm A results row for {incident_id}")
    return {}


def results_row(archive_incident: str, representation: str, replicate: int, extracted: dict,
                model_rec: dict, score: dict | None, evidence_len: int) -> dict:
    meta = json.loads((evidence_dir(archive_incident) / "incident.json").read_text(encoding="utf-8"))
    incident_id = meta["incident_id"]
    baseline = first_arm_a_row(incident_id)
    gt = baseline["ground_truth_coordinate"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(env("RESULTS_ROOT")) / "SC-01.jsonl"
    arm = extracted.get("arm_coordinate")
    refusal = extracted.get("outcome") == "refusal" or arm is None
    if refusal:
        chosen = None
        err = {"coord_error_bytes": None, "coord_error_ms": None, "coord_direction": None}
        restore_attempted = False
        restore_verdict = "stub"
        consistency_verdict = "stub"
        legit_rows = None
        damage_rows = None
        legit_bytes = None
        damage_bytes = None
        t_restore = None
        detail = {"outcome": "refusal", "refusal_reason": extracted.get("refusal_reason")}
    else:
        reject_peek(arm)
        chosen = chosen_from_arm(arm)
        err = coord_errors(chosen, gt)
        restore_attempted = True
        restore_verdict = score["restore_verdict"]
        consistency_verdict = score["consistency_verdict"]
        legit_rows = score["legit_rows_lost"]
        damage_rows = score["damage_rows_retained"]
        legit_bytes = score.get("legit_bytes_lost")
        damage_bytes = score.get("damage_bytes_retained")
        t_restore = None
        detail = {"arm_coordinate": arm, "p4": {
            "restore_verdict": score["restore_verdict"],
            "p4_consistency_verdict": score["p4_consistency_verdict"],
            "damage_rows_retained": score["damage_rows_retained"],
            "legit_rows_lost": score["legit_rows_lost"],
            "cached": score["cached"],
        }}
    row = {
        "run_id": f"r_{stamp}_{secrets.token_hex(3)}",
        "scenario_id": "SC-01",
        "incident_id": incident_id,
        "replicate": replicate,
        "run_ts": now,
        "supersedes": None,
        "arm": "model",
        "representation": representation,
        "ranker_version": None,
        "model_id": os.environ.get("MODEL_ID") or (model_rec or {}).get("model_id"),
        "harness_commit": harness_commit_at_production(),
        "ground_truth_coordinate": gt,
        "chosen_coordinate": chosen,
        "naive_coordinate": baseline.get("naive_coordinate"),
        "incident_open_coordinate": meta["open_coordinate"],
        "incident_close_coordinate": meta["close_coordinate"],
        **err,
        "naive_coord_error_bytes": None if refusal else baseline.get("naive_coord_error_bytes"),
        "naive_coord_error_ms": None if refusal else baseline.get("naive_coord_error_ms"),
        "legit_rows_lost": legit_rows,
        "legit_bytes_lost": legit_bytes,
        "damage_rows_retained": damage_rows,
        "damage_bytes_retained": damage_bytes,
        "fs_granularity_penalty_ms": None,
        "restore_attempted": restore_attempted,
        "restore_verdict": restore_verdict,
        "consistency_verdict": consistency_verdict,
        "validation_detail": detail,
        "t_to_coordinate_ms": int((model_rec or {}).get("latency_ms") or 0),
        "t_to_validated_restore_ms": t_restore,
        "t_total_ms": int((model_rec or {}).get("latency_ms") or 0),
        "evidence_bytes_presented": evidence_len,
        "token_count": int((model_rec or {}).get("prompt_tokens") or 0) if model_rec else None,
        "retrieval_calls": 1,
        "reset_tier": "t2",
        "snapshot_pre_injection": meta["snapshot_pre_injection"],
        "snapshot_post_capture": meta["snapshot_post_capture"],
        "workload_rate_tps": meta["workload_rate_tps"],
        "workload_mix": meta["workload_mix"],
        "ledger_integrity_ok": True,
        "notes": None,
    }
    return row


def append_row(row: dict) -> dict:
    path = Path(env("RESULTS_ROOT")) / "SC-01.jsonl"
    payload = json.dumps(row)
    proc = run_bin("lab-results", ["append", "--file", str(path), "--row", payload])
    if proc.returncode != 0:
        die(EXIT_ASSERT, proc.stderr.strip() or proc.stdout.strip() or "lab-results append failed")
    return json.loads(proc.stdout)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-arm-b-score")
    p.add_argument("--incident", required=True)
    p.add_argument("--representation", required=True, choices=("R0", "R1", "R2"))
    p.add_argument("--extract", required=True, help="extract JSON from lab-arm-b-extract")
    p.add_argument("--model-record", help="lab-model JSON record")
    p.add_argument("--replicate", type=int, default=1)
    p.add_argument("--evidence-bytes", type=int, default=None)
    p.add_argument("--append", action="store_true")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    extracted = json.loads(Path(args.extract).read_text(encoding="utf-8"))
    model_rec = json.loads(Path(args.model_record).read_text(encoding="utf-8")) if args.model_record else {}
    arm = extracted.get("arm_coordinate")
    score = None
    if extracted.get("outcome") == "determination" and arm:
        reject_peek(arm)
        score = p4_score(args.incident, arm)
    ev = args.evidence_bytes
    if ev is None:
        ev = 0
    row = results_row(args.incident, args.representation, args.replicate, extracted, model_rec, score, ev)
    payload = {
        "extract": extracted,
        "score": None if score is None else {k: score[k] for k in score if k != "report"},
        "results_row": row,
        "p4_report": None if score is None else score.get("report"),
    }
    write_json(Path(args.out), payload)
    if args.append:
        payload["append"] = append_row(row)
        write_json(Path(args.out), payload)
    print(json.dumps({"ok": True, "out": args.out, "outcome": extracted.get("outcome"),
                      "restore_verdict": row.get("restore_verdict")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
