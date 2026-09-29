# Tasks — P0.1: P0 Remediation

Ordered and dependency-aware. Each task `Rnnn` has a work instruction at `work-instructions/WI-Rnnn.md` giving the
tier below this list: exact commands, files, acceptance tests, non-regression checks and review bundle.

**Run one task per agent invocation.** `[P]` marks tasks that may run in parallel with the preceding block.

## Phase A — Governance

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| R001 | Append constitution Articles XII and XIII; inventory the defects against them | — | constitution, defect inventory | FR-1..FR-6 framing |

> R001 is deliberately first and deliberately cheap. Every later task cites the articles it satisfies, so the
> articles must exist before the repairs land.

## Phase B — Boundary integrity (blocker)

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| R002 | Remove the receiver hatch; re-implement regression by host-side mutation; add the enumeration corpus | R001 | `bin/lab-wal-receive`, `bin/lab-isolation-test` | FR-1, FR-2, RC-1..RC-7 |

## Phase C — Evidence continuity (blocker)

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| R003 | Persistent supervised consumer; incident precondition; slot lag fails closed | R001 | `bin/lab-consumer`, unit file, `bin/lab-slot`, `bin/lab-incident` | FR-3, RC-8..RC-12 |

## Phase D — Verification integrity (blocker)

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| R004 | Tier every criterion; delete the prose matcher; re-implement AC-6 and AC-14 mechanically; add `--json` | R002, R003 | `bin/lab-verify` | FR-4, RC-13..RC-17 |

## Phase E — Untested guard and hygiene

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| R005 [P] | Prove the reset guard with a `noexec`-safe live process, both refusal and success | R001 | reset guard test | FR-5, RC-18 |
| R006 [P] | Remove the stale data directory; pin versions; generate the environment table | R001 | `etc/lab.env`, `docs/environment.md` | FR-6, RC-19, RC-20 |

## Phase F — Gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| R007 | Re-run the full suite; update the P0 checklist and limitations; write the acceptance memo | R002..R006 | acceptance memo | RC-21 |

## Dependency graph

```
R001 --+-- R002 --+
       |          +-- R004 -- R007
       +-- R003 --+           |
       |                      |
       +-- R005 [P] ----------+
       +-- R006 [P] ----------+
```

## Anti-goals for this tranche

Do not build, in P0.1: the ground-truth oracle, the results row schema, analytics, the ranking function,
representations, the model harness, restore verification, scenario damage logic, or the steady-state workload's
business content. Do not refactor `bin/lab-reset` beyond adding a test. Do not change any file under
`specs/P0-lab-substrate/contracts/`. Do not mechanically re-implement the seven non-load-bearing tier A criteria. If
a task seems to require one of these, it has been misread.

## A note on why this tranche is small

Six repairs and a gate. The temptation is to fold P1 work in while the lab is open. Resist it: the point of a
remediation tranche is that its diff is small enough to review line by line, which is exactly what the P0 review
showed is necessary.
