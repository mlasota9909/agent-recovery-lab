# FROZEN AMENDMENT 1 — Pre-registered Analysis Plan (P10, Article XXI)

Amends: `scaling-analysis-plan.md` (which stays byte-identical, Article XV).
Frozen at: Q001, before any `results/scaling-runs.jsonl` row exists. The pre-registered
digest is one SHA-256 over this file together with the plan. Q005 refuses to run if either
file changes after the first row.
ADRs: ADR-P10-8, ADR-P10-9. Consumers MUST read the plan together with this amendment.

Nothing here changes a hypothesis's direction, an A4 interpretation, or the
report-whatever-it-shows commitment. It fixes how each quantity is computed where the
plan's wording is not executable on the real lab.

## P1. Context window per model (supersedes the literal "262 144" in A3 H2, C2 and C5)

The plan assumes a 262 144-token window for all three models. The pinned identities say
otherwise:

| model | window | source |
| --- | --- | --- |
| `gb10a-deepseek-v4-flash` | 262 144 | P6.1 runtime pin; served `max_model_len` re-verified live 2026-09-24 |
| `alienware-qwen38-27b` | 196 608 | P9 registry `backend_identity.max_model_len` (inside the pinned digest) |
| `gympc-gemma4-26b` | 100 352 | P9 registry `backend_identity.max_model_len` (inside the pinned digest) |

Feasibility uses each model's real window. ADR-P10-4 already says "each model's real
`prompt_tokens` and its … window decide feasibility"; the number was wrong, the mechanism
was not. If a backend serves a window different from its pin, its identity digest no
longer matches, containment R2d fails, and its cells are `run_failure`. The window is never
silently changed.

## P2. `canonical_tokens` and "presented size"

`canonical_tokens` is the `lab-ws-punct-1` token count (`lab_tokenize.token_estimate`) of
the complete assembled prompt: the frozen template plus the guarded model_view content,
i.e. the whole model-visible text. A1's "presented size" is this quantity. The content-only
count is recorded in the detail sidecar.

## P3. `infeasible_context` (operationalises C3 and ADR-P10-3)

A cell is `infeasible_context` iff `model_prompt_tokens + 8192 > context_window`. 8192 is
the frozen P9 completion budget (ADR-P9-3). A request that cannot hold the prompt plus
that budget cannot be submitted under the frozen decoding configuration.
`model_prompt_tokens` is the backend's own count for the chat request:

- the backend `/tokenize` endpoint on the chat messages when it supports them;
- otherwise `/tokenize` of the prompt text plus the model's chat-template overhead,
  measured once per model before its first sweep cell as
  `usage.prompt_tokens − /tokenize(prompt)` on one real small submission.

Infeasible cells are never submitted. For submitted cells, `model_prompt_tokens` is the
API's `usage.prompt_tokens`.

## P4. H1 operationalisation (A3 H1, on A1's conditional accuracy as frozen)

- **Metric.** H1 stays on A1's recovery accuracy: correct / accepted within a cell.
- **Largest within-window scale.** For each model m, S\*(m) is the largest
  `scale_target` ≤ 250 000, excluding the 10 000 anchor, whose R0 request fits m's window
  (backend count + 8 192 ≤ window, P3). It is fixed by m's **pre-submission token
  preflight**, which runs and is recorded before m's first sweep submission. It does not
  depend on any outcome. If m has no such scale, H1 is not evaluable for m.
- **No fallback.** If any of m's R0 cells at the anchor or at S\* is a `run_failure`, or
  either cell has zero `accepted` replicates, H1 is not evaluable for m. The contrast is
  never moved to another scale.
- **Statistic.** Two-sample percentile bootstrap of acc(anchor) − acc(S\*):
  10 000 resamples, `random.Random(42)`. In each resample, draw each cell's accepted
  replicates' correct/incorrect outcomes with replacement, at that cell's own number
  accepted, and take the difference of the means. Percentile indices follow
  `lab_p9_statlib`'s convention. `lab_p9_statlib` has no conditional bootstrap, so this
  statistic is a new P10 function; statlib itself is reused unchanged.
