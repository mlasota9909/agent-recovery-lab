# Tasks — P0: Lab Substrate and Evidence Isolation

Ordered and dependency-aware. Each task `Tnnn` has a work instruction at `work-instructions/WI-Tnnn.md` giving the
tier below this list: exact commands, files, acceptance tests and review bundle.

**Run one task per agent invocation.** `[P]` marks tasks that may run in parallel with the preceding block.

## Phase A — Discovery (stop-gate)

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| T001 | Probe host and guest, verify device attachment, write `etc/lab.env` | — | `bin/lab-discover`, `etc/lab.env` | FR-1, AC-1, AC-2 |

> T001 is a stop-gate. If `DEV_LOCATION` resolves to `host`, the tranche halts pending a plan amendment.

## Phase B — Copy-on-write storage

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| T002 | Create `labpool` and the parent/children dataset layout | T001 | pool + datasets | FR-2.1, FR-2.2 |
| T003 | Relocate the PostgreSQL data directory onto `DS_PGDATA` | T002 | data dir move | FR-2.2 |
| T004 | Create `labdb`, scenario relations, `REPLICA IDENTITY FULL`, DDL audit trigger | T003 | schema + event trigger | FR-3.2, FR-3.3, AC-6, AC-7 |

## Phase C — Evidence path and recovery configuration

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| T005 | Create host evidence root, archive sink, incident scoping, results store | T001 | `bin/lab-incident`, host dirs | FR-3.5, FR-4.4, D-2, D-3 |
| T006 | Configure `wal_level=logical`, archiving, `wal2json` slot | T004, T005 | postgresql.conf, slot | FR-3.1, FR-3.4 |
| T007 | Bound slot retention; slot lag CLI; overwrite-refusal archive command | T006 | `bin/lab-slot` | FR-3.4, FR-3.6, AC-8, AC-10 |

## Phase D — Identity and isolation

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| T008 | Create `lab_app` / `lab_agent` OS users and DB roles; least privilege | T004 | identities, grants | FR-4.1, FR-4.2, FR-4.3, AC-11 |
| T009 | Isolation test suite incl. deliberate-regression case | T005, T008 | `bin/lab-isolation-test` | FR-7, AC-12, AC-13 |

## Phase E — Coordinate anchoring

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| T010 | Heartbeat table and 1 Hz writer | T006 | `bin/lab-heartbeat` | FR-5.1, AC-14 |
| T011 | Snapshot CLI with LSN capture + forced WAL switch; coordinate resolver | T010 | `bin/lab-snapshot`, `bin/lab-snapshots`, `bin/lab-coordinate` | FR-5.2, FR-5.3, FR-5.4, AC-15, AC-16 |

## Phase F — Reset

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| T012 | Three-tier reset CLI, evidence-preserving | T011 | `bin/lab-reset` | FR-6, AC-17 |

## Phase G — Verification and freeze

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| T013 [P] | Filesystem evidence proof: `zfs diff` + `.zfs/snapshot` reads | T011 | proof scripts | FR-2.4, FR-2.5, AC-4, AC-5 |
| T014 [P] | Database evidence proof: before-images, DDL ordering, heartbeat density | T010 | proof scripts | AC-6, AC-7, AC-14 |
| T015 | Full acceptance suite `bin/lab-verify`; idempotence sweep; freeze contracts | T012, T013, T014 | `bin/lab-verify` | AC-1..AC-18 |

## Dependency graph

```
T001
 |-- T002 -- T003 -- T004 --+-- T006 -- T007
 |                          |     |
 |-- T005 ------------------+     +-- T010 -- T011 -- T012 --+
       |                    |                  |             |
       +-- T009 <-- T008 ---+                  +-- T013 [P] -+-- T015
                                               +-- T014 [P] -+
```

## Anti-goals for this tranche

Do not build, in P0: a WAL parser, a filesystem event daemon, `zfs send` plumbing, the ground-truth oracle, the
results row schema, analytics, the ranking function, representations, the model harness, restore verification, the
steady-state workload's business logic, or the injector's damage logic. If a task seems to require one of these, it
has been misread.
