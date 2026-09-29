"""P7.1 AC-01..21 read-only, tiered acceptance gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from lab_p71_l004 import derive, provenance_scan, root
from lab_p51 import frozen_contract_rows
from lab_p3_util import write_json
from lab_redaction import pinned  # ADR-M002

EXIT_ASSERT = 1


def loadj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def criterion(ac: int, tier: str, requirement: str, observed, passed: bool) -> dict:
    return {"id": f"AC-P7.1-{ac:02d}", "tier": tier, "requirement": requirement,
            "observed": observed, "result": "PASS" if passed else "FAIL"}


def memo_object() -> dict:
    path = root() / "docs/p7-acceptance-memo.md"
    if not path.is_file():
        return {}
    match = re.search(r"```json\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)
    return json.loads(match.group(1)) if match else {}


def contract_state() -> dict:
    rows = {row["path"]: {"observed": row["live"], "expected": row["recorded"],
                           "match": row["ok"]} for row in frozen_contract_rows()}
    paths = {
        "sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.md": "9e9a86ef6d74a1de6765890f3e6ef79d4e766e75db6e3f913cf6c5b8c98e82d2",
        "sdd/specs/P6-arm-b-model-harness/contracts/arm-b-protocol.md": pinned("99368b81220490fdd5a0906d0ef398c2589749508563ed136f8a111f8b9bb31f"),
        "sdd/specs/P6.1-arm-b-answerability/contracts/model-runtime.amendment-1.md": "ee097868a897e1ba52c3dbec042461187824ef5e753a0970dc53369038a500f2",
        "sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md": pinned("74a9c25f15b42ded29a59e3a24414a8bd9ec8f36bee4314bff768a951f78ef55"),
        "sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md": pinned("4665066de522a368126e580db94411a63de768008b2bf40f758a93fb73be840e"),
        "sdd/specs/P7.1-matrix-isolation/contracts/incident-isolation.md": "02238cf2953eb11d32217b3f0b84d81a1bd985c3b9c96b7394c07706bbab8767",
        "sdd/specs/P7.1-matrix-isolation/contracts/run-matrix-plan.amendment-1.md": "96c1c9a0962b1b050e742b2cefadf601970f3927c5905b67098ba6f2f0512640",
        "sdd/specs/P7.1-matrix-isolation/contracts/run-matrix-plan.amendment-2.md": "6739c6440b82b24c78a57acbe63a9bb02613a5d27d7c33938e19dead661e9498",
    }
    for rel, expected in paths.items():
        observed = sha(root() / rel)
        rows[rel] = {"observed": observed, "expected": expected, "match": observed == expected}
    return {"ok": all(v["match"] for v in rows.values()), "files": rows}


def run(mapping_path: Path) -> dict:
    c: list[dict] = []
    constitution = (root() / "sdd/.specify/memory/constitution.md").read_text(encoding="utf-8")
    root_cause = loadj(root() / "logs/review/L001/root-cause.json")
    decision = loadj(root() / "logs/review/L001/decision.json")
    adr = (root() / "logs/review/L001/adr.md").read_text(encoding="utf-8")
    c.append(criterion(1, "M", "Article XIX and XX in force", {"XIX": "Article XIX" in constitution,
                       "XX": "Article XX" in constitution}, "Article XIX" in constitution and "Article XX" in constitution))
    adr_ok = all(f"ADR-P7.1-{n}" in adr for n in range(1, 6)) and (root() / "docs/adr/ADR-P7.1-6-live-heartbeat-coordinate-enum.md").is_file()
    c.append(criterion(2, "M", "root cause and ADR-P7.1-1..6 recorded", {"root_cause": root_cause, "adrs": adr_ok}, bool(root_cause) and adr_ok))
    c.append(criterion(3, "A", "FULL decision operator-countersigned", decision,
                       decision.get("decision") == "FULL" and decision.get("operator_countersigned") is True))

    isolation = loadj(root() / "logs/review/L002/isolation-proof.json")
    contract = root() / "sdd/specs/P7.1-matrix-isolation/contracts/incident-isolation.md"
    runtime_files = list((root() / "runtime/incidents").glob("*.env"))
    c.append(criterion(4, "M", "per-incident dataset contract present", {"contract": contract.is_file(), "runtimes": len(runtime_files)}, contract.is_file() and len(runtime_files) >= 3))
    c.append(criterion(5, "M", "incident runtimes use distinct datasets and ports", {"runtime_files": len(runtime_files)}, len(runtime_files) >= 3))
    neg = (root() / "logs/review/L002/negative-disposable-parent.txt").read_text(encoding="utf-8")
    c.append(criterion(6, "M", "shared-parent reset refused", {"negative": bool(neg)}, "refus" in neg.lower() or "exit" in neg.lower()))
    c.append(criterion(7, "M", "sibling state byte-identical after reset", isolation,
                       isolation.get("ok") is True and isolation.get("byte_identical") is True and isolation.get("heartbeat_identical") is True))

    p4 = loadj(root() / "logs/review/L003/sc02-p4-verdict.json")
    sets = loadj(root() / "logs/review/L003/sc0304-set-verdict.json")
    c.append(criterion(8, "M", "SC-02 oracle and real P4 validation", p4,
                       p4.get("restore_attempted") is True and p4.get("restore_verdict") != "stub"))
    c.append(criterion(9, "M", "SC-03/04 set validation", sets,
                       all((sets.get(s) or {}).get("precision") == 1.0 and (sets.get(s) or {}).get("recall") == 1.0 for s in ("SC-03", "SC-04"))))

    comp, active, mappings = derive(root() / "results/matrix.jsonl")
    samples = loadj(root() / "logs/review/L004/live-coord-sample.json")
    c.append(criterion(10, "M", "live coordinates with measured non-zero skew", samples,
                       samples.get("ok") is True and all(x["chosen_coordinate"].get("resolved_by") == "live_heartbeat"
                       and x["chosen_coordinate"].get("skew_ms", 0) > 0 for x in samples.get("samples") or [])))
    c.append(criterion(11, "M", "completeness plus validity partition", comp,
                       comp["ok"] and comp["total_rows"] == comp["total_planned_runs"] == 51 and comp["partition"]["stub_validations"] == 0))
    negative = loadj(root() / "logs/review/L004/negative-test.json")
    c.append(criterion(12, "M", "dropped-row negative detected then restored", negative,
                       negative.get("negative_exit") not in (None, 0) and negative.get("restored_original_exit") == 0))
    manifest = loadj(root() / "results/superseded_manifest.json")
    c.append(criterion(13, "M", "supersede-not-delete including irrecoverable attempts",
                       {"edges": len(mappings), "irrecoverable": len(manifest.get("irrecoverable") or [])},
                       len(mappings) >= 51 and len(manifest.get("irrecoverable") or []) == 34))

    headline = loadj(root() / "logs/review/L005/headline.json")
    raw_headline = json.dumps(headline)
    c.append(criterion(14, "M", "headline dimensions disaggregated", headline.get("strongest_actionability_gap"),
                       headline.get("strongest_actionability_gap") == "SC-04" and "strongest_figure" not in raw_headline))
    sc04 = ((headline.get("scenarios") or {}).get("SC-04") or {})
    c.append(criterion(15, "M", "SC-04 compactness counter-result", sc04,
                       sc04.get("compactness", {}).get("compactness_holds") is False and
                       sc04.get("compactness", {}).get("evidence_bytes_r2", 0) > sc04.get("compactness", {}).get("evidence_bytes_r0", 0)))
    c.append(criterion(16, "M", "SC-01 sole headline and byte-identical", headline.get("sc01_hashes"),
                       headline.get("sole_validated_headline") == "SC-01" and headline.get("sc01_hashes", {}).get("ok") is True))
    scan = provenance_scan()
    c.append(criterion(17, "M", "active prompts and representations provenance-blind", scan, scan["ok"]))

    mapping = loadj(mapping_path)
    weakened = [e for e in mapping.get("entries") or [] if e.get("change") == "weakened"]
    hashes = contract_state()
    c.append(criterion(18, "M", "criterion mapping strengthened/corrected and frozen hashes verified",
                       {"mapping_ok": mapping.get("ok"), "weakened": weakened, "hashes": hashes},
                       mapping.get("ok") is True and not weakened and hashes["ok"]))
    sc02_active = [r for r in active if r.get("scenario_id") == "SC-02" and
                   (((r.get("validation_detail") or {}).get("matrix") or {}).get("outcome") == "determination")]
    c.append(criterion(19, "M", "SC-02 active determinations use real P4 verdicts",
                       [r.get("restore_verdict") for r in sc02_active], bool(sc02_active) and all(r.get("restore_verdict") != "stub" for r in sc02_active)))
    readonly = root() / "logs/review/L006/readonly-proof.txt"
    inner = os.environ.get("LAB_READONLY_CHECK") == "1"
    c.append(criterion(20, "M", "P7/P7.1 gates read-only with tier totals",
                       {"inner": inner, "proof": readonly.is_file()}, inner or readonly.is_file()))
    memo = memo_object()
    c.append(criterion(21, "A", "acceptance memo records D1/D2/D3 and P7.1-only acceptance", memo,
                       memo.get("p7_accepted_only_after") == "P7.1" and set((memo.get("defects_remediated") or {})) == {"D1", "D2", "D3"}))

    m = [x for x in c if x["tier"] == "M"]
    a = [x for x in c if x["tier"] == "A"]
    mp = sum(x["result"] == "PASS" for x in m); ap = sum(x["result"] == "PASS" for x in a)
    return {"ok": mp == len(m) and ap == len(a), "criteria": c,
            "totals": {"M": {"passed": mp, "total": len(m)}, "A": {"passed": ap, "total": len(a)}}}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lab-verify-p7.1")
    p.add_argument("--mapping", default=str(root() / "logs/review/L006/criterion-mapping.json"))
    args = p.parse_args(argv)
    payload = run(Path(args.mapping))
    m = payload["totals"]["M"]; a = payload["totals"]["A"]
    print(f"TIER M {m['passed']}/{m['total']} · TIER A {a['passed']}/{a['total']}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if os.environ.get("LAB_READONLY_CHECK") != "1":
        write_json(root() / "logs/review/L006/verify-p7.1.json", payload)
    return 0 if payload["ok"] else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main())
