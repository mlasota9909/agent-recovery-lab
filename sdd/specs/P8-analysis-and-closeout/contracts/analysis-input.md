# FROZEN CONTRACT — analysis-input (P8)

Status: FROZEN on M001 acceptance. Changes only by Article XV supersession + re-pin.

## 1. Consumable rows
- Source: results/*.jsonl (never results/fixtures/).
- Active partition ONLY. A row is active iff:
  - it is not marked superseded (no `superseded_by`, not in any supersession manifest), AND
  - it belongs to the final validated matrix run (validity partition = active).
- Physical rows: 116. Active rows: 51. Partition: {determinations:25, refusals:25, run_failures:1}.

## 2. Mandatory companions to every aggregate
Every aggregate artefact MUST carry, in its metadata sidecar:
- `validity_partition`: {active_total, determinations, refusals, run_failures, superseded_excluded}
- `supersession_provenance`: list of superseded run ids folded out, with the row that superseded each
- `source_row_ids`: the exact active row ids the aggregate was computed from

## 3. Refusals
Refusal rows are observed outcomes. They are counted, never dropped, never imputed to a guess.

## 4. Provenance-blindness (comparison outputs)
Any artefact that compares R0/R1/R2 MUST be computed from a view that excludes `principal`/role
and any answer-key coordinate field. Permitted comparison inputs: representation id, evidence_bytes,
prompt_tokens, refusal flag, determination verdict, coordinate error vs ground truth.

## 5. Validation tiers (immutable labels)
- SC-01: P4-validated (headline)
- SC-02: P4-validated
- SC-03: set-validated (precision/recall + earliest-safe bound + legitimate-DML sacrifice)
- SC-04: set-validated (as SC-03)
Relabelling any set-validated scenario as P4-validated is a hard failure.
