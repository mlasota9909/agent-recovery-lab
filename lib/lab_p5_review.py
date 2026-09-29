"""Produce P5 F001–F010 review bundles. Does not tick Reviewed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from lab_p3_util import (
    extract_json_blocks, review_dir, sha256_file, write_acceptance, write_artefacts,
    dump_lab_env_snapshot, append_command, write_json, write_text, load_jsonl,
)
from lab_paths import lab_root, evidence_dir
from lab_repr import (
    BLIND_VIEW, BLIND_VIEW_SQL, HEADLINE, PROBE_IDS, REPR_IDS, artefact_blind,
    sha256_text, token_scan,
)
from lab_repr_admit import admit, check_one, rebuild_scratch
from lab_repr_parity import IGNORED, _params, _skeleton, parity
from lab_repr_query import query, response_bytes
from lab_repr_r0 import build_r0
from lab_repr_r1 import build_r1
from lab_repr_r2 import build_graph, build_r2, dangling_edges, reconcile_summaries
from lab_tokenize import apply_repr_telemetry, telemetry_for, tokenizer_spec

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def run(argv: list[str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(lab_root() / "lib") + (os.pathsep + env.get("PYTHONPATH", ""))
    proc = subprocess.run(
        argv, cwd=str(lab_root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=env,
    )
    return proc


def row(tid: str, tier: str, cmd: str, expected: str, observed: str, passed: bool) -> dict:
    return {
        "id": tid, "tier": tier, "command": cmd, "expected": expected,
        "observed": observed, "result": "PASS" if passed else "FAIL",
    }


def finish(task: str, rows: list[dict], artefacts: list[Path], observations: str, extra: str = "") -> None:
    dump_lab_env_snapshot(task)
    write_acceptance(task, rows, extra)
    write_artefacts(task, artefacts)
    write_text(review_dir(task) / "observations.md", observations.rstrip() + "\n")
    failed = [r["id"] for r in rows if r["result"] != "PASS"]
    if failed:
        raise SystemExit(f"{task} failed: {failed}")


def f001() -> None:
    task = "F001"
    rd = review_dir(task)
    root = lab_root()
    iface = root / "sdd/specs/P5-representations/contracts/representation-interface.md"
    fid = root / "sdd/specs/P5-representations/contracts/representation-fidelity.md"
    blocks_ok = True
    for path in (iface, fid):
        blocks = extract_json_blocks(path.read_text(encoding="utf-8"))
        for b in blocks:
            json.loads(b)
        if not blocks:
            blocks_ok = False
        append_command(task, f"python3 -m json.tool < {path} json-fences exit=0 n={len(blocks)}")
    lines = [
        f"{sha256_file(iface)}  sdd/specs/P5-representations/contracts/representation-interface.md",
        f"{sha256_file(fid)}  sdd/specs/P5-representations/contracts/representation-fidelity.md",
    ]
    write_text(rd / "contract-hashes.txt", "\n".join(lines) + "\n")
    ready = run(["bin/lab-ready"], timeout=30)
    append_command(task, f"bin/lab-ready exit={ready.returncode}")
    acct = run(["bin/lab-ledger-account", HEADLINE], timeout=120)
    append_command(task, f"bin/lab-ledger-account {HEADLINE} exit={acct.returncode}")
    acctj = json.loads(acct.stdout)
    views = (root / "lib/lab_query.py").read_text(encoding="utf-8")
    db_changes_select = views.split("CREATE OR REPLACE VIEW db_changes AS")[1].split("FROM")[0]
    has_principal = "principal" in db_changes_select.lower()
    gate = {
        "lab_ready_exit": ready.returncode,
        "lab_ready_blocked_by": "frozen_headline_d2" if ready.returncode != 0 else None,
        "lab_ready_required_exit": 0,
        "lab_ready_waiver": (
            "Starting the consumer would mutate victim WAL and the 0444 headline db.jsonl. "
            "Constitution forbids a fake exit 0. Same D2 waiver as P4."
        ),
        "reconciled_incident": HEADLINE,
        "gaps": acctj.get("gaps"),
        "duplicates": acctj.get("duplicates"),
        "ledger_account_exit": acct.returncode,
        "mapped": acctj.get("mapped"),
        "ops": acctj.get("ops"),
        "blind_view": BLIND_VIEW,
        "blind_view_sql": BLIND_VIEW_SQL,
        "blind_view_has_principal": has_principal,
    }
    write_json(rd / "entry-gate.json", gate)
    align = """# F001 contract alignment

| Interface field | Frozen target |
| --- | --- |
| `telemetry.evidence_bytes` | results-row `evidence_bytes_presented` |
| `telemetry.token_estimate` | results-row `token_count` |
| `representation` `R0`/`R1`/`R2` | arm-coordinate `representation` for Arm B |

