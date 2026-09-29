# Tasks — P2.1: Reconciliation Soundness & Contract Amendment

Ordered and dependency-aware. Each task `Ynnn` has a work instruction at `work-instructions/WI-Ynnn.md` giving the
tier below this list: exact commands, artefacts, tier-labelled acceptance tests, a mandatory negative test, the review
bundle and an operator checklist.

**Run one task per agent invocation. Do not batch.**

## Phase A — Principle and the formal deviation record

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| Y001 | Append Article XV (amendment of frozen artefacts); write ADR-P2.1-1 recording the §4 deviation | — | `constitution.md`, ADR-P2.1-1 | FR-1, AC-P2.1-01, AC-P2.1-04 |

> Y001 establishes the amendment mechanism and the formal deviation record before any code changes, so the fix is made
> against a stated principle rather than as another one-off.

## Phase B — Restore the key at its root

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| Y002 | Recover `xid` from the transaction envelope + workload-side `txid_current()`; withdraw greedy fallback; freeze `capture-completeness.amendment-1.md` | Y001 | `bin/lab-consumer`, `bin/lab-capture-workload`, `bin/lab-ledger-account`, amendment-1 | FR-2, FR-3, FR-4, AC-P2.1-02..09, AC-P2.1-13 |

> Y002 is the task to read line by line: it decides the binding mapping key every incident ledger from P3 onward is
> certified against, and it either restores the frozen contract's original key or proves it cannot be restored.

## Phase C — Prove it sound in the real regime

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| Y003 | Repeated-key reconciliation soundness test + co-occurring gap+duplicate negative case | Y002 | `bin/lab-capture-workload` repeated-key profile, soundness test harness | FR-5, AC-P2.1-10, AC-P2.1-11, AC-P2.1-12 |

## Phase D — Gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| Y004 | `bin/lab-verify-p2.1` tiered gate; contract hash re-verify (incl. `capture-completeness.md`); memo update | Y001..Y003 | `bin/lab-verify-p2.1`, `docs/p2-acceptance-memo.md` | FR-6, AC-P2.1-14, AC-P2.1-15, AC-P2.1-16 |

## Dependency graph

```
Y001 -- Y002 -- Y003 -- Y004
```

## Anti-goals for this tranche

Do not, in P2.1: mutate `capture-completeness.md` or any other frozen contract in place; add a field to the results
row or ledger-integrity contract; build analytics, ranking, representations, retrieval or any model call; implement
real restore; touch SC-02/03/04; read `principal` in any mapping/detection path; or reach for the `op_uid` fallback
before exhausting and evidencing the transaction-envelope `xid` path. If a task appears to require any of these, it has
been misread — record it in `observations.md` and continue within scope.
