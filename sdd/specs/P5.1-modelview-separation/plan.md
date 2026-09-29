# Plan — P5.1: Model-View Separation

## Architecture decisions (locked)

### ADR-P5.1-1 — the confound is recorded as a defect, not retro-justified

`bin/lab-verify-p5` closed green and the P5 work is sound: R0/R1/R2 are deterministically built, provenance-blind, and
R2's evidence-bytes are a small fraction of R0's. But the review found a latent confound in the frozen interface:

- **D1 — answer key in the subject-visible envelope.** The response envelope (`representation-interface` §4) contains
  both `content` (evidence the model reads) and `answer` (the pre-computed result). For `PB-6-candidate-windows`,
  `answer` is the recovery coordinate (`candidates:[{window_index, last_safe_lsn_int, anomaly_score}]`), identical
  across R0/R1/R2 (hard rule R3). P6 scores the model's coordinate via the P4 restore+validate path, so `answer` has no
  scoring role — but if P6 passes the envelope to the model, the model reads the coordinate for free and the ablation
  measures nothing. §5 even designates PB-6 as the probe the model uses to locate a coordinate, so the answer key sits
  in the envelope for the most damaging probe.
- **D2 — headline probe mislabel.** The F009 headline was labelled `PB-4`; the recovery probe is `PB-6`. R2 <br> R0 on
  both, so the result holds, but the reported number must be PB-6's.

This ADR names D1 a defect of the same class as the P0.1 test hatch (Article XII), the P3 provenance-in-detection
(Article II), and the P1 `harness_commit` (Article XIV): an unenforced separation between what a subject may see and
the answer key. It does not pretend the co-location was correct.

### ADR-P5.1-2 — split `model_view` from `reference` by supersession, do not delete the answer

The `answer` is *useful* — it is the parity reference that confirms all three representations are asked to support the
same result, and it feeds telemetry. The fix is not to delete it but to move it out of the subject-visible surface. By
Article XV the frozen `representation-interface.md` is not mutated; `representation-interface.amendment-1.md` defines:

- `model_view` = `{incident_id, representation, probe_id, params, content, telemetry}` — the **only** object P6 may
  pass to a model. It carries no `answer`.
- `reference` = `{answer}` — a separate object, used solely by the P5 parity and telemetry tests, never handed to a
  subject.

`bin/lab-repr-modelview` emits the first; `bin/lab-repr-reference` emits the second. `bin/lab-repr-query` (F005) is left
byte-identical (it is referenced by frozen F005 review artefacts); the new emitters are thin wrappers over it that
project out the respective surface, so no representation logic is re-implemented.

### ADR-P5.1-3 — the split is enforced by a guard, not by documentation

Mirroring the read-only harness (ADR-P3.1-3) and the provenance triad (P3), `bin/lab-modelview-guard <model_view.json>`
mechanically inspects the subject-visible bytes and refuses any that carry: an `answer` or `reference` key; a
coordinate-answer field surfaced as structured data (`candidates`, an answer-level `last_safe_lsn_int`,
`first_lsn_int`/`last_lsn_int` presented as answer fields rather than inside `content`); or a provenance token
(`principal`/`usename`/`session_user`/UID). `content` may legitimately contain LSN digits — that is the evidence the
model reads to *derive* the coordinate; the guard forbids the *structured pre-computed answer*, not the appearance of a
number in the evidence text. This makes Article XVII a mechanically re-derived property (tier M) and closes the class:
any future emitter that regresses into including the answer is caught.

### ADR-P5.1-4 — corrected, never weakened

Every P5 criterion still exists and still asserts its original property. Where a criterion's *mechanism or label*
changes — the parity check moving from the full response envelope to the `model_view` surface (still: only
`content`+`telemetry` differ), and the headline criterion moving from `PB-4` to `PB-6` (still: R2 evidence-bytes
strictly and materially < R0) — the change is mechanism/label only; the property asserted is preserved or strengthened.
A machine-readable old→new mapping is recorded (AC-P5.1-13). Making a gate green by weakening it is prohibited and is
the one way this tranche can fail its own review.

## Constitutional change

Article XVII is appended by G001:

> **Article XVII — Subject-visible surface excludes the reference answer.** Where an experiment measures whether a
> subject (a model, a ranker, a human) can *derive* an answer from evidence, the bytes presented to that subject MUST
> NOT contain the reference answer, the ground-truth coordinate, or any pre-computed result the experiment is testing
> the subject's ability to produce. The subject-visible surface (the "model view") is defined explicitly and separately
> from the reference answer used to score or to check parity. This separation MUST be mechanically enforced (a guard
> that inspects the subject-visible bytes and refuses any that carry the answer), not merely documented. Presenting the
> answer alongside the evidence a subject reads is a defect of the same class as a silent test hatch (Article XII) and
> a provenance leak (Article II).

This sits alongside Article XII (no test hatches), XIII (verification tiers), XIV (provenance of record), XV (amendment
of frozen artefacts) and XVI (read-only gates) as the sixth lesson learned from review, each closing a class rather
than an instance.

## Task breakdown

| Task | Owns | Closes |
| --- | --- | --- |
| G001 | Article XVII; ADR-P5.1-1/2/3 | governance + design of record |
| G002 | `representation-interface.amendment-1.md`; `bin/lab-repr-modelview`; `bin/lab-repr-reference`; `bin/lab-modelview-guard` + negative test | D1 |
| G003 | parity re-scoped to model_view; F009 headline relabelled to PB-6; `bin/lab-verify-p5` re-derived to honest green; R0/R1/R2 artefacts proven byte-identical | D1, D2 |
| G004 | `bin/lab-verify-p5.1` gate; contract-hash re-verify; old→new criterion mapping; memo update | all |

## Sequencing

G001 first (principle and recorded design before any change). G002 depends on G001 (it builds the split and the guard
that Article XVII requires). G003 depends on G002 (it re-scopes parity to the model_view surface the emitter produces,
and relabels the headline). G004 is the gate and runs last.

```
G001 -- G002 -- G003 -- G004
```

## Risks

- **The guard forbids LSN digits in `content` and breaks R0.** Mitigated by ADR-P5.1-3: the guard forbids the
  *structured answer* (an `answer`/`reference` key, `candidates`, answer-level coordinate fields), never the appearance
  of a number inside the `content` string. A negative test confirms a clean R0 model_view (whose content is raw LSN
  lines) passes.
- **A representation is accidentally rebuilt while "fixing" the interface.** Mitigated by AC-P5.1-11 requiring
  F002/F003/F004 artefact hashes to re-verify byte-identical; the new emitters are projections over the existing
  `bin/lab-repr-query`, not re-implementations.
- **The relabel is used to quietly weaken the headline.** Mitigated by AC-P5.1-13 (old→new mapping; PB-6 delta must
  still assert R2 strictly and materially < R0) and operator review.
- **A model_view leaks provenance through `content`.** Article II still binds; AC-P5.1-12 strips provenance and asserts
  none appears in any model_view, content or summary.
- **The frozen `representation-interface.md` is edited instead of superseded.** Mitigated by AC-P5.1-03/13 requiring
  the original file to stay byte-identical (F001 hash) and the change to live in `amendment-1`.
