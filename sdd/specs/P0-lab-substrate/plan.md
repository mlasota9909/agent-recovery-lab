# Plan — P0: Lab Substrate and Evidence Isolation

Technical approach for `spec.md`. Decisions here are locked; tasks implement them and do not re-open them.

## 1. Constitution check

| Article | How this plan complies |
| --- | --- |
| I Determinism | P0 contains no selection logic at all; it only creates substrate. Nothing here is a model. |
| II Provenance | Two identities created at OS and DB level; provenance recorded at capture; P0 ships the field, P3 enforces the negative test |
| III Out-of-band | Evidence root, archive sink and results store are host paths; single narrow append channel outward; closed files 0444 |
| IV CLI-first | Ten CLIs under `bin/`, all JSON out |
| V Stock only | `zfs diff` + `.zfs/snapshot`; `wal2json` logical decoding; base backup + archived WAL. No parser, no daemon, no send/recv |
| VI Simplicity | Shell + SQL + Python only; one flat config; no containers |
| VII Contracts | `contracts/lab-env.md`, `contracts/coordinate.md`, `contracts/cli.md` frozen at tranche end |
| VIII Fail loud | Every check exits non-zero on absence; isolation suite carries a deliberate-regression case |
| IX Traceability | Each task carries scenario / RQ |
| X Containment | Synthetic data only; destruction confined to guest; host writes confined to deploy root |
| XI Evidence | Review bundle per task under `logs/review/` |

## 2. Topology

```
r740core  (host, Ubuntu Server, KVM, ext4)
|
|-- <repo>/            deploy root
|     |-- sdd/                       this package
|     |-- bin/                       CLIs
|     |-- etc/lab.env                the single config file
|     |-- evidence/                  EVIDENCE ROOT      (0750 mlasota, victim has no access)
|     |     +-- <scenario>/<incident>/
|     |           db.jsonl           logical decoding stream (wal2json)
|     |           fs_diff.tsv        zfs diff output
|     |           fs_hashes.tsv      per-snapshot content hashes
|     |           snapshots.json     snapshot manifest w/ LSN + skew
|     |           injection.log      what the injector did (scoring only)
|     |           workload.json      steady-state manifest (scoring only)
|     |-- archive/<incident>/        WAL ARCHIVE SINK   (the one inbound append path)
|     |     current -> <incident>/   host-managed symlink, per-incident scoping
|     |-- basebackup/<incident>/     pg_basebackup output
|     |-- results/                   results store (P1 owns schema)
|     +-- logs/review/<task>/        review bundles
|
+-- thesisvm01  (KVM guest = THE VICTIM)
      |-- /dev/vdb, /dev/vdc  -->  zpool labpool
      |-- labpool/victim               parent  (recursive snapshot target)
      |     |-- labpool/victim/pgdata     -> /var/lib/postgresql/<ver>/main
      |     +-- labpool/victim/protected  -> /srv/protected
      |-- postgres: wal_level=logical, archive_mode=on, slot for wal2json
      |-- lab_app    (OS user + DB role)  legitimate steady-state work
      +-- lab_agent  (OS user + DB role)  the injector
```

## 3. Locked decisions

**D-1 ZFS lives in the guest, one pool, one parent dataset, two children.**
`/dev/vdb` and `/dev/vdc` are virtio devices, therefore guest disks. One `labpool` across both; parent
`labpool/victim` with children `pgdata` and `protected`. Rationale: `zfs snapshot -r labpool/victim@X` gives a single
atomic point-in-time across the database and the filesystem, which is what makes the coordinate triple meaningful
rather than approximate. Sibling datasets would not.

**D-2 Evidence pull, not push.** Three of four evidence streams are host processes reaching into the guest:
`pg_recvlogical`, `pg_basebackup`, and `zfs diff` over SSH. Only the WAL archive pushes outward. Consequence: the
victim has exactly one narrow append path, so Article III becomes a claim about a single auditable channel. This
materially simplifies the isolation argument.

