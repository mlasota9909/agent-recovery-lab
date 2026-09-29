# ADR-P9-1 — Cross-model sweep rows land in a sidecar, not the frozen results schema

Status: accepted 2026-09-01 (P9 N001)

## Context

The P1 results-row schema (`etc/results-row.schema.json`, digest
`103eaa92ea48bca7ebcc7ce451b1978d822e92af41dc92b8fbf8f1e7a26d3775`) is a frozen
contract. It has no field for `model_alias`, `model_family`, `tokenizer_id`,
`sweep_id`, or `replicate_index`. The P9 sweep needs all five to tag 45 rows by
(scenario x representation x model x replicate).

`results/SC-01.jsonl` and `results/matrix.jsonl` are the banked result of record.
Article XVI and AC-P9-12 require them to be byte-identical before and after P9.

## Decision

The sweep writes **one self-contained JSONL file, `results/sweep-runs.jsonl`**, and
touches nothing else under `results/`. Each line carries:

- the sidecar keys: `sweep_id`, `results_row_id`, `scenario`, `representation`,
  `model_alias`, `model_family`, `tokenizer_id`, `replicate_index`, `outcome`;
- an embedded `results_row` object built to the **unchanged** P1 schema shape
  (same field names, same `resolved_by` enum incl. `live_heartbeat`), so an
  analyst can validate each embedded row against the frozen schema;
- an embedded `p4` object for determinations (verdict, `damage_rows_retained`,
  `legit_rows_lost`, skew), or the refusal reason, or the run-failure diagnosis.

The frozen schema is **not** amended: no new field is added to
`etc/results-row.schema.json`, its digest does not move, and no prior row is
rewritten. The five sweep keys live only at the top level of the sidecar line,
outside the embedded `results_row`.

## Consequences

- `results/SC-01.jsonl`, `results/matrix.jsonl`, and every prior contract digest
  stay byte-identical (AC-P9-12).
- N004 completeness is checked against `results/sweep-runs.jsonl` alone
  (rows == planned; determination/refusal/run_failure partition).
- N005/N006 load only `results/sweep-runs.jsonl` joined to the frozen SC-01
  oracle; they never read `results/SC-01.jsonl` for sweep aggregation.
- If a future consumer truly needs these keys in the canonical schema, that is a
  separate P1 `results-row.amendment-2.md` with its own ADR and a repo-wide
  digest re-pin — explicitly out of scope here.
