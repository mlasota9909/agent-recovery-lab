# Tasks — P5.1: Model-View Separation

One task per invocation, in order, dry run first. Do not batch. Each task's real instructions are in its work
instruction file under `work-instructions/WI-<id>.md`.

| Order | Task | Title | Depends on | Blocks | Serves |
| --- | --- | --- | --- | --- | --- |
| 1 | G001 | Article XVII; ADR-P5.1-1/2/3 | — | G002, G003, G004 | FR-1, AC-P5.1-01, AC-P5.1-02 |
| 2 | G002 | `representation-interface.amendment-1.md`; `bin/lab-repr-modelview`; `bin/lab-repr-reference`; `bin/lab-modelview-guard` | G001 | G003, G004 | FR-2..FR-5, AC-P5.1-03..08 |
| 3 | G003 | parity re-scoped to model_view; F009 relabel to PB-6; re-derive `bin/lab-verify-p5`; artefacts byte-identical | G002 | G004 | FR-6, FR-7, AC-P5.1-09..12, AC-P5.1-14 |
| 4 | G004 | `bin/lab-verify-p5.1` gate; contract-hash re-verify; old→new mapping; memo | G003 | — | FR-8, AC-P5.1-13, AC-P5.1-15, AC-P5.1-16 |

`G004` is the gate and runs last. The task to read line by line is **G002**: it decides what P6 is allowed to hand the
model.