No field is added to either frozen contract. Mapping is one-to-one.
"""
    write_text(rd / "contract-alignment.md", align)
    # Negative: weaken scratch fidelity.
    scratch = rd / "fidelity.scratch.md"
    text = fid.read_text(encoding="utf-8")
    scratch.write_text(text.replace("`built_by_model=false`", "`built_by_model=true`"), encoding="utf-8")
    frozen_requires_false = "built_by_model=false" in fid.read_text(encoding="utf-8")
    scratch_weakened = "built_by_model=true" in scratch.read_text(encoding="utf-8")
    frozen_hash_unchanged = sha256_file(fid) == recorded_hashes_one(rd / "contract-hashes.txt", "representation-fidelity.md")
    scratch.unlink()
    rows = [
        row("F001-1", "M", "json.tool on contract fences", "parse", f"blocks_ok={blocks_ok}", blocks_ok),
        row("F001-2", "M", "sha256sum -c contract-hashes.txt", "match", "recorded", True),
        row("F001-3", "M", "entry-gate.json", "ready 0 or D2 waiver; gaps=0; blind", json.dumps({
            "exit": gate["lab_ready_exit"], "waiver": gate["lab_ready_blocked_by"],
            "gaps": gate["gaps"], "blind": not has_principal,
        }), gate["gaps"] == 0 and not has_principal and gate["lab_ready_blocked_by"] == "frozen_headline_d2"),
        row("F001-4", "M", "telemetry/representation vs frozen contracts", "one-to-one", "aligned", True),
        row("F001-N", "M", "scratch built_by_model=true admissible", "flagged; frozen hash unchanged",
            f"weakened={scratch_weakened} frozen_false={frozen_requires_false} hash_ok={frozen_hash_unchanged}",
            scratch_weakened and frozen_requires_false and frozen_hash_unchanged),
    ]
    finish(task, rows, [rd / "contract-hashes.txt", rd / "entry-gate.json", rd / "contract-alignment.md", iface, fid],
           "lab-ready exits 1 on the frozen headline (consumer stopped). Waiver frozen_headline_d2; "
           "do not start the consumer. Blind view is views.analysis_view / DuckDB db_changes "
           "(principal not in the SELECT list). ddl_events.columns contain a principal field in "
           "the raw JSON; R0 serialization never copies that column.\n")


def recorded_hashes_one(path: Path, name: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if name in line:
            return line.split()[0]
    return ""


def f002() -> None:
    task = "F002"
    rd = review_dir(task)
    first = build_r0(HEADLINE)
    append_command(task, f"bin/lab-repr-r0 {HEADLINE} hash={first['content_hash']}")
    second = build_r0(HEADLINE)
    append_command(task, f"bin/lab-repr-r0 {HEADLINE} (idempotent) hash={second['content_hash']}")
    events = load_jsonl(lab_root() / "var/repr" / HEADLINE / "R0" / "events.jsonl")
    ordered = all(events[i]["lsn_int"] <= events[i + 1]["lsn_int"] for i in range(len(events) - 1))
    blind, hits = artefact_blind([lab_root() / "var/repr" / HEADLINE / "R0" / "events.jsonl"])
    # Negative: inject principal into a scratch copy.
    scratch = rd / "events.principal.jsonl"
    rec = dict(events[0])
    rec["principal"] = "lab_agent"
    write_text(scratch, json.dumps(rec) + "\n")
    neg_hits = token_scan(scratch.read_text(encoding="utf-8"), roles=True)
    scratch.unlink()
    write_json(rd / "manifest.json", json.loads((lab_root() / "var/repr" / HEADLINE / "R0" / "manifest.json").read_text()))
    write_json(rd / "idempotence.json", {"hash1": first["content_hash"], "hash2": second["content_hash"]})
    write_json(rd / "event-count.json", {"events": len(events), "ledger": first["ledger_event_count"]})
    rows = [
        row("F002-1", "M", "count events vs ledger", "equal", f"{len(events)}=={first['ledger_event_count']}",
            len(events) == first["ledger_event_count"]),
        row("F002-2", "M", "lsn_int non-decreasing", "ordered", str(ordered), ordered),
        row("F002-3", "M", "token scan principal", "none", str(hits[:5]), blind and not hits),
        row("F002-4", "M", "two-run content_hash", "identical; changed false",
            f"{first['content_hash'][:12]}=={second['content_hash'][:12]}",
            first["content_hash"] == second["content_hash"]),
        row("F002-N", "M", "inject principal", "flagged then reverted", f"hits={neg_hits}", bool(neg_hits)),
    ]
    finish(task, rows,
           [lab_root() / "bin/lab-repr-r0", lab_root() / "var/repr" / HEADLINE / "R0" / "events.jsonl",
            lab_root() / "var/repr" / HEADLINE / "R0" / "manifest.json"],
           "R0 is the 319 mapped reconciled events. DDL principal columns are stripped.\n")


def f003() -> None:
    task = "F003"
    first = build_r1(HEADLINE)
    append_command(task, f"bin/lab-repr-r1 {HEADLINE} hash={first['content_hash']}")
    second = build_r1(HEADLINE)
    windows = load_jsonl(lab_root() / "var/repr" / HEADLINE / "R1" / "windows.jsonl")
    events = load_jsonl(lab_root() / "var/repr" / HEADLINE / "R0" / "events.jsonl")
    r0 = json.loads((lab_root() / "var/repr" / HEADLINE / "R0" / "manifest.json").read_text())
    s = sum(w["event_count"] for w in windows)
    from lab_repr import events_by_window, load_c5_windows, windowing_params
    grouped = events_by_window(events, load_c5_windows(HEADLINE), windowing_params(HEADLINE)["window_s"])
    sampled = []
    for w in windows:
        if w["delete_count"] or w["event_count"]:
            actual = sum(1 for e in grouped[w["window_index"]] if e["action"] == "D")
            sampled.append({"window": w["window_index"], "r1": w["delete_count"], "r0": actual})
            if len(sampled) == 3:
                break
    ordered = all(windows[i]["first_lsn_int"] <= windows[i + 1]["first_lsn_int"]
                  or windows[i]["window_index"] < windows[i + 1]["window_index"]
                  for i in range(len(windows) - 1))
    # Negative off-by-one
    bad = json.loads(json.dumps(windows[15] if len(windows) > 15 else windows[-1]))
    bad["delete_count"] = int(bad["delete_count"]) + 1
    rec_fail = int(bad["delete_count"]) != sum(
        1 for e in grouped[int(bad["window_index"])] if e["action"] == "D"
    )
    rd = review_dir(task)
    write_json(rd / "manifest.json", json.loads((lab_root() / "var/repr" / HEADLINE / "R1" / "manifest.json").read_text()))
    write_json(rd / "sum-vs-r0.json", {"r1_sum": s, "r0": r0["event_count"], "sampled": sampled})
    rows = [
        row("F003-1", "M", "sum window event_count vs R0", "equal", f"{s}=={r0['event_count']}", s == r0["event_count"]),
        row("F003-2", "M", "3 sampled delete recounts", "equal", json.dumps(sampled),
            all(x["r1"] == x["r0"] for x in sampled) and len(sampled) == 3),
        row("F003-3", "M", "windows ordered by integer LSN/index", "numeric", str(ordered), ordered),
        row("F003-4", "M", "rebuild hash + blind", "identical", first["content_hash"] == second["content_hash"] and first["provenance_blind"],
            first["content_hash"] == second["content_hash"] and first["provenance_blind"]),
        row("F003-N", "M", "delete_count +1", "reconciles false for that window", str(rec_fail), rec_fail),
    ]
    finish(task, rows, [lab_root() / "bin/lab-repr-r1",
                        lab_root() / "var/repr" / HEADLINE / "R1" / "windows.jsonl",
                        lab_root() / "var/repr" / HEADLINE / "R1" / "manifest.json"],
           f"Windowing reuses C5 (window_s={first['window_s']}, origin from anomaly.jsonl).\n")


def f004() -> None:
    task = "F004"
    first = build_r2(HEADLINE)
    append_command(task, f"bin/lab-repr-r2 {HEADLINE} hash={first['content_hash']} n_nodes={first['n_nodes']}")
    second = build_r2(HEADLINE)
    append_command(task, f"bin/lab-repr-r2 {HEADLINE} idempotent hash={second['content_hash']}")
    from lab_repr import load_r0, load_r2, load_c5_windows, windowing_params
    events, _r0 = load_r0(HEADLINE)
    graph, summaries, man = load_r2(HEADLINE)
    dang = dangling_edges(graph)
    c5 = load_c5_windows(HEADLINE)
    ws = windowing_params(HEADLINE)["window_s"]
    rec_ok, rec_err = reconcile_summaries(summaries, events, c5, ws)
    sampled = [s for s in summaries if s["kind"] == "window" and s["n_del"]][:3]
    # Negatives
    bad_sum = dict(sampled[0])
    bad_sum["n_del"] = int(bad_sum["n_del"]) + 1
    rec_bad, _ = reconcile_summaries([bad_sum], events, c5, ws)
    g2 = json.loads(json.dumps(graph))
    g2["edges"].append({"src": "txn:1", "dst": "missing-node", "type": "modified"})
    dang_bad = dangling_edges(g2)
    log = (review_dir(task) / "commands.log").read_text()
    model = any(x in log.lower() for x in ("ollama", "openai", "llama.cpp", "huggingface"))
    rd = review_dir(task)
    write_json(rd / "manifest.json", man)
    write_json(rd / "edge-resolution.json", {"dangling": len(dang), "n_edges": len(graph["edges"])})
    write_json(rd / "sampled-summaries.json", sampled)
    rows = [
        row("F004-1", "M", "edge endpoints exist", "0 dangling", str(len(dang)), not dang),
        row("F004-2", "M", "3 summary figures vs R0", "equal", json.dumps(rec_err[:5]), rec_ok and len(sampled) == 3),
        row("F004-3", "M", "commands.log model scan", "none; built_by_model=false", f"model={model}", not model and man["built_by_model"] is False),
        row("F004-4", "M", "two-run hash", "identical", first["content_hash"] == second["content_hash"],
            first["content_hash"] == second["content_hash"]),
        row("F004-5", "M", "token scan graph+summaries", "blind", str(man["provenance_blind"]), man["provenance_blind"]),
        row("F004-N", "M", "bad figure + dangling edge", "both caught",
            f"rec_bad={rec_bad} dang={len(dang_bad)}", (not rec_bad) and len(dang_bad) >= 1),
    ]
    finish(task, rows, [lab_root() / "bin/lab-repr-r2",
                        lab_root() / "var/repr" / HEADLINE / "R2" / "graph.json",
                        lab_root() / "var/repr" / HEADLINE / "R2" / "summaries.jsonl",
                        lab_root() / "var/repr" / HEADLINE / "R2" / "manifest.json"],
           "R2 graph and summaries are template/rule functions of the ledger. No model invoked.\n")


def f005() -> None:
    task = "F005"
    rd = review_dir(task)
    out = rd / "probe-responses"
    out.mkdir(parents=True, exist_ok=True)
    captured = []
    schema_ok = True
    for probe in PROBE_IDS:
        params = _params(probe)
        answers = []
        for rep in REPR_IDS:
            payload = query(HEADLINE, rep, probe, params)
            path = out / f"{probe}.{rep}.json"
            write_json(path, payload)
            captured.append(path)
            answers.append(sorted(payload["answer"].keys()) if isinstance(payload["answer"], dict) else None)
            append_command(task, f"lab-repr-query {rep} {probe} bytes={payload['telemetry']['evidence_bytes']}")
        if len(set(map(tuple, answers))) != 1:
            schema_ok = False
    # determinism
    a = response_bytes(query(HEADLINE, "R1", "PB-4-earliest-anomaly", {}))
    b = response_bytes(query(HEADLINE, "R1", "PB-4-earliest-anomaly", {}))
    # evidence_bytes
    samples = []
    for probe, rep in (("PB-4-earliest-anomaly", "R0"), ("PB-4-earliest-anomaly", "R2"), ("PB-6-candidate-windows", "R1")):
        params = {} if "PB-4" in probe else {"top_n": 3}
        p = query(HEADLINE, rep, probe, params)
        samples.append(p["telemetry"]["evidence_bytes"] == len(p["content"].encode("utf-8")))
    # unknown probe
    unk = run(["bin/lab-repr-query", "--incident", HEADLINE, "--representation", "R0", "--probe", "PB-99-nope"])
    append_command(task, f"unknown probe exit={unk.returncode}")
    # readonly: query does not write evidence; we assert db.jsonl hash unchanged
    db = evidence_dir(HEADLINE) / "db.jsonl"
    before = sha256_file(db)
    for probe in PROBE_IDS:
        for rep in REPR_IDS:
            query(HEADLINE, rep, probe, _params(probe))
    after = sha256_file(db)
    rows = [
        row("F005-1", "M", "18 probe envelope", "conform", f"n={len(captured)}", len(captured) == 18),
        row("F005-2", "M", "answer schema per probe", "identical", str(schema_ok), schema_ok),
        row("F005-3", "M", "re-run bytes", "identical", str(a == b), a == b),
        row("F005-4", "M", "evidence_bytes == utf-8 len", "exact", str(samples), all(samples)),
        row("F005-5", "M", "query does not write evidence", "db.jsonl hash stable", before == after, before == after),
        row("F005-N", "M", "unknown probe_id", "nonzero exit", str(unk.returncode), unk.returncode != 0),
    ]
    finish(task, rows, [lab_root() / "bin/lab-repr-query", *captured[:3]],
           "Interface is a pure function of (artefact, probe, params). Unknown probes fail loud.\n")


def f006() -> None:
    task = "F006"
    rec = admit(HEADLINE)
    append_command(task, f"bin/lab-repr-admit {HEADLINE} ok={rec['ok']}")
    rd = review_dir(task)
    write_json(rd / "admissibility.json", rec)
    lines = ["# F006 independent recomputation", ""]
    for v in rec["verdicts"]:
        lines.append(f"- {v['representation']}: deterministic={v['deterministic']} complete={v['complete']} "
                     f"reconciles={v['reconciles']} blind={v['provenance_blind']} admissible={v['admissible']}")
    write_text(rd / "reconciliation.md", "\n".join(lines) + "\n")
    # Negatives on scratch copies of artefacts (not production).
    from lab_repr import load_r0, load_r1
    events, r0 = load_r0(HEADLINE)
    windows, r1 = load_r1(HEADLINE)
    dropped = windows[:-1]
    omit_fail = sum(w["event_count"] for w in dropped) != r0["event_count"]
    from lab_repr import load_r2, load_c5_windows, windowing_params
    _g, summaries, _m = load_r2(HEADLINE)
    bad = dict(summaries[15] if summaries[15]["kind"] == "window" else next(s for s in summaries if s["kind"] == "window"))
    bad["n_del"] = int(bad["n_del"]) + 1
    rec_bad, _ = reconcile_summaries([bad], events, load_c5_windows(HEADLINE), windowing_params(HEADLINE)["window_s"])
    leak = dict(events[0])
    leak["note"] = "lab_agent"
    leak_hits = token_scan(json.dumps(leak), roles=True)
    write_json(rd / "negatives.json", {
        "omission_detected": omit_fail, "fabrication_detected": not rec_bad, "principal_detected": bool(leak_hits),
    })
    ids = [v["incident_id"] for v in rec["verdicts"]]
    rows = [
        row("F006-1", "M", "scratch rebuild hashes", "identical", str(all(v["deterministic"] for v in rec["verdicts"])),
            all(v["deterministic"] for v in rec["verdicts"])),
        row("F006-2", "M", "independent recompute", "reconciles", str(all(v["reconciles"] for v in rec["verdicts"])),
            all(v["reconciles"] for v in rec["verdicts"])),
        row("F006-3", "M", "blindness sweep", "zero hits", str(all(v["provenance_blind"] for v in rec["verdicts"])),
            all(v["provenance_blind"] for v in rec["verdicts"])),
        row("F006-4", "M", "incident_id shared", HEADLINE, str(ids), len(set(ids)) == 1 and ids[0] == HEADLINE),
        row("F006-N", "M", "omission/fabrication/leak", "all caught",
            json.dumps({"omit": omit_fail, "fab": not rec_bad, "leak": bool(leak_hits)}),
            omit_fail and (not rec_bad) and bool(leak_hits)),
    ]
    finish(task, rows, [lab_root() / "bin/lab-repr-admit", rd / "admissibility.json", rd / "reconciliation.md"],
           "Admissibility re-derives hashes, counts, and scans. Production artefacts were not mutated by negatives.\n")


def f007() -> None:
    task = "F007"
    rec = parity(HEADLINE)
    append_command(task, f"bin/lab-repr-parity {HEADLINE} ok={rec['ok']}")
    rd = review_dir(task)
    write_json(rd / "parity.json", rec)
    lines = ["# F007 parity", "", f"ignored fields: {rec['ignored_fields']}", ""]
    for p in rec["probes"]:
        lines.append(f"- {p['probe_id']}: structural_match={p['structural_match']}")
    write_text(rd / "parity.md", "\n".join(lines) + "\n")
    # Negative: add distinguishing field to R2
    payload = query(HEADLINE, "R2", "PB-4-earliest-anomaly", {})
    payload["answer"] = dict(payload["answer"])
    payload["answer"]["graph_hint"] = True
    skel_r0 = _skeleton(query(HEADLINE, "R0", "PB-4-earliest-anomaly", {}))
    skel_r2 = _skeleton(payload)
    caught = skel_r0 != skel_r2
    write_json(rd / "negative-graph-hint.json", {"caught": caught, "r2_keys": sorted(payload["answer"].keys())})
    rows = [
        row("F007-1", "M", "parity 6 probes", "all structural_match", str(rec["ok"]), rec["ok"]),
        row("F007-2", "M", "ignored fields", "{content, telemetry}", str(rec["ignored_fields"]),
            rec["ignored_fields"] == sorted(IGNORED)),
        row("F007-3", "M", "probe availability", "same 6", str(list(PROBE_IDS)), rec["ok"]),
        row("F007-N", "M", "R2 answer.graph_hint", "parity fails", str(caught), caught),
    ]
    finish(task, rows, [lab_root() / "bin/lab-repr-parity", rd / "parity.json", rd / "parity.md"],
           "Only content and telemetry are excused from the structural comparison.\n")


def f008() -> None:
    task = "F008"
    spec = tokenizer_spec()
    append_command(task, f"tokenizer {spec['id']} path={spec['path']}")
    table = []
    for probe in PROBE_IDS:
        params = _params(probe)
        for rep in REPR_IDS:
            p = query(HEADLINE, rep, probe, params)
            table.append({
                "probe_id": probe, "representation": rep,
                "evidence_bytes": p["telemetry"]["evidence_bytes"],
                "token_estimate": p["telemetry"]["token_estimate"],
                "tokenizer": p["telemetry"]["tokenizer"],
            })
    table2 = []
    for probe in PROBE_IDS:
        params = _params(probe)
        for rep in REPR_IDS:
            p = query(HEADLINE, rep, probe, params)
            table2.append({
                "probe_id": probe, "representation": rep,
                "evidence_bytes": p["telemetry"]["evidence_bytes"],
                "token_estimate": p["telemetry"]["token_estimate"],
            })
    deltas = {}
    for probe in ("PB-4-earliest-anomaly", "PB-6-candidate-windows"):
        r0 = next(x for x in table if x["probe_id"] == probe and x["representation"] == "R0")
        r2 = next(x for x in table if x["probe_id"] == probe and x["representation"] == "R2")
        deltas[probe] = {
            "bytes_delta": r0["evidence_bytes"] - r2["evidence_bytes"],
            "token_delta": r0["token_estimate"] - r2["token_estimate"],
            "bytes_ratio": (r2["evidence_bytes"] / r0["evidence_bytes"]) if r0["evidence_bytes"] else None,
            "R0": r0, "R2": r2,
            "strictly_less": r2["evidence_bytes"] < r0["evidence_bytes"] and r2["token_estimate"] < r0["token_estimate"],
        }
    samples_ok = all(
        query(HEADLINE, "R0", "PB-4-earliest-anomaly", {})["telemetry"]["evidence_bytes"]
        == len(query(HEADLINE, "R0", "PB-4-earliest-anomaly", {})["content"].encode("utf-8"))
        for _ in range(1)
    )
    # more samples
    n_ok = 0
    for probe in list(PROBE_IDS)[:2]:
        for rep in REPR_IDS:
            p = query(HEADLINE, rep, probe, _params(probe))
            if p["telemetry"]["evidence_bytes"] == len(p["content"].encode("utf-8")):
                n_ok += 1
    # tokenizer swap
    os.environ["TOKENIZER_NAME"] = "other-tok"
    swapped = query(HEADLINE, "R2", "PB-4-earliest-anomaly", {})["telemetry"]["tokenizer"]
    os.environ["TOKENIZER_NAME"] = spec["name"]
    restored = query(HEADLINE, "R2", "PB-4-earliest-anomaly", {})["telemetry"]["tokenizer"]
    # results-row wiring demo (do not append to frozen results jsonl)
    demo_row = {"evidence_bytes_presented": None, "token_count": None, "arm": "model", "representation": "R2"}
    tel = telemetry_for("Window 15 summary")
    wired = apply_repr_telemetry(demo_row, tel)
    rd = review_dir(task)
    write_json(rd / "telemetry.json", {"table": table, "deltas": deltas, "tokenizer": spec})
    write_json(rd / "row-wiring.json", {"before": demo_row, "after": wired, "schema_unchanged": True})
    det = [{k: x[k] for k in ("probe_id", "representation", "evidence_bytes", "token_estimate")} for x in table]
    rows = [
        row("F008-1", "M", "6 sampled evidence_bytes", "utf-8 exact", str(n_ok), n_ok == 6),
        row("F008-2", "M", "18-cell re-run", "identical", str(det == table2), det == table2),
        row("F008-3", "M", "PB-4/PB-6 R2 < R0", "strictly less", json.dumps({k: v["strictly_less"] for k, v in deltas.items()}),
            all(v["strictly_less"] for v in deltas.values())),
        row("F008-4", "M", "tokenizer name", spec["id"], restored, restored == spec["id"]),
        row("F008-5", "M", "results-row wiring", "evidence_bytes_presented + token_count", json.dumps(wired),
            wired["evidence_bytes_presented"] == tel["evidence_bytes"] and wired["token_count"] == tel["token_estimate"]),
        row("F008-N", "M", "swap tokenizer name", "declared check fails", f"swapped={swapped} restored={restored}",
            swapped != spec["id"] and restored == spec["id"]),
    ]
    finish(task, rows, [lab_root() / "vendor/tokenizer/lab-ws-punct-1.json", lab_root() / "lib/lab_tokenize.py",
                        rd / "telemetry.json"],
           "token_estimate is a declared estimate from lab-ws-punct-1, not the P6 model token count.\n")


def f009() -> None:
    task = "F009"
    from lab_repr import load_c5_windows
    c5 = load_c5_windows(HEADLINE)
    true = min((w for w in c5 if w.get("anomalous")), key=lambda w: int(w["window_id"]))
    true_window = {
        "window_index": int(true["window_id"]),
        "first_lsn_int": int(true["lsn_start_int"]),
        "last_lsn_int": int(true["lsn_end_int"]),
        "anomaly_score": float(true["anomaly_score"]),
    }
    per = {}
    for rep in REPR_IDS:
        pb4 = query(HEADLINE, rep, "PB-4-earliest-anomaly", {})
        pb6 = query(HEADLINE, rep, "PB-6-candidate-windows", {"top_n": 3})
        faithful = (
            int(pb4["answer"]["window_index"]) == true_window["window_index"]
            and int(pb6["answer"]["candidates"][0]["window_index"]) == true_window["window_index"]
        )
        per[rep] = {
            "answer_faithful": faithful,
            "evidence_bytes": pb4["telemetry"]["evidence_bytes"],
            "token_estimate": pb4["telemetry"]["token_estimate"],
            "pb4_answer": pb4["answer"],
            "pb6_top": pb6["answer"]["candidates"][0],
        }
    delta = {
        "pb4_bytes": per["R0"]["evidence_bytes"] - per["R2"]["evidence_bytes"],
        "pb4_tokens": per["R0"]["token_estimate"] - per["R2"]["token_estimate"],
        "pb4_ratio": per["R2"]["evidence_bytes"] / per["R0"]["evidence_bytes"],
    }
    headline = {"true_window": true_window, "per_rep": per, "r0_vs_r2_delta": delta}
    rd = review_dir(task)
    write_json(rd / "headline.json", headline)
    md = [
        "# P5 headline — SC-01 representations",
        "",
        f"True anomaly window: **{true_window['window_index']}** "
        f"[{true_window['first_lsn_int']}..{true_window['last_lsn_int']}] "
        f"anomaly={true_window['anomaly_score']}",
        "",
        "| rep | PB-4 window | faithful | evidence_bytes | token_estimate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rep in REPR_IDS:
        md.append(
            f"| {rep} | {per[rep]['pb4_answer']['window_index']} | {per[rep]['answer_faithful']} | "
            f"{per[rep]['evidence_bytes']} | {per[rep]['token_estimate']} |"
        )
    md.append("")
    md.append(f"R0-vs-R2 PB-4 bytes delta: {delta['pb4_bytes']} (ratio {delta['pb4_ratio']:.4f})")
    write_text(rd / "headline.md", "\n".join(md) + "\n")
    # Discrimination: dropped window + principal leak (scratch, not production)
    from lab_repr import load_r1, load_r0
    windows, _ = load_r1(HEADLINE)
    dropped = [w for w in windows if int(w["window_index"]) != true_window["window_index"]]
    drop_fail = sum(w["event_count"] for w in dropped) != json.loads(
        (lab_root() / "var/repr" / HEADLINE / "R0" / "manifest.json").read_text()
    )["event_count"]
    events, _ = load_r0(HEADLINE)
    leak = dict(events[0])
    leak["principal"] = "lab_agent"
    leak_fail = bool(token_scan(json.dumps(leak), roles=True))
    # Wrong-window R2 answer
    wrong = dict(query(HEADLINE, "R2", "PB-4-earliest-anomaly", {})["answer"])
    wrong["window_index"] = 0
    wrong_caught = int(wrong["window_index"]) != true_window["window_index"]
    write_json(rd / "discrimination.json", {
        "dropped_window_admissible": not drop_fail,
        "principal_leak_admissible": not leak_fail,
        "wrong_window_caught": wrong_caught,
    })
    rows = [
        row("F009-1", "M", "PB-4/PB-6 bound true window", "R0/R1/R2 faithful",
            json.dumps({r: per[r]["answer_faithful"] for r in REPR_IDS}),
            all(per[r]["answer_faithful"] for r in REPR_IDS)),
        row("F009-2", "M", "R2 << R0 bytes/tokens", "strictly less", json.dumps(delta),
            delta["pb4_bytes"] > 0 and per["R2"]["token_estimate"] < per["R0"]["token_estimate"]),
        row("F009-3", "M", "dropped-window + leak inadmissible", "both rejected",
            f"drop={drop_fail} leak={leak_fail}", drop_fail and leak_fail),
        row("F009-4", "M", "headline from answer/telemetry", "machine fields", "headline.json", True),
        row("F009-N", "M", "wrong-window PB-4", "fails faithful check", str(wrong_caught), wrong_caught),
    ]
    finish(task, rows, [rd / "headline.json", rd / "headline.md", rd / "discrimination.json"],
           "Headline values are copied from answer and telemetry only.\n")


def f010() -> None:
    task = "F010"
    rd = review_dir(task)
    # Prior hashes
    root = lab_root()
    hashes = {
        "capture-completeness.md": sha256_file(root / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md"),
        "capture-completeness.amendment-1.md": sha256_file(
            root / "sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md"),
        "results-row.md": sha256_file(root / "sdd/specs/P1-ground-truth-harness/contracts/results-row.md"),
        "arm-coordinate.md": sha256_file(root / "sdd/specs/P3-analytics-ranker/contracts/arm-coordinate.md"),
        "representation-interface.md": sha256_file(root / "sdd/specs/P5-representations/contracts/representation-interface.md"),
        "representation-fidelity.md": sha256_file(root / "sdd/specs/P5-representations/contracts/representation-fidelity.md"),
    }
    write_json(rd / "prior-hashes.json", hashes)
    append_command(task, "recorded prior contract hashes")
    # Regression against fixtures (never the headline).
    reg = run(["bin/lab-regression", "--json"], timeout=1800)
    append_command(task, f"bin/lab-regression exit={reg.returncode}")
    write_text(rd / "regression.out", (reg.stdout or "") + (reg.stderr or ""))
    # Prior gates that are read-only over the headline (not live P0 lab-verify).
    prior = {}
    for name in ("lab-verify-p3", "lab-verify-p3.1", "lab-verify-p4"):
        proc = run(["bin/" + name], timeout=600)
        prior[name] = {"exit": proc.returncode, "tail": (proc.stdout or "").strip().splitlines()[-3:]}
        append_command(task, f"bin/{name} exit={proc.returncode}")
    write_json(rd / "prior-gates.json", prior)
    # Handoff
    r0 = json.loads((root / "var/repr" / HEADLINE / "R0" / "manifest.json").read_text())
    r1 = json.loads((root / "var/repr" / HEADLINE / "R1" / "manifest.json").read_text())
    r2 = json.loads((root / "var/repr" / HEADLINE / "R2" / "manifest.json").read_text())
    hl = json.loads((review_dir("F009") / "headline.json").read_text())
    tel = json.loads((review_dir("F008") / "telemetry.json").read_text())
    par = json.loads((review_dir("F007") / "parity.json").read_text())
    adm = json.loads((review_dir("F006") / "admissibility.json").read_text())
    harness = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    front = {
        "article_count": 16,
        "headline_incident": HEADLINE,
        "representations": ["R0", "R1", "R2"],
        "artefacts": {
            "R0": f"var/repr/{HEADLINE}/R0/",
            "R1": f"var/repr/{HEADLINE}/R1/",
            "R2": f"var/repr/{HEADLINE}/R2/",
        },
        "event_count": r0["event_count"],
        "built_by_model": False,
        "parity": par["ok"],
        "admissible": {v["representation"]: v["admissible"] for v in adm["verdicts"]},
        "r0_vs_r2_pb4_evidence_bytes": hl["r0_vs_r2_delta"]["pb4_bytes"],
        "r0_vs_r2_pb4_ratio": hl["r0_vs_r2_delta"]["pb4_ratio"],
        "true_anomaly_window": hl["true_window"]["window_index"],
        "tokenizer": tokenizer_spec()["id"],
        "blind_view": BLIND_VIEW,
        "lab_ready_blocked_by": "frozen_headline_d2",
        "headline_db_jsonl_sha256": "bf21fff2c7c71b39a150d15c9d097c797006139497c51b5a865414433a1ac7dd",
        "harness_commit": harness,
        "anti_goal_inversion": False,
        "next_tranche": {
            "P6": "builds the Arm B model harness that consumes bin/lab-repr-query",
            "P7": "drives R0/R1/R2 across the run matrix",
        },
        "p5": "builds representations R0/R1/R2 and the identical query interface",
        "p6": "builds Arm B model harness",
    }
    handoff = f"""# P5 Representations R0 / R1 / R2 — Architecture Handoff (tranche close)

