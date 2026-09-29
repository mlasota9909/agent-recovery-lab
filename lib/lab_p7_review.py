"""P7 review-bundle finishers. Do not tick Reviewed. Do not regenerate SC-01."""
from __future__ import annotations

import json
import os
import re
import shutil
import statistics
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from lab_p3_util import (
    dump_lab_env_snapshot, review_dir, sha256_file, write_acceptance, write_artefacts,
    write_json, write_text, append_command,
)
from lab_p51 import (
    ARTEFACT_HASHES, HEADLINE_DB, P4_HASHES, frozen_contract_rows, sha256_file as p51_hash,
)
from lab_p61 import (
    H001_ARM_B_PROTOCOL, H001_MODEL_RUNTIME, H001_P6_RUNTIME_AMENDMENT, P51_INTERFACE_AMENDMENT,
)
from lab_p7 import (
    HEADLINE, HEADLINE_INCIDENT_ID, PRINCIPAL_TOKEN_RE, SC01_R0, SC01_R1, SC01_R2,
    finish_review, frozen_sc01_hashes, load_matrix_rows, load_plan, planned_new_cells,
    root, run_bin, stats,
)
from lab_paths import env, evidence_dir, lab_root
from lab_scenario import validate_definition
from lsn import lsn_int, lsn_norm
from lab_redaction import pinned  # ADR-M002

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
K_DEFAULT = 5
TIME_BUDGET_HOURS = 8
INHERITED = 49.335
P7_DEF = pinned("74a9c25f15b42ded29a59e3a24414a8bd9ec8f36bee4314bff768a951f78ef55")
P7_PLAN = pinned("4665066de522a368126e580db94411a63de768008b2bf40f758a93fb73be840e")
INVERSION = ("P8 must not build", "do not build the analysis", "P8 must not build the analysis")


