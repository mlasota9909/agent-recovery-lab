# FROZEN CONTRACT — Candidate Coordinate Record (C5 output)

**Contract ID:** candidate-coordinate
**Frozen by:** D001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV), never by silent edit.
**Consumed by:** the Arm A ranker (C7, D006), and — read-only — the P4 restore harness and P5/P6 Arm B.

## 1. Purpose

Defines the single record shape emitted by the derived-analytics layer for each candidate recovery coordinate it
proposes. A candidate is a point the ledger evidence suggests *might* be a safe recovery target; the ranker (C7) later
orders candidates and selects one. This contract fixes what a candidate carries so the ranker, the results row and any
later consumer agree without renegotiation.

## 2. Hard rules

- **R1 — provenance-blind.** A candidate record MUST NOT contain, and its producer MUST NOT read, any provenance
  field: `principal`, `session_user`, `usename`, or originating UID. Detection is provenance-blind (Article II). A
  field named or aliased to any of these in a candidate record is a contract violation.
- **R2 — integer LSN.** Every LSN is carried both as the canonical Postgres text form (`"3/A0F1B8"`) **and** as a
  64-bit integer (`(high<<32)+low`). All ordering and "at or below" resolution use the integer. String comparison of
  LSNs is prohibited (the `3/9` vs `3/10` trap).
- **R3 — cross-layer resolved.** Every candidate resolves to a filesystem snapshot per ADR-008: the newest snapshot
  whose recorded LSN is ≤ the candidate LSN. The resulting skew is recorded, never discarded.
- **R4 — reproducible.** For a fixed ledger and fixed analytics config, the set of candidate records is
  byte-identical across runs. No wall-clock, PID, or nondeterministic ordering may leak into the record.
- **R5 — no ground-truth.** A candidate record MUST NOT contain any field derived from the injection log or the
  oracle optimum. Candidates are produced from evidence only.

## 3. Record schema (JSONL, one object per candidate)

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | the incident this candidate belongs to |
| `candidate_id` | string | stable id, deterministic function of `(incident_id, lsn_int)` |
| `lsn_text` | string | canonical Postgres LSN text form |
| `lsn_int` | integer | `(high<<32)+low`; the value used for all ordering |
| `wall_clock` | string (ISO-8601, UTC) | heartbeat-resolved wall time at this LSN |
| `snapshot` | string | resolved filesystem snapshot name (newest with recorded LSN ≤ `lsn_int`) |
| `skew_seconds` | number | wall-clock gap between `lsn_int` and the resolved snapshot's LSN |
| `skew_rows` | integer | committed ledger rows falling in the skew gap |
| `features` | object | the deterministic feature scores below (§4) |
| `analytics_version` | string | version tag of the analytics config that produced this record |

## 4. `features` object (all deterministic, all provenance-blind)

| Field | Type | Meaning |
| --- | --- | --- |
| `proximity_to_first_suspicious` | number | integer-LSN distance from this candidate to the first window whose anomaly score crosses threshold; smaller is safer-latest |
| `data_loss_rows` | integer | committed legitimate-looking rows between this candidate and the safe frontier (volume that would be lost if we recover here) |
| `consistency_risk` | number | flag/score for filesystem-vs-DB skew or straddling an open transaction at this LSN |
| `anomaly_score` | number | mean+3σ anomaly score of the window containing this candidate |
| `ddl_in_window` | boolean | whether a DDL record falls in this candidate's window |

The feature semantics are fixed here so the ranker (C7) and any later analysis read the same definitions. The
*weights* over these features are NOT part of this contract — they live in the versioned ranker config (D006), so the
ranker can be retuned without breaking the candidate schema.

## 5. Example (illustrative, non-normative)

```json
{"incident_id":"SC-01-20260825T0100Z-a1","candidate_id":"SC-01-20260825T0100Z-a1:12897342","lsn_text":"3/C4B2FE","lsn_int":12897342,"wall_clock":"2026-08-25T01:03:41Z","snapshot":"labpool/victim@snap_0007","skew_seconds":0.82,"skew_rows":3,"features":{"proximity_to_first_suspicious":118,"data_loss_rows":0,"consistency_risk":0.0,"anomaly_score":0.11,"ddl_in_window":false},"analytics_version":"p3-analytics-1"}
```

## 6. Change control

Frozen at D001 and hash-recorded in `logs/review/D001/`. Any later change is a new superseding amendment file
(`candidate-coordinate.amendment-N.md`) with its own ADR; this file stays byte-identical (Article XV).