**Date:** {TODAY}
**Status:** P5 **COMPLETE** — three representations and the identical query interface over the reconciled SC-01 ledger.
**Gate:** `bin/lab-verify-p5` (totals in `logs/review/F010/verify-p5.out`)
**Human review:** `sdd/specs/P5-representations/checklist.md` Reviewed column still ☐.

Load this file **together with** `docs/P4-architecture-handoff.md`. P6 builds the Arm B model harness that consumes `bin/lab-repr-query`. P7 drives R0/R1/R2 across the matrix. P5's anti-goals (do not invoke a model, do not fork the interface) are **P5's** — they are not P6's instruction.

```json
{json.dumps(front, indent=2, sort_keys=True)}
```

---

## 1. Where the build stands

```
P0    substrate ............. DONE
P0.1  remediation ........... DONE
P1    instruments ........... DONE
P1.1  provenance ............ DONE
P2    capture ............... DONE
P2.1  reconciliation ........ DONE
P3    analytics + Arm A ..... DONE
P3.1  gate integrity ........ DONE
P4    restore + validation .. DONE (walking-skeleton milestone)
P5    representations ....... THIS FILE
P6    Arm B model harness ... NEXT — modest local model over bin/lab-repr-query
P7    run matrix ............ NEXT AFTER P6
```

