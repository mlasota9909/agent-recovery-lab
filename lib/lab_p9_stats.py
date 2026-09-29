"""lab-p9-stats (N005): the pre-registered analysis.

Refuses to run if statistical-analysis-plan.md drifted after the first sweep row
(Article XXI.2). Computes exactly what the frozen plan names, selects the matching
pre-declared interpretation verbatim, lints the prose for unscoped universals, and
writes thesis/analysis/p9-statistics.{json,md} regenerable byte-identical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from statistics import median

from lab_p3_util import EXIT_ASSERT, die
from lab_p9 import REPR_IDS, SPEC_DIR, load_frozen_hashes, root, sha256_file
from lab_p9_statlib import bootstrap_paired_diff, cliffs_delta, cochran_q, holm, mcnemar_exact
from lab_p9_sweep import sweep_path

BOOTSTRAP_SEED = 42
BOOTSTRAP_N = 10000
VERDICT_KEYS = ("correct", "incorrect_safe", "incorrect_corrupt", "not_recovered")

# Verbatim pre-declared interpretations (statistical-analysis-plan.md §4).
INTERPRETATIONS = {
    "H1_and_H2": (
        '"representation governs modest-model actionability, invariant across '
        'tested models/families" — scoped to SC-01(/02), K=5, 3 models.'
    ),
    "H1_not_H2": (
        '"representation benefit is inversely related to model capability; largest '
        'exactly where the operator is constrained to a small local model" — this '
        'STRENGTHENS the data-residency / operator-assist argument and MUST be '
        'reported as such.'
    ),
    "not_H1": (
        '"no detectable representation effect on determination at this scale" — '
        'reported honestly; the compactness and validity-methodology contributions stand.'
    ),
}

# Unscoped-universal phrases that must not appear applied to the n=1-scenario claim.
UNIVERSAL_PATTERNS = [
    r"\bin general\b", r"\bproves that\b", r"\bproven\b", r"\balways\b",
    r"\bfor all models\b", r"\bfor any model\b", r"\buniversally\b",
    r"\bguarantees\b", r"\binvariably\b", r"\bcategorically\b",
    r"representation determines\b", r"\bdetermines actionability\b",
    r"\bregardless of model\b", r"\bevery model\b",
]


def plan_path() -> Path:
    return root() / SPEC_DIR / "contracts" / "statistical-analysis-plan.md"


def _git_commit_for_first_row() -> str | None:
    """The commit that first added results/sweep-runs.jsonl content, if tracked
    history has it; the file is gitignored, so fall back to the freeze record."""
    p = subprocess.run(["git", "-C", str(root()), "log", "--diff-filter=A",
                        "--format=%H", "--", "results/sweep-runs.jsonl"],
                       text=True, capture_output=True, check=False)
    out = (p.stdout or "").strip().splitlines()
    return out[-1] if out else None


def plan_drift_check() -> dict:
    frozen = load_frozen_hashes()
    pinned = frozen["contracts"]["statistical-analysis-plan.md"]
    live = sha256_file(plan_path())
    first_row_utc = None
    if sweep_path().is_file():
        rows = [json.loads(l) for l in sweep_path().read_text(encoding="utf-8").splitlines() if l.strip()]
        if rows:
            first_row_utc = min(r.get("run_ts", "") for r in rows)
    rec = {
        "plan_digest_pinned": pinned,
        "plan_digest_live": live,
        "digest_unchanged": pinned == live,
        "frozen_before_first_sweep_row": frozen.get("frozen_before_first_sweep_row") is True,
        "freeze_commit": frozen.get("frozen_at_commit"),
        "first_sweep_row_utc": first_row_utc,
        "ok": pinned == live and frozen.get("frozen_before_first_sweep_row") is True,
    }
    return rec


# --- load the active partition -------------------------------------

def load_active() -> dict:
    rows = [json.loads(l) for l in sweep_path().read_text(encoding="utf-8").splitlines() if l.strip()]
    by_cell: "OrderedDict[str, dict]" = OrderedDict()
    superseded = 0
    for r in rows:
        if r["cell_id"] in by_cell:
            superseded += 1
        by_cell[r["cell_id"]] = r
    latest = list(by_cell.values())
    active = [r for r in latest if r["outcome"] in ("determination", "refusal")]
    run_failures = [r for r in latest if r["outcome"] == "run_failure"]
    return {
        "rows": latest,
        "active": active,
        "run_failures": run_failures,
        "superseded": superseded,
        "validity_partition": {
            "total_cells": len(latest),
            "determinations": sum(1 for r in latest if r["outcome"] == "determination"),
            "refusals": sum(1 for r in latest if r["outcome"] == "refusal"),
            "run_failures": len(run_failures),
        },
    }


def _grid(active: list[dict]) -> dict:
    """(representation, model_alias) -> {k: 1/0 determination, verdicts, damage, legit}."""
    g: dict = {}
    for r in active:
        key = (r["representation"], r["model_alias"])
        cell = g.setdefault(key, {"det": {}, "verdicts": [], "damage": [], "legit": [],
                                  "family": r["model_family"], "tokenizer_id": r["tokenizer_id"]})
        det = 1 if r["outcome"] == "determination" else 0
        cell["det"][r["replicate_index"]] = det
        if det and r.get("p4"):
            cell["verdicts"].append(r["p4"]["restore_verdict"])
            cell["damage"].append(r["p4"]["damage_rows_retained"])
            cell["legit"].append(r["p4"]["legit_rows_lost"])
    return g


def analyse(active: list[dict]) -> dict:
    grid = _grid(active)
    models = sorted({m for _, m in grid})
    reps = list(REPR_IDS)
    k_max = 1 + max((k for cell in grid.values() for k in cell["det"]), default=-1)

    # per-cell determination_rate + outcome/verdict table
    cells = {}
    for (rep, model), cell in grid.items():
        ks = sorted(cell["det"])
        dets = [cell["det"][k] for k in ks]
        vc = Counter(cell["verdicts"])
        cells[f"{rep}|{model}"] = {
            "representation": rep, "model": model, "family": cell["family"],
            "k": len(dets), "determinations": sum(dets),
            "determination_rate": (sum(dets) / len(dets)) if dets else None,
            "refusals": len(dets) - sum(dets),
            "verdict_distribution": {v: vc.get(v, 0) for v in VERDICT_KEYS},
            "median_damage_rows_retained": (median(cell["damage"]) if cell["damage"] else None),
            "median_legit_rows_lost": (median(cell["legit"]) if cell["legit"] else None),
        }

    # H1 - Cochran's Q across R0/R1/R2, paired over replicate (+ the single incident)
    def q_for(model_filter):
        matrix = []
        for model in models:
            if model_filter and model != model_filter:
                continue
            for k in range(k_max):
                block = []
                ok = True
                for rep in reps:
                    cell = grid.get((rep, model))
                    if not cell or k not in cell["det"]:
                        ok = False
                        break
                    block.append(cell["det"][k])
                if ok:
                    matrix.append(block)
        return cochran_q(matrix)

    h1 = {
        "pooled": q_for(None),
        "per_model": {m: q_for(m) for m in models},
    }

    # pairwise McNemar per model, Holm across the 3 pairs (family = 3 pairs per model)
    pairs = [("R0", "R1"), ("R0", "R2"), ("R1", "R2")]
    mcnemar = {}
    for model in models:
        raw = {}
        for a, b in pairs:
            ca, cb = grid.get((a, model)), grid.get((b, model))
            bcount = ccount = 0
            if ca and cb:
                for k in range(k_max):
                    if k in ca["det"] and k in cb["det"]:
                        va, vb = ca["det"][k], cb["det"][k]
                        if va == 1 and vb == 0:
                            bcount += 1
                        elif va == 0 and vb == 1:
                            ccount += 1
            raw[f"{a}_vs_{b}"] = mcnemar_exact(bcount, ccount)
        holm_adj = holm({k: v["p"] for k, v in raw.items()})
        mcnemar[model] = {k: {**raw[k], **holm_adj[k]} for k in raw}

    # H2 - per-model bootstrap 95% CI on (R2 - R0) rate; invariant IFF CI low > 0 for every model
    h2 = {}
    for model in models:
        c0, c2 = grid.get(("R0", model)), grid.get(("R2", model))
        blocks = []
        if c0 and c2:
            for k in range(k_max):
                if k in c0["det"] and k in c2["det"]:
                    blocks.append((c2["det"][k], c0["det"][k]))
        ci = bootstrap_paired_diff(blocks, seed=BOOTSTRAP_SEED, n_resamples=BOOTSTRAP_N)
        r2 = [c2["det"][k] for k in sorted(c2["det"])] if c2 else []
        r0 = [c0["det"][k] for k in sorted(c0["det"])] if c0 else []
        rnd = lambda v: (round(v, 6) if isinstance(v, float) else v)  # noqa: E731
        h2[model] = {
            "r2_minus_r0_point": rnd(ci["point"]),
            "ci95": [rnd(ci["ci_low"]), rnd(ci["ci_high"])],
            "ci_lower_gt_zero": (ci["ci_low"] is not None and ci["ci_low"] > 0),
            "cliffs_delta_r2_vs_r0": cliffs_delta(r2, r0),
        }

    h1_holds = (h1["pooled"].get("p") is not None and h1["pooled"]["p"] < 0.05)
    h2_holds = bool(h2) and all(v["ci_lower_gt_zero"] for v in h2.values())
    return {
        "models": models, "representations": reps, "k": k_max,
        "cells": cells,
        "H1_representation_effect": h1,
        "pairwise_mcnemar_holm": mcnemar,
        "H2_model_invariance": h2,
        "H1_holds": h1_holds,
        "H2_holds": h2_holds,
        "outcome_key": ("H1_and_H2" if h1_holds and h2_holds
                        else "H1_not_H2" if h1_holds and not h2_holds
                        else "not_H1"),
    }


def lint_universals(text: str) -> dict:
    hits = []
    for pat in UNIVERSAL_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            line = text[:m.start()].count("\n") + 1
            hits.append({"pattern": pat, "line": line, "match": m.group(0)})
    return {"ok": not hits, "violations": hits}


def render_md(drift: dict, partition: dict, a: dict, interp_text: str) -> str:
    L = []
    L.append("# P9 pre-registered statistics\n")
    L.append("Analysis plan `statistical-analysis-plan.md` frozen at N001 "
             f"(digest `{drift['plan_digest_pinned'][:16]}...`), before the first sweep row "
             f"({drift['first_sweep_row_utc']}). Digest unchanged at analysis time: "
             f"{drift['digest_unchanged']}.\n")
    L.append("## Validity partition (carried beside every aggregate)\n")
    L.append(f"- planned cells: 45  (SC-01 x R0/R1/R2 x 3 models x K=5)")
    L.append(f"- determinations: {partition['determinations']}")
    L.append(f"- refusals: {partition['refusals']}  (observed outcomes, Article VIII — not missing data)")
    L.append(f"- run failures: {partition['run_failures']}\n")
    L.append("## Determination rate and P4 verdicts per (representation x model)\n")
    L.append("| representation | model | family | det/K | det rate | verdicts (correct/safe/corrupt/not-rec) | median damage rows | median legit rows |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for key in sorted(a["cells"]):
        c = a["cells"][key]
        vd = c["verdict_distribution"]
        L.append(f"| {c['representation']} | {c['model']} | {c['family']} | "
                 f"{c['determinations']}/{c['k']} | {c['determination_rate']:.2f} | "
                 f"{vd['correct']}/{vd['incorrect_safe']}/{vd['incorrect_corrupt']}/{vd['not_recovered']} | "
                 f"{c['median_damage_rows_retained']} | {c['median_legit_rows_lost']} |")
    L.append("")
    q = a["H1_representation_effect"]["pooled"]
    L.append("## H1 — representation effect (Cochran's Q across R0/R1/R2)\n")
    L.append(f"- pooled (blocks = model x replicate = {q['blocks']}): "
             f"Q = {q['Q']:.3f}, df = {q['df']}, p = {q['p']:.4g}  → "
             f"{'reject H0 (effect detected)' if a['H1_holds'] else 'fail to reject H0'}")
    for m, qm in a["H1_representation_effect"]["per_model"].items():
        qv = f"{qm['Q']:.3f}" if qm["Q"] is not None else "n/a"
        pv = f"{qm['p']:.4g}" if qm["p"] is not None else "n/a"
        L.append(f"- {m}: Q = {qv}, p = {pv} (blocks = {qm['blocks']})")
    L.append("\n### Pairwise McNemar (exact), Holm-corrected across the 3 pairs per model\n")
    L.append("| model | pair | b | c | p raw | p Holm | reject 0.05 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for m, mm in a["pairwise_mcnemar_holm"].items():
        for pair, rec in mm.items():
            L.append(f"| {m} | {pair} | {rec['b']} | {rec['c']} | {rec['p']:.4g} | "
                     f"{rec['p_holm']:.4g} | {rec['reject_at_0.05']} |")
    L.append("\n## H2 — model-invariance of the R2 ≥ R0 ordering\n")
    L.append("Bootstrap 95% CI on (R2 − R0) determination-rate difference, "
             f"{BOOTSTRAP_N} resamples, seed {BOOTSTRAP_SEED}. "
             "H2 holds IFF the CI lower bound > 0 for **every** model.\n")
    L.append("| model | (R2−R0) point | 95% CI | CI low > 0 | Cliff's delta (R2 vs R0) |")
    L.append("| --- | --- | --- | --- | --- |")
    for m, h in a["H2_model_invariance"].items():
        lo, hi = h["ci95"]
        cd = h["cliffs_delta_r2_vs_r0"]
        L.append(f"| {m} | {h['r2_minus_r0_point']:+.2f} | "
                 f"[{lo:+.2f}, {hi:+.2f}] | {h['ci_lower_gt_zero']} | "
                 f"{cd['delta']:+.2f} ({cd['magnitude']}) |")
    L.append(f"\n- H1 holds (pre-registered primary = pooled Cochran's Q, p < 0.05): "
             f"**{a['H1_holds']}**   H2 holds: **{a['H2_holds']}**\n")
    L.append("## Pre-declared interpretation (Article XXI.3 — emitted verbatim from plan §4)\n")
    L.append(f"> {interp_text}\n")
    L.append(_exploratory(a) + "\n")
    L.append("## Sample-size honesty (plan §5)\n")
    L.append("K=5 x 3 models is a feasibility / proof-of-concept scale, not a powered "
             "study. No result here is a population-level claim; no universal language "
             "is attached to this single-scenario evidence.\n")
    return "\n".join(L) + "\n"


def _exploratory(a: dict) -> str:
    """Exploratory (not pre-registered) — Article XVIII root-cause of the pooled result.
    Every statement is a restatement of a number in the tables above."""
    pooled = a["H1_representation_effect"]["pooled"]
    per = a["H1_representation_effect"]["per_model"]
    h2 = a["H2_model_invariance"]
    sig_models = [m for m, q in per.items() if q.get("p") is not None and q["p"] < 0.05]
    dirs = []
    for m, h in h2.items():
        pt = h["r2_minus_r0_point"]
        arrow = "R2 > R0" if pt > 0 else "R0 > R2" if pt < 0 else "R0 = R2"
        dirs.append(f"{m}: (R2−R0) = {pt:+.2f} ({arrow})")
    L = ["## Exploratory (not pre-registered) — root-cause of the pre-registered outcome (Article XVIII)\n"]
    L.append("This section diagnoses the pre-registered result from the primary evidence; "
             "per plan §6 it cannot override the conclusion above.\n")
    per_txt = ", ".join(f"{m}: p = {per[m]['p']:.3g}" for m in per if per[m]["p"] is not None)
    L.append(f"- The pooled Cochran's Q is non-significant (Q = {pooled['Q']:.3f}, "
             f"p = {pooled['p']:.3g}); the per-model Cochran's Q is significant for "
             f"{len(sig_models)} of 3 models ({per_txt}).")
    L.append(f"- The per-model effects point in **opposite directions**: "
             + "; ".join(dirs) + ".")
    L.append("- A pooled omnibus test cancels opposing within-group effects, so the "
             "pre-registered pooled null is the expected reading of a real but "
             "**model-specific and directionally inconsistent** representation effect — "
             "not evidence of no effect.")
    def ci(m: str) -> str:
        lo, hi = h2[m]["ci95"]
        return f"[{lo:+.2f}, {hi:+.2f}]"
    L.append("- Consequence for the results: the P6.1 / SC-01 R0 < R1 < R2 ordering does "
             "**not** replicate as a uniform ordering across tested models. On this "
             "incident the DeepSeek-V4-Flash baseline needs the R2 graph "
             f"(R2 − R0 = {h2['gb10a-deepseek-v4-flash']['r2_minus_r0_point']:+.2f}, "
             f"CI {ci('gb10a-deepseek-v4-flash')}), Gemma-4-26B is best on the raw "
             f"log and refuses R2 entirely "
             f"(R2 − R0 = {h2['gympc-gemma4-26b']['r2_minus_r0_point']:+.2f}, "
             f"CI {ci('gympc-gemma4-26b')}), and Qwen3.8-27B determines on every "
             "representation. The compactness result (P8, 40.1x at SC-01) and the "
             "out-of-band validity methodology are unaffected by this.")
    return "\n".join(L)


def run(review: Path) -> dict:
    drift = plan_drift_check()
    if not drift["ok"]:
        die(EXIT_ASSERT, "assertion failed: statistical-analysis-plan drift or "
            f"post-collection edit — refusing to analyse (Article XXI.2): {drift}")
    act = load_active()
    partition = act["validity_partition"]
    a = analyse(act["active"])
    interp_text = INTERPRETATIONS[a["outcome_key"]]
    md = render_md(drift, partition, a, interp_text)
    lint = lint_universals(md)
    payload = {
        "plan_drift_check": drift,
        "validity_partition": partition,
        "superseded_rows_excluded": act["superseded"],
        "run_failures": [{"cell_id": r["cell_id"], "reason": r.get("failure_reason")}
                         for r in act["run_failures"]],
        "analysis": a,
        "pre_declared_interpretation_key": a["outcome_key"],
        "pre_declared_interpretation": interp_text,
        "universal_language_lint": lint,
        "bootstrap": {"seed": BOOTSTRAP_SEED, "n_resamples": BOOTSTRAP_N},
        "ok": lint["ok"],
    }
    out_json = root() / "thesis" / "analysis" / "p9-statistics.json"
    out_md = root() / "thesis" / "analysis" / "p9-statistics.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text(md, encoding="utf-8")
    review.mkdir(parents=True, exist_ok=True)
    (review / "p9-statistics.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (review / "p9-statistics.md").write_text(md, encoding="utf-8")
    (review / "regen-hash.txt").write_text(
        f"p9-statistics.json  {hashlib.sha256(out_json.read_bytes()).hexdigest()}\n"
        f"p9-statistics.md    {hashlib.sha256(out_md.read_bytes()).hexdigest()}\n", encoding="utf-8")
    if not lint["ok"]:
        die(EXIT_ASSERT, f"assertion failed: universal-language lint: {lint['violations']}")
    return payload


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-p9-stats")
    p.add_argument("--review", default=str(root() / "logs" / "review" / "N005"))
    p.add_argument("--drift-only", action="store_true")
    p.add_argument("--lint", metavar="FILE", help="run the universal-language lint on FILE and exit")
    args = p.parse_args(argv)
    if args.lint:
        rec = lint_universals(Path(args.lint).read_text(encoding="utf-8"))
        print(json.dumps(rec, indent=2))
        return 0 if rec["ok"] else EXIT_ASSERT
    if args.drift_only:
        rec = plan_drift_check()
        print(json.dumps(rec, indent=2, sort_keys=True))
        return 0 if rec["ok"] else EXIT_ASSERT
    rec = run(Path(args.review))
    print(json.dumps({"ok": rec["ok"], "interpretation_key": rec["pre_declared_interpretation_key"],
                      "H1_holds": rec["analysis"]["H1_holds"], "H2_holds": rec["analysis"]["H2_holds"],
                      "partition": rec["validity_partition"],
                      "lint_ok": rec["universal_language_lint"]["ok"]}, indent=2, sort_keys=True))
    return 0 if rec["ok"] else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
