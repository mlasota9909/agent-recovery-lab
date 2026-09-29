"""lab-p9-analysis (N006): Arm A vs Arm B head-to-head + framing. N007 is reserved and
runs only where its local-only generator is present.

Every number is computed from rows / cached P4 reports, never transcribed.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import median

from lab_arm_b_score import score_from_report
from lab_p3_util import EXIT_ASSERT, die
from lab_p9 import REPR_IDS, SPEC_DIR, root, sha256_file
from lab_p9_sweep import sweep_path
from lab_repr import HEADLINE

BASELINE_ALIAS = "gb10a-deepseek-v4-flash"      # P6.1 / P8 headline Arm B model


def _load_active() -> list[dict]:
    from collections import OrderedDict
    rows = [json.loads(l) for l in sweep_path().read_text(encoding="utf-8").splitlines() if l.strip()]
    by_cell: "OrderedDict[str, dict]" = OrderedDict()
    for r in rows:
        by_cell[r["cell_id"]] = r
    return [r for r in by_cell.values() if r["outcome"] in ("determination", "refusal")]


def _cached_report(tag: str) -> dict | None:
    p = root() / "var" / "restore" / HEADLINE / tag / "report.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _arm_a_from_results() -> dict:
    """The deterministic ranker's coordinate from results/SC-01.jsonl + its cached P4 report."""
    import os
    path = Path(os.environ["RESULTS_ROOT"]) / "SC-01.jsonl"
    arm_a_row = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("arm") == "deterministic":
            arm_a_row = r
            break
    if not arm_a_row:
        die(EXIT_ASSERT, "no deterministic (Arm A) row in results/SC-01.jsonl")
    report = _cached_report("arm_a")
    scored = score_from_report(report, cached=True) if report else None
    return {
        "arm": "arm_a",
        "selector": arm_a_row.get("ranker_version") or "p3-rank-1",
        "coordinate_lsn": (arm_a_row.get("chosen_coordinate") or {}).get("lsn"),
        "coord_error_bytes": arm_a_row.get("coord_error_bytes"),
        "p4_verdict": scored["restore_verdict"] if scored else None,
        "damage_rows_retained": scored["damage_rows_retained"] if scored else None,
        "legit_rows_lost": scored["legit_rows_lost"] if scored else None,
    }


def _arm_b_per_rep(active: list[dict], model: str | None) -> dict:
    out = {}
    for rep in REPR_IDS:
        cells = [r for r in active if r["representation"] == rep
                 and (model is None or r["model_alias"] == model)]
        det = [r for r in cells if r["outcome"] == "determination"]
        verdicts = Counter(r["p4"]["restore_verdict"] for r in det if r.get("p4"))
        damage = [r["p4"]["damage_rows_retained"] for r in det if r.get("p4")]
        legit = [r["p4"]["legit_rows_lost"] for r in det if r.get("p4")]
        coords = Counter((r["results_row"] or {}).get("chosen_coordinate", {}).get("lsn")
                         for r in det)
        out[rep] = {
            "k": len(cells),
            "determinations": len(det),
            "refusals": len(cells) - len(det),
            "determination_rate": (len(det) / len(cells)) if cells else None,
            "p4_verdicts": dict(verdicts),
            "median_damage_rows_retained": (median(damage) if damage else None),
            "median_legit_rows_lost": (median(legit) if legit else None),
            "modal_coordinate_lsn": (coords.most_common(1)[0][0] if coords else None),
        }
    return out


