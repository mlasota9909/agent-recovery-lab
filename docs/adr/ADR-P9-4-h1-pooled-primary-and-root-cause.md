# ADR-P9-4 — H1's pre-registered primary test is the pooled Cochran's Q; the null is root-caused, not reframed

Status: accepted 2026-09-01 (P9 N005)
Authority: Article XXI (report what the pre-registered plan shows; no reframing),
Article XVIII (a null is root-caused before it is reported), Article XX (resolve,
record, continue).

## Context

`statistical-analysis-plan.md` §3 names, for H1: "Cochran's Q across the three
representations on the binary determination outcome (paired over
replicate+incident), then pairwise McNemar with Holm correction." §3 also fixes the
Holm family as "the 3 pairwise comparisons per model", and §3's H2 is explicitly
"per model". The plan does not state whether H1's Cochran's Q is one pooled test or
one test per model.

The sweep result forces the question. Determination counts:

| representation | deepseek | gemma | qwen | pooled |
| --- | --- | --- | --- | --- |
| R0 | 2/5 | 4/5 | 5/5 | 11/15 |
| R1 | 0/5 | 2/5 | 5/5 | 7/15 |
| R2 | 5/5 | 0/5 | 5/5 | 10/15 |

- Pooled Cochran's Q (blocks = model x replicate = 15): Q = 2.889, p = 0.236 → **not significant**.
- Per-model Cochran's Q: deepseek Q = 7.60, p = 0.022; gemma Q = 6.00, p = 0.050; qwen Q = 0, p = 1.
- The deepseek and gemma effects point in **opposite directions** (deepseek needs
  R2; gemma needs R0), so they cancel when pooled.

## Decision

1. **H1's pre-registered primary test is the single pooled Cochran's Q** ("Cochran's
   Q across the three representations" reads most naturally as one test; H2 is the
   clause that carries the explicit "per model" qualifier). Pre-registered result:
   **H1 does not hold** (p = 0.236). H2 does not hold (the bootstrap 95% CI on
   R2 − R0 is not > 0 for every model; it is [−1.00, −0.40] for gemma).
2. Outcome branch = ¬H1 → the plan §4 interpretation emitted **verbatim** is
   *"no detectable representation effect on determination at this scale"*.
3. Per **Article XVIII**, that pooled null is root-caused from the primary evidence
   in a clearly-labelled **"Exploratory (not pre-registered)"** section
   (`p9-statistics.md`): the pooled null is the expected reading of a real but
   **model-specific and directionally inconsistent** representation effect — the
   per-model Cochran's Q is significant for deepseek and gemma, in opposite
   directions. Per plan §6 this section cannot override the pre-registered
   conclusion, and it does not: it explains it.
4. This was **not** chosen because it is the more favourable result — it is the
   less favourable one. The pooled reading is the more literal reading of the
   frozen plan, and choosing the per-model reading to recover an "effect detected"
   headline is exactly the selective-analysis move Article XXI exists to prevent.

## Consequence for the results

The P6.1 / SC-01 R0 < R1 < R2 ordering **does not replicate as a uniform ordering**
across the three tested models/families. The R2 advantage is real for the DeepSeek
baseline and, on this incident, reversed for Gemma-4 and absent for Qwen3.8. The
compactness result (P8: 40.1x at SC-01) and the out-of-band recovery-validity
methodology are independent of this and stand.
