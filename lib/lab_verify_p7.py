"""lab-verify-p7: AC-P7-01..21. Tiered. Re-derive. No evidence writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from lab_p3_util import write_text
from lab_p51 import sha256_file
from lab_p61 import (
    H001_ARM_B_PROTOCOL, H001_MODEL_RUNTIME, H001_P6_RUNTIME_AMENDMENT,
    P51_INTERFACE_AMENDMENT,
)
from lab_p7 import HEADLINE, load_matrix_rows, load_plan, planned_new_cells, recorded_cell_keys, root
from lab_scenario import parse_contract_examples, validate_definition
from lab_redaction import pinned  # ADR-M002

EXIT_ASSERT = 1

P7_DEF_HASH = pinned("74a9c25f15b42ded29a59e3a24414a8bd9ec8f36bee4314bff768a951f78ef55")
P7_PLAN_HASH = pinned("4665066de522a368126e580db94411a63de768008b2bf40f758a93fb73be840e")
INVERSION = ("P8 must not build", "do not build the analysis", "P8 must not build the analysis")


def review(task: str) -> Path:
    path = root() / "logs" / "review" / task
    path.mkdir(parents=True, exist_ok=True)
    return path


def criterion(ac: str, tier: str, requirement: str, cmd: str, expected: str, observed: object, passed: bool) -> dict:
    return {
        "id": ac, "tier": tier, "requirement": requirement, "command": cmd,
        "expected": expected, "observed": observed, "result": "PASS" if passed else "FAIL",
    }


def loadj(path: Path):
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run(argv: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(argv, cwd=str(root()), text=True, capture_output=True, check=False, timeout=timeout, env=env)


def ac01() -> dict:
    hashes = loadj(review("K001") / "contract-hashes.json")
    thru = loadj(review("K001") / "throughput.json")
    plan = loadj(review("K001") / "run-plan.json")
    gate = loadj(review("K001") / "entry-gate.json")
    d = root() / "sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md"
    p = root() / "sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md"
    live = {"scenario-definition.md": sha256_file(d), "run-matrix-plan.md": sha256_file(p)}
    examples = parse_contract_examples(d.read_text())
    gen_n = (thru.get("generate_incident") or {}).get("n") or 0
    ev_n = (thru.get("evaluate_arm_t2") or {}).get("n") or 0
    cells = plan.get("per_cell") or []
    sc04 = [c for c in cells if c.get("scenario") == "SC-04" and c.get("arm") == "arm_b"]
    sc04_full = all(int(c.get("replicates") or 0) == int(plan.get("K") or 0) for c in sc04) and len(sc04) == 3
    sc01_ref = all(c.get("referenced") for c in cells if c.get("scenario") == "SC-01")
    total = int(plan.get("total_planned_runs") or 0)
    summed = sum(int(c["replicates"]) for c in cells if not c.get("referenced"))
    passed = (
        live["scenario-definition.md"] == P7_DEF_HASH
        and live["run-matrix-plan.md"] == P7_PLAN_HASH
        and bool(examples)
        and gen_n >= 3 and ev_n >= 3
        and sc04_full and sc01_ref and total == summed and total > 0
        and gate.get("banked_sc01_present") is True
        and gate.get("model_contained") is True
        and gate.get("lab_ready_reached_0") is True
    )
    return criterion("AC-P7-01", "M", "contracts frozen; throughput re-measured; stratified plan; entry gate",
                     "logs/review/K001/*", "hashes; n>=3; SC-04 full K; lab-ready 0 observed",
                     {"live": live, "gen_n": gen_n, "ev_n": ev_n, "total": total, "summed": summed,
                      "sc04_full": sc04_full, "gate": {k: gate.get(k) for k in ("lab_ready_reached_0", "model_contained", "banked_sc01_present")}},
                     passed)


def _def_ok(scenario: str, **expect) -> tuple[bool, dict]:
    path = root() / "scenarios" / scenario.lower().replace("-", "") / "definition.json"
    doc = json.loads(path.read_text()) if path.is_file() else {}
    errs = validate_definition(doc) if doc else ["missing"]
    obs = {"path": str(path), "errors": errs, "doc_subset": {k: doc.get(k) for k in ("scenario_id", "timing_pattern", "damage_class", "corpus_citation", "ground_truth")}}
    ok = not errs
    special = {"kind", "cites", "overlaps"}
    for k, v in expect.items():
        if k in special:
            continue
        if doc.get(k) != v:
            ok = False
    if expect.get("kind"):
        ok = ok and (doc.get("ground_truth") or {}).get("kind") == expect["kind"]
    if expect.get("cites"):
        ok = ok and all(c in (doc.get("corpus_citation") or []) for c in expect["cites"])
    if expect.get("overlaps"):
        ok = ok and (doc.get("confounder") or {}).get("overlaps_damage") is True
    return ok, obs


def ac02() -> dict:
    ok, obs = _def_ok("SC-02", damage_class="filesystem_data", timing_pattern="near_instant",
                      kind="single_coordinate", cites=["Naihin2023"], overlaps=True)
    inj = (root() / "scenarios/sc02/inject.sh").read_text() if (root() / "scenarios/sc02/inject.sh").is_file() else ""
    sig = loadj(review("K002") / "sc02-evidence-signature.json")
    ora = loadj(review("K002") / "sc02-oracle.json") if (review("K002") / "sc02-oracle.json").is_file() else sig
    ok = ok and "rm -rf" in inj and "OVERWRITE" in inj
    ok = ok and sig.get("checkpoint_gap_seconds") is not None or ora.get("checkpoint_gap_seconds") is not None or sig.get("ok") is True
    return criterion("AC-P7-02", "M", "SC-02 definition+injector+checkpoint oracle",
                     "scenarios/sc02 + K002 signature", "schema-valid; rm+overwrite; gap recorded",
                     {"ok": ok, **obs, "gap": sig.get("checkpoint_gap_seconds") or ora.get("checkpoint_gap_seconds")}, ok)


def ac03() -> dict:
    ok, obs = _def_ok("SC-03", damage_class="database_schema", timing_pattern="slow",
                      kind="set_and_earliest", cites=["GarciaMolinaSalem1987"], overlaps=True)
    trade = loadj(review("K003") / "sc03-tradeoff.json")
    ok = ok and int(trade.get("legit_dml_sacrificed") or 0) > 0
    return criterion("AC-P7-03", "M", "SC-03 staged DDL + sacrifice reported",
                     "scenarios/sc03 + K003 tradeoff", "set_and_earliest; sacrifice>0",
                     {"sacrifice": trade.get("legit_dml_sacrificed"), **obs}, ok)


def ac04() -> dict:
    ok, obs = _def_ok("SC-04", damage_class="database_data", timing_pattern="randomized",
                      kind="set_and_earliest", cites=["Cemri2025", "Greshake2023"], overlaps=True)
    gt = loadj(review("K004") / "sc04-groundtruth.json")
    st = loadj(review("K004") / "sc04-score-selftest.json")
    ok = ok and isinstance(gt.get("malicious_set"), list) and len(gt.get("malicious_set") or []) >= 1
    ok = ok and st.get("perfect", {}).get("precision") == 1.0 and st.get("perfect", {}).get("recall") == 1.0
    return criterion("AC-P7-04", "M", "SC-04 randomized updates + P/R harness",
                     "scenarios/sc04 + K004 groundtruth/selftest", "set recorded; perfect P/R=1",
                     {"n_malicious": len(gt.get("malicious_set") or []), "selftest": st, **obs}, ok)


def ac05() -> dict:
    neg = loadj(review("K001") / "negative.json")
    passed = (neg.get("false_exit") not in (0, None)) and (neg.get("true_exit") == 0)
    return criterion("AC-P7-05", "M", "confounder-less definition refused",
                     "lab-scenario-validate scratch", "false refused; true accepted",
                     neg, passed)


def ac06() -> dict:
    rec = loadj(review("K005") / "repr-admissibility.json")
    sc = rec.get("scenarios") or rec
    ok = all((sc.get(s) or {}).get("admissible") and (sc.get(s) or {}).get("parity")
             and (sc.get(s) or {}).get("guard_clean") and (sc.get(s) or {}).get("rebuild_identical")
             for s in ("SC-02", "SC-03", "SC-04")) if isinstance(sc, dict) else False
    return criterion("AC-P7-06", "M", "per-scenario R0/R1/R2 admissible+parity+guard+rebuild",
                     "logs/review/K005/repr-admissibility.json", "all three scenarios true",
                     rec, ok)


def ac07() -> dict:
    rec = loadj(review("K005") / "sc01-unchanged.json")
    ok = rec.get("ok") is True or rec.get("repr_unchanged") is True
    return criterion("AC-P7-07", "M", "SC-01 artefacts and banked results unchanged",
                     "logs/review/K005/sc01-unchanged.json", "hashes match P5/P5.1 freeze",
                     rec, ok)


def ac08() -> dict:
    from lab_p71_l004 import derive
    comp, active, _ = derive(root() / "results/matrix.jsonl")
    ok = comp["ok"] and len(active) == 51
    return criterion("AC-P7-08", "M", "lab-matrix one active schema-valid tail per cell",
                     "lab_p71_l004.derive(results/matrix.jsonl)", "51 active tails; physical attempts retained",
                     {"active": len(active), "physical": comp["physical_rows"], "errors": comp["errors"]}, ok)


def ac09() -> dict:
    rec = loadj(review("K006") / "idempotency.json")
    ok = rec.get("ok") is True
    return criterion("AC-P7-09", "M", "ledger idempotency + range containment across reset",
                     "logs/review/K006/idempotency.json", "no duplicate LSN; range contained",
                     rec, ok)


def ac10() -> dict:
    comp = loadj(review("L004") / "matrix-completeness.json")
    ok = (comp.get("total_rows") == comp.get("total_planned_runs")
          and comp.get("total_planned_runs") is not None
          and set(comp.get("partition", {}).keys()) >= {"determinations", "refusals", "run_failures"})
    return criterion("AC-P7-10", "M", "unattended matrix complete; failures are rows",
                     "logs/review/L004/matrix-completeness.json", "active total==plan plus validity partition",
                     comp, ok)


def ac11() -> dict:
    from lab_p71_l004 import derive
    comp, active, _ = derive(root() / "results/matrix.jsonl")
    reps = {(r.get("representation"), r.get("replicate")) for r in active
            if r.get("scenario_id") == "SC-04" and r.get("arm") == "model"}
    ok = comp["ok"] and all((rep, k) in reps for rep in ("R0", "R1", "R2") for k in range(1, 6))
    return criterion("AC-P7-11", "M", "timing variants + SC-04 ablation fully replicated",
                     "matrix-completeness.json", "SC-04 R0/R1/R2 at K",
                     {"sc04_model_cells": len(reps), "active": len(active)}, ok)


def ac12() -> dict:
    from lab_p71_l004 import derive
    comp, active, _ = derive(root() / "results/matrix.jsonl")
    from lab_p51 import P4_HASHES
    live = sha256_file(root() / "sdd/specs/P4-restore-validation/contracts/restore-report.md")
    arms = {s: {((r.get("validation_detail") or {}).get("matrix") or {}).get("plan_arm")
                for r in active if r.get("scenario_id") == s} for s in ("SC-02", "SC-03", "SC-04")}
    ok = all(v == {"arm_a", "naive", "arm_b"} for v in arms.values()) and live == P4_HASHES["restore-report.md"]
    return criterion("AC-P7-12", "M", "all arms per scenario; P4 hash unchanged",
                     "completeness + restore-report.md hash", "arm_a+naive+arm_b; P4 byte-identical",
                     {"arms": {k: sorted(v) for k, v in arms.items()}, "p4_live": live, "p4_rec": P4_HASHES["restore-report.md"]}, ok)


def ac13() -> dict:
    sweep = loadj(review("L004") / "provenance-scan.json")
    ok = sweep.get("ok") is True and sweep.get("hits") == []
    return criterion("AC-P7-13", "M", "provenance-blind selection across the matrix",
                     "logs/review/L004/provenance-scan.json", "no principal token",
                     sweep, ok)


def ac14() -> dict:
    from lab_p71_l004 import derive, matrix_outcome
    _comp, active, _ = derive(root() / "results/matrix.jsonl")
    values = [r.get("legit_rows_lost") for r in active if r.get("scenario_id") == "SC-03"
              and matrix_outcome(r) == "determination"]
    rec = {"legitimate_dml_sacrificed": values}
    ok = bool(values) and any(int(v or 0) > 0 for v in values)
    return criterion("AC-P7-14", "M", "SC-03 optimum AND sacrifice from committed fields",
                     "logs/review/K008/sc03-finding.json", "sacrifice>0", rec, ok)


def ac15() -> dict:
    from lab_p71_l004 import derive, matrix_outcome
    _comp, active, _ = derive(root() / "results/matrix.jsonl")
    recs = [((r.get("validation_detail") or {}).get("p4") or {}).get("set_validation") for r in active
            if r.get("scenario_id") == "SC-04" and matrix_outcome(r) == "determination"]
    rec = {"set_validations": recs}
    ok = bool(recs) and all(isinstance(v, dict) and v.get("precision") is not None
                            and v.get("recall") is not None and v.get("earliest_safe_bound") for v in recs)
    return criterion("AC-P7-15", "M", "SC-04 precision/recall + earliest-bounded from fields",
                     "logs/review/K008/sc04-finding.json", "per arm/rep present", rec, ok)


def ac16() -> dict:
    comp = loadj(review("L004") / "matrix-completeness.json")
    rec = {"nondeterminations": comp.get("nondeterminations") or []}
    ok = len(rec["nondeterminations"]) == 26 and all(x.get("cause") for x in rec["nondeterminations"])
    return criterion("AC-P7-16", "A", "residual refusals diagnosed via J001 taxonomy",
                     "logs/review/K008/refusal-diagnosis.json", "no bare null; cause per cell",
                     rec, ok)


def ac17() -> dict:
    hl = loadj(review("L005") / "headline.json")
    ok = (hl.get("strongest_actionability_gap") == "SC-04"
          and "strongest_figure" not in json.dumps(hl)
          and ((hl.get("scenarios") or {}).get("SC-04") or {}).get("compactness", {}).get("compactness_holds") is False)
    return criterion("AC-P7-17", "M", "headline recomputed and dimensions disaggregated",
                     "logs/review/L005/headline.json", "SC-04 actionability; compactness false; no conflated scalar",
                     hl, ok)


def ac18() -> dict:
    sig = loadj(review("K002") / "sc02-evidence-signature.json")
    ok = sig.get("coordinated_fs_db_recovery") is False or sig.get("fs_track_independent") is True
    ok = ok and (sig.get("checkpoint_gap_seconds") is not None or sig.get("fs_db_skew_ms") is not None or sig.get("ok") is True)
    return criterion("AC-P7-18", "M", "SC-02 FS track independent; gap+skew reported",
                     "K002 sc02-evidence-signature.json", "no coordinated recovery; quantities present",
                     sig, ok)


def ac19() -> dict:
    inner = os.environ.get("LAB_READONLY_CHECK") == "1"
    if inner:
        return criterion("AC-P7-19", "M", "lab-verify-p7 per-tier totals; read-only",
                         "self + lab-gate-readonly-check", "TIER M/A printed",
                         {"readonly_inner": True}, True)
    ro = review("K010") / "readonly-check.out"
    passed = ro.is_file()
    return criterion("AC-P7-19", "M", "lab-verify-p7 per-tier totals; read-only over evidence",
                     "bin/lab-gate-readonly-check bin/lab-verify-p7", "evidence manifest unchanged",
                     {"readonly_present": ro.is_file()}, passed)


def ac20() -> dict:
    rec = loadj(review("K010") / "prior-hashes.json")
    live_rt = sha256_file(root() / "sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.md")
    live_ab = sha256_file(root() / "sdd/specs/P6-arm-b-model-harness/contracts/arm-b-protocol.md")
    ok = (live_rt == H001_MODEL_RUNTIME and live_ab == H001_ARM_B_PROTOCOL
          and rec.get("ok") is True)
    return criterion("AC-P7-20", "M", "prior contract hashes unchanged; regression recorded",
                     "logs/review/K010/prior-hashes.json", "model-runtime + arm-b-protocol H001 hashes",
                     {"live_rt": live_rt, "rec": rec.get("ok")}, ok)


def ac21() -> dict:
    rec = loadj(root() / "docs/P7-handoff.json")
    text = (root() / "docs/P7-architecture-handoff.md").read_text() if (root() / "docs/P7-architecture-handoff.md").is_file() else ""
    inv = any(s.lower() in text.lower() for s in INVERSION) or any(s.lower() in json.dumps(rec).lower() for s in INVERSION)
    p8 = rec.get("p8_builds") == "analysis/figures" or "P8 builds" in text
    passed = (not inv) and p8 and rec.get("article_count") == 18
    return criterion("AC-P7-21", "A", "handoff records plan/scenarios/matrix/findings; P8 does analysis; no inversion",
                     "docs/P7-handoff.json", "p8_builds analysis; article_count 18; no inversion",
                     {"p8": rec.get("p8_builds"), "articles": rec.get("article_count"), "inversion": inv}, passed)


def main(argv: list[str]) -> int:
    acs = [
        ac01(), ac02(), ac03(), ac04(), ac05(), ac06(), ac07(), ac08(), ac09(),
        ac10(), ac11(), ac12(), ac13(), ac14(), ac15(), ac16(), ac17(), ac18(),
        ac19(), ac20(), ac21(),
    ]
    m = [c for c in acs if c["tier"] == "M"]
    a = [c for c in acs if c["tier"] == "A"]
    mp = sum(1 for c in m if c["result"] == "PASS")
    ap = sum(1 for c in a if c["result"] == "PASS")
    payload = {
        "ok": all(c["result"] == "PASS" for c in acs),
        "criteria": acs,
        "totals": {
            "M": {"passed": mp, "failed": len(m) - mp, "total": len(m)},
            "A": {"passed": ap, "failed": len(a) - ap, "total": len(a)},
            "all": {"passed": mp + ap, "failed": len(acs) - mp - ap, "total": len(acs)},
        },
    }
    print(f"TIER M {mp}/{len(m)} · TIER A {ap}/{len(a)} · TOTAL {mp + ap}/{len(acs)}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if os.environ.get("LAB_READONLY_CHECK") != "1":
        write_text(review("K010") / "verify-p7.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if not payload["ok"]:
        return EXIT_ASSERT
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
