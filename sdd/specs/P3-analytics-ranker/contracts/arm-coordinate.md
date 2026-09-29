# FROZEN CONTRACT — Arm Coordinate (the coordinate an arm selects)

**Contract ID:** arm-coordinate
**Frozen by:** D001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV).
**Produced by:** Arm A ranker (C7, D006) and the naive comparator (D007); later also Arm B (C8, P6).
**Consumed by:** the P1 `evaluate-arm` phase and results row; the P4 restore harness.

## 1. Purpose

Both experiment arms — the deterministic ranker and, later, the modest local model — must hand back a recovery
coordinate in **one identical shape**, so the harness can score either arm the same way and Arm B cannot be told
apart from Arm A by anything except the coordinate it chose and the rationale it gives. This is what makes the
ablation clean. This contract fixes that shape.

## 2. Hard rules

- **R1 — one shape for every arm.** Arm A, the naive comparator and Arm B all emit exactly this record. No arm adds
  or removes a field. Arm B's extra telemetry (tokens, latency) lives in the results row, not here.
- **R2 — read-only selection.** Emitting an arm coordinate never executes a restore and never carries write
  authority. The coordinate is a *recommendation*; the harness performs the restore against it (P4).
- **R3 — integer LSN (R2 of the candidate contract).** `lsn_int` is authoritative for all comparison; `lsn_text` is
  the human/Postgres form. No string LSN comparison.
- **R4 — aligns with the results row.** `lsn_text`, `lsn_int`, `wall_clock` and `snapshot` map one-to-one onto the
  FROZEN `results-row.md` `recovery_coordinate.*` fields. This contract may not contradict that one.
- **R5 — provenance-blind selection path.** The value of the coordinate is a function of provenance-blind evidence and
  (for the naive arm) an operator-supplied approximate incident time only. Never of the injection log or oracle
  optimum. The rationale text must not embed provenance either.
- **R6 — declared selector version.** Every coordinate names the exact selector that produced it: for Arm A the
  ranker config version; for naive the comparator version and its incident-time-error parameter; for Arm B the model
  id and representation level.

## 3. Record schema (one JSON object per arm evaluation)

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | the incident evaluated |
| `arm` | string | one of `arm_a`, `naive`, `arm_b` |
| `selector_version` | string | ranker config version / comparator version / model id — the exact selector |
| `representation` | string | `n/a` for Arm A and naive; `R0`/`R1`/`R2` for Arm B |
| `lsn_text` | string | chosen coordinate, canonical Postgres LSN text |
| `lsn_int` | integer | chosen coordinate, `(high<<32)+low` — authoritative |
| `wall_clock` | string (ISO-8601, UTC) | heartbeat-resolved wall time at the chosen LSN |
| `snapshot` | string | resolved filesystem snapshot (newest with LSN ≤ `lsn_int`) |
| `chosen_candidate_id` | string \| null | the `candidate_id` selected (Arm A); `null` if the arm selects without candidates (naive) |
| `rationale` | string | operator-facing explanation; deterministic for Arm A; provenance-free |
| `selection_inputs` | object | the exact inputs the selector was given (see §4) — the anti-peek audit record |

## 4. `selection_inputs` — the anti-peek audit record

Every arm records precisely what it was allowed to see, so the operator can verify no ground-truth leaked in:

| Field | Type | Meaning |
| --- | --- | --- |
| `ledger_view` | string | the provenance-blind view/query used (must be a default, principal-free view) |
| `approx_incident_time` | string \| null | operator-supplied approximate time (naive only); `null` for Arm A |
| `incident_time_error_seconds` | number \| null | the declared, fixed error applied to the naive time; `null` for Arm A |
| `read_injection_log` | boolean | MUST be `false` for every arm |
| `read_oracle_optimum` | boolean | MUST be `false` for every arm |
| `read_provenance` | boolean | MUST be `false` for every arm |

An arm evaluation whose `selection_inputs` has any of the last three `true` is a contract violation and the harness
rejects it. This is the machine-readable form of "detection does not peek at the answer".

## 5. Example (illustrative, non-normative)

```json
{"incident_id":"SC-01-20260825T0100Z-a1","arm":"arm_a","selector_version":"p3-rank-1","representation":"n/a","lsn_text":"3/C4B2FE","lsn_int":12897342,"wall_clock":"2026-08-25T01:03:41Z","snapshot":"labpool/victim@snap_0007","chosen_candidate_id":"SC-01-20260825T0100Z-a1:12897342","rationale":"Latest candidate before the first window exceeding mean+3sigma deletion density; zero legitimate rows lost; no cross-layer skew.","selection_inputs":{"ledger_view":"db_changes","approx_incident_time":null,"incident_time_error_seconds":null,"read_injection_log":false,"read_oracle_optimum":false,"read_provenance":false}}
```

## 6. Change control

Frozen at D001 and hash-recorded in `logs/review/D001/`. Later changes supersede via
`arm-coordinate.amendment-N.md` with its own ADR; this file stays byte-identical (Article XV).
