# FROZEN CONTRACT — Synthetic Scale Generator (P10)

Frozen at Q001. Governs how the SC-01 incident is padded to target token sizes. Superseding changes use an Article XV amendment; the original stays byte-identical.

## C1. Invariants the generator MUST preserve

1. **True recovery point fixed.** The malicious window and the oracle optimum coordinate are byte-identical to the frozen SC-01 incident at every scale. The generator adds only legitimate activity; it never adds, moves, or removes damage.
2. **Confounder preserved and scaled.** Padding is concurrent-style legitimate change activity of the same kinds already present in SC-01 (inserts/updates on the same relations, file writes in the protected subtree), interleaved across the timeline so the "separate damage from legitimate work" problem scales rather than becoming trivially separable.
3. **Provenance/answer-blind.** Padded records carry no `principal`/role field and no answer-key coordinate. The model-visible surface after padding still passes `lab-modelview-guard`.
4. **Deterministic.** Given `(scale_target, seed)` the padded ledger is byte-identical on rebuild. Seed pinned at 42 (matching P6/P9).

## C2. Scale targets (pre-registered set)

Target sizes are expressed in **R0 model-visible tokens** measured with the pinned canonical tokenizer (the P5 estimator tokenizer), recorded per run alongside each model's actual `prompt_tokens`:

`{ 10_000, 50_000, 100_000, 200_000, 250_000, 500_000, 1_000_000 }`

Rationale for the split, stated so it cannot be reverse-fitted later:
- 10k–250k sit **inside** the 262 144-token context window of all three P9 models → probes the **soft limit** (accuracy degradation before the hard limit; lost-in-the-middle regime).
- 500k, 1M **exceed** the window → probes the **hard limit** (R0 physically un-submittable) while R2 stays submittable.
- 10k is the anchor near SC-01's natural ~17.9k so the curve connects to the P9 result.

## C3. Per-run outcome taxonomy (superset of P6.1)

Each `(representation, scale_target, model, replicate)` cell records exactly one:
- `accepted` — model returned a resolvable coordinate that the parser accepted; then scored by the P4 oracle path to one of `correct | incorrect_safe | incorrect_corrupt | not_recovered`.
- `refusal_genuine` — model explicitly declined (no coordinate offered).
- `refusal_parser` — model offered locators the parser rejected as inconsistent/unresolvable (the P6.1/F1 distinction — MUST stay separate from genuine refusal).
- `infeasible_context` — the assembled model_view prompt exceeds the model's context window; the invocation is not attempted. This is a first-class outcome, NOT a refusal and NOT a failure.
- `run_failure` — harness/containment fault; diagnosed, never silently dropped.

## C4. What the generator MUST NOT do

- MUST NOT read `injection_log.json` or the oracle to decide where to pad (that would leak onset). Padding placement is a function of `(seed, scale_target)` only.
- MUST NOT alter R1/R2 construction rules. R2 remains deterministic window summaries built by the frozen P5 rules; at larger scale it simply has more windows. R2 is expected to GROW with scale, slowly — the contract forbids any special-casing that artificially flattens it.
- MUST NOT change the P1 results-row schema. New fields (`scale_run_id`, `scale_target`, `canonical_tokens`, `outcome`) live only in the `scaling-runs.jsonl` sidecar.

## C5. `scaling-runs.jsonl` row shape (frozen)

```json
{
  "scale_run_id": "sc01-s200000-r0-deepseek-k3",
  "scenario": "SC-01",
  "representation": "R0",
  "scale_target": 200000,
  "model_id": "gb10a-deepseek-v4-flash",
  "replicate": 3,
  "canonical_tokens": 199847,
  "model_prompt_tokens": 201203,
  "context_window": 262144,
  "outcome": "accepted",
  "verdict": "incorrect_safe",
  "damage_rows_retained": 0,
  "legit_rows_lost": 24,
  "oracle_optimum_lsn_int": 8069841617,
  "chosen_lsn_int": 8069841593,
  "guard_pass": true,
  "seed": 42,
  "harness_commit": "<git HEAD at row time>"
}
```
