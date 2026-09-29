# Contract — Results Row

**Status:** FROZEN at end of P1. Load-bearing for P3 (Arm A), P4 (restore verdicts), P5 (representation telemetry),
P6 (Arm B), P7 (analysis and every reported figure).

This is the single most consequential contract in the project. Every quantitative result is a field in
this row. A field added after runs have started makes earlier rows incomparable and forces a re-run.

## Amendment rule

Later tranches MAY **append** a field, provided it is nullable with a documented default of `null`.

Later tranches MUST NOT rename a field, change its type or unit, repurpose its meaning, or make a previously-nullable
field required. Any of those requires an explicit dated amendment at the bottom of this file and a stated decision
about whether prior rows are invalidated.

## Storage

One append-only JSONL file per scenario at `${RESULTS_ROOT}/<scenario_id>.jsonl`, one JSON object per line, UTF-8, no
trailing commas, no wrapping array. A closed results file is mode 0444. Rows are never mutated in place; a correction
is a new row with `supersedes` set.

## Fields

### Identity and grouping

| Field | Type | Null? | Unit | Meaning |
| --- | --- | --- | --- | --- |
| `run_id` | string, `r_<UTC compact>_<6 hex>` | no | — | Unique per evaluate-arm invocation |
| `scenario_id` | string, `SC-0[1-4]` | no | — | Which scripted disaster |
| `incident_id` | string, `i_<UTC compact>_<6 hex>` | no | — | **The join key.** Groups arms and replicates that saw the same incident |
| `replicate` | integer >= 1 | no | — | Nth replicate of this scenario/arm combination |
| `run_ts` | ISO 8601 UTC, microsecond | no | — | When this arm was evaluated |
| `supersedes` | string or null | yes | — | `run_id` this row corrects, if any |

### Arm identification

| Field | Type | Null? | Unit | Meaning |
| --- | --- | --- | --- | --- |
| `arm` | enum `stub` \| `deterministic` \| `model` \| `naive` | no | — | Which method selected the coordinate |
| `representation` | enum `none` \| `R0` \| `R1` \| `R2` | no | — | `none` for stub/deterministic/naive; R0..R2 for model arms |
| `ranker_version` | string or null | yes | — | Version of the deterministic ranker, when `arm=deterministic` |
| `model_id` | string or null | yes | — | Local model identifier, when `arm=model` |
| `harness_commit` | string, 40 hex | no | — | Git commit of the harness that produced this row |

### Coordinates

Each coordinate is an embedded object valid against the frozen `P0-lab-substrate/contracts/coordinate.md`, carrying
`wall_clock`, `lsn`, `snapshot`, `skew_ms`, `skew_bytes`, `resolved_by`.

| Field | Type | Null? | Meaning |
| --- | --- | --- | --- |
| `ground_truth_coordinate` | coordinate object | no | The optimum, from the oracle. **Byte-identical across all arms of one incident** |
| `chosen_coordinate` | coordinate object or null | yes | What this arm selected; null only if the arm failed to select |
| `naive_coordinate` | coordinate object or null | yes | Last snapshot before the operator's approximate incident time |
| `incident_open_coordinate` | coordinate object | no | Incident boundary, from `incident.json` |
| `incident_close_coordinate` | coordinate object | no | Incident boundary, from `incident.json` |

### Coordinate error — how far off was the pick

| Field | Type | Null? | Unit | Meaning |
| --- | --- | --- | --- | --- |
| `coord_error_bytes` | integer >= 0 or null | yes | WAL bytes | `abs(chosen.lsn - ground_truth.lsn)`, `pg_lsn` arithmetic |
| `coord_error_ms` | integer >= 0 or null | yes | ms | `abs(chosen.wall_clock - ground_truth.wall_clock)` |
| `coord_direction` | enum `exact` \| `before` \| `after` or null | yes | — | Whether the pick was at, earlier than, or later than the optimum |
| `naive_coord_error_bytes` | integer >= 0 or null | yes | WAL bytes | Same measure for the naive comparator |
| `naive_coord_error_ms` | integer >= 0 or null | yes | ms | Same measure for the naive comparator |

> `coord_direction` matters more than its size. A pick *after* the optimum may retain damage, which is qualitatively
> worse than losing legitimate work. Never collapse this into the absolute error alone.

### Outcome error — what the pick actually cost

| Field | Type | Null? | Unit | Meaning |
| --- | --- | --- | --- | --- |
| `legit_rows_lost` | integer >= 0 or null | yes | rows | Legitimate committed rows absent after restoring to `chosen_coordinate` |
| `legit_bytes_lost` | integer >= 0 or null | yes | bytes | Same, in bytes |
| `damage_rows_retained` | integer >= 0 or null | yes | rows | Malicious effects still present after restore |
| `damage_bytes_retained` | integer >= 0 or null | yes | bytes | Same, in bytes |
| `fs_granularity_penalty_ms` | integer >= 0 or null | yes | ms | Loss attributable to snapshot interval rather than selection error (SC-02) |

### Restore and validation

| Field | Type | Null? | Meaning |
| --- | --- | --- | --- |
| `restore_attempted` | boolean | no | Whether a restore was performed |
| `restore_verdict` | enum `stub` \| `correct` \| `incorrect_safe` \| `incorrect_corrupt` \| `not_recovered` | no | `stub` in P1. No P1 code path may emit `correct` |
| `consistency_verdict` | enum `stub` \| `consistent` \| `inconsistent` \| `unknown` | no | Cross-layer consistency of the restored state |
| `validation_detail` | object or null | yes | Free-form per-verdict evidence; never used for scoring |

### Timing

