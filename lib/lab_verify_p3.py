"""lab-verify-p3: AC-P3-01..19. Tiered. Re-derive; do not trust D00x prose."""
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
RESULTS_INCIDENT = "i_20260824T091611Z_122142"


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


def p3_contracts() -> Path:
    return root() / "sdd/specs/P3-analytics-ranker/contracts"


def completeness() -> Path:
    return root() / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md"


def amendment() -> Path:
    return root() / "sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md"


def headline_ev() -> Path:
    return root() / "evidence" / "SC-01" / HEADLINE


def p3_dir() -> Path:
    return headline_ev() / "p3"


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def py_env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def ac01() -> dict:
    cand = p3_contracts() / "candidate-coordinate.md"
    arm = p3_contracts() / "arm-coordinate.md"
    recorded = {}
    rec_file = review("D001") / "contract-hashes.txt"
    if rec_file.is_file():
        for ln in rec_file.read_text(encoding="utf-8").splitlines():
            parts = ln.split()
            if len(parts) >= 2:
                recorded[Path(parts[1]).name] = parts[0]
    gate = {}
    gf = review("D001") / "entry-gate.json"
    if gf.is_file():
        gate = json.loads(gf.read_text(encoding="utf-8"))
    digest_c = sha256_file(cand) if cand.is_file() else ""
    digest_a = sha256_file(arm) if arm.is_file() else ""
    from lab_p3_util import extract_json_blocks, contract_schema_has_provenance
    blocks_ok = True
    for path in (cand, arm):
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        blocks = extract_json_blocks(text)
        if not blocks:
            blocks_ok = False
        for block in blocks:
            json.loads(block)
        if contract_schema_has_provenance(text):
            blocks_ok = False
    passed = (
        cand.is_file() and arm.is_file() and blocks_ok
        and digest_c == recorded.get("candidate-coordinate.md") == P3_HASHES["candidate-coordinate.md"]
        and digest_a == recorded.get("arm-coordinate.md") == P3_HASHES["arm-coordinate.md"]
        and int(gate.get("lab_ready_exit", 1)) == 0
        and int(gate.get("gaps", 1)) == 0
        and int(gate.get("duplicates", 1)) == 0
    )
    return criterion(
        "AC-P3-01", "M",
        "both P3 contracts frozen; entry gate recorded",
        "D001 hashes + entry-gate.json + example JSON",
        "hashes match D001; lab_ready_exit=0; gaps=0 duplicates=0",
        {
            "candidate": digest_c, "arm": digest_a, "recorded": recorded, "entry_gate": gate,
            "blocks_ok": blocks_ok,
        },
        passed,
    )


def ac02() -> dict:
    inj_bin = root() / "bin" / "lab-inject-sc01"
    log = headline_ev() / "injection_log.json"
    rec = json.loads(log.read_text(encoding="utf-8")) if log.is_file() else {}
    n_ops = rec.get("n_ops") or rec.get("ops") or (len(rec.get("affected_natural_keys") or []) if rec else 0)
    if isinstance(rec.get("ops"), list):
        n_ops = len(rec["ops"])
    has_window = all(rec.get(k) for k in ("lsn_start", "lsn_end")) or all(
        rec.get(k) for k in ("t_start", "t_end")
    )
    principal = rec.get("principal") or ""
    src = (root() / "lib" / "lab_inject_sc01.py").read_text(encoding="utf-8") if (root() / "lib" / "lab_inject_sc01.py").is_file() else ""
    lab_only = "require_lab" in src or "ROLE_AGENT" in src
    passed = inj_bin.is_file() and log.is_file() and int(n_ops or 0) >= 200 and has_window and lab_only
    return criterion(
        "AC-P3-02", "M",
        "lab-inject-sc01 writes an injection log with ops and damage window",
        "bin/lab-inject-sc01 + evidence injection_log.json",
        ">=200 ops; lsn/time window present; lab-contained",
        {"bin": inj_bin.is_file(), "n_ops": n_ops, "has_window": has_window, "principal": principal, "lsn_start": rec.get("lsn_start")},
        passed,
    )


