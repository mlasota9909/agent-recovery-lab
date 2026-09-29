# Tasks — P1: Ground Truth, Results Contract and Run Harness

Ordered and dependency-aware. Each task `Wnnn` has a work instruction at `work-instructions/WI-Wnnn.md` giving the
tier below this list: exact commands, artefacts, tier-labelled acceptance tests, a mandatory negative test, the review
bundle and an operator checklist.

**Run one task per agent invocation.** `[P]` marks tasks that may run in parallel with the preceding block.

## Phase A — Correct the record, then freeze the contracts

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| W001 | Verify P0/P0.1 preconditions; correct the P0.1 handoff's inverted P1 anti-goals; open the tranche | — | `docs/P0.1-architecture-handoff.md` correction, precondition report | Gate |
| W002 | Author and freeze `contracts/results-row.md` and `contracts/ledger-integrity.md`; hash-record them | W001 | both new contracts | FR-1, FR-2, ADR-P1-1 |

> W001 is a cheap stop-gate. It confirms `lab-verify` is still 18/18, confirms the three P0 contracts are unchanged by
> hash, and fixes the handoff sentence that tells a future agent P1 must not build the oracle or results schema —
> which is exactly backwards and would derail the tranche.
>
> W002 writes no code. It is reviewed line by line because ADR-P1-1 makes it the most expensive task to get wrong.

## Phase B — Instruments that guard the evidence

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| W003 | Results writer and validator; append-only, immutable, no coercion | W002 | `bin/lab-results` | FR-1.7, FR-1.8, AC-P1-01..03 |
| W004 | Ledger integrity CLI and the reset catch-up barrier | W002 | `bin/lab-ledger-verify`, `bin/lab-barrier` | FR-2, ADR-P1-4, ADR-P1-5, AC-P1-04..07 |

## Phase C — Generate a real incident

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| W005 | SC-01 legitimate workload as `lab_app`, with commit manifest | W004 | `bin/lab-workload` | FR-4, AC-P1-08, AC-P1-09 |
| W006 | SC-01 injector as `lab_agent`; the scripted DELETE, recorded verbatim | W005 | `bin/lab-inject` | FR-3.1 inputs, AC-P1-09 |

## Phase D — The oracle

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| W007 | Ground-truth oracle: optimum coordinate plus scoring manifest; deterministic and auditable | W006 | `bin/lab-oracle` | FR-3, AC-P1-10..14 |

> W007 is the task every downstream number is scored against. Its acceptance includes an **independent cross-check**:
> the optimum must be re-derived from the workload manifest by a path that does not reuse the oracle's own code.

## Phase E — The two-phase harness and the null run

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| W008 | `lab-generate-incident`, `lab-evaluate-arm`, analysis stub, restore stub; the null run | W007, W003 | four CLIs | FR-5, FR-6, AC-P1-15..20 |

> AC-P1-17 lives here and is the single most important assertion in the tranche: a second arm evaluated against the
> same `incident_id`, without regenerating, must append a row whose ground-truth coordinate is **byte-identical**.
> That is the empirical proof that ADR-P1-2's fixed-incident property holds and the ablation is therefore valid.

## Phase F — Measure, then plan the matrix

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| W009 | Re-measure cycle times post-reset-guard; derive the stratified sample-size plan | W008 | `bin/lab-throughput`, `docs/sample-size-plan.md` | FR-7, ADR-P1-6, AC-P1-21, AC-P1-22 |

## Phase G — Gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| W010 | P1 acceptance runner, tiered; idempotence sweep; contract hash freeze; acceptance memo | W003..W009 | `bin/lab-verify-p1`, memo | AC-P1-01..24 |

## Dependency graph

```
W001 -- W002 --+-- W003 --+
               |          |
               +-- W004 --+-- W005 -- W006 -- W007 -- W008 -- W009 -- W010
                                                        |              |
                                                        +--------------+
```

W003 and W004 may run in either order once W002 is frozen. Everything from W005 onward is strictly sequential because
each stage consumes the artefact the previous stage produces.

## Anti-goals for this tranche

Do not build, in P1: derived analytics (change-burst density, churn, anomaly scoring), candidate generation, the
deterministic ranking function or its weights, the naive comparator's calibration, representations R0/R1/R2, any
retrieval interface, any language model invocation, real point-in-time restore into a sandbox, row/byte/schema
validation of restored state, or the damage logic for SC-02, SC-03 and SC-04.

P1 ships **stubs** for analysis and restore that implement the interfaces their real successors will implement, so
that P3 and P4 are substitutions rather than rewrites. A stub that does real work is a scope violation; a stub that
fabricates a successful verdict is an Article VIII violation.

If a task appears to require one of the above, it has been misread. Record the apparent need in `observations.md` and
continue within scope.
