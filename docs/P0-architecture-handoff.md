# P0 Lab Substrate — Architecture Handoff

**Date:** 2026-08-17  
**Status:** P0 COMPLETE at first close, then **accepted only after P0.1** (see `docs/P0.1-architecture-handoff.md` and `docs/p0-acceptance-memo.md`).  
**Verify now:** `TIER M: 9/9 PASS · TIER A: 9/9 PASS · TOTAL: 18/18` — not an undifferentiated 18/18.  
**Next tranche:** P1 may begin.  
**Human review:** Reviewed columns still ☐ — operator owns ticks.

> **P0.1 superseded these open items from §12 below:** start a persistent `pg_recvlogical` consumer (done); delete `${PG_DATA}.pre-zfs` (done); isolation hatch (removed); AC-10 lag (fail-closed, 3360 B steady-state); reset guard (proven). Read the P0.1 handoff before planning P1.

This file is for an architecture chat. It is a snapshot of what was built, tested, decided, and left open. Primary sources remain the SDD package and per-task review bundles.

---

## 1. What this lab is

This experiment measures whether a **recovery coordinate** can be identified from **out-of-band evidence** (filesystem + database change) without using provenance in detection.

P0 builds **no analysis and no measurements**. It stands up:

1. A resettable victim (`thesisvm01`) on ZFS so ablation arms are comparable.
2. An evidence path the victim cannot read or overwrite.
3. A cross-layer coordinate triple (wall clock, LSN, snapshot) with **reported skew**.
4. Two identities (`lab_app` / `lab_agent`) so scoring can tell legitimate work from damage. Provenance is scoring-only (Constitution Article II).

Constitution: `sdd/.specify/memory/constitution.md` (ratified 2026-08-17). Spec/plan/tasks: `sdd/specs/P0-lab-substrate/`.

---

## 2. Topology (as discovered and built)

```
r740core  (Ubuntu 26.04, KVM, ext4, hostname r740core)
|
|-- <repo>/          deploy root (host writes only here)
|     bin/                         CLIs (JSON stdout, stderr logs)
|     etc/lab.env                  single flat KEY=value config
|     evidence/                    0750 mlasota — victim cannot access
|     archive/<incident>/          WAL sink; current -> latest incident
|     basebackup/<incident>/
|     results/                     P1 owns schema
|     logs/review/T001..T015/      acceptance evidence
|     sdd/                         spec kit + WIs + frozen contracts
|
+-- thesisvm01  (KVM guest, 203.0.113.10, also Tailscale 203.0.113.32)
      /dev/vdb (201G) + /dev/vdc (202G)  -->  zpool labpool  STRIPE
      labpool/victim                   parent, snapdir=visible, recursive snap target
        labpool/victim/pgdata          recordsize=8K -> /var/lib/postgresql/18/main
        labpool/victim/protected       -> /srv/protected
      PostgreSQL 18.4, wal_level=logical, archive_mode=on
      slot lab_slot plugin wal2json 2.6-3
      OS+DB: lab_app (steady-state), lab_agent (injector)
```

**DEV_LOCATION=guest** confirmed (vdb/vdc absent on host, present in guest). Plan D-1 not contradicted.

Stripe not mirror: ground truth lives on the host; experiment does not need victim-disk redundancy.

---

## 3. Current `etc/lab.env`

```
LAB_HOST=r740core
LAB_ROOT=<repo>
VM_NAME=thesisvm01
VM_SSH=thesisvm01
VM_ADDR=203.0.113.10
DEV_A=/dev/vdb
DEV_B=/dev/vdc
DEV_LOCATION=guest
ZFS_VERSION=2.4.1-1ubuntu5
PG_VERSION=18
PG_DATA=/var/lib/postgresql/18/main
PG_PORT=5432
ZPOOL=labpool
DS_PARENT=labpool/victim
DS_PGDATA=labpool/victim/pgdata
DS_PROTECTED=labpool/victim/protected
MNT_PROTECTED=/srv/protected
EVIDENCE_ROOT=<repo>/evidence
ARCHIVE_ROOT=<repo>/archive
ARCHIVE_CURRENT=<repo>/archive/current
BASEBACKUP_ROOT=<repo>/basebackup
RESULTS_ROOT=<repo>/results
ARCHIVE_MOUNT_IN_VM=/var/lib/postgresql/archive_sink
DB_NAME=labdb
DDL_AUDIT_TABLE=lab_ddl_audit
SLOT_NAME=lab_slot
SLOT_PLUGIN=wal2json
SLOT_MAX_WAL_KEEP=8GB
SLOT_WARN_RETAINED=64MB
SLOT_MIN_FREE=20GB
OS_USER_APP=lab_app
OS_USER_AGENT=lab_agent
WAL2JSON_VERSION=2.6-3
ROLE_APP=lab_app
ROLE_AGENT=lab_agent
HEARTBEAT_TABLE=lab_heartbeat
HEARTBEAT_HZ=1
SNAP_PREFIX=s_
SNAP_PRISTINE=pristine
SNAP_PRE_INJECTION=pre_injection
SNAP_POST_CAPTURE=post_capture
```

