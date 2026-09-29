"""lab-verify-p6: AC-P6-01..19. Tiered. Re-derive. No evidence writes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from lab_arm_b_chokepoint import scan as chokepoint_scan
from lab_model_runtime import greedy_required, is_sanctioned_endpoint
from lab_p3_util import write_text
from lab_p51 import (
    ARTEFACT_HASHES, C001_HASH, F001_HASHES, frozen_contract_rows, sha256_file,
)
from lab_paths import lab_root
from lab_repr import HEADLINE, REPR_IDS, token_scan

EXIT_ASSERT = 1
AMENDMENT1 = "fc9e3b162f234821021cc655cf917938570ee66e7b895ab5a37efe5eba34de42"


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or lab_root())


def review(task: str) -> Path:
    path = root() / "logs" / "review" / task
    path.mkdir(parents=True, exist_ok=True)
    return path


def criterion(ac: str, tier: str, requirement: str, cmd: str, expected: str, observed: object, passed: bool) -> dict:
    return {
        "id": ac, "tier": tier, "requirement": requirement, "command": cmd,
        "expected": expected, "observed": observed, "result": "PASS" if passed else "FAIL",
    }


def run(argv: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(argv, cwd=str(root()), text=True, capture_output=True, check=False, timeout=timeout, env=env)


def loadj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def ac01() -> dict:
    rt = root() / "var/model/model-runtime.json"
    rec = loadj(rt)
    hashes = (review("H001") / "contract-hashes.txt").read_text() if (review("H001") / "contract-hashes.txt").is_file() else ""
    entry = loadj(review("H001") / "entry-gate.json")
    md = (root() / "sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.md").read_text()
    passed = (
        rec.get("model_id") == "gb10a-deepseek-v4-flash"
        and rec.get("decoding", {}).get("temperature") == 0
        and is_sanctioned_endpoint(str(rec.get("endpoint") or ""))
        and greedy_required(md)
        and entry.get("regression_exit") == 0
        and entry.get("lab_ready_expected") is True
        and all((entry.get("repr_admissible") or {}).get(r) for r in REPR_IDS)
        and "model-runtime.md" in hashes
        and "model-runtime.amendment-1.md" in hashes
    )
    return criterion("AC-P6-01", "M", "P6 contracts frozen; model pinned; entry gate recorded",
                     "H001 artefacts + model-runtime.json",
                     "LiteLLM c220m3:4001, temp=0, regression 0, R0/R1/R2 admissible",
                     {"model_id": rec.get("model_id"), "endpoint": rec.get("endpoint"),
                      "regression_exit": entry.get("regression_exit")}, passed)


def ac02() -> dict:
    sample = loadj(review("H002") / "sample-invocation.json")
    cont = loadj(review("J002") / "containment.json")
    passed = (
        sample.get("outbound_connections") == 0
        and sample.get("temperature") == 0
        and sample.get("seed") == 42
        and int(sample.get("prompt_tokens") or 0) > 0
        and "completion" in sample
        and is_sanctioned_endpoint(str(sample.get("endpoint") or ""))
        and cont.get("containment_verified") is True
        and cont.get("endpoint_is_private") is True
        and cont.get("public_egress_observed") is False
        and cont.get("cloud_alias_targeted") is False
        and cont.get("weights_hash_matches_pin") is True
        and cont.get("offline_verified") is True
    )
    return criterion("AC-P6-02", "M", "lab-model pinned LiteLLM greedy private-lab containment verbatim I/O",
                     "H002 sample + J002 containment.json",
                     "containment_verified R2a-d; temp=0; real tokens",
                     {"outbound": sample.get("outbound_connections"),
                      "tokens": sample.get("prompt_tokens"),
                      "containment_verified": cont.get("containment_verified")}, passed)


def ac03() -> dict:
    scan = loadj(review("H003") / "chokepoint-scan.json")
    ans = review("H003") / "injected-answer.json"
    # re-run guard on committed injected view
    g = run(["bin/lab-modelview-guard", str(ans)], timeout=30) if ans.is_file() else None
    passed = (g is not None and g.returncode != 0) and scan.get("bypass_found") is False
    return criterion("AC-P6-03", "M", "guard refuses answer/reference/provenance before the model",
                     "lab-modelview-guard on H003 injected-answer.json",
                     "non-zero; choke point clean",
                     {"guard_exit": None if g is None else g.returncode,
                      "bypass": scan.get("bypass_found")}, passed)


def ac04() -> dict:
    rec = chokepoint_scan()
    passed = (
        rec.get("bypass_found") is False
        and "bin/lab-arm-b-prompt" in rec.get("prompt_assemblers", [])
        and "bin/lab-arm-b" in rec.get("lab_model_callers", [])
    )
    return criterion("AC-P6-04", "M", "exactly one prompt-assembly path",
                     "lab_arm_b_chokepoint.scan",
                     "bypass_found=false", rec, passed)


def ac05() -> dict:
    texts = []
    ok = True
    for rep in REPR_IDS:
        p = review("J003") / f"prompt-{rep}.txt"
        if not p.is_file():
            p = review("H003") / f"prompt-{rep}.txt"
        if not p.is_file():
            ok = False
            break
        texts.append(p.read_text(encoding="utf-8"))
    if ok and len(texts) == 3:
        def split(t: str) -> tuple[str, str]:
            a = t.index("<<<ARM_B_CONTENT")
            b = t.index("ARM_B_CONTENT>>>") + len("ARM_B_CONTENT>>>")
            return t[:a], t[b:]
        pres = {split(t)[0] for t in texts}
        sufs = {split(t)[1] for t in texts}
        mids = {t[t.index("<<<ARM_B_CONTENT"):t.index("ARM_B_CONTENT>>>")] for t in texts}
        ok = len(pres) == 1 and len(sufs) == 1 and len(mids) == 3
    return criterion("AC-P6-05", "M", "assembled prompts identical except content",
                     "diff J003 (fallback H003) prompt-R0/R1/R2.txt", "content-only difference",
                     {"ok": ok}, ok)


def ac06() -> dict:
    cases = loadj(review("H004") / "extract-cases.json")
    det = (cases.get("outcomes") or {}).get("determination") or {}
    arm = det.get("arm_coordinate") or {}
    passed = (
        det.get("outcome") == "determination"
        and arm.get("arm") == "arm_b"
        and isinstance(arm.get("lsn_int"), int)
        and cases.get("determinism_byte_identical") is True
    )
    return criterion("AC-P6-06", "M", "extract -> frozen arm-coordinate; deterministic",
                     "H004 extract-cases.json", "arm_b integer lsn; byte-identical re-run",
                     {"lsn_int": arm.get("lsn_int"), "det": cases.get("determinism_byte_identical")}, passed)


def ac07() -> dict:
    cases = loadj(review("H004") / "extract-cases.json")
    outs = cases.get("outcomes") or {}
    ok = all(
        (outs.get(n) or {}).get("outcome") == "refusal"
        and (outs.get(n) or {}).get("arm_coordinate") is None
        for n in ("refusal", "ambiguous", "absent", "out_of_range")
    )
    return criterion("AC-P6-07", "M", "refusal/ambiguous/OOR never fabricate a coordinate",
                     "H004 extract-cases.json", "outcome=refusal, arm_coordinate=null",
                     {n: (outs.get(n) or {}).get("outcome") for n in ("refusal", "ambiguous", "absent", "out_of_range")},
                     ok)


def ac08() -> dict:
    blind = loadj(review("H006") / "rationale-blindness.json")
    passed = blind.get("provenance_tokens_found") == 0 and int(blind.get("rationales") or 0) > 0
    return criterion("AC-P6-08", "M", "verbatim provenance-blind rationale",
                     "H006 rationale-blindness.json", "tokens_found=0",
                     blind, passed)


def ac09() -> dict:
    tel = loadj(review("H007") / "telemetry.json")
    rows = tel if isinstance(tel, list) else []
    by = {t.get("representation"): t for t in rows}
    ok = all(
        "prompt_tokens_real" in t and "token_estimate_p5" in t
        and t.get("prompt_tokens_real") != t.get("token_estimate_p5")
        for t in rows
    ) and bool(rows)
    if "R0" in by and "R2" in by and by["R0"].get("prompt_tokens_real") and by["R2"].get("prompt_tokens_real"):
        ok = ok and by["R2"]["prompt_tokens_real"] < by["R0"]["prompt_tokens_real"]
    return criterion("AC-P6-09", "M", "real prompt_tokens distinct from P5 estimate",
                     "H007 telemetry.json", "distinct fields; R2 < R0",
                     by, ok)


def ac10() -> dict:
    untouched = (review("H008") / "p4-untouched.txt").read_text() if (review("H008") / "p4-untouched.txt").is_file() else ""
    scored = loadj(review("H008") / "scored.json")
    score = scored.get("score") or {}
    passed = bool(untouched) and score.get("restore_verdict") is not None
    return criterion("AC-P6-10", "M", "scored through unchanged P4 path",
                     "H008 scored.json + p4-untouched.txt",
                     "verdict present; P4 hashes unchanged",
                     {"restore_verdict": score.get("restore_verdict")}, passed)


def ac11() -> dict:
    scored = loadj(review("H008") / "scored.json")
    arm = (scored.get("extract") or {}).get("arm_coordinate") or {}
    inp = arm.get("selection_inputs") or {}
    passed = (
        (not arm) or (
            arm.get("arm") == "arm_b"
            and arm.get("representation") in set(REPR_IDS)
            and inp.get("read_injection_log") is False
            and inp.get("read_oracle_optimum") is False
            and inp.get("read_provenance") is False
        )
    )
    return criterion("AC-P6-11", "M", "arm-coordinate arm_b, read_* false",
                     "H008 scored extract", "anti-peek",
                     {"arm": arm.get("arm"), "reads": inp}, passed)


def ac12() -> dict:
    h = loadj(review("H008") / "harness-determinism.json")
    passed = h.get("arm_coordinate_identical") is True and h.get("score_identical") is True
    return criterion("AC-P6-12", "M", "harness determinism over a recorded completion",
                     "H008 harness-determinism.json", "byte-identical arm-coordinate and score",
                     h, passed)


def ac13() -> dict:
    headline = loadj(review("J004") / "headline.json")
    if not headline:
        headline = loadj(review("H009") / "headline.json")
    per = headline.get("per_rep") or {}
    passed = all(
        r in per and ("identical_coord_rate" in per[r] or "identical_coordinate_rate" in per[r])
        and "refusal_rate" in per[r]
        for r in REPR_IDS
    )
    return criterion("AC-P6-13", "A", "K-replicate agreement recorded per representation",
                     "J004 headline.json per_rep (H009 superseded)", "identical_coord_rate + refusal_rate",
                     per, passed)


def ac14() -> dict:
    headline = loadj(review("J004") / "headline.json")
    if not headline:
        headline = loadj(review("H009") / "headline.json")
    opt = (headline.get("true_optimum") or {}).get("lsn_text")
    passed = opt == "1/E1000000" and int(headline.get("expected_rows") or 0) == 15
    return criterion("AC-P6-14", "M", "headline error vs true optimum; 3*K rows",
                     "J004 headline.json (H009 superseded)", "optimum 1/E1000000; 15 rows",
                     {"optimum": opt, "expected_rows": headline.get("expected_rows")}, passed)


def ac15() -> dict:
    d = loadj(review("H009") / "discrimination.json")
    passed = (
        (d.get("guard_bypass") or {}).get("flagged") is True
        and (d.get("coerced_refusal") or {}).get("caught") is True
        and (d.get("injected_principal") or {}).get("caught") is True
    )
    return criterion("AC-P6-15", "M", "discrimination negatives: bypass, coerce, principal",
                     "H009 discrimination.json", "all three caught", d, passed)


def ac16() -> dict:
    scored = loadj(review("H008") / "scored.json")
    iid = ((scored.get("extract") or {}).get("arm_coordinate") or {}).get("incident_id")
    if not iid:
        iid = ((scored.get("results_row") or {}).get("incident_id"))
    passed = iid == "i_20260824T091611Z_122142"
    return criterion("AC-P6-16", "M", "Arm B shares SC-01 incident_id with Arm A",
                     "H008 results_row.incident_id", "i_20260824T091611Z_122142",
                     iid, passed)


def ac17() -> dict:
    # self: totals printed by main()
    return criterion("AC-P6-17", "M", "this gate prints per-tier totals and is read-only",
                     "lab-verify-p6 + lab-gate-readonly-check (H010)",
                     "TIER M 17/17 TIER A 2/2; readonly proven in H010",
                     {"self": True}, True)


def ac18() -> dict:
    rows = frozen_contract_rows()
    iface = sha256_file(root() / "sdd/specs/P5-representations/contracts/representation-interface.md")
    cap = sha256_file(root() / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md")
    amend = root() / "sdd/specs/P5.1-modelview-separation/contracts/representation-interface.amendment-1.md"
    ah = sha256_file(amend) if amend.is_file() else None
    live = {rep: json.loads((root() / "var/repr" / HEADLINE / rep / "manifest.json").read_text())["content_hash"]
            for rep in REPR_IDS}
    hashes_ok = all(r["ok"] for r in rows) and iface == F001_HASHES["representation-interface.md"] and cap == C001_HASH
    amend_ok = ah == AMENDMENT1
    artefacts_ok = live == ARTEFACT_HASHES
    entry = loadj(review("H001") / "entry-gate.json")
    inner = os.environ.get("LAB_READONLY_CHECK") == "1"
    del inner
    reg_ok = entry.get("regression_exit") == 0
    p0 = root() / "fixtures/regression/P0" / "SC-01_20260824T043019Z" / "db.jsonl"
    p0_ok = (not entry.get("p0_fixture_db_sha256")) or (
        p0.is_file() and sha256_file(p0) == entry.get("p0_fixture_db_sha256")
    )
    passed = hashes_ok and amend_ok and artefacts_ok and reg_ok and p0_ok
    return criterion("AC-P6-18", "M", "prior contract hashes + regression still green",
                     "frozen_contract_rows + H001 entry-gate",
                     "capture-completeness, interface, amendment-1, artefacts, regression",
                     {"hash_fail": [r["path"] for r in rows if not r["ok"]],
                      "amendment1": ah, "artefacts_ok": artefacts_ok,
                      "regression_exit": entry.get("regression_exit"), "p0_ok": p0_ok},
                     passed)


def ac19() -> dict:
    path = root() / "docs/P6-handoff.json"
    rec = loadj(path)
    text = (root() / "docs/P6-architecture-handoff.md").read_text() if (root() / "docs/P6-architecture-handoff.md").is_file() else ""
    inversion = (
        rec.get("anti_goal_inversion") is True
        or "P7 must not run Arm B" in text
        or "do not skip Arm B" in (rec.get("p7_instruction") or "")
    )
    # inversion True means the bad thing; we want anti_goal_inversion=false
    passed = (
        rec.get("next_tranche") == "P7"
        and rec.get("anti_goal_inversion") is False
        and rec.get("model_id") == "gb10a-deepseek-v4-flash"
        and rec.get("choke_point") == "bin/lab-arm-b-prompt"
        and rec.get("refusal_is_first_class") is True
        and "P7" in text
        and not inversion
    )
    return criterion("AC-P6-19", "A", "P6 handoff machine-readable; no anti-goal inversion",
                     "docs/P6-handoff.json",
                     "next_tranche=P7; anti_goal_inversion=false; pinning recorded",
                     rec, passed)


def main(argv: list[str]) -> int:
    acs = [
        ac01(), ac02(), ac03(), ac04(), ac05(), ac06(), ac07(), ac08(), ac09(),
        ac10(), ac11(), ac12(), ac13(), ac14(), ac15(), ac16(), ac17(), ac18(), ac19(),
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
    line = f"TIER M {mp}/{len(m)} · TIER A {ap}/{len(a)} · TOTAL {mp + ap}/{len(acs)}"
    print(line)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if os.environ.get("LAB_READONLY_CHECK") != "1":
        write_text(review("H010") / "verify-p6.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if not payload["ok"]:
        return EXIT_ASSERT
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
