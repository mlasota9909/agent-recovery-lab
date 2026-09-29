"""lab-p10-sweep (Q004): SC-01 x {R0,R2} x 7 scale targets x 3 models x K=5.

Writes ONLY results/scaling-runs.jsonl (frozen C5 keys) and results/scaling-runs-detail.jsonl
(diagnostics keyed by scale_run_id). Never touches results/sweep-runs.jsonl, results/SC-*.jsonl
or any ledger. Resumable per cell; the latest row for a scale_run_id supersedes earlier ones
(retained, Article XIX). Scoring = unchanged P4 on real rows + ledger replay of padded rows
(scale-generator.amendment-1 A4). Feasibility per scaling-analysis-plan.amendment-1 P1-P3.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
from collections import Counter
from pathlib import Path

from lab_p10 import (
    CONTEXT_WINDOWS, DEFAULT_K, INCIDENT, MAX_TOKENS, MODEL_SHORT, PRIMARY_REPS, SCALE_TARGETS,
    SCENARIO, SEED, prereg_check, root, scaled_root, scaling_detail_path, scaling_runs_path,
    sha256_text, utc,
)
from lsn import lsn_int

C5_KEYS = (
    "scale_run_id", "scenario", "representation", "scale_target", "model_id", "replicate",
    "canonical_tokens", "model_prompt_tokens", "context_window", "outcome", "verdict",
    "damage_rows_retained", "legit_rows_lost", "oracle_optimum_lsn_int", "chosen_lsn_int",
    "guard_pass", "seed", "harness_commit",
)
OUTCOMES = ("accepted", "refusal_genuine", "refusal_parser", "infeasible_context", "run_failure")


def scale_run_id(target: int, rep: str, alias: str, k: int) -> str:
    return f"sc01-s{target}-{rep.lower()}-{MODEL_SHORT[alias]}-k{k}"


def backends() -> dict:
    p = root() / "var" / "model" / "p10-backends.json"
    if not p.is_file():
        raise RuntimeError(f"{p} missing (local, gitignored alias->backend map)")
    return json.loads(p.read_text(encoding="utf-8"))


def _post(url: str, body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def model_prompt_tokens(alias: str, prompt: str) -> tuple[int, str]:
    """Backend's own count for the chat request (plan amendment P3)."""
    b = backends()[alias]
    base = b["backend"][:-3] if b["backend"].endswith("/v1") else b["backend"]
    try:
        r = _post(base + "/tokenize", {"model": b["served_model"],
                                       "messages": [{"role": "user", "content": prompt}]})
        if isinstance(r.get("count"), int):
            return int(r["count"]), "tokenize-messages"
    except Exception:  # noqa: BLE001 -- fall through to the prompt+overhead method
        pass
    r = _post(base + "/tokenize", {"model": b["served_model"], "prompt": prompt, "add_special_tokens": False})
    toks = r.get("tokens") if isinstance(r.get("tokens"), list) else r.get("token_ids")
    n = int(r["count"]) if isinstance(r.get("count"), int) else len(toks or [])
    return n + chat_overhead(alias), "tokenize-prompt+overhead"


_OVERHEAD: dict[str, int] = {}


def chat_overhead(alias: str) -> int:
    path = root() / "logs" / "review" / "Q004" / "chat-overhead.json"
    if not _OVERHEAD and path.is_file():
        _OVERHEAD.update(json.loads(path.read_text(encoding="utf-8")))
    if alias not in _OVERHEAD:
        raise RuntimeError(f"no measured chat-template overhead for {alias}; run --measure-overhead")
    return int(_OVERHEAD[alias])


OVERHEAD_PROBE = "Reply with exactly one word: ok"