| Field | Type | Null? | Unit | Meaning |
| --- | --- | --- | --- | --- |
| `t_to_coordinate_ms` | integer >= 0 | no | ms | Wall clock from arm start to coordinate selected |
| `t_to_validated_restore_ms` | integer >= 0 or null | yes | ms | Wall clock to a validated restore; null when stubbed |
| `t_total_ms` | integer >= 0 | no | ms | Whole evaluate-arm invocation |

### Ablation telemetry — null until P5

| Field | Type | Null? | Unit | Meaning |
| --- | --- | --- | --- | --- |
| `evidence_bytes_presented` | integer >= 0 or null | yes | bytes | Evidence actually handed to the selecting arm |
| `token_count` | integer >= 0 or null | yes | tokens | Prompt plus completion tokens, `arm=model` only |
| `retrieval_calls` | integer >= 0 or null | yes | count | Queries the arm made against the representation |

### Run context

| Field | Type | Null? | Meaning |
| --- | --- | --- | --- |
| `reset_tier` | enum `t0` \| `t1` \| `t2` | no | Tier used before this arm ran |
| `snapshot_pre_injection` | string | no | Name of the `pre_injection` snapshot |
| `snapshot_post_capture` | string | no | Name of the `post_capture` snapshot |
| `workload_rate_tps` | number > 0 | no | Legitimate workload rate for this incident |
| `workload_mix` | string | no | Legitimate workload operation mix, e.g. `insert:60,update:30,delete:10` |
| `ledger_integrity_ok` | boolean | no | Result of `lab-ledger-verify` at arm start. A row with `false` MUST NOT be analysed |
| `notes` | string or null | yes | Operator annotation. **Never** parsed for scoring (Article XIII) |

## Validation rules

1. **No coercion.** A string where an integer is required is a failure, not a cast. A missing required field is a
   failure, not a null.
2. Every coordinate object validates against the frozen coordinate contract, all six required fields present.
3. If `arm = model` then `model_id` and `representation` in `R0..R2` are required.
4. If `arm` is `stub`, `deterministic` or `naive` then `representation = none`.
5. If `chosen_coordinate` is null then all coordinate-error and outcome-error fields are null.
6. `restore_verdict = correct` requires `damage_rows_retained = 0` and `legit_rows_lost = 0`. Any other combination is
   a contradiction and MUST fail validation.
7. In P1, `restore_verdict` and `consistency_verdict` MUST both be `stub`.
8. `ground_truth_coordinate` MUST be byte-identical across every row sharing an `incident_id`. The writer asserts this
   on append and refuses the row on mismatch.

## Example row

```json
{
  "run_id": "r_20260820T041233Z_9f2a1c",
  "scenario_id": "SC-01",
  "incident_id": "i_20260820T041005Z_3ba77e",
  "replicate": 1,
  "run_ts": "2026-08-20T04:12:33.881204Z",
  "supersedes": null,
  "arm": "stub",
  "representation": "none",
  "ranker_version": null,
  "model_id": null,
  "harness_commit": "4f1c9ab2d3e5f60718293a4b5c6d7e8f90a1b2c3",
  "ground_truth_coordinate": {
    "wall_clock": "2026-08-20T04:10:52.114003Z", "lsn": "3/A2F41C08",
    "snapshot": "s_20260820T041050Z", "skew_ms": 2114, "skew_bytes": 262144,
    "resolved_by": "lsn_first"
  },
  "chosen_coordinate": {
    "wall_clock": "2026-08-20T04:10:50.000000Z", "lsn": "3/A2F00000",
    "snapshot": "s_20260820T041050Z", "skew_ms": 0, "skew_bytes": 0,
    "resolved_by": "snapshot_first"
  },
  "naive_coordinate": null,
  "incident_open_coordinate": { "wall_clock": "2026-08-20T04:10:05.002110Z", "lsn": "3/A1000000", "snapshot": "s_20260820T041005Z", "skew_ms": 0, "skew_bytes": 0, "resolved_by": "snapshot_first" },
  "incident_close_coordinate": { "wall_clock": "2026-08-20T04:11:40.774221Z", "lsn": "3/A3B00000", "snapshot": "s_20260820T041140Z", "skew_ms": 0, "skew_bytes": 0, "resolved_by": "snapshot_first" },
  "coord_error_bytes": 268296, "coord_error_ms": 2114, "coord_direction": "before",
  "naive_coord_error_bytes": null, "naive_coord_error_ms": null,
  "legit_rows_lost": null, "legit_bytes_lost": null,
  "damage_rows_retained": null, "damage_bytes_retained": null,
  "fs_granularity_penalty_ms": null,
  "restore_attempted": false, "restore_verdict": "stub",
  "consistency_verdict": "stub", "validation_detail": null,
  "t_to_coordinate_ms": 412, "t_to_validated_restore_ms": null, "t_total_ms": 1188,
  "evidence_bytes_presented": null, "token_count": null, "retrieval_calls": null,
  "reset_tier": "t2",
  "snapshot_pre_injection": "pre_injection", "snapshot_post_capture": "post_capture",
  "workload_rate_tps": 20, "workload_mix": "insert:60,update:30,delete:10",
  "ledger_integrity_ok": true, "notes": null
}
```

## Invariants

- A row is meaningless without its `incident_id`; grouping by it is what makes the ablation analysable.
- Rows with `ledger_integrity_ok = false` are retained as evidence but excluded from every figure.
- Coordinate error and outcome error are reported together, always. A near-miss coordinate with catastrophic outcome
  error is the most interesting result in the dataset and must never be hidden behind a single number.

---
Frozen at end of P1. Amendments: none.
