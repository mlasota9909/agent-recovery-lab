"""lab-p9-sweep (N004): SC-01 x {R0,R1,R2} x 3 models x K=5 through the guarded
interface, scored by the unchanged P4 path.

Writes ONLY results/sweep-runs.jsonl (ADR-P9-1). Never appends to results/SC-01.jsonl
or results/matrix.jsonl. Resumable per cell. A cell that cannot proceed becomes a
run_failure row with a diagnosis (Article XIX); the batch continues. A
"cannot determine" completion is a refusal (Article VIII), never coerced.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from lab_arm_b_score import p4_score, results_row
from lab_p3_util import EXIT_ASSERT, canonical_json, die
from lab_p7 import ledger_idempotency
from lab_evaluate_arm import harness_commit_at_production
from lab_p9 import DEFAULT_K, REPR_IDS, SWEEP_ID, load_model_set, root
from lab_repr import HEADLINE

SCENARIO = "SC-01"
INCIDENT = HEADLINE


def sweep_path() -> Path:
    return root() / "results" / "sweep-runs.jsonl"


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_bin(name: str, argv: list[str], env_extra: dict | None = None,
            timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib")
    if env_extra:
        env.update(env_extra)
    return subprocess.run([str(root() / "bin" / name), *argv], cwd=str(root()),
                          text=True, capture_output=True, check=False, env=env, timeout=timeout)


def cell_id(rep: str, alias: str, k: int) -> str:
    return f"{SCENARIO}|{rep}|{alias}|{k}"


def load_done() -> dict[str, dict]:
    done: dict[str, dict] = {}
    if sweep_path().is_file():
        for line in sweep_path().read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["cell_id"]] = r
    return done


def append(rec: dict) -> None:
    sweep_path().parent.mkdir(parents=True, exist_ok=True)
    with sweep_path().open("a", encoding="utf-8") as fh:
        fh.write(canonical_json(rec) + "\n")


def assemble_prompt(rep: str, cache: dict) -> Path:
    if rep in cache:
        return cache[rep]
    out = root() / "var" / "arm_b" / "_p9sweep" / f"{INCIDENT}-{rep}.prompt"
    out.parent.mkdir(parents=True, exist_ok=True)
    p = run_bin("lab-arm-b-prompt", ["--incident", INCIDENT, "--representation", rep, "--out", str(out)])
    if p.returncode != 0:
        raise RuntimeError(f"lab-arm-b-prompt {rep}: {p.stderr.strip() or p.stdout.strip()}")
    cache[rep] = out
    return out


def run_cell(rep: str, model: dict, k: int, harness_commit: str, prompt_cache: dict) -> dict:
    alias = model["alias"]
    cid = cell_id(rep, alias, k)
    base = {
        "cell_id": cid,
        "sweep_id": SWEEP_ID,
        "scenario": SCENARIO,
        "incident": INCIDENT,
        "representation": rep,
        "model_alias": alias,
        "model_family": model.get("family"),
        "tokenizer_id": model.get("tokenizer_id"),
        "model_digest": model.get("model_digest"),
        "replicate_index": k,
        "run_ts": utc(),
    }
    workdir = root() / "var" / "arm_b" / "_p9sweep" / INCIDENT / rep / alias / f"k{k}"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        prompt_path = assemble_prompt(rep, prompt_cache)
        model_json = workdir / "model.json"
        p = run_bin("lab-p9-model", ["--alias", alias, "--prompt-file", str(prompt_path),
                                     "--out", str(model_json)])
        if p.returncode != 0:
            raise RuntimeError(f"lab-p9-model: {p.stderr.strip() or p.stdout.strip()}")
        mrec = json.loads(model_json.read_text(encoding="utf-8"))
        if not mrec.get("containment_verified"):
            raise RuntimeError("containment_verified=false for this invocation")
        completion_path = workdir / "completion.txt"
        completion_path.write_text(mrec.get("completion") or "", encoding="utf-8")
        extract_json = workdir / "extract.json"
        p = run_bin("lab-arm-b-extract", ["--completion", str(completion_path),
                                          "--incident", INCIDENT, "--representation", rep,
                                          "--out", str(extract_json)],
                    env_extra={"MODEL_ID": alias})
        if p.returncode != 0:
            raise RuntimeError(f"lab-arm-b-extract: {p.stderr.strip() or p.stdout.strip()}")
        extracted = json.loads(extract_json.read_text(encoding="utf-8"))
        outcome = extracted.get("outcome")
        arm = extracted.get("arm_coordinate")
        score = None
        if outcome == "determination" and arm:
            try:
                score = p4_score(INCIDENT, arm)
            except SystemExit as exc:               # p4_score dies loud; keep the batch going
                raise RuntimeError(f"P4 score failed for lsn {arm.get('lsn_int')}: {exc}") from exc
        ev_bytes = prompt_path.stat().st_size
        row = results_row(INCIDENT, rep, k, extracted, mrec, score, ev_bytes)
        row["model_id"] = alias
        row["harness_commit"] = harness_commit
        rec = dict(base)
        rec.update({
            "outcome": outcome,
            "finish_reason": mrec.get("finish_reason"),
            "raw_completion": mrec.get("completion"),
            "raw_completion_sha256": mrec.get("completion_sha256"),
            "reasoning_chars": len(mrec.get("reasoning_content") or ""),
            "prompt_tokens": mrec.get("prompt_tokens"),
            "completion_tokens": mrec.get("completion_tokens"),
            "latency_ms": mrec.get("latency_ms"),
            "containment_verified": mrec.get("containment_verified"),
            "refusal_reason": extracted.get("refusal_reason"),
            "results_row_id": row["run_id"],
            "results_row": row,
            "p4": None if score is None else {
                "restore_verdict": score["restore_verdict"],
                "p4_consistency_verdict": score["p4_consistency_verdict"],
                "damage_rows_retained": score["damage_rows_retained"],
                "legit_rows_lost": score["legit_rows_lost"],
                "cached": score["cached"],
                "coord_error_bytes": row.get("coord_error_bytes"),
                "coord_error_ms": row.get("coord_error_ms"),
                "coord_direction": row.get("coord_direction"),
            },
        })
        return rec
    except (Exception, SystemExit) as exc:  # noqa: BLE001 -- a failed cell is a row, not an abort (Article XIX)
        rec = dict(base)
        rec.update({
            "outcome": "run_failure",
            "failure_reason": str(exc)[:500],
            "traceback": traceback.format_exc()[-1200:],
            "results_row_id": f"r_{stamp()}_{secrets.token_hex(3)}",
            "results_row": None,
            "p4": None,
        })
        return rec


def run(k: int = DEFAULT_K, force: bool = False, only_rep: str | None = None,
        only_model: str | None = None) -> dict:
    models = load_model_set()["models"]
    if only_model:
        models = [m for m in models if m["alias"] == only_model]
    reps = [only_rep] if only_rep else list(REPR_IDS)
    harness_commit = harness_commit_at_production()  # refuses on a dirty tree (Article XIV)
    ledger = ledger_idempotency(INCIDENT)
    if not ledger["ok"]:
        die(EXIT_ASSERT, f"assertion failed: SC-01 ledger idempotency broken: {ledger}")
    done = load_done()
    prompt_cache: dict = {}
    planned = 0
    ran = []
    for rep in reps:
        for model in models:
            for kk in range(k):
                planned += 1
                cid = cell_id(rep, model["alias"], kk)
                if cid in done and not force:
                    ran.append({"cell_id": cid, "skipped": True,
                                "outcome": done[cid].get("outcome")})
                    continue
                rec = run_cell(rep, model, kk, harness_commit, prompt_cache)
                append(rec)
                ran.append({"cell_id": cid, "skipped": False, "outcome": rec["outcome"]})
    return {"planned": planned, "ran": ran, "ledger_idempotency": ledger}


def completeness() -> dict:
    rows = [json.loads(l) for l in sweep_path().read_text(encoding="utf-8").splitlines() if l.strip()]
    planned = len(REPR_IDS) * len(load_model_set()["models"]) * DEFAULT_K
    by_cell: dict[str, list] = {}
    for r in rows:
        by_cell.setdefault(r["cell_id"], []).append(r)
    latest = {cid: recs[-1] for cid, recs in by_cell.items()}
    det = sum(1 for r in latest.values() if r["outcome"] == "determination")
    ref = sum(1 for r in latest.values() if r["outcome"] == "refusal")
    fail = sum(1 for r in latest.values() if r["outcome"] == "run_failure")
    # sidecar<->embedded join integrity
    join_ok = all(
        (r["outcome"] == "run_failure") or
        (r.get("results_row") and r["results_row"].get("run_id") == r.get("results_row_id"))
        for r in latest.values()
    )
    det_have_p4 = all(
        r["p4"] is not None and r["p4"].get("restore_verdict")
        for r in latest.values() if r["outcome"] == "determination"
    )
    return {
        "planned": planned,
        "distinct_cells": len(latest),
        "rows_total_incl_superseded": len(rows),
        "determinations": det,
        "refusals": ref,
        "run_failures": fail,
        "rows_equal_planned": len(latest) == planned and (det + ref + fail) == planned,
        "sidecar_embedded_join_ok": join_ok,
        "determinations_carry_p4_verdict": det_have_p4,
        "ok": (len(latest) == planned and (det + ref + fail) == planned
               and join_ok and det_have_p4),
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-p9-sweep")
    p.add_argument("--k", type=int, default=DEFAULT_K)
    p.add_argument("--force", action="store_true")
    p.add_argument("--representation", choices=REPR_IDS)
    p.add_argument("--model")
    p.add_argument("--completeness", action="store_true")
    p.add_argument("--review", default=str(root() / "logs" / "review" / "N004"))
    args = p.parse_args(argv)
    review = Path(args.review)
    review.mkdir(parents=True, exist_ok=True)
    if args.completeness:
        rec = completeness()
        (review / "sweep-completeness.json").write_text(
            json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(rec, indent=2, sort_keys=True))
        return 0 if rec["ok"] else EXIT_ASSERT
    out = run(k=args.k, force=args.force, only_rep=args.representation, only_model=args.model)
    from collections import Counter
    c = Counter(r["outcome"] for r in out["ran"])
    print(json.dumps({"planned": out["planned"], "outcomes": dict(c),
                      "ledger_ok": out["ledger_idempotency"]["ok"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
