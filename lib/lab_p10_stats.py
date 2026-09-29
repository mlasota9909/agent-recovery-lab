"""lab-p10-stats (Q005): the pre-registered P10 scaling analysis.

Refuses to run unless the plan digest matches the pre-registration AND the pre-registration
precedes every scaling row (Article XXI; plan amendment P10). Computes A1 metrics, the A2
two-curve figure, H1/H2/H3 exactly per plan + amendment, emits the realised A4 branch
verbatim, lints the prose. Every number and the figure regenerate byte-identical from
results/scaling-runs.jsonl (+ its detail sidecar and the Q004 preflights).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from lab_p10 import (
    CONTEXT_WINDOWS, DEFAULT_K, MAX_TOKENS, MODEL_SHORT, PRIMARY_REPS, SCALE_TARGETS,
    frozen_hashes_ok, prereg_check, root, scaling_detail_path, scaling_runs_path,
)

ANCHOR = 10_000
H1_MAX_SCALE = 250_000
HARD_SCALES = (500_000, 1_000_000)
CANONICAL_HARD_LIMIT = 262_144
N_RESAMPLES = 10_000
SEED = 42
N_PLANNED_MODELS = 3
ALPHA_FAMILY = 0.05
ALPHA_PER_MODEL = ALPHA_FAMILY / N_PLANNED_MODELS          # Bonferroni (plan amendment P4)
MODELS = ("gb10a-deepseek-v4-flash", "gympc-gemma4-26b", "alienware-qwen38-27b")
PRETTY = {"gb10a-deepseek-v4-flash": "DeepSeek-V4-Flash", "gympc-gemma4-26b": "Gemma-4-26B",
          "alienware-qwen38-27b": "Qwen3.8-27B"}

# A4 verbatim interpretations (scaling-analysis-plan.md, frozen)
A4 = {
    (True, True): ("Raw-evidence recovery degrades within the context window and becomes infeasible beyond it, "
                   "while the compact representation stays submittable; compression converts an infeasible task "
                   "into a feasible, safe-but-conservative one at scale."),
    (False, True): ("Raw-evidence recovery does not measurably lose accuracy inside the window for these models, "
                    "but becomes physically infeasible beyond it; the value of compression at scale is feasibility, "
                    "not within-window accuracy."),
    (True, False): ("Raw-evidence recovery degrades with scale even where submittable; compression preserves "
                    "accuracy by keeping evidence inside the reliable-attention regime."),
    (False, False): ("No scale effect was detected in the tested range; the compact representation's advantage "
                     "remains, as in P9, model-specific rather than scale-driven. This bounds the scaling claim "
                     "and is reported as such."),
}
H3_WITHDRAWAL = ("The uniform-safety claim from P9 is explicitly withdrawn for the scaled regime: at least one "
                 "scaled cell produced an incorrect_corrupt recovery.")

LIMITATION_SENTENCE = (
    "Limitation: the scaling is synthetic. SC-01 was padded with generated legitimate activity placed in the "
    "unused tails of its WAL segments, so this is not a real large incident; the padding is identifiable in "
    "principle (separate transaction-id and row-id ranges), and one scenario with three models was tested."
)

P10_UNIVERSAL_PATTERNS = [
    r"\bR2 is (?:always |generally |universally )?(?:better|superior)\b", r"\bsuperior\b",
    r"\bscale[- ]independent\b", r"\bindependent of scale\b", r"\bregardless of scale\b",
    r"\bat (?:any|every) scale\b", r"\bcompression always\b",
]


def lint(text: str) -> dict:
    from lab_p9_stats import UNIVERSAL_PATTERNS
    hits = []
    for pat in list(UNIVERSAL_PATTERNS) + P10_UNIVERSAL_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            hits.append({"pattern": pat, "line": text[:m.start()].count("\n") + 1, "match": m.group(0)})
    return {"ok": not hits, "violations": hits}


# --- data ----------------------------------------------------------------------------

def load(runs: Path | None = None, detail: Path | None = None) -> tuple[dict, dict]:
    runs = runs or scaling_runs_path()
    detail = detail or scaling_detail_path()
    rows: dict[str, dict] = {}
    for line in runs.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["scale_run_id"]] = r                  # latest supersedes (retained in file)
    det: dict[str, dict] = {}
    if detail.is_file():
        for line in detail.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                det[d["scale_run_id"]] = d
    return rows, det


def cells(rows: dict) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows.values():
        out[(r["representation"], int(r["scale_target"]), r["model_id"])].append(r)
    for v in out.values():
        v.sort(key=lambda r: int(r["replicate"]))
    return out


def metrics(rs: list[dict]) -> dict:
    c = Counter(r["outcome"] for r in rs)
    k = len(rs)
    acc = [r for r in rs if r["outcome"] == "accepted"]
    n_acc = len(acc)
    feas = k - c["infeasible_context"]
    correct = sum(1 for r in acc if r["verdict"] == "correct")
    safe = sum(1 for r in acc if r["verdict"] in {"correct", "incorrect_safe"})
    ct = [int(r["canonical_tokens"]) for r in rs]
    mt = [int(r["model_prompt_tokens"]) for r in rs if r.get("model_prompt_tokens") is not None]
    return {
        "k": k, "outcomes": dict(sorted(c.items())),
        "acceptance_rate": n_acc / k if k else None,
        "feasible_acceptance_rate": (n_acc / feas) if feas else None,
        "recovery_accuracy": (correct / n_acc) if n_acc else None,
        "safe_or_better_rate": (safe / n_acc) if n_acc else None,
        "n_accepted": n_acc, "n_correct": correct,
        "verdicts": dict(sorted(Counter(r["verdict"] for r in acc).items())),
        "median_canonical_tokens": statistics.median(ct) if ct else None,
        "median_model_prompt_tokens": statistics.median(mt) if mt else None,
    }


# --- statistics ----------------------------------------------------------------------

def _pct_bounds(diffs: list[float], alpha: float) -> tuple[float, float]:
    n = len(diffs)
    lo = diffs[max(0, int((alpha / 2) * n) - 1)]
    hi = diffs[min(n - 1, int((1 - alpha / 2) * n) - 1)]
    return lo, hi


def bootstrap_two_sample(a: list[int], b: list[int], seed: int = SEED, n_resamples: int = N_RESAMPLES,
                         alpha: float = ALPHA_PER_MODEL) -> dict:
    """Percentile CI of mean(a) - mean(b), each sample resampled independently with
    replacement at its own size (plan amendment P4). Index convention = lab_p9_statlib."""
    rng = random.Random(seed)
    na, nb = len(a), len(b)
    point = sum(a) / na - sum(b) / nb
    diffs = []
    for _ in range(n_resamples):
        sa = sum(a[rng.randrange(na)] for _ in range(na)) / na
        sb = sum(b[rng.randrange(nb)] for _ in range(nb)) / nb
        diffs.append(sa - sb)
    diffs.sort()
    lo, hi = _pct_bounds(diffs, alpha)
    return {"point": point, "ci_low": lo, "ci_high": hi, "n_a": na, "n_b": nb, "n_resamples": n_resamples,
            "seed": seed, "alpha": alpha, "confidence": 1 - alpha}


def _first_submission_utc(m: str) -> str | None:
    short = MODEL_SHORT[m]
    ts = []
    if scaling_detail_path().is_file():
        for line in scaling_detail_path().read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if f"-{short}-k" in d["scale_run_id"] and d.get("submitted"):
                    ts.append(d["row_utc"])
    return min(ts) if ts else None


def validate_preflight(m: str, rec: dict) -> list[str]:
    """Plan amendment P4: S* is fixed pre-submission from recorded counts. Re-derive it."""
    errs = []
    man = json.loads((root() / "runtime" / "p10-scaled-manifest.json").read_text(encoding="utf-8"))
    if rec.get("context_window") != CONTEXT_WINDOWS[m]:
        errs.append("window differs from the pin")
    if rec.get("max_tokens") != MAX_TOKENS:
        errs.append("completion budget differs from 8192")
    for t in SCALE_TARGETS:
        for rep in PRIMARY_REPS:
            c = (rec.get("cells") or {}).get(f"{t}|{rep}")
            if not c:
                errs.append(f"missing preflight cell {t}|{rep}")
                continue
            if c["prompt_sha256"] != man["targets"][str(t)]["prompt_sha256"][rep]:
                errs.append(f"prompt hash mismatch at {t}|{rep}")
            if c["feasible"] != (c["model_prompt_tokens"] + MAX_TOKENS <= CONTEXT_WINDOWS[m]):
                errs.append(f"feasibility flag inconsistent at {t}|{rep}")
    within = [t for t in SCALE_TARGETS if ANCHOR < t <= H1_MAX_SCALE
              and (rec.get("cells") or {}).get(f"{t}|R0", {}).get("feasible")]
    if rec.get("s_star") != (max(within) if within else None):
        errs.append("recorded S* does not follow from the recorded counts")
    first = _first_submission_utc(m)
    if first is not None and not rec.get("preflight_utc", "9") < first:
        errs.append("preflight was not recorded before the model's first submission")
    return errs


def load_preflights() -> dict:
    out = {}
    for m in MODELS:
        p = root() / "logs" / "review" / "Q004" / f"preflight-{MODEL_SHORT[m]}.json"
        if p.is_file():
            rec = json.loads(p.read_text(encoding="utf-8"))
            rec["validation_errors"] = validate_preflight(m, rec)
            out[m] = rec
    return out


def h1(cm: dict, pre: dict) -> dict:
    per = {}
    for m in MODELS:
        rec = {"model": m}
        if m not in pre:
            rec.update({"evaluable": False, "why": "no pre-submission preflight (backend unavailable)"})
            per[m] = rec
            continue
        if pre[m].get("validation_errors"):
            rec.update({"evaluable": False, "why": "preflight invalid: " + "; ".join(pre[m]["validation_errors"])})
            per[m] = rec
            continue
        s_star = pre[m].get("s_star")
        rec["s_star"] = s_star
        if s_star is None:
            rec.update({"evaluable": False, "why": "no within-window scale > anchor (preflight)"})
            per[m] = rec
            continue
        a = cm.get(("R0", ANCHOR, m), [])
        b = cm.get(("R0", s_star, m), [])
        why = []
        for name, rs in (("anchor", a), ("S*", b)):
            if len(rs) < DEFAULT_K:
                why.append(f"{name} has {len(rs)}/{DEFAULT_K} rows")
            if any(r["outcome"] == "run_failure" for r in rs):
                why.append(f"{name} has run_failure")
            if not any(r["outcome"] == "accepted" for r in rs):
                why.append(f"{name} has zero accepted")
        if why:
            rec.update({"evaluable": False, "why": "; ".join(why),
                        "anchor_metrics": metrics(a) if a else None, "s_star_metrics": metrics(b) if b else None})
            per[m] = rec
            continue
        xa = [1 if r["verdict"] == "correct" else 0 for r in a if r["outcome"] == "accepted"]
        xb = [1 if r["verdict"] == "correct" else 0 for r in b if r["outcome"] == "accepted"]
        bs = bootstrap_two_sample(xa, xb)
        rec.update({"evaluable": True, "accuracy_anchor": sum(xa) / len(xa), "accuracy_s_star": sum(xb) / len(xb),
                    "bootstrap": bs, "holds": bs["ci_low"] > 0})
        per[m] = rec
    # H1 is existential over the three planned models: it HOLDS if any evaluable model holds;
    # it DOES NOT HOLD only if all three are evaluable and none holds; otherwise not evaluable.
    if any(r.get("holds") for r in per.values()):
        holds = True
    elif all(r.get("evaluable") for r in per.values()):
        holds = False
    else:
        holds = None
    return {"per_model": per, "holds": holds, "evaluable": holds is not None,
            "n_evaluable": sum(1 for r in per.values() if r.get("evaluable")),
            "rule": ("H1 holds for m iff the Bonferroni (alpha=0.05/3) two-sample bootstrap CI of "
                     "acc(anchor) - acc(S*) has lower bound > 0; H1 HOLDS iff it holds for >= 1 model.")}


def h2(cm: dict) -> dict:
    per = {}
    for m in MODELS:
        rec = {}
        ok = True
        evaluable = True
        for t in HARD_SCALES:
            r0 = cm.get(("R0", t, m), [])
            r2 = cm.get(("R2", t, m), [])
            if len(r0) < DEFAULT_K or len(r2) < DEFAULT_K or \
                    any(r["outcome"] == "run_failure" for r in r0 + r2):
                evaluable = False
            r0_rate = sum(1 for r in r0 if r["outcome"] == "infeasible_context") / len(r0) if r0 else None
            r2_rate = sum(1 for r in r2 if r["outcome"] == "infeasible_context") / len(r2) if r2 else None
            rec[str(t)] = {"r0_infeasible_rate": r0_rate, "r2_infeasible_rate": r2_rate,
                           "r0_rows": len(r0), "r2_rows": len(r2)}
            if r0_rate != 1.0 or r2_rate != 0.0:
                ok = False
        rec["evaluable"] = evaluable
        rec["condition_met"] = ok and evaluable
        per[m] = rec
    all_eval = all(r["evaluable"] for r in per.values())
    return {"per_model": per, "evaluable": all_eval,
            "holds": all_eval and all(r["condition_met"] for r in per.values()),
            "rule": "at each scale >= 500k: R0 infeasible_context rate == 1.0 AND R2 == 0.0, for all three models"}


def h3(rows: dict) -> dict:
    corrupt = sorted(r["scale_run_id"] for r in rows.values()
                     if r["outcome"] == "accepted" and r["verdict"] == "incorrect_corrupt")
    n_acc = sum(1 for r in rows.values() if r["outcome"] == "accepted")
    return {"holds": not corrupt, "n_accepted": n_acc, "incorrect_corrupt_ids": corrupt}


def r2_non_decreasing(cm: dict) -> dict:
    """AC-P10-11 (tier A): median R2 canonical tokens is non-decreasing in scale."""
    med = {}
    for t in SCALE_TARGETS:
        vals = [int(r["canonical_tokens"]) for m in MODELS for r in cm.get(("R2", t, m), [])]
        if vals:
            med[t] = statistics.median(vals)
    seq = [med[t] for t in sorted(med)]
    return {"median_r2_canonical_by_scale": {str(k): v for k, v in sorted(med.items())},
            "non_decreasing": all(a <= b for a, b in zip(seq, seq[1:])), "n_scales": len(seq)}


def limits(cm: dict) -> dict:
    canon = {}
    for t in SCALE_TARGETS:
        vals = [int(r["canonical_tokens"]) for m in MODELS for r in cm.get(("R0", t, m), [])]
        if vals:
            canon[t] = statistics.median(vals)
    canonical_hard = next((t for t in sorted(canon) if canon[t] > CANONICAL_HARD_LIMIT), None)
    per = {}
    for m in MODELS:
        hard = next((t for t in SCALE_TARGETS
                     if cm.get(("R0", t, m)) and all(r["outcome"] == "infeasible_context" for r in cm[("R0", t, m)])), None)
        base = metrics(cm[("R0", ANCHOR, m)])["recovery_accuracy"] if cm.get(("R0", ANCHOR, m)) else None
        soft = None
        if base is not None:
            for t in SCALE_TARGETS[1:]:
                rs = cm.get(("R0", t, m))
                if not rs or len(rs) < DEFAULT_K or any(r["outcome"] == "run_failure" for r in rs):
                    continue
                acc = metrics(rs)["recovery_accuracy"]
                if acc is not None and base - acc >= 0.15:
                    soft = t
                    break
        per[m] = {"hard_limit_scale": hard, "anchor_accuracy": base, "soft_limit_scale": soft}
    return {"canonical_hard_limit_scale": canonical_hard, "canonical_hard_limit_tokens": CANONICAL_HARD_LIMIT,
            "per_model": per}


# --- figure --------------------------------------------------------------------------

def figure(cm: dict, out_png: Path) -> dict:
    """Two-curve figure (A2). Palette: validated default categorical slots 1-2
    (dataviz validate_palette: all checks pass on the light surface); neutral ink for
    reference lines; one y-axis (tokens); legend + direct end labels."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, NullFormatter
    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    colour = {"R0": "#eb6834", "R2": "#2a78d6"}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "text.color": ink,
                         "axes.labelcolor": ink2, "xtick.color": ink2, "ytick.color": ink2,
                         "axes.edgecolor": grid, "axes.facecolor": surface, "figure.facecolor": surface})
    fig, axes = plt.subplots(1, 3, figsize=(11.8, 4.2), dpi=150, sharey=True, sharex=True)
    ticks = [10_000, 50_000, 100_000, 200_000, 500_000, 1_000_000]
    tick_labels = ["10k", "50k", "100k", "200k", "500k", "1M"]
    for ax, m in zip(axes, MODELS):
        have = False
        usable = CONTEXT_WINDOWS[m] - MAX_TOKENS
        ax.axhline(CANONICAL_HARD_LIMIT, color="#9a9994", lw=1.0, ls=(0, (4, 3)), zorder=1,
                   label="262,144 canonical tokens (pre-registered line)")
        ax.axhline(usable, color=ink2, lw=1.4, ls=(0, (6, 2, 1, 2)), zorder=1,
                   label="usable prompt limit (model window − 8,192)")
        ax.text(1.35e6, usable, f"{usable:,}", color=ink2, fontsize=7, va="bottom", ha="right")
        for rep in PRIMARY_REPS:
            xs, ys, xm, ym, xi, yi = [], [], [], [], [], []
            for t in SCALE_TARGETS:
                rs = cm.get((rep, t, m), [])
                if not rs:
                    continue
                have = True
                ct = statistics.median(int(r["canonical_tokens"]) for r in rs)
                xs.append(t); ys.append(ct)
                mts = [int(r["model_prompt_tokens"]) for r in rs if r.get("model_prompt_tokens") is not None]
                if mts:
                    xm.append(t); ym.append(statistics.median(mts))
                if all(r["outcome"] == "infeasible_context" for r in rs):
                    xi.append(t); yi.append(statistics.median(mts) if mts else ct)
            if xs:
                ax.plot(xs, ys, "-", color=colour[rep], lw=2, solid_capstyle="round", zorder=3,
                        marker="o", ms=5.5, mfc=colour[rep], mec=surface, mew=1.2,
                        label=f"{rep} canonical tokens")
                ax.text(xs[-1] * 1.08, ys[-1], rep, color=ink, fontsize=8, va="center", fontweight="bold")
            if xm:
                ax.plot(xm, ym, "-", color=colour[rep], lw=1.0, alpha=0.55, zorder=2,
                        marker="o", ms=4, mfc=surface, mec=colour[rep], mew=1.0,
                        label=f"{rep} model tokens (backend count)")
            if xi:
                ax.plot(xi, yi, "x", color=ink, ms=7, mew=1.8, zorder=4,
                        label="infeasible_context (not submitted)")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlim(7_000, 1_500_000)
        ax.xaxis.set_major_locator(FixedLocator(ticks)); ax.set_xticklabels(tick_labels)
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.grid(True, which="major", color=grid, lw=0.8, ls="-", zorder=0)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.set_title(PRETTY[m] + f"  (window {CONTEXT_WINDOWS[m]:,})", fontsize=9, color=ink)
        ax.set_xlabel("scale target (canonical R0 tokens)")
        if not have:
            ax.text(0.5, 0.5, "no rows recorded", transform=ax.transAxes, ha="center", va="center",
                    color=ink2, fontsize=8.5)
    axes[0].set_ylabel("presented prompt size (tokens)")
    handles, labels = [], []
    for ax in axes:
        for h, lab in zip(*ax.get_legend_handles_labels()):
            if lab not in labels:
                handles.append(h); labels.append(lab)
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=7.5, frameon=False,
               bbox_to_anchor=(0.5, -0.01), labelcolor=ink)
    fig.suptitle("P10: presented prompt size against scale, per model (R0 raw change log, R2 three window summaries)",
                 fontsize=9.5, color=ink)
    fig.tight_layout(rect=(0, 0.13, 1, 0.95))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, metadata={"Software": None}, facecolor=surface)
    plt.close(fig)
    rel = out_png.relative_to(root()) if out_png.is_relative_to(root()) else out_png
    return {"path": str(rel), "sha256": hashlib.sha256(out_png.read_bytes()).hexdigest()}


