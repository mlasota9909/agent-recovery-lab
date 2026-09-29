# Spec — P0: Lab Substrate and Evidence Isolation

**Feature ID:** P0-lab-substrate
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** nothing (this is the foundation tranche)
**Blocks:** P1 (ground truth + results schema), P2 (evidence capture), P4 (restore)

## 1. Purpose

Stand up the victim environment, the out-of-band evidence path and the reset primitives that every later tranche
depends on. P0 builds no analysis logic and makes no measurements. Its single job is to make the lab *reproducible*
and the evidence *trustworthy*, so that results produced in P1 onward are sound.

## 2. Problem statement

The experiment measures whether a recovery coordinate can be identified from out-of-band evidence alone. That claim
collapses unless four things are structurally true before any measurement is taken:

1. Victim state can be returned to a known point, cheaply and repeatably, so arms of the ablation are compared under
   identical conditions rather than merely similar ones.
2. Evidence cannot be reached by the principal that causes damage; otherwise "out-of-band" is an assertion, not a
   property.
3. Filesystem and database change can be tied to a single point in time, so a coordinate means something across both
   layers.
4. Legitimate and damaging activity are distinguishable at scoring time, and *only* at scoring time.

## 3. Scope

### In scope

- ZFS pool and dataset layout inside `thesisvm01`, sized and mounted for the Postgres data directory and a protected
  file subtree.
- PostgreSQL configured for logical decoding with before-images, WAL archiving to a host-side sink, and a DDL audit
  trail that flows through the same decoding stream.
- Two lab identities, `lab_app` (legitimate steady-state work) and `lab_agent` (the injector), separated at both OS
  and database level, with provenance recorded.
- Host-side evidence root, WAL archive sink and results directory, outside the VM, unreadable by victim principals.
- A coordinate anchoring mechanism: a heartbeat table plus per-snapshot LSN capture and WAL switch.
- Three-tier reset CLI: T0 pristine, T1 pre-disaster, T2 post-disaster.
- An isolation test suite including deliberate-regression cases.
- One flat config file recording every discovered value.

### Out of scope

- Steady-state workload content and the injector's damage logic (P1 owns the scenario semantics; P0 only creates the
  identities and proves they are separable).
- Ground-truth oracle, results row schema, analytics, representations, model harness, restore verification.
- Off-host physical air-gap, WORM/object-lock immutability, tamper-evident logging. P0 achieves *logical*
  out-of-band isolation on one machine; physical immutability is a deployment concern recorded as a limitation.
- Containers inside the VM. Explicitly rejected: scripts plus separate identities deliver provenance more simply.

## 4. Requirements

### FR-1 Substrate discovery and configuration
FR-1.1 The lab MUST record every discovered fact (host name, guest name and address, device paths, ZFS version,
PostgreSQL version and data directory, pool and dataset names, mount points, host paths) in `etc/lab.env` as flat
`KEY=value`.
FR-1.2 The lab MUST verify, not assume, whether `/dev/vdb` and `/dev/vdc` are attached to the host or the guest, and
MUST stop if the answer contradicts the plan.
FR-1.3 No later component may hardcode a value that `lab.env` should carry.

### FR-2 Copy-on-write victim storage
FR-2.1 A single ZFS pool MUST exist inside `thesisvm01` across the two available devices.
FR-2.2 A parent dataset MUST contain two children: one for the PostgreSQL data directory, one for the protected file
subtree, so a recursive snapshot yields one atomic point-in-time across both layers.
FR-2.3 Snapshot creation MUST complete in under 2 seconds, and rollback in under 5 seconds, for the lab's data volume.
FR-2.4 Past filesystem content MUST be readable via `.zfs/snapshot/<name>/<path>` without mounting, cloning or
`zfs send`.
FR-2.5 `zfs diff` between two snapshots MUST yield a parseable change list.

### FR-3 PostgreSQL evidence and recovery configuration
FR-3.1 `wal_level=logical`, `archive_mode=on`, and a replication slot for `wal2json` MUST be in place.
FR-3.2 Scenario relations MUST be `REPLICA IDENTITY FULL` so UPDATE and DELETE carry before-images.
FR-3.3 DDL MUST be captured. Because logical decoding does not emit DDL, an event trigger on `ddl_command_end` MUST
write to an audited table that is itself part of the decoded stream, preserving LSN ordering.
FR-3.4 The WAL archive command MUST write outside the VM and MUST refuse to overwrite an existing segment.
FR-3.5 The archive MUST be scoped per incident, so that a T1 reset replaying the same timeline cannot silently
corrupt a prior incident's archive.
FR-3.6 A replication slot MUST NOT be able to fill the victim disk unattended: retention MUST be bounded and lag
MUST be observable.

### FR-4 Identity separation and provenance
FR-4.1 Two OS users and two database roles MUST exist: `lab_app` and `lab_agent`.
FR-4.2 Every captured change MUST carry the causing principal.
FR-4.3 `lab_agent` MUST have the privileges needed to cause each scenario's damage, and no more.
FR-4.4 Neither `lab_app` nor `lab_agent` may read, list, modify or delete anything under the host evidence root, the
WAL archive, or the results store.
FR-4.5 Provenance MUST be available to scoring and MUST be withheld from analysis (Constitution Article II). P0
delivers the field and the two-view separation; P3 enforces the negative test on analytics.

