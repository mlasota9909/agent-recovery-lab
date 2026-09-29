"""P7 shared helpers: cells, ledger idempotency, results-row envelope, review finish."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, dump_lab_env_snapshot, review_dir, sha256_file,
    write_acceptance, write_artefacts, write_json, write_text,
)
from lab_paths import env, evidence_dir, lab_root
from lsn import lsn_int, lsn_norm
from results_schema import load_schema, type_errors, rule_errors

HEADLINE = "SC-01_20260824T091611Z"
HEADLINE_INCIDENT_ID = "i_20260824T091611Z_122142"
SC01_R0 = "25bff369c36784ae0ba8923f719036ca74b9ba560eddb672c3cba7fecfd64933"
SC01_R1 = "fbf77d349d539e698ef995f3ac602efb086e8a1b7191e951e21cc71b56dc8e88"
SC01_R2 = "0d0ebe449f0c57072ebf7229c926b7dee491c0fc15f3cc469e8b776dd6ec3c86"
RESULTS_ARM = {"arm_a": "deterministic", "naive": "naive", "arm_b": "model"}
COORD_FIELDS = ("wall_clock", "lsn", "snapshot", "skew_ms", "skew_bytes", "resolved_by")
PRINCIPAL_TOKEN_RE = (
    r"(?<![A-Za-z0-9_])(principal|usename|session_user|originating_uid|user_id|uid|lab_agent|lab_app)(?![A-Za-z0-9_])"
)


def root() -> Path:
    return lab_root()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_bin(name: str, args: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    envp = os.environ.copy()
    envp["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + envp["PYTHONPATH"] if envp.get("PYTHONPATH") else "")
    return subprocess.run(
        [str(root() / "bin" / name), *args],
        cwd=str(root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=envp,
    )


def ssh(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", env("VM_SSH"), cmd],
        text=True, capture_output=True, check=False, timeout=timeout,
    )


def cell_key(scenario: str, timing: str, arm: str, representation: str, replicate: int) -> str:
    return f"{scenario}|{timing}|{arm}|{representation}|{replicate}"


def planned_new_cells(plan: dict) -> list[dict]:
    cells = []
    for row in plan.get("per_cell") or []:
        if row.get("referenced"):
            continue
        n = int(row["replicates"])
        for i in range(1, n + 1):
            cells.append({
                "scenario": row["scenario"],
                "timing_pattern": row["timing_pattern"],
                "arm": row["arm"],
                "representation": row["representation"],
                "replicate": i,
                "cell_key": cell_key(row["scenario"], row["timing_pattern"], row["arm"], row["representation"], i),
            })
    return cells


def load_plan() -> dict:
    path = root() / "logs/review/K001/run-plan.json"
    if not path.is_file():
        raise SystemExit("precondition failed: logs/review/K001/run-plan.json missing")
    return json.loads(path.read_text(encoding="utf-8"))


def matrix_path() -> Path:
    return Path(env("RESULTS_ROOT")) / "matrix.jsonl"


def load_matrix_rows(path: Path | None = None) -> list[dict]:
    p = path or matrix_path()
    rows = []
    if not p.is_file():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def row_cell_key(row: dict) -> str | None:
    detail = (row.get("validation_detail") or {}) if isinstance(row.get("validation_detail"), dict) else {}
    matrix = detail.get("matrix") or {}
    scenario = row.get("scenario_id")
    timing = matrix.get("timing_pattern")
    arm = matrix.get("plan_arm") or {
        "deterministic": "arm_a", "naive": "naive", "model": "arm_b", "stub": "stub",
    }.get(row.get("arm"))
    representation = row.get("representation") if row.get("representation") != "none" else "NA"
    replicate = row.get("replicate")
    if not all([scenario, timing, arm, representation, replicate]):
        return None
    return cell_key(scenario, timing, arm, representation, int(replicate))


def recorded_cell_keys(rows: list[dict] | None = None) -> set[str]:
    keys = set()
    for row in rows or load_matrix_rows():
        k = row_cell_key(row)
        if k:
            keys.add(k)
    return keys


def ledger_lsn_ids(incident: str) -> list[str]:
    path = evidence_dir(incident) / "db.jsonl"
    lsns = []
    if not path.is_file():
        return lsns
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        lsn = rec.get("lsn")
        if lsn:
            lsns.append(lsn_norm(lsn))
    return lsns


def ledger_idempotency(incident: str) -> dict:
    """P1 commit-LSN idempotency + open/close containment (lab-ledger-verify)."""
    from lab_ledger_verify import load_jsonl, verify
    meta = json.loads((evidence_dir(incident) / "incident.json").read_text(encoding="utf-8"))
    rows = load_jsonl(evidence_dir(incident) / "db.jsonl")
    rec = verify(rows, meta["open_coordinate"]["lsn"], meta["close_coordinate"]["lsn"], incident)
    return {
        "incident": incident,
        "n_lsn_records": rec["records"],
        "duplicate_lsns": rec["duplicate_lsns"],
        "outside_open_close": rec["out_of_range"],
        "open_lsn": rec["open_lsn"],
        "close_lsn": rec["close_lsn"],
        "ok": rec["ok"] is True,
        "monotonic": rec["monotonic"],
        "duplicate_lsns_count": rec["duplicate_lsns_count"],
        "out_of_range_count": rec["out_of_range_count"],
    }


def resolve_lsn(lsn: str) -> dict:
    proc = run_bin("lab-coordinate", ["--lsn", lsn], timeout=60)
    if proc.returncode != 0:
        raise SystemExit(f"assertion failed: lab-coordinate --lsn {lsn}: {proc.stderr.strip() or proc.stdout.strip()}")
    raw = json.loads(proc.stdout)
    return {k: raw[k] for k in COORD_FIELDS}


def blank_results_row(meta: dict, *, arm: str, representation: str, replicate: int,
                      timing_pattern: str, plan_arm: str, reset_tier: str,
                      outcome: str, failure_reason: str | None,
                      chosen: dict | None, naive: dict | None,
                      err: dict, t_to_coordinate_ms: int, t_total_ms: int,
                      restore_attempted: bool, restore_verdict: str,
                      consistency_verdict: str, detail: dict,
                      evidence_bytes: int | None, token_count: int | None,
                      ranker_version: str | None, model_id: str | None,
                      fs_penalty_ms: int | None,
                      legit_rows_lost, legit_bytes_lost, damage_rows_retained, damage_bytes_retained) -> dict:
    now = utc_now()
    stamp = utc_stamp()
    matrix = {
        "timing_pattern": timing_pattern,
        "plan_arm": plan_arm,
        "outcome": outcome,
        "failure_reason": failure_reason,
        "replicate_index": replicate,
    }
    if isinstance(detail, dict):
        for flag in ("victim_rollback", "host_coord", "t2_skipped_reason", "p4_skipped"):
            if flag in detail:
                matrix[flag] = detail[flag]
    merged_detail = dict(detail or {})
    merged_detail["matrix"] = matrix
    row = {
        "run_id": f"r_{stamp}_{secrets.token_hex(3)}",
        "scenario_id": meta["scenario_id"],
        "incident_id": meta["incident_id"],
        "replicate": replicate,
        "run_ts": now,
        "supersedes": None,
        "arm": arm,
        "representation": representation,
        "ranker_version": ranker_version,
        "model_id": model_id,
        "harness_commit": harness_commit(),
        "ground_truth_coordinate": meta["oracle_coordinate"],
        "chosen_coordinate": chosen,
        "naive_coordinate": naive,
        "incident_open_coordinate": meta["open_coordinate"],
        "incident_close_coordinate": meta["close_coordinate"],
        "coord_error_bytes": err.get("coord_error_bytes"),
        "coord_error_ms": err.get("coord_error_ms"),
        "coord_direction": err.get("coord_direction"),
        "naive_coord_error_bytes": err.get("naive_coord_error_bytes"),
        "naive_coord_error_ms": err.get("naive_coord_error_ms"),
        "legit_rows_lost": legit_rows_lost,
        "legit_bytes_lost": legit_bytes_lost,
        "damage_rows_retained": damage_rows_retained,
        "damage_bytes_retained": damage_bytes_retained,
        "fs_granularity_penalty_ms": fs_penalty_ms,
        "restore_attempted": restore_attempted,
        "restore_verdict": restore_verdict,
        "consistency_verdict": consistency_verdict,
        "validation_detail": merged_detail,
        "t_to_coordinate_ms": t_to_coordinate_ms,
        "t_to_validated_restore_ms": None,
        "t_total_ms": t_total_ms,
        "evidence_bytes_presented": evidence_bytes,
        "token_count": token_count,
        "retrieval_calls": 1 if arm == "model" else None,
        "reset_tier": reset_tier,
        "snapshot_pre_injection": meta["snapshot_pre_injection"],
        "snapshot_post_capture": meta["snapshot_post_capture"],
        "workload_rate_tps": meta["workload_rate_tps"],
        "workload_mix": meta["workload_mix"],
        "ledger_integrity_ok": True,
        "notes": None,
    }
    schema = load_schema()
    errors = type_errors(schema, row) + rule_errors(row)
    if errors:
        raise SystemExit("assertion failed: row rejected: " + "; ".join(errors))
    return row


def harness_commit() -> str:
    lab = str(root())
    dirty = subprocess.run(
        ["git", "-C", lab, "status", "--porcelain", "--untracked-files=all"],
        text=True, capture_output=True, check=False,
    )
    if dirty.returncode != 0:
        raise SystemExit(f"precondition failed: git status: {dirty.stderr.strip()}")
    if dirty.stdout.strip():
        raise SystemExit(
            "refusing to produce a results row: harness working tree is dirty; "
            "commit or stash the following paths\n" + dirty.stdout
        )
    p = subprocess.run(["git", "-C", lab, "rev-parse", "HEAD"], text=True, capture_output=True, check=False)
    commit = p.stdout.strip()
    if p.returncode != 0 or len(commit) != 40:
        raise SystemExit(f"precondition failed: git rev-parse HEAD: {p.stderr.strip() or commit}")
    return commit


def append_matrix_row(row: dict) -> dict:
    dest = matrix_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = run_bin("lab-results", ["append", "--file", str(dest), "--row", json.dumps(row)])
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "lab-results append failed")
    scenario_path = Path(env("RESULTS_ROOT")) / f"{row['scenario_id']}.jsonl"
    proc2 = run_bin("lab-results", ["append", "--file", str(scenario_path), "--row", json.dumps(row)])
    if proc2.returncode != 0:
        raise SystemExit(proc2.stderr.strip() or proc2.stdout.strip() or "scenario results append failed")
    return json.loads(proc.stdout)


def freeze_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finish_review(task: str, rows: list[dict], artefacts: list[Path], observations: str,
                  extra_acceptance: str = "") -> None:
    dump_lab_env_snapshot(task)
    write_acceptance(task, rows, extra_acceptance)
    write_artefacts(task, artefacts)
    write_text(review_dir(task) / "observations.md", observations if observations.endswith("\n") else observations + "\n")


def stats(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean_s": statistics.mean(values) if values else None,
        "median_s": statistics.median(values) if values else None,
        "min_s": min(values) if values else None,
        "max_s": max(values) if values else None,
        "spread_s": (max(values) - min(values)) if values else None,
        "sd_s": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


def recover_after_t2(incident: str) -> dict:
    """T2 rolls PGDATA back; the host consumer is gone. Recreate the slot if
    needed, start heartbeat+consumer, wait for lab-slot --check, then restore
    the frozen db.jsonl so catch-up WAL is not appended onto the incident."""
    ed = evidence_dir(incident)
    ledger = ed / "db.jsonl"
    frozen_path = ed / "db.jsonl.frozen"
    if frozen_path.is_file():
        frozen = frozen_path.read_bytes()
    elif ledger.is_file():
        frozen = ledger.read_bytes()
    else:
        frozen = None
    if ledger.is_file():
        os.chmod(ledger, 0o644)
    try:
        slot = run_bin("lab-slot", ["--create"], timeout=90)
        run_bin("lab-heartbeat", ["--start"], timeout=60)
        cons = run_bin("lab-consumer", ["start", incident], timeout=90)
        barrier = run_bin("lab-barrier", [], timeout=180)
        return {
            "slot_exit": slot.returncode,
            "consumer_exit": cons.returncode,
            "barrier_exit": barrier.returncode,
            "barrier_stderr": (barrier.stderr or "")[-500:],
        }
    finally:
        run_bin("lab-consumer", ["stop", incident], timeout=60)
        if frozen is not None:
            if ledger.is_file():
                os.chmod(ledger, 0o644)
            ledger.write_bytes(frozen)
            os.chmod(ledger, 0o444)


def point_current(incident: str) -> None:
    archive = Path(env("ARCHIVE_ROOT"))
    if not (archive / incident).is_dir():
        raise SystemExit(f"precondition failed: archive {incident} is absent")
    tmp = archive / f".current.{incident}.{os.getpid()}"
    tmp.symlink_to(incident)
    tmp.replace(Path(env("ARCHIVE_CURRENT")))


def frozen_sc01_hashes() -> dict:
    inc = HEADLINE
    db = evidence_dir(inc) / "db.jsonl"
    results = Path(env("RESULTS_ROOT")) / "SC-01.jsonl"
    repr_base = root() / "var" / "repr" / inc
    live_repr = {}
    for name in ("R0", "R1", "R2"):
        man = json.loads((repr_base / name / "manifest.json").read_text(encoding="utf-8"))
        live_repr[name] = man["content_hash"]
    return {
        "db_jsonl_sha256": sha256_file(db) if db.is_file() else None,
        "results_sha256": sha256_file(results) if results.is_file() else None,
        "results_rows": sum(1 for line in results.read_text().splitlines() if line.strip()) if results.is_file() else 0,
        "repr": live_repr,
        "repr_recorded": {"R0": SC01_R0, "R1": SC01_R1, "R2": SC01_R2},
        "repr_unchanged": live_repr == {"R0": SC01_R0, "R1": SC01_R1, "R2": SC01_R2},
    }
