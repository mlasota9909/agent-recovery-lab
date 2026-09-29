# ADR-P9-3 — Uniform `max_tokens` = 8192 for the cross-model sweep

Status: accepted 2026-09-01 (P9 N001)
Authority: Article XVIII (an instrument artefact must not be reported as a subject
finding), Article XXI (fix the decoding budget before data collection), frozen
`model-sweep-plan.md` §2 (greedy, fixed seed — silent on `max_tokens`).

## Context

The P6.1 baseline runtime (`var/model/model-runtime.json`) uses `max_tokens: 512`.
DeepSeek-V4-Flash emits the tagged `COORDINATE:` / `REFUSAL:` line directly and
finishes in well under 512 tokens. Two of the three P9 models — Gemma-4-26B and
Qwen3.8-27B — are reasoning models: they emit chain-of-thought first and the
tagged line last. At `max_tokens: 512` a Qwen R1/R2 call was observed to stop with
`finish_reason: "length"` while still mid-reasoning, producing an **empty**
`content` and therefore an "absent tagged line" refusal.

A refusal caused by truncation is an instrument artefact, not evidence the model
could not localise a safe point. Reporting it as a refusal would violate Article
XVIII.

## Decision

The sweep fixes `max_tokens = 8192` for **every** model, in
`lab_p9.P9_DECODING`, recorded in `runtime/p9-model-set.json` and pinned before the
first sweep row. Greedy decoding (`temperature = 0`, `top_p = 1`) and the fixed
seed (42) are unchanged.

`max_tokens` is a truncation ceiling only: for greedy decoding, a completion that
stops on its own (`finish_reason: "stop"`) is **byte-identical** under a 512 or an
8192 budget. So this changes nothing for DeepSeek's already-complete outputs; it
only stops penalising the reasoning models for a budget set around a
non-reasoning baseline. `max_tokens` is not part of the `model_view` and does not
vary across models, so the anti-artefact interface invariant (`model-sweep-plan`
§4) is untouched.

Any sweep cell that still stops on `length` is recorded with
`finish_reason: "length"` on its model record and is a candidate instrument
artefact to diagnose in N004, not a silent refusal.

## Consequences

- Reasoning models get room to finish; their determinations/refusals reflect the
  model, not the budget.
- The DeepSeek column remains comparable to J004 (same non-truncated outputs).
- `runtime/p9-model-set.json` is the single source of the decoding block; N005's
  plan-drift check and the gate read it.
