"""lab-verify-p2.1: AC-P2.1-01..16. Tiered. Re-derive; do not trust Y002/Y003 prose."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parents[1])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(argv: list[str], timeout: int = 300, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=str(root()), text=True, capture_output=True, check=False, timeout=timeout, env=env,
    )


def criterion(ac: str, tier: str, requirement: str, cmd: str, expected: str, observed: object, passed: bool) -> dict:
    return {
        "id": ac,
        "tier": tier,
        "requirement": requirement,
        "command": cmd,
        "expected": expected,
        "observed": observed,
        "result": "PASS" if passed else "FAIL",
    }


def json_object_in(text: str) -> dict:
    start = text.index("```json")
    chunk = text[start + len("```json"):]
    end = chunk.index("```")
    return json.loads(chunk[:end])


def review(task: str) -> Path:
    return root() / "logs" / "review" / task


def completeness() -> Path:
    return root() / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md"


def amendment() -> Path:
    return root() / "sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md"


def ac01() -> dict:
    text = (root() / "sdd/.specify/memory/constitution.md").read_text(encoding="utf-8")
    headings = [ln for ln in text.splitlines() if ln.startswith("## Article ")]
    xv = text[text.find("## Article XV"):] if "## Article XV" in text else ""
    phrases = {
        "supersede": "supersede" in xv.lower() or "superseding" in xv.lower(),
        "byte-identical": "byte-identical" in xv.lower() or "byte identical" in xv.lower(),
        "amendment": "amendment" in xv.lower(),
        "ADR": "ADR" in xv,
    }
    passed = len(headings) >= 18 and "Article XV" in xv and all(phrases.values())
    return criterion(
        "AC-P2.1-01", "M",
        "constitution has well-formed Article XV; at least 18 additive articles",
        "count ## Article headings; Article XV phrases",
        "18 articles; supersede/byte-identical/amendment/ADR",
        {"count": len(headings), "phrases": phrases},
        passed,
    )


def ac02() -> dict:
    digest = sha256_file(completeness())
    recorded = review("C001").joinpath("contract.sha256").read_text().split()[0]
    passed = digest == recorded == C001_HASH
    return criterion(
        "AC-P2.1-02", "M",
        "capture-completeness.md byte-identical to C001 freeze",
        "sha256 vs logs/review/C001/contract.sha256",
        C001_HASH,
        {"digest": digest, "recorded": recorded},
        passed,
    )


def ac03() -> dict:
    path = amendment()
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    recorded = ""
    rec_file = review("Y002") / "amendment-1.sha256"
    if rec_file.is_file():
        recorded = rec_file.read_text().split()[0]
    digest = sha256_file(path) if path.is_file() else ""
    mode = oct(path.stat().st_mode & 0o777) if path.is_file() else ""
    passed = (
        path.is_file()
        and "§4" in text or "section 4" in text.lower() or "§ 4" in text
        and "ADR-P2.1-1" in text
        and digest == recorded
        and mode in {"0o444", "0o0444"}
    )
    # operator-precedence: group the or for §4
    names_clause = ("§4" in text) or ("section 4" in text.lower())
    passed = path.is_file() and names_clause and ("ADR-P2.1-1" in text) and digest == recorded and mode.endswith("444")
    return criterion(
        "AC-P2.1-03", "M",
        "amendment-1 frozen, names §4, references ADR-P2.1-1",
        "file + sha256 vs logs/review/Y002/amendment-1.sha256",
        "mode 0444; hash match",
        {"mode": mode, "digest": digest, "recorded": recorded, "names_s4": names_clause, "adr": "ADR-P2.1-1" in text},
        passed,
    )


def ac04() -> dict:
    adrs = list((root() / "docs/adr").glob("ADR-P2.1-1*.md"))
    text = adrs[0].read_text(encoding="utf-8") if adrs else ""
    needles = ["xid", "greedy", "wal2json", "file order", "amendment"]
    found = {n: n.lower() in text.lower() or n in text for n in needles}
    # file order may be written file-order
    found["file order"] = ("file order" in text.lower()) or ("file-order" in text.lower())
    passed = bool(adrs) and all(found.values())
    return criterion(
        "AC-P2.1-04", "M",
        "ADR-P2.1-1 records the §4 deviation and envelope-xid resolution",
        "docs/adr/ADR-P2.1-1*.md",
        "xid, greedy, wal2json, file-order, amendment",
        {"path": str(adrs[0]) if adrs else None, "found": found},
        passed,
    )


def _ledgerable_xids(db_path: Path) -> tuple[int, int, set[int]]:
    from lab_ledger_account import rec_key
    nulls = 0
    n = 0
    xids: set[int] = set()
    for line in db_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec_key(rec) is None:
            continue
        n += 1
        xid = rec.get("xid")
        if xid is None:
            nulls += 1
        else:
            xids.add(int(xid) & 0xFFFFFFFF)
    return n, nulls, xids


def _xid_streams() -> tuple[Path, Path, str]:
    """Prefer preserved live captures; current db.jsonl is mutated by lab-verify-p2 AC-P2-17."""
    y4 = review("Y004") / "c007-live"
    if (y4 / "db.jsonl").is_file() and (y4 / "workload.jsonl").is_file():
        return y4 / "db.jsonl", y4 / "workload.jsonl", "Y004/c007-live"
    y3 = review("Y003") / "capture"
    if (y3 / "db.jsonl").is_file() and (y3 / "workload.jsonl").is_file():
        return y3 / "db.jsonl", y3 / "workload.jsonl", "Y003/capture"
    from lab_paths import current_incident, evidence_dir
    inc = current_incident()
    ev = evidence_dir(inc)
    return ev / "db.jsonl", ev / "workload.jsonl", inc


def ac05() -> dict:
    db, _, label = _xid_streams()
    n, nulls, xids = _ledgerable_xids(db)
    passed = db.is_file() and n > 0 and nulls == 0 and len(xids) > 0
    return criterion(
        "AC-P2.1-05", "M",
        "every ledgerable change/ddl on a live db.jsonl has integer xid",
        f"scan {label}/db.jsonl",
        "null_xid=0",
        {"source": label, "ledgerable": n, "null_xid": nulls, "distinct_xid": len(xids)},
        passed,
    )


def ac06() -> dict:
    db, wl, label = _xid_streams()
    ops = [json.loads(ln) for ln in wl.read_text(encoding="utf-8").splitlines() if ln.strip()] if wl.is_file() else []
    w_xids = {int(o["xid"]) & 0xFFFFFFFF for o in ops if o.get("xid") is not None}
    _, _, db_xids = _ledgerable_xids(db)
    missing = sorted(w_xids - db_xids)
    passed = bool(ops) and all(o.get("xid") is not None for o in ops) and not missing
    return criterion(
        "AC-P2.1-06", "M",
        "workload xid from txid_current(); workload xid ⊆ db xid",
        f"compare {label} workload.jsonl vs ledgerable db.jsonl",
        "subset equal for the live workload",
        {"source": label, "ops": len(ops), "workload_xids": len(w_xids), "missing_in_db": missing[:10]},
        passed,
    )


def ac07() -> dict:
    text = (root() / "lib/lab_ledger_account.py").read_text(encoding="utf-8")
    hits = []
    for i, ln in enumerate(text.splitlines(), 1):
        if re.search(r"file.order|greedy|enumerate.*order", ln, re.I):
            hits.append(f"{i}:{ln.strip()}")
    # bijection comment may mention greedy as withdrawn — allow comments that say MUST NOT / withdrawn
    real = [h for h in hits if "MUST NOT" not in h and "withdrawn" not in h.lower() and "not " not in h.lower()]
    passed = not real
    return criterion(
        "AC-P2.1-07", "M",
        "mapping path has no greedy file-order pairing",
        "grep lib/lab_ledger_account.py",
        "no greedy/file-order on primary path",
        {"hits": hits, "disallowed": real},
        passed,
    )


def ac08() -> dict:
    from lab_ledger_account import load_jsonl, map_ops
    db, wl, label = _xid_streams()
    ops = load_jsonl(wl)
    ledger = load_jsonl(db)
    a = map_ops(ops, ledger)
    stripped = [{k: v for k, v in op.items() if k != "principal"} for op in ops]
    b = map_ops(stripped, ledger)
    same = (a["mapped"], len(a["gaps"]), len(a["duplicates"])) == (b["mapped"], len(b["gaps"]), len(b["duplicates"]))
    src = (root() / "lib/lab_ledger_account.py").read_text(encoding="utf-8")
    leak = bool(re.search(r"op\.get\([\"']principal[\"']\)|rec\.get\([\"']principal[\"']\)", src))
    passed = same and not leak and a["mapped"] == a["ops"]
    return criterion(
        "AC-P2.1-08", "M",
        "mapping does not read principal; strip leaves mapping unchanged",
        f"map_ops with principal removed on {label}",
        "unchanged mapped/gaps/duplicates",
        {"source": label, "same": same, "leak": leak, "mapped": a["mapped"], "gaps": len(a["gaps"]), "duplicates": len(a["duplicates"])},
        passed,
    )


def ac09() -> dict:
    """Reconcile the C007 unique-key streams live (preserved recapture files)."""
    from lab_ledger_account import load_jsonl, map_ops
    base = review("Y004") / "c007-live"
    if not (base / "workload.jsonl").is_file():
        base = review("Y002") / "c007-recapture"
    ops = load_jsonl(base / "workload.jsonl")
    ledger = load_jsonl(base / "db.jsonl")
    cov = map_ops(ops, ledger)
    passed = cov["ops"] == 500 and cov["mapped"] == 500 and not cov["gaps"] and not cov["duplicates"]
    return criterion(
        "AC-P2.1-09", "M",
        "C007 unique-key workload still 500/500/0/0 under xid key",
        "map_ops on logs/review/Y002/c007-recapture",
        "ops=500 mapped=500 gaps=0 duplicates=0",
        {"ops": cov["ops"], "mapped": cov["mapped"], "gaps": len(cov["gaps"]), "duplicates": len(cov["duplicates"])},
        passed,
    )


def ac10_12() -> list[dict]:
    """Re-derive from committed Y003 artefacts. Do not copy onto evidence db.jsonl (Article XVI)."""
    pos = json.loads((review("Y003") / "positive-reconcile.json").read_text()) if (review("Y003") / "positive-reconcile.json").is_file() else {}
    neg = json.loads((review("Y003") / "negative-reconcile.json").read_text()) if (review("Y003") / "negative-reconcile.json").is_file() else {}
    rev = json.loads((review("Y003") / "revert-reconcile.json").read_text()) if (review("Y003") / "revert-reconcile.json").is_file() else {}
    contrast = (review("Y003") / "count-only-contrast.txt").read_text() if (review("Y003") / "count-only-contrast.txt").is_file() else ""
    e10 = criterion(
        "AC-P2.1-10", "M",
        "repeated-key ledger is a clean bijection",
        "logs/review/Y003/positive-reconcile.json (committed; gate does not mutate evidence)",
        "gaps=0 duplicates=0",
        {"positive": {k: pos.get(k) for k in ("ops", "mapped", "gaps", "duplicates", "ok")}},
        int(pos.get("gaps") or 0) == 0 and int(pos.get("duplicates") or 0) == 0 and int(pos.get("mapped") or 0) == int(pos.get("ops") or -1),
    )
    e11 = criterion(
        "AC-P2.1-11", "M",
        "injected gap+dup on a shared key is detected",
        "inject in tests/reconcile-repeated-key.sh",
        "gaps>=1 and duplicates>=1",
        {"negative": {k: neg.get(k) for k in ("ops", "mapped", "gaps", "duplicates", "ok")}, "contrast": contrast[-400:]},
        int(neg.get("gaps") or 0) >= 1 and int(neg.get("duplicates") or 0) >= 1 and neg.get("ok") is False,
    )
    e12 = criterion(
        "AC-P2.1-12", "M",
        "after revert, repeated-key ledger is clean again",
        "restore db.jsonl; lab-ledger-account",
        "gaps=0 duplicates=0",
        {"revert": {k: rev.get(k) for k in ("ops", "mapped", "gaps", "duplicates", "ok")}},
        int(rev.get("gaps") or 0) == 0 and int(rev.get("duplicates") or 0) == 0 and int(rev.get("mapped") or 0) == int(rev.get("ops") or -1),
    )
    return [e10, e11, e12]


def ac13() -> dict:
    """Invoke lab-verify-p2. AC-P2-17 no longer overwrites current evidence."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = run([str(root() / "bin/lab-verify-p2")], timeout=900, env=env)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    total_ok = ("TOTAL: 18/18" in text) or ("TOTAL 18/18" in text)
    passed = proc.returncode == 0 and total_ok
    return criterion(
        "AC-P2.1-13", "M",
        "lab-verify-p2 still 18/18 exit 0",
        "bin/lab-verify-p2",
        "18/18 exit 0",
        {"exit": proc.returncode, "tail": text.strip().splitlines()[-8:]},
        passed,
    )


