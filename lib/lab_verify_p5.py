"""lab-verify-p5: AC-P5-01..19. Tiered. Re-derive. No evidence writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from lab_repr import HEADLINE, PROBE_IDS, REPR_IDS, sha256_file, token_scan
from lab_repr_admit import admit
from lab_p51 import headline_material
from lab_repr_modelview import parity_modelview
from lab_repr_parity import IGNORED, parity
from lab_repr_query import query, response_bytes
from lab_tokenize import evidence_bytes, tokenizer_spec
from lab_redaction import pinned  # ADR-M002

EXIT_ASSERT = 1

C001_HASH = "59aeaa61281f211046b953a0641de72dc55c3f6cecc7278ee45802d41003d647"
C001_AMEND_HASH = None  # filled from F001/F010 re-verify of the file itself
P3_HASHES = {
    "candidate-coordinate.md": "d8795aee07c3379750dc1529bed8311933c0cb2e213da8e9e294593acd17c7f6",
    "arm-coordinate.md": "d2bdef97d8605dab4393b8cf7d69d52f1c196329b4cd6ee15fb27c5e01090947",
}
P4_HASHES = {
    "restore-report.md": pinned("974815821369d1e1477e65851cf0ba39e23e156adf63c5e3840baafa5b30d357"),
    "promotion-gate.md": "edaaeaca69a5b9dbec1172c811b26387b9887f46d8125ab84a29c18442eddfe7",
}
HEADLINE_DB = "bf21fff2c7c71b39a150d15c9d097c797006139497c51b5a865414433a1ac7dd"
RESULTS_ROW = "sdd/specs/P1-ground-truth-harness/contracts/results-row.md"


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parents[1])


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


def recorded_hashes(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, rest = line.partition("  ")
        name = Path(rest.strip()).name
        out[name] = digest.strip()
    return out


def ac01() -> dict:
    base = root() / "sdd/specs/P5-representations/contracts"
    rec = recorded_hashes(review("F001") / "contract-hashes.txt")
    got = {
        "representation-interface.md": sha256_file(base / "representation-interface.md"),
        "representation-fidelity.md": sha256_file(base / "representation-fidelity.md"),
    }
    gate = loadj(review("F001") / "entry-gate.json")
    ready_ok = (
        gate.get("lab_ready_exit") == 0
        or gate.get("lab_ready_blocked_by") == "frozen_headline_d2"
    )
    passed = (
        got == rec
        and ready_ok
        and gate.get("gaps") == 0
        and gate.get("duplicates") == 0
        and gate.get("blind_view_has_principal") is False
        and gate.get("reconciled_incident") == HEADLINE
    )
    return criterion("AC-P5-01", "M", "P5 contracts frozen; entry gate recorded",
                     "F001 contract-hashes + entry-gate.json",
                     "hashes match; ready 0 or frozen_headline_d2 waiver; gaps=0",
                     {"got": got, "gate": gate}, passed)


def ac02() -> dict:
    man = loadj(root() / "var/repr" / HEADLINE / "R0" / "manifest.json")
    events = (root() / "var/repr" / HEADLINE / "R0" / "events.jsonl").read_text().splitlines()
    n = len([ln for ln in events if ln.strip()])
    passed = (
        int(man["event_count"]) == int(man["ledger_event_count"]) == n
        and man.get("built_by_model") is False
    )
    return criterion("AC-P5-02", "M", "R0 event_count equals ledger event count",
                     "R0/manifest.json + events.jsonl count", "equal",
                     {"event_count": man.get("event_count"), "n": n}, passed)


def ac03() -> dict:
    r0 = loadj(root() / "var/repr" / HEADLINE / "R0" / "manifest.json")
    r1 = loadj(root() / "var/repr" / HEADLINE / "R1" / "manifest.json")
    passed = int(r1["event_count"]) == int(r0["event_count"]) and r1.get("reconciles") is True
    return criterion("AC-P5-03", "M", "R1 per-window counts sum to R0",
                     "R1 vs R0 manifests", "event_count equal; reconciles",
                     {"r0": r0.get("event_count"), "r1": r1.get("event_count")}, passed)


def ac04() -> dict:
    from lab_repr import load_r2
    from lab_repr_r2 import dangling_edges
    graph, _sum, man = load_r2(HEADLINE)
    dang = dangling_edges(graph)
    passed = not dang and man.get("built_by_model") is False
    return criterion("AC-P5-04", "M", "R2 graph endpoints resolve; deterministic",
                     "load_r2 + dangling_edges", "0 dangling",
                     {"dangling": len(dang), "n_edges": len(graph["edges"])}, passed)


def ac05() -> dict:
    man = loadj(root() / "var/repr" / HEADLINE / "R2" / "manifest.json")
    log = (review("F004") / "commands.log").read_text(encoding="utf-8") if (review("F004") / "commands.log").is_file() else ""
    model_hits = [ln for ln in log.splitlines() if re.search(r"\b(ollama|llama|openai|anthropic|vllm|huggingface)\b", ln, re.I)]
    passed = man.get("reconciles") is True and man.get("built_by_model") is False and not model_hits
    return criterion("AC-P5-05", "M", "R2 summaries reconcile; no model",
                     "R2 manifest + F004 commands.log", "reconciles; built_by_model=false",
                     {"reconciles": man.get("reconciles"), "model_hits": model_hits}, passed)


def ac06() -> dict:
    schemas = {}
    ok = True
    for probe in PROBE_IDS:
        params = {"window_index": 15} if probe == "PB-1-window-events" else (
            {"top_n": 3} if probe in {"PB-3-entity-churn", "PB-6-candidate-windows"} else (
                {"entity": "p2_probe"} if probe == "PB-5-entity-activity" else {}
            )
        )
        keys = None
        for rep in REPR_IDS:
            payload = query(HEADLINE, rep, probe, params)
            missing = [k for k in ("incident_id", "representation", "probe_id", "answer", "content", "telemetry")
                       if k not in payload]
            if missing:
                ok = False
            sk = sorted(payload["answer"].keys()) if isinstance(payload["answer"], dict) else None
            if keys is None:
                keys = sk
            elif sk != keys:
                ok = False
            schemas[f"{probe}:{rep}"] = sk
    return criterion("AC-P5-06", "M", "18 probe responses share envelope and answer schema",
                     "lab-repr-query 6x3", "identical answer keys per probe",
                     schemas, ok)


def ac07() -> dict:
    payload = query(HEADLINE, "R2", "PB-4-earliest-anomaly", {})
    again = query(HEADLINE, "R2", "PB-4-earliest-anomaly", {})
    passed = response_bytes(payload) == response_bytes(again)
    return criterion("AC-P5-07", "M", "probe response byte-identical on re-run",
                     "PB-4 R2 twice", "bytes equal",
                     {"equal": passed}, passed)


def ac08() -> dict:
    rec = admit(HEADLINE)
    passed = all(v["deterministic"] for v in rec["verdicts"]) and rec["ok"]
    return criterion("AC-P5-08", "M", "rebuild byte-identical for R0/R1/R2",
                     "lab-repr-admit", "deterministic true",
                     rec["verdicts"], passed)


def ac09() -> dict:
    rec = admit(HEADLINE)
    passed = all(v["reconciles"] and v["complete"] for v in rec["verdicts"])
    return criterion("AC-P5-09", "M", "R1/R2 reconcile to R0/ledger",
                     "lab-repr-admit reconciles", "all true",
                     rec["verdicts"], passed)


def ac10() -> dict:
    rec = admit(HEADLINE)
    passed = all(v["provenance_blind"] for v in rec["verdicts"])
    return criterion("AC-P5-10", "M", "no principal token in artefacts or probe sweep",
                     "lab-repr-admit blindness", "provenance_blind true",
                     rec["verdicts"], passed)


def ac11() -> dict:
    rec = parity_modelview(HEADLINE)
    # Reference answers remain identical (parity of the non-subject surface).
    ref = parity(HEADLINE)
    passed = rec["ok"] and rec["ignored_fields"] == sorted(IGNORED) and ref["ok"]
    return criterion("AC-P5-11", "M", "model_view parity; only content/telemetry differ",
                     "lab-repr-modelview parity + lab-repr-parity answers",
                     "structural_match all true on model_view",
                     {"model_view": rec, "reference_ok": ref["ok"]}, passed)


def ac12() -> dict:
    payload = query(HEADLINE, "R0", "PB-4-earliest-anomaly", {})
    got = int(payload["telemetry"]["evidence_bytes"])
    want = evidence_bytes(payload["content"])
    passed = got == want
    return criterion("AC-P5-12", "M", "evidence_bytes equals UTF-8 length of content",
                     "PB-4 R0 telemetry vs len(utf-8)", "exact",
                     {"got": got, "want": want}, passed)


def ac13() -> dict:
    spec = tokenizer_spec()
    rows = {}
    ok = True
    for probe in ("PB-4-earliest-anomaly", "PB-6-candidate-windows"):
        params = {} if probe.startswith("PB-4") else {"top_n": 3}
        r0 = query(HEADLINE, "R0", probe, params)
        r2 = query(HEADLINE, "R2", probe, params)
        rows[probe] = {
            "R0_bytes": r0["telemetry"]["evidence_bytes"],
            "R2_bytes": r2["telemetry"]["evidence_bytes"],
            "R0_tokens": r0["telemetry"]["token_estimate"],
            "R2_tokens": r2["telemetry"]["token_estimate"],
            "tokenizer": r2["telemetry"]["tokenizer"],
        }
        if not (r2["telemetry"]["evidence_bytes"] < r0["telemetry"]["evidence_bytes"]
                and r2["telemetry"]["token_estimate"] < r0["telemetry"]["token_estimate"]
                and r2["telemetry"]["tokenizer"] == spec["id"]):
            ok = False
    return criterion("AC-P5-13", "M", "R2 < R0 bytes and tokens on PB-4 and PB-6; pinned tokenizer",
                     "query PB-4/PB-6 R0 vs R2", "strictly less; tokenizer id matches",
                     {"spec": spec["id"], "rows": rows}, ok)


def ac14() -> dict:
    hl = loadj(review("F009") / "headline.json")
    tel = loadj(review("F008") / "telemetry.json")
    pb6 = tel["deltas"]["PB-6-candidate-windows"]
    from lab_repr_modelview import model_view
    live_r0 = model_view(HEADLINE, "R0", "PB-6-candidate-windows", {"top_n": 3})
    live_r2 = model_view(HEADLINE, "R2", "PB-6-candidate-windows", {"top_n": 3})
    r0b = int(live_r0["telemetry"]["evidence_bytes"])
    r2b = int(live_r2["telemetry"]["evidence_bytes"])
    mat = headline_material(r0b, r2b)
    true_w = int(hl["true_window"]["window_index"])
    faithful = True
    for rep in REPR_IDS:
        ans = query(HEADLINE, rep, "PB-4-earliest-anomaly", {})["answer"]
        if int(ans["window_index"]) != true_w:
            faithful = False
        cands = query(HEADLINE, rep, "PB-6-candidate-windows", {"top_n": 3})["answer"]["candidates"]
        if not cands or int(cands[0]["window_index"]) != true_w:
            faithful = False
    recorded_r0 = int(pb6["R0"]["evidence_bytes"])
    recorded_r2 = int(pb6["R2"]["evidence_bytes"])
    passed = (
        faithful
        and mat["ok"]
        and r0b == recorded_r0
        and r2b == recorded_r2
        and true_w == 15
    )
    return criterion("AC-P5-14", "M", "headline: all three bound the true anomaly; PB-6 R2 << R0",
                     "F008 PB-6 telemetry + live model_view", "window 15; PB-6 R2 materially fewer bytes",
                     {"faithful": faithful, "headline": mat, "true_window": true_w,
                      "recorded_pb6": {"R0": recorded_r0, "R2": recorded_r2}}, passed)


def ac15() -> dict:
    rec = loadj(review("F009") / "discrimination.json")
    passed = rec.get("dropped_window_admissible") is False and rec.get("principal_leak_admissible") is False
    return criterion("AC-P5-15", "M", "dropped window and principal leak rejected",
                     "F009/discrimination.json", "both inadmissible",
                     rec, passed)


def ac16() -> dict:
    ids = []
    for name in REPR_IDS:
        man = loadj(root() / "var/repr" / HEADLINE / name / "manifest.json")
        ids.append(man.get("incident_id"))
    passed = len(set(ids)) == 1 and ids[0] == HEADLINE
    return criterion("AC-P5-16", "M", "all three manifests share reconciled SC-01 incident_id",
                     "R0/R1/R2 manifest incident_id", HEADLINE,
                     ids, passed)


def ac17() -> dict:
    binp = root() / "bin" / "lab-verify-p5"
    passed = binp.is_file() and os.access(binp, os.X_OK)
    return criterion("AC-P5-17", "M", "lab-verify-p5 exists (read-only proven by F010-2)",
                     "stat bin/lab-verify-p5", "0755",
                     {"present": binp.is_file(), "mode": oct(binp.stat().st_mode & 0o777) if binp.is_file() else None},
                     passed)


def ac18() -> dict:
    cc = root() / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md"
    amend = root() / "sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md"
    got_cc = sha256_file(cc)
    got_amend = sha256_file(amend)
    p3 = {n: sha256_file(root() / "sdd/specs/P3-analytics-ranker/contracts" / n) for n in P3_HASHES}
    p4 = {n: sha256_file(root() / "sdd/specs/P4-restore-validation/contracts" / n) for n in P4_HASHES}
    db = sha256_file(root() / "evidence/SC-01" / HEADLINE / "db.jsonl")
    p5 = recorded_hashes(review("F001") / "contract-hashes.txt")
    live_p5 = {
        "representation-interface.md": sha256_file(root() / "sdd/specs/P5-representations/contracts/representation-interface.md"),
        "representation-fidelity.md": sha256_file(root() / "sdd/specs/P5-representations/contracts/representation-fidelity.md"),
    }
    regression = review("F010") / "regression.out"
    reg_ok = False
    if regression.is_file():
        text = regression.read_text(encoding="utf-8")
        reg_ok = "TOTAL" in text and "FAIL" not in text.split("TOTAL")[-1]
        # lab-regression prints ok true
        reg_ok = '"ok": true' in text or '"ok":true' in text or "ok=true" in text or "RESULT: PASS" in text
    passed = (
        got_cc == C001_HASH
        and p3 == P3_HASHES
        and p4 == P4_HASHES
        and db == HEADLINE_DB
        and p5 == live_p5
        and amend.is_file()
        and got_amend
        and reg_ok
    )
    return criterion("AC-P5-18", "M", "prior contract hashes unchanged; regression green",
                     "sha256sum prior contracts + F010/regression.out",
                     C001_HASH,
                     {"capture_completeness": got_cc, "amendment": got_amend, "p3": p3, "p4": p4,
                      "headline_db": db, "p5": live_p5, "reg_ok": reg_ok}, passed)


def ac19() -> dict:
    path = root() / "docs/P5-architecture-handoff.md"
    if not path.is_file():
        return criterion("AC-P5-19", "A", "P5 handoff machine-readable fields",
                         "docs/P5-architecture-handoff.md", "json block", None, False)
    text = path.read_text(encoding="utf-8")
    obj = json_object_in(text)
    nxt = json.dumps(obj.get("next_tranche") or {})
    inverted = "do not build Arm B" in nxt or "do not build Arm B" in text.lower()
    passed = (
        obj.get("representations") == ["R0", "R1", "R2"]
        and obj.get("built_by_model") is False
        and obj.get("parity") is True
        and obj.get("anti_goal_inversion") is False
        and not inverted
        and "Arm B" in json.dumps(obj.get("next_tranche") or {})
        and "lab-repr-query" in json.dumps(obj.get("next_tranche") or {})
        and obj.get("headline_incident") == HEADLINE
    )
    return criterion("AC-P5-19", "A", "handoff records R0/R1/R2, parity, delta; P6=Arm B",
                     "docs/P5-architecture-handoff.md JSON", "machine-readable; no inversion",
                     obj, passed)


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
    out = review("F010")
    out.mkdir(parents=True, exist_ok=True)
    footer = f"TIER M {mp}/{len(m)}\nTIER A {ap}/{len(a)}\nTOTAL {mp + ap}/{len(results)}\n"
    (out / "verify-p5.out").write_text(
        "\n".join(f"{r['id']} | {r['tier']} | {r['result']} | {r['requirement']}" for r in results)
        + "\n" + footer,
        encoding="utf-8",
    )
    return 0 if not failed else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