---

## 4. Locked decisions (do not re-litigate)

| ID | Decision |
| --- | --- |
| D-1 | One ZFS pool **in the guest**, parent `labpool/victim` + children pgdata/protected so `zfs snapshot -r` is atomic across DB+FS |
| D-2 | Evidence **pull** from host (`pg_recvlogical`, `pg_basebackup`, `zfs diff` over SSH). Only WAL archive **pushes** out |
| D-3 | Archive scoped per incident via host-managed `archive/current` symlink. T1 replay re-emits same WAL names; without this, silent corruption until P4 |
| D-4 | DDL via `SECURITY DEFINER` event trigger into `lab_ddl_audit` (decoded like DML). Logical decoding does not emit DDL |
| D-5 | `lab_heartbeat` 1 Hz (`clock_timestamp` + `pg_current_wal_lsn`) in the decoded stream |
| D-6 | Snapshot records LSN then `pg_switch_wal()`. Skew is a measured result, not a bug to hide |
| D-7 | T0/T1/T2 all ZFS rollback. T1 (`pre_injection`) is the ablation default |
| D-8 | No containers. Identity = OS user + DB role |
| D-9 | One flat `lab.env` |
| D-10 | Evidence is files (JSONL/TSV), not a service |

**Snapshot LSN ordering (T011):** `zfs snapshot -r` → `pg_current_wal_lsn()` → `pg_switch_wal()`. Recorded LSN is an **upper** anchor just after the FS boundary. Resolver must never pick a snapshot **above** the target LSN (would already contain damage).

---

## 5. Frozen contracts (2026-08-17)

- `sdd/specs/P0-lab-substrate/contracts/lab-env.md`
- `sdd/specs/P0-lab-substrate/contracts/coordinate.md` — triple: `wall_clock`, `lsn`, `snapshot`, `skew_ms`, `skew_bytes`, `resolved_by`
- `sdd/specs/P0-lab-substrate/contracts/cli.md`

Coordinate resolution:

1. `--lsn` → newest snapshot whose recorded LSN is **at or below**; never above; fail if none.
2. `--time` → newest heartbeat at or below, then rule 1. Heartbeat **gap** → `degraded=true` + `gap_ms`, no interpolation.
3. `--snapshot` → that snapshot’s LSN, skew 0.
4. Skew always computed (`pg_wal_lsn_diff` for bytes). Never defaulted to zero except snapshot_first.

---

## 6. CLIs under `bin/`

Contract CLIs: `lab-discover`, `lab-incident`, `lab-wal-receive`, `lab-wal-config`, `lab-slot`, `lab-identities`, `lab-isolation-test`, `lab-heartbeat`, `lab-snapshot`, `lab-snapshots`, `lab-coordinate`, `lab-reset`, `lab-verify`.

Supporting (task-owned, not all in cli.md): `lab-zfs-init`, `lab-pgdata-relocate`, `lab-schema-init`, `lab-zfs-diff-*`, `lab-repomix-backup`.

Conventions: JSON on stdout; exit 0/1/2/3; idempotent `"changed": false`; no key material.

---

## 7. Database substrate (`labdb`)

- `lab_ledger` — ~1,000,000 synthetic rows (seeded in 16s); `REPLICA IDENTITY FULL` (relreplident=`f`). After T015 rehearsal count was 1,000,003.
- `lab_reference` — FULL replica identity.
- `lab_ddl_audit` — event trigger on `ddl_command_end` (+ paired drop trigger because PG does not expose dropped objects on `ddl_command_end` alone). SECURITY DEFINER, owned by postgres. `lab_agent` can **cause** rows, cannot SELECT/UPDATE/DELETE.
- `lab_heartbeat` — 1 Hz writer (systemd `lab-heartbeat.service` on guest). REPLICA IDENTITY DEFAULT.
- `lab_provenance_marker` — AFTER DML trigger, SECURITY DEFINER, `session_user`. Scoring only. P3 must strip this from analytics and assert coordinate unchanged.