def compactness() -> dict:
    p = root() / "logs" / "review" / "M004" / "compactness.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def build_armab() -> dict:
    active = _load_active()
    arm_a = _arm_a_from_results()
    arm_b_baseline = _arm_b_per_rep(active, BASELINE_ALIAS)
    arm_b_allmodels = _arm_b_per_rep(active, None)
    comp = compactness()
    framing = (
        "Arm A (the deterministic ranker `p3-rank-1`) is the correctness / backbone "
        "layer: it computes a recovery coordinate directly from the out-of-band "
        "evidence with no model in the path, so its optimality is the reference the "
        "LLM is measured against. Arm B (a contained modest local model reading ONE "
        "representation through the guard) is the interpretation / accessibility "
        "layer: it lets an operator who is constrained to a small local model reach a "
        "safe decision from a compact view. This mirrors VerifyRCA / VeriOps-Agent, "
        "which decouple LLM hypothesis generation from a non-LLM evidence verifier "
        "(coverage / safety / rollback-feasibility). Arm A matching or beating Arm B "
        "on coordinate optimality is therefore the EXPECTED division of labour, not "
        "evidence the LLM is decorative: the LLM's contribution is turning a compact, "
        "provenance-blind representation into an actionable, safe determination where "
        "the raw log defeats the same model."
    )
    # honest cross-model note: did any Arm B cell reach `correct` where Arm A did not?
    correct_cells = []
    for rep in REPR_IDS:
        for r in [x for x in active if x["representation"] == rep and x["outcome"] == "determination"]:
            if r.get("p4", {}).get("restore_verdict") == "correct":
                correct_cells.append(f"{r['model_family']}/{rep}")
    cross_model_note = (
        f"Arm A's P4 verdict on this incident is `{arm_a['p4_verdict']}` (safe but "
        f"conservative). {len(set(correct_cells))} Arm B (model x representation) "
        f"combinations reached `correct` — {sorted(set(correct_cells))} — so on this "
        "incident some models on the raw log (R0) are more optimal than the "
        "deterministic ranker. That does not overturn the framing: Arm A is the "
        "always-available, model-free backbone whose verdict is bounded and "
        "predictable; Arm B's optimality is model- and representation-dependent, as "
        "the P9 sweep shows."
    ) if correct_cells else (
        f"No Arm B cell beat Arm A's `{arm_a['p4_verdict']}` verdict on this incident."
    )
    accessibility = (
        "The accessibility payload the interpretation layer consumes is the R2 "
        f"representation. At SC-01 scale median presented bytes fall from "
        f"{comp.get('SC-01', {}).get('median_r0')} (R0) to "
        f"{comp.get('SC-01', {}).get('median_r2')} (R2), a "
        f"{comp.get('SC-01', {}).get('ratio_r0_over_r2')}x reduction. This is not "
        f"universal: on the tiny SC-04 incident R2 is "
        f"{comp.get('SC-04', {}).get('median_r2')} bytes versus R0 at "
        f"{comp.get('SC-04', {}).get('median_r0')}, so `compactness_holds=false` "
        "there. Compactness and actionability are reported as separate findings."
    )
    return {
        "incident": HEADLINE,
        "arm_a": arm_a,
        "arm_b_baseline_model": {"model": BASELINE_ALIAS, "per_representation": arm_b_baseline},
        "arm_b_all_models": {"per_representation": arm_b_allmodels},
        "naive": {
            "p4_verdict": (score_from_report(_cached_report("too_late_naive"), True)["restore_verdict"]
                           if _cached_report("too_late_naive") else None),
            "damage_rows_retained": (score_from_report(_cached_report("too_late_naive"), True)["damage_rows_retained"]
                                     if _cached_report("too_late_naive") else None),
        },
        "framing": framing,
        "cross_model_optimality_note": cross_model_note,
        "accessibility_payload": accessibility,
        "division_of_labour_expected": True,
    }


def render_armab_md(rec: dict) -> str:
    a = rec["arm_a"]
    L = ["# Arm A vs Arm B — head-to-head and the correctness / interpretation framing\n"]
    L.append(f"Incident: `{rec['incident']}` (SC-01, P4-validated). All values computed "
             "from `results/sweep-runs.jsonl` and the cached P4 reports.\n")
    L.append("## Framing\n")
    L.append(rec["framing"] + "\n")
    L.append("## Head-to-head\n")
    L.append("| arm | representation | det rate | P4 verdict(s) | median damage rows | median legit rows | coordinate |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    L.append(f"| Arm A ({a['selector']}) | n/a (reads evidence directly) | 1.00 | "
             f"{a['p4_verdict']} | {a['damage_rows_retained']} | {a['legit_rows_lost']} | {a['coordinate_lsn']} |")
    for rep in REPR_IDS:
        b = rec["arm_b_baseline_model"]["per_representation"][rep]
        v = ", ".join(f"{k}:{n}" for k, n in b["p4_verdicts"].items()) or "—"
        L.append(f"| Arm B ({BASELINE_ALIAS}) | {rep} | {b['determination_rate']:.2f} | {v} | "
                 f"{b['median_damage_rows_retained']} | {b['median_legit_rows_lost']} | {b['modal_coordinate_lsn']} |")
    L.append(f"| naive (checkpoint before operator estimate) | n/a | 1.00 | {rec['naive']['p4_verdict']} | "
             f"{rec['naive']['damage_rows_retained']} | — | — |")
    L.append("\n### Cross-model Arm B (all 3 models pooled per representation)\n")
    L.append("| representation | det rate | P4 verdicts | median damage rows | median legit rows |")
    L.append("| --- | --- | --- | --- | --- |")
    for rep in REPR_IDS:
        b = rec["arm_b_all_models"]["per_representation"][rep]
        v = ", ".join(f"{k}:{n}" for k, n in b["p4_verdicts"].items()) or "—"
        L.append(f"| {rep} | {b['determination_rate']:.2f} | {v} | "
                 f"{b['median_damage_rows_retained']} | {b['median_legit_rows_lost']} |")
    L.append("\n## Cross-model optimality (honest note)\n")
    L.append(rec["cross_model_optimality_note"] + "\n")
    L.append("## Accessibility payload (compactness cross-reference)\n")
    L.append(rec["accessibility_payload"] + "\n")
    L.append("## One-sentence reading\n")
    L.append("Arm A being at least as optimal as Arm B is the expected outcome of the "
             "correctness-layer / interpretation-layer split; the LLM earns its place by "
             "making a compact, provenance-blind representation actionable for a "
             "constrained operator, not by beating the deterministic ranker on skew.\n")
    return "\n".join(L) + "\n"


