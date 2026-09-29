# P10 — Specification: Token-Scaling of the Recovery-Point Task

## Problem

P9 established the R0/R1/R2 effect is model-specific on SC-01 at its natural size (~17.9 k R0 tokens), inside every model's 262 144-token window. The unanswered question that keeps the result "small": if the raw log fits, why compress? P10 characterises the regime where evidence scale forces the representation trade-off.

## Objective

Holding the SC-01 incident and its true recovery point fixed, synthetically scale the legitimate change history so R0's presented size sweeps 10 k → 1 M canonical tokens, and measure — under a pre-registered plan — acceptance, feasibility, and recovery accuracy for R0 vs R2 across the three P9 models.

## Functional requirements

- **FR-1** A deterministic scale generator that pads SC-01 to each target in `scale-generator.md` C2, preserving invariants C1 (fixed optimum, scaled confounder, blindness, determinism).
- **FR-2** Each padded incident reconciles exactly (P2.1 exactly-once property holds) and its oracle optimum equals the frozen SC-01 optimum. A padded incident whose optimum moved is a hard failure.
- **FR-3** Representation parity at scale: R0/R1/R2 built from each padded ledger via frozen P5 rules through the identical guarded `model_view`; only `content`/`telemetry` differ by representation.
- **FR-4** The scaling sweep runs `SC-01 × {R0,R2} × 7 scale targets × 3 models × K` (R1 optional, see plan), records one `scaling-runs.jsonl` row per cell with the C5 shape and the C3 outcome, and treats `infeasible_context` as first-class.
- **FR-5** The pre-registered analysis (`scaling-analysis-plan.md`) produces the two-curve figure, the H1/H2/H3 evaluation, and the verbatim interpretation for the realised branch.
- **FR-6** Read-only on all prior artefacts; new data in a sidecar; no P1 schema change; no P9 number altered.

## Non-goals

- No claim of universal R2 superiority; no real large-incident field test; no new scenario; no model fine-tuning; no context-extension tricks.

## Acceptance criteria (tier M unless noted)

- **AC-P10-01** Both contracts frozen with recorded digests; Article XXI pre-registration recorded before any scaling run. **(gate: digest predates first row)**
- **AC-P10-02** Scale generator deterministic: same `(target, seed)` → byte-identical padded ledger (rebuild twice, compare).
- **AC-P10-03** Invariant C1.1 held: every padded incident's oracle optimum == frozen SC-01 optimum. **Negative test:** inject one damage row into padding → optimum moves → generator refuses / flags. 
- **AC-P10-04** Exactly-once reconciliation holds on a padded incident (P2.1 property under scaling). **Negative test:** duplicate one padded LSN → reconciliation reports the duplicate.
- **AC-P10-05** Representation parity at scale: model_view differs only by `content`/`telemetry` across R0/R2 at a fixed scale. **Negative test:** inject a model-specific field → guard/parity check fails.
- **AC-P10-06** `infeasible_context` recorded correctly: at ≥500k R0 canonical_tokens > 262 144 and outcome is `infeasible_context`, not `refusal_*`. **Negative test:** mislabel an over-window prompt as refusal → check fails.
- **AC-P10-07** Provenance/answer-blind at scale: padded model_view passes `lab-modelview-guard`. **Negative test:** padding writes a `principal` → guard fires.
- **AC-P10-08** Analysis refuses to run if the plan digest changed after the first scaling row (Article XXI). **Negative test:** bump the plan → analysis halts.
- **AC-P10-09** H1/H2/H3 evaluated exactly per plan; realised-branch interpretation emitted verbatim; universal-language lint passes.
- **AC-P10-10** Two-curve figure regenerates byte-identical from `scaling-runs.jsonl`; the synthetic-padding limitation sentence is present adjacent to it.
- **AC-P10-11** R2-grows check: R2 canonical_tokens is a non-decreasing function of scale in the recorded data (proves R2 was not artificially flattened). **(tier A — descriptive assertion on recorded rows)**
- **AC-P10-12** Prior-evidence manifest byte-identical before/after the whole tranche (Article XVI); P9 `sweep-runs.jsonl` SHA-256 unchanged.
- **AC-P10-13** Final gate prints TIER M x/x · TIER A y/y · TOTAL; prior tranche gates re-run green against their pinned fixtures; close-out memo carries the validity partition and the realised interpretation.
