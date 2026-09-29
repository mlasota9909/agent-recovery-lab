# Spec — P6: Arm B, the modest-local-model harness

**Feature ID:** P6-arm-b-model-harness
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P1 (results row), P3 (arm-coordinate contract, SC-01 incident, Arm A/naive baselines), P3.1 (read-only
gates + regression), P4 (restore+validate scoring path), P5 (representations R0/R1/R2 + query interface), P5.1
(`model_view`/`reference` split + `bin/lab-modelview-guard`).
**Blocks:** P7 (run matrix) drives Arm B across all scenarios; P8 (analysis) reports the R0-vs-R1-vs-R2 result.

## 1. Purpose

Run the experiment. Point one modest, offline local model at the SC-01 incident's three representations — R0, R1, R2 —
through the guarded `model_view` interface, and record the recovery coordinate the model chooses for each, scored
objectively against ground truth via the unchanged P4 restore+validate path. The deliverable is the R0-vs-R1-vs-R2
comparison at **fixed model and fixed scenario**: the evidence that a purpose-built representation, not model size, is
what lets a modest model locate the recovery point.

The model is held constant; the representation is the independent variable (ADR-004, ADR-P5-1). P6 adds the subject
(the model) and the machinery to run it honestly; it changes nothing upstream.

## 2. Background — what already exists

P6 is invocation-and-scoring over finished, certified infrastructure. Reuse, do not rebuild:

- `bin/lab-repr-modelview` (six-key subject surface), `bin/lab-modelview-guard` (the guard), `bin/lab-repr-reference`
  (the answer — parity/telemetry only), `bin/lab-repr-query`, and the SC-01 representation artefacts under
  `var/repr/<incident>/` (P5/P5.1).
- FROZEN `arm-coordinate.md` — Arm B emits exactly this shape (`arm=arm_b`, `representation` in {R0,R1,R2}), with the
  `selection_inputs` anti-peek block.
- FROZEN `results-row.md` — `evidence_bytes`/`token_count` take Arm B telemetry; `recovery_coordinate.*` and the
  verdict come from scoring.
- The **unchanged P4 restore+validate path** and its 4-level verdict; `bin/lab-coordinate` (integer LSN resolver).
- `bin/lab-regression`, `bin/lab-gate-readonly-check` (P3.1); the reconciled SC-01 incident and Arm A/naive results
  (P3), which Arm B is compared against.

P6 adds: the two contracts (model runtime + Arm B protocol), the offline model wrapper, the single guarded
prompt-assembly choke point, deterministic coordinate extraction, the refusal-aware run driver, verbatim explanation
capture, real-token/latency telemetry, the scoring wiring, the headline, and the gate.

## 3. Scope

### In scope

- Two frozen contracts: `model-runtime.md` (offline model id/weights/decoding/loopback) and `arm-b-protocol.md`
  (prompt template, query protocol, extraction grammar, refusal grammar, replicate count K).
- `bin/lab-model` — offline local-model invocation with pinned decoding, verbatim I/O + real token counts + latency,
  and a per-invocation outbound-socket check (offline proof).
- `bin/lab-arm-b-prompt` — the single guarded prompt-assembly choke point; identical across R0/R1/R2 except
  `model_view.content`; calls `bin/lab-modelview-guard`.
- `bin/lab-arm-b-extract` — deterministic parse of the model's final tagged line into the frozen arm-coordinate shape;
  unparsable/ambiguous -> refusal (never a guess).
- `bin/lab-arm-b` — the refusal-aware run driver: run K replicates per representation, record determinations and
  refusals, capture verbatim rationale, wire telemetry.
- Scoring wiring: the extracted coordinate scored through the unchanged P4 restore+validate path -> verdict +
  `damage_rows_retained` + `legit_rows_lost`, emitted as arm-coordinate/results with `arm=arm_b`.
- The SC-01 headline: same model, R0/R1/R2, K replicates, objective coordinate error vs ground truth, all appended
  automatically; the R0-vs-R1-vs-R2 comparison table; discrimination negatives (guard, refusal, provenance).
- `bin/lab-verify-p6` tiered read-only gate; prior contract-hash re-verification; regression; the P6 handoff.

### Out of scope

- SC-02/03/04 Arm B runs and the full run matrix (that is **P7**). P6 establishes Arm B on the SC-01 incident.
- Any change to a frozen contract, or any new field on the results row / arm-coordinate / representation-interface
  contracts.
