# FROZEN CONTRACT AMENDMENT 1 — Model-View / Reference Separation

**Amends:** `representation-interface` (frozen by F001)
**Amendment ID:** representation-interface.amendment-1
**Frozen by:** G002
**Status:** FROZEN — supersedes §4 and §6 of the base contract for the purpose of what a subject may be shown. The base
`representation-interface.md` file remains byte-identical (Article XV); this amendment governs where a conflict exists.
**Authority:** Article XVII (subject-visible surface excludes the reference answer), Article XV (amendment by
supersession).

## 1. Why this amendment exists

The base contract §4 puts `answer` and `content` in one response envelope, and §5 designates
`PB-6-candidate-windows` as the probe P6's model uses to locate a recovery coordinate. `answer` for PB-6 is that
coordinate. Handing the whole envelope to the model would let it read the coordinate instead of deriving it from
`content`, voiding the R0-vs-R1-vs-R2 comparison. This amendment separates the subject-visible surface from the
reference answer so the comparison measures the representation, not a leaked answer.

## 2. The two surfaces

The base response envelope (§4) is unchanged as an **internal** structure produced by `bin/lab-repr-query`. What
changes is that no consumer acting as an experimental subject may be shown the whole envelope. Two projections are
defined over it:

### 2.1 `model_view` — the only object a subject (P6's model) may be shown

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | echoed |
| `representation` | string | `R0` / `R1` / `R2` |
| `probe_id` | string | one of the fixed probe IDs (base §5) |
| `params` | object | probe parameters |
| `content` | string | the evidence the representation surfaces (differs across representations) |
| `telemetry` | object | `evidence_bytes`, `token_estimate`, `tokenizer` (differs across representations) |

The `model_view` carries **no `answer`** and **no `reference`** key. It is produced by `bin/lab-repr-modelview`.

### 2.2 `reference` — used only to score-adjacent parity/telemetry checks, never shown to a subject

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | echoed |
| `representation` | string | echoed |
| `probe_id` | string | echoed |
| `answer` | object | the structured answer (base §5 schema), identical across R0/R1/R2 for a probe |

The `reference` is produced by `bin/lab-repr-reference`. It exists so the parity test can confirm all three
representations are asked to support the same result, and so telemetry has a stable anchor. It MUST NOT be included in
any bytes handed to a subject.

## 3. Hard rules (supersede base §4/§6 on conflict)

- **A1 — subject sees only `model_view`.** Any consumer that is an experimental subject (P6's model) is given the
  `model_view` and nothing else. Handing it `answer`, `reference`, or the full base envelope is a violation of Article
  XVII.
- **A2 — `model_view` has exactly six keys.** `incident_id`, `representation`, `probe_id`, `params`, `content`,
  `telemetry`. No `answer`, no `reference`, no coordinate field at the top level.
- **A3 — parity on the model_view surface.** For a given probe and incident, the `model_view` is structurally identical
  across R0/R1/R2; only `content` and `telemetry` differ. (This restates base R3 on the subject-visible surface.)
- **A4 — guard-enforced.** `bin/lab-modelview-guard` mechanically refuses any `model_view` carrying an `answer`/`reference`
  key, a structured coordinate-answer field (`candidates`, an answer-level `last_safe_lsn_int`, or
  `first_lsn_int`/`last_lsn_int` presented as answer fields), or a provenance token. LSN digits appearing inside the
  `content` string are permitted — that is the evidence the subject reads to derive the coordinate.
- **A5 — provenance-blind (base R5 unchanged).** No `principal`/`usename`/`session_user`/UID in `model_view`, `content`,
  `reference` or any summary.
- **A6 — read-only, deterministic (base R4, R7 unchanged).** Producing either projection mutates nothing and is a pure
  function of (representation artefact, probe, params); re-run is byte-identical.

## 4. Headline probe (clarifies base §5)

The recovery-relevant probe is `PB-6-candidate-windows`. The P5 headline (F009) is reported on **PB-6**: R2
`evidence_bytes` for the PB-6 `model_view.content` is strictly and materially less than R0's. Any earlier reference to
`PB-4` as the headline probe is a labelling error corrected here; the measured property (R2 evidence-bytes < R0 on the
recovery probe) is unchanged.

## 5. Example (illustrative, non-normative)

Same probe, two representations — `model_view` only, note **no `answer`**, identical structure, differing `content`
and `telemetry`:

```json
{
  "incident_id": "SC-01-20260825T0100Z-a1",
  "representation": "R0",
  "probe_id": "PB-6-candidate-windows",
  "params": {"top_n": 3},
  "content": "12897001 DELETE orders ...\n12897002 DELETE orders ...\n(... many raw event lines ...)",
  "telemetry": {"evidence_bytes": 38674, "token_estimate": 9669, "tokenizer": "qwen2-bpe-vendored-1"}
}
```

```json
{
  "incident_id": "SC-01-20260825T0100Z-a1",
  "representation": "R2",
  "probe_id": "PB-6-candidate-windows",
  "params": {"top_n": 3},
  "content": "Window 15 [12897001..12897850]: 200 DELETE on relation orders, 3 legitimate INSERT; anomaly 250.5. Candidate windows by anomaly: 15, 14, 13. Prior windows nominal.",
  "telemetry": {"evidence_bytes": 199, "token_estimate": 52, "tokenizer": "qwen2-bpe-vendored-1"}
}
```

The corresponding `reference` (never shown to the model), identical across R0/R1/R2:

```json
{
  "incident_id": "SC-01-20260825T0100Z-a1",
  "representation": "R2",
  "probe_id": "PB-6-candidate-windows",
  "answer": {"candidates": [{"window_index": 15, "last_safe_lsn_int": 12897000, "anomaly_score": 250.5}]}
}
```

## 6. Change control

Frozen at G002 and hash-recorded in `logs/review/G002/`. The base `representation-interface.md` stays byte-identical
(its F001 hash must keep verifying). Later changes supersede via `representation-interface.amendment-2.md` with its own
ADR (Article XV).