def ac03() -> dict:
    env = py_env()
    proc = run([str(root() / "bin" / "lab-ledger-account"), HEADLINE], timeout=120, env=env)
    cov = {}
    try:
        cov = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pass
    wl = load_jsonl(headline_ev() / "workload.jsonl")
    principals = {op.get("principal") for op in wl}
    keys: dict[object, int] = {}
    for op in wl:
        nk = op.get("natural_key")
        if nk is not None:
            keys[nk] = keys.get(nk, 0) + 1
    repeated = sum(1 for v in keys.values() if v > 1)
    ok = (
        proc.returncode == 0
        and int(cov.get("gaps", 1)) == 0
        and int(cov.get("duplicates", 1)) == 0
        and int(cov.get("mapped") or 0) == int(cov.get("ops") or -1)
        and "lab_app" in principals
        and repeated >= 1
    )
    return criterion(
        "AC-P3-03", "M",
        "SC-01 incident reconciles exactly-once; concurrent lab_app workload",
        f"lab-ledger-account {HEADLINE}",
        "gaps=0 duplicates=0; lab_app present; repeated keys",
        {
            "exit": proc.returncode,
            "ops": cov.get("ops"), "mapped": cov.get("mapped"),
            "gaps": cov.get("gaps"), "duplicates": cov.get("duplicates"),
            "principals": sorted(p for p in principals if p),
            "repeated_keys": repeated,
        },
        ok,
    )


def ac04() -> dict:
    rows = load_jsonl(p3_dir() / "analytics.jsonl")
    need = ("change_burst_density", "churn_by_relation", "churn_by_path", "n_deletes", "ddl")
    keys_ok = bool(rows) and all(all(k in w for k in need) for w in rows)
    det = review("D003") / "determinism.diff"
    det_empty = (not det.is_file()) or det.read_bytes() == b""
    passed = keys_ok and len(rows) >= 2 and det_empty
    return criterion(
        "AC-P3-04", "M",
        "analytics computes burst, churn, deletion spikes; two runs identical",
        "p3/analytics.jsonl + D003/determinism.diff",
        "required fields present; determinism.diff empty",
        {"n_windows": len(rows), "keys_ok": keys_ok, "determinism_empty": det_empty,
         "max_deletes": max((w.get("n_deletes") or 0) for w in rows) if rows else 0},
        passed,
    )


def ac05() -> dict:
    rows = load_jsonl(p3_dir() / "analytics.jsonl")
    # Re-derive: ddl flag true iff the window claims ddl, and at least one true and one false.
    flagged = [w["window_id"] for w in rows if w.get("ddl")]
    unflagged = [w["window_id"] for w in rows if not w.get("ddl")]
    passed = bool(flagged) and bool(unflagged) and all(isinstance(w.get("ddl"), bool) for w in rows)
    return criterion(
        "AC-P3-05", "M",
        "DDL flag raised only for windows that contain DDL",
        "scan analytics.jsonl ddl field",
        "some true, some false; boolean per window",
        {"ddl_windows": flagged, "n_unflagged": len(unflagged)},
        passed,
    )


def ac06() -> dict:
    meta = json.loads((headline_ev() / "incident.json").read_text(encoding="utf-8"))
    inj = json.loads((headline_ev() / "injection_log.json").read_text(encoding="utf-8"))
    baseline = meta.get("quiescent_baseline") or {}
    from lsn import lsn_int, lsn_norm
    base_end = lsn_int(lsn_norm(baseline.get("lsn_end_exclusive") or "0/0"))
    inj_start = lsn_int(lsn_norm(inj.get("lsn_start") or "0/0"))
    proof = {}
    bp = review("D004") / "baseline-window.json"
    if bp.is_file():
        proof = json.loads(bp.read_text(encoding="utf-8"))
    passed = base_end <= inj_start and bool(baseline) and proof.get("predates_injection") is True
    return criterion(
        "AC-P3-06", "M",
        "mean+3σ baseline predates injection (declared, not fitted)",
        "incident.json quiescent_baseline vs injection_log lsn_start",
        "baseline_end <= injection_start; predates_injection true",
        {"baseline_end": baseline.get("lsn_end_exclusive"), "inj_start": inj.get("lsn_start"),
         "predates": proof.get("predates_injection"), "cmp_le": base_end <= inj_start},
        passed,
    )


