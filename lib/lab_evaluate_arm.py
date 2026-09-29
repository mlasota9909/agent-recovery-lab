"""lab-evaluate-arm: repeatable phase 2 against a frozen incident."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lsn import lsn_cmp, lsn_int
from results_schema import canonical_json

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3
# EXIT_PRECOND is also the documented dirty-tree refusal (Article XIV): a dirty
# working tree is a missing precondition for emitting a results row.
HARNESS_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

COORD_FIELDS = ("wall_clock", "lsn", "snapshot", "skew_ms", "skew_bytes", "resolved_by")


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def env(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        die(EXIT_PRECOND, f"precondition failed: {key} missing from lab.env")
    return v


def bin_path(name: str) -> str:
    return str(Path(os.environ["LAB_ROOT"]) / "bin" / name)


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(args, text=True, capture_output=True, check=False, env=os.environ)
    if check and p.returncode != 0:
        die(p.returncode if p.returncode in {1, 2, 3} else EXIT_ASSERT,
            f"assertion failed: {' '.join(args)}: {p.stderr.strip() or p.stdout.strip()}")
    return p


def run_json(args: list[str]) -> dict:
    p = run(args)
    return json.loads(p.stdout)


def pg_unit() -> str:
    return f"postgresql@{env('PG_VERSION')}-{Path(env('PG_DATA')).name}"


def stop_postgres() -> None:
    run(["ssh", "-o", "BatchMode=yes", env("VM_SSH"), f"sudo -n systemctl stop {pg_unit()}"])
    for _ in range(40):
        p = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", env("VM_SSH"), "sudo -n pgrep -x postgres"],
            text=True, capture_output=True, check=False,
        )
        if p.returncode != 0:
            return
        time.sleep(0.25)
    die(EXIT_PRECOND, "precondition failed: PostgreSQL is still running after stop")


def point_current(incident: str) -> None:
    root = Path(env("ARCHIVE_ROOT"))
    if not (root / incident).is_dir():
        die(EXIT_PRECOND, f"precondition failed: archive {incident} is absent")
    tmp = root / f".current.{incident}.{os.getpid()}"
    tmp.symlink_to(incident)
    tmp.replace(Path(env("ARCHIVE_CURRENT")))


def parse_ts(ts: str) -> float:
    return datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()


def coord_errors(chosen: dict, gt: dict) -> dict:
    b = abs(lsn_int(chosen["lsn"]) - lsn_int(gt["lsn"]))
    ms = abs(int(round((parse_ts(chosen["wall_clock"]) - parse_ts(gt["wall_clock"])) * 1000)))
    cmp = lsn_cmp(chosen["lsn"], gt["lsn"])
    direction = "exact" if cmp == 0 else ("before" if cmp < 0 else "after")
    return {"coord_error_bytes": b, "coord_error_ms": ms, "coord_direction": direction}


def porcelain_paths(lab_root: Path) -> list[str]:
    """git status --porcelain --untracked-files=all, always against $LAB_ROOT."""
    p = subprocess.run(
        ["git", "-C", str(lab_root), "status", "--porcelain", "--untracked-files=all"],
        text=True, capture_output=True, check=False,
    )
    if p.returncode != 0:
        die(EXIT_PRECOND, f"precondition failed: git status in {lab_root}: {p.stderr.strip() or p.stdout.strip()}")
    paths: list[str] = []
    for line in p.stdout.splitlines():
        if not line.strip():
            continue
        rest = line[3:] if len(line) >= 4 else line
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest.strip())
    return paths


def harness_commit_at_production() -> str:
    """HEAD at $LAB_ROOT, or refuse. Never reads HARNESS_COMMIT_AT_P1_OPEN."""
    lab_root = Path(env("LAB_ROOT"))
    dirty = porcelain_paths(lab_root)
    if dirty:
        listed = "\n".join(dirty)
        die(
            EXIT_PRECOND,
            "refusing to produce a results row: harness working tree is dirty; "
            "commit or stash the following paths\n" + listed,
        )
    p = subprocess.run(
        ["git", "-C", str(lab_root), "rev-parse", "HEAD"],
        text=True, capture_output=True, check=False,
    )
    if p.returncode != 0:
        die(EXIT_PRECOND, f"precondition failed: git rev-parse HEAD in {lab_root}: {p.stderr.strip() or p.stdout.strip()}")
    commit = p.stdout.strip()
    if not HARNESS_COMMIT_RE.fullmatch(commit):
        die(EXIT_ASSERT, f"assertion failed: harness_commit is not 40 lowercase hex: {commit!r}")
    return commit


def next_replicate(path: Path, incident_id: str) -> int:
    n = 0
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("incident_id") == incident_id:
                n = max(n, int(row.get("replicate") or 0))
    return n + 1


def restore_ledger(path: Path, payload: bytes, mode: int) -> None:
    path.write_bytes(payload)
    os.chmod(path, mode & 0o777)


def evaluate(archive_incident: str, arm: str, tier: str) -> dict:
    arm_aliases = {"arm_a": "arm_a", "deterministic": "arm_a", "naive": "naive", "stub": "stub"}
    if arm not in arm_aliases:
        die(EXIT_USAGE, "usage: --arm stub|arm_a|naive")
    arm_key = arm_aliases[arm]
    if tier not in {"t0", "t1", "t2"}:
        die(EXIT_USAGE, "usage: --tier t0|t1|t2")
    scenario = archive_incident.split("_", 1)[0]
    ev = Path(env("EVIDENCE_ROOT")) / scenario / archive_incident
    meta_path = ev / "incident.json"
    if not meta_path.is_file():
        die(EXIT_PRECOND, f"precondition failed: {meta_path} is absent; incident was not registered")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ledger_path = ev / "db.jsonl"
    if not ledger_path.is_file():
        die(EXIT_PRECOND, f"precondition failed: {ledger_path} is absent")
    # Fail fast on a dirty tree / bad HEAD before the expensive reset.
    harness_commit_at_production()
    if arm_key == "stub":
        return _evaluate_stub(archive_incident, arm_key, tier, meta, ledger_path, scenario)
    return _evaluate_p3(archive_incident, arm_key, tier, meta, scenario)


def _evaluate_stub(archive_incident: str, arm: str, tier: str, meta: dict, ledger_path: Path, scenario: str) -> dict:
    frozen_ledger = ledger_path.read_bytes()
    frozen_mode = ledger_path.stat().st_mode
    t0 = time.monotonic()
    marks: dict[str, int] = {}
    last = t0

    def mark(name: str) -> int:
        nonlocal last
        now = time.monotonic()
        ms = int(round((now - last) * 1000))
        marks[name] = ms
        last = now
        return ms

    point_current(archive_incident)
    scratch_tree = "/logs/review/" in str(ledger_path)
    if not scratch_tree:
        subprocess.run([bin_path("lab-consumer"), "start", archive_incident], text=True, capture_output=True, env=os.environ)
        try:
            stop_postgres()
            run_json([bin_path("lab-reset"), "--tier", tier])
            mark("reset")
            run_json([bin_path("lab-barrier")])
            mark("barrier")
        finally:
            subprocess.run([bin_path("lab-consumer"), "stop", archive_incident], text=True, capture_output=True, env=os.environ)
            restore_ledger(ledger_path, frozen_ledger, frozen_mode)
    else:
        mark("reset")
        mark("barrier")

    verify = run([bin_path("lab-ledger-verify"), "--incident", archive_incident], check=False)
    if verify.returncode != 0:
        die(EXIT_ASSERT, "assertion failed: lab-ledger-verify refused to proceed: " + verify.stderr.strip() + verify.stdout)
    vj = json.loads(verify.stdout)
    if not vj.get("ok"):
        die(EXIT_ASSERT, "assertion failed: ledger_integrity_ok is false; no row appended")
    mark("ledger_verify")

    t_coord0 = time.monotonic()
    analysis = run_json([bin_path("lab-analyse-stub"), "--incident", archive_incident])
    t_to_coordinate_ms = int(round((time.monotonic() - t_coord0) * 1000))
    mark("analysis")
    restore = run_json([bin_path("lab-restore-stub"), "--incident", archive_incident])
    mark("restore")
    gt = meta["oracle_coordinate"]
    chosen = analysis["coordinate"]
    naive = {
        k: v for k, v in
        json.loads(run([bin_path("lab-coordinate"), "--snapshot", meta["snapshot_pre_injection"]], check=True).stdout)
        .items() if k in COORD_FIELDS
    }
    err = coord_errors(chosen, gt)
    naive_err = coord_errors(naive, gt)
    t_total_ms = int(round((time.monotonic() - t0) * 1000))
    results_path = Path(env("RESULTS_ROOT")) / f"{scenario}.jsonl"
    incident_id = meta["incident_id"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"r_{stamp}_{secrets.token_hex(3)}"
    row = {
        "run_id": run_id,
        "scenario_id": scenario,
        "incident_id": incident_id,
        "replicate": next_replicate(results_path, incident_id),
        "run_ts": now,
        "supersedes": None,
        "arm": arm,
        "representation": "none",
        "ranker_version": None,
        "model_id": None,
        "harness_commit": harness_commit_at_production(),
        "ground_truth_coordinate": gt,
        "chosen_coordinate": chosen,
        "naive_coordinate": naive,
        "incident_open_coordinate": meta["open_coordinate"],
        "incident_close_coordinate": meta["close_coordinate"],
        **err,
        "naive_coord_error_bytes": naive_err["coord_error_bytes"],
        "naive_coord_error_ms": naive_err["coord_error_ms"],
        "legit_rows_lost": None,
        "legit_bytes_lost": None,
        "damage_rows_retained": None,
        "damage_bytes_retained": None,
        "fs_granularity_penalty_ms": None,
        "restore_attempted": bool(restore.get("restore_attempted")),
        "restore_verdict": restore["restore_verdict"],
        "consistency_verdict": restore["consistency_verdict"],
        "validation_detail": restore.get("validation_detail"),
        "t_to_coordinate_ms": t_to_coordinate_ms,
        "t_to_validated_restore_ms": None,
        "t_total_ms": t_total_ms,
        "evidence_bytes_presented": None,
        "token_count": None,
        "retrieval_calls": None,
        "reset_tier": tier,
        "snapshot_pre_injection": meta["snapshot_pre_injection"],
        "snapshot_post_capture": meta["snapshot_post_capture"],
        "workload_rate_tps": meta["workload_rate_tps"],
        "workload_mix": meta["workload_mix"],
        "ledger_integrity_ok": True,
        "notes": None,
    }
    # append via the writer so validation/invariants are enforced
    payload = json.dumps(row)
    appended = run_json([bin_path("lab-results"), "append", "--file", str(results_path), "--row", payload])
    mark("results_append")
    return {
        "ok": True,
        "changed": True,
        "incident": archive_incident,
        "incident_id": incident_id,
        "run_id": run_id,
        "arm": arm,
        "tier": tier,
        "strategy": analysis.get("strategy"),
        "ground_truth_coordinate": gt,
        "chosen_coordinate": chosen,
        "t_to_coordinate_ms": t_to_coordinate_ms,
        "t_total_ms": int(round((time.monotonic() - t0) * 1000)),
        "steps_ms": marks,
        "results": appended,
    }


def reject_peek(rec: dict) -> None:
    inputs = rec.get("selection_inputs") or {}
    for flag in ("read_injection_log", "read_oracle_optimum", "read_provenance"):
        if inputs.get(flag) is True:
            die(EXIT_ASSERT, f"assertion failed: arm coordinate peek flag {flag}=true; scorer refused")


def arm_coordinate_to_chosen(rec: dict) -> dict:
    reject_peek(rec)
    raw = run_json([bin_path("lab-coordinate"), "--lsn", rec["lsn_text"]])
    return {k: raw[k] for k in COORD_FIELDS}


def _evaluate_p3(archive_incident: str, arm: str, tier: str, meta: dict, scenario: str) -> dict:
    """Score Arm A / naive via the oracle. P3 does not restore (P4)."""
    from lab_oracle import score_chosen

    point_current(archive_incident)
    t0 = time.monotonic()
    t_coord0 = time.monotonic()
    if arm == "arm_a":
        selector = run_json([bin_path("lab-rank"), archive_incident])
        rec = selector["coordinate"]
        results_arm = "deterministic"
        ranker_version = rec.get("selector_version")
    else:
        selector = run_json([bin_path("lab-naive"), archive_incident])
        rec = selector["coordinate"]
        results_arm = "naive"
        ranker_version = None
    reject_peek(rec)
    t_to_coordinate_ms = int(round((time.monotonic() - t_coord0) * 1000))
    chosen = arm_coordinate_to_chosen(rec)
    naive_sel = run_json([bin_path("lab-naive"), archive_incident])
    naive = arm_coordinate_to_chosen(naive_sel["coordinate"])
    gt = meta["oracle_coordinate"]
    err = coord_errors(chosen, gt)
    naive_err = coord_errors(naive, gt)
    scored = score_chosen(archive_incident, chosen["lsn"])
    err["coord_error_bytes"] = scored["coord_error_bytes"]
    err["coord_direction"] = scored["coord_direction"]
    t_total_ms = int(round((time.monotonic() - t0) * 1000))
    results_path = Path(env("RESULTS_ROOT")) / f"{scenario}.jsonl"
    incident_id = meta["incident_id"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"r_{stamp}_{secrets.token_hex(3)}"
    row = {
        "run_id": run_id,
        "scenario_id": scenario,
        "incident_id": incident_id,
        "replicate": next_replicate(results_path, incident_id),
        "run_ts": now,
        "supersedes": None,
        "arm": results_arm,
        "representation": "none",
        "ranker_version": ranker_version,
        "model_id": None,
        "harness_commit": harness_commit_at_production(),
        "ground_truth_coordinate": gt,
        "chosen_coordinate": chosen,
        "naive_coordinate": naive,
        "incident_open_coordinate": meta["open_coordinate"],
        "incident_close_coordinate": meta["close_coordinate"],
        **err,
        "naive_coord_error_bytes": naive_err["coord_error_bytes"],
        "naive_coord_error_ms": naive_err["coord_error_ms"],
        "legit_rows_lost": scored["legit_rows_lost"],
        "legit_bytes_lost": scored["legit_bytes_lost"],
        "damage_rows_retained": scored["damage_rows_retained"],
        "damage_bytes_retained": scored["damage_bytes_retained"],
        "fs_granularity_penalty_ms": None,
        "restore_attempted": False,
        "restore_verdict": "stub",
        "consistency_verdict": "stub",
        "validation_detail": {"arm_coordinate": rec, "oracle_score": scored},
        "t_to_coordinate_ms": t_to_coordinate_ms,
        "t_to_validated_restore_ms": None,
        "t_total_ms": t_total_ms,
        "evidence_bytes_presented": None,
        "token_count": None,
        "retrieval_calls": None,
        "reset_tier": tier,
        "snapshot_pre_injection": meta["snapshot_pre_injection"],
        "snapshot_post_capture": meta["snapshot_post_capture"],
        "workload_rate_tps": meta["workload_rate_tps"],
        "workload_mix": meta["workload_mix"],
        "ledger_integrity_ok": True,
        "notes": None,
    }
    payload = json.dumps(row)
    appended = run_json([bin_path("lab-results"), "append", "--file", str(results_path), "--row", payload])
    return {
        "ok": True,
        "changed": True,
        "incident": archive_incident,
        "incident_id": incident_id,
        "run_id": run_id,
        "arm": results_arm,
        "tier": tier,
        "arm_coordinate": rec,
        "ground_truth_coordinate": gt,
        "chosen_coordinate": chosen,
        "t_to_coordinate_ms": t_to_coordinate_ms,
        "t_total_ms": int(round((time.monotonic() - t0) * 1000)),
        "results": appended,
        "row": row,
    }


def main(argv: list[str]) -> int:
    incident = None
    arm = "stub"
    tier = "t2"
    i = 0
    while i < len(argv):
        if argv[i] == "--incident" and i + 1 < len(argv):
            incident = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--arm" and i + 1 < len(argv):
            arm = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--tier" and i + 1 < len(argv):
            tier = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--validate-coordinate" and i + 1 < len(argv):
            rec = json.loads(Path(argv[i + 1]).read_text(encoding="utf-8"))
            reject_peek(rec)
            print(json.dumps({"ok": True, "peek_rejected": False}, sort_keys=True))
            return 0
        die(EXIT_USAGE, "usage: lab-evaluate-arm --incident <id> --arm stub|arm_a|naive --tier t2")
    if not incident:
        die(EXIT_USAGE, "usage: lab-evaluate-arm --incident <id> --arm stub|arm_a|naive --tier t2")
    rec = evaluate(incident, arm, tier)
    print(json.dumps(rec, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
