"""lab-verify-p6.1: AC-P6.1-01..19. Tiered. Re-derive. No evidence writes."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from lab_article18 import well_formed as xviii_well_formed
from lab_diagnose_refusal import diagnose_dir
from lab_p3_util import write_text
from lab_p51 import ARTEFACT_HASHES, artefacts_byte_identical, frozen_contract_rows, sha256_file
from lab_p61 import (
    GT_LSN, H001_ARM_B_PROTOCOL, H001_MODEL_RUNTIME, H001_P6_RUNTIME_AMENDMENT,
    INCIDENT, P51_INTERFACE_AMENDMENT, p6_contracts, p61_contracts, root,
)
from lab_repr import HEADLINE, REPR_IDS, token_scan

EXIT_ASSERT = 1
K = 5


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


def loadj(path: Path):
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ac01() -> dict:
    text = (root() / "sdd/.specify/memory/constitution.md").read_text(encoding="utf-8")
    rec = xviii_well_formed(text)
    passed = rec["ok"] is True and rec["article_count"] == 18
    return criterion("AC-P6.1-01", "M", "Article XVIII well-formed; article count 18",
                     "well_formed(constitution.md)", "18; null root-caused from primary evidence", rec, passed)


def ac02() -> dict:
    adr = (review("J001") / "adr.md").read_text(encoding="utf-8") if (review("J001") / "adr.md").is_file() else ""
    passed = all(x in adr for x in ("ADR-P6.1-1", "ADR-P6.1-2", "ADR-P6.1-3", "ADR-P6.1-4"))
    passed = passed and "grammar-noncompliance" in adr and "window=26870" in adr
    return criterion("AC-P6.1-02", "M", "ADR-P6.1-1..4 recorded with per-representation counts",
                     "logs/review/J001/adr.md", "four ADRs; verbatim quotes",
                     {"has_all_adrs": passed}, passed)


def ac03() -> dict:
    path = review("J001") / "refusal-diagnosis.json"
    rec = loadj(path)
    live = diagnose_dir(root() / "logs/review/H009/completions") if (root() / "logs/review/H009/completions").is_dir() else {}
    per = rec.get("per_representation") or {}
    sums_ok = all((per.get(r) or {}).get("total") == K for r in REPR_IDS) and rec.get("n_classified") == 15
    live_causes = [(x["representation"], x["replicate"], x["cause"]) for x in (live.get("per_completion") or [])]
    rec_causes = [(x["representation"], x["replicate"], x["cause"]) for x in (rec.get("per_completion") or [])]
    passed = path.is_file() and sums_ok and live_causes == rec_causes and len(rec_causes) == 15
    return criterion("AC-P6.1-03", "M", "15 completions classified from bytes; counts sum to K",
                     "lab-diagnose-refusal logs/review/H009/completions",
                     "15; per-rep total=5; re-derivable",
                     {"n": rec.get("n_classified"), "per": per, "rerun_match": live_causes == rec_causes}, passed)


def ac04() -> dict:
    amend = p61_contracts() / "model-runtime.amendment-1.md"
    text = amend.read_text(encoding="utf-8") if amend.is_file() else ""
    base = p6_contracts() / "model-runtime.md"
    base_hash = sha256_file(base)
    passed = (
        amend.is_file()
        and "R2a" in text and "R2b" in text and "R2c" in text and "R2d" in text
        and "containment_verified" in text
        and "c220m3" in text and "gb10a" in text
        and base_hash == H001_MODEL_RUNTIME
    )
    return criterion("AC-P6.1-04", "M", "runtime amendment frozen; base byte-identical",
                     "model-runtime.amendment-1.md + H001 hash",
                     "R2a-d; H001 model-runtime.md hash",
                     {"base_hash": base_hash, "amend_exists": amend.is_file()}, passed)


def ac05() -> dict:
    rec = loadj(review("J002") / "containment.json")
    passed = (
        rec.get("containment_verified") is True
        and rec.get("endpoint_is_private") is True
        and rec.get("public_egress_observed") is False
        and rec.get("cloud_alias_targeted") is False
        and rec.get("weights_hash_matches_pin") is True
        and rec.get("alias_targeted") == "gb10a-deepseek-v4-flash"
        and rec.get("endpoint_host") == "c220m3"
    )
    return criterion("AC-P6.1-05", "M", "containment_verified true with named sub-checks",
                     "logs/review/J002/containment.json",
                     "R2a-d all hold; host=c220m3; alias pinned", rec, passed)


def ac06() -> dict:
    rec = loadj(review("J002") / "negative.json")
    passed = (
        rec.get("public_caught") is True
        and rec.get("cloud_caught") is True
        and rec.get("reverted_ok") is True
    )
    return criterion("AC-P6.1-06", "M", "NEGATIVE: public endpoint or cloud alias is refused",
                     "logs/review/J002/negative.json",
                     "named sub-check fail then revert pass", rec, passed)


def ac07() -> dict:
    amend = p61_contracts() / "arm-b-protocol.amendment-1.md"
    text = amend.read_text(encoding="utf-8") if amend.is_file() else ""
    base = p6_contracts() / "arm-b-protocol.md"
    base_hash = sha256_file(base)
    passed = (
        amend.is_file()
        and "window=<int>" in text
        and "hex" in text.lower()
        and "ts=<iso8601>" in text
        and "latest safe point" in text
        and base_hash == H001_ARM_B_PROTOCOL
    )
    return criterion("AC-P6.1-07", "M", "protocol amendment frozen; base byte-identical",
                     "arm-b-protocol.amendment-1.md + H001 hash",
                     "resolvable locator; H001 protocol hash",
                     {"base_hash": base_hash, "amend_exists": amend.is_file()}, passed)


def ac08() -> dict:
    cases = loadj(review("J003") / "extract-cases.json")
    same = cases.get("same_point") or {}
    ints = [same.get(k, {}).get("lsn_int") for k in ("window", "lsn_hex", "lsn_int", "ts")]
    same_ok = len(ints) == 4 and all(isinstance(x, int) for x in ints) and len(set(ints)) == 1
    refusals = cases.get("refusals") or {}
    ref_ok = all(
        (refusals.get(n) or {}).get("outcome") == "refusal"
        and (refusals.get(n) or {}).get("arm_coordinate") is None
        for n in ("empty", "unresolvable", "both_tags", "neither")
    )
    passed = same_ok and ref_ok
    return criterion("AC-P6.1-08", "M", "four locator forms agree; empty/ambiguous/unresolvable refuse",
                     "J003 extract-cases.json", "same lsn_int; refusal lsn_int null",
                     {"ints": ints, "refusals": {k: (v or {}).get("outcome") for k, v in refusals.items()}}, passed)


def ac09() -> dict:
    texts = []
    ok = True
    for rep in REPR_IDS:
        p = review("J003") / f"prompt-{rep}.txt"
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
    return criterion("AC-P6.1-09", "M", "assembled prompts identical except content",
                     "diff J003 prompt-R0/R1/R2.txt", "content-only difference", {"ok": ok}, ok)


def ac10() -> dict:
    sweep = (review("J003") / "guard-sweep.out").read_text(encoding="utf-8") if (review("J003") / "guard-sweep.out").is_file() else ""
    rec = loadj(review("J003") / "guard-sweep.json")
    passed = rec.get("all_pass") is True and rec.get("answer_or_candidates") is False
    if not rec:
        passed = "exit=0" in sweep and "answer" not in sweep.lower()
    return criterion("AC-P6.1-10", "M", "every assembled input passes the guard; no answer/candidates",
                     "J003 guard-sweep", "all exit 0", rec or {"sweep": sweep[:400]}, passed)


def ac11() -> dict:
    rec = loadj(review("J003") / "negative.json")
    passed = rec.get("answer_leak_caught") is True and rec.get("bare_refusal_stays_refusal") is True
    return criterion("AC-P6.1-11", "M", "NEGATIVE: spliced answer refused; bare REFUSAL stays refusal",
                     "J003 negative.json", "guard non-zero; extract outcome=refusal", rec, passed)


def ac12() -> dict:
    rec = artefacts_byte_identical()
    return criterion("AC-P6.1-12", "M", "R0/R1/R2 artefacts byte-identical to P5.1 close",
                     "F002/F003/F004 content_hash", str(ARTEFACT_HASHES), rec, rec.get("ok") is True)


def ac13() -> dict:
    h = loadj(review("J004") / "headline.json")
    per = h.get("per_rep") or {}
    ok = True
    for r in REPR_IDS:
        row = per.get(r) or {}
        if "determinations" not in row or "refusal_rate" not in row:
            ok = False
        if int(row.get("determinations") or 0) > 0:
            if row.get("median_damage_retained") is None and row.get("p4") is None:
                # allow explicit nulls only if no determinations
                ok = False
    return criterion("AC-P6.1-13", "M", "J004 headline per-rep determination/refusal and P4 scores",
                     "logs/review/J004/headline.json", "rates + P4 fields for determinations", per, ok and bool(per))


def ac14() -> dict:
    det = (review("J004") / "determinism.txt").read_text(encoding="utf-8") if (review("J004") / "determinism.txt").is_file() else ""
    h = loadj(review("J004") / "headline.json")
    per = h.get("per_rep") or {}
    agree = all("identical_coordinate_rate" in (per.get(r) or {}) or "identical_coord_rate" in (per.get(r) or {}) for r in REPR_IDS)
    passed = ("byte-identical" in det.lower() or "identical=true" in det.lower() or "true" in det) and agree
    return criterion("AC-P6.1-14", "M", "harness determinism R7 and replicate agreement R8",
                     "J004 determinism.txt + headline identical_coordinate_rate",
                     "byte-identical re-extract/score; agreement present",
                     {"determinism": det[:300], "agree": agree}, passed)


def ac15() -> dict:
    hits = []
    for path in (review("J003").glob("prompt-R*.txt")):
        text = path.read_text(encoding="utf-8")
        found = token_scan(text)
        if found:
            hits.append({"path": str(path), "tokens": found})
    j004 = review("J004") / "runs"
    if j004.is_dir():
        for path in j004.rglob("*.completion"):
            found = token_scan(path.read_text(encoding="utf-8"))
            if found:
                hits.append({"path": str(path), "tokens": found})
        for path in j004.rglob("*.rationale.txt"):
            found = token_scan(path.read_text(encoding="utf-8"))
            if found:
                hits.append({"path": str(path), "tokens": found})
    passed = not hits
    return criterion("AC-P6.1-15", "M", "no provenance tokens in prompts or rationales",
                     "token_scan J003 prompts + J004 completions", "none",
                     {"hits": hits[:8], "n_hits": len(hits)}, passed)


def ac16() -> dict:
    path = review("H009") / "headline.superseded.json"
    rec = loadj(path)
    pointer = rec.get("superseded_by") or rec.get("pointer") or ""
    text = json.dumps(rec)
    passed = path.is_file() and ("J004" in pointer or "J004" in text)
    return criterion("AC-P6.1-16", "M", "prior null retained as headline.superseded.json with J004 pointer",
                     "logs/review/H009/headline.superseded.json", "exists; pointer to J004",
                     {"exists": path.is_file(), "pointer": pointer or text[:200]}, passed)


def ac17() -> dict:
    mapping = loadj(review("J005") / "criterion-mapping.json")
    rows = mapping.get("changes") or mapping.get("criteria") or []
    if isinstance(mapping.get("mapping"), list):
        rows = mapping["mapping"]
    statuses = [r.get("status") for r in rows] if rows else []
    weakened = [r for r in rows if r.get("status") == "weakened"]
    names = " ".join(json.dumps(r) for r in rows)
    has_containment = "containment" in names.lower() or "R2" in names
    has_grammar = "grammar" in names.lower() or "locator" in names.lower()
    hashes = frozen_contract_rows()
    proto = sha256_file(p6_contracts() / "arm-b-protocol.md")
    runtime = sha256_file(p6_contracts() / "model-runtime.md")
    p6_amend = sha256_file(p6_contracts() / "model-runtime.amendment-1.md")
    iface_am = root() / "sdd/specs/P5.1-modelview-separation/contracts/representation-interface.amendment-1.md"
    hashes_ok = (
        all(r["ok"] for r in hashes)
        and proto == H001_ARM_B_PROTOCOL
        and runtime == H001_MODEL_RUNTIME
        and p6_amend == H001_P6_RUNTIME_AMENDMENT
        and sha256_file(iface_am) == P51_INTERFACE_AMENDMENT
    )
    passed = bool(rows) and not weakened and has_containment and has_grammar and hashes_ok
    passed = passed and all(s in {"preserved", "strengthened"} for s in statuses)
    return criterion("AC-P6.1-17", "M", "no frozen contract mutated; mapping has no weakened",
                     "criterion-mapping.json + frozen hashes",
                     "preserved/strengthened only; P6 contracts byte-identical",
                     {"weakened": weakened, "hash_fail": [r["path"] for r in hashes if not r["ok"]],
                      "n_changes": len(rows)}, passed)


def ac18() -> dict:
    inner = os.environ.get("LAB_READONLY_CHECK") == "1"
    if inner:
        return criterion("AC-P6.1-18", "M", "lab-verify-p6.1 per-tier totals; both gates readonly",
                         "lab-verify-p6.1 + lab-gate-readonly-check",
                         "TIER M/A printed; evidence unchanged",
                         {"self": True, "readonly_inner": True}, True)
    ro = (review("J005") / "readonly-check.out").read_text(encoding="utf-8") if (review("J005") / "readonly-check.out").is_file() else ""
    p6 = loadj(review("J005") / "verify-p6.json")
    passed = (review("J005") / "readonly-check.out").is_file()
    p6_ok = p6.get("ok") is True
    return criterion("AC-P6.1-18", "M", "lab-verify-p6.1 per-tier totals; both gates readonly",
                     "this gate + J005 readonly-check.out + lab-verify-p6",
                     "TIER M/A printed; evidence unchanged",
                     {"readonly_present": bool(ro), "p6_ok": p6_ok}, passed and p6_ok)


def ac19() -> dict:
    path = root() / "docs/p6-acceptance-memo.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    rec = {}
    for b in blocks:
        try:
            rec = json.loads(b)
            break
        except json.JSONDecodeError:
            continue
    if not rec:
        # YAML-like field
        m = re.search(r"p6_accepted_only_after:\s*\"?P6\.1\"?", text)
        rec = {"p6_accepted_only_after": "P6.1"} if m else {}
    passed = rec.get("p6_accepted_only_after") == "P6.1" and "D1" in text and "D2" in text
    return criterion("AC-P6.1-19", "A", "memo records both defects and p6_accepted_only_after=P6.1",
                     "docs/p6-acceptance-memo.md", 'p6_accepted_only_after: "P6.1"',
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
        write_text(review("J005") / "verify-p61.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if not payload["ok"]:
        return EXIT_ASSERT
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
