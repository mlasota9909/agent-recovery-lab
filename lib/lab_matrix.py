"""lab-matrix: unattended per-cell orchestrator. Failed runs become rows."""
from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path

from lab_evaluate_arm import coord_errors, reject_peek
from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, write_json
from lab_p7 import (
    COORD_FIELDS, HEADLINE, RESULTS_ARM, append_matrix_row, blank_results_row, cell_key,
    harness_commit, ledger_idempotency, load_matrix_rows, load_plan, matrix_path,
    planned_new_cells, point_current, recorded_cell_keys, root, row_cell_key, run_bin,
)
from lab_paths import env, evidence_dir
from lab_snapshot_coord import naive_from_manifest, resolve_lsn_from_manifest
from lsn import lsn_int

SCENARIO_DIR = {
    "SC-02": "sc02",
    "SC-03": "sc03",
    "SC-04": "sc04",
}


def latest_incident(scenario: str) -> str | None:
    root_ev = Path(env("EVIDENCE_ROOT")) / scenario
    if not root_ev.is_dir():
        return None
    cands = [p.name for p in root_ev.iterdir() if (p / "incident.json").is_file()]
    return sorted(cands)[-1] if cands else None


def load_meta(incident: str) -> dict:
    return json.loads((evidence_dir(incident) / "incident.json").read_text(encoding="utf-8"))


def activate_runtime(incident: str) -> dict:
    """Select the committed runtime record inside this long-lived orchestrator."""
    runtime_root = root() / "runtime" / "incidents"
    matches = []
    for path in sorted(runtime_root.glob("*.env")):
        values = {}
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw and "=" in raw:
                k, v = raw.split("=", 1)
                values[k] = v
        if values.get("ARCHIVE_INCIDENT") == incident:
            matches.append((path, values))
    if len(matches) != 1:
        raise RuntimeError(f"expected one incident runtime for {incident}, found {len(matches)}")
    path, values = matches[0]
    os.environ.update(values)
    os.environ.update({
        "LAB_ACTIVE_INCIDENT": incident,
        "DS_PARENT": values["INC_DS"],
        "DS_PGDATA": values["INC_DS"] + "/pgdata",
        "DS_PROTECTED": values["INC_DS"] + "/protected",
        "PG_DATA": values["INC_PGDATA"],
        "PG_PORT": values["INC_PG_PORT"],
        "MNT_PROTECTED": values["INC_PROTECTED"],
        "SLOT_NAME": values["INC_SLOT"],
    })
    return {"runtime": str(path), **values}