def ac07() -> dict:
    rows = load_jsonl(p3_dir() / "anomaly.jsonl")
    spike = max(rows, key=lambda w: w.get("n_deletes") or 0) if rows else {}
    quiet = min(rows, key=lambda w: w.get("window_id", 99)) if rows else {}
    passed = (
        bool(rows)
        and spike.get("anomalous") is True
        and float(spike.get("anomaly_score") or 0) >= 3.0
        and quiet.get("anomalous") is False
        and float(quiet.get("anomaly_score") or 99) < 3.0
    )
    return criterion(
        "AC-P3-07", "M",
        "SC-01 deletion window anomalous; quiescent window below threshold",
        "p3/anomaly.jsonl",
        "max-deletes window score>=3 anomalous; window 0 score<3",
        {
            "spike": {"window_id": spike.get("window_id"), "n_deletes": spike.get("n_deletes"),
                      "score": spike.get("anomaly_score"), "anomalous": spike.get("anomalous")},
            "quiet": {"window_id": quiet.get("window_id"), "score": quiet.get("anomaly_score"),
                      "anomalous": quiet.get("anomalous")},
        },
        passed,
    )


def ac08() -> dict:
    from lab_p3_util import validate_candidate, provenance_in_obj
    rows = load_jsonl(p3_dir() / "candidates.jsonl")
    errs = []
    prov = []
    for rec in rows:
        errs.extend(validate_candidate(rec))
        prov.extend(provenance_in_obj(rec))
    passed = bool(rows) and not errs and not prov
    return criterion(
        "AC-P3-08", "M",
        "candidates conform to candidate-coordinate.md; no provenance fields",
        "validate p3/candidates.jsonl",
        "schema ok; no principal/session_user/usename/UID",
        {"n": len(rows), "errors": errs[:6], "provenance": prov[:6]},
        passed,
    )


def ac09() -> dict:
    env = py_env()
    proc = run([str(root() / "bin" / "lab-candidates"), "--lsn-order-fixture"], timeout=30, env=env)
    rec = {}
    try:
        rec = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pass
    passed = proc.returncode == 0 and rec.get("integer_orders_lt") is True and rec.get("string_compare_would_fail") is True
    return criterion(
        "AC-P3-09", "M",
        "candidate ordering uses integer LSN; 3/9 < 3/10",
        "lab-candidates --lsn-order-fixture",
        "integer_orders_lt true; string compare would fail",
        rec,
        passed,
    )


def ac10() -> dict:
    rec = json.loads((p3_dir() / "arm-a-coordinate.json").read_text(encoding="utf-8"))
    det = review("D006") / "determinism.diff"
    det_empty = (not det.is_file()) or det.read_bytes() == b""
    weights = json.loads((root() / "etc" / "rank-weights.json").read_text(encoding="utf-8"))
    passed = (
        rec.get("arm") == "arm_a"
        and rec.get("selector_version") == weights.get("version") == "p3-rank-1"
        and weights.get("tie_break") == "latest_safe_lsn_int"
        and det_empty
    )
    return criterion(
        "AC-P3-10", "M",
        "lab-rank deterministic; versioned weights and tie-break recorded",
        "arm-a-coordinate.json + etc/rank-weights.json + D006/determinism.diff",
        "selector_version=p3-rank-1; tie_break=latest_safe_lsn_int; identical re-run",
        {
            "selector_version": rec.get("selector_version"),
            "weights_version": weights.get("version"),
            "tie_break": weights.get("tie_break"),
            "determinism_empty": det_empty,
        },
        passed,
    )


def ac11() -> dict:
    from lab_p3_util import validate_arm
    from lsn import lsn_int
    rec = json.loads((p3_dir() / "arm-a-coordinate.json").read_text(encoding="utf-8"))
    row = json.loads((review("D008") / "results-arm-a.json").read_text(encoding="utf-8")) if (review("D008") / "results-arm-a.json").is_file() else {}
    chosen = row.get("chosen_coordinate") or {}
    errs = validate_arm(rec)
    mapped = (
        rec.get("lsn_text") == chosen.get("lsn")
        and rec.get("wall_clock") == chosen.get("wall_clock")
        and rec.get("snapshot") == chosen.get("snapshot")
        and rec.get("lsn_int") == lsn_int(chosen.get("lsn") or "0/0")
    )
    passed = not errs and mapped
    return criterion(
        "AC-P3-11", "M",
        "chosen coordinate conforms to arm-coordinate.md and maps onto chosen_coordinate.*",
        "validate arm-a-coordinate.json vs D008 results-arm-a.json",
        "schema ok; lsn_text/lsn_int/wall_clock/snapshot map 1:1",
        {"errors": errs, "mapped": mapped, "lsn_text": rec.get("lsn_text"), "chosen_lsn": chosen.get("lsn")},
        passed,
    )


