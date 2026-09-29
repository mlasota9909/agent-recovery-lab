# P11 — Specification: Answer-Grammar Re-Score of the Token-Scaling Runs

## Problem

P10 proved the large-scale half of the scaling story (R0 infeasible, R2 feasible: H2) and safety (H3), but its within-window accuracy hypothesis (H1) was not evaluable: the frozen P6.1 extractor rejected every within-window R0 answer as `refusal_parser` because multi-locator answers did not resolve to exactly one LSN. So the claim "raw data works at small scale" rests only on P10's exploratory re-scoring.

## Objective

Repair the extractor instrument under pre-registration and re-score the banked P10 completions with it, to establish as pre-registered results (a) whether raw data works at small scale (H4) and (b) whether R0 accuracy degrades within the context window (H1-R) — without re-running the scaling sweep and without altering any P10 number.

## Functional requirements

- **FR-1** A relaxed answer grammar (`answer-grammar.md`) that accepts a single resolved LSN when all offered locators name the same event, resolves timestamps at heartbeat granularity, is answer-blind, and is applied symmetrically to R0 and R2.
- **FR-2** A deterministic extractor `bin/lab-regrammar` implementing the frozen grammar, provably answer-blind.
- **FR-3** Re-parse of the FULL P10 submitted set (every cell with a banked completion), classification to the C3/A5 taxonomy, verdict via the unchanged P4 oracle path, one `rescoring-runs.jsonl` row per completion with the G6 shape.
- **FR-4** A consistency gate: completions whose extracted coordinate is unchanged keep their P10 verdict class; any divergence halts pending an ADR.
- **FR-5** The pre-registered analysis (`rescore-analysis-plan.md`) evaluating H4, H1-R, H3-R, emitting the verbatim interpretation for the realised branch, with the feasibility figure inherited read-only from P10.
- **FR-6** A conditional confirmatory within-window re-run (R004) that fires only on the pre-registered under-power trigger; otherwise skipped by rule.
- **FR-7** Read-only on all P10 and prior artefacts; new data in a sidecar; no P1 or P10 schema change; no P10 number altered.

## Non-goals

- No re-run of infeasible 500k/1M cells; no new scenario; no model change; no context-extension; no change to how a coordinate is scored (only how it is extracted).

## Acceptance criteria (tier M unless noted)

- **AC-P11-01** Both contracts frozen with recorded digests; Article XXI pre-registration recorded before any re-score row. **(gate: digests predate first row)**
- **AC-P11-02** Extractor deterministic: same completion + frozen view → byte-identical parse on rebuild.
- **AC-P11-03** Extractor answer-blind. **Negative test:** feed the oracle optimum into the extractor's inputs → a guard asserts it is never read; the parse is byte-identical with and without it.
- **AC-P11-04** Grammar symmetric across R0/R2. **Negative test:** introduce a representation-conditional branch → parity guard fails closed.
- **AC-P11-05** Completeness + consistency: every banked P10 completion is re-parsed; unchanged-coordinate completions keep their P10 verdict class. **Negative test:** flip one unchanged-coordinate verdict → consistency gate catches it.
- **AC-P11-06** Safety preserved: re-parse introduces no `incorrect_corrupt`. **Negative test:** inject a synthetic completion that resolves to a damage-retaining coordinate → it is scored `incorrect_corrupt` and surfaced, not suppressed.
- **AC-P11-07** H1-R evaluated exactly per plan (Bonferroni over 3 models), result recorded HOLDS/NULL with the statistic.
- **AC-P11-08** H4 evaluated exactly per plan (bootstrap CI vs 0.5), result recorded.
- **AC-P11-09** Analysis refuses to run if the grammar OR plan digest changed after the first re-score row (Article XXI). **Negative test:** bump either → analysis halts.
- **AC-P11-10** Realised interpretation emitted verbatim; universal-language lint passes (no accuracy-cliff / no R2-precision overclaim; null-H1-R stated plainly if realised).
- **AC-P11-11** Conditional re-run trigger evaluated mechanically from re-scored data; if skipped, `skip-by-rule` recorded; if fired, re-run is contained, greedy, seed 42, same frozen prompts, rows flagged `no_new_model_call=false`. **(tier A)**
- **AC-P11-12** Read-only: `results/scaling-runs.jsonl` SHA-256 unchanged; banked completions in `results/scaling-runs-detail.jsonl` byte-identical; P9 `sweep-runs.jsonl` unchanged; prior-evidence manifest byte-identical before/after. **Negative test:** touch a byte in a scratch copy → check fails.
- **AC-P11-13** Final gate prints TIER M x/x · TIER A y/y · TOTAL; prior tranche gates (incl. `lab-verify-p10`) re-run green read-only; close-out memo carries the realised interpretation and the anti-inversion handoff.
