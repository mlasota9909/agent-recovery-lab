# ADR-P10-9 — Pre-registration made executable: H1 statistic, taxonomy, scope, K, recorded descriptives

Status: accepted 2026-09-24 (P10 Q001, before any scaling data)
Authority: Article XXI.1–2 (plan frozen before data), Article XX.1, Article XVIII.
Amendments: `scaling-analysis-plan.amendment-1.md` P2, P4, P5, P7–P10; `scale-generator.amendment-1.md` A5–A7.

## Context

The frozen plan names H1 on A1's conditional "recovery accuracy" (correct / accepted), to
be tested with a bootstrap from `lib/lab_p9_statlib.py`, which is reused unchanged. That
library offers only a paired binary bootstrap, and conditional accuracy is undefined for a
cell that accepts nothing. Several other quantities are named but not defined precisely
enough to compute without choices, and those choices have to be fixed before data:

- `canonical_tokens`;
- the split between parser refusals and genuine refusals;
- whether to run R1;
- K;
- where the ≥500k/1M R0 cells stand.

## Decision

Fix every open choice now, before any sweep row exists. The H1 part was revised after the
Q001 independent review, which correctly found that the first version's switch to an
unconditional correct-rate changed the hypothesis.

- **H1.** Stays on A1's conditional accuracy.
- **S\*.** Per model, S\* is fixed from pre-submission token counts: the largest
  ≤ 250k R0 request that fits the window. Failures or zero-accepted cells make the
  contrast not evaluable, with no fallback to another scale.
- **H1 statistic.** A two-sample percentile bootstrap (10 000 resamples, seed 42) of the
  accuracy difference.
- **Correction.** Bonferroni across the 3 planned models (α = 0.05/3), because H1 asks
  "any model". H2 and H3 are exact or descriptive.
- **Statlib.** `lab_p9_statlib` is reused unchanged, for the exploratory paired
  acceptance-rate contrast.
- **`canonical_tokens`.** The canonical count of the entire model-visible prompt.
- **Refusals.** Genuine means an explicit `REFUSAL:` line only. Every other extractor
  refusal is a parser refusal, with `finish_reason` recorded.
- **Scope.** R1 is not run. K = 5 everywhere, for 210 planned cells.
- **Timing gate.** The Article XXI timing gate fails closed: every row must join a
  timestamped detail record.
- **Descriptives.** Record the visible-window set and the damage's relative position at
  every scale.
- **R2 size.** Measured at 248 canonical tokens at every tested padding level. It is
  reported as it is; the builder is not changed (C4).

## Consequences


- Because the plan cannot be changed after data, these definitions are the only ones Q005
  may use. Any other cut of the data is labelled exploratory and cannot override the
  pre-registered branch.