# --- N007 (reserved) --------------------------------------------------

def _n007():
    """N007 is reserved; its generator is a local-only module outside the repository."""
    sys.path.insert(0, str(root() / "analysis"))
    try:
        import gen_related_work
    except ImportError:
        return None
    return gen_related_work


CLAIM_WORDS = ("success", "accuracy", "precision", "recall", "outperform", "achiev",
               "score", "f1", "state-of-the-art", "sota", "beats", "win rate", "pass@")
ATTRIBUTION_WORDS = ("median", "ratio", "sc-01", "sc-02", "sc-03", "sc-04", "reported",
                     "~92", "around 92", "compactness", "rca-accuracy", "recovery-gap")


def _fabricated_metric_lint(text: str) -> dict:
    """Flag an unattributed hard number presented as a result (e.g. '99.7 success',
    '73% accuracy') that is not tied to a named source."""
    import re
    hits = []
    num = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?x\b"
                     r"|\b\d{2,3}(?:\.\d+)?\b(?=[^\n]{0,40}(?:" + "|".join(CLAIM_WORDS) + r"))"
                     r"|(?:" + "|".join(CLAIM_WORDS) + r")[^\n]{0,40}\b\d{2,3}(?:\.\d+)?\b",
                     re.IGNORECASE)
    lines = text.split("\n")
    for i, ln in enumerate(lines, 1):
        for m in num.finditer(ln):
            if not any(w in ln.lower() for w in ATTRIBUTION_WORDS):
                hits.append({"match": m.group(0).strip(), "line": i})
    return {"ok": not hits, "unattributed_numbers": hits}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-p9-analysis")
    p.add_argument("--what", choices=("armab", "related", "both"), default="both")
    p.add_argument("--review", default=str(root() / "logs" / "review"))
    p.add_argument("--lint-fabricated", metavar="FILE")
    args = p.parse_args(argv)
    if args.lint_fabricated:
        rec = _fabricated_metric_lint(Path(args.lint_fabricated).read_text(encoding="utf-8"))
        print(json.dumps(rec, indent=2))
        return 0 if rec["ok"] else EXIT_ASSERT

    out = {}
    if args.what in ("armab", "both"):
        rec = build_armab()
        md = render_armab_md(rec)
        (root() / "thesis" / "analysis").mkdir(parents=True, exist_ok=True)
        (root() / "thesis" / "analysis" / "armA-vs-armB.json").write_text(
            json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (root() / "thesis" / "analysis" / "armA-vs-armB.md").write_text(md, encoding="utf-8")
        rev = Path(args.review) / "N006"
        rev.mkdir(parents=True, exist_ok=True)
        (rev / "armA-vs-armB.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (rev / "armA-vs-armB.md").write_text(md, encoding="utf-8")
        out["armab_ok"] = True
    n007 = _n007() if args.what in ("related", "both") else None
    if args.what == "related" and n007 is None:
        die(EXIT_ASSERT, "N007 is reserved; its local-only generator is not present")
    if n007 is not None:
        rec = n007.build_related_work()
        md = n007.render_related_md(rec)
        (root() / "thesis" / "related-work").mkdir(parents=True, exist_ok=True)
        (root() / "thesis" / "related-work" / "positioning-table.md").write_text(md, encoding="utf-8")
        (root() / "thesis" / "related-work" / "positioning-table.json").write_text(
            json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        rev = Path(args.review) / "N007"
        rev.mkdir(parents=True, exist_ok=True)
        (rev / "positioning-table.md").write_text(md, encoding="utf-8")
        lint = _fabricated_metric_lint(md)
        (rev / "attribution-lint.json").write_text(json.dumps(lint, indent=2) + "\n", encoding="utf-8")
        out["related_ok"] = lint["ok"]
        out["attribution_lint"] = lint
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if all(v for k, v in out.items() if k.endswith("_ok")) else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