def ensure_c5(incident: str) -> dict:
    """Window metrics + anomaly scores. R1/R2 consume every C5 window, including
    non-anomalous ones. lab-candidates (Arm A) still requires a 3σ hit."""
    for name in ("lab-analytics", "lab-anomaly"):
        proc = run_bin(name, [incident], timeout=180)
        if proc.returncode != 0:
            raise RuntimeError(f"{name} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return {"ok": True}


def ensure_analytics(incident: str) -> dict:
    ensure_c5(incident)
    proc = run_bin("lab-candidates", [incident], timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"lab-candidates failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return {"ok": True}


def run_arm_a(incident: str) -> dict:
    ensure_analytics(incident)
    proc = run_bin("lab-rank", [incident], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "lab-rank failed")
    return json.loads(proc.stdout)


def run_naive(incident: str) -> dict:
    proc = run_bin("lab-naive", [incident], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "lab-naive failed")
    return json.loads(proc.stdout)


def run_arm_b(incident: str, representation: str, replicate: int, dest: Path) -> dict:
    ensure_c5(incident)
    repr_root = root() / "var" / "repr" / incident
    for name in ("R0", "R1", "R2"):
        if (repr_root / name / "manifest.json").is_file():
            continue
        proc = run_bin(f"lab-repr-{name.lower()}", [incident], timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(
                f"lab-repr-{name.lower()} failed: "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
    dest.mkdir(parents=True, exist_ok=True)
    proc = run_bin("lab-arm-b", [
        "--incident", incident, "--representation", representation,
        "--replicates", "1", "--dest", str(dest),
    ], timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "lab-arm-b failed")
    rec = json.loads((dest / "replicate-0.json").read_text(encoding="utf-8"))
    rec["replicate_index"] = replicate
    return rec


def p4_maybe(incident: str, arm_coord: dict) -> dict | None:
    """Run unchanged P4 when the SC-01 oracle-manifest exists. New scenarios
    have no such file; skip rather than crash so the determination is still a row."""
    from lab_arm_b_score import p4_score
    man = evidence_dir(incident) / "oracle-manifest.json"
    if not man.is_file():
        return {"skipped": True, "reason": "oracle-manifest.json absent; P4 validator is SC-01-shaped"}
    try:
        return p4_score(incident, arm_coord)
    except SystemExit as exc:
        return {"skipped": True, "reason": f"p4 SystemExit: {exc}"}
    except (Exception, SystemExit) as exc:
        return {"skipped": True, "reason": f"p4 score failed: {exc}"}


def chosen_from_arm(incident: str, arm: dict) -> dict:
    proc = run_bin("lab-coordinate", ["--incident", incident, "--lsn", arm["lsn_text"]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "live lab-coordinate failed")
    rec = json.loads(proc.stdout)
    if rec.get("resolved_by") != "live_heartbeat":
        raise RuntimeError(f"live incident resolved by {rec.get('resolved_by')}, expected live_heartbeat")
    return {k: rec[k] for k in COORD_FIELDS}


def validation_for(incident: str, scenario: str, arm_coord: dict, chosen: dict) -> dict:
    if scenario == "SC-02":
        from lab_arm_b_score import p4_score
        return p4_score(incident, arm_coord)
    from lab_validate_set import validate_set
    inj = json.loads((evidence_dir(incident) / "injection.json").read_text(encoding="utf-8"))
    cut = lsn_int(chosen["lsn"])
    if scenario == "SC-03":
        identified = [{"xid": op["xid"]} for op in inj["ops"] if lsn_int(op["commit_lsn"]) >= cut]
    elif scenario == "SC-04":
        identified = [{"row_id": op["row_id"], "xid": op["xid"]} for op in inj["ops"]
                      if lsn_int(op["commit_lsn"]) >= cut]
    else:
        raise RuntimeError(f"no validation path for {scenario}")
    scored = validate_set(incident, identified, chosen["lsn"])
    if scored["verdict"] == "set_correct" and scored["legitimate_dml_sacrificed"] == 0:
        row_verdict = "correct"
    elif scored["earliest_correctly_bounded"]:
        row_verdict = "incorrect_safe"
    else:
        row_verdict = "incorrect_corrupt"
    return {
        "restore_verdict": row_verdict,
        "consistency_verdict": "consistent" if scored["verdict"] == "set_correct" else "inconsistent",
        "legit_rows_lost": scored["legitimate_dml_sacrificed"],
        "damage_rows_retained": scored["fn"],
        "legit_bytes_lost": None,
        "damage_bytes_retained": None,
        "set_validation": scored,
    }


def naive_arm_record(meta: dict, naive: dict, error_seconds: int) -> dict:
    return {
        "incident_id": meta["incident_id"],
        "arm": "naive",
        "selector_version": "p3-naive-1",
        "representation": "n/a",
        "lsn_text": naive["lsn"],
        "lsn_int": lsn_int(naive["lsn"]),
        "wall_clock": naive["wall_clock"],
        "snapshot": naive["snapshot"],
        "chosen_candidate_id": None,
        "rationale": "last archive snapshot at or before approx_incident_time + declared error (host-side)",
        "selection_inputs": {
            "ledger_view": "snapshots.json",
            "approx_incident_time": meta.get("approx_incident_time"),
            "incident_time_error_seconds": error_seconds,
            "read_injection_log": False,
            "read_oracle_optimum": False,
            "read_provenance": False,
        },
    }


def failure_row(meta: dict, cell: dict, reason: str, t_ms: int) -> dict:
    return blank_results_row(
        meta,
        arm=RESULTS_ARM[cell["arm"]],
        representation="none" if cell["representation"] == "NA" else cell["representation"],
        replicate=cell["replicate"],
        timing_pattern=cell["timing_pattern"],
        plan_arm=cell["arm"],
        reset_tier="t2",
        outcome="run_failure",
        failure_reason=reason,
        chosen=None,
        naive=None,
        err={},
        t_to_coordinate_ms=t_ms,
        t_total_ms=t_ms,
        restore_attempted=False,
        restore_verdict="stub",
        consistency_verdict="stub",
        detail={"failure_reason": reason},
        evidence_bytes=None,
        token_count=None,
        ranker_version=None,
        model_id=env("MODEL_ID") if cell["arm"] == "arm_b" else None,
        fs_penalty_ms=None,
        legit_rows_lost=None, legit_bytes_lost=None,
        damage_rows_retained=None, damage_bytes_retained=None,
    )


def success_row(meta: dict, cell: dict, *, chosen, naive, arm_rec, outcome, t_ms,
                restore, evidence_len, tokens, model_id, ranker_version, extra_detail) -> dict:
    gt = meta["oracle_coordinate"]
    err = {"coord_error_bytes": None, "coord_error_ms": None, "coord_direction": None,
           "naive_coord_error_bytes": None, "naive_coord_error_ms": None}
    if chosen:
        err.update(coord_errors(chosen, gt))
    # Frozen results-row rule 5: if chosen is null, all coordinate-error
    # fields (including naive_*) must be null. A refusal still records
    # naive_coordinate; it must not carry naive_coord_error_*.
    if naive and chosen:
        nerr = coord_errors(naive, gt)
        err["naive_coord_error_bytes"] = nerr["coord_error_bytes"]
        err["naive_coord_error_ms"] = nerr["coord_error_ms"]
    restore_attempted = False
    restore_verdict = "stub"
    consistency_verdict = "stub"
    legit = damage = legit_b = damage_b = None
    if restore:
        restore_attempted = True
        restore_verdict = restore["restore_verdict"]
        consistency_verdict = restore["consistency_verdict"]
        legit = restore.get("legit_rows_lost")
        damage = restore.get("damage_rows_retained")
        legit_b = restore.get("legit_bytes_lost")
        damage_b = restore.get("damage_bytes_retained")
    fs_penalty = None
    extra = dict(extra_detail or {})
    extra["arm_coordinate"] = arm_rec
    if restore:
        extra["p4"] = {k: restore[k] for k in restore if k != "report"}
    gap = (meta.get("checkpoint_gap_seconds") if isinstance(meta.get("checkpoint_gap_seconds"), (int, float))
           else (meta.get("incident_extra") or {}).get("checkpoint_gap_seconds") if False else None)
    # checkpoint gap lives on incident extra written into incident.json
    gap = meta.get("checkpoint_gap_seconds")
    if gap is None:
        gap = (json.loads((evidence_dir(meta["archive_incident"]) / "sc02-oracle.json").read_text())
               .get("checkpoint_gap_seconds")
               if cell["scenario"] == "SC-02" and (evidence_dir(meta["archive_incident"]) / "sc02-oracle.json").is_file()
               else None)
    if gap is not None and chosen:
        fs_penalty = int(round(float(gap) * 1000))
    return blank_results_row(
        meta,
        arm=RESULTS_ARM[cell["arm"]],
        representation="none" if cell["representation"] == "NA" else cell["representation"],
        replicate=cell["replicate"],
        timing_pattern=cell["timing_pattern"],
        plan_arm=cell["arm"],
        reset_tier="t2",
        outcome=outcome,
        failure_reason=None,
        chosen=chosen,
        naive=naive,
        err=err,
        t_to_coordinate_ms=t_ms,
        t_total_ms=t_ms,
        restore_attempted=restore_attempted,
        restore_verdict=restore_verdict,
        consistency_verdict=consistency_verdict,
        detail=extra,
        evidence_bytes=evidence_len,
        token_count=tokens,
        ranker_version=ranker_version,
        model_id=model_id,
        fs_penalty_ms=fs_penalty,
        legit_rows_lost=legit, legit_bytes_lost=legit_b,
        damage_rows_retained=damage, damage_bytes_retained=damage_b,
    )


def run_cell(cell: dict, *, force: bool = False) -> dict:
    if cell["scenario"] == "SC-01":
        return {"ok": True, "skipped": True, "reason": "sc01_referenced"}
    existing = recorded_cell_keys()
    if not force and cell["cell_key"] in existing:
        return {"ok": True, "skipped": True, "reason": "already_recorded", "cell_key": cell["cell_key"]}
    incident = latest_incident(cell["scenario"])
    if not incident:
        raise RuntimeError(f"no frozen incident for {cell['scenario']}; generate first")
    if incident.startswith("SC-01"):
        raise RuntimeError("refusing to evaluate an SC-01 incident in lab-matrix")
    point_current(incident)
    runtime = activate_runtime(incident)
    meta = load_meta(incident)
    harness_commit()
    t0 = time.monotonic()
    os.environ.pop("LAB_P7_HOST_COORD", None)
    os.environ.pop("LAB_P7_HOST_INCIDENT", None)
    extra_detail: dict = {
        "victim_rollback": False,
        "host_coord": False,
        "incident_runtime": runtime["runtime"],
        "live_isolated_cluster": True,
    }
    try:
        error_s = int(os.environ.get("SC01_NAIVE_TIME_ERROR_SECONDS") or "20")
        naive_live = run_naive(incident)
        naive_sel = naive_live
        naive_arm = naive_live["coordinate"]
        naive = chosen_from_arm(incident, naive_arm)
        reject_peek(naive_sel["coordinate"])
        restore = None
        evidence_len = None
        tokens = None
        model_id = None
        ranker_version = None
        arm_rec = None
        chosen = None
        outcome = "determination"
        if cell["arm"] == "arm_a":
            sel = run_arm_a(incident)
            arm_rec = sel["coordinate"]
            reject_peek(arm_rec)
            chosen = chosen_from_arm(incident, arm_rec)
            ranker_version = arm_rec.get("selector_version")
        elif cell["arm"] == "naive":
            arm_rec = naive_arm
            chosen = naive
        else:
            dest = root() / "var" / "arm_b" / incident / cell["representation"] / f"k{cell['replicate']}"
            rec = run_arm_b(incident, cell["representation"], cell["replicate"], dest)
            arm_rec = rec.get("arm_coordinate")
            outcome = rec.get("outcome") or "refusal"
            tokens = rec.get("prompt_tokens")
            model_id = env("MODEL_ID")
            prompt_path = dest / "replicate-0.prompt"
            evidence_len = prompt_path.stat().st_size if prompt_path.is_file() else None
            if outcome == "determination" and arm_rec:
                reject_peek(arm_rec)
                chosen = chosen_from_arm(incident, arm_rec)
            else:
                chosen = None
                outcome = "refusal"
        if outcome == "determination" and chosen and arm_rec:
            restore = validation_for(incident, cell["scenario"], arm_rec, chosen)
        t_ms = int(round((time.monotonic() - t0) * 1000))
        try:
            row = success_row(
                meta, cell, chosen=chosen, naive=naive, arm_rec=arm_rec, outcome=outcome,
                t_ms=t_ms, restore=restore, evidence_len=evidence_len, tokens=tokens,
                model_id=model_id, ranker_version=ranker_version, extra_detail=extra_detail,
            )
            if force:
                predecessors = [r for r in load_matrix_rows() if row_cell_key(r) == cell["cell_key"]
                                and r.get("run_id") != row.get("run_id")]
                if predecessors:
                    row["supersedes"] = predecessors[-1]["run_id"]
            appended = append_matrix_row(row)
        except SystemExit as exc:
            raise RuntimeError(f"results-row rejected: {exc}") from exc
        return {"ok": True, "skipped": False, "run_id": row["run_id"], "outcome": outcome,
                "cell_key": cell["cell_key"], "append": appended}
    except Exception as exc:
        t_ms = int(round((time.monotonic() - t0) * 1000))
        reason = str(exc)[:500]
        row = failure_row(meta, cell, reason, t_ms)
        if force:
            predecessors = [r for r in load_matrix_rows() if row_cell_key(r) == cell["cell_key"]
                            and r.get("run_id") != row.get("run_id")]
            if predecessors:
                row["supersedes"] = predecessors[-1]["run_id"]
        appended = append_matrix_row(row)
        return {"ok": True, "skipped": False, "run_id": row["run_id"], "outcome": "run_failure",
                "failure_reason": reason, "cell_key": cell["cell_key"], "append": appended,
                "traceback": traceback.format_exc()[-1500:]}


def run_plan(plan: dict | None = None, *, force: bool = False) -> dict:
    plan = plan or load_plan()
    cells = planned_new_cells(plan)
    results = []
    for cell in cells:
        results.append(run_cell(cell, force=force))
    return {"ok": True, "n": len(results), "results": results}


def main(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="lab-matrix")
    p.add_argument("--plan", help="run-plan.json")
    p.add_argument("--cell", help="scenario|timing|arm|representation|replicate")
    p.add_argument("--force", action="store_true")
    p.add_argument("--idempotency-check", metavar="INCIDENT")
    args = p.parse_args(argv)
    if args.idempotency_check:
        rec = ledger_idempotency(args.idempotency_check)
        print(json.dumps(rec, sort_keys=True))
        return 0 if rec.get("ok") else EXIT_ASSERT
    if args.cell:
        parts = args.cell.split("|")
        if len(parts) != 5:
            die(EXIT_USAGE, "usage: --cell scenario|timing|arm|rep|replicate")
        cell = {
            "scenario": parts[0], "timing_pattern": parts[1], "arm": parts[2],
            "representation": parts[3], "replicate": int(parts[4]),
            "cell_key": cell_key(parts[0], parts[1], parts[2], parts[3], int(parts[4])),
        }
        out = run_cell(cell, force=args.force)
        print(json.dumps(out, sort_keys=True, default=str))
        return 0
    plan = json.loads(Path(args.plan).read_text()) if args.plan else load_plan()
    out = run_plan(plan, force=args.force)
    print(json.dumps({"ok": True, "n": out["n"],
                      "outcomes": [r.get("outcome") or r.get("reason") for r in out["results"]]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
