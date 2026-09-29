# Spec — P5.1: Model-View Separation (the subject must not be handed the answer)

**Feature ID:** P5.1-modelview-separation
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P5 (accepted, pending this remediation)
**Blocks:** P6 (Arm B model harness) — P6 must hand the model a surface that excludes the reference answer; that
surface, and the guard enforcing it, must exist and be frozen first.

## 1. Purpose

Split the subject-visible surface of the representation query interface (`model_view`) from the reference answer
(`reference`), so that the modest local model in P6 is given evidence to reason over and is **not** given the
pre-computed recovery coordinate. Enforce the split with a mechanical guard. Preserve the reference answer for the
parity and telemetry tests that legitimately use it. Add the constitutional principle that stops any future tranche
from handing a subject the answer it is being tested on. Change no representation artefact and no frozen contract file.

## 2. Problem statement

**D1 — the answer key is in the subject-visible envelope.** The frozen `representation-interface` response envelope
(§4) contains both `content` (the evidence a model reads) and `answer` (the pre-computed structured result). For the
recovery probe `PB-6-candidate-windows`, `answer` is the recovery coordinate itself
(`candidates:[{window_index, last_safe_lsn_int, anomaly_score}]`), computed by the deterministic pipeline and identical
across R0/R1/R2. Hard rule R3 of the contract fixes `answer` as identical in structure across all three representations
— which is correct for a parity reference, but means that if P6 passes the response envelope to the model, the model
reads the coordinate for free from `answer`. P6 scores the model's coordinate through the P4 restore+validate path
against the oracle, so `answer` has no scoring role; its only legitimate P5 uses are the parity check (all three
representations support the same result) and telemetry. But nothing mechanically prevents `answer` from reaching the
model, so the R0-vs-R1-vs-R2 ablation — the entire contribution — could be measuring a leaked answer rather than the
representation. The contract's §5 designates PB-6 as "the one P6's model uses to locate a recovery coordinate", so the
answer key sits in the envelope for exactly the probe where it is most damaging.

**D2 — the headline is reported on the wrong probe label.** The P5 F009 headline was labelled `PB-4-earliest-anomaly`,
but the recovery-relevant probe defined by the contract is `PB-6-candidate-windows`. R2's evidence-bytes are strictly
and materially smaller than R0's on both probes, so the result holds — but the reported number must be the PB-6 delta,
since PB-6 is the probe P6's model uses to locate a recovery coordinate. This is a labelling correction, not a re-run.

## 3. Scope

### In scope

- **Article XVII** added to the constitution: the subject-visible surface must exclude the reference answer, enforced
  mechanically.
- **ADR-P5.1-1** recording D1 (answer key in subject view) and D2 (headline probe relabel) with the contract-§4/§5
  evidence; **ADR-P5.1-2** the `model_view`/`reference` split; **ADR-P5.1-3** the guard mechanism.
- **`representation-interface.amendment-1.md`** (Article XV supersession): defines `model_view` =
  `{incident_id, representation, probe_id, params, content, telemetry}` as the only object P6 may pass to a model, and
  `reference` = `{answer}` as a separate object used solely by parity/telemetry tests. The original
  `representation-interface.md` stays byte-identical.
- `bin/lab-repr-modelview <incident> <representation> <probe> [params-json]` — emits only the `model_view` object.
- `bin/lab-repr-reference <incident> <representation> <probe> [params-json]` (or a `--reference` mode) — emits the
  `reference` object (`answer`) for the parity/telemetry tests, separate from the model view.
- `bin/lab-modelview-guard` — inspects a `model_view` JSON and refuses (exit non-zero, naming the first violation) any
  that contains an `answer`/`reference` key, a coordinate-answer field (`candidates`, `last_safe_lsn_int` at the answer
  level, `first_lsn_int`/`last_lsn_int` as answer fields), or a provenance token.
- Re-scoping the P5 parity test to the `model_view` surface (only `content` + `telemetry` differ across R0/R1/R2).
- Relabelling the F009 headline to **PB-6** (recovery probe); confirming R2 `evidence_bytes` strictly and materially <
  R0 on PB-6; the reported number is the PB-6 delta.
- Confirming the R0/R1/R2 representation artefacts are byte-identical to their P5 close (P5.1 changes the interface
  surface, not the representations).
- `bin/lab-verify-p5.1` gate; a re-derived `bin/lab-verify-p5` that reaches honest green under the relabel and the
  model-view surface; an acceptance memo recording "P5 accepted only after P5.1".

### Out of scope

- Any change to a frozen contract file (mutate none; supersede `representation-interface` by amendment only).
- Any new field on any frozen contract.
- Rebuilding or re-fitting the R0/R1/R2 representation artefacts, or the graph/summaries (they are sound).
- Re-running the SC-01 headline to change its numbers (only the reported probe label changes).
- Any P6 model invocation, retrieval logic, or Arm B scoring.
- Reading `principal` in any path.
- Making any criterion pass by weakening what it checks.

## 4. Functional requirements

- **FR-1 Subject-view principle.** The constitution gains Article XVII: where an experiment measures whether a subject
  can derive an answer from evidence, the bytes presented to that subject MUST NOT contain the reference answer, the
  ground-truth coordinate, or any pre-computed result the experiment tests the subject's ability to produce. The
  subject-visible surface is defined explicitly and separately from the reference answer, and the separation is
  mechanically enforced.
- **FR-2 The split, by amendment.** `representation-interface.amendment-1.md` defines `model_view` =
  `{incident_id, representation, probe_id, params, content, telemetry}` (the only object P6 may pass to a model) and
  `reference` = `{answer}` (parity/telemetry only). The original contract file stays byte-identical (Article XV).
