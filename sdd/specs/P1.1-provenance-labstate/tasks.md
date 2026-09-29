# Tasks — P1.1: Provenance & Lab-State Remediation

Ordered and dependency-aware. Each task `Xnnn` has a work instruction at `work-instructions/WI-Xnnn.md` giving the
tier below this list: exact commands, artefacts, tier-labelled acceptance tests, a mandatory negative test, the review
bundle and an operator checklist.

**Run one task per agent invocation. Do not batch.**

## Phase A — Principle, then the provenance fix

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| X001 | Append Article XIV (provenance of record); correct the false handoff note | — | `constitution.md`, handoff note | AC-P1.1-01, AC-P1.1-02 |
| X002 | Fix `harness_commit`: HEAD at production time + dirty-tree refusal | X001 | `bin/lab-evaluate-arm` | FR-1, AC-P1.1-03..06 |

> X001 changes behaviour-governing text before any code, so the fix is made against a stated principle rather than a
> one-off. X002 is the task to read line by line: it changes what every future results row records.

## Phase B — Contain the bad rows

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| X003 | Quarantine P1 stub rows under `results/fixtures/` with a manifest | X002 | `results/fixtures/`, `bin/lab-results` read path | FR-2, AC-P1.1-07, AC-P1.1-08 |

## Phase C — Make the lab safe to advance, and the numbers honest

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| X004 | `bin/lab-ready` P2-readiness gate + tested recovery runbook | X003 | `bin/lab-ready`, `docs/runbook-slot-recovery.md` | FR-3, FR-4, AC-P1.1-09..11 |
| X005 | Planned-vs-completed disambiguation across memo/plan/throughput | X003 | memo, `docs/sample-size-plan.md` | FR-5, AC-P1.1-12, AC-P1.1-13 |

## Phase D — Gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| X006 | `bin/lab-verify-p1.1` tiered gate; contract hash re-verify; memo update | X001..X005 | `bin/lab-verify-p1.1`, memo | FR-6, AC-P1.1-14..16 |

## Dependency graph

```
X001 -- X002 -- X003 --+-- X004 --+-- X006
                       |          |
                       +-- X005 --+
```

X004 and X005 may run in either order once X003 is complete. X006 runs last.

## Anti-goals for this tranche

Do not, in P1.1: modify any frozen contract; add a field to the results row; build analytics, ranking,
representations, retrieval or any model call; implement real restore; touch SC-02/03/04. Do not repair the
invalidated slot by creating a new slot. If a task appears to require any of these, it has been misread — record it in
`observations.md` and continue within scope.
