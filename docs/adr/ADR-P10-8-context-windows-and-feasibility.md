# ADR-P10-8 — Per-model context windows and the `infeasible_context` rule

Status: accepted 2026-09-24 (P10 Q001, before any scaling data)
Authority: Article XX.1; ADR-P10-4 ("each model's real prompt_tokens and its window decide feasibility").
Amendment: `scaling-analysis-plan.amendment-1.md` P1–P3.

## Context

The frozen P10 contracts assume a 262 144-token window for all three P9 models. The pinned
identities disagree:

| model | window | source |
| --- | --- | --- |
| DeepSeek-V4-Flash | 262 144 | P6.1 runtime pin; re-verified live 2026-09-24 |
| Qwen3.8-27B | 196 608 | P9 registry backend identity |
| Gemma-4-26B | 100 352 | P9 registry backend identity |

Two further facts bear on feasibility:

- Model tokenizers are larger than the canonical count on R0: 0.92× for DeepSeek, 1.24×
  for Qwen and 1.33× for Gemma, measured on P9's R0 prompt.
- A request must also leave room for the frozen 8 192-token completion budget
  (ADR-P9-3), or the backend rejects it.

## Decision

- **Windows.** Feasibility is judged against each model's real window.
- **Rule.** A cell is `infeasible_context` iff the backend's own token count for the chat
  request, plus 8 192, exceeds that window.
- **Counting.** The count comes from the backend's `/tokenize`, with a per-model
  chat-template overhead measured once from a real small submission where `/tokenize`
  cannot take chat messages.
- **Submission.** Infeasible cells are never submitted.
- **Identity.** A backend serving a different window than its pin fails identity (R2d).
  Its cells become `run_failure`, and the window is never silently changed.

## Consequences

- **Where each model's R0 ceiling falls.** The ceiling arrives much earlier than the
  contract's 250k assumption, so "10k–250k are all inside every window" is false:

  | model | approximate R0 ceiling (canonical tokens) |
  | --- | --- |
  | Gemma-4-26B | ~69k |
  | Qwen3.8-27B | ~152k |
  | DeepSeek-V4-Flash | ~276k |

  This is a result, not a failure (ADR-P10-3).
- **H1 and H2.** H1's "largest within-window scale" is therefore defined per model (plan
  amendment P4). H2 at 500k and above is unaffected.