Grants: `lab_app` SELECT/INSERT/UPDATE on scenario tables, **no DELETE**. `lab_agent`: DELETE+UPDATE on ledger, ALTER/DROP scenario relations, write `/srv/protected`. Neither is superuser/replication.

---

## 8. WAL archive append channel (T005)

Not a filesystem mount. Guest `postgres` has a dedicated ed25519 key under `/var/lib/postgresql/archive_sink/` (0700). Host authorized_keys:

```
command="<repo>/bin/lab-wal-receive",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty
```

Receiver accepts only `append <24 uppercase hex>`. Writes via temp + `ln` (fails if exists). Guest cannot name the incident dir. Fingerprint in T005 bundle: `SHA256:m4aFbwBACt6HzWUlI5LK5YhAk+MWkZAEhhW4/LYxkHc`. Private key never logged.

`archive_timeout=1min` so idle periods still close segments.

---

## 9. Task-by-task results

All agent results PASS 2026-08-17. Bundles: `logs/review/Tnnn/`.

| Task | What was done | Negative test | Notable deviation |
| --- | --- | --- | --- |
| T001 | Discover host/guest, write lab.env. Installed PostgreSQL 18 on guest (operator later authorised software install). | Unreachable VM_SSH → exit 2, lab.env unchanged | First runs BLOCKED: no passwordless sudo, then no PG. Then PASS |
| T002 | Stripe pool, parent+2 children, snapdir=visible, pgdata 8K. Snap 0.139s, rollback 0.203s | Missing DEV_B → exit 2, pool intact | pgdata `canmount=off` until T003 |
| T003 | Relocate PGDATA onto ZFS; original kept at `PG_DATA.pre-zfs` (not deleted) | Copy while cluster running refused (exit 2) | `fuser -m` unusable on `/`; idempotence briefly remounted staging — recovered; now short-circuits if already on DS_PGDATA |
| T004 | labdb, 1e6 ledger rows, FULL replica identity, DDL audit | Temporarily DEFAULT, documented, restored FULL | lab_agent grants deferred to T008; extra sql_drop trigger |
| T005 | Host dirs 0750, lab-incident, overwrite-refusal receive | postgres cannot list other incidents or overwrite | ARCHIVE_MOUNT_IN_VM is SSH client dir not NFS/9p; created OS lab_agent early for denial test |
| T006 | wal_level=logical, archive_command, lab_slot wal2json, host pg_recvlogical proof | Bad archive_command increased failed_count 0→6 then restored | Narrow HBA for host 203.0.113.1 replication; stats reset so final failed_count=0 |
| T007 | max_slot_wal_keep_size=8GB, lab-slot lag CLI, overwrite exit 42 | Low-space / lag assertions fail closed | Extra keys SLOT_WARN_RETAINED, SLOT_MIN_FREE |
| T008 | OS+DB identities, least privilege, provenance markers | Grant lab_app DELETE, T008-6 breaks, revoke restores | Disposable wal2json slot for AC-11 then dropped |
| T009 | lab-isolation-test, 55 assertions, `--regression` PASS→FAIL→PASS | Missing-path negative | `--negative-nonexistent` extra flag |
| T010 | 1 Hz heartbeat systemd writer | Gap handling forwarded to T011 | Brief writer outage during template fix; ~0.983–1.0 Hz measured |
| T011 | snapshot/snapshots/coordinate CLIs | Snapshot **above** LSN not selected; far LSN skew not zeroed | none |
| T012 | lab-reset t0/t1/t2; evidence hashed intact; invalidated snaps rejected | Running-postgres guard exists | Guest `/tmp` noexec blocked live “still running” binary test |
| T013 | `.zfs/snapshot` read after delete; zfs diff +/M/-/R | Silent same-size mtime-unchanged still `M` | Extra parent-dir `M` from ZFS; no clones/send |
| T014 | Decoded DELETE old tuple; CREATE/DROP ordered vs DML; heartbeat ~0.991 Hz | Replica identity DEFAULT would drop before-images; restored FULL | Disposable decode slot so lab_slot not consumed |
| T015 | lab-verify AC-1..18; idempotence; hardcode/prohibition sweeps; 49.335s e2e rehearsal; freeze contracts | Injected env literal → only AC-1 FAIL, then restored | Slot consumer inactive; lag ~436MB > 64MB warn — start consumer before P1 |