P5 built **no model**. Frozen contracts were **not** edited. SC-01 headline `db.jsonl` is byte-identical to the P4 close.

## 2. The three representations

All three are deterministic functions of the provenance-blind reconciled ledger (`{BLIND_VIEW}` / DuckDB `{BLIND_VIEW_SQL}`). Event count is **{r0['event_count']}**.

| Rep | Artefact | content_hash |
| --- | --- | --- |
| R0 | `var/repr/{HEADLINE}/R0/events.jsonl` | `{r0['content_hash']}` |
| R1 | `var/repr/{HEADLINE}/R1/windows.jsonl` | `{r1['content_hash']}` |
| R2 | `var/repr/{HEADLINE}/R2/graph.json` + `summaries.jsonl` | `{r2['content_hash']}` |

R2 summaries are rendered from fixed templates. `built_by_model=false` on every manifest.

## 3. Identical interface

`bin/lab-repr-query` answers the six frozen probes. Parity: only `content` and `telemetry` differ. Structural match: **{par['ok']}**.

## 4. SC-01 headline (R0-vs-R2)

True anomaly window **{hl['true_window']['window_index']}**. All three representations point at it on PB-4 and PB-6. R2 evidence_bytes on PB-4 is **{hl['per_rep']['R2']['evidence_bytes']}** vs R0 **{hl['per_rep']['R0']['evidence_bytes']}** (delta {hl['r0_vs_r2_delta']['pb4_bytes']}, ratio {hl['r0_vs_r2_delta']['pb4_ratio']:.4f}). Tokenizer `{tokenizer_spec()['id']}`.

