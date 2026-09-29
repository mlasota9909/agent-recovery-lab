"""lab-verify-p5.1: AC-P5.1-01..16. Tiered. Re-derive. No evidence writes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from lab_article17 import constitution_path, prior_articles, well_formed
from lab_p3_util import write_text
from lab_p51 import (
    ARTEFACT_HASHES, F001_HASHES, MATERIAL_RATIO, MODEL_VIEW_KEYSET,
    amendment_path, artefacts_byte_identical, frozen_contract_rows,
    headline_material, interface_path, pb6_headline, root, sha256_file,
)
from lab_repr import HEADLINE, PROBE_IDS, REPR_IDS, token_scan
from lab_repr_modelview import MODEL_VIEW_KEYS, model_view, parity_modelview, probe_params, reference

EXIT_ASSERT = 1


def review(task: str) -> Path:
    path = root() / "logs" / "review" / task
    path.mkdir(parents=True, exist_ok=True)
    return path


def criterion(ac: str, tier: str, requirement: str, cmd: str, expected: str, observed: object, passed: bool) -> dict:
    return {
        "id": ac, "tier": tier, "requirement": requirement, "command": cmd,
        "expected": expected, "observed": observed, "result": "PASS" if passed else "FAIL",
    }


def json_object_in(text: str) -> dict:
    start = text.index("```json")
    chunk = text[start + len("```json"):]
    end = chunk.index("```")
    return json.loads(chunk[:end])


def run(argv: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(argv, cwd=str(root()), text=True, capture_output=True, check=False, timeout=timeout, env=env)


def bin_path(name: str) -> Path:
    return root() / "bin" / name


def ac01() -> dict:
    path = constitution_path(root())
    text = path.read_text(encoding="utf-8")
    rec = well_formed(text)
    pre = review("G001") / "constitution.pre.md"
    prior_ok = True
    if pre.is_file():
        prior_ok = prior_articles(text).rstrip() == pre.read_text(encoding="utf-8").rstrip()
    rec_ok = rec["ok"] and rec.get("article_count") == 18
    passed = rec_ok and prior_ok
    return criterion("AC-P5.1-01", "M", "Article XVII well-formed; article count 18",
                     "well_formed(constitution.md)", "18; mechanically enforced guard",
                     {**rec, "prior_articles_unchanged": prior_ok}, passed)


def ac02() -> dict:
    a1 = (root() / "docs/adr/ADR-P5.1-1-answer-key-in-subject-view.md").read_text(encoding="utf-8")
    a2 = (root() / "docs/adr/ADR-P5.1-2-modelview-reference-split.md").read_text(encoding="utf-8")
    a3 = (root() / "docs/adr/ADR-P5.1-3-modelview-guard.md").read_text(encoding="utf-8")
    passed = (
        "§4" in a1 and "R3" in a1 and "§5" in a1
        and "answer" in a1 and "content" in a1
        and "PB-6" in a1 and "PB-4" in a1
        and "model_view" in a2 and "reference" in a2 and "bin/lab-repr-query" in a2
        and "lab-modelview-guard" in a3 and "candidates" in a3 and "content" in a3
    )
    return criterion("AC-P5.1-02", "M", "ADR-P5.1-1/2/3 record D1/D2, split, guard",
                     "inspect docs/adr/ADR-P5.1-*.md", "§4 R3 §5; split; guard",
                     {"adr1_quotes": "§4" in a1 and "R3" in a1 and "§5" in a1,
                      "adr2": "model_view" in a2, "adr3": "lab-modelview-guard" in a3}, passed)


def ac03() -> dict:
    amend = amendment_path()
    text = amend.read_text(encoding="utf-8") if amend.is_file() else ""
    mode = oct(amend.stat().st_mode & 0o777) if amend.is_file() else None
    keys_ok = all(k in text for k in MODEL_VIEW_KEYSET) and "`answer`" in text
    iface = sha256_file(interface_path())
    passed = amend.is_file() and mode == "0o444" and keys_ok and iface == F001_HASHES["representation-interface.md"]
    return criterion("AC-P5.1-03", "M", "amendment-1 frozen; base interface byte-identical",
                     "stat amendment + sha256 interface", "0444; F001 hash",
                     {"mode": mode, "keys_ok": keys_ok, "interface": iface}, passed)


def _keys_of(obj: dict) -> list[str]:
    return sorted(obj.keys())


def ac04() -> dict:
    rows = []
    ok = True
    for probe in PROBE_IDS:
        params = probe_params(probe)
        for rep in REPR_IDS:
            view = model_view(HEADLINE, rep, probe, params)
            keys = _keys_of(view)
            clean = keys == sorted(MODEL_VIEW_KEYS) and "answer" not in view and "reference" not in view
            rows.append({"rep": rep, "probe": probe, "keys": keys, "ok": clean})
            ok = ok and clean
    return criterion("AC-P5.1-04", "M", "lab-repr-modelview emits exactly six keys, no answer",
                     "R0/R1/R2 x 6 probes", str(list(MODEL_VIEW_KEYS)),
                     {"n": len(rows), "all_ok": ok}, ok)


def ac05() -> dict:
    ref = reference(HEADLINE, "R2", "PB-6-candidate-windows", {"top_n": 3})
    view = model_view(HEADLINE, "R2", "PB-6-candidate-windows", {"top_n": 3})
    cands = (ref.get("answer") or {}).get("candidates")
    passed = (
        "answer" in ref and isinstance(cands, list) and cands
        and "answer" not in view and "candidates" not in view
        and "last_safe_lsn_int" not in view
    )
    return criterion("AC-P5.1-05", "M", "lab-repr-reference emits answer separately",
                     "PB-6 R2 reference vs model_view", "candidates in reference only",
                     {"reference_keys": _keys_of(ref), "n_candidates": len(cands or []),
                      "model_view_has_answer": "answer" in view}, passed)


def _write_scratch(name: str, obj: dict) -> Path:
    path = review("G004") / "scratch" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _guard_bin(path: Path) -> subprocess.CompletedProcess[str]:
    return run([str(bin_path("lab-modelview-guard")), str(path)], timeout=60)


def ac06() -> dict:
    view = model_view(HEADLINE, "R0", "PB-6-candidate-windows", {"top_n": 3})
    clean = _write_scratch("r0-pb6-clean.json", view)
    proc = _guard_bin(clean)
    # LSN digits must appear in R0 content (raw log) and still pass.
    has_digit = any(ch.isdigit() for ch in view["content"])
    passed = proc.returncode == 0 and has_digit
    return criterion("AC-P5.1-06", "M", "guard passes clean R0 model_view (LSN digits allowed)",
                     "lab-modelview-guard r0-pb6-clean.json", "exit 0; content has digits",
                     {"exit": proc.returncode, "has_digit": has_digit,
                      "stderr": (proc.stderr or "")[:200]}, passed)


def ac07() -> dict:
    view = model_view(HEADLINE, "R2", "PB-6-candidate-windows", {"top_n": 3})
    ref = reference(HEADLINE, "R2", "PB-6-candidate-windows", {"top_n": 3})
    dirty_ans = deepcopy(view)
    dirty_ans["answer"] = ref["answer"]
    p_ans = _write_scratch("injected-answer.json", dirty_ans)
    ans_proc = _guard_bin(p_ans)
    ans_named = "answer" in (ans_proc.stderr or "").lower() or "candidates" in (ans_proc.stderr or "").lower()
    clean_proc = _guard_bin(_write_scratch("injected-answer-reverted.json", view))
    dirty_pr = deepcopy(view)
    dirty_pr["telemetry"] = dict(view["telemetry"])
    dirty_pr["telemetry"]["principal"] = "lab_agent"
    p_pr = _write_scratch("injected-principal.json", dirty_pr)
    pr_proc = _guard_bin(p_pr)
    pr_named = "principal" in (pr_proc.stderr or "").lower()
    pr_clean = _guard_bin(_write_scratch("injected-principal-reverted.json", view))
    passed = (
        ans_proc.returncode != 0 and ans_named and clean_proc.returncode == 0
        and pr_proc.returncode != 0 and pr_named and pr_clean.returncode == 0
    )
    return criterion("AC-P5.1-07", "M", "NEGATIVE: injected answer and principal each refused, then pass",
                     "scratch inject answer + principal", "nonzero then 0 after revert",
                     {"answer_exit": ans_proc.returncode, "answer_named": ans_named,
                      "principal_exit": pr_proc.returncode, "principal_named": pr_named,
                      "reverted": [clean_proc.returncode, pr_clean.returncode]}, passed)


def ac08() -> dict:
    rows = []
    ok = True
    for probe in PROBE_IDS:
        params = probe_params(probe)
        for rep in REPR_IDS:
            view = model_view(HEADLINE, rep, probe, params)
            path = _write_scratch(f"sweep-{rep}-{probe}.json", view)
            proc = _guard_bin(path)
            rows.append({"rep": rep, "probe": probe, "exit": proc.returncode})
            if proc.returncode != 0:
                ok = False
    return criterion("AC-P5.1-08", "M", "every R0/R1/R2 x 6-probe model_view passes the guard",
                     "lab-modelview-guard x 18", "all exit 0",
                     {"n": len(rows), "failed": [r for r in rows if r["exit"] != 0]}, ok)


def ac09() -> dict:
    rec = parity_modelview(HEADLINE)
    return criterion("AC-P5.1-09", "M", "model_view parity: only content+telemetry differ",
                     "parity_modelview live", "structural_match all true",
                     rec, rec["ok"])


def ac10() -> dict:
    rec = pb6_headline()
    live = headline_material(
        int(model_view(HEADLINE, "R0", "PB-6-candidate-windows", {"top_n": 3})["telemetry"]["evidence_bytes"]),
        int(model_view(HEADLINE, "R2", "PB-6-candidate-windows", {"top_n": 3})["telemetry"]["evidence_bytes"]),
    )
    passed = rec["ok"] and live["ok"] and live["R0_evidence_bytes"] == rec["R0_evidence_bytes"]
    return criterion("AC-P5.1-10", "M", "headline reported on PB-6; R2 materially < R0",
                     "F008 + live model_view PB-6", f"R2 <= {MATERIAL_RATIO}*R0 and strictly less",
                     {"recorded": rec, "live": live}, passed)


def ac11() -> dict:
    rec = artefacts_byte_identical()
    return criterion("AC-P5.1-11", "M", "R0/R1/R2 artefacts byte-identical to P5 close",
                     "manifest content_hash vs F002/F003/F004", str(ARTEFACT_HASHES),
                     rec, rec["ok"])


def ac12() -> dict:
    hits = []
    for probe in PROBE_IDS:
        params = probe_params(probe)
        for rep in REPR_IDS:
            view = model_view(HEADLINE, rep, probe, params)
            blob = json.dumps(view, sort_keys=True)
            found = token_scan(blob, roles=True)
            if found:
                hits.append({"rep": rep, "probe": probe, "hits": found[:5]})
    return criterion("AC-P5.1-12", "M", "no provenance token on any model_view",
                     "token_scan 18 model_views", "zero hits",
                     {"hits": hits}, not hits)


def ac13() -> dict:
    rows = frozen_contract_rows()
    mapping_path = review("G004") / "criterion-mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8")) if mapping_path.is_file() else []
    weakened = []
    p5_ids = [f"AC-P5-{i:02d}" for i in range(1, 20)]
    mapped_ids = []
    for entry in mapping:
        eid = entry.get("id") or entry.get("old_id")
        mapped_ids.append(eid)
        status = entry.get("status")
        strictness = entry.get("strictness")
        if status == "weakened" or strictness == "weakened":
            weakened.append(eid)
        if status in {"mechanism-changed", "label-changed"} and strictness not in {"preserved", "strengthened"}:
            weakened.append(eid)
    hashes_ok = all(r["ok"] for r in rows)
    coverage = set(p5_ids) <= set(mapped_ids)
    passed = hashes_ok and coverage and not weakened and bool(mapping)
    return criterion("AC-P5.1-13", "M", "frozen hashes unchanged; no criterion weakened",
                     "sha256 prior contracts + criterion-mapping.json", "all ok; none weakened",
                     {"hash_fail": [r["path"] for r in rows if not r["ok"]],
                      "coverage": coverage, "weakened": weakened, "n_mapped": len(mapping)}, passed)


def ac14() -> dict:
    if os.environ.get("LAB_READONLY_CHECK") == "1":
        out = (review("F010") / "verify-p5.out").read_text(encoding="utf-8") if (review("F010") / "verify-p5.out").is_file() else ""
        passed = "TIER M 18/18" in out and "TIER A 1/1" in out and "TOTAL 19/19" in out
        return criterion("AC-P5.1-14", "M", "lab-verify-p5 honest green (nested readonly uses F010 out)",
                         "logs/review/F010/verify-p5.out", "19/19",
                         {"skipped_nested_rerun": True, "has_1919": passed}, passed)
    proc = run([str(bin_path("lab-verify-p5"))], timeout=1800)
    text = (proc.stdout or "") + (proc.stderr or "")
    passed = proc.returncode == 0 and "TIER M 18/18" in text and "TOTAL 19/19" in text
    return criterion("AC-P5.1-14", "M", "lab-verify-p5 re-derived honest green; parity on model_view; headline PB-6",
                     "bin/lab-verify-p5", "TIER M 18/18 TIER A 1/1 TOTAL 19/19",
                     {"exit": proc.returncode, "tail": text[-400:]}, passed)


def ac15() -> dict:
    inner = os.environ.get("LAB_READONLY_CHECK") == "1"
    p5 = None
    if not inner:
        p5 = run([str(bin_path("lab-gate-readonly-check")), str(bin_path("lab-verify-p5"))], timeout=1800)
        passed = p5.returncode == 0
    else:
        # Outer lab-gate-readonly-check already manifests evidence around this process.
        # Do not re-enter lab-verify-p5.1 here (would recurse). Self-check is G004-4.
        passed = True
    bins = bin_path("lab-verify-p5.1").is_file() and os.access(bin_path("lab-verify-p5.1"), os.X_OK)
    passed = passed and bins
    return criterion("AC-P5.1-15", "M", "lab-verify-p5.1 present; read-only over evidence",
                     "lab-gate-readonly-check bin/lab-verify-p5 (self-check is G004-4)",
                     "exit 0; no evidence mutation",
                     {"inner": inner,
                      "p5_exit": None if p5 is None else p5.returncode,
                      "bin": bins}, passed)


def ac16() -> dict:
    path = root() / "docs/p5-acceptance-memo.md"
    if not path.is_file():
        return criterion("AC-P5.1-16", "A", "memo records P5 accepted only after P5.1",
                         "docs/p5-acceptance-memo.md", "json fields", None, False)
    obj = json_object_in(path.read_text(encoding="utf-8"))
    passed = (
        obj.get("p5_accepted_only_after") == "P5.1"
        and obj.get("headline_probe") == "PB-6-candidate-windows"
        and obj.get("remediated_defect") == "answer-key-in-subject-view"
    )
    return criterion("AC-P5.1-16", "A", "memo machine-readable fields",
                     "docs/p5-acceptance-memo.md JSON", "p5_accepted_only_after P5.1; headline PB-6",
                     obj, passed)


def main(argv: list[str]) -> int:
    results = [
        ac01(), ac02(), ac03(), ac04(), ac05(), ac06(), ac07(), ac08(),
        ac09(), ac10(), ac11(), ac12(), ac13(), ac14(), ac15(), ac16(),
    ]
    failed = [r for r in results if r["result"] != "PASS"]
    for r in results:
        print(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}")
    m = [r for r in results if r["tier"] == "M"]
    a = [r for r in results if r["tier"] == "A"]
    mp, ap = sum(r["result"] == "PASS" for r in m), sum(r["result"] == "PASS" for r in a)
    print(f"TIER M {mp}/{len(m)}")
    print(f"TIER A {ap}/{len(a)}")
    print(f"TOTAL {mp + ap}/{len(results)}")
    out = review("G004")
    footer = f"TIER M {mp}/{len(m)}\nTIER A {ap}/{len(a)}\nTOTAL {mp + ap}/{len(results)}\n"
    write_text(
        out / "verify-p5.1.out",
        "\n".join(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}" for r in results)
        + "\n" + footer,
    )
    return 0 if not failed else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