---

## 10. Full-suite acceptance (T015)

`bin/lab-verify` last recheck: **18 PASS / 0 FAIL**, exit 0.

| AC | Criterion | How proven |
| --- | --- | --- |
| AC-1 | lab.env sourced; no hardcoded env in downstream bin | literal sweep, zero violations |
| AC-2 | Devices guest-side | T001 |
| AC-3 | Snap <2s, rollback <5s | T002 0.139s / 0.203s |
| AC-4 | Prior file content via `.zfs/snapshot` | T013 |
| AC-5 | zfs diff create/mod/del/rename | T013 |
| AC-6 | DELETE old tuple (REPLICA IDENTITY FULL) | T014 |
| AC-7 | CREATE/DROP in stream, LSN-ordered vs DML | T014 |
| AC-8 | Archive overwrite refused non-zero | T007 exit 42, checksum unchanged |
| AC-9 | Two incidents, disjoint archive scopes | T005 |
| AC-10 | Slot retention bounded, lag reported | bounded=true; **consumer inactive**, retained_bytes=436278992 |
| AC-11 | lab_app vs lab_agent distinguishable | T008 markers in wal2json |
| AC-12 | Victim principals denied evidence/archive/results | 55 PASS isolation |
| AC-13 | Isolation goes red on grant, green on revoke | 3-phase regression |
| AC-14 | Heartbeat ~1 Hz monotonic LSN | T014 0.991 Hz |
| AC-15 | Snapshot manifest LSN + WAL switch | ops `[zfs_snapshot, pg_current_wal_lsn, pg_switch_wal]` |
| AC-16 | Newest snapshot at-or-below; skew reported | lab-coordinate |
| AC-17 | T0/T1/T2 expected state, evidence intact | T012 + T015 rehearsal |
| AC-18 | Re-run scripts `"changed": false` | T001–T010 setup CLIs |

End-to-end rehearsal: legitimate lab_app change → lab_agent damage → resolve coordinate → T1 damage absent → recreate post_capture → T2 damage present. Cycle **49.335 s**. T1 rollback 5.813 s (reset 13.386 s); T2 rollback 4.706 s (reset 17.606 s).

---

## 11. Isolation / ethics constraints (do not violate)

- Article II: never wire `principal` / provenance into detection, ranking, representations, or models. P3 owns the strip-and-assert test.
- Article V banned: WAL parser / pg_waldump analysis, fanotify/inotify evidence daemons, zfs send/recv/clones/loop mounts for past state, extra brokers/ORMs/web daemons.
- Article III: evidence on host, append-only WAL path, closed files 0444.
- Article X: synthetic data only; host writes confined to `<repo>`.

---

## 12. Open items for P1 (and ops)

1. **Start a `pg_recvlogical` / wal2json consumer** against `lab_slot` before capture. AC-10 passed because retention is bounded, but lag is above 64MB warn and `active=false`.
2. Operator should tick Reviewed in `checklist.md` after reading bundles.
3. `${PG_DATA}.pre-zfs` still on guest; operator may delete after review.
4. P1: results-row contract, scenario semantics, ground-truth oracle. Do not expand P0 contracts in passing.
5. Isolation is logical/same-host (known limitation). FS granularity = snapshot interval (SC-02). T0 is ZFS rollback not libvirt snapshot.

---

## 13. Where to read next (architecture chat)

1. `sdd/.specify/memory/constitution.md`
2. `sdd/specs/P0-lab-substrate/spec.md` + `plan.md`
3. Frozen contracts (three files)
4. This handoff
5. Spot-check `logs/review/T011/ordering-decision.md`, `T005/append-channel-design.md`, `T008/provenance-mechanism.md`, then `docs/P0.1-architecture-handoff.md`

Backup of this work: run `<repo>/bin/lab-repomix-backup` → dated `backups/thesis-p01-<UTC>.md` plus `backups/repomix-latest.md`. Pack includes SDD, `bin/`, `etc/`, both architecture handoffs, review-bundle markdown, and P0.1 proof JSON (not WAL/archive/keys; not bulky `verify-results.json` / heartbeat dumps).
