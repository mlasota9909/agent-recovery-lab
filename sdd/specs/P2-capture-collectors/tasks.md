# Tasks — P2: Capture Collectors & the Append-Only Ledger

Ordered and dependency-aware. Each task `Cnnn` has a work instruction at `work-instructions/WI-Cnnn.md` giving the
tier below this list: exact commands, artefacts, tier-labelled acceptance tests, a mandatory negative test, the review
bundle and an operator checklist.

**Run one task per agent invocation. Do not batch.**

Two entry conditions apply to every task: `bin/lab-ready` must exit 0 before capture work, and the git working tree
must be clean before producing any provenance-bearing artefact.

## Phase A — Contract and entry gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| C001 | Freeze `capture-completeness.md`; record `lab-ready` exit 0 as the entry gate | — | contract, entry-gate record | FR-1, AC-P2-01 |

> C001 freezes the definition of a complete ledger **before** any collector is wired, so every downstream task builds
> against a stated contract. Read the contract line by line — it is what P3 will hold you to.

## Phase B — Orchestration and the streams

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| C002 | `bin/lab-capture {start|stop|status}` — collector orchestration + session manifest | C001 | `bin/lab-capture` | FR-2, AC-P2-02..04 |
| C003 | Snapshot loop LSN anchoring → `snapshots.json` (every snapshot carries an LSN) | C002 | snapshot loop | FR-3, AC-P2-05 |
| C004 | Filesystem capture: `fs_diff.tsv` walker + `fs_hashes.tsv` tree hasher | C002 | `bin/lab-fs-capture` | FR-4, AC-P2-06, AC-P2-07 |
| C005 | DB stream integrity: before-images on U/D + DDL in one LSN-ordered stream | C002 | integrity verifier | FR-5, AC-P2-08, AC-P2-09 |

## Phase C — Query layer and workload

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| C006 | `bin/lab-query` — no-ETL DuckDB view layer over the ledger | C003, C004, C005 | `bin/lab-query` | FR-6, AC-P2-10 |
| C007 | `bin/lab-capture-workload` — deterministic 500-op mixed workload, provenance-labelled | C002 | `bin/lab-capture-workload` | FR-7 input, AC-P2-11 |

## Phase D — The keystone: exactly-once reconciliation

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| C008 | `bin/lab-ledger-account` — exactly-once coverage + all completeness assertions | C003, C004, C005, C006, C007 | `bin/lab-ledger-account` | FR-7, AC-P2-12..14 |

> C008 is the tranche's reason for existing. Its 500-operation exactly-once proof is what makes every downstream
> number trustworthy. The operator will hand-trace sampled operations to their ledger records.

## Phase E — Teardown and gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| C009 | Capture teardown + slot hygiene (lag → 0, slot dropped, ledger retained) | C002 | teardown path | FR-8, AC-P2-15 |
| C010 | `bin/lab-verify-p2` tiered gate; contract hash re-verify; P2 handoff | C001..C009 | `bin/lab-verify-p2`, handoff | FR-9, AC-P2-16..18 |

## Dependency graph

```
C001 -- C002 --+-- C003 --+
               |          |
               +-- C004 --+-- C006 --+
               |          |          |
               +-- C005 --+          +-- C008 -- C010
               |                     |
               +-- C007 -------------+
               |
               +-- C009 ------------------------ C010
```

C003, C004, C005 and C007 may run in any order once C002 is complete. C006 needs the three streams (C003–C005). C008
needs C003–C007. C009 needs only C002. C010 runs last.

## Anti-goals for this tranche

Do not, in P2: modify any frozen contract or add a field to the results row or ledger-integrity contract; build any
analytics, ranking, representation, retrieval interface or model call (that is P3+); implement real point-in-time
restore or restored-state validation (P4); implement SC-01..04 damage logic (P2 uses a generic mixed workload only);
read the provenance label in any detection/ranking/query-default path; build a WAL parser, a `fanotify`/`inotify`
daemon, `zfs send`/clone plumbing, or any bespoke server/broker/queue. If a task appears to require any of these, it
has been misread — record it in `observations.md` and continue within scope.