# --- exploratory (labelled; cannot override the pre-registered branch) ---------------

def exploratory(cm: dict, det: dict, pre: dict) -> dict:
    from lab_p9_statlib import bootstrap_paired_diff
    out = {"acceptance_anchor_vs_s_star": {}, "refusal_parser_reasons": {}, "visible_windows": {},
           "malicious_relative_position_r0": {}}
    for m in MODELS:
        s = (pre.get(m) or {}).get("s_star")
        a = cm.get(("R0", ANCHOR, m), [])
        b = cm.get(("R0", s, m), []) if s else []
        if len(a) == len(b) == DEFAULT_K:
            blocks = [(1 if a[k]["outcome"] == "accepted" else 0, 1 if b[k]["outcome"] == "accepted" else 0)
                      for k in range(DEFAULT_K)]
            out["acceptance_anchor_vs_s_star"][m] = bootstrap_paired_diff(blocks, seed=SEED)
    reasons = Counter()
    for sid, d in det.items():
        if d.get("refusal_reason") and sid in {r["scale_run_id"] for rs in cm.values() for r in rs
                                               if r["outcome"] == "refusal_parser"}:
            reasons[(sid.split("-")[2], d["refusal_reason"][:60])] += 1
    out["refusal_parser_reasons"] = {f"{k[0]}: {k[1]}": v for k, v in sorted(reasons.items())}
    out["corrected_extraction"] = corrected_extraction(cm, pre)
    for t in SCALE_TARGETS:
        ds = [d for sid, d in det.items() if sid.startswith(f"sc01-s{t}-")]
        if ds:
            out["visible_windows"][str(t)] = ds[0].get("visible_windows")
            out["malicious_relative_position_r0"][str(t)] = ds[0].get("malicious_relative_position_r0")
    return out


