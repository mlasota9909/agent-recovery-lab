# FROZEN CONTRACT — Arm B Protocol (prompt, query protocol, extraction & refusal grammar)

**Contract ID:** arm-b-protocol
**Frozen by:** H001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV).
**Produced/consumed by:** `bin/lab-arm-b-prompt` (H003), `bin/lab-arm-b-extract` (H004), `bin/lab-arm-b` (H005).
**Authority:** Article XVII (subject sees only `model_view`), Article I (deterministic harness), Article VIII (refusal
never coerced), Article II (provenance-blind).

## 1. Purpose

Hold the Arm B *procedure* constant across R0/R1/R2 so the representation is the only thing that varies. This contract
fixes the prompt template, the query protocol (which probe, how many turns), the grammar by which the model's answer is
extracted into the frozen `arm-coordinate` shape, and the grammar by which a refusal is recognised. If any of these
varied across representations, the ablation would be confounded.

## 2. The task the model is given

The model is asked, for the SC-01 incident, to identify the **recovery coordinate**: the latest safe point before the
damaging activity began, expressed as a window and/or an LSN it reads out of the `model_view.content`. It is explicitly
told it may answer that it **cannot determine** a coordinate. It is given only the `model_view` (six keys, no answer),
for the recovery-relevant probe `PB-6-candidate-windows`.

## 3. Hard rules

- **R1 — identical prompt except content.** The system prompt, the task instructions, the answer-format instructions
  and the refusal instructions are byte-identical across R0/R1/R2. The only substring that differs between
  representations is the `model_view.content` (and nothing else from the `model_view`). Proven by diffing assembled
  prompts (H003).
- **R2 — single guarded assembly path.** The prompt is assembled in exactly one place (`bin/lab-arm-b-prompt`), which
  calls `bin/lab-modelview-guard` on the `model_view` before templating. No other code path may build model input. A
  bypass is an Article XVII violation.
- **R3 — fixed query protocol.** One probe (`PB-6-candidate-windows`), one model turn, `max_tokens` per the runtime
  contract. No tool use, no multi-turn negotiation, no re-prompting to "try again" after a refusal (re-prompting to
  coerce an answer is prohibited).
- **R4 — deterministic extraction grammar.** The model is instructed to end its answer with one machine-parsable line
  in exactly one of these two forms:
  - `COORDINATE: window=<int> lsn=<postgres-lsn-text>` — a determination; or
  - `REFUSAL: <free-text reason>` — a declared inability to determine.
  `bin/lab-arm-b-extract` parses only this final tagged line. `window`/`lsn` are resolved to the frozen coordinate via
  `bin/lab-coordinate` (integer LSN). If both a COORDINATE and a REFUSAL line appear, or neither, or the COORDINATE is
  unparsable/out-of-range, the outcome is a **refusal** (see R5) — never a guessed coordinate.
- **R5 — refusal is first-class and never coerced.** A `REFUSAL` line, an absent/ambiguous tagged line, or an
  unparsable coordinate all record an `outcome="refusal"` arm result with `lsn_int=null`, the raw completion retained.
  The harness must not substitute a heuristic or "best guess" coordinate for a refusal (Article VIII).
- **R6 — the rationale is the model's verbatim explanation, provenance-scrubbed only for blindness.** The operator-facing
  `rationale` is the model's own words (captured verbatim as qualitative evidence), asserted to contain no
  principal/usename/UID token (Article II). No paraphrase, no invention.
- **R7 — harness determinism.** Given a fixed completion, `bin/lab-arm-b-prompt` (for a fixed model_view),
  `bin/lab-arm-b-extract` and the scoring wiring are pure functions: re-running them on the recorded completion yields a
  byte-identical arm-coordinate and score. Model non-determinism is characterised separately by K replicates (§4).
- **R8 — replicates.** Each representation is run `K` times (K recorded here, default 5). All K completions are
  retained; the reported per-representation outcome and its replicate agreement are computed from the K records.

## 4. Replicate & outcome schema (per Arm B run; the coordinate itself is the frozen `arm-coordinate` shape)

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | the SC-01 incident (shared with Arm A and the representations) |
| `representation` | string | `R0` / `R1` / `R2` |
| `replicate` | integer | 0..K-1 |
| `outcome` | string | `determination` or `refusal` |
| `arm_coordinate` | object \| null | the frozen `arm-coordinate` record (arm=`arm_b`); `null` on refusal |
| `raw_completion_sha256` | string | SHA-256 of the retained verbatim completion |
| `prompt_tokens` | integer | real prompt tokens the model consumed (runtime-reported) |
| `completion_tokens` | integer | real completion tokens |
| `latency_ms` | integer | wall-clock invocation latency |
| `score` | object \| null | the P4 verdict + `damage_rows_retained` + `legit_rows_lost`; `null` on refusal |
| `coordinate_error` | object \| null | objective error vs ground truth (LSN delta + rows); `null` on refusal |

## 5. Example final answer lines (illustrative, non-normative)

A determination:
```
...reasoning over the summarised windows...
COORDINATE: window=14 lsn=3/C4B2FE
```
A refusal:
```
...the evidence does not let me localise the burst...
REFUSAL: multiple windows show comparable deletion volume; cannot isolate a single safe point
```

## 6. Change control

Frozen at H001 and hash-recorded in `logs/review/H001/`. Later changes supersede via `arm-b-protocol.amendment-N.md`
with its own ADR; this file stays byte-identical (Article XV).