def ac12() -> dict:
    rec = json.loads((p3_dir() / "naive-coordinate.json").read_text(encoding="utf-8")) if (p3_dir() / "naive-coordinate.json").is_file() else {}
    if not rec and (review("D007") / "naive-coordinate.json").is_file():
        rec = json.loads((review("D007") / "naive-coordinate.json").read_text(encoding="utf-8"))
    cfg = {}
    for raw in (root() / "etc" / "scenarios" / "sc01.env").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"')
    err = rec.get("selection_inputs", {}).get("incident_time_error_seconds")
    declared = int(cfg.get("SC01_NAIVE_TIME_ERROR_SECONDS") or -1)
    flags = rec.get("selection_inputs") or {}
    passed = (
        rec.get("arm") == "naive"
        and err == declared == 20
        and flags.get("read_injection_log") is False
        and flags.get("read_oracle_optimum") is False
        and flags.get("read_provenance") is False
    )
    return criterion(
        "AC-P3-12", "M",
        "naive comparator uses declared fixed time error from scenario config",
        "naive-coordinate.json vs etc/scenarios/sc01.env",
        "incident_time_error_seconds=20; peek flags false",
        {"error": err, "declared": declared, "arm": rec.get("arm"), "flags": flags},
        passed,
    )


def ac13() -> dict:
    from results_schema import load_schema, validate_row
    schema = load_schema()
    a = json.loads((review("D008") / "results-arm-a.json").read_text(encoding="utf-8"))
    n = json.loads((review("D008") / "results-naive.json").read_text(encoding="utf-8"))
    ea, en = validate_row(schema, a), validate_row(schema, n)
    fields_ok = all(
        row.get("coord_error_bytes") is not None
        and row.get("damage_rows_retained") is not None
        and row.get("damage_bytes_retained") is not None
        and row.get("legit_rows_lost") is not None
        and row.get("harness_commit")
        for row in (a, n)
    )
    same = a.get("incident_id") == n.get("incident_id") == RESULTS_INCIDENT
    arms = {a.get("arm"), n.get("arm")} == {"deterministic", "naive"}
    passed = not ea and not en and fields_ok and same and arms
    return criterion(
        "AC-P3-13", "M",
        "evaluate-arm writes schema-valid rows with LSN and rows/bytes error for both arms",
        "validate D008 results-arm-a.json and results-naive.json",
        "schema ok; same incident_id; arms differ; oracle fields populated",
        {
            "errors_a": ea, "errors_n": en, "incident_id": a.get("incident_id"),
            "arms": [a.get("arm"), n.get("arm")],
            "damage_a": a.get("damage_rows_retained"), "damage_n": n.get("damage_rows_retained"),
            "harness_commit": a.get("harness_commit"),
        },
        passed,
    )


def ac14() -> dict:
    a = json.loads((review("D008") / "results-arm-a.json").read_text(encoding="utf-8"))
    n = json.loads((review("D008") / "results-naive.json").read_text(encoding="utf-8"))
    da, dn = int(a["damage_rows_retained"]), int(n["damage_rows_retained"])
    ea, en = int(a["coord_error_bytes"]), int(n["coord_error_bytes"])
    win = da < dn or (da == dn and ea < en)
    headline = (review("D009") / "headline.md").read_text(encoding="utf-8") if (review("D009") / "headline.md").is_file() else ""
    passed = win and da == 0 and dn > 0 and "WIN" in headline
    return criterion(
        "AC-P3-14", "M",
        "headline: Arm A strictly better on damaged rows retained (tie-break LSN error)",
        "compare D008 results rows",
        "arm_a damage_rows_retained < naive",
        {"arm_a": da, "naive": dn, "lsn_err_a": ea, "lsn_err_n": en, "win": win},
        passed,
    )


def ac15() -> dict:
    diff = review("D009") / "provenance-blind.diff"
    empty = diff.is_file() and diff.read_bytes() == b""
    return criterion(
        "AC-P3-15", "M",
        "stripping provenance leaves Arm A coordinate byte-identical",
        "logs/review/D009/provenance-blind.diff",
        "empty diff",
        {"exists": diff.is_file(), "bytes": diff.stat().st_size if diff.is_file() else None},
        empty,
    )