def measure_overhead(alias: str) -> dict:
    """Plan amendment P3 fallback: chat-template overhead = usage.prompt_tokens of one real
    submission of a fixed neutral probe minus /tokenize(probe). Never a sweep prompt."""
    from lab_p9_model import invoke
    b = backends()[alias]
    base = b["backend"][:-3] if b["backend"].endswith("/v1") else b["backend"]
    r = _post(base + "/tokenize", {"model": b["served_model"], "prompt": OVERHEAD_PROBE, "add_special_tokens": False})
    toks = r.get("tokens") if isinstance(r.get("tokens"), list) else r.get("token_ids")
    raw = int(r["count"]) if isinstance(r.get("count"), int) else len(toks or [])
    rec = invoke(alias, OVERHEAD_PROBE)
    overhead = int(rec["prompt_tokens"]) - raw
    path = root() / "logs" / "review" / "Q004" / "chat-overhead.json"
    cur = json.loads(path.read_text()) if path.is_file() else {}
    cur[alias] = overhead
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cur, indent=1, sort_keys=True) + "\n")
    return {"alias": alias, "probe_raw_tokens": raw, "usage_prompt_tokens": rec["prompt_tokens"],
            "overhead": overhead, "containment_verified": rec["containment_verified"]}


def identity_check(alias: str) -> dict:
    """Live identity vs pin before any of the model's cells (containment R2d, P1)."""
    from lab_p9 import backend_served_digest, load_model_set, tokenizer_fingerprint
    m = next(x for x in load_model_set()["models"] if x["alias"] == alias)
    b = backends()[alias]
    out = {"alias": alias}
    try:
        tf = tokenizer_fingerprint(b["backend"], b["served_model"])
        out["tokenizer_fingerprint"] = tf.get("fingerprint")
        if not tf.get("ok"):
            out["error"] = f"tokenizer probe failed: {tf.get('error')}"[:300]
        out["tokenizer_ok"] = tf.get("ok") and tf.get("fingerprint") == m["tokenizer_probe"]["fingerprint"]
        dg = backend_served_digest(b["backend"], b["served_model"])
        out["served_max_model_len"] = (dg.get("identity") or {}).get("max_model_len")
        out["window_ok"] = out["served_max_model_len"] == CONTEXT_WINDOWS[alias]
        if m.get("model_digest_kind") == "backend_immutable_identity":
            out["digest_ok"] = dg.get("model_digest") == m["model_digest"]
        else:
            out["digest_ok"] = True   # weights_sha256 pin re-verified out of band (Q004 bundle)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
    out["ok"] = bool(out.get("tokenizer_ok") and out.get("window_ok") and out.get("digest_ok"))
    return out


# --- env helpers ---------------------------------------------------------------------

def run_bin(name: str, argv: list[str], env_extra: dict | None = None, timeout: int = 1800):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib")
    if env_extra:
        env.update(env_extra)
    return subprocess.run([str(root() / "bin" / name), *argv], cwd=str(root()), text=True,
                          capture_output=True, check=False, env=env, timeout=timeout)


def padded_env(target: int) -> dict:
    d = scaled_root(target)
    return {"EVIDENCE_ROOT": str(d / "evidence"), "LAB_REPR_ROOT": str(d / "repr")}


REAL_EVIDENCE_ROOT = None


def real_env() -> dict:
    return {"EVIDENCE_ROOT": REAL_EVIDENCE_ROOT}


# --- prompts, oracle-side descriptives ----------------------------------------------

def assemble(target: int, rep: str) -> tuple[str, bool]:
    """Re-assemble through the single guarded choke point; must equal the generator's prompt."""
    from lab_arm_b_prompt import assemble as _assemble
    keep = {k: os.environ.get(k) for k in ("EVIDENCE_ROOT", "LAB_REPR_ROOT")}
    os.environ.update(padded_env(target))
    try:
        text = _assemble(INCIDENT, rep, scratch_dir=scaled_root(target) / "guard")
    finally:
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    gen = (scaled_root(target) / "prompts" / f"{rep}.prompt").read_text(encoding="utf-8")
    if text != gen:
        raise RuntimeError(f"re-assembled {rep} prompt at {target} differs from the generator's")
    return text, True