- Any modification to the P4 restore+validate path, the representations, or the guard (all reused unchanged).
- Fine-tuning, training, adapters, sampling, multi-turn/tool-use protocols, or any outbound model call.
- Choosing or tuning the ranker (Arm A is P3); P6 does not re-open Arm A.

## 4. Functional requirements

- **FR-1 Contracts + entry gate.** Both P6 contracts written and hash-frozen. The tranche opens only when
  `bin/lab-regression` is green, the SC-01 representations R0/R1/R2 exist and are admissible (P5 F006 manifests), and
  the offline model runtime is healthy and provably offline; H001 records all three plus the discovered model
  id/quantisation/weights hash. `bin/lab-ready` exiting 1 (frozen headline) is expected and not a blocker.
- **FR-2 Offline model invocation.** `bin/lab-model` invokes the pinned local model over loopback with greedy decoding
  and a fixed seed, captures verbatim prompt/completion + real token counts + latency, and verifies no outbound socket
  was opened during the call.
- **FR-3 Single guarded prompt choke point.** `bin/lab-arm-b-prompt` is the only path that assembles model input; it
  guards the `model_view` and templates the fixed prompt; the assembled prompt is identical across R0/R1/R2 except the
  `content`. No other code path builds model input.
- **FR-4 Deterministic extraction.** `bin/lab-arm-b-extract` parses the model's final tagged line into the frozen
  arm-coordinate shape (integer-LSN resolved); unparsable/ambiguous/out-of-range or an explicit refusal line yields a
  refusal outcome; extraction is byte-identical on re-run over a recorded completion.
- **FR-5 Refusal-aware run driver.** `bin/lab-arm-b` runs K replicates per representation, records each as a
  determination or a refusal with the raw completion retained, and never coerces a refusal into a guess.
- **FR-6 Verbatim explanation capture.** The model's operator-facing rationale is captured verbatim into the results
  directory, asserted provenance-blind, and wired to `arm-coordinate.rationale`.
- **FR-7 Real telemetry.** Real model `prompt_tokens` and `latency_ms` per run are recorded and land in the results
  row's `token_count`/telemetry, recorded as distinct from P5's pinned-tokenizer estimate (closes ADR-P5-5).
- **FR-8 Scoring through unchanged P4.** Each determination's coordinate is scored through the unchanged P4
  restore+validate path, yielding the 4-level verdict, `damage_rows_retained` and `legit_rows_lost`, emitted as an
  arm-coordinate/results row with `arm=arm_b` and `selection_inputs.read_*` all false.
- **FR-9 Headline.** On SC-01, the same model is run over R0/R1/R2 (K replicates each); the objective coordinate error
  vs ground truth is computed for each and appended automatically; the R0-vs-R1-vs-R2 comparison is produced from
  machine-readable fields; discrimination negatives prove the guard, the refusal path and provenance-blindness are
  enforced.