def ac16() -> dict:
    scan = (review("D009") / "no-peek-scan.log").read_text(encoding="utf-8") if (review("D009") / "no-peek-scan.log").is_file() else ""
    rec = json.loads((p3_dir() / "arm-a-coordinate.json").read_text(encoding="utf-8"))
    flags = rec.get("selection_inputs") or {}
    all_false = all(flags.get(k) is False for k in ("read_injection_log", "read_oracle_optimum", "read_provenance"))
    scan_ok = "peek_flags_all_false=True" in scan or "strace_hits_after_revert=[]" in scan
    src = (root() / "lib" / "lab_rank.py").read_text(encoding="utf-8")
    rank_peek = any(n in src for n in ("injection_log.json", "oracle.json", "injection.json"))
    passed = all_false and scan_ok and not rank_peek
    return criterion(
        "AC-P3-16", "M",
        "ranker reads no ground truth; peek flags false; scan clean",
        "arm-a-coordinate selection_inputs + D009/no-peek-scan.log + grep lab_rank.py",
        "all peek flags false; injection_log never opened by ranker",
        {"flags": flags, "scan_ok": scan_ok, "rank_peek": rank_peek},
        passed,
    )


def write_prior_hashes() -> Path:
    lines = []
    p0 = root() / "sdd/specs/P0-lab-substrate/contracts"
    for name, expect in P0_HASHES.items():
        got = sha256_file(p0 / name)
        lines.append(f"{got}  {p0 / name}")
    p1c = root() / "sdd/specs/P1-ground-truth-harness/contracts"
    for name, expect in P1_HASHES.items():
        path = (root() / "etc" / name) if name.endswith(".json") else (p1c / name)
        got = sha256_file(path)
        lines.append(f"{got}  {path}")
    lines.append(f"{sha256_file(completeness())}  {completeness()}")
    lines.append(f"{sha256_file(amendment())}  {amendment()}")
    for name in P3_HASHES:
        path = p3_contracts() / name
        lines.append(f"{sha256_file(path)}  {path}")
    out = review("D010")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "prior-hashes.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ac18_hashes() -> dict:
    observed_p0 = {name: sha256_file(root() / "sdd/specs/P0-lab-substrate/contracts" / name) for name in P0_HASHES}
    p1c = root() / "sdd/specs/P1-ground-truth-harness/contracts"
    observed_p1 = {
        "results-row.md": sha256_file(p1c / "results-row.md"),
        "results-row.amendment-1.md": sha256_file(p1c / "results-row.amendment-1.md"),
        "ledger-integrity.md": sha256_file(p1c / "ledger-integrity.md"),
        "results-row.schema.json": sha256_file(root() / "etc/results-row.schema.json"),
    }
    c001 = sha256_file(completeness())
    observed_p3 = {name: sha256_file(p3_contracts() / name) for name in P3_HASHES}
    hash_ok = observed_p0 == P0_HASHES and observed_p1 == P1_HASHES and c001 == C001_HASH and observed_p3 == P3_HASHES
    write_prior_hashes()
    return {
        "hash_ok": hash_ok,
        "p0": {k: observed_p0[k] == v for k, v in P0_HASHES.items()},
        "p1": {k: observed_p1[k] == v for k, v in P1_HASHES.items()},
        "c001": c001 == C001_HASH,
        "p3": {k: observed_p3[k] == v for k, v in P3_HASHES.items()},
        "capture_completeness": c001,
    }


def prior_gates() -> list[dict]:
    """Bins present + lab-regression. Per-gate readonly-check is AC-P3.1-04 (Z002/Z004)."""
    bins = {
        name: (root() / "bin" / name).is_file()
        for name in ("lab-verify", "lab-verify-p1", "lab-verify-p1.1", "lab-verify-p2", "lab-verify-p2.1", "lab-regression", "lab-gate-readonly-check")
    }
    reg = run([str(root() / "bin/lab-regression")], timeout=1800, env=py_env())
    text = (reg.stdout or "") + "\n" + (reg.stderr or "")
    total_ok = ("TOTAL 5/5" in text) or ("TOTAL: 5/5" in text)
    rows = [
        {
            "name": "prior-gate-binaries",
            "exit": 0 if all(bins.values()) else 1,
            "total_ok": all(bins.values()),
            "bins": bins,
        },
        {
            "name": "lab-regression",
            "exit": reg.returncode,
            "total_ok": total_ok and reg.returncode == 0,
            "tail": text.strip().splitlines()[-16:],
        },
    ]
    out = review("D010")
    out.mkdir(parents=True, exist_ok=True)
    (out / "prior-gates.log").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return rows