def descriptives(target: int, prompt_r0: str) -> dict:
    """Oracle-side, after generation: visible windows and the damage's relative position."""
    ed = scaled_root(target) / "evidence" / "SC-01" / INCIDENT
    an = [json.loads(x) for x in (ed / "p3" / "anomaly.jsonl").read_text(encoding="utf-8").splitlines() if x]
    top = sorted(an, key=lambda w: (-float(w["anomaly_score"]), int(w["window_id"])))[:3]
    inj_xid = int(json.loads((ed / "injection.json").read_text(encoding="utf-8"))["xid"])
    content = prompt_r0.split("<<<ARM_B_CONTENT", 1)[1].split("ARM_B_CONTENT>>>", 1)[0]
    pos = None
    off = 0
    for line in content.splitlines(keepends=True):
        if line.strip():
            try:
                if int(json.loads(line).get("xid", -1)) == inj_xid:
                    pos = off / max(len(content), 1)
                    break
            except json.JSONDecodeError:
                pass
        off += len(line)
    return {"visible_windows": [int(w["window_id"]) for w in top],
            "malicious_relative_position_r0": None if pos is None else round(pos, 6)}


def padded_rows_lost(target: int, chosen_lsn: int, optimum_lsn: int) -> int:
    """P4's own rule and unit (lab_validate legit_vs_optimum) applied to the padded
    manifest records: sum row_count where chosen < commit_lsn <= optimum."""
    from lab_p10_scale import load_real
    ed = scaled_root(target) / "evidence" / "SC-01" / INCIDENT
    n_real = _real_manifest_len()
    total = 0
    for line in (ed / "workload-manifest.jsonl").read_text(encoding="utf-8").splitlines()[n_real:]:
        m = json.loads(line)
        c = lsn_int(m["commit_lsn"])
        if chosen_lsn < c <= optimum_lsn:
            total += int(m.get("row_count") or len(m.get("row_ids") or []))
    return total


_REAL_MAN_LEN: list[int] = []


def _real_manifest_len() -> int:
    if not _REAL_MAN_LEN:
        p = Path(REAL_EVIDENCE_ROOT) / "SC-01" / INCIDENT / "workload-manifest.jsonl"
        _REAL_MAN_LEN.append(len(p.read_text(encoding="utf-8").splitlines()))
    return _REAL_MAN_LEN[0]


INFRA_REASON_PREFIXES = ("incident range unavailable",)


def resolver_healthy(target: int) -> bool:
    """The coordinate service answers for the frozen optimum under the padded env."""
    p = run_bin("lab-coordinate", ["--lsn", "1/E1000000"], env_extra=padded_env(target), timeout=120)
    return p.returncode == 0


def classify(extracted: dict, completion: str, target: int) -> str:
    """Generator amendment A5. An extractor refusal caused by the harness (incident metadata
    missing, coordinate service down) is a run_failure, not a model outcome."""
    if extracted.get("outcome") == "determination" and extracted.get("arm_coordinate"):
        return "accepted"
    reason = extracted.get("refusal_reason") or ""
    if reason.startswith(INFRA_REASON_PREFIXES):
        raise RuntimeError(f"extractor infrastructure fault: {reason[:300]}")
    if reason.startswith("unresolvable locator") and not resolver_healthy(target):
        raise RuntimeError(f"coordinate service unhealthy during extraction: {reason[:300]}")
    from lab_arm_b_extract import tagged_lines
    coords, refusals = tagged_lines(completion or "")
    # C3: genuine = the model explicitly declined and offered no coordinate. A completion
    # that writes and then repeats its REFUSAL line still offers no locator, so it is genuine.
    if refusals and not coords:
        return "refusal_genuine"
    return "refusal_parser"


# --- one cell ------------------------------------------------------------------------