### FR-5 Coordinate anchoring
FR-5.1 A heartbeat table MUST be written once per second carrying wall clock and current WAL LSN, flowing through
logical decoding, giving a dense LSN-to-time index at no extra cost.
FR-5.2 At every snapshot the harness MUST record the LSN and force a WAL segment switch, tying the filesystem
snapshot to a database position.
FR-5.3 A coordinate MUST be representable as the triple defined in `contracts/coordinate.md`.
FR-5.4 Resolving an LSN to a snapshot MUST return the newest snapshot at or below it, and MUST report the resulting
skew rather than hiding it.

### FR-6 Three-tier reset
FR-6.1 T0 pristine: return to an empty, freshly initialised baseline.
FR-6.2 T1 pre-disaster: return to the `pre_injection` snapshot, retaining the quiescent baseline and the legitimate
work history, discarding the damage. This is the default between ablation arms.
FR-6.3 T2 post-disaster: return to `post_capture`, allowing analysis and restore logic to be iterated without
re-running the incident.
FR-6.4 Every tier MUST leave the host-side evidence store and WAL archive intact and re-usable.
FR-6.5 Reset MUST be a single CLI with an explicit tier argument, safe to re-run.

### FR-7 Isolation assurance
FR-7.1 A test suite MUST assert every clause of FR-4.4 from the perspective of each victim principal.
FR-7.2 The suite MUST include a deliberate-regression case: grant a victim principal access, confirm the suite
FAILS, revoke, confirm it passes. A check that cannot fail is worthless (Constitution Article VIII).
FR-7.3 The suite MUST be runnable as one command and emit JSON.

### NFR
NFR-1 Every capability is a CLI under `bin/`, text in, JSON out (Article IV).
NFR-2 Every script is idempotent.
NFR-3 Runtime languages limited to POSIX shell, SQL, Python 3.
NFR-4 No outbound network calls at experiment time.
NFR-5 Nothing outside `<repo>` is written on the host.

## 5. Acceptance criteria

The tranche is accepted when all of the following are demonstrated, with captured output, in review bundles:

| AC | Criterion |
| --- | --- |
| AC-1 | `etc/lab.env` exists and every downstream script sources it; no hardcoded environment values found by grep |
| AC-2 | Device attachment verified as guest-side; contradiction would have stopped the build |
| AC-3 | Recursive snapshot of the parent dataset completes < 2s; rollback < 5s; both timed |
| AC-4 | A file's prior content is read from `.zfs/snapshot/` after deletion, without clone or mount |
| AC-5 | `zfs diff` lists a created, a modified, a deleted and a renamed path correctly |
| AC-6 | A `DELETE` decoded from the logical stream contains the full old tuple (proves REPLICA IDENTITY FULL) |
| AC-7 | A `CREATE TABLE` and a `DROP TABLE` appear in the decoded stream in correct LSN order relative to DML |
| AC-8 | Archive command refuses to overwrite an existing segment and returns non-zero |
| AC-9 | Two successive incidents produce disjoint archive scopes; no segment collision after a T1 reset |
| AC-10 | Replication slot retention is bounded and slot lag is reported by a CLI |
| AC-11 | A change made by `lab_app` and one by `lab_agent` are distinguishable by recorded provenance |
| AC-12 | Each victim principal fails to read, list, write and delete under the evidence root, archive and results store |
| AC-13 | Deliberate-regression: granting access makes the isolation suite FAIL; revoking restores PASS |
| AC-14 | Heartbeat rows appear at ~1 Hz in the decoded stream with monotonically increasing LSN |
| AC-15 | Snapshot manifest records LSN per snapshot and a forced WAL switch occurred at each |
| AC-16 | LSN-to-snapshot resolution returns the newest snapshot at or below, and reports skew in ms and bytes |
| AC-17 | T0, T1 and T2 each return the victim to the expected state, timed, evidence intact |
| AC-18 | Re-running any task's script is a no-op that reports existing correct state |

## 6. Traceability

| Requirement group | Serves | Rationale |
| --- | --- | --- |
| FR-2, FR-5, FR-6 | All scenarios SC-01..SC-04; RQ5 | cross-layer coordinate is built and its skew measured |
| FR-3 | SC-01, SC-03, SC-04 | substrate is real and demonstrated |
| FR-4, FR-7 | All scenarios | isolation is architectural and tested, not asserted |
| FR-6 | Ablation validity | fixed-incident re-evaluation makes arms comparable and runs cheap |

## 7. Known limitations

1. Isolation is logical and same-host. Physical air-gap, WORM immutability and tamper-evident logging are deployment
   concerns, deliberately out of scope; no measured quantity depends on the evidence store's physical location.
2. Filesystem recovery granularity is bounded by snapshot interval. This is not a defect to apologise for: it is the
   real-world constraint SC-02 exists to expose, and it is reported per run as a granularity penalty.
3. T0 is implemented as a ZFS rollback rather than a libvirt snapshot, for speed and code-path reuse; the libvirt
   snapshot is retained only as a coarse rebuild fallback.