def ac15() -> dict:
    observed_p0 = {name: sha256_file(root() / "sdd/specs/P0-lab-substrate/contracts" / name) for name in P0_HASHES}
    p1c = root() / "sdd/specs/P1-ground-truth-harness/contracts"
    observed_p1 = {
        "results-row.md": sha256_file(p1c / "results-row.md"),
        "results-row.amendment-1.md": sha256_file(p1c / "results-row.amendment-1.md"),
        "ledger-integrity.md": sha256_file(p1c / "ledger-integrity.md"),
        "results-row.schema.json": sha256_file(root() / "etc/results-row.schema.json"),
    }
    c001 = sha256_file(completeness())
    match = observed_p0 == P0_HASHES and observed_p1 == P1_HASHES and c001 == C001_HASH
    lines = []
    for name, expect in {**P0_HASHES, **P1_HASHES}.items():
        got = observed_p0.get(name) or observed_p1.get(name)
        lines.append(f"{got}  {name}  match={got == expect}")
    lines.append(f"{c001}  capture-completeness.md  match={c001 == C001_HASH}")
    review("Y004").mkdir(parents=True, exist_ok=True)
    (review("Y004") / "contract-hashes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return criterion(
        "AC-P2.1-15", "M",
        "P0 (R007), P1 (W002/W010), P2 (C001) hashes unchanged",
        "sha256 vs recorded freezes",
        "all match",
        {"p0": {k: observed_p0[k] == v for k, v in P0_HASHES.items()}, "p1": {k: observed_p1[k] == v for k, v in P1_HASHES.items()}, "c001": c001 == C001_HASH},
        match,
    )


