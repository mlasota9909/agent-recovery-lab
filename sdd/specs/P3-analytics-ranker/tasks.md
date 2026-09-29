# Tasks — P3: Derived Analytics & the Arm A Deterministic Ranker

Ordered and dependency-aware. Each task `Dnnn` has a work instruction at `work-instructions/WI-Dnnn.md` giving the
tier below this list: exact commands, artefacts, tier-labelled acceptance tests, a mandatory negative test, the review
bundle and an operator checklist.

**Run one task per agent invocation. Do not batch.**

Two entry conditions apply to every task: `bin/lab-ready` must exit 0 **and** the target incident must have passed
`bin/lab-ledger-account` before any analytics; and the git working tree must be clean before producing any
provenance-bearing or results-bearing artefact.

## Phase A — Contracts and entry gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| D001 | Freeze `candidate-coordinate.md` + `arm-coordinate.md`; record `lab-ready` 0 and reconciliation as the entry gate | — | the two contracts, entry-gate record | FR-1, AC-P3-01 |

> D001 freezes what analytics emit and what an arm returns **before** any producer is written, so every downstream
> task builds against a stated shape. Read both contracts line by line — the provenance and no-peek rules are the
> load-bearing part.

## Phase B — The SC-01 incident

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| D002 | SC-01 injector + concurrent repeated-key workload + oracle params → one reconciled SC-01 incident | D001 | `bin/lab-inject-sc01`, SC-01 workload profile | FR-2, AC-P3-02, AC-P3-03 |

> D002 is bounded to SC-01 only (ADR-P3-6). It reuses the P1 `generate-incident` harness and P2 capture; it adds only
> the injector, the workload profile and the oracle parameters. SC-02..04 are deferred.

## Phase C — Derived analytics

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| D003 | `bin/lab-analytics` — burst density, per-relation/path churn, deletion spikes, DDL flag (provenance-blind) | D002 | `bin/lab-analytics` | FR-3, AC-P3-04, AC-P3-05 |
| D004 | mean+3σ anomaly scoring against the declared quiescent baseline window | D003 | anomaly scorer | FR-4, AC-P3-06, AC-P3-07 |

## Phase D — Candidates and the arms

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| D005 | `bin/lab-candidates` — candidate generation to `candidate-coordinate.md` | D003, D004 | `bin/lab-candidates` | FR-5, AC-P3-08, AC-P3-09 |
| D006 | `bin/lab-rank` — Arm A deterministic ranker (declared weights + tie-breaks) | D005 | `bin/lab-rank` | FR-6, AC-P3-10, AC-P3-11 |
| D007 | `bin/lab-naive` — naive comparator (declared, fixed time error) | D005 | `bin/lab-naive` | FR-7, AC-P3-12 |

## Phase E — Wiring, headline, gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| D008 | Wire Arm A + naive into `evaluate-arm` so both errors auto-land in the results row | D006, D007 | evaluate-arm wiring | FR-8, AC-P3-13 |
| D009 | Headline SC-01 (Arm A beats naive) + provenance-blindness + no-peek negatives | D008 | the tranche's proof | FR-9, AC-P3-14, AC-P3-15, AC-P3-16 |
| D010 | `bin/lab-verify-p3` tiered gate; all prior contract hashes re-verified; P3 handoff | D001..D009 | `bin/lab-verify-p3`, handoff | FR-10, AC-P3-17..19 |

> D009 is the tranche's reason for existing. The operator will read both arms' recovery-point errors straight from the
> results row, confirm Arm A won honestly against a declared naive-error parameter, and personally re-run the
> strip-provenance test to confirm Arm A's coordinate does not move.

## Dependency graph

```
D001 -- D002 --+-- D003 -- D004 -- D005 --+-- D006 --+
                                          |          +-- D008 -- D009 -- D010
                                          +-- D007 --+
```

D006 and D007 may run in either order once D005 is complete. D008 needs both. D009 needs D008. D010 runs last.

## Anti-goals for this tranche

Do not, in P3: modify any frozen contract or add a field to the results row or ledger-integrity contract; build any
representation R0/R1/R2 or the Arm B query interface (that is **P5**); invoke any model or build the Arm B harness
(that is **P6**); implement real point-in-time restore or restored-state validation (that is **P4**); build SC-02,
SC-03 or SC-04 injectors (later tranches — P3 realizes only SC-01); read the `principal` provenance field, the
injection log, or the oracle optimum in any detection/ranking path; rig the naive comparator's time error to
disadvantage it. If a task appears to require any of these, it has been misread — record it in `observations.md` and
continue within scope.