def run_cell(target: int, rep: str, model: dict, k: int, prompt: str, canon: int,
             guard_pass: bool, optimum_lsn: int, harness_commit: str, desc: dict) -> tuple[dict, dict]:
    from lab_tokenize import token_estimate
    alias = model["alias"]
    sid = scale_run_id(target, rep, alias, k)
    row = {key: None for key in C5_KEYS}
    row.update({"scale_run_id": sid, "scenario": SCENARIO, "representation": rep, "scale_target": target,
                "model_id": alias, "replicate": k, "canonical_tokens": canon,
                "context_window": CONTEXT_WINDOWS[alias], "oracle_optimum_lsn_int": optimum_lsn,
                "guard_pass": guard_pass, "seed": SEED, "harness_commit": harness_commit})
    content = prompt.split("<<<ARM_B_CONTENT", 1)[1].split("ARM_B_CONTENT>>>", 1)[0]
    det = {"scale_run_id": sid, "row_utc": utc(), "prompt_sha256": sha256_text(prompt),
           "content_canonical_tokens": token_estimate(content), **desc}
    work = root() / "var" / "arm_b" / "_p10sweep" / f"s{target}" / rep / alias / f"k{k}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        n_tok, method = model_prompt_tokens(alias, prompt)
        row["model_prompt_tokens"] = n_tok
        det["token_count_method"] = method
        det["request_tokens_with_budget"] = n_tok + MAX_TOKENS
        if n_tok + MAX_TOKENS > CONTEXT_WINDOWS[alias]:
            row["outcome"] = "infeasible_context"
            det["submitted"] = False
            return row, det
        det["submitted"] = True
        prompt_path = work / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        model_json = work / "model.json"
        p = run_bin("lab-p9-model", ["--alias", alias, "--prompt-file", str(prompt_path), "--out", str(model_json)],
                    env_extra=real_env(), timeout=2400)
        if p.returncode != 0:
            raise RuntimeError(f"lab-p9-model: {(p.stderr or p.stdout).strip()[-400:]}")
        mrec = json.loads(model_json.read_text(encoding="utf-8"))
        if not mrec.get("containment_verified"):
            raise RuntimeError("containment_verified=false")
        row["model_prompt_tokens"] = int(mrec.get("prompt_tokens") or n_tok)
        det.update({"predicted_prompt_tokens": n_tok, "finish_reason": mrec.get("finish_reason"),
                    "completion_tokens": mrec.get("completion_tokens"), "latency_ms": mrec.get("latency_ms"),
                    "raw_completion": mrec.get("completion"), "raw_completion_sha256": mrec.get("completion_sha256"),
                    "reasoning_chars": len(mrec.get("reasoning_content") or ""),
                    "containment_verified": True, "outbound_public_peers": mrec.get("outbound_public_peers")})
        completion_path = work / "completion.txt"
        completion_path.write_text(mrec.get("completion") or "", encoding="utf-8")
        extract_json = work / "extract.json"
        p = run_bin("lab-arm-b-extract", ["--completion", str(completion_path), "--incident", INCIDENT,
                                          "--representation", rep, "--out", str(extract_json)],
                    env_extra={**padded_env(target), "MODEL_ID": alias})
        if p.returncode != 0:
            raise RuntimeError(f"lab-arm-b-extract: {(p.stderr or p.stdout).strip()[-400:]}")
        extracted = json.loads(extract_json.read_text(encoding="utf-8"))
        outcome = classify(extracted, mrec.get("completion") or "", target)
        row["outcome"] = outcome
        det["refusal_reason"] = extracted.get("refusal_reason")
        det["arm_coordinate"] = extracted.get("arm_coordinate")
        if outcome == "accepted":
            arm = extracted["arm_coordinate"]
            chosen = int(arm["lsn_int"])
            row["chosen_lsn_int"] = chosen
            p4 = p4_score_real(arm)
            pad_lost = padded_rows_lost(target, chosen, optimum_lsn)
            verdict = p4["restore_verdict"]
            if verdict == "correct" and pad_lost > 0:      # guard; A4 derivation says unreachable
                verdict = "incorrect_safe"
                det["verdict_guard_fired"] = True
            row["verdict"] = verdict
            row["damage_rows_retained"] = int(p4["damage_rows_retained"])
            row["legit_rows_lost"] = int(p4["legit_rows_lost"]) + pad_lost
            det["p4"] = {k2: p4[k2] for k2 in ("restore_verdict", "p4_consistency_verdict",
                                                 "damage_rows_retained", "legit_rows_lost", "cached")}
            det["padded_legit_rows_lost"] = pad_lost
        return row, det
    except (Exception, SystemExit) as exc:  # noqa: BLE001 -- a failed cell is a row (Article XIX)
        row["outcome"] = "run_failure"
        det["failure_reason"] = str(exc)[:600]
        det["traceback"] = traceback.format_exc()[-1500:]
        return row, det


