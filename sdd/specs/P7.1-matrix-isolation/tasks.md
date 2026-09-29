# Tasks — P7.1: Matrix Isolation

One task per invocation, in order, dry run first. Do not batch. Each task's real instructions are in its work
instruction file under `work-instructions/WI-<id>.md`.

| Order | Task | Title | Depends on | Blocks | Serves |
| --- | --- | --- | --- | --- | --- |
| 1 | L001 | Article XIX; D1 root cause; FULL/FALLBACK decision; ADR-P7.1-1..5 | — | L002, L003, L004, L005, L006 | FR-1, FR-2, AC-P7.1-01..03 |
| 2 | L002 | `incident-isolation.md`; per-incident datasets + scoped reset; sibling-safety negative test | L001 (FULL) | L004, L006 | FR-3, FR-4, AC-P7.1-04..07 |
| 3 | L003 | SC-02 `oracle-manifest.json` + P4 wiring; SC-03/04 set-validation verdict | L001 (FULL) | L004, L006 | FR-6, AC-P7.1-08, AC-P7.1-09 |
| 4 | L004 | live re-run SC-02/03/04 under isolation; supersede prior cells; completeness+validity partition | L002, L003 | L005, L006 | FR-5, FR-7, FR-8, AC-P7.1-10..13, AC-P7.1-19 |
| 5 | L005 | disaggregated honest headline; SC-01 sole validated headline | L004 (or L001 FALLBACK) | L006 | FR-9, AC-P7.1-14, AC-P7.1-15, AC-P7.1-16 |
| 6 | L006 | `bin/lab-verify-p7.1` gate; re-derive `-p7`; contract-hash re-verify; mapping; memo | L005 | — | FR-10, AC-P7.1-17, AC-P7.1-18, AC-P7.1-20, AC-P7.1-21 |

`L006` is the gate and runs last. The task to read line by line is **L002**: the sibling-safety negative test is what
proves the root cause is actually fixed. **L002/L003/L004 execute only if L001 recorded decision FULL**; under
FALLBACK they are marked `not_executed` with the decision reason and L005 delivers the documentation-only corrections.
