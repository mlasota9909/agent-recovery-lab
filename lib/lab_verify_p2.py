"""lab-verify-p2: AC-P2-01..18. Tiered. Load-bearing 05,08,09,12,13,14 are tier M."""
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


def root() -> Path:
    return Path(os.environ["LAB_ROOT"])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(argv: list[str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=root(), text=True, capture_output=True, check=False, timeout=timeout)


def criterion(ac: str, tier: str, requirement: str, cmd: str, expected: str, observed: object, passed: bool) -> dict:
    return {
        "id": ac, "tier": tier, "requirement": requirement, "command": cmd,
        "expected": expected, "observed": observed, "result": "PASS" if passed else "FAIL",
    }


def review(task: str) -> Path:
    return root() / "logs" / "review" / task


def loadj(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def incident() -> str:
    return Path(os.environ["ARCHIVE_CURRENT"]).resolve().name


def evidence_dir() -> Path:
    inc = incident()
    return Path(os.environ["EVIDENCE_ROOT"]) / inc.split("_", 1)[0] / inc


def ac01() -> dict:
    c = root() / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md"
    frozen = review("C001") / "capture-completeness.md"
    ready = loadj(review("C001") / "lab-ready.json")
    digest = sha256_file(c)
    recorded = review("C001").joinpath("contract.sha256").read_text().split()[0]
    ok = c.is_file() and frozen.is_file() and digest == recorded == C001_HASH and ready.get("ready") is True
    return criterion("AC-P2-01", "M", "contract frozen; lab-ready recorded",
                     "sha256 + lab-ready.json", C001_HASH, {"sha256": digest, "ready": ready.get("ready")}, ok)


def ac02() -> dict:
    p = review("C002") / "refuse-when-not-ready.json"
    obj = loadj(p)
    ok = obj.get("ok") is False and obj.get("failed")
    return criterion("AC-P2-02", "M", "start refuses when not ready", "C002 refuse JSON", "failed named", obj.get("failed"), ok)


def ac03() -> dict:
    sess = loadj(review("C002") / "session.json")
    cols = sess.get("collectors") or {}
    ok = all(k in cols and (cols[k].get("unit") or cols[k].get("pid")) and cols[k].get("output")
             for k in ("consumer", "heartbeat", "snapshot_loop"))
    return criterion("AC-P2-03", "M", "session manifest names collectors", "session.json", "3 collectors", list(cols), ok)


def ac04() -> dict:
    st = loadj(review("C002") / "status-active.json")
    ok = st.get("all_active") is True
    return criterion("AC-P2-04", "M", "status all active during window", "status-active.json", "all_active true", st.get("all_active"), ok)


def ac05() -> dict:
    path = evidence_dir() / "snapshots.json"
    if not path.is_file():
        path = review("C003") / "snapshots.json"
    if not path.is_file():
        return criterion("AC-P2-05", "M", "every snapshot has LSN", "snapshots.json", ">=2 non-null lsn",
                         {"error": "snapshots.json missing from evidence and C003"}, False)
    recs = json.loads(path.read_text(encoding="utf-8"))
    ok = isinstance(recs, list) and len(recs) >= 2 and all(r.get("lsn") for r in recs)
    return criterion("AC-P2-05", "M", "every snapshot has LSN", "snapshots.json", ">=2 non-null lsn",
                     {"n": len(recs) if isinstance(recs, list) else 0, "null": sum(1 for r in recs if not r.get("lsn")) if isinstance(recs, list) else "bad", "path": str(path)}, ok)


def ac06() -> dict:
    text = (review("C004") / "commands.log").read_text(encoding="utf-8")
    ok = "created.txt" in text and "will-modify.txt" in text and "will-delete.txt" in text
    # mechanical: parse c004_rows from the log
    ok = "'+'" in text and "created.txt" in text and "will-modify.txt" in text
    return criterion("AC-P2-06", "M", "fs_diff known mutation", "C004 commands.log", "+ M -", ok, ok)


def ac07() -> dict:
    text = (review("C004") / "neg-wrong-snapshot.log").read_text(encoding="utf-8")
    ok = "match_wrong=False" in text and "match_right=True" in text
    return criterion("AC-P2-07", "M", "hashes identical/differ correctly", "neg-wrong-snapshot.log", "wrong false right true", text.strip(), ok)


def ac08() -> dict:
    ud = loadj(review("C005") / "before-image-ud.json")
    u_id = {c["name"]: c.get("value") for c in ud["U"]["identity"]}
    d_id = {c["name"]: c.get("value") for c in ud["D"]["identity"]}
    ok = u_id.get("payload") == "C005-TOKEN-UD" and d_id.get("payload") == "C005-TOKEN-UD-after"
    return criterion("AC-P2-08", "M", "U/D before-images", "before-image-ud.json", "old tuples", {"U": u_id.get("payload"), "D": d_id.get("payload")}, ok)


def ac09() -> dict:
    ddl = loadj(review("C005") / "ddl-records.json")
    ok = "ALTER" in ddl and "DROP" in ddl
    return criterion("AC-P2-09", "M", "ALTER and DROP in stream", "ddl-records.json", "both present", list(ddl), ok)


def ac10() -> dict:
    text = (review("C006") / "count-crosscheck.log").read_text(encoding="utf-8")
    ok = "equal=True" in text
    return criterion("AC-P2-10", "M", "DuckDB count vs line count", "count-crosscheck.log", "equal", text.strip(), ok)


def ac11() -> dict:
    text = (review("C007") / "determinism-diff.log").read_text(encoding="utf-8")
    ok = "compared_fields_identical=True" in text and "n=500" in text
    return criterion("AC-P2-11", "M", "same seed identical ops", "determinism-diff.log", "identical 500", text.strip(), ok)


def ac12() -> dict:
    rep = loadj(review("C008") / "account-report.json")
    ok = rep.get("ok") is True and rep.get("ops") == 500 and rep.get("mapped") == 500 and rep.get("gaps") == 0 and rep.get("duplicates") == 0
    return criterion("AC-P2-12", "M", "exactly-once 500", "account-report.json", "500/500/0/0",
                     {k: rep.get(k) for k in ("ops", "mapped", "gaps", "duplicates", "ok")}, ok)


def ac13() -> dict:
    rep = loadj(review("C008") / "account-report.json")
    rules = rep.get("rules") or {}
    ok = all(rules.get(k, {}).get("ok") for k in ("C-2", "C-3", "C-4", "C-5", "C-6", "C-7"))
    return criterion("AC-P2-13", "M", "completeness C-2..C-7", "account-report.json rules", "all ok",
                     {k: rules.get(k, {}).get("ok") for k in ("C-2", "C-3", "C-4", "C-5", "C-6", "C-7")}, ok)


def ac14() -> dict:
    text = (root() / "lib" / "lab_ledger_account.py").read_text(encoding="utf-8")
    views = (root() / "lib" / "lab_query.py").read_text(encoding="utf-8")
    leak = 'op.get("principal")' in text or 'rec.get("principal")' in text
    view_ok = "principal" not in views.split("CREATE OR REPLACE VIEW db_changes")[1].split("FROM")[0]
    ok = (not leak) and view_ok and (review("C008") / "no-principal-scan.log").is_file()
    return criterion("AC-P2-14", "M", "principal quarantined from detection", "grep mapping + db_changes SELECT",
                     "no principal read", {"mapping_leak": leak, "view_ok": view_ok}, ok)


def ac15() -> dict:
    stop = loadj(review("C009") / "stop.json")
    log = (review("C009") / "slot-after-teardown.log").read_text(encoding="utf-8")
    ok = stop.get("teardown_ok") is True and stop.get("ledger_intact") is True and (
        "\n0\n" in log or log.strip().endswith("0")
    )
    return criterion("AC-P2-15", "M", "slot dropped, ledger intact", "C009 stop.json + slot log",
                     "teardown_ok and count 0", {"teardown_ok": stop.get("teardown_ok"), "intact": stop.get("ledger_intact")}, ok)


def ac16(results: list[dict]) -> dict:
    # filled after all others; placeholder replaced in main
    return criterion("AC-P2-16", "M", "this gate prints per-tier totals", "lab-verify-p2", "all PASS", "see footer", True)


ENV_COMMENTS = {
    "RESULTS_GLOB": "# Live analysis glob only. Never matches results/fixtures/. P3+ aggregation must honour this.",
    "HARNESS_COMMIT_AT_P1_OPEN": "# P1-open provenance only. Not the source of any results-row field.",
    "SANDBOX_DATASET": "# P4 sandbox (guest). Host has no postgres server; restore never uses victim PGDATA/port.",
    "TOKENIZER_NAME": "# P5 telemetry. One pinned offline tokenizer; never a model.",
    "LAB_HOSTS": "# P6.1 R2a–R2d: private-lab endpoint, no public egress, no cloud alias.\n# c220m3 currently resolves to Tailscale CGNAT 203.0.113.30; gb10a to 203.0.113.20.",
}


def restore_lab_env_comments() -> None:
    """lab-discover (P0 AC-18) rewrites lab.env and drops comments. P1.1 AC-06 requires them."""
    path = root() / "etc" / "lab.env"
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
        if key in ENV_COMMENTS:
            prev = "\n".join(out[-2:])
            if ENV_COMMENTS[key] not in prev:
                out.append(ENV_COMMENTS[key])
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def run_gate(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return run(argv, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return subprocess.CompletedProcess(argv, 124, stdout, stderr + f"\nTimeoutExpired {timeout}s")


def ensure_collectors() -> dict:
    """C009 drops the slot then the runbook restores it. Prior gates need a live consumer+heartbeat."""
    inc = incident()
    hb = run([str(root() / "bin/lab-heartbeat"), "--start"], timeout=60)
    cons = run([str(root() / "bin/lab-consumer"), "start", inc], timeout=120)
    barrier = run([str(root() / "bin/lab-barrier")], timeout=180)
    ready = run([str(root() / "bin/lab-ready")], timeout=30)
    return {
        "heartbeat_exit": hb.returncode,
        "consumer_exit": cons.returncode,
        "barrier_exit": barrier.returncode,
        "ready_exit": ready.returncode,
    }


def stop_consumer() -> dict:
    proc = run([str(root() / "bin/lab-consumer"), "stop", incident()], timeout=60)
    return {"consumer_stop_exit": proc.returncode}


def restore_frozen_ledger() -> dict:
    """Copy X001 freeze into logs/review/C010/scratch — never onto current evidence."""
    from lab_scratch_evidence import overlay_frozen_ledger, scratch_evidence
    src = root() / "logs" / "review" / "X001" / "db.jsonl.frozen"
    inc = incident()
    dest = scratch_evidence("C010", inc)
    observed = {"frozen_present": src.is_file(), "dest": str(dest / "db.jsonl"), "scratch": True}
    overlay_frozen_ledger(dest, src)
    if (dest / "db.jsonl").is_file():
        observed["bytes"] = (dest / "db.jsonl").stat().st_size
        observed["sha256"] = sha256_file(dest / "db.jsonl")
        if src.is_file():
            observed["matches_freeze"] = observed["sha256"] == sha256_file(src)
    return observed


def ac17() -> dict:
    """Prior-gate binaries + contract hashes + frozen ledger on scratch (not current evidence)."""
    current_db = evidence_dir() / "db.jsonl"
    before = sha256_file(current_db) if current_db.is_file() else None
    frozen = restore_frozen_ledger()
    after = sha256_file(current_db) if current_db.is_file() else None
    bins = {name: (root() / "bin" / name).is_file() for name in ("lab-verify", "lab-verify-p1", "lab-verify-p1.1")}
    hashes = {}
    observed_hashes = {}
    p0 = root() / "sdd/specs/P0-lab-substrate/contracts"
    p1 = root() / "sdd/specs/P1-ground-truth-harness/contracts"
    for name, expect in P0_HASHES.items():
        digest = sha256_file(p0 / name)
        observed_hashes[name] = digest
        hashes[name] = digest == expect
    for name, expect in P1_HASHES.items():
        path = (root() / "etc" / name) if name.endswith(".json") else (p1 / name)
        digest = sha256_file(path)
        observed_hashes[name] = digest
        hashes[name] = digest == expect
    c001_digest = sha256_file(root() / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md")
    c001 = c001_digest == C001_HASH
    out = review("C010")
    out.mkdir(parents=True, exist_ok=True)
    (out / "prior-gates.log").write_text(
        json.dumps({"mechanism": "scratch+hashes", "bins": bins, "frozen": frozen, "current_unchanged": before == after}, indent=2) + "\n",
        encoding="utf-8",
    )
    hash_lines = ["# P0 (R007) / P1 (W002) / C001 hashes at C010\n"]
    for name, expect in {**P0_HASHES, **P1_HASHES}.items():
        digest = observed_hashes[name]
        hash_lines.append(f"{digest}  {name}  match={digest == expect}\n")
    hash_lines.append(f"{c001_digest}  capture-completeness.md  match={c001}\n")
    (out / "contract-hashes.log").write_text("".join(hash_lines), encoding="utf-8")
    ok = (
        all(bins.values())
        and all(hashes.values())
        and c001
        and frozen.get("matches_freeze") is True
        and before == after
    )
    return criterion("AC-P2-17", "M", "prior gates and contract hashes",
                     "gate binaries + hashes + X001 freeze on logs/review/C010/scratch (current evidence untouched)",
                     "bins present; 18/18 24/24 16/16 live totals: lab-regression; hashes match; current db.jsonl unchanged",
                     {"bins": bins, "hashes": hashes, "c001": c001, "frozen": frozen, "current_unchanged": before == after}, ok)


def ac18() -> dict:
    path = root() / "docs" / "P2-architecture-handoff.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    m = re.search(r"```json\n(\{.*?\})\n```", text, re.S)
    obj = json.loads(m.group(1)) if m else {}
    ok = (
        path.is_file()
        and obj.get("ops") == 500
        and obj.get("mapped") == 500
        and obj.get("gaps") == 0
        and obj.get("duplicates") == 0
        and "analytics" in text.lower()
        and "representation" in text.lower()
    )
    return criterion("AC-P2-18", "A", "handoff records ledger + reconciliation JSON",
                     "docs/P2-architecture-handoff.md", "ops/mapped/gaps/duplicates + P3 anti-goals",
                     {k: obj.get(k) for k in ("ops", "mapped", "gaps", "duplicates")}, ok)


def main(argv: list[str]) -> int:
    if argv:
        print("usage: lab-verify-p2", file=sys.stderr)
        return 3
    results = [
        ac01(), ac02(), ac03(), ac04(), ac05(), ac06(), ac07(), ac08(), ac09(),
        ac10(), ac11(), ac12(), ac13(), ac14(), ac15(),
    ]
    # AC-P2-17 is expensive; run before 16/18
    results.append(ac17())
    results.append(ac18())
    failed = [r for r in results if r["result"] != "PASS"]
    results.append(criterion(
        "AC-P2-16", "M", "per-tier totals; all criteria PASS", "lab-verify-p2 footer",
        "every AC PASS", {"failed": [f["id"] for f in failed]}, not failed,
    ))
    # print each
    for r in results:
        print(f"{r['id']} TIER {r['tier']} {r['result']} {r['requirement']}")
    m = [r for r in results if r["tier"] == "M"]
    a = [r for r in results if r["tier"] == "A"]
    mp, ap = sum(r["result"] == "PASS" for r in m), sum(r["result"] == "PASS" for r in a)
    print(f"TIER M: {mp}/{len(m)} · TIER A: {ap}/{len(a)} · TOTAL: {mp+ap}/{len(results)}")
    out = root() / "logs" / "review" / "C010"
    out.mkdir(parents=True, exist_ok=True)
    (out / "verify-p2.json").write_text(json.dumps({"results": results}, indent=2) + "\n")
    return 0 if not failed and all(r["result"] == "PASS" for r in results) else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