- **FR-10 Gate + handoff.** `bin/lab-verify-p6` runs every P6 check with per-tier totals and is read-only over the
  evidence root; all prior contract hashes re-verify unchanged; `bin/lab-regression` green; the P6 handoff records the
  model pinning, the guarded choke point, the refusal path, the real-token-vs-estimate finding, the R0-vs-R1-vs-R2
  result, and states P7 drives the matrix.

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P6-01 | M | Both P6 contracts exist, example JSON parses, and are hash-frozen in `logs/review/H001/`; the entry gate is recorded (regression green, SC-01 R0/R1/R2 admissible, model runtime healthy + offline) with the discovered `model_id`/`quantization`/`weights_sha256` |
| AC-P6-02 | M | `bin/lab-model` invokes the model over a **loopback** endpoint with `temperature=0`, fixed `seed` and recorded `weights_sha256`; a per-invocation check shows **no outbound socket** was opened (Article X); verbatim prompt/completion + real `prompt_tokens`/`completion_tokens`/`latency_ms` are captured |
| AC-P6-03 | M | Every model input is produced by `bin/lab-repr-modelview` and passed through `bin/lab-modelview-guard`; a `model_view` carrying an `answer`/`reference` key, a coordinate field, or a provenance token is **refused before reaching the model** |
| AC-P6-04 | M | There is exactly **one** prompt-assembly path (`bin/lab-arm-b-prompt`); a repository scan finds no other code that assembles or sends model input bypassing the guard (the choke-point property) |
| AC-P6-05 | M | The assembled prompt is byte-identical across R0/R1/R2 except the injected `model_view.content` (protocol parity), proven by diffing the three assembled prompts for `PB-6` |
| AC-P6-06 | M | `bin/lab-arm-b-extract` parses the final tagged line into the frozen arm-coordinate shape with integer-LSN resolution; re-running extraction on a recorded completion yields a **byte-identical** arm-coordinate |
| AC-P6-07 | M | A completion with a `REFUSAL` line, no tagged line, an ambiguous double line, or an unparsable/out-of-range coordinate yields `outcome="refusal"` with `lsn_int=null` and the raw completion retained — **never a fabricated coordinate**; the negative proves a coerced guess is caught |
| AC-P6-08 | M | The model's operator-facing rationale is captured verbatim, wired to `arm-coordinate.rationale`, and asserted provenance-blind (no principal/usename/session_user/UID token) |
| AC-P6-09 | M | Real model `prompt_tokens` and `latency_ms` are recorded per run and land in the results row; the real token count is recorded **distinct** from P5's pinned-tokenizer `token_estimate` for the same probe/representation (closes ADR-P5-5) |
| AC-P6-10 | M | Each determination's coordinate is scored through the **unchanged** P4 restore+validate path (P4 gate hash unchanged), producing the 4-level verdict, `damage_rows_retained` and `legit_rows_lost` |
| AC-P6-11 | M | Each Arm B result is the frozen `arm-coordinate` shape with `arm=arm_b`, `representation` in {R0,R1,R2}, and `selection_inputs.read_injection_log=read_oracle_optimum=read_provenance=false`; the harness rejects any arm-coordinate with a `read_*` true |
| AC-P6-12 | M | **Harness determinism:** given a fixed recorded completion, prompt assembly (for a fixed model_view), extraction and scoring re-run **byte-identical**, isolating model non-determinism from harness non-determinism |
| AC-P6-13 | A | The model call is pinned (greedy + fixed seed + recorded weights hash); K replicates per representation are recorded and their replicate agreement (identical-coordinate rate) is reported — an honest characterisation of the stochastic subject (asserts on the recorded replicate fields) |
| AC-P6-14 | M | **Headline:** the same model is run over R0/R1/R2 on SC-01; the objective coordinate error vs ground truth (LSN delta and rows) is computed for each from committed fields and appended automatically to results; the R0-vs-R1-vs-R2 comparison table is produced from machine-readable fields |
| AC-P6-15 | M | **Discrimination:** with the guard deliberately bypassed so the model input carries the `reference` answer, the recorded outcome changes (the model can then read the coordinate) and the guard/`selection_inputs` check catches the bypass — proving the guard and blindness are enforced, not assumed |
| AC-P6-16 | M | Arm B results are incident-scoped: every arm-coordinate/result carries the single SC-01 `incident_id` shared with Arm A (P3) and the representations (P5), so P7/P8 can compare arms on one incident |
| AC-P6-17 | M | `bin/lab-verify-p6` reports every criterion with per-tier totals printed separately, exit 0, and is read-only over the evidence root (proven by `bin/lab-gate-readonly-check`) |
| AC-P6-18 | M | All prior gates still green via regression (`-p1` 24/24 … `-p5` 19/19, `-p5.1` 16/16); every prior contract hash unchanged incl. `capture-completeness.md`, `representation-interface.md` and `representation-interface.amendment-1.md` byte-identical; `bin/lab-regression` green against pinned fixtures |
| AC-P6-19 | A | The P6 handoff records the model pinning, the guarded choke point, the refusal path, the real-token-vs-estimate finding, the SC-01 R0-vs-R1-vs-R2 result, and states P7 drives the run matrix (asserted on machine-readable fields; anti-goal-inversion guarded) |

Seventeen of nineteen criteria are tier M. The two tier A criteria are the replicate characterisation (AC-P6-13) and
the handoff record (AC-P6-19), both of which assert on machine-readable fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p6` green with per-tier totals and proven read-only; both P6 contracts frozen; the offline model
pinned (greedy + seed + weights hash) and provably offline; a single guarded prompt-assembly choke point with no
bypass; deterministic extraction with a first-class refusal path that is never coerced; verbatim provenance-blind
rationale capture; real token/latency telemetry recorded distinct from P5's estimate; every determination scored
through the unchanged P4 path into the frozen arm-coordinate shape with `read_*` all false; the SC-01 headline running
the same model over R0/R1/R2 with objective error vs ground truth appended automatically and the R0-vs-R1-vs-R2 table
produced from machine-readable fields; the discrimination negatives proving guard, refusal and blindness are enforced;
all prior gates, regression and contract hashes unchanged; and the P6 handoff written without anti-goal inversion.