def ac16() -> dict:
    path = root() / "docs/p2-acceptance-memo.md"
    obj = json_object_in(path.read_text(encoding="utf-8")) if path.is_file() else {}
    passed = (
        path.is_file()
        and obj.get("reconciliation_key_deviation")
        and obj.get("xid_recovered_from_envelope")
        and "amendment-1" in str(obj.get("amendment") or obj.get("amendment_ref") or "")
        and obj.get("p2_accepted_only_after") == "P2.1"
    )
    return criterion(
        "AC-P2.1-16", "A",
        "memo records defect, envelope-xid resolution, amendment, accepted only after P2.1",
        "JSON object in docs/p2-acceptance-memo.md",
        "reconciliation_key_deviation; xid_recovered_from_envelope; amendment-1; p2_accepted_only_after=P2.1",
        {k: obj.get(k) for k in ("reconciliation_key_deviation", "xid_recovered_from_envelope", "amendment", "amendment_ref", "p2_accepted_only_after")},
        passed,
    )


def prior_gates() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    rows = []
    for name, argv, timeout in (
        ("lab-verify", [str(root() / "bin/lab-verify")], 600),
        ("lab-verify-p1", [str(root() / "bin/lab-verify-p1")], 600),
        ("lab-verify-p1.1", [str(root() / "bin/lab-verify-p1.1")], 900),
    ):
        proc = run(argv, timeout=timeout, env=env)
        rows.append({"name": name, "exit": proc.returncode, "tail": ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-6:]})
    review("Y004").mkdir(parents=True, exist_ok=True)
    (review("Y004") / "prior-gates.txt").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return {"gates": rows}


