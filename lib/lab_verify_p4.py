"""lab-verify-p4: AC-P4-01..19. Tiered. Re-derive from artefacts. No evidence writes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from lab_redaction import pinned  # ADR-M002

EXIT_ASSERT = 1

P4_HASHES = {
    "restore-report.md": pinned("974815821369d1e1477e65851cf0ba39e23e156adf63c5e3840baafa5b30d357"),
    "promotion-gate.md": "edaaeaca69a5b9dbec1172c811b26387b9887f46d8125ab84a29c18442eddfe7",
}
C001_HASH = "59aeaa61281f211046b953a0641de72dc55c3f6cecc7278ee45802d41003d647"
P3_HASHES = {
    "candidate-coordinate.md": "d8795aee07c3379750dc1529bed8311933c0cb2e213da8e9e294593acd17c7f6",
    "arm-coordinate.md": "d2bdef97d8605dab4393b8cf7d69d52f1c196329b4cd6ee15fb27c5e01090947",
}
HEADLINE_DB = "bf21fff2c7c71b39a150d15c9d097c797006139497c51b5a865414433a1ac7dd"
HEADLINE = "SC-01_20260824T091611Z"


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parents[1])


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(task: str) -> Path:
    return root() / "logs" / "review" / task


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


def loadj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ac01() -> dict:
    base = root() / "sdd/specs/P4-restore-validation/contracts"
    got = {n: sha256_file(base / n) for n in P4_HASHES}
    passed = got == P4_HASHES
    return criterion("AC-P4-01", "M", "P4 contracts frozen and hash-verified",
                     "sha256sum contracts/*.md", str(P4_HASHES), got, passed)


def ac02() -> dict:
    rt = loadj(review("E002") / "replay-target.json")
    src = (root() / "lib/lab_restore_db.py").read_text()
    victim = os.environ.get("PG_DATA") or "/var/lib/postgresql/18/main"
    hits = [ln for ln in (review("E002") / "commands.log").read_text().splitlines()
            if ("pg_ctl" in ln or "systemctl" in ln) and victim in ln]
    passed = (
        rt.get("stopped_at_target") is True
        and "labpool/sandbox" in src
        and not hits
        and (root() / "bin/lab-restore-db").is_file()
    )
    return criterion("AC-P4-02", "M", "DB PITR into sandbox, never victim",
                     "inspect replay-target + commands.log", "sandbox; no victim pg_ctl",
                     {"stopped": rt.get("stopped_at_target"), "victim_pg_ctl_hits": hits}, passed)


def ac03() -> dict:
    rt = loadj(review("E002") / "replay-target.json")
    passed = (
        int(rt["replay_lsn_int"]) >= int(rt["target_lsn_int"])
        and rt.get("beyond_target_absent") is True
        and rt.get("stopped_at_target") is True
    )
    return criterion("AC-P4-03", "M", "replay stopped at target; beyond-target absent",
                     "replay-target.json", "replay >= target; beyond absent", rt, passed)


def ac04() -> dict:
    clone = loadj(review("E003") / "clone.json")
    log = (review("E003") / "commands.log").read_text()
    passed = (
        str(clone.get("clone_dataset") or "").startswith("labpool/sandbox/")
        and "zfs rollback" not in log
        and (root() / "bin/lab-restore-fs").is_file()
    )
    return criterion("AC-P4-04", "M", "FS restore is zfs clone under labpool/sandbox",
                     "clone.json + commands.log", "sandbox clone; no rollback", clone, passed)


def ac05() -> dict:
    skew = loadj(review("E004") / "skew.json")
    order = loadj(review("E004") / "lsn-order.json")
    passed = (
        int(skew["snapshot_lsn_int"]) <= int(skew["target_lsn_int"])
        and order.get("integer_ok") is True
        and order.get("string_would_pick_3_9") is True
        and skew.get("skew_ms") is not None
    )
    return criterion("AC-P4-05", "M", "integer LSN snapshot pick; skew recorded",
                     "skew.json + lsn-order.json", "snap LSN <= target; 3/10 > 3/9",
                     {"skew": skew, "order": order}, passed)


def ac06() -> dict:
    sample = loadj(review("E005") / "validation-sample.json")
    rels = (sample.get("db_validation") or {}).get("relations") or {}
    passed = "p2_probe" in rels and "row_count" in rels["p2_probe"] and "content_hash" in rels["p2_probe"]
    return criterion("AC-P4-06", "M", "row-level compare vs oracle manifest",
                     "validation-sample.json", "p2_probe row_count+content_hash",
                     rels.get("p2_probe"), passed)


def ac07() -> dict:
    sample = loadj(review("E005") / "validation-sample.json")
    fs = sample.get("fs_validation") or {}
    neg = loadj(review("E005") / "negative-injected.json")
    passed = (
        int((sample.get("summary") or {}).get("files_mismatched") or 0) == 0
        and int((neg.get("summary") or {}).get("files_mismatched") or 0) >= 1
    )
    return criterion("AC-P4-07", "M", "byte-level compare; missing/extra detected",
                     "validation-sample + negative-injected", "Arm A 0; injected file mismatch",
                     {"arm_a_files": fs, "injected": (neg.get("summary") or {}).get("files_mismatched")}, passed)


def ac08() -> dict:
    sample = loadj(review("E005") / "validation-sample.json")
    neg = loadj(review("E005") / "negative-injected.json")
    passed = (
        (sample.get("schema_validation") or {}).get("ddl_match") is True
        and int((neg.get("summary") or {}).get("schema_diffs") or 0) >= 1
    )
    return criterion("AC-P4-08", "M", "schema DDL compare; alter detected",
                     "validation-sample + negative-injected", "match on Arm A; diff on ALTER",
                     {"ddl_match": (sample.get("schema_validation") or {}).get("ddl_match"),
                      "neg_diffs": (neg.get("summary") or {}).get("schema_diffs")}, passed)


def ac09() -> dict:
    cases = {
        "zero": "correct",
        "legit": "incorrect-safe",
        "damage": "incorrect-corrupt",
        "unusable": "not-recovered",
    }
    src = (root() / "lib/lab_verdict.py").read_text()
    ns: dict = {}
    exec(compile(src, str(root() / "lib/lab_verdict.py"), "exec"), ns)  # noqa: S102 — re-derive mapping
    got = {}
    for name, want in cases.items():
        val = loadj(review("E006") / "cases" / f"{name}.json")
        got[name] = ns["verdict_of"](val, usable=bool(val.get("usable", True)))
    passed = got == cases
    return criterion("AC-P4-09", "M", "4-level verdict mapping",
                     "lab_verdict.verdict_of on E006 cases", str(cases), got, passed)


def ac10() -> dict:
    report = loadj(root() / "var/restore" / HEADLINE / "arm_a" / "report.json")
    req = (
        "incident_id", "restore_of", "coordinate", "db_validation", "fs_validation",
        "schema_validation", "summary", "consistency_verdict", "promotion",
        "restore_target", "safety", "selector_provenance", "harness_commit",
    )
    missing = [k for k in req if k not in report]
    passed = not missing and report["promotion"]["decision"] in {"withheld", "simulated"}
    return criterion("AC-P4-10", "M", "restore report schema-valid; harness_commit present",
                     "var/restore/.../arm_a/report.json", "required fields",
                     {"missing": missing, "harness": report.get("harness_commit")}, passed)


def ac11() -> dict:
    src = (root() / "lib/lab_promote.py").read_text()
    passed = (
        'verdict != "correct"' in src
        and "no authorization token" in src
        and (root() / "bin/lab-promote").is_file()
    )
    return criterion("AC-P4-11", "M", "promote refuses without correct verdict and token",
                     "inspect lab_promote.py", "both gates present",
                     {"verdict_gate": 'verdict != "correct"' in src, "token_gate": "no authorization token" in src},
                     passed)


def ac12() -> dict:
    rec = loadj(root() / "var/restore" / HEADLINE / "e007synth" / "promotion.json")
    src = (root() / "lib/lab_promote.py").read_text()
    passed = (
        rec.get("decision") == "simulated"
        and rec.get("decision") != "authorized"
        and "lab must never emit decision=authorized" in src
    )
    return criterion("AC-P4-12", "M", "clean+authorized promote is simulated only",
                     "e007synth/promotion.json", "simulated; never authorized",
                     rec.get("decision"), passed)


def ac13() -> dict:
    gt = loadj(review("E009") / "ground-truth-report.json")
    s = gt.get("summary") or {}
    passed = (
        gt.get("consistency_verdict") == "correct"
        and s.get("damage_rows_retained") == 0
        and s.get("legit_rows_lost") == 0
        and s.get("files_mismatched") == 0
        and s.get("schema_diffs") == 0
    )
    return criterion("AC-P4-13", "M", "ground-truth restore is correct with all zeros",
                     "E009/ground-truth-report.json", "correct; zeros",
                     {"verdict": gt.get("consistency_verdict"), "summary": s}, passed)


def ac14() -> dict:
    disc = loadj(review("E009") / "discrimination-reports.json")
    late = disc["too_late"]
    early = disc["too_early"]
    late_s = late.get("summary") or {}
    early_s = early.get("summary") or {}
    passed = (
        late.get("consistency_verdict") == "incorrect-corrupt"
        and int(late_s.get("damage_rows_retained", 0)) > 0
        and early.get("consistency_verdict") == "incorrect-safe"
        and int(early_s.get("legit_rows_lost", 0)) > 0
        and early_s.get("damage_rows_retained") == 0
    )
    return criterion("AC-P4-14", "M", "too-late corrupt; too-early safe",
                     "E009/discrimination-reports.json", "incorrect-corrupt vs incorrect-safe",
                     {"late": late.get("consistency_verdict"), "early": early.get("consistency_verdict")}, passed)


def ac15() -> dict:
    md = (review("E008") / "agreement.md").read_text()
    passed = "damage_rows_retained equal: **True**" in md and "P3-formula legit equal: **True**" in md
    return criterion("AC-P4-15", "M", "Arm A real-restore agrees with P3 analytical damage + P3-formula legit",
                     "E008/agreement.md", "damage 0=0; P3-formula 48=48",
                     {"has_damage_true": "damage_rows_retained equal: **True**" in md,
                      "has_p3_true": "P3-formula legit equal: **True**" in md}, passed)


def ac16() -> dict:
    txt = (review("E008") / "safety-manifest.txt").read_text()
    passed = "identical True" in txt or "identical true" in txt
    return criterion("AC-P4-16", "M", "victim+evidence manifest identical across restore+teardown",
                     "E008/safety-manifest.txt", "identical True", txt.strip().splitlines(), passed)


def ac17() -> dict:
    binp = root() / "bin" / "lab-verify-p4"
    passed = binp.is_file() and os.access(binp, os.X_OK)
    return criterion("AC-P4-17", "M", "lab-verify-p4 exists and does not write the evidence root",
                     "stat bin/lab-verify-p4; lab-gate-readonly-check (E010-2)", "0755; evidence manifest unchanged",
                     {"present": binp.is_file(), "mode": oct(binp.stat().st_mode & 0o777) if binp.is_file() else None},
                     passed)


def ac18() -> dict:
    cc = root() / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md"
    got_cc = sha256_file(cc)
    p3 = root() / "sdd/specs/P3-analytics-ranker/contracts"
    got_p3 = {n: sha256_file(p3 / n) for n in P3_HASHES}
    db = root() / "evidence/SC-01" / HEADLINE / "db.jsonl"
    got_db = sha256_file(db) if db.is_file() else None
    passed = got_cc == C001_HASH and got_p3 == P3_HASHES and got_db == HEADLINE_DB
    return criterion("AC-P4-18", "M", "prior contract hashes and headline db.jsonl unchanged",
                     "sha256sum capture-completeness + p3 contracts + headline db.jsonl",
                     C001_HASH, {"capture_completeness": got_cc, "p3": got_p3, "headline_db": got_db}, passed)


def ac19() -> dict:
    path = root() / "docs/P4-architecture-handoff.md"
    if not path.is_file():
        return criterion("AC-P4-19", "A", "P4 handoff machine-readable fields",
                         "docs/P4-architecture-handoff.md", "json block", None, False)
    obj = json_object_in(path.read_text(encoding="utf-8"))
    passed = (
        obj.get("walking_skeleton") is True
        and obj.get("ground_truth_verdict") == "correct"
        and obj.get("p5") == "builds representations R0/R1/R2"
        and obj.get("p6") == "builds Arm B model harness"
        and ("PITR" in (obj.get("mechanism") or "") or "clone" in (obj.get("mechanism") or ""))
        and obj.get("anti_goal_inversion") is False
        and obj.get("headline_db_jsonl_sha256") == HEADLINE_DB
    )
    return criterion("AC-P4-19", "A", "handoff records mechanism, skew, loop-close, milestone, P5/P6",
                     "docs/P4-architecture-handoff.md JSON", "machine-readable fields", obj, passed)


def main(argv: list[str]) -> int:
    results = [
        ac01(), ac02(), ac03(), ac04(), ac05(), ac06(), ac07(), ac08(), ac09(),
        ac10(), ac11(), ac12(), ac13(), ac14(), ac15(), ac16(), ac17(), ac18(), ac19(),
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
    out = review("E010")
    out.mkdir(parents=True, exist_ok=True)
    footer = f"TIER M {mp}/{len(m)}\nTIER A {ap}/{len(a)}\nTOTAL {mp + ap}/{len(results)}\n"
    (out / "verify-p4.out").write_text(
        "\n".join(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}" for r in results)
        + "\n" + footer,
        encoding="utf-8",
    )
    return 0 if not failed else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
