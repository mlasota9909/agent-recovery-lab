# SDD Package, Tranche P2 (Capture Collectors & the Append-Only Ledger)

Same format as P0, P0.1, P1 and P1.1: **GitHub Spec Kit** layout, extended with a `work-instructions/` tier below
`tasks.md` that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `<repo>/sdd`. Nothing under `specs/P0-lab-substrate/`,
`specs/P0.1-remediation/`, `specs/P1-ground-truth-harness/` or `specs/P1.1-provenance-labstate/` is edited. All prior
contracts stay hash-frozen. This tranche adds one new frozen contract (`capture-completeness.md`) and builds the
collectors that produce the evidence ledger.

## Why this tranche exists

Everything so far measured the lab and froze the contracts. **P2 produces the evidence.** For each scripted incident
it assembles a single append-only ledger from five streams:

| Stream | Mechanism | File |
| --- | --- | --- |
| DB changes (with before-images) | `pg_recvlogical` + `wal2json` | `db.jsonl` |
| Schema changes (DDL) | `lab_ddl_audit` event trigger, in the same stream | `db.jsonl` |
| WAL position over time | one-second `lab_heartbeat` rows | `db.jsonl` |
| Point-in-time filesystem + DB | periodic `zfs snapshot -r`, LSN-anchored | `snapshots.json` |
| Filesystem changes | `zfs diff` walker + `.zfs/snapshot/` tree hasher | `fs_diff.tsv`, `fs_hashes.tsv` |

and presents all of it, with no ETL, as queryable DuckDB views.

The research claim depends entirely on this ledger being **complete and exactly-once**: every operation accounted for
once, every UPDATE and DELETE carrying a before-image (so damaged-data retention can be scored), every DDL visible
(SC-03 depends on it), every snapshot carrying an LSN (so a chosen coordinate resolves across layers), and slot lag
returning to zero with the slot cleanly dropped at teardown. If any of these fails silently, the analytics in P3 and
every downstream result is invalid. P2 therefore ends in a **500-operation exactly-once reconciliation**, not just
a set of files.

## What P2 delivers

| # | Deliverable | Task |
| --- | --- | --- |
| 1 | Frozen `capture-completeness.md` contract; tranche opened behind the `lab-ready` entry gate | C001 |
| 2 | `bin/lab-capture` — coherent start/stop/status orchestration of all collectors for an incident window | C002 |
| 3 | LSN-anchored snapshot loop writing `snapshots.json` (every snapshot carries an LSN) | C003 |
| 4 | Filesystem capture: `fs_diff.tsv` walker + `.zfs/snapshot/` tree hasher → `fs_hashes.tsv` | C004 |
| 5 | DB stream integrity: before-images on U/D and DDL in one LSN-ordered `db.jsonl` | C005 |
| 6 | `bin/lab-query` — no-ETL DuckDB view layer over the whole ledger | C006 |
| 7 | `bin/lab-capture-workload` — deterministic 500-op mixed workload with provenance labels | C007 |
| 8 | `bin/lab-ledger-account` — exactly-once reconciliation of workload against ledger | C008 |
| 9 | Capture-session teardown + slot hygiene (lag → 0, slot dropped, snapshots retained) | C009 |
| 10 | `bin/lab-verify-p2` tiered gate; contract re-verify; P2 architecture handoff | C010 |

## Target environment

Unchanged and confirmed by the P0/P0.1/P1/P1.1 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- DuckDB as the read-only view layer (the only new dependency, read-only).
- Deploy root `<repo>`. Config `etc/lab.env`.
- `bin/lab-verify` **18/18**, `bin/lab-verify-p1` **24/24**, `bin/lab-verify-p1.1` **16/16**, all exit 0.

## Two entry conditions (do not skip)

1. `bin/lab-ready` exits 0 (ADR-P1.1-4). If not, run `docs/runbook-slot-recovery.md` first.
2. The git working tree is clean before any provenance-bearing artefact is produced (Article XIV).

## Install

```bash
# on r740core, as mlasota
cd <repo>
# unpack this package so that it merges into ./sdd
```

## Run one task per invocation

```bash
cd <repo>
<executor> --print "$(cat sdd/prompts/execute-P2.md)

TASK_TO_EXECUTE: C001
MODE: DRY_RUN"
```

Review the dry-run bundle, then re-run with `MODE: EXECUTE`. Proceed `C001 → C010`, one task per call. **Do not batch
tasks** — batching lets the agent optimise across contract boundaries and is how a green self-report hid a real defect
three times already.
