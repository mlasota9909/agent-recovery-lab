# FROZEN CONTRACT — model-sweep-plan (P9)

Status: FROZEN at N001 (Article XV). Digest pinned in the gate and in N004/N005.

## 1. Purpose
Define the exact cross-model ablation matrix so the R0/R1/R2 representation effect can
be tested for model-invariance and defended against the single-model prompt/tokenizer
artefact risk.

## 2. Fixed factors
- Scenario: SC-01 (mandatory, P4-validated). SC-02 optional IFF N001 throughput permits;
  if included it is fully P4-validated (has oracle-manifest). SC-03/04 EXCLUDED.
- Representation: R0 (flat log), R1 (time-window summaries), R2 (graph+summaries).
- Model: EXACTLY 3 distinct local models, recorded by `{alias, family, param_class,
  tokenizer_id, weights_sha256, quantisation}`. The three MUST NOT share a tokenizer_id;
  at least two distinct model families are required. One model is the P6.1 baseline
  (~27B) recorded verbatim from the P6.1 runtime record.
- Decoding: greedy (temperature 0), fixed seed. Temperature MUST NOT be varied
  (varying it changes the evaluation target — prohibited).
- Replicates: K = 5 per (scenario x representation x model) cell.

## 3. Matrix size
cells = scenarios x 3 representations x 3 models ; rows = cells x K.
SC-01 only: 1 x 3 x 3 x 5 = 45 rows. SC-01+SC-02: 90 rows.

## 4. Interface invariant (anti-artefact — load-bearing)
Every model, for every representation, is queried through the SINGLE P5.1 `model_view`
surface via `bin/lab-modelview-guard`. Only `content` and `telemetry` may differ across
representations; NOTHING structural may differ across models. This is what licenses the
claim that a cross-model difference is representational, not interface-tuning.

## 5. Row schema
Reuse the P1 results-row schema unchanged (incl. `resolved_by` enum with `live_heartbeat`).
Add ONLY via a P1 amendment IF a new field is unavoidable: `model_alias`, `model_family`,
`tokenizer_id`, `sweep_id`, `replicate_index`. Prefer carrying these in a sidecar
`sweep-runs.jsonl` keyed by results-row id to avoid touching the frozen schema; the WI
decides and records which, under Article XV.

## 6. Provenance / containment
Article II (provenance-blind deciders) and Article X + P6.1 amendment (containment)
apply to every model unchanged. Each model's containment is re-verified in N002.

## 7. Outcome partition
Every cell run yields determination | refusal | run_failure. Refusals are data
(Article VIII). run_failure rows are retained (Article XIX). Aggregates always carry
the validity partition.
