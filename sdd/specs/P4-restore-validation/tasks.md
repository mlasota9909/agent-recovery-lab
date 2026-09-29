# Tasks — P4: Restore, Validation & the Promotion Gate

Ordered and dependency-aware. Each task `Ennn` has a work instruction at `work-instructions/WI-Ennn.md` giving the
tier below this list: exact commands, artefacts, tier-labelled acceptance tests, a mandatory negative test, the review
bundle and an operator checklist.

**Run one task per agent invocation. Do not batch.**

Three entry conditions apply to every task: `bin/lab-ready` must exit 0 **and** the target SC-01 incident must have
passed `bin/lab-ledger-account`; any coordinate restored must have `arm_no_peek_ok` true (or be the labelled
`ground_truth` coordinate); and the git working tree must be clean before producing any provenance-bearing or
results-bearing artefact. Every restore leaves the victim and evidence store byte-identical.

## Phase A — Contracts and entry gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| E001 | Freeze `restore-report.md` + `promotion-gate.md`; record `lab-ready` 0, SC-01 reconciliation, and coordinate no-peek as the entry gate | — | the two contracts, entry-gate record | FR-1, AC-P4-01 |

> E001 freezes what a restore reports and where the validate/promote boundary sits **before** any restore code is
> written. Read both contracts line by line — the safety block (restore-report R6) and the promotion gates
> (promotion-gate R2/R3/R4) are the load-bearing parts.

## Phase B — The two restore layers

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| E002 | `bin/lab-restore-db` — PITR of the base backup + WAL to a target LSN into a new sandbox cluster | E001 | `bin/lab-restore-db` | FR-2, AC-P4-02, AC-P4-03 |
| E003 | `bin/lab-restore-fs` — `zfs clone` of the resolved snapshot into a sandbox mountpoint | E001 | `bin/lab-restore-fs` | FR-3, AC-P4-04 |

> E002 and E003 are the two halves of restore, each non-destructive to the victim by construction. They may be built
> in either order. Both must prove the victim is byte-identical before and after.

## Phase C — Orchestration and validation

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| E004 | `bin/lab-restore` — resolve one coordinate to (LSN, snapshot), restore both layers, record skew | E002, E003 | `bin/lab-restore` | FR-4, AC-P4-05 |
| E005 | `bin/lab-validate` — row/byte/schema comparison against the oracle manifest, classified mismatches | E004 | `bin/lab-validate` | FR-5, AC-P4-06, AC-P4-07, AC-P4-08 |
| E006 | `bin/lab-verdict` — the deterministic 4-level consistency verdict + assembled report | E005 | `bin/lab-verdict` | FR-6, AC-P4-09, AC-P4-10 |

## Phase D — Promotion, agreement, headline

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| E007 | `bin/lab-promote` — guarded promotion gate (clean verdict + explicit token; lab simulation only) | E006 | `bin/lab-promote` | FR-7, AC-P4-11, AC-P4-12 |
| E008 | oracle<->reality agreement (Arm A) + the victim+evidence-untouched safety property | E006, E007 | agreement + safety checks | FR-8, AC-P4-15, AC-P4-16 |
| E009 | loop-closing headline (true coordinate -> `correct`) + discrimination negatives | E008 | the tranche's proof | FR-9, AC-P4-13, AC-P4-14 |

> E009 is the tranche's reason for existing. The operator will feed the true ground-truth coordinate themselves and
> confirm the verdict is `correct` with zero mismatches, then confirm a post-damage coordinate does NOT validate clean.

## Phase E — Gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| E010 | `bin/lab-verify-p4` tiered + read-only gate; all prior hashes re-verified; regression; P4 handoff | E001..E009 | `bin/lab-verify-p4`, handoff | FR-10, AC-P4-17..19 |

## Dependency graph

```
E001 --+-- E002 --+
       +-- E003 --+-- E004 -- E005 -- E006 -- E007 -- E008 -- E009 -- E010
```

E002 and E003 may run in either order once E001 is complete. E004 needs both. E010 runs last.

## Anti-goals for this tranche

Do not, in P4: modify any frozen contract or add a field to the results row or ledger-integrity contract; restore into
or start recovery against the victim cluster, or `zfs rollback`/write the victim dataset (sandbox clusters and
`zfs clone` only); use the oracle manifest or injection log to choose or adjust a coordinate (manifest is for
validation scoring only); perform a real (non-simulated) promotion, or auto-promote on a clean verdict without an
explicit token; build any representation R0/R1/R2 or the Arm B query interface (that is **P5**); invoke any model or
build the Arm B harness (that is **P6**); build SC-02/03/04 injectors (later tranches); leave an orphaned sandbox
cluster or ZFS clone behind. If a task appears to require any of these, it has been misread — record it in
`observations.md` and continue within scope.