- **Multiple comparisons.** H1 asks "for at least one of the 3 planned models", so use a
  Bonferroni correction across the 3: per-model two-sided α = 0.05 / 3, i.e. a 98.33%
  interval. H1 holds for m iff that interval's lower bound > 0. **H1 HOLDS** iff it holds
  for at least one model.
- **Exact hypotheses.** H2 and H3 are exact or descriptive conditions, not inferential
  tests, so no correction applies to them.
- **Exploratory, labelled as such.** The paired acceptance-rate difference (anchor vs
  S\*) is reported with the unchanged `bootstrap_paired_diff`. It cannot override the
  pre-registered branch.

## P5. A2 limit points (descriptive)

1. **Canonical hard limit** (as pre-registered): the smallest `scale_target` whose R0
   `canonical_tokens` exceeds 262 144.
2. **Per-model hard limit**: the smallest `scale_target` at which that model's R0 cells
   are `infeasible_context`.
3. **Per-model soft limit**: the smallest completed `scale_target` at which that model's
   R0 recovery accuracy (conditional, A1) falls at least 15 points below its anchor
   value. It is not computed where accuracy is undefined.

## P6. H2 and H3

- **H2.** At every `scale_target` ≥ 500 000, the R0 `infeasible_context` rate is 1.0 for
  every model and the R2 `infeasible_context` rate is 0.0 for every model, each against
  its P1 window. H2 HOLDS iff both are met exactly.
- **H3.** No `accepted` cell at any scale has verdict `incorrect_corrupt`, using the
  verdict defined in `scale-generator.amendment-1.md` A4.

## P7. Scope and K (fixes ADR-P10-2's "only if throughput allows" before data)

- The primary sweep is R0 and R2. **R1 is not run in P10.** This is decided here, before
  data, so the omission cannot become selective.
- K = 5 in every cell: the ≥500k R0 cells are never submitted and R2 prompts are tiny, so
  the K = 3 relief is not needed.
- Planned cells: 2 representations × 7 targets × 3 models × 5 = **210**.
- If a model's backend cannot be restored to its pinned identity, its cells are
  `run_failure` with that diagnosis. They are never replaced by another model and never
  dropped (Article XIX). Any hypothesis clause that needs them is reported as not
  evaluable for that model.

## P8. Descriptive records required beside every headline

- **Visible windows.** Record the three windows the frozen `PB-6-candidate-windows`
  (top_n = 3) interface shows at each scale. Padding adds changes to every window it
  reaches, and the frozen P3 anomaly rule (max z over burst, deletes and changes against
  the pre-injection baseline) can reorder the lower two. Measured during generator
  development: `[15, 16, 14]` at 0 padded events, `[15, 16, 10]` at 3 000, `[15, 16, 5]`
  at 40 000. Window 15, which holds the damage, ranks first throughout. This is recorded,
  never intervened on.
- **Malicious window position.** Record the relative position of the first damaging
  event's line in the R0 prompt content. It is computed oracle-side after generation and
  never used by the generator.

## P9. R2 size under the frozen interface (bears on A2's expectation and AC-P10-11)

The frozen interface presents R2 as the summaries of the three visible windows at every
scale. Each summary line has a fixed shape, and `lab-ws-punct-1` counts a digit run as one
token. Measured on the instrument during generator development, before any sweep data:
R2 is 248 canonical tokens at 0, 3 000 and 40 000 padded events. A2's expectation that R2
grows "sub-linearly but NOT flat" is therefore not expected to hold in canonical tokens.
R2 model tokens can still grow slightly as its counts gain digits. This is reported as
measured. No change is made to the R2 builder or query to alter its size (C4). AC-P10-11
tests non-decreasing size only, and is evaluated as written.

## P10. Plan-drift refusal (A5, AC-P10-08)

Q005 halts in either of these cases:

- SHA-256 over (`scaling-analysis-plan.md`, this amendment) differs from the digest in
  `logs/review/Q001/preregistration.json` and `contracts/frozen-hashes.json`;
- the pre-registration timestamp is not earlier than the first scaling row.

The timing check fails closed. Every `results/scaling-runs.jsonl` row must join, by
`scale_run_id`, to a `results/scaling-runs-detail.jsonl` record carrying `row_utc`. A
missing join or a missing timestamp is a violation. Each `row_utc`, and the mtime of every
`scaling-runs*` file, must be later than the pre-registration timestamp.