def unavailable_row(target, rep, m, k, canon, guard_pass, optimum, harness_commit, ident, desc):
    alias = m["alias"]
    row = {key: None for key in C5_KEYS}
    row.update({"scale_run_id": scale_run_id(target, rep, alias, k), "scenario": SCENARIO, "representation": rep,
                "scale_target": target, "model_id": alias, "replicate": k, "canonical_tokens": canon,
                "context_window": CONTEXT_WINDOWS[alias], "oracle_optimum_lsn_int": optimum,
                "guard_pass": guard_pass, "seed": SEED, "harness_commit": harness_commit, "outcome": "run_failure"})
    det = {"scale_run_id": row["scale_run_id"], "row_utc": utc(), "submitted": False, **desc,
           "failure_reason": ("model backend failed its live identity check (containment R2d / "
                              f"reachability): {json.dumps({k2: ident.get(k2) for k2 in ('tokenizer_ok', 'window_ok', 'digest_ok', 'served_max_model_len', 'error')})}")}
    return row, det


def p4_score_real(arm: dict) -> dict:
    """Unchanged p4_score with EVIDENCE_ROOT on the frozen root (P4 part of A4). The frozen
    die() writes its reason to stderr; capture it so a run_failure carries its diagnosis."""
    import contextlib
    import io
    from lab_arm_b_score import p4_score
    keep = os.environ.get("EVIDENCE_ROOT")
    os.environ["EVIDENCE_ROOT"] = REAL_EVIDENCE_ROOT
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            return p4_score(INCIDENT, arm)
    except SystemExit as exc:
        raise RuntimeError(f"P4 scoring refused (exit {exc.code}): {err.getvalue().strip()[-400:]}") from exc
    finally:
        os.environ["EVIDENCE_ROOT"] = keep


# --- pre-submission feasibility preflight (plan amendment P4: S* fixed before data) ----

def preflight_path(alias: str) -> Path:
    return root() / "logs" / "review" / "Q004" / f"preflight-{MODEL_SHORT[alias]}.json"


def _model_has_submissions(alias: str) -> bool:
    short = MODEL_SHORT[alias]
    p = scaling_detail_path()
    if not p.is_file():
        return False
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            if f"-{short}-k" in d["scale_run_id"] and d.get("submitted"):
                return True
    return False


def preflight(alias: str, prompts: dict[tuple[int, str], str]) -> dict:
    """Backend token counts for every (target, rep) prompt and S*(m), recorded BEFORE the
    model's first submission. Once written it is reused, never recomputed."""
    path = preflight_path(alias)
    if path.is_file():
        rec = json.loads(path.read_text(encoding="utf-8"))
        for key, text in prompts.items():
            k = f"{key[0]}|{key[1]}"
            if rec["cells"][k]["prompt_sha256"] != sha256_text(text):
                raise SystemExit(f"preflight for {alias} is stale at {k}: prompt changed after S* was fixed")
        return rec
    if _model_has_submissions(alias):
        raise SystemExit(f"refusing to create the {alias} preflight: the model already has submitted "
                         "cells, so S* could no longer be fixed before its first submission")
    cells = {}
    for (target, rep), text in sorted(prompts.items()):
        n, method = model_prompt_tokens(alias, text)
        cells[f"{target}|{rep}"] = {"model_prompt_tokens": n, "method": method, "prompt_sha256": sha256_text(text),
                                    "request_tokens_with_budget": n + MAX_TOKENS,
                                    "feasible": n + MAX_TOKENS <= CONTEXT_WINDOWS[alias]}
    within = [t for t in SCALE_TARGETS if 10_000 < t <= 250_000 and cells[f"{t}|R0"]["feasible"]]
    rec = {"alias": alias, "context_window": CONTEXT_WINDOWS[alias], "max_tokens": MAX_TOKENS,
           "preflight_utc": utc(), "cells": cells, "s_star": max(within) if within else None,
           "rule": "S* = largest scale_target <= 250000 (excluding the 10000 anchor) whose R0 request fits the window"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return rec


# --- sweep ---------------------------------------------------------------------------

def load_rows() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if scaling_runs_path().is_file():
        for line in scaling_runs_path().read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["scale_run_id"]] = r
    return out