def corrected_extraction(cm: dict, pre: dict) -> dict:
    """EXPLORATORY: re-derive acceptance/accuracy with parser-rejected but evidence-consistent
    lsn+ts answers re-scored (lab-p10-explore). Labelled; cannot override the branch."""
    path = root() / "results" / "scaling-runs-exploratory.jsonl"
    if not path.is_file():
        return {"available": False}
    ex = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            ex[e["scale_run_id"]] = e
    per_cell, contrasts = {}, {}
    for (rep, t, m), rs in cm.items():
        outcomes = []
        for r in rs:
            e = ex.get(r["scale_run_id"])
            if r["outcome"] == "accepted":
                outcomes.append(r["verdict"])
            elif e and e.get("evidence_consistent"):
                outcomes.append(e["verdict"])
        n_acc = len(outcomes)
        per_cell[f"{rep}|{t}|{m}"] = {"k": len(rs), "corrected_accepted": n_acc,
                                     "corrected_accuracy": (outcomes.count("correct") / n_acc) if n_acc else None,
                                     "verdicts": dict(sorted(Counter(outcomes).items()))}
    for m in MODELS:
        s = (pre.get(m) or {}).get("s_star")
        a = per_cell.get(f"R0|{ANCHOR}|{m}")
        b = per_cell.get(f"R0|{s}|{m}") if s else None
        if not a or not b or not a["corrected_accepted"] or not b["corrected_accepted"]:
            continue
        def xs(key):
            out = []
            for r in cm[("R0", key, m)]:
                e = ex.get(r["scale_run_id"])
                if r["outcome"] == "accepted":
                    out.append(1 if r["verdict"] == "correct" else 0)
                elif e and e.get("evidence_consistent"):
                    out.append(1 if e["verdict"] == "correct" else 0)
            return out
        contrasts[m] = bootstrap_two_sample(xs(ANCHOR), xs(s))
    return {"available": True, "rule": "evidence-consistent lsn+ts pair naming one presented R0 event",
            "n_rescored": sum(1 for e in ex.values() if e.get("evidence_consistent")),
            "n_parser_refusals_examined": len(ex), "per_cell": per_cell,
            "h1_style_contrast_exploratory": contrasts}


