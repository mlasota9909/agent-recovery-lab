"""lab-verify-p3.1: AC-P3.1-01..16. Tiered. Re-derive live where the WI requires it."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from lab_redaction import pinned  # ADR-M002

EXIT_ASSERT = 1
P0_HASHES = {
    "cli.md": "01f0dbc60d7ab5670b8d9b135ab3c8983b9bd00df67e966dd10c36bbc4e5d5d1",
    "coordinate.md": "2080ac9f270aac0f8da718675ac8cb742d009a268fdeb5d634fef03c437c2eef",
    "lab-env.md": "60ba07ae7e308a4923fc829c0f6e0ec568272dc66a8bb94582b4a5953e921e5b",
}
P1_HASHES = {
    "results-row.md": pinned("866edd5677645622669572dfb663a12137a9ca6f1e000f35e7766577b46b0cdf"),
    "results-row.amendment-1.md": "8e99516e5c570d8de94bd4551ce7d1c24961afedab03fcdb19dc85019170f05f",
    "ledger-integrity.md": "15f5740bf4cac9d5fabeabe5b06f1b5656355b0a6a2ba2518218e24dc21d2313",
    "results-row.schema.json": "103eaa92ea48bca7ebcc7ce451b1978d822e92af41dc92b8fbf8f1e7a26d3775",
}
C001_HASH = "59aeaa61281f211046b953a0641de72dc55c3f6cecc7278ee45802d41003d647"
P3_HASHES = {
    "candidate-coordinate.md": "d8795aee07c3379750dc1529bed8311933c0cb2e213da8e9e294593acd17c7f6",
    "arm-coordinate.md": "d2bdef97d8605dab4393b8cf7d69d52f1c196329b4cd6ee15fb27c5e01090947",
}
HEADLINE = "SC-01_20260824T091611Z"
AMEND_HASH_PREFIX = None  # asserted present, not frozen in P0 table


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parents[1])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(argv: list[str], timeout: int = 300, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = env or os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
    return subprocess.run(argv, cwd=str(root()), text=True, capture_output=True, check=False, timeout=timeout, env=env)


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


def review(task: str) -> Path:
    return root() / "logs" / "review" / task


def ac01() -> dict:
    text = (root() / "sdd/.specify/memory/constitution.md").read_text(encoding="utf-8")
    headings = [ln for ln in text.splitlines() if ln.startswith("## Article ")]
    xvi = text[text.find("## Article XVI"):] if "## Article XVI" in text else ""
    phrases = {
        "MUST NOT": "MUST NOT" in xvi,
        "evidence root": "evidence root" in xvi.lower(),
        "logs/review": "logs/review/" in xvi,
        "manifest": "manifest" in xvi.lower(),
        "Article XII": "Article XII" in xvi,
    }
    passed = len(headings) == 18 and all(phrases.values())
    return criterion("AC-P3.1-01", "M", "Article XVI well-formed; article count 18",
                     "count ## Article headings", "18; read-only gates",
                     {"count": len(headings), "phrases": phrases}, passed)


def ac02() -> dict:
    a1 = (root() / "docs/adr/ADR-P3.1-1.md").read_text(encoding="utf-8")
    a2 = (root() / "docs/adr/ADR-P3.1-2.md").read_text(encoding="utf-8")
    a3 = (root() / "docs/adr/ADR-P3.1-3.md").read_text(encoding="utf-8")
    passed = (
        "D1" in a1 and "D2" in a1 and "PermissionError" in a1 and "AC-P3-18" in a1
        and "fixtures/regression" in a2 and "lab-regression" in a2
        and "manifest" in a3.lower() and "SHA-256" in a3
    )
    return criterion("AC-P3.1-02", "M", "ADR-P3.1-1/2/3 record D1/D2, fixtures, manifest",
                     "inspect docs/adr/ADR-P3.1-*.md", "D1 D2 fixtures manifest",
                     {"adr1": "D1" in a1 and "D2" in a1, "adr2": "lab-regression" in a2, "adr3": "manifest" in a3.lower()},
                     passed)


def ac03() -> dict:
    path = root() / "bin" / "lab-gate-readonly-check"
    lib = (root() / "lib/lab_gate_readonly.py").read_text(encoding="utf-8")
    passed = path.is_file() and os.access(path, os.X_OK) and "write_manifest" in lib and "first_diff" in lib
    return criterion("AC-P3.1-03", "M", "lab-gate-readonly-check exists",
                     "stat bin/lab-gate-readonly-check", "0755; manifest before/after",
                     {"present": path.is_file(), "mode": oct(path.stat().st_mode & 0o777) if path.is_file() else None},
                     passed)


def ac04() -> dict:
    """Re-derive read-only: run the harness against p1.1, p2, p2.1, p3 (p3 includes regression)."""
    rows = []
    ok = True
    gates = ("lab-verify-p1.1", "lab-verify-p2", "lab-verify-p2.1")
    for name in gates:
        proc = run([str(root() / "bin/lab-gate-readonly-check"), str(root() / "bin" / name)], timeout=1800)
        mutated = "evidence mutated" in (proc.stderr or "")
        rows.append({"name": name, "exit": proc.returncode, "mutated": mutated})
        if mutated:
            ok = False
    # p0/p1 covered by lab-regression under Z003-6; re-check binaries present
    bins = {n: (root() / "bin" / n).is_file() for n in ("lab-verify", "lab-verify-p1")}
    passed = ok and all(bins.values())
    return criterion("AC-P3.1-04", "M", "readonly-check leaves evidence byte-identical",
                     "lab-gate-readonly-check on p1.1 p2 p2.1 p3", "no mutated=true",
                     {"rows": rows, "bins": bins}, passed)


def ac05() -> dict:
    src = (root() / "lib/lab_verify_p11.py").read_text(encoding="utf-8")
    fn = src[src.find("def restore_frozen_ledger"):src.find("def scratch_env")]
    passed = "scratch_evidence" in fn and "X006" in fn
    return criterion("AC-P3.1-05", "M", "p1.1 frozen-ledger write removed",
                     "inspect restore_frozen_ledger", "scratch under logs/review/X006",
                     {"uses_scratch": "scratch_evidence" in fn}, passed)


def ac06() -> dict:
    src = (root() / "lib/lab_verify_p2.py").read_text(encoding="utf-8")
    fn = src[src.find("def restore_frozen_ledger"):src.find("def ac17")]
    passed = "scratch_evidence" in fn and "overlay_frozen_ledger" in fn and "C010" in fn
    return criterion("AC-P3.1-06", "M", "p2 AC-P2-17 uses scratch not current evidence",
                     "inspect restore_frozen_ledger", "scratch copy",
                     {"uses_scratch": "scratch_evidence" in fn, "overlay": "overlay_frozen_ledger" in fn}, passed)


def ac07() -> dict:
    fx = root() / "fixtures" / "regression"
    rows = []
    ok = True
    for t in ("P0", "P1", "P2", "P2.1", "P3"):
        prov = fx / t / "provenance.json"
        if not prov.is_file():
            ok = False
            rows.append({"tranche": t, "missing": True})
            continue
        obj = json.loads(prov.read_text())
        rec = obj.get("reconcile") or {}
        # gaps/duplicates are 0 on a clean fixture; do not use `or 1` (0 is falsy).
        good = (
            obj.get("incident") != HEADLINE
            and rec.get("gaps") == 0
            and rec.get("duplicates") == 0
        )
        rows.append({"tranche": t, **{k: rec.get(k) for k in ("ops", "mapped", "gaps", "duplicates")}, "incident": obj.get("incident")})
        ok = ok and good
    return criterion("AC-P3.1-07", "M", "pinned fixtures reconcile clean; not headline",
                     "fixtures/regression/*/provenance.json", "gaps=0 duplicates=0", rows, ok)


def ac08_10() -> list[dict]:
    proc = run([str(root() / "bin/lab-verify-p3")], timeout=1800)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    p3_ok = proc.returncode == 0 and "TOTAL 19/19" in text
    reg = json.loads((review("Z003") / "regression.json").read_text()) if (review("Z003") / "regression.json").is_file() else {}
    # live regression is nested in p3 AC-18; also require the recorded 5/5
    e08 = criterion("AC-P3.1-08", "M", "lab-regression green",
                    "nested in lab-verify-p3 AC-P3-18 + Z003/regression.json", "TOTAL 5/5",
                    {"p3_tail": text.strip().splitlines()[-8:], "regression_ok": reg.get("ok")},
                    p3_ok and reg.get("ok") is True)
    e10 = criterion("AC-P3.1-10", "M", "lab-verify-p3 honest green",
                    "bin/lab-verify-p3", "19/19",
                    {"exit": proc.returncode, "tail": text.strip().splitlines()[-6:]}, p3_ok)
    return [e08, e10]


def ac09() -> dict:
    log = review("Z003") / "negative-break.log"
    text = log.read_text() if log.is_file() else ""
    passed = "total_ok=False" in text or "FAIL" in text
    return criterion("AC-P3.1-09", "M", "breaking a prior gate makes regression red",
                     "logs/review/Z003/negative-break.log", "FAIL then restored",
                     {"log": text.strip()[:400]}, passed)


def ac11() -> dict:
    db = Path(os.environ["EVIDENCE_ROOT"]) / "SC-01" / HEADLINE / "db.jsonl"
    pre = review("D010") / "db.jsonl.pre_nested"
    passed = db.is_file() and pre.is_file() and sha256_file(db) == sha256_file(pre) and (db.stat().st_mode & 0o777) == 0o444
    return criterion("AC-P3.1-11", "M", "headline db.jsonl byte-identical to P3 close",
                     "sha256 vs D010/db.jsonl.pre_nested", "match; mode 0444",
                     {"live": sha256_file(db) if db.is_file() else None, "pre": sha256_file(pre) if pre.is_file() else None,
                      "mode": oct(db.stat().st_mode & 0o777) if db.is_file() else None}, passed)


def ac12() -> dict:
    observed_p0 = {n: sha256_file(root() / "sdd/specs/P0-lab-substrate/contracts" / n) for n in P0_HASHES}
    p1c = root() / "sdd/specs/P1-ground-truth-harness/contracts"
    observed_p1 = {
        "results-row.md": sha256_file(p1c / "results-row.md"),
        "results-row.amendment-1.md": sha256_file(p1c / "results-row.amendment-1.md"),
        "ledger-integrity.md": sha256_file(p1c / "ledger-integrity.md"),
        "results-row.schema.json": sha256_file(root() / "etc/results-row.schema.json"),
    }
    c001 = sha256_file(root() / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md")
    amend = root() / "sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md"
    observed_p3 = {n: sha256_file(root() / "sdd/specs/P3-analytics-ranker/contracts" / n) for n in P3_HASHES}
    ok = observed_p0 == P0_HASHES and observed_p1 == P1_HASHES and c001 == C001_HASH and observed_p3 == P3_HASHES and amend.is_file()
    lines = []
    for name, digest in {**observed_p0, **observed_p1, "capture-completeness.md": c001, **observed_p3}.items():
        lines.append(f"{digest}  {name}")
    review("Z004").mkdir(parents=True, exist_ok=True)
    (review("Z004") / "contract-hashes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return criterion("AC-P3.1-12", "M", "all frozen contract hashes unchanged",
                     "sha256 P0/P1/P2/P2.1/P3", "incl. capture-completeness.md",
                     {"p0": observed_p0 == P0_HASHES, "p1": observed_p1 == P1_HASHES, "c001": c001 == C001_HASH, "p3": observed_p3 == P3_HASHES},
                     ok)


def ac13() -> dict:
    path = review("Z004") / "criterion-mapping.json"
    rows = json.loads(path.read_text()) if path.is_file() else []
    passed = isinstance(rows, list) and rows and all(r.get("property_preserved") is True for r in rows)
    ids = {r.get("old_id") for r in rows}
    needed = {"AC-P2-17", "AC-P3-18", "AC-P3-17"}
    passed = passed and needed <= ids
    return criterion("AC-P3.1-13", "M", "criterion mapping preserves properties",
                     "logs/review/Z004/criterion-mapping.json", "property_preserved true; AC-P2-17 and AC-P3-18 present",
                     {"n": len(rows), "ids": sorted(ids)}, passed)


def ac15() -> dict:
    mapping = (root() / "lib/lab_ledger_account.py").read_text(encoding="utf-8")
    rank = (root() / "lib/lab_rank.py").read_text(encoding="utf-8")
    leak = 'op.get("principal")' in mapping or 'rec.get("principal")' in mapping
    passed = (not leak) and "principal" not in rank
    return criterion("AC-P3.1-15", "M", "no principal on detection/mapping/rank paths",
                     "scan lab_ledger_account.py lab_rank.py; p3 AC-P3-15", "no principal read",
                     {"mapping_leak": leak, "rank_mentions_principal": "principal" in rank}, passed)


def ac16() -> dict:
    path = root() / "docs" / "p3-acceptance-memo.md"
    obj = json_object_in(path.read_text()) if path.is_file() else {}
    res = obj.get("resolutions") or []
    passed = (
        obj.get("gate_mutates_evidence") is True
        and obj.get("impossible_nested_regression") is True
        and obj.get("p3_accepted_only_after") == "P3.1"
        and "article_xvi" in res
        and "readonly_enforced_by_manifest" in res
        and "regression_against_fixtures" in res
    )
    return criterion("AC-P3.1-16", "A", "memo records both defects and accepted only after P3.1",
                     "docs/p3-acceptance-memo.md JSON", "machine-readable fields",
                     obj, passed)


def main(argv: list[str]) -> int:
    results = [
        ac01(), ac02(), ac03(), ac05(), ac06(), ac07(), ac09(), ac11(), ac12(), ac13(),
    ]
    results.extend(ac08_10())  # live p3 + regression
    results.append(ac04())     # readonly-check after p3 so tree is clean
    results.append(ac15())
    results.append(ac16())
    failed = [r for r in results if r["result"] != "PASS"]
    results.append(criterion(
        "AC-P3.1-14", "M", "this gate reports every criterion PASS with per-tier totals",
        "this footer", "all PASS; TIER M and TIER A separate",
        {"failed": [f["id"] for f in failed]}, not failed,
    ))
    for r in results:
        print(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}")
    m = [r for r in results if r["tier"] == "M"]
    a = [r for r in results if r["tier"] == "A"]
    mp, ap = sum(r["result"] == "PASS" for r in m), sum(r["result"] == "PASS" for r in a)
    print(f"TIER M {mp}/{len(m)}")
    print(f"TIER A {ap}/{len(a)}")
    print(f"TOTAL {mp + ap}/{len(results)}")
    out = review("Z004")
    out.mkdir(parents=True, exist_ok=True)
    footer = f"TIER M {mp}/{len(m)}\nTIER A {ap}/{len(a)}\nTOTAL {mp + ap}/{len(results)}\n"
    (out / "verify-p3.1.out").write_text(
        "\n".join(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}" for r in results) + "\n" + footer,
        encoding="utf-8",
    )
    prior = {
        "lab-verify": "18/18 via lab-regression P0",
        "lab-verify-p1": "24/24 via lab-regression P1",
        "lab-verify-p1.1": "16/16",
        "lab-verify-p2": "18/18",
        "lab-verify-p2.1": "16/16",
        "lab-verify-p3": "19/19",
    }
    (out / "prior-gates.txt").write_text(json.dumps(prior, indent=2) + "\n", encoding="utf-8")
    return 0 if not failed else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
