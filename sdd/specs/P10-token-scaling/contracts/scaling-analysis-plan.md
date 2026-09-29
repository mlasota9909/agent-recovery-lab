# FROZEN PRE-REGISTERED ANALYSIS PLAN — P10 (Article XXI)

Frozen at Q001, BEFORE any `scaling-runs.jsonl` row exists. Q005 refuses to run if this file's digest changed after the first scaling run was recorded. Reuses `lib/lab_p9_statlib.py` unchanged.

## A1. Unit and metrics

Per `(representation, scale_target, model)` cell over K replicates:
- **acceptance rate** = share of replicates with `outcome ∈ {accepted}` (i.e. resolvable coordinate produced AND submittable).
- **feasible-acceptance rate** = accepted / (K − infeasible_context) — separates "model couldn't" from "prompt couldn't be sent".
- **recovery accuracy** = share of accepted replicates scored `correct`.
- **safe-or-better rate** = share scored `correct` or `incorrect_safe` (the safety line P9 established).
- **presented size** = median `canonical_tokens` (the two-curve x-quantity).

## A2. The two-curve model (primary descriptive output)

Plot, per model, presented `canonical_tokens` vs `scale_target` for R0 and R2 on one axis. Pre-registered expectation, stated so a null is honest:
- R0 grows approximately linearly with scale (raw records).
- R2 grows **sub-linearly but NOT flat** (more windows → more summary text). The claim under test is *divergence of growth rates and R0 crossing the window*, never "R2 is constant".
- The **crossover / infeasibility point** is the scale at which R0 `canonical_tokens` exceeds 262 144 (hard limit) and, separately, the scale at which R0 `recovery accuracy` drops by ≥ 15 points from its 10k value (soft limit, if it occurs).

## A3. Pre-registered hypotheses

- **H1 (soft-limit degradation).** For at least one model, R0 recovery accuracy at the largest *within-window* scale (≤250k) is lower than at 10k by a margin whose bootstrap 95% CI (10 000 resamples, seed 42) excludes 0. HOLDS iff CI lower bound > 0 for ≥1 model.
- **H2 (hard-limit divergence).** At scales ≥500k, R0 `infeasible_context` rate = 1.0 for all three models (262k window) while R2 `infeasible_context` rate = 0.0. HOLDS iff both conditions are met exactly.
- **H3 (safety holds under scale).** No cell at any scale produces `incorrect_corrupt`. Descriptive, pre-registered as a safety check.

## A4. Pre-declared interpretations (emit the matching one verbatim)

1. **H1 ∧ H2:** "Raw-evidence recovery degrades within the context window and becomes infeasible beyond it, while the compact representation stays submittable; compression converts an infeasible task into a feasible, safe-but-conservative one at scale."
2. **¬H1 ∧ H2:** "Raw-evidence recovery does not measurably lose accuracy inside the window for these models, but becomes physically infeasible beyond it; the value of compression at scale is feasibility, not within-window accuracy."
3. **H1 ∧ ¬H2** (only possible if a model's window were larger than tested): "Raw-evidence recovery degrades with scale even where submittable; compression preserves accuracy by keeping evidence inside the reliable-attention regime."
4. **¬H1 ∧ ¬H2:** "No scale effect was detected in the tested range; the compact representation's advantage remains, as in P9, model-specific rather than scale-driven. This bounds the scaling claim and is reported as such."
- H3 branch: if any `incorrect_corrupt` appears, the uniform-safety claim from P9 is explicitly withdrawn for the scaled regime and reported.

## A5. Honesty guards (lint, must pass)

- Universal-language lint: no sentence may claim R2 superiority or scale-independence beyond what H1–H3 support on the tested set (1 scenario, 3 models, K replicates).
- Every figure/number regenerates byte-identical from `scaling-runs.jsonl`.
- The synthetic-padding limitation sentence MUST appear adjacent to every headline scaling figure.