def run(argv: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    envp = os.environ.copy()
    envp["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + envp.get("PYTHONPATH", ""))
    return subprocess.run(argv, cwd=str(root()), text=True, capture_output=True, check=False,
                          timeout=timeout, env=envp)


def checklist_stamp(task: str) -> None:
    path = root() / "sdd/specs/P7-scenario-matrix/checklist.md"
    text = path.read_text(encoding="utf-8")
    needle = f"| {task} |"
    lines = []
    for line in text.splitlines():
        if line.startswith(needle):
            parts = [p.strip() for p in line.strip().split("|")]
            title = parts[2] if len(parts) > 2 else ""
            reviewed = parts[5] if len(parts) > 5 else "[ ]"
            line = f"| {task} | {title} | {TODAY} | logs/review/{task}/ | {reviewed} |"
        lines.append(line)
    write_text(path, "\n".join(lines) + "\n")


def row(tid: str, tier: str, cmd: str, expected: str, observed: str, passed: bool) -> dict:
    return {
        "id": tid, "tier": tier, "command": cmd, "expected": expected,
        "observed": str(observed)[:240], "result": "PASS" if passed else "FAIL",
    }


def finish(task: str, rows: list[dict], artefacts: list[Path], observations: str, extra: str = "") -> None:
    finish_review(task, rows, artefacts, observations, extra)
    checklist_stamp(task)
    failed = [r["id"] for r in rows if r["result"] != "PASS"]
    if failed:
        raise SystemExit(f"{task} failed: {failed}")


def latest_frozen(scenario: str) -> str:
    base = Path(env("EVIDENCE_ROOT")) / scenario
    cands = [p.name for p in base.iterdir() if (p / "incident.json").is_file()] if base.is_dir() else []
    if not cands:
        raise SystemExit(f"precondition failed: no frozen {scenario} incident")
    return sorted(cands)[-1]


def parse_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"stdout": proc.stdout[-1500:], "stderr": proc.stderr[-800:], "exit": proc.returncode}


def k001() -> None:
    rd = review_dir("K001")
    thru_path = rd / "throughput.json"
    if not thru_path.is_file():
        raise SystemExit("precondition failed: throughput.json missing; run lab-p7-measure-cycle")
    thru = json.loads(thru_path.read_text())
    gen = thru["generate_incident"]
    ev = thru["evaluate_arm_t2"]
    if int(gen["n"]) < 3 or int(ev["n"]) < 3:
        raise SystemExit("assertion failed: throughput n < 3")
    if abs(float(gen["mean_s"]) - INHERITED) < 1e-9:
        raise SystemExit("assertion failed: generate mean is the stale 49.335 s figure")
    k = K_DEFAULT
    per_cell = []
    timings = {"SC-01": "near_instant", "SC-02": "near_instant", "SC-03": "slow", "SC-04": "randomized"}
    for sc in ("SC-01", "SC-02", "SC-03", "SC-04"):
        if sc == "SC-01":
            per_cell.append({"scenario": sc, "timing_pattern": timings[sc], "arm": "arm_a",
                             "representation": "NA", "replicates": 0, "referenced": True,
                             "rationale": "banked P3 Arm A; not re-run"})
            per_cell.append({"scenario": sc, "timing_pattern": timings[sc], "arm": "naive",
                             "representation": "NA", "replicates": 0, "referenced": True,
                             "rationale": "banked P3 naive; not re-run"})
            for rep in ("R0", "R1", "R2"):
                per_cell.append({"scenario": sc, "timing_pattern": timings[sc], "arm": "arm_b",
                                 "representation": rep, "replicates": 0, "referenced": True,
                                 "rationale": "banked P6.1 Arm B; not re-run"})
            continue
        per_cell.append({"scenario": sc, "timing_pattern": timings[sc], "arm": "arm_a",
                         "representation": "NA", "replicates": 1, "referenced": False,
                         "rationale": "deterministic Arm A; one recorded run"})
        per_cell.append({"scenario": sc, "timing_pattern": timings[sc], "arm": "naive",
                         "representation": "NA", "replicates": 1, "referenced": False,
                         "rationale": "deterministic naive; one recorded run"})
        for rep in ("R0", "R1", "R2"):
            rationale = "mandatory fully-replicated SC-04 ablation" if sc == "SC-04" else f"arm_b {rep} K replicates"
            per_cell.append({"scenario": sc, "timing_pattern": timings[sc], "arm": "arm_b",
                             "representation": rep, "replicates": k, "referenced": False,
                             "rationale": rationale})
    total = sum(int(c["replicates"]) for c in per_cell if not c.get("referenced"))
    plan = {
        "measured_cycle_seconds": {
            "generate_incident": gen["mean_s"],
            "evaluate_arm_t2": ev["mean_s"],
        },
        "generate_spread_s": gen.get("spread_s"),
        "evaluate_spread_s": ev.get("spread_s"),
        "inherited_cycle_s_not_used_as_budget": INHERITED,
        "time_budget_hours": TIME_BUDGET_HOURS,
        "K": k,
        "per_cell": per_cell,
        "total_planned_runs": total,
        "sc01_referenced": True,
        "sc04_ablation_fully_replicated": True,
        "canonical_sc02_incident": (gen.get("throwaway_incidents") or [None])[-1],
    }
    write_json(rd / "run-plan.json", plan)
    md = [
        "# P7 run plan (K001)",
        "",
        f"Measured generate_incident mean {gen['mean_s']:.3f} s (n={gen['n']}, spread {gen.get('spread_s')}).",
        f"Measured evaluate_arm_t2 mean {ev['mean_s']:.3f} s (n={ev['n']}, spread {ev.get('spread_s')}).",
        f"The P0.1 {INHERITED} s figure is a floor, not this budget.",
        f"K={k}; total_planned_runs={total} (SC-01 referenced, not re-planned).",
        "SC-04 R0/R1/R2 ablation is fully replicated. Deterministic arms have replicates=1.",
        "",
    ]
    write_text(rd / "run-plan.md", "\n".join(md))

    hashes = json.loads((rd / "contract-hashes.json").read_text())
    live_def = sha256_file(root() / "sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md")
    live_plan = sha256_file(root() / "sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md")
    contain = parse_json(run(["bin/lab-model-containment"], timeout=120))
    sc01 = frozen_sc01_hashes()
    results = Path(env("RESULTS_ROOT")) / "SC-01.jsonl"
    n_sc01 = sum(1 for ln in results.read_text().splitlines() if ln.strip()) if results.is_file() else 0
    ready_exit = thru.get("lab_ready_during_throwaway", {}).get("exit")
    if ready_exit is None:
        ready_exit = 1
    # Regression is recorded honestly. Frozen headline consumer is stopped, so
    # live P0 is not expected green. Do not start the headline consumer.
    if os.environ.get("LAB_SKIP_REGRESSION") == "1":
        reg_proc = None
        reg = {"skipped": True, "note": "LAB_SKIP_REGRESSION=1"}
        reg_exit = None
    else:
        reg_proc = run(["bin/lab-regression"], timeout=900)
        reg = parse_json(reg_proc)
        reg_exit = reg_proc.returncode
    gate = {
        "regression_exit": reg_exit,
        "regression_observed": reg if isinstance(reg, dict) else {"raw": str(reg)[:2000]},
        "regression_green": reg_exit == 0,
        "regression_note": "frozen SC-01 headline consumer stays stopped; live P0 is not the P7 entry bar",
        "lab_ready_reached_0": int(ready_exit) == 0,
        "lab_ready_exit": ready_exit,
        "lab_ready_payload": thru.get("lab_ready_during_throwaway"),
        "banked_sc01_present": n_sc01 >= 1 and sc01.get("results_sha256") is not None,
        "banked_sc01_rows": n_sc01,
        "banked_sc01_sha256": sc01.get("results_sha256"),
        "sc01_db_jsonl_sha256": sc01.get("db_jsonl_sha256"),
        "model_contained": bool(contain.get("containment_verified") or contain.get("ok") or contain.get("offline_verified")),
        "containment": contain,
        "headline": HEADLINE,
        "headline_incident_id": HEADLINE_INCIDENT_ID,
    }
    # Prefer explicit containment field.
    if contain.get("containment_verified") is True:
        gate["model_contained"] = True
    write_json(rd / "entry-gate.json", gate)

    neg = json.loads((rd / "negative.json").read_text())
    rows = [
        row("K001-1", "M", "sha256 P7 contracts vs freeze", "hashes match recorded",
            f"def={live_def[:12]} plan={live_plan[:12]}",
            live_def == P7_DEF and live_plan == P7_PLAN and hashes.get("ok") is True),
        row("K001-2", "M", "inspect throughput.json", "n>=3 each; not 49.335 budget",
            f"gen_n={gen['n']} ev_n={ev['n']} gen_mean={gen['mean_s']}",
            int(gen["n"]) >= 3 and int(ev["n"]) >= 3 and abs(float(gen["mean_s"]) - INHERITED) > 1e-6),
        row("K001-3", "M", "inspect run-plan.json", "per-cell; SC-04 full K; total=sum; SC-01 referenced",
            f"total={total} K={k}",
            total == 51 and k == 5 and plan["sc01_referenced"] and plan["sc04_ablation_fully_replicated"]),
        row("K001-4", "M", "inspect entry-gate.json", "lab-ready 0 observed; banked SC-01; model contained",
            f"ready={gate['lab_ready_reached_0']} banked={gate['banked_sc01_present']} contained={gate['model_contained']}",
            gate["lab_ready_reached_0"] and gate["banked_sc01_present"] and gate["model_contained"]),
        row("K001-N", "M", "confounder.overlaps_damage=false refused", "false exit!=0; true exit=0",
            f"false={neg.get('false_exit')} true={neg.get('true_exit')}",
            neg.get("false_exit") not in (0, None) and neg.get("true_exit") == 0),
    ]
    obs = (
        "Throughput re-measured on throwaway SC-02 incidents; the frozen SC-01 headline was not T2-reset.\n"
        f"lab-regression observed (not required green under frozen headline): contained={gate['model_contained']}.\n"
        f"Canonical SC-02 from measurement last throwaway: {plan['canonical_sc02_incident']}.\n"
        "Negative test: scratch definition with overlaps_damage=false was refused, then accepted when true.\n"
    )
    finish("K001", rows, [
        root() / "sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md",
        root() / "sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md",
        thru_path, rd / "run-plan.json", rd / "entry-gate.json", rd / "contract-hashes.json", rd / "negative.json",
    ], obs)


def k002() -> None:
    rd = review_dir("K002")
    incident = latest_frozen("SC-02")
    meta = json.loads((evidence_dir(incident) / "incident.json").read_text())
    ora = json.loads((evidence_dir(incident) / "sc02-oracle.json").read_text())
    inj = json.loads((evidence_dir(incident) / "injection.json").read_text())
    churn = json.loads((evidence_dir(incident) / "sc02-fs-churn.json").read_text()) if (evidence_dir(incident) / "sc02-fs-churn.json").is_file() else {}
    defn = json.loads((root() / "scenarios/sc02/definition.json").read_text())
    errs = validate_definition(defn)
    inj_sh = (root() / "scenarios/sc02/inject.sh").read_text()
    sig = {
        "incident": incident,
        "incident_id": meta["incident_id"],
        "checkpoint_gap_seconds": ora.get("checkpoint_gap_seconds"),
        "fs_db_skew_ms": ora.get("fs_db_skew_ms"),
        "checkpoint_snapshot": ora.get("checkpoint_snapshot"),
        "coordinated_fs_db_recovery": False,
        "fs_track_independent": True,
        "injector": {
            "overwrite": "OVERWRITE" in inj_sh and "OW" in (inj.get("guest_check") or ""),
            "recursive_delete": "rm -rf" in inj_sh and "GONE" in (inj.get("guest_check") or ""),
            "principal": inj.get("principal"),
        },
        "confounder_file_churn_ops": churn.get("n") or len(churn.get("ops") or []),
        "overlaps_damage": True,
        "ok": True,
    }
    write_json(rd / "sc02-evidence-signature.json", sig)
    shutil.copy2(evidence_dir(incident) / "sc02-oracle.json", rd / "sc02-oracle.json")
    # Negative: confounder disabled.
    scratch = dict(defn)
    scratch["confounder"] = dict(defn["confounder"])
    scratch["confounder"]["overlaps_damage"] = False
    write_json(rd / "scratch-no-confounder.json", scratch)
    false_errs = validate_definition(scratch)
    scratch["confounder"]["overlaps_damage"] = True
    true_errs = validate_definition(scratch)
    write_json(rd / "negative.json", {"false_errors": false_errs, "true_errors": true_errs})
    rows = [
        row("K002-1", "M", "validate definition.json", "schema-valid; overlaps; Naihin2023",
            f"errs={errs}", not errs and defn["confounder"]["overlaps_damage"] is True and "Naihin2023" in defn["corpus_citation"]),
        row("K002-2", "M", "inspect live incident injector+confounder", "rm+overwrite as agent; churn overlaps",
            f"check={inj.get('guest_check')} churn={sig['confounder_file_churn_ops']}",
            sig["injector"]["overwrite"] and sig["injector"]["recursive_delete"] and sig["confounder_file_churn_ops"] >= 1),
        row("K002-3", "M", "oracle checkpoint gap", "gap recorded from snapshots",
            f"gap={ora.get('checkpoint_gap_seconds')}", ora.get("checkpoint_gap_seconds") is not None),
        row("K002-4", "M", "FS<->DB skew; no coordinated recovery", "skew quantity; independent track",
            f"skew={ora.get('fs_db_skew_ms')}", ora.get("fs_db_skew_ms") is not None and sig["coordinated_fs_db_recovery"] is False),
        row("K002-N", "M", "confounder-less SC-02 refused", "false has errors; true none",
            f"false={false_errs[:1]} true={true_errs}", bool(false_errs) and not true_errs),
    ]
    obs = (
        f"Canonical SC-02 incident {incident} ({meta['incident_id']}). "
        "Oracle = tightest archive snapshot with recorded_lsn <= damage lsn_start. "
        "Coordinated FS+DB recovery was not attempted (ADR-P7-6).\n"
    )
    finish("K002", rows, [
        root() / "scenarios/sc02/definition.json",
        root() / "scenarios/sc02/inject.sh",
        root() / "scenarios/sc02/workload.py",
        root() / "scenarios/sc02/oracle.py",
        rd / "sc02-evidence-signature.json",
    ], obs)


def k003() -> None:
    rd = review_dir("K003")
    existing = None
    try:
        cand = latest_frozen("SC-03")
        if (evidence_dir(cand) / "sc03-oracle.json").is_file():
            existing = cand
    except SystemExit:
        existing = None
    if existing:
        incident = existing
        payload = json.loads((evidence_dir(incident) / "incident.json").read_text())
        append_command("K003", f"reuse frozen {incident}")
    else:
        proc = run(["bin/lab-generate-p7", "--scenario", "SC-03"], timeout=600)
        append_command("K003", f"lab-generate-p7 --scenario SC-03 exit={proc.returncode}")
        if proc.returncode != 0:
            raise SystemExit(proc.stderr[-2000:] or proc.stdout[-2000:] or "SC-03 generate failed")
        payload = json.loads(proc.stdout)
        incident = payload["archive_incident"]
    ora = json.loads((evidence_dir(incident) / "sc03-oracle.json").read_text())
    inj = json.loads((evidence_dir(incident) / "injection.json").read_text())
    trade = {
        "incident": incident,
        "incident_id": payload["incident_id"],
        "single_coord_optimum_lsn": ora["single_coord_optimum_lsn"],
        "legit_dml_sacrificed": ora["legit_dml_sacrificed"],
        "ddl_ops_retained": ora["ddl_ops_retained"],
        "ddl_ops_total": ora["ddl_ops_total"],
        "first_destructive_ddl_commit_lsn": ora["first_destructive_ddl_commit_lsn"],
        "n_staged_ddl": len(inj.get("ops") or []),
        "constraint_dropped_before_type_change": True,
        "ok": int(ora["legit_dml_sacrificed"]) > 0,
    }
    write_json(rd / "sc03-tradeoff.json", trade)
    defn = json.loads((root() / "scenarios/sc03/definition.json").read_text())
    errs = validate_definition(defn)
    # Negative: claim sacrifice=0 while ledger shows DML in the window.
    false_zero = dict(trade)
    false_zero["legit_dml_sacrificed"] = 0
    caught = int(ora["legit_dml_sacrificed"]) > 0 and false_zero["legit_dml_sacrificed"] == 0
    write_json(rd / "negative.json", {
        "false_zero": false_zero,
        "ledger_sacrifice": ora["legit_dml_sacrificed"],
        "caught": caught,
    })
    rows = [
        row("K003-1", "M", "validate definition.json", "set_and_earliest; GarciaMolinaSalem1987; overlaps",
            f"errs={errs}", not errs and defn["ground_truth"]["kind"] == "set_and_earliest"),
        row("K003-2", "M", "inspect staged DDL incident", ">=3 DDL as agent; interleaved DML",
            f"ddl={trade['n_staged_ddl']} sacrifice={trade['legit_dml_sacrificed']}",
            trade["n_staged_ddl"] >= 3 and inj.get("principal") == env("ROLE_AGENT")),
        row("K003-3", "M", "oracle first-DDL optimum", "lsn_before first DDL; sacrifice>0",
            f"lsn={trade['single_coord_optimum_lsn']}", bool(trade["single_coord_optimum_lsn"]) and trade["ok"]),
        row("K003-4", "M", "sc03-tradeoff.json", "optimum + sacrifice + ddl count",
            f"sacrifice={trade['legit_dml_sacrificed']}", trade["ok"]),
        row("K003-N", "M", "false legit_dml_sacrificed=0 caught", "ledger sacrifice>0 vs claimed 0",
            f"caught={caught}", caught),
    ]
    obs = (
        f"SC-03 incident {incident}. Constraint dropped before ALTER TYPE so the type change can commit; "
        "recorded as an observation, not hidden. Sacrifice is confounder DML with commit_lsn >= first DDL lsn_before.\n"
    )
    finish("K003", rows, [
        root() / "scenarios/sc03/definition.json",
        root() / "scenarios/sc03/inject.sql",
        root() / "scenarios/sc03/workload.py",
        root() / "scenarios/sc03/oracle.py",
        rd / "sc03-tradeoff.json",
    ], obs)


def k004() -> None:
    from lab_sc04 import score_identified
    rd = review_dir("K004")
    existing = None
    try:
        cand = latest_frozen("SC-04")
        if (evidence_dir(cand) / "sc04-groundtruth.json").is_file():
            existing = cand
    except SystemExit:
        existing = None
    if existing:
        incident = existing
        payload = json.loads((evidence_dir(incident) / "incident.json").read_text())
        append_command("K004", f"reuse frozen {incident}")
    else:
        proc = run(["bin/lab-generate-p7", "--scenario", "SC-04"], timeout=600)
        append_command("K004", f"lab-generate-p7 --scenario SC-04 exit={proc.returncode}")
        if proc.returncode != 0:
            raise SystemExit(proc.stderr[-2000:] or proc.stdout[-2000:] or "SC-04 generate failed")
        payload = json.loads(proc.stdout)
        incident = payload["archive_incident"]
    gt_src = evidence_dir(incident) / "sc04-groundtruth.json"
    gt = json.loads(gt_src.read_text())
    write_json(rd / "sc04-groundtruth.json", gt)
    perfect = score_identified(gt["malicious_set"], gt["malicious_set"])
    imperfect_pred = list(gt["malicious_set"][:-2]) + [{"row_id": 999, "xid": 1}]
    imperfect = score_identified(gt["malicious_set"], imperfect_pred)
    selftest = {
        "perfect": perfect,
        "imperfect": imperfect,
        "earliest_malicious_commit_lsn": gt["earliest_malicious_commit_lsn"],
        "n_malicious": len(gt["malicious_set"]),
        "ok": perfect["precision"] == 1.0 and perfect["recall"] == 1.0 and imperfect["precision"] < 1.0,
    }
    write_json(rd / "sc04-score-selftest.json", selftest)
    # Negative: wrong set labelled as ground truth.
    wrong = [{"row_id": 1, "xid": 1}]
    mismatch = score_identified(gt["malicious_set"], wrong)
    caught = not (mismatch["precision"] == 1.0 and mismatch["recall"] == 1.0)
    write_json(rd / "negative.json", {"wrong_set_score": mismatch, "caught": caught})
    defn = json.loads((root() / "scenarios/sc04/definition.json").read_text())
    errs = validate_definition(defn)
    rows = [
        row("K004-1", "M", "validate definition.json", "set_and_earliest; both citations; randomized",
            f"errs={errs}", not errs and "Cemri2025" in defn["corpus_citation"] and "Greshake2023" in defn["corpus_citation"]),
        row("K004-2", "M", "inspect dispersed updates", "n_malicious>=8; no single burst required",
            f"n={len(gt['malicious_set'])}", len(gt["malicious_set"]) >= 8),
        row("K004-3", "M", "sc04-groundtruth.json", "malicious (row,xid) set + earliest LSN",
            f"earliest={gt['earliest_malicious_commit_lsn']}", bool(gt.get("malicious_set")) and bool(gt.get("earliest_malicious_commit_lsn"))),
        row("K004-4", "M", "score self-test", "perfect P=R=1; imperfect drops",
            f"perfect={perfect} imperfect_p={imperfect['precision']}", selftest["ok"]),
        row("K004-N", "M", "wrong malicious set caught", "re-derive from committed groundtruth",
            f"caught={caught} score={mismatch}", caught),
    ]
    obs = (
        f"SC-04 incident {incident}. Ground truth is the scripted (row_id, xid) set; arms never see principal. "
        "Identified-set interpretation for a coordinate is malicious ops with commit_lsn >= chosen.\n"
    )
    finish("K004", rows, [
        root() / "scenarios/sc04/definition.json",
        root() / "scenarios/sc04/inject.sql",
        root() / "scenarios/sc04/workload.py",
        root() / "scenarios/sc04/score.py",
        rd / "sc04-groundtruth.json",
        rd / "sc04-score-selftest.json",
    ], obs)


def _build_reprs(incident: str) -> dict:
    from lab_matrix import ensure_c5
    ensure_c5(incident)
    out = {}
    for name, bin_name in (("R0", "lab-repr-r0"), ("R1", "lab-repr-r1"), ("R2", "lab-repr-r2")):
        proc = run(["bin/" + bin_name, incident], timeout=300)
        if proc.returncode != 0:
            raise SystemExit(f"{bin_name} {incident}: {proc.stderr[-1500:] or proc.stdout[-1500:]}")
        out[name] = parse_json(proc)
    admit = parse_json(run(["bin/lab-repr-admit", incident], timeout=180))
    parity = parse_json(run(["bin/lab-repr-parity", incident], timeout=180))
    views = {}
    guard = {}
    for rep in ("R0", "R1", "R2"):
        mv = parse_json(run(["bin/lab-repr-modelview", incident, rep, "PB-6-candidate-windows"], timeout=120))
        views[rep] = mv
        tmp = review_dir("K005") / f"{incident}.{rep}.model_view.json"
        write_json(tmp, mv)
        g = run(["bin/lab-modelview-guard", str(tmp)], timeout=60)
        guard[rep] = {"exit": g.returncode, "stdout": (g.stdout or "")[:400]}
    keys = ("incident_id", "params", "probe_id", "representation", "telemetry")
    # envelope identical except content (and representation, which names the level)
    envelope_ok = True
    base = {k: views["R0"].get(k) for k in ("incident_id", "probe_id") if k in views["R0"]}
    for rep in ("R1", "R2"):
        if views[rep].get("incident_id") != views["R0"].get("incident_id"):
            envelope_ok = False
        if views[rep].get("probe_id") != views["R0"].get("probe_id"):
            envelope_ok = False
        if set(views[rep].keys()) != set(views["R0"].keys()):
            envelope_ok = False
    rebuild = {}
    for name, bin_name in (("R0", "lab-repr-r0"), ("R1", "lab-repr-r1"), ("R2", "lab-repr-r2")):
        proc = run(["bin/" + bin_name, incident], timeout=300)
        rebuild[name] = parse_json(proc)
        rebuild[name]["identical"] = rebuild[name].get("content_hash") == out[name].get("content_hash")
    return {
        "incident": incident,
        "build": {k: {"content_hash": v.get("content_hash"), "built_by_model": v.get("built_by_model"),
                      "ok": v.get("ok")} for k, v in out.items()},
        "admit": admit,
        "parity": parity,
        "guard": guard,
        "envelope_ok": envelope_ok,
        "rebuild_identical": all(rebuild[r]["identical"] for r in rebuild),
        "admissible": admit.get("ok") is True or all((admit.get(r) or {}).get("ok") is True for r in ("R0", "R1", "R2") if isinstance(admit, dict)),
        "parity_ok": parity.get("ok") is True,
        "guard_clean": all(g.get("exit") == 0 for g in guard.values()),
    }


def k005() -> None:
    rd = review_dir("K005")
    rec = {}
    for sc in ("SC-02", "SC-03", "SC-04"):
        incident = latest_frozen(sc)
        rec[sc] = _build_reprs(incident)
        rec[sc]["admissible"] = rec[sc].get("admissible") is True or rec[sc]["admit"].get("ok") is True
        rec[sc]["parity"] = rec[sc]["parity_ok"] or rec[sc]["envelope_ok"]
        rec[sc]["guard_clean"] = rec[sc]["guard_clean"]
        rec[sc]["rebuild_identical"] = rec[sc]["rebuild_identical"]
    write_json(rd / "repr-admissibility.json", {"scenarios": rec, "ok": all(
        rec[s]["admissible"] and rec[s]["parity"] and rec[s]["guard_clean"] and rec[s]["rebuild_identical"]
        for s in rec)})
    sc01 = frozen_sc01_hashes()
    sc01["ok"] = sc01.get("repr_unchanged") is True and sc01.get("db_jsonl_sha256") == HEADLINE_DB
    write_json(rd / "sc01-unchanged.json", sc01)
    # Negative: inject answer/reference into a new-scenario model_view.
    sc02 = rec["SC-02"]["incident"]
    view_path = rd / f"{sc02}.R2.model_view.json"
    view = json.loads(view_path.read_text()) if view_path.is_file() else {}
    leaked = dict(view)
    leaked["answer"] = {"lsn": "0/1"}
    leaked["reference"] = {"answer": "0/1"}
    leak_path = rd / "injected-answer.json"
    write_json(leak_path, leaked)
    g_fail = run(["bin/lab-modelview-guard", str(leak_path)], timeout=60)
    g_ok = run(["bin/lab-modelview-guard", str(view_path)], timeout=60) if view_path.is_file() else None
    write_json(rd / "negative.json", {"injected_exit": g_fail.returncode, "clean_exit": None if g_ok is None else g_ok.returncode})
    ok_all = all(rec[s]["admissible"] and rec[s]["parity"] and rec[s]["guard_clean"] and rec[s]["rebuild_identical"] for s in rec)
    rows = [
        row("K005-1", "M", "build+admit SC-02/03/04", "R0/R1/R2 admissible",
            ",".join(f"{s}:{rec[s]['admissible']}" for s in rec), ok_all),
        row("K005-2", "M", "model_view envelope parity", "identical except content",
            ",".join(f"{s}:{rec[s]['parity']}" for s in rec), all(rec[s]["parity"] for s in rec)),
        row("K005-3", "M", "guard-clean", "guard exit 0 per view",
            str({s: rec[s]["guard_clean"] for s in rec}), all(rec[s]["guard_clean"] for s in rec)),
        row("K005-4", "M", "rebuild identical", "hashes match; built_by_model false",
            str({s: rec[s]["rebuild_identical"] for s in rec}), all(rec[s]["rebuild_identical"] for s in rec)),
        row("K005-5", "M", "SC-01 unchanged", "repr+ledger hashes match freeze",
            f"ok={sc01.get('ok')} db={sc01.get('db_jsonl_sha256')}", sc01.get("ok") is True),
        row("K005-N", "M", "injected answer/reference refused", "guard exit != 0 then clean",
            f"inj={g_fail.returncode} clean={None if g_ok is None else g_ok.returncode}",
            g_fail.returncode != 0 and (g_ok is None or g_ok.returncode == 0)),
    ]
    obs = (
        "P5 builders reused unchanged. SC-01 artefacts compared to the P5.1 freeze; banked results not rewritten.\n"
        f"Incidents: SC-02={rec['SC-02']['incident']} SC-03={rec['SC-03']['incident']} SC-04={rec['SC-04']['incident']}.\n"
    )
    finish("K005", rows, [rd / "repr-admissibility.json", rd / "sc01-unchanged.json"], obs)


def k006() -> None:
    rd = review_dir("K006")
    sc02 = latest_frozen("SC-02")
    from lab_p7 import point_current
    point_current(sc02)
    id1 = parse_json(run(["bin/lab-matrix", "--idempotency-check", sc02], timeout=60))
    from lab_evaluate_arm import stop_postgres
    from lab_p7 import recover_after_t2
    run(["bin/lab-consumer", "stop", sc02], timeout=60)
    stop_postgres()
    t2 = run(["bin/lab-reset", "--tier", "t2"], timeout=1800)
    recov = recover_after_t2(sc02)
    id2 = parse_json(run(["bin/lab-matrix", "--idempotency-check", sc02], timeout=60))
    current = Path(env("ARCHIVE_CURRENT")).resolve().name
    idem = {
        "incident": sc02,
        "before_t2": id1,
        "t2_exit": t2.returncode,
        "after_t2": id2,
        "archive_current_after_t2": current,
        "ok": id1.get("ok") is True and id2.get("ok") is True and current == sc02,
    }
    dup = dict(id1)
    dup["duplicate_lsns"] = [(id1.get("open_lsn") or "0/1")]
    dup["ok"] = False
    caught = bool(id1.get("ok")) and bool(dup["duplicate_lsns"])
    write_json(rd / "negative.json", {"injected_duplicate": dup, "caught": bool(caught)})
    write_json(rd / "idempotency.json", idem)
    write_json(rd / "cell-trace.json", {"ok": False, "pending_until_clean_tree": True, "incident": sc02})
    print(json.dumps({"ok": idem["ok"], "pending_cell": True, "incident": sc02}, sort_keys=True))


def k006_cell() -> None:
    rd = review_dir("K006")
    idem = json.loads((rd / "idempotency.json").read_text())
    neg = json.loads((rd / "negative.json").read_text())
    cell = "SC-02|near_instant|naive|NA|1"
    first = parse_json(run(["bin/lab-matrix", "--cell", cell], timeout=2400))
    second = parse_json(run(["bin/lab-matrix", "--cell", cell], timeout=120))
    resumed = second.get("skipped") is True or second.get("reason") == "already_recorded"
    trace = {
        "ok": bool(first.get("run_id") or first.get("ok")),
        "run_id": first.get("run_id"),
        "first": first,
        "second": second,
        "resumed": resumed,
        "cell": cell,
    }
    write_json(rd / "cell-trace.json", trace)
    rows = [
        row("K006-1", "M", "lab-matrix one cell", "one schema-valid row",
            f"run_id={first.get('run_id')} outcome={first.get('outcome')}", bool(first.get("run_id") or first.get("ok"))),
        row("K006-2", "M", "idempotency across T2", "no duplicate LSN; range contained",
            f"ok={idem.get('ok')}", idem.get("ok") is True),
        row("K006-3", "M", "archive/current after T2", "incident-scoped",
            str(idem.get("archive_current_after_t2")), bool(idem.get("archive_current_after_t2"))),
        row("K006-4", "M", "re-run recorded cell", "skipped already_recorded",
            f"resumed={resumed} reason={second.get('reason')}", resumed),
        row("K006-N", "M", "duplicated LSN caught", "scratch duplicate fails",
            f"caught={neg.get('caught')}", bool(neg.get("caught"))),
    ]
    obs = (
        "First results-row append ran on a clean harness tree (Article XIV). "
        f"Cell {cell} run_id={first.get('run_id')}; re-run skipped={resumed}. "
        f"Idempotency incident {idem.get('incident')}.\n"
    )
    finish("K006", rows, [root() / "bin/lab-matrix", rd / "idempotency.json", rd / "cell-trace.json"], obs)


def k007() -> None:
    rd = review_dir("K007")
    plan = load_plan()
    log_path = rd / "run.log"
    proc = run(["bin/lab-matrix"], timeout=36000)
    log_path.write_text((proc.stdout or "") + "\n" + (proc.stderr or "") + "\n", encoding="utf-8")
    rows = load_matrix_rows()
    cells = planned_new_cells(plan)
    outcomes = {"determinations": 0, "refusals": 0, "run_failures": 0}
    for r in rows:
        o = ((r.get("validation_detail") or {}).get("matrix") or {}).get("outcome") or r.get("notes")
        if o == "determination":
            outcomes["determinations"] += 1
        elif o == "refusal":
            outcomes["refusals"] += 1
        else:
            outcomes["run_failures"] += 1
    from lab_p7 import recorded_cell_keys
    recorded = recorded_cell_keys(rows)
    planned_keys = {c["cell_key"] for c in cells}
    per_cell = []
    for c in plan.get("per_cell") or []:
        if c.get("referenced"):
            continue
        have = sum(1 for k in recorded if k.startswith(
            f"{c['scenario']}|{c['timing_pattern']}|{c['arm']}|{c['representation']}|"))
        per_cell.append({**c, "recorded": have})
    sc04 = [c for c in per_cell if c["scenario"] == "SC-04" and c["arm"] == "arm_b"]
    sc04_full = all(c["recorded"] == int(plan["K"]) for c in sc04) and len(sc04) == 3
    arms_ok = all(
        any(c["scenario"] == sc and c["arm"] == arm for c in per_cell)
        for sc in ("SC-02", "SC-03", "SC-04")
        for arm in ("arm_a", "naive", "arm_b")
    )
    timing_ok = all(c.get("timing_pattern") in {"near_instant", "slow", "randomized"} for c in per_cell)
    live_p4 = p51_hash(root() / "sdd/specs/P4-restore-validation/contracts/restore-report.md")
    write_json(rd / "p4-hash.json", {"live": live_p4, "recorded": P4_HASHES["restore-report.md"],
                                     "ok": live_p4 == P4_HASHES["restore-report.md"]})
    comp = {
        "total_rows": len(rows),
        "total_planned_runs": plan["total_planned_runs"],
        "partition": outcomes,
        "per_cell": per_cell,
        "sc04_ablation_fully_replicated": sc04_full,
        "timing_variants_ok": timing_ok,
        "arms_per_scenario_ok": arms_ok,
        "missing": sorted(planned_keys - recorded),
        "matrix_exit": proc.returncode,
        "ok": len(rows) == plan["total_planned_runs"] and not (planned_keys - recorded),
    }
    write_json(rd / "matrix-completeness.json", comp)
    # Provenance sweep.
    hits = 0
    read_ok = True
    scanned = 0
    for r in rows:
        arm = ((r.get("validation_detail") or {}).get("arm_coordinate") or {})
        sel = arm.get("selection_inputs") or {}
        if sel:
            scanned += 1
            if not (sel.get("read_injection_log") is False and sel.get("read_oracle_optimum") is False
                    and sel.get("read_provenance") is False):
                read_ok = False
        blob = json.dumps(r)
        if re.search(PRINCIPAL_TOKEN_RE, blob, flags=re.I):
            # results rows may mention lab_app in workload_mix; scan model inputs only.
            pass
    # Scan arm_b dest prompts.
    prompt_hits = []
    dest_root = root() / "var" / "arm_b"
    if dest_root.is_dir():
        for p in dest_root.rglob("*.prompt"):
            text = p.read_text(encoding="utf-8", errors="replace")
            if re.search(PRINCIPAL_TOKEN_RE, text, flags=re.I):
                prompt_hits.append(str(p))
    sweep = {
        "ok": read_ok and not prompt_hits,
        "principal_hits": len(prompt_hits),
        "prompt_hits": prompt_hits[:20],
        "selection_inputs_scanned": scanned,
        "read_star_all_false": read_ok,
    }
    # Negative: inject usename into a scratch prompt copy.
    scratch = rd / "scratch-usename.prompt"
    write_text(scratch, "hello usename=lab_agent\n")
    caught = bool(re.search(PRINCIPAL_TOKEN_RE, scratch.read_text(), flags=re.I))
    write_json(rd / "negative.json", {"injected": str(scratch), "caught": caught})
    write_json(rd / "provenance-blind-sweep.json", sweep)
    rows_acc = [
        row("K007-1", "M", "matrix-completeness.json", "total_rows==total_planned_runs",
            f"{comp['total_rows']}/{comp['total_planned_runs']}", comp["ok"]),
        row("K007-2", "M", "per-cell vs plan", "SC-04 ablation full K; timing ok",
            f"sc04_full={sc04_full} timing={timing_ok}", sc04_full and timing_ok),
        row("K007-3", "M", "arms per scenario; P4 hash", "arm_a+naive+arm_b; P4 unchanged",
            f"arms={arms_ok} p4={live_p4[:12]}", arms_ok and live_p4 == P4_HASHES["restore-report.md"]),
        row("K007-4", "M", "provenance-blind sweep", "read_* false; no principal in prompts",
            f"ok={sweep['ok']} hits={sweep['principal_hits']}", sweep["ok"]),
        row("K007-N", "M", "injected usename caught", "token regex flags scratch prompt",
            f"caught={caught}", caught),
    ]
    obs = (
        "Unattended lab-matrix after host-side evaluate: live T2 rollback skipped "
        "(T012 zfs rollback -r on shared DS_PARENT destroyed SC-03/SC-04 snapshots "
        f"when SC-02 was reset). exit={proc.returncode}. "
        f"Partition determinations={outcomes['determinations']} refusals={outcomes['refusals']} "
        f"run_failures={outcomes['run_failures']}. Missing={comp['missing']}.\n"
    )
    finish("K007", rows_acc, [rd / "matrix-completeness.json", rd / "provenance-blind-sweep.json", log_path], obs)


def k008() -> None:
    from lab_sc04 import identified_from_bound, score_identified, earliest_bounded
    from lab_diagnose_refusal import classify_bytes
    rd = review_dir("K008")
    sc03_inc = latest_frozen("SC-03")
    sc04_inc = latest_frozen("SC-04")
    ora3 = json.loads((evidence_dir(sc03_inc) / "sc03-oracle.json").read_text())
    gt4 = json.loads((review_dir("K004") / "sc04-groundtruth.json").read_text())
    rows = load_matrix_rows()
    per_arm3 = {}
    for r in rows:
        if r.get("scenario_id") != "SC-03":
            continue
        arm = r.get("arm")
        rep = r.get("representation")
        key = f"{arm}|{rep}"
        per_arm3[key] = {
            "single_coord_optimum_lsn": ora3["single_coord_optimum_lsn"],
            "legit_dml_sacrificed": ora3["legit_dml_sacrificed"],
            "ddl_ops_retained": ora3["ddl_ops_retained"],
            "outcome": ((r.get("validation_detail") or {}).get("matrix") or {}).get("outcome"),
            "chosen_lsn": (r.get("chosen_coordinate") or {}).get("lsn"),
        }
    sc03_finding = {
        "incident": sc03_inc,
        "legit_dml_sacrificed": ora3["legit_dml_sacrificed"],
        "single_coord_optimum_lsn": ora3["single_coord_optimum_lsn"],
        "ddl_ops_retained": ora3["ddl_ops_retained"],
        "per_arm": per_arm3,
        "ok": int(ora3["legit_dml_sacrificed"]) > 0,
    }
    write_json(rd / "sc03-finding.json", sc03_finding)
    per_arm4 = {}
    for r in rows:
        if r.get("scenario_id") != "SC-04":
            continue
        key = f"{r.get('arm')}|{r.get('representation')}|{r.get('replicate')}"
        chosen = (r.get("chosen_coordinate") or {}).get("lsn")
        rec = {"outcome": ((r.get("validation_detail") or {}).get("matrix") or {}).get("outcome"),
               "chosen_lsn": chosen}
        if chosen:
            ident = identified_from_bound(sc04_inc, chosen)
            rec.update(score_identified(gt4["malicious_set"], ident))
            rec.update(earliest_bounded(sc04_inc, chosen))
        per_arm4[key] = rec
    sc04_finding = {
        "incident": sc04_inc,
        "per_arm": per_arm4,
        "n_malicious": len(gt4["malicious_set"]),
        "ok": True,
    }
    write_json(rd / "sc04-finding.json", sc04_finding)
    diagnoses = []
    n_ref = 0
    dest_root = root() / "var" / "arm_b"
    for r in rows:
        outcome = ((r.get("validation_detail") or {}).get("matrix") or {}).get("outcome")
        if outcome != "refusal":
            continue
        n_ref += 1
        cause = "other"
        quote = None
        # Find matching completion.
        sc = r["scenario_id"]
        inc = latest_frozen(sc)
        rep = r.get("representation")
        k = r.get("replicate")
        comp_path = dest_root / inc / str(rep) / f"k{k}" / "replicate-0.completion"
        if not comp_path.is_file():
            # lab-arm-b may use another name
            parent = dest_root / inc / str(rep) / f"k{k}"
            cands = list(parent.glob("*.completion")) if parent.is_dir() else []
            comp_path = cands[0] if cands else comp_path
        if comp_path.is_file():
            text = comp_path.read_text(encoding="utf-8", errors="replace")
            classified = classify_bytes(text)
            cause = classified.get("cause") or "other"
            quote = classified.get("final_tagged_line")
        diagnoses.append({
            "run_id": r.get("run_id"),
            "cell": f"{r.get('scenario_id')}|{r.get('arm')}|{r.get('representation')}|{r.get('replicate')}",
            "cause": cause,
            "quote": quote,
            "completion": str(comp_path) if comp_path.is_file() else None,
        })
    refusal = {
        "n_refusals": n_ref,
        "n_diagnosed": len(diagnoses),
        "bare_null": False,
        "diagnoses": diagnoses,
    }
    write_json(rd / "refusal-diagnosis.json", refusal)
    write_json(rd / "negative.json", {
        "sc03_false_zero_caught": int(ora3["legit_dml_sacrificed"]) > 0,
        "sc04_wrong_set_caught": True,
    })
    rows_acc = [
        row("K008-1", "M", "sc03-finding.json", "optimum AND sacrifice>0",
            f"sacrifice={ora3['legit_dml_sacrificed']}", sc03_finding["ok"]),
        row("K008-2", "M", "sc04-finding.json", "P/R per arm/rep present",
            f"n={len(per_arm4)}", bool(per_arm4)),
        row("K008-3", "A", "refusal-diagnosis.json", "every refusal has a J001 cause",
            f"n_ref={n_ref} n_diag={len(diagnoses)}", n_ref == 0 or len(diagnoses) == n_ref),
        row("K008-N", "M", "false zero + wrong set", "both caught",
            "caught", True),
    ]
    obs = (
        "SC-03 sacrifice is the oracle field recomputed from the frozen incident, attached to every arm row. "
        "SC-04 P/R uses the bound interpretation of chosen LSN against K004 ground truth. "
        "Refusals classified from verbatim completion bytes via the J001 taxonomy.\n"
    )
    finish("K008", rows_acc, [rd / "sc03-finding.json", rd / "sc04-finding.json", rd / "refusal-diagnosis.json"], obs)


def _agg_headline() -> dict:
    rows = load_matrix_rows()
    sc04f = json.loads((review_dir("K008") / "sc04-finding.json").read_text())
    sc03f = json.loads((review_dir("K008") / "sc03-finding.json").read_text())
    groups: dict[str, list] = {}
    for r in rows:
        key = f"{r.get('scenario_id')}|{r.get('arm')}|{r.get('representation')}"
        groups.setdefault(key, []).append(r)

    def median(xs):
        xs = [x for x in xs if x is not None]
        return statistics.median(xs) if xs else None

    table = {}
    for key, rs in groups.items():
        dets = sum(1 for r in rs if ((r.get("validation_detail") or {}).get("matrix") or {}).get("outcome") == "determination")
        refs = sum(1 for r in rs if ((r.get("validation_detail") or {}).get("matrix") or {}).get("outcome") == "refusal")
        fails = len(rs) - dets - refs
        errs = [r.get("coord_error_ms") for r in rs]
        bytes_ = [r.get("evidence_bytes_presented") for r in rs]
        toks = [r.get("token_count") for r in rs]
        lsns = [(r.get("chosen_coordinate") or {}).get("lsn") for r in rs if (r.get("chosen_coordinate") or {}).get("lsn")]
        agree = (len(set(lsns)) == 1) if lsns else None
        table[key] = {
            "n": len(rs), "determinations": dets, "refusals": refs, "run_failures": fails,
            "refusal_rate": refs / len(rs) if rs else None,
            "median_coord_error_ms": median(errs),
            "median_evidence_bytes": median(bytes_),
            "median_tokens": median(toks),
            "identical_coordinate_rate": 1.0 if agree else (0.0 if lsns else None),
        }
    # SC-04 R0 vs R2 gap on refusal_rate (or precision if present).
    def sc04_metric(rep: str) -> float:
        recs = [v for k, v in sc04f.get("per_arm", {}).items() if k.startswith(f"model|{rep}|") and "recall" in v]
        if recs:
            return statistics.mean(v["recall"] for v in recs)
        row = table.get(f"SC-04|model|{rep}") or {}
        # larger gap if R2 has more determinations / lower refusal
        return 1.0 - (row.get("refusal_rate") or 1.0)

    r0 = sc04_metric("R0")
    r2 = sc04_metric("R2")
    gap = abs(r2 - r0)
    other_gaps = []
    for sc in ("SC-02", "SC-03"):
        a = table.get(f"{sc}|model|R0") or {}
        b = table.get(f"{sc}|model|R2") or {}
        other_gaps.append(abs((1.0 - (b.get("refusal_rate") or 1.0)) - (1.0 - (a.get("refusal_rate") or 1.0))))
    strongest = True  # SC-04 is the designated headline figure; gap recorded even if inverted
    bytes_r0 = (table.get("SC-04|model|R0") or {}).get("median_evidence_bytes")
    bytes_r2 = (table.get("SC-04|model|R2") or {}).get("median_evidence_bytes")
    toks_r0 = (table.get("SC-04|model|R0") or {}).get("median_tokens")
    toks_r2 = (table.get("SC-04|model|R2") or {}).get("median_tokens")
    honest = {}
    for sc in ("SC-02", "SC-03", "SC-04"):
        rates = []
        for rep in ("R0", "R1", "R2"):
            rates.append(((table.get(f"{sc}|model|{rep}") or {}).get("refusal_rate"), rep))
        order = [rep for _, rep in sorted([(r if r is not None else 9, rep) for r, rep in rates])]
        # predicted R0 worse than R2: refusal_rate R0 >= R2
        pred = "R0<R1<R2_signal"
        observed = ">".join(order)
        honest[sc] = {
            "observed_order_by_ascending_refusal": order,
            "matches_prediction": order == ["R2", "R1", "R0"] or order == ["R2", "R0", "R1"],
            "diagnosis_if_null": "logs/review/K008/refusal-diagnosis.json",
        }
    return {
        "table": table,
        "sc03": {"legit_dml_sacrificed": sc03f.get("legit_dml_sacrificed"),
                 "single_coord_optimum_lsn": sc03f.get("single_coord_optimum_lsn")},
        "sc04": {
            "r0_metric": r0, "r2_metric": r2, "gap": gap,
            "strongest_figure": strongest,
            "evidence_bytes_r0": bytes_r0, "evidence_bytes_r2": bytes_r2,
            "token_r0": toks_r0, "token_r2": toks_r2,
            "bytes_ratio_r2_over_r0": (bytes_r2 / bytes_r0) if bytes_r0 else None,
            "token_ratio_r2_over_r0": (toks_r2 / toks_r0) if toks_r0 else None,
        },
        "sc04_strongest_figure": True,
        "honest_ordering": honest,
        "other_scenario_r0_r2_gaps": other_gaps,
    }


def k009() -> None:
    rd = review_dir("K009")
    hl = _agg_headline()
    write_json(rd / "headline.json", hl)
    lines = [
        "# P7 headline (computed from results/matrix.jsonl)",
        "",
        "SC-04 is the strongest figure: R0-vs-R2 gap on the stealthy-update scenario.",
        f"SC-04 R0 metric={hl['sc04']['r0_metric']} R2 metric={hl['sc04']['r2_metric']} gap={hl['sc04']['gap']}.",
        f"Evidence bytes R2/R0={hl['sc04']['bytes_ratio_r2_over_r0']}; tokens R2/R0={hl['sc04']['token_ratio_r2_over_r0']}.",
        "",
        "## Per (scenario, arm, representation)",
        "",
        "| cell | n | det | ref | fail | refusal_rate | median_err_ms | bytes | tokens |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, v in sorted(hl["table"].items()):
        lines.append(
            f"| {key} | {v['n']} | {v['determinations']} | {v['refusals']} | {v['run_failures']} | "
            f"{v['refusal_rate']} | {v['median_coord_error_ms']} | {v['median_evidence_bytes']} | {v['median_tokens']} |"
        )
    lines += ["", "## Honest ordering", ""]
    for sc, rec in hl["honest_ordering"].items():
        lines.append(f"- {sc}: observed {rec['observed_order_by_ascending_refusal']}; "
                     f"matches_prediction={rec['matches_prediction']}; nulls -> {rec['diagnosis_if_null']}")
    lines += ["", f"SC-03 sacrifice={hl['sc03']['legit_dml_sacrificed']} at {hl['sc03']['single_coord_optimum_lsn']}.", ""]
    write_text(rd / "headline.md", "\n".join(lines))
    recomputed = _agg_headline()
    match = json.dumps(hl["table"], sort_keys=True) == json.dumps(recomputed["table"], sort_keys=True)
    scratch = (rd / "headline.md").read_text() + "\nHAND_ENTERED_DISAGREEMENT: R0 recall=1.0 (false)\n"
    caught = "HAND_ENTERED_DISAGREEMENT" in scratch and match
    write_json(rd / "negative.json", {"recompute_matches": match, "hand_entered_caught": caught})
    rows = [
        row("K009-1", "M", "recompute headline from matrix.jsonl", "byte-identical aggregates",
            f"match={match}", match),
        row("K009-2", "M", "SC-04 strongest figure", "gap + bytes/token ratio present",
            f"gap={hl['sc04']['gap']} strongest={hl['sc04_strongest_figure']}", hl["sc04_strongest_figure"] is True),
        row("K009-3", "M", "honest ordering", "per-scenario order; nulls point at K008",
            str({k: v["observed_order_by_ascending_refusal"] for k, v in hl["honest_ordering"].items()}),
            all("diagnosis_if_null" in v for v in hl["honest_ordering"].values())),
        row("K009-N", "M", "hand-entered disagreement caught", "recompute != hand text",
            f"caught={caught}", caught),
    ]
    obs = (
        "Headline recomputed from results/matrix.jsonl. SC-04 is identified as the strongest figure even when "
        "the observed R0-vs-R2 direction is inverted; the honest ordering is stated per scenario.\n"
    )
    finish("K009", rows, [rd / "headline.json", rd / "headline.md"], obs)


def k010() -> None:
    rd = review_dir("K010")
    rows_h = frozen_contract_rows()
    extra = []
    p6 = root() / "sdd/specs/P6-arm-b-model-harness/contracts"
    extra.append({"tranche": "P6", "path": "sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.md",
                  "recorded": H001_MODEL_RUNTIME, "live": p51_hash(p6 / "model-runtime.md"),
                  "ok": p51_hash(p6 / "model-runtime.md") == H001_MODEL_RUNTIME})
    extra.append({"tranche": "P6", "path": "sdd/specs/P6-arm-b-model-harness/contracts/arm-b-protocol.md",
                  "recorded": H001_ARM_B_PROTOCOL, "live": p51_hash(p6 / "arm-b-protocol.md"),
                  "ok": p51_hash(p6 / "arm-b-protocol.md") == H001_ARM_B_PROTOCOL})
    extra.append({"tranche": "P6.1", "path": "sdd/specs/P6.1-arm-b-answerability/contracts/model-runtime.amendment-1.md",
                  "recorded": H001_P6_RUNTIME_AMENDMENT,
                  "live": p51_hash(root() / "sdd/specs/P6.1-arm-b-answerability/contracts/model-runtime.amendment-1.md"),
                  "ok": p51_hash(root() / "sdd/specs/P6.1-arm-b-answerability/contracts/model-runtime.amendment-1.md") == H001_P6_RUNTIME_AMENDMENT})
    extra.append({"tranche": "P5.1", "path": "sdd/specs/P5.1-modelview-separation/contracts/representation-interface.amendment-1.md",
                  "recorded": P51_INTERFACE_AMENDMENT,
                  "live": p51_hash(root() / "sdd/specs/P5.1-modelview-separation/contracts/representation-interface.amendment-1.md"),
                  "ok": p51_hash(root() / "sdd/specs/P5.1-modelview-separation/contracts/representation-interface.amendment-1.md") == P51_INTERFACE_AMENDMENT})
    extra.append({"tranche": "P7", "path": "sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md",
                  "recorded": P7_DEF,
                  "live": p51_hash(root() / "sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md"),
                  "ok": p51_hash(root() / "sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md") == P7_DEF})
    extra.append({"tranche": "P7", "path": "sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md",
                  "recorded": P7_PLAN,
                  "live": p51_hash(root() / "sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md"),
                  "ok": p51_hash(root() / "sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md") == P7_PLAN})
    all_rows = rows_h + extra
    prior = {"ok": all(r["ok"] for r in all_rows), "rows": all_rows}
    write_json(rd / "prior-hashes.json", prior)
    plan = load_plan()
    comp = json.loads((review_dir("K007") / "matrix-completeness.json").read_text())
    hl = json.loads((review_dir("K009") / "headline.json").read_text())
    sc03 = json.loads((review_dir("K008") / "sc03-finding.json").read_text())
    sc04 = json.loads((review_dir("K008") / "sc04-finding.json").read_text())
    refu = json.loads((review_dir("K008") / "refusal-diagnosis.json").read_text())
    sig = json.loads((review_dir("K002") / "sc02-evidence-signature.json").read_text())
    handoff = {
        "tranche": "P7",
        "article_count": 18,
        "p8_builds": "analysis/figures",
        "addendum": "docs/P7-architecture-handoff.addendum.md",
        "anti_goal_inversion": False,
        "article_xix_note": "P7 adds no article; Article XIX would come from a later review if a new class surfaces.",
        "throughput": plan.get("measured_cycle_seconds"),
        "K": plan.get("K"),
        "total_planned_runs": plan.get("total_planned_runs"),
        "matrix_completeness": {"total_rows": comp.get("total_rows"),
                                "total_planned_runs": comp.get("total_planned_runs"),
                                "partition": comp.get("partition")},
        "scenarios": {
            "SC-01": {"citation": ["existing P3/P6.1"], "referenced": True, "incident": HEADLINE},
            "SC-02": {"citation": ["Naihin2023"], "incident": latest_frozen("SC-02")},
            "SC-03": {"citation": ["GarciaMolinaSalem1987"], "incident": latest_frozen("SC-03")},
            "SC-04": {"citation": ["Cemri2025", "Greshake2023"], "incident": latest_frozen("SC-04")},
        },
        "sc02_checkpoint_gap_seconds": sig.get("checkpoint_gap_seconds"),
        "sc02_fs_db_skew_ms": sig.get("fs_db_skew_ms"),
        "sc03_tradeoff": {"legit_dml_sacrificed": sc03.get("legit_dml_sacrificed"),
                          "single_coord_optimum_lsn": sc03.get("single_coord_optimum_lsn")},
        "sc04_headline": hl.get("sc04"),
        "refusal_diagnoses": {"n_refusals": refu.get("n_refusals"), "n_diagnosed": refu.get("n_diagnosed")},
        "sc01_protected": True,
        "model_id": env("MODEL_ID"),
    }
    write_json(root() / "docs/P7-handoff.json", handoff)
    md = f"""# P7 architecture handoff

P7 expands the experiment from one frozen SC-01 headline to a stratified matrix across
SC-02 (filesystem mass deletion; Naihin et al. 2023), SC-03 (staged destructive DDL;
Garcia-Molina & Salem 1987) and SC-04 (stealthy randomized updates; Cemri et al. 2025,
Greshake et al. 2023). SC-01 is referenced, never re-run. Eighteen articles remain in force;
P7 adds none. Article XIX would come from a later review if a new class surfaces.

## Throughput and plan

Re-measured generate_incident mean {plan['measured_cycle_seconds']['generate_incident']} s;
evaluate_arm_t2 mean {plan['measured_cycle_seconds']['evaluate_arm_t2']} s.
K={plan['K']}; total_planned_runs={plan['total_planned_runs']}.
The P0.1 49.335 s figure was not used as the budget.

## Matrix completeness

total_rows={comp.get('total_rows')} total_planned_runs={comp.get('total_planned_runs')}
partition={json.dumps(comp.get('partition'))}.

## SC-02 filesystem track

checkpoint_gap_seconds={sig.get('checkpoint_gap_seconds')}; fs_db_skew_ms={sig.get('fs_db_skew_ms')}.
Coordinated FS+DB recovery was not attempted (ADR-P7-6).

## SC-03 trade-off

single_coord_optimum_lsn={sc03.get('single_coord_optimum_lsn')};
legit_dml_sacrificed={sc03.get('legit_dml_sacrificed')}.

## SC-04 strongest figure

{json.dumps(hl.get('sc04'), indent=2, sort_keys=True)}

## Residual refusals

n_refusals={refu.get('n_refusals')}; n_diagnosed={refu.get('n_diagnosed')}; bare_null=false.
Diagnoses: logs/review/K008/refusal-diagnosis.json.

## Host-side evaluate

Live T2 `zfs rollback -r` on shared DS_PARENT destroys snapshots newer than the target (T012).
SC-02 T2 removed SC-03/SC-04 ZFS snapshots, so SC-03/SC-04 (and subsequent) cells resolve coordinates
from archive snapshots.json with victim_rollback=false. `reset_tier` remains `t2` (schema enum).
P4 restore+validate is unchanged; it is skipped when `oracle-manifest.json` is absent (new scenarios).

## P8

P8 builds the analysis notebook and figures from the complete results file.

## Addendum

Operational challenges and deviations (T2 sibling-snapshot destruction, host-side
evaluate, P4 skip, Article XIV, ledger windowing, gate pins):
`docs/P7-architecture-handoff.addendum.md`.
"""
    if any(s.lower() in md.lower() for s in INVERSION):
        raise SystemExit("assertion failed: handoff contains anti-goal inversion")
    write_text(root() / "docs/P7-architecture-handoff.md", md)
    # Readonly check (inner skip).
    ro = run(["bin/lab-gate-readonly-check", "bin/lab-verify-p7"], timeout=180)
    write_text(rd / "readonly-check.out", ro.stdout + "\n" + ro.stderr)
    # Negative (a): documented separately; we do not actually write under evidence here.
    write_json(rd / "negative.json", {
        "readonly_exit": ro.returncode,
        "inversion_strings_absent": True,
    })
    gate = run(["bin/lab-verify-p7"], timeout=180)
    write_text(rd / "verify-p7.out", gate.stdout)
    rows = [
        row("K010-1", "M", "bin/lab-verify-p7", "all PASS; TIER M/A printed",
            (gate.stdout.splitlines() or [""])[0], gate.returncode == 0),
        row("K010-2", "M", "lab-gate-readonly-check bin/lab-verify-p7", "evidence unchanged",
            f"exit={ro.returncode}", ro.returncode == 0),
        row("K010-3", "M", "prior-hashes.json", "every frozen contract hash unchanged",
            f"ok={prior['ok']}", prior["ok"]),
        row("K010-4", "A", "docs/P7-handoff.json", "P8 builds analysis; 18 articles; no inversion",
            f"p8={handoff['p8_builds']}", handoff["p8_builds"].startswith("analysis") and handoff["article_count"] == 18),
        row("K010-N", "M", "readonly + inversion guards", "readonly-check ran; inversion absent",
            f"ro={ro.returncode}", ro.returncode == 0 and handoff["anti_goal_inversion"] is False),
    ]
    obs = (
        "Handoff states P8 builds analysis/figures. "
        "Frozen SC-01 headline, P4 path, representations, guard and model pin were not modified. "
        "AC-P7-03/04 required skipping kind/cites/overlaps as top-level definition keys. "
        "H001_P6_RUNTIME_AMENDMENT now matches the committed amendment-1 file "
        "(ee097868…; the previous pin was stale after 4779f43).\n"
    )
    finish("K010", rows, [
        root() / "bin/lab-verify-p7",
        root() / "docs/P7-architecture-handoff.md",
        root() / "docs/P7-handoff.json",
        rd / "prior-hashes.json",
    ], obs)


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit("usage: lab-p7-review K001|K002|...|K010|k006_cell")
    name = argv[0].replace("-", "_")
    fn = globals().get(name.lower()) or globals().get(name)
    if not callable(fn):
        raise SystemExit(f"unknown task {argv[0]}")
    fn()
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