- **FR-3 Model-view emitter.** `bin/lab-repr-modelview` emits only the `model_view` object for any
  (incident, representation, probe, params). It has exactly the six model_view keys and no `answer`/`reference` key.
- **FR-4 Reference emitter.** `bin/lab-repr-reference` emits the `reference` object (`answer`) separately, for the
  parity/telemetry tests. It is never part of a `model_view`.
- **FR-5 Guard.** `bin/lab-modelview-guard <model_view.json>` refuses (exit non-zero, first violation named) any model
  view carrying an `answer`/`reference` key, a coordinate-answer field, or a provenance token; passes a clean model
  view. It is the mechanical enforcement Article XVII requires.
- **FR-6 Parity re-scoped.** The P5 parity property (only `content`+`telemetry` differ across R0/R1/R2) is asserted on
  the `model_view` surface: for each probe, the model_view envelope is structurally identical across the three
  representations, differing only in `content` and `telemetry`.
- **FR-7 Headline relabel.** The F009 headline is reported on **PB-6** (recovery probe). R2 `evidence_bytes` strictly
  and materially < R0 on PB-6, re-derived from committed artefacts. `bin/lab-verify-p5` re-derived so its headline
  criterion asserts on PB-6; the change is mechanism/label only and recorded in the old→new mapping (Article XV /
  AC-P5.1-13). R2/R1/R0 artefacts byte-identical to P5 close.
- **FR-8 Gate and memo.** `bin/lab-verify-p5.1` runs every P5.1 criterion with per-tier totals; re-verifies all prior
  contract hashes unchanged; runs `bin/lab-gate-readonly-check` against itself and `bin/lab-verify-p5`; and the
  acceptance memo records the remediation and "P5 accepted only after P5.1".

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P5.1-01 | M | `constitution.md` contains a well-formed Article XVII (subject-visible surface excludes the reference answer); article count is 17 |
| AC-P5.1-02 | M | ADR-P5.1-1 records D1 (answer key in subject view, with §4/§5 evidence) and D2 (headline probe relabel); ADR-P5.1-2 the model_view/reference split; ADR-P5.1-3 the guard mechanism |
| AC-P5.1-03 | M | `representation-interface.amendment-1.md` exists and defines `model_view` = exactly `{incident_id, representation, probe_id, params, content, telemetry}` and `reference` = `{answer}`; the original `representation-interface.md` is byte-identical (F001 hash re-verifies) |
| AC-P5.1-04 | M | `bin/lab-repr-modelview <incident> <repr> <probe> [params]` emits an object with exactly the six model_view keys and no `answer`/`reference` key, for every representation and probe |
| AC-P5.1-05 | M | `bin/lab-repr-reference` emits the `reference` object (`answer`) separately; the `answer` is available to parity/telemetry tests and is not part of any model_view |
| AC-P5.1-06 | M | `bin/lab-modelview-guard` passes a clean model_view and exits non-zero naming the first violation on one carrying an `answer` key, a coordinate-answer field (`candidates`/answer-level `last_safe_lsn_int`), or a provenance token |
| AC-P5.1-07 | M | NEGATIVE: injecting `answer` into a model_view (and, separately, a `principal` token) each make `bin/lab-modelview-guard` exit non-zero; removing them passes again |
| AC-P5.1-08 | M | Every `bin/lab-repr-modelview` output, across R0/R1/R2 × all six probes, passes `bin/lab-modelview-guard` |
| AC-P5.1-09 | M | Parity on the model_view surface: for each probe the model_view envelope is structurally identical across R0/R1/R2, differing only in `content` and `telemetry` (re-derived, not asserted) |
| AC-P5.1-10 | M | The F009 headline is reported on PB-6; R2 `evidence_bytes` is strictly and materially less than R0 on PB-6, re-derived from committed artefacts |
| AC-P5.1-11 | M | R0/R1/R2 representation artefacts are byte-identical to their P5 close (F002/F003/F004 hashes re-verify); no representation rebuilt |
| AC-P5.1-12 | M | Provenance-blindness preserved on the model_view surface: a strip test finds no `principal`/`usename`/`session_user`/UID in any model_view, content, or summary |
| AC-P5.1-13 | M | No frozen contract file mutated (all prior hashes re-verify, incl. `representation-interface.md`); no criterion weakened (old→new mapping recorded; the relabel is mechanism/label only, PB-6 delta still asserts R2<R0) |
| AC-P5.1-14 | M | `bin/lab-verify-p5` re-derived: headline criterion asserts on PB-6; gate reaches honest green with per-tier totals, exit 0; passes `bin/lab-gate-readonly-check` (evidence byte-identical) |
| AC-P5.1-15 | M | `bin/lab-verify-p5.1` reports every criterion PASS with per-tier totals printed separately, exit 0; passes `bin/lab-gate-readonly-check` |
| AC-P5.1-16 | A | `docs/p5-acceptance-memo.md` records the remediated confound and `p5_accepted_only_after: "P5.1"` on machine-readable fields |

All criteria are tier M except AC-P5.1-16, which attests a one-time documentation event and still asserts on JSON
fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p5.1` green with per-tier totals; Article XVII in force; `model_view` and `reference` split by
amendment with the original contract byte-identical; `bin/lab-repr-modelview` emits only the subject-visible surface
and every emission passes `bin/lab-modelview-guard`; the guard demonstrably refuses an injected answer and an injected
provenance token; parity holds on the model_view surface; the headline reports the PB-6 delta with R2<R0; the R0/R1/R2
artefacts byte-identical to their P5 close; all frozen contract files unchanged; no criterion weakened; acceptance memo
updated.
