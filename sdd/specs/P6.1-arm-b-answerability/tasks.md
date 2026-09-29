# Tasks — P6.1: Arm B Answerability

One task per invocation, in order, dry run first. Do not batch. Each task's real instructions are in its work
instruction file under `work-instructions/WI-<id>.md`.

| Order | Task | Title | Depends on | Blocks | Serves |
| --- | --- | --- | --- | --- | --- |
| 1 | J001 | Article XVIII; per-completion refusal diagnosis; ADR-P6.1-1..4 | — | J002, J003, J004, J005 | FR-1, FR-2, AC-P6.1-01..03 |
| 2 | J002 | `model-runtime.amendment-1.md`; rewritten containment check | J001 | J004, J005 | FR-3, FR-4, AC-P6.1-04..06 |
| 3 | J003 | `arm-b-protocol.amendment-1.md`; rebuilt prompt + extractor; guard/refusal/parity tests | J001 | J004, J005 | FR-5, FR-6, FR-8, AC-P6.1-07..12, AC-P6.1-15 |
| 4 | J004 | SC-01 Arm B re-run R0/R1/R2 × K; honest headline; prior null quarantined | J002, J003 | J005 | FR-7, FR-8, AC-P6.1-13, AC-P6.1-14, AC-P6.1-16 |
| 5 | J005 | `bin/lab-verify-p6.1` gate; re-derive `-p6`; contract-hash re-verify; mapping; memo | J004 | — | FR-9, AC-P6.1-17, AC-P6.1-18, AC-P6.1-19 |

`J005` is the gate and runs last. The task to read line by line is **J001**: its diagnosis decides whether J003 fixes
an instrument artefact or whether a surviving refusal is a genuine finding about the model.