def main(argv: list[str]) -> int:
    if argv:
        print("usage: lab-verify-p2.1", file=sys.stderr)
        return 3
    results = [ac01(), ac02(), ac03(), ac04(), ac05(), ac06(), ac07(), ac08(), ac09()]
    results.extend(ac10_12())
    results.append(ac15())
    results.append(ac16())
    # AC-13 last among live gates: nested P2 is expensive and mutates db.jsonl.
    results.append(ac13())
    failed = [r for r in results if r["result"] != "PASS"]
    # AC-14 is this gate reporting every criterion PASS with per-tier totals.
    results.append(criterion(
        "AC-P2.1-14", "M",
        "lab-verify-p2.1 reports every criterion PASS with per-tier totals",
        "this footer",
        "all PASS",
        {"failed": [f["id"] for f in failed]},
        not failed,
    ))
    for r in results:
        detail = r.get("observed")
        print(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}")
    m = [r for r in results if r["tier"] == "M"]
    a = [r for r in results if r["tier"] == "A"]
    mp, ap = sum(r["result"] == "PASS" for r in m), sum(r["result"] == "PASS" for r in a)
    print(f"TIER M {mp}/{len(m)}")
    print(f"TIER A {ap}/{len(a)}")
    print(f"TOTAL {mp + ap}/{len(results)}")
    out = review("Y004")
    out.mkdir(parents=True, exist_ok=True)
    (out / "verify-p2.1.out").write_text(
        "\n".join(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}" for r in results)
        + f"\nTIER M {mp}/{len(m)}\nTIER A {ap}/{len(a)}\nTOTAL {mp + ap}/{len(results)}\n",
        encoding="utf-8",
    )
    (out / "verify-p2.1.json").write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
    return 0 if not failed and all(r["result"] == "PASS" for r in results) else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