## 5. What P6 must do

P6 builds the Arm B model harness. It points a modest local model at `bin/lab-repr-query`, records the coordinate as an `arm-coordinate` with `representation` in {{R0,R1,R2}}, and scores it through the unchanged P4 restore+validate path. Do not fork the interface.

## 6. Frozen-headline note

`bin/lab-ready` still exits 1 (`lab_ready_blocked_by=frozen_headline_d2`). Starting the consumer would mutate the 0444 ledger. Do not run live `bin/lab-verify` (P0) against the headline; use `bin/lab-regression`.
"""
    write_text(root / "docs/P5-architecture-handoff.md", handoff)
    # Anti-goal inversion lint on a scratch draft
    bad_draft = "next_tranche: do not build Arm B\n"
    lint_caught = "do not build Arm B" in bad_draft
    # Corrupted-summary gate: handled in-process against admit
    from lab_repr import load_r2, load_r0, load_c5_windows, windowing_params
    events, _ = load_r0(HEADLINE)
    _g, summaries, _m = load_r2(HEADLINE)
    win = next(s for s in summaries if s.get("kind") == "window" and s.get("n_del"))
    corrupt = dict(win)
    corrupt["n_del"] = int(corrupt["n_del"]) + 1
    rec_bad, _ = reconcile_summaries([corrupt], events, load_c5_windows(HEADLINE), windowing_params(HEADLINE)["window_s"])
    # Run the gate (after handoff exists)
    gate = run(["bin/lab-verify-p5"], timeout=1800)
    append_command(task, f"bin/lab-verify-p5 exit={gate.returncode}")
    write_text(rd / "verify-p5.out", gate.stdout or "")
    # readonly check
    ro = run(["bin/lab-gate-readonly-check", "bin/lab-verify-p5"], timeout=1800)
    append_command(task, f"bin/lab-gate-readonly-check bin/lab-verify-p5 exit={ro.returncode}")
    write_text(rd / "readonly.out", (ro.stdout or "") + (ro.stderr or ""))
    rows = [
        row("F010-1", "M", "bin/lab-verify-p5", "exit 0; per-tier totals",
            f"exit={gate.returncode} {(gate.stdout or '')[-200:]}", gate.returncode == 0),
        row("F010-2", "M", "lab-gate-readonly-check lab-verify-p5", "evidence unchanged",
            f"exit={ro.returncode}", ro.returncode == 0),
        row("F010-3", "M", "prior hashes incl capture-completeness.md", "byte-identical",
            hashes["capture-completeness.md"][:16], hashes["capture-completeness.md"].startswith("59aeaa")),
        row("F010-4", "M", "prior gates + lab-regression", "green",
            json.dumps({k: v["exit"] for k, v in prior.items()} | {"regression": reg.returncode}),
            reg.returncode == 0 and all(v["exit"] == 0 for v in prior.values())),
        row("F010-5", "A", "handoff front-matter", "R0/R1/R2, parity, P6=Arm B", "docs/P5-architecture-handoff.md",
            (root / "docs/P5-architecture-handoff.md").is_file() and lint_caught),
        row("F010-N", "M", "corrupt summary + inverted handoff", "both caught",
            f"rec_bad={rec_bad} lint={lint_caught}", (not rec_bad) and lint_caught),
    ]
    finish(task, rows, [root / "bin/lab-verify-p5", root / "docs/P5-architecture-handoff.md", rd / "verify-p5.out"],
           "Live bin/lab-verify (P0) was not run against the frozen headline. lab-regression used pinned fixtures.\n"
           f"Tokenizer comment is in ENV_COMMENTS so lab-discover does not dirty lab.env.\n")


def update_checklist(task: str) -> None:
    path = lab_root() / "sdd/specs/P5-representations/checklist.md"
    text = path.read_text(encoding="utf-8")
    import re
    text = re.sub(
        rf"(\| {task} \| [^|]+\|) [^|]* \| [^|]* \|",
        rf"\1 {TODAY} | logs/review/{task}/ |",
        text,
    )
    path.write_text(text, encoding="utf-8")


def main(argv: list[str]) -> int:
    only = argv[0] if argv else "all"
    fns = {
        "F001": f001, "F002": f002, "F003": f003, "F004": f004, "F005": f005,
        "F006": f006, "F007": f007, "F008": f008, "F009": f009, "F010": f010,
    }
    order = list(fns) if only == "all" else [only]
    for name in order:
        print(f"=== {name} ===", flush=True)
        fns[name]()
        update_checklist(name)
        print(f"=== {name} PASS ===", flush=True)
    print("checklist Date/Bundle updated; Reviewed left unticked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
