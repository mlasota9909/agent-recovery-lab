# FROZEN CONTRACT — Representation Query Interface (identical across R0/R1/R2)

**Contract ID:** representation-interface
**Frozen by:** F001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV).
**Produced by:** `bin/lab-repr-query` (F005), serving R0 (F002), R1 (F003), R2 (F004).
**Consumed by:** the P6 Arm B model harness (a modest local model), and the P5 parity/telemetry tests.

## 1. Purpose

The three representations exist to be compared. That comparison is only clean if a consumer cannot tell them apart
except by the content each returns. This contract fixes **one** request envelope, **one** response envelope, and
**one** fixed probe set, presented **identically** across R0, R1 and R2. A representation may return different content
and will report different telemetry, but it may not alter the shape of the conversation. This is the property that
lets P6 attribute any difference in the model's success to the representation rather than the interface.

## 2. Hard rules

- **R1 — one envelope for every representation.** The request and response schemas in sections 3 and 4 are identical
  for R0, R1 and R2. No representation adds, removes or renames an envelope field.
- **R2 — one fixed probe set.** The probes in section 5 are frozen by ID. Every representation must answer every probe.
  A representation may not expose a probe another does not, nor decline a probe another answers.
- **R3 — only `content` and `telemetry` may differ.** For a given probe and incident, the `representation`, `probe_id`,
  `answer` shape, and all envelope fields are identical in structure across R0/R1/R2. The `content` payload (the
  evidence the representation surfaces) and the `telemetry` (bytes, token estimate) legitimately differ — that
  difference is the experiment.
- **R4 — read-only.** Answering a probe never mutates the representation, the ledger or any evidence. The interface is
  a pure function of (representation artefact, probe, params).
- **R5 — provenance-blind (Article II).** No `principal`, `usename`, `session_user` or UID appears in a request, a
  response, the `content`, the `answer`, or any summary surfaced through the interface. The consumer sees what changed
  and when, never who.
- **R6 — integer LSN.** Any coordinate or window bound the interface returns carries an authoritative integer
  `lsn_int`; `lsn_text` is the human form. No string LSN comparison anywhere behind the interface.
- **R7 — deterministic.** The same (representation, probe, params) over the same incident returns a byte-identical
  response, including telemetry. Asserted by re-run.

## 3. Request envelope (identical across R0/R1/R2)

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | the incident whose representation is queried |
| `representation` | string | `R0` / `R1` / `R2` — which representation to answer from |
| `probe_id` | string | one of the fixed probe IDs in section 5 |
| `params` | object | probe parameters (see each probe); `{}` when a probe takes none |

## 4. Response envelope (identical across R0/R1/R2)

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | echoed |
| `representation` | string | echoed (`R0`/`R1`/`R2`) |
| `probe_id` | string | echoed |
| `answer` | object | the structured answer to the probe — same schema per probe across all three representations (see section 5) |
| `content` | string | the evidence the representation surfaces to support the answer (the payload a model would read); differs across representations |
| `telemetry` | object | `evidence_bytes` (integer, exact UTF-8 byte length of `content`), `token_estimate` (integer), `tokenizer` (string, name+version of the pinned tokenizer used) |

## 5. The fixed probe set (frozen by ID)

Each probe defines its `params` and the `answer` schema that every representation must return identically. `content`
is representation-specific; `answer` is not.

| Probe ID | Params | `answer` schema (identical across R0/R1/R2) |
| --- | --- | --- |
| `PB-1-window-events` | `{window_index:int}` | `{window_index, event_count, first_lsn_int, last_lsn_int}` |
| `PB-2-deletion-density` | `{}` | `{windows:[{window_index, delete_count, anomaly_score}]}` |
| `PB-3-entity-churn` | `{top_n:int}` | `{entities:[{entity, kind, change_count}]}` (kind ∈ relation/file) |
| `PB-4-earliest-anomaly` | `{}` | `{window_index, first_lsn_int, last_lsn_int, anomaly_score}` |
| `PB-5-entity-activity` | `{entity:string}` | `{entity, kind, change_count, first_lsn_int, last_lsn_int}` |
| `PB-6-candidate-windows` | `{top_n:int}` | `{candidates:[{window_index, last_safe_lsn_int, anomaly_score}]}` |

`PB-6-candidate-windows` is the recovery-relevant probe: it is the one P6's model uses to locate a recovery
coordinate, and the one the P5 headline (F009) measures the R0-vs-R2 evidence-bytes delta on.

## 6. Example (illustrative, non-normative)

Same probe, same envelope, two representations — note identical `answer`, different `content` and `telemetry`:

```json
{
  "incident_id": "SC-01-20260825T0100Z-a1",
  "representation": "R0",
  "probe_id": "PB-4-earliest-anomaly",
  "answer": {"window_index": 15, "first_lsn_int": 12897001, "last_lsn_int": 12897850, "anomaly_score": 250.5},
  "content": "12897001 DELETE orders ...\n12897002 DELETE orders ...\n(... 848 more raw event lines ...)",
  "telemetry": {"evidence_bytes": 61240, "token_estimate": 15310, "tokenizer": "qwen2-bpe-vendored-1"}
}
```

```json
{
  "incident_id": "SC-01-20260825T0100Z-a1",
  "representation": "R2",
  "probe_id": "PB-4-earliest-anomaly",
  "answer": {"window_index": 15, "first_lsn_int": 12897001, "last_lsn_int": 12897850, "anomaly_score": 250.5},
  "content": "Window 15 [12897001..12897850]: 201 DELETE on relation orders, 3 legitimate INSERT; anomaly 250.5 (mean+3sigma exceeded). Prior window 14: nominal.",
  "telemetry": {"evidence_bytes": 168, "token_estimate": 44, "tokenizer": "qwen2-bpe-vendored-1"}
}
```

## 7. Change control

Frozen at F001 and hash-recorded in `logs/review/F001/`. Later changes supersede via
`representation-interface.amendment-N.md` with its own ADR; this file stays byte-identical (Article XV).
