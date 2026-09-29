# FROZEN AMENDMENT 1 — analysis-input (P8)

Status: FROZEN on P8-M003 acceptance. ADR: `docs/adr/ADR-P8-1-sc01-corrected-batch-supplement.md`.

## Superseded clause (verbatim)

From `analysis-input.md`, section 1:

> - Source: results/*.jsonl (never results/fixtures/).

## Replacement

The 51-row matrix analysis source remains `results/*.jsonl` (never `results/fixtures/`). For SC-01-only reported
headline, actionability, compactness, and coordinate-error outputs, the corrected P6.1 J004 batch is an authorized
supplemental source because the banked SC-01 results ledger predates that rerun. Its immutable inputs are:

- R0 `logs/review/J004/runs/R0/replicates.json` sha256 `bae0027550deeb1645bfe66b51aba368603bc6a85554a73a33776b087077ad52`
- R1 `logs/review/J004/runs/R1/replicates.json` sha256 `34d8b0019927fdf9885d9d11173d453938a676df034de4d734d1194f7511d118`
- R2 `logs/review/J004/runs/R2/replicates.json` sha256 `17f04c10806df1137ca20068af9dff9a9e72dd962cfea577855cf2de2ac97f2d`

Every output using this supplement MUST carry the 51-row matrix validity partition plus exact J004 record identifiers
and these source hashes. No other review-bundle artefact is consumable.