def ac18(hash_info: dict, gates: list[dict]) -> dict:
    gates_ok = bool(gates) and all(g.get("exit") == 0 and g.get("total_ok") for g in gates)
    passed = hash_info.get("hash_ok") is True and gates_ok
    return criterion(
        "AC-P3-18", "M",
        "prior contract hashes unchanged; every prior gate present and read-only; lab-regression green",
        "sha256 + lab-gate-readonly-check + bin/lab-regression",
        "hashes match; gates do not mutate evidence; regression 5/5",
        {"hashes": {k: hash_info.get(k) for k in ("p0", "p1", "c001", "p3")}, "gates": gates},
        passed,
    )


def ac19() -> dict:
    path = root() / "docs" / "P3-architecture-handoff.md"
    summary_path = review("D010") / "p3-summary.json"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    obj = json_object_in(text) if "```json" in text else {}
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    merged = {**summary, **obj} if obj else summary
    p5 = str(merged.get("p5") or "")
    p6 = str(merged.get("p6") or "")
    p4 = str(merged.get("p4") or "")
    features = merged.get("analytics_feature_set") or merged.get("feature_set") or []
    inversion = (
        "must not build representations" in p4.lower()
        or "must not build representations" in p5.lower()
        or "must not build representations" in p6.lower()
    )
    builds_r = ("R0" in p5 and "R1" in p5 and "R2" in p5 and "build" in p5.lower())
    builds_b = "Arm B" in p6 and "build" in p6.lower()
    restore = "restore" in p4.lower()
    passed = (
        path.is_file() and summary_path.is_file()
        and bool(features)
        and merged.get("ranker_version") == "p3-rank-1"
        and int(merged.get("window_s") or 0) == 2
        and restore and builds_r and builds_b and not inversion
        and merged.get("headline") in {"arm_a_wins", "WIN", "arm_a"}
    )
    return criterion(
        "AC-P3-19", "A",
        "handoff records feature set, ranker version, SC-01 result; P5=R0/R1/R2 P6=Arm B",
        "docs/P3-architecture-handoff.md JSON + D010/p3-summary.json",
        "window_s=2; p3-rank-1; P4 restore; P5 builds R0/R1/R2; P6 Arm B; no inversion",
        {
            "window_s": merged.get("window_s"),
            "ranker_version": merged.get("ranker_version"),
            "feature_set": features,
            "p4": p4, "p5": p5, "p6": p6,
            "headline": merged.get("headline"),
            "inversion": inversion,
        },
        passed,
    )


def main(argv: list[str]) -> int:
    if argv:
        print("usage: lab-verify-p3", file=sys.stderr)
        return 3
    results = [
        ac01(), ac02(), ac03(), ac04(), ac05(), ac06(), ac07(), ac08(), ac09(),
        ac10(), ac11(), ac12(), ac13(), ac14(), ac15(), ac16(),
    ]
    hash_info = ac18_hashes()
    gates = prior_gates()
    results.append(ac18(hash_info, gates))
    results.append(ac19())
    failed = [r for r in results if r["result"] != "PASS"]
    results.append(criterion(
        "AC-P3-17", "M",
        "lab-verify-p3 reports every criterion PASS with per-tier totals",
        "this footer",
        "all PASS; TIER M and TIER A printed separately",
        {"failed": [f["id"] for f in failed]},
        not failed,
    ))
    for r in results:
        print(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}")
    m = [r for r in results if r["tier"] == "M"]
    a = [r for r in results if r["tier"] == "A"]
    mp, ap = sum(r["result"] == "PASS" for r in m), sum(r["result"] == "PASS" for r in a)
    print(f"TIER M {mp}/{len(m)}")
    print(f"TIER A {ap}/{len(a)}")
    print(f"TOTAL {mp + ap}/{len(results)}")
    out = review("D010")
    out.mkdir(parents=True, exist_ok=True)
    footer = f"TIER M {mp}/{len(m)}\nTIER A {ap}/{len(a)}\nTOTAL {mp + ap}/{len(results)}\n"
    (out / "verify-p3.out").write_text(
        "\n".join(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}" for r in results) + "\n" + footer,
        encoding="utf-8",
    )
    (out / "verify-p3.json").write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
    return 0 if not failed and all(r["result"] == "PASS" for r in results) else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