# --- run -----------------------------------------------------------------------------

def fmt(x, pct=False):
    if x is None:
        return "—"
    return f"{x:.0%}" if pct else (f"{x:,.0f}" if isinstance(x, (int, float)) and x >= 100 else f"{x:.3g}")


def render(res: dict) -> str:
    L = ["# P10 — Token-scaling of the recovery-point task (pre-registered analysis)", "",
         f"Pre-registration gate: plan digest `{res['gate']['plan_digest_live'][:16]}…` matches the Q001 record; "
         f"pre-registered at {res['gate']['preregistered_utc']}, before every scaling row "
         f"(`frozen_before_data = {res['gate']['frozen_before_data']}`).", "",
         f"Rows: {res['partition']['rows']} of {res['partition']['planned']} planned cells present. "
         f"Outcomes: " + ", ".join(f"{k} {v}" for k, v in res["partition"]["outcomes"].items()) + ".", "",
         "## Two-curve figure", "",
         f"![P10 two-curve figure](../figures/FIG-P10-two-curve.png)", "",
         LIMITATION_SENTENCE, "",
         "## Per-cell metrics (A1)", "",
         "| rep | scale | model | K | outcomes | acceptance | feasible acceptance | accuracy | safe-or-better | canonical tokens | model tokens |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for key in sorted(res["cells"], key=lambda k: (k.split("|")[0], int(k.split("|")[1]), k.split("|")[2])):
        rep, t, m = key.split("|")
        c = res["cells"][key]
        L.append(f"| {rep} | {int(t):,} | {PRETTY[m]} | {c['k']} | "
                 + ", ".join(f"{k} {v}" for k, v in c["outcomes"].items())
                 + f" | {fmt(c['acceptance_rate'], True)} | {fmt(c['feasible_acceptance_rate'], True)} | "
                 f"{fmt(c['recovery_accuracy'], True)} | {fmt(c['safe_or_better_rate'], True)} | "
                 f"{fmt(c['median_canonical_tokens'])} | {fmt(c['median_model_prompt_tokens'])} |")
    L += ["", "## Pre-registered hypotheses", "",
          "| hypothesis | result | statistic |", "| --- | --- | --- |"]
    for m, r in res["H1"]["per_model"].items():
        if r.get("evaluable"):
            b = r["bootstrap"]
            L.append(f"| H1 · {PRETTY[m]} (S* = {r['s_star']:,}) | {'holds' if r['holds'] else 'does not hold'} | "
                     f"acc(anchor) {r['accuracy_anchor']:.2f} − acc(S*) {r['accuracy_s_star']:.2f} = {b['point']:+.2f}, "
                     f"{b['confidence']:.2%} CI [{b['ci_low']:+.2f}, {b['ci_high']:+.2f}] |")
        else:
            L.append(f"| H1 · {PRETTY[m]} | not evaluable | {r['why']} |")
    L.append(f"| **H1** | **{'HOLDS' if res['H1']['holds'] else ('NOT EVALUABLE' if res['H1']['holds'] is None else 'DOES NOT HOLD')}** | "
             f"{res['H1']['n_evaluable']} evaluable model(s); Bonferroni α = 0.05/3 per model |")
    for m, r in res["H2"]["per_model"].items():
        cells_txt = "; ".join(f"{int(t):,}: R0 {fmt(v['r0_infeasible_rate'], True)} infeasible, "
                              f"R2 {fmt(v['r2_infeasible_rate'], True)}" for t, v in r.items() if t.isdigit())
        L.append(f"| H2 · {PRETTY[m]} | {'met' if r['condition_met'] else ('not evaluable' if not r['evaluable'] else 'not met')} | {cells_txt} |")
    L.append(f"| **H2** | **{'HOLDS' if res['H2']['holds'] else ('NOT EVALUABLE' if not res['H2']['evaluable'] else 'DOES NOT HOLD')}** | {res['H2']['rule']} |")
    L.append(f"| **H3** | **{'HOLDS' if res['H3']['holds'] else 'DOES NOT HOLD'}** | "
             f"{len(res['H3']['incorrect_corrupt_ids'])} incorrect_corrupt among {res['H3']['n_accepted']} accepted |")
    L += ["", "## Realised branch and pre-declared interpretation (A4, verbatim)", ""]
    br = res["branch"]
    if br["selectable"]:
        L += [f"Branch: H1 = {br['H1']}, H2 = {br['H2']}.", "", f"> {br['interpretation']}", ""]
    else:
        L += [f"No A4 branch can be selected: {br['why']}. The pre-registered interpretation is therefore not "
              "emitted; the evaluable parts are reported above as they are.", ""]
    if not res["H3"]["holds"]:
        L += [f"> {H3_WITHDRAWAL}", ""]
    li = res["limits"]
    L += ["## Limit points (A2, descriptive)", "",
          f"- Canonical hard limit (R0 canonical tokens above {li['canonical_hard_limit_tokens']:,}): "
          f"scale {fmt(li['canonical_hard_limit_scale'])}.",
          *[f"- {PRETTY[m]}: hard limit (all R0 cells infeasible) at scale {fmt(v['hard_limit_scale'])}; "
            f"anchor accuracy {fmt(v['anchor_accuracy'], True)}; soft limit (≥15-point accuracy drop) at "
            f"{fmt(v['soft_limit_scale'])}." for m, v in li["per_model"].items()], "",
          "## AC-P10-11 (tier A): R2 grows, is not flattened", "",
          f"Median R2 canonical tokens by scale: {res['r2']['median_r2_canonical_by_scale']}; non-decreasing: "
          f"{res['r2']['non_decreasing']}. R2 is constant in canonical tokens because the frozen interface shows "
          "three window summaries at every tested scale and a digit run is one canonical token; nothing was "
          "special-cased to make it so.", "",
          "## Exploratory (not pre-registered; cannot override the branch above)", "",
          f"- Paired acceptance-rate contrast, anchor vs S* (unchanged `lab_p9_statlib.bootstrap_paired_diff`): "
          f"{json.dumps({PRETTY[m]: {k: v for k, v in b.items() if k in ('point', 'ci_low', 'ci_high')} for m, b in res['exploratory']['acceptance_anchor_vs_s_star'].items()})}.",
          f"- Parser-refusal reasons: {json.dumps(res['exploratory']['refusal_parser_reasons'])}. "
          "The frozen P6.1 extractor accepts a multi-locator answer only if every locator resolves to the same "
          "LSN; a timestamp resolves at heartbeat granularity, so an lsn+ts pair naming one event is rejected.",
          f"- Corrected extraction (Article XVIII follow-up; evidence-consistent lsn+ts answers re-scored): "
          f"{json.dumps({k: v for k, v in res['exploratory']['corrected_extraction'].items() if k != 'per_cell'}, default=str)}.",
          f"- Visible windows by scale: {json.dumps(res['exploratory']['visible_windows'])}.",
          f"- Relative position of the first damaging line in the R0 prompt: "
          f"{json.dumps(res['exploratory']['malicious_relative_position_r0'])}.", "",
          f"Figure SHA-256: `{res['figure']['sha256']}`. Source: `results/scaling-runs.jsonl` "
          f"(SHA-256 `{res['source']['scaling_runs_sha256'][:16]}…`).", ""]
    return "\n".join(L)


def analyse(runs: Path | None = None) -> dict:
    rows, det = load(runs)
    cm = cells(rows)
    pre = load_preflights()
    res = {
        "partition": {"rows": len(rows), "planned": 2 * len(SCALE_TARGETS) * 3 * DEFAULT_K,
                      "outcomes": dict(sorted(Counter(r["outcome"] for r in rows.values()).items()))},
        "cells": {f"{rep}|{t}|{m}": metrics(rs) for (rep, t, m), rs in cm.items()},
        "H1": h1(cm, pre), "H2": h2(cm), "H3": h3(rows),
        "limits": limits(cm), "r2": r2_non_decreasing(cm), "exploratory": exploratory(cm, det, pre),
        "preflight_s_star": {m: p.get("s_star") for m, p in pre.items()},
    }
    why = []
    if not res["H1"]["evaluable"]:
        miss = [PRETTY[m] for m, r in res["H1"]["per_model"].items() if not r.get("evaluable")]
        why.append(f"H1 is not established: no evaluable model holds and it is not evaluable for {', '.join(miss)}")
    if not res["H2"]["evaluable"]:
        miss = [PRETTY[m] for m, r in res["H2"]["per_model"].items() if not r["evaluable"]]
        why.append(f"H2 requires all three models and is not evaluable for {', '.join(miss)}")
    if why:
        res["branch"] = {"selectable": False, "H1": res["H1"]["holds"], "H2": res["H2"]["holds"] if res["H2"]["evaluable"] else None,
                         "why": "; ".join(why)}
    else:
        key = (res["H1"]["holds"], res["H2"]["holds"])
        res["branch"] = {"selectable": True, "H1": key[0], "H2": key[1], "interpretation": A4[key]}
    return res


def run(out_dir: Path | None = None, fig_path: Path | None = None) -> dict:
    gate = prereg_check()
    if not gate["ok"] or not frozen_hashes_ok()["ok"]:
        print(json.dumps({"halt": "Article XXI: plan digest drifted or pre-registration does not precede the data",
                          "gate": gate}, indent=2, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
    if out_dir is not None and fig_path is None:
        fig_path = out_dir / "FIG-P10-two-curve.png"     # never touch thesis/figures from a scratch run
    out_dir = out_dir or (root() / "thesis" / "analysis")
    fig_path = fig_path or (root() / "thesis" / "figures" / "FIG-P10-two-curve.png")
    res = analyse()
    res["gate"] = {k: gate[k] for k in ("plan_digest_live", "preregistered_utc", "frozen_before_data")}
    res["figure"] = figure(cells(load()[0]), fig_path)
    res["source"] = {"scaling_runs_sha256": hashlib.sha256(scaling_runs_path().read_bytes()).hexdigest(),
                     "scaling_detail_sha256": hashlib.sha256(scaling_detail_path().read_bytes()).hexdigest()}
    md = render(res)
    res["lint"] = lint(md)
    if not res["lint"]["ok"]:
        print(json.dumps(res["lint"], indent=2), file=sys.stderr)
        raise SystemExit("universal-language lint failed")
    (out_dir / "p10-scaling.md").write_text(md, encoding="utf-8")
    (out_dir / "p10-scaling.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n",
                                             encoding="utf-8")
    return res


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-p10-stats")
    p.add_argument("--lint", metavar="FILE")
    a = p.parse_args(argv)
    if a.lint:
        r = lint(Path(a.lint).read_text(encoding="utf-8"))
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1
    res = run()
    print(json.dumps({"H1": res["H1"]["holds"], "H2": res["H2"]["holds"], "H2_evaluable": res["H2"]["evaluable"],
                      "H3": res["H3"]["holds"], "branch": res["branch"], "figure_sha256": res["figure"]["sha256"],
                      "lint_ok": res["lint"]["ok"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