**D-3 Archive sink is incident-scoped behind a host-managed symlink.** `archive_command` writes to
`archive/current/`, and the host repoints `current` at a new incident directory before each run. Rationale: after a
T1 reset the cluster replays the same timeline and re-emits segment names it has already emitted, with different
contents. Without per-incident scoping this silently corrupts the archive, and the failure would not surface until a
PITR attempt in P4 — days later, and very hard to diagnose. The archive command additionally refuses overwrite.

**D-4 DDL via event trigger into a decoded table.** Logical decoding does not emit DDL, which would gut SC-03
(schema damage). An event trigger on `ddl_command_end`, `SECURITY DEFINER`, owned by `postgres`, writes to
`lab_ddl_audit`, which is included in the decoded relation set. Schema changes therefore arrive in the *same* JSONL
stream in correct LSN order, with no second pipeline to reconcile. `lab_agent` can cause audit rows but cannot read
or alter them.

**D-5 Heartbeat table for LSN-to-time density.** `lab_heartbeat` gets one row per second carrying
`clock_timestamp()` and `pg_current_wal_lsn()`. Because it flows through decoding like any other change, the evidence
store gains a dense LSN/time index for free, with no extra collector process. This is what lets an operator-supplied
approximate wall-clock incident time be mapped into LSN space.

**D-6 Snapshot-time LSN capture plus forced WAL switch.** At each snapshot the harness records
`pg_current_wal_lsn()` into `snapshots.json` and calls `pg_switch_wal()`. This is the filesystem-to-database tie.
Cross-layer skew is then a *reported measurement* per run, not a problem to be solved — which converts the
hardest integration problem into a result.

**D-7 Three-tier reset, all ZFS rollback.** T0 pristine, T1 `pre_injection` (default between arms), T2
`post_capture` (analysis iteration). All three share one code path; the libvirt snapshot survives only as a coarse
rebuild fallback. T1 is what makes the ablation valid: inject once, evaluate R0/R1/R2 against byte-identical
evidence, so arms differ by representation alone.

**D-8 No containers.** Rejected. The VM already provides isolation, filesystem control and the reset primitive.
Containers add a second orchestration surface and buy nothing experimental. Their one real contribution —
distinguishing legitimate from damaging activity — is delivered more simply by identity: separate OS users and
separate Postgres roles, so provenance is a recorded fact rather than a runtime artefact.

**D-9 One flat config file.** `etc/lab.env`, `KEY=value`, sourced by every script. No config framework, no layering,
no per-environment overrides.

**D-10 Storage is a directory tree, not a service.** Evidence is JSONL and TSV files. Later tranches point DuckDB at
them in place; no ETL, no schema migration, no server to run, and immutability is trivially enforceable with file
modes.

## 4. Sequencing rationale

T001 discovers reality before anything is built, and can stop the tranche. T002-T003 create storage, because
Postgres must be relocated onto ZFS before it is configured. T004-T007 configure the database for evidence and
recovery. T008-T009 create identities and prove isolation, before any workload exists to muddy the test. T010-T011
build coordinate anchoring, which needs a configured database. T012 builds reset, which needs snapshots to exist.
T013-T015 verify end-to-end and freeze the contracts.

Parallelism is limited on purpose: T013/T014 may overlap T010/T011, everything else is sequential. The cost of a
wrong ordering here is a substrate defect discovered in P4.

## 5. Risks

| Risk | Mitigation |
| --- | --- |
| Devices are host-attached, not guest-attached | T001 verifies and stops; plan would need amendment before proceeding |
| Postgres data directory move corrupts cluster | T003 stops the cluster, copies with `rsync -aHAX --numeric-ids`, verifies, keeps the original until AC passes |
| Replication slot fills victim disk mid-matrix | Bounded retention, lag CLI, and a pre-run check in T007 |
| Archive collision across re-runs | D-3 incident scoping plus overwrite refusal (AC-8, AC-9) |
| DDL invisible, SC-03 silently unmeasurable | D-4 event trigger, proven by AC-7 |
| Before-images absent, damage retention unscorable | `REPLICA IDENTITY FULL`, proven by AC-6 decoding a real DELETE |
| Isolation asserted but untested | AC-13 deliberate-regression case |
| Agent drifts across task boundaries | One task per invocation; review bundle per task; frozen contracts |
