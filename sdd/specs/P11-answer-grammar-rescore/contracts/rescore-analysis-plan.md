# FROZEN PRE-REGISTERED ANALYSIS PLAN — P11 (Article XXI)

Frozen at R001, BEFORE any `rescoring-runs.jsonl` row exists. R005 refuses to run if this file's digest OR the answer-grammar digest changed after the first re-score row. Reuses `lib/lab_p9_statlib.py` unchanged.

## A1. Unit and metrics (within-window R0, plus R2 for symmetry)

Per `(representation, scale_target, model)` cell over the P10 replicates, computed from re-scored verdicts:
- **recovery accuracy** = share of accepted replicates scored `correct`.
- **safe-or-better rate** = share scored `correct` or `incorrect_safe`.
- **accept-after-regrammar rate** = share now `accepted` (was the point of the repair).
- **anchor** = the natural SC-01 size (~19 435 R0 tokens). **S\*** = each model's largest within-window scale (DeepSeek 250k, Qwen 100k, Gemma 50k), as fixed in P10.

## A2. Pre-registered hypotheses

- **H4 (small-scale R0 competence — the author's claim).** At the anchor scale, pooled R0 recovery accuracy across the three models exceeds 0.5 with a bootstrap 95% CI (10 000 resamples, seed 42) whose lower bound > 0.5. HOLDS iff CI lower bound > 0.5. Interpreted as "raw data works when it fits."
- **H1-R (within-window degradation — re-evaluation of P10's H1).** For at least one model, R0 recovery accuracy at S\* is lower than at the anchor by a margin whose bootstrap 95% CI (seed 42) excludes 0, Bonferroni-corrected over the three models. HOLDS iff the corrected CI lower bound > 0 for ≥1 model. **Pre-registered expectation: likely NULL** given P10's exploratory 5/5 for Gemma and Qwen.
- **H3-R (safety preserved under re-grammar).** Re-parsing introduces no `incorrect_corrupt`. Descriptive safety check.
- **CONSISTENCY (mandatory gate, not a hypothesis).** For every completion whose extracted coordinate is unchanged by the new grammar, the re-scored verdict class equals the P10 verdict class. Any divergence is a defect and halts (Article XX) pending an ADR.

## A3. Pre-declared interpretations (emit the matching one verbatim)

1. **H4 ∧ ¬H1-R:** "With the answer-grammar instrument repaired, raw-evidence recovery is correct at small scale and does not lose accuracy anywhere inside the context window. Combined with P10's H2, the raw representation works while it fits and becomes infeasible once it does not. The compact representation's advantage at scale is feasibility, not within-window precision."
2. **H4 ∧ H1-R:** "Raw-evidence recovery is correct at small scale but measurably degrades toward the top of the context window for at least one model, and becomes infeasible beyond it (P10 H2). The compact representation preserves feasibility across the whole range."
3. **¬H4:** "Even with the repaired grammar, raw-evidence recovery is not reliably correct at small scale on this incident and model set; the small-scale-competence claim is not supported and is withdrawn." (Reported honestly; would sharply bound the thesis claim.)
- H3-R branch: if any `incorrect_corrupt` appears, P10's uniform-safety claim is explicitly revisited for the affected cells and reported.

## A4. Conditional confirmatory re-run (governs R004)

R004 fires ONLY if, after R003 re-parsing, **any** within-window R0 cell used in H4 or H1-R has fewer than 5 evaluable (accepted) replicates. Trigger, N to top up, and per-cell target are computed mechanically from the re-scored data and recorded in `logs/review/R003/rerun-trigger.json`. If no cell is under 5, R004 is **skipped by rule** and recorded as such — no model call. If it fires, the re-run uses the frozen P6.1 harness containment path, greedy, seed 42, the SAME frozen prompts, and the new grammar for extraction; new rows carry `no_new_model_call=false` and are clearly separated.

## A5. Honesty guards (lint, must pass)

- Universal-language lint: no sentence may claim an accuracy cliff, R2 precision superiority, or scale-independence beyond what H4/H1-R/H3-R support on the tested set (1 scenario, 3 models, P10 replicates).
- If H1-R is null, the write-up MUST say R0 does not degrade within the window and MUST NOT imply it does.
- Every figure/number regenerates byte-identical from `rescoring-runs.jsonl` (+ the P10 feasibility rows it inherits read-only).
- The instrument-repair framing MUST appear: results are re-scored under a grammar frozen before data, not re-run models.