def append(row: dict, det: dict) -> None:
    for path, obj in ((scaling_runs_path(), row), (scaling_detail_path(), det)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")


def planned_cells(models: list[dict], k: int = DEFAULT_K) -> list[tuple]:
    return [(t, rep, m, kk) for t in SCALE_TARGETS for rep in PRIMARY_REPS for m in models for kk in range(k)]


def run(only_model: str | None = None, only_target: int | None = None, retry_failures: bool = False,
        log=print) -> dict:
    global REAL_EVIDENCE_ROOT
    from lab_evaluate_arm import harness_commit_at_production
    from lab_p7 import ledger_idempotency
    from lab_p9 import load_model_set
    REAL_EVIDENCE_ROOT = os.environ["EVIDENCE_ROOT"]
    pre = prereg_check()
    if not pre["plan_digest_ok"]:
        raise SystemExit("refusing to sweep: analysis-plan digest drifted from the pre-registration")
    harness_commit = harness_commit_at_production()
    idem = [{"at": "start", **{k: v for k, v in ledger_idempotency(INCIDENT).items() if k == "ok"}}]
    if not idem[0]["ok"]:
        raise SystemExit("SC-01 ledger idempotency broken before sweep")
    models = [m for m in load_model_set()["models"] if not only_model or m["alias"] == only_model]
    ident = {m["alias"]: identity_check(m["alias"]) for m in models}
    for a, r in ident.items():
        log(json.dumps({"identity": a, "ok": r["ok"], **{k: r.get(k) for k in ("served_max_model_len", "error")}}))
    all_prompts = {(t, rep): assemble(t, rep)[0] for t in SCALE_TARGETS for rep in PRIMARY_REPS}
    pre_rec = {}
    for m in models:
        if ident[m["alias"]]["ok"]:
            pre_rec[m["alias"]] = preflight(m["alias"], all_prompts)
            log(json.dumps({"preflight": m["alias"], "s_star": pre_rec[m["alias"]]["s_star"]}))
    done = load_rows()
    oracle = json.loads((Path(REAL_EVIDENCE_ROOT) / "SC-01" / INCIDENT / "oracle.json").read_text(encoding="utf-8"))
    optimum = lsn_int(oracle["coordinate"]["lsn"])
    ran = Counter()
    deferred = []
    for target in SCALE_TARGETS:
        if only_target and target != only_target:
            continue
        idem.append({"at": f"before s{target}", "ok": ledger_idempotency(INCIDENT)["ok"]})
        if not idem[-1]["ok"]:
            raise SystemExit(f"SC-01 ledger idempotency broken before s{target}; no cell of this block submitted")
        prompts = {rep: assemble(target, rep) for rep in PRIMARY_REPS}
        desc = descriptives(target, prompts["R0"][0])
        from lab_tokenize import token_estimate
        for rep in PRIMARY_REPS:
            text, gp = prompts[rep]
            canon = token_estimate(text)
            for m in models:
                for kk in range(DEFAULT_K):
                    sid = scale_run_id(target, rep, m["alias"], kk)
                    prev = done.get(sid)
                    if prev and not (retry_failures and prev["outcome"] == "run_failure"):
                        ran["skipped"] += 1
                        continue
                    if not ident[m["alias"]]["ok"]:
                        # PA P1/P7: never silently absent. Record a diagnosed run_failure;
                        # --retry-failures supersedes it once the backend is restored.
                        if prev and prev["outcome"] == "run_failure":
                            ran["skipped"] += 1
                            continue
                        row, det = unavailable_row(target, rep, m, kk, canon, gp, optimum, harness_commit,
                                                   ident[m["alias"]], desc)
                        append(row, det)
                        done[sid] = row
                        deferred.append(sid)
                        ran["run_failure"] += 1
                        continue
                    t = time.monotonic()
                    row, det = run_cell(target, rep, m, kk, text, canon, gp, optimum, harness_commit, desc)
                    if prev:
                        det["supersedes_outcome"] = prev["outcome"]
                    det["cell_seconds"] = round(time.monotonic() - t, 1)
                    append(row, det)
                    done[sid] = row
                    ran[row["outcome"]] += 1
                    log(json.dumps({"cell": sid, "outcome": row["outcome"], "verdict": row["verdict"],
                                    "model_prompt_tokens": row["model_prompt_tokens"], "s": det["cell_seconds"]}))
    idem.append({"at": "end", "ok": ledger_idempotency(INCIDENT)["ok"]})
    if not idem[-1]["ok"]:
        raise SystemExit("SC-01 ledger idempotency broken after the sweep")
    return {"ran": dict(ran), "recorded_unavailable_model_failures": len(deferred), "identity": ident,
            "s_star": {a: r["s_star"] for a, r in pre_rec.items()},
            "ledger_idempotency": idem, "harness_commit": harness_commit}


def reclassify() -> dict:
    """Correct rows labelled refusal_parser by the stricter multi-REFUSAL rule (a sweep-code
    defect contradicting C3). Appends a superseding row per affected cell that reuses the
    RECORDED completion unchanged (no new model call); the original row is retained."""
    from lab_arm_b_extract import tagged_lines
    latest, det = {}, {}
    for line in scaling_runs_path().read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            latest[r["scale_run_id"]] = r
    for line in scaling_detail_path().read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            det[d["scale_run_id"]] = d
    fixed = []
    for sid, r in sorted(latest.items()):
        if r["outcome"] != "refusal_parser":
            continue
        d = det[sid]
        coords, refusals = tagged_lines(d.get("raw_completion") or "")
        if refusals and not coords:
            row = dict(r)
            row["outcome"] = "refusal_genuine"
            nd = dict(d)
            nd.update({"row_utc": utc(), "supersedes_outcome": "refusal_parser",
                       "reclassified": ("C3: explicit REFUSAL with no coordinate offered; the recorded completion "
                                        "was mislabelled refusal_parser by a sweep-code rule stricter than C3"),
                       "reclassified_without_new_model_call": True})
            append(row, nd)
            fixed.append(sid)
    return {"reclassified": fixed}


def completeness() -> dict:
    from lab_p9 import load_model_set
    models = load_model_set()["models"]
    rows = load_rows()
    planned = {scale_run_id(t, rep, m["alias"], kk) for t, rep, m, kk in planned_cells(models)}
    by = Counter(r["outcome"] for sid, r in rows.items() if sid in planned)
    missing = sorted(planned - set(rows))
    per_scale: dict = {}
    for sid, r in rows.items():
        key = f"{r['scale_target']}|{r['representation']}"
        per_scale.setdefault(key, Counter())[r["outcome"]] += 1
    return {"planned": len(planned), "present": len(planned & set(rows)), "missing": len(missing),
            "missing_ids": missing[:30], "outcomes": dict(by),
            "partition_by_scale": {k: dict(v) for k, v in sorted(per_scale.items())},
            "ok": not missing and sum(by.values()) == len(planned)}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-p10-sweep")
    p.add_argument("--model")
    p.add_argument("--target", type=int, choices=SCALE_TARGETS)
    p.add_argument("--retry-failures", action="store_true")
    p.add_argument("--completeness", action="store_true")
    p.add_argument("--reclassify", action="store_true", help="C3 correction of multi-REFUSAL rows (no model call)")
    p.add_argument("--identity", action="store_true", help="live identity check of each model, no cells")
    p.add_argument("--measure-overhead", metavar="ALIAS", help="measure the chat-template token overhead")
    args = p.parse_args(argv)
    if args.measure_overhead:
        print(json.dumps(measure_overhead(args.measure_overhead), indent=2, sort_keys=True))
        return 0
    if args.identity:
        from lab_p9 import load_model_set
        print(json.dumps({m["alias"]: identity_check(m["alias"]) for m in load_model_set()["models"]},
                         indent=2, sort_keys=True))
        return 0
    if args.reclassify:
        print(json.dumps(reclassify(), indent=2, sort_keys=True))
        return 0
    if args.completeness:
        rec = completeness()
        print(json.dumps(rec, indent=2, sort_keys=True))
        return 0 if rec["ok"] else 1
    out = run(only_model=args.model, only_target=args.target, retry_failures=args.retry_failures)
    print(json.dumps({k: v for k, v in out.items() if k != "identity"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
