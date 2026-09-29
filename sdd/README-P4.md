# SDD Package, Tranche P4 (Restore, Validation & the Promotion Gate)

Same format as P0, P0.1, P1, P1.1, P2, P2.1, P3 and P3.1: **GitHub Spec Kit** layout, extended with a
`work-instructions/` tier below `tasks.md` that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `/home/mlasota/thesis/sdd`. Nothing under any prior `specs/*/` directory is
edited, and every prior frozen contract — including `capture-completeness.md` and its amendment — stays
byte-identical so its recorded hash keeps verifying.

## Why this tranche exists — the loop-closing milestone

Everything upstream built the evidence ledger (P2/P2.1) and the deterministic detection-and-ranking layer that turns
it into a recovery coordinate (P3). **P4 closes the loop.** It takes a coordinate and performs the *real* recovery:
point-in-time restore of PostgreSQL into an isolated sandbox, a ZFS clone restore of the filesystem subtree, and a
validation of the restored state against the ground-truth oracle manifest at row, byte and schema level, ending in a
consistency verdict and a promotion gate.

The single acceptance test the whole tranche is built around: **feed the known ground-truth coordinate and the restore
must validate clean.** If feeding the perfect coordinate does not reproduce the pre-incident state exactly, the harness
is wrong and no analysis result from P3 or P6 means anything. This is the test that certifies the measurement apparatus
itself.

**Milestone:** P0 through P4 plus SC-01 is the complete walking skeleton. At this point the experiment has a sound,
quantitative, end-to-end result — inject, capture, detect, rank, restore, validate — even if nothing else lands. This
milestone is protected above all others.

## The one rule that makes P4 safe

**Restore is read-only with respect to the victim and the evidence store.** A restore MUST:

- reconstruct PostgreSQL into a **new, isolated sandbox cluster** (its own PGDATA and port) by replaying the host-side
  base backup and archived WAL — it must **never** start, stop, or write the victim cluster; and
- reconstruct the filesystem by **`zfs clone`** of the resolved snapshot into a sandbox mountpoint — it must **never**
  `zfs rollback` or otherwise mutate the victim dataset.

`zfs clone` is non-destructive; `zfs rollback` destroys the victim's current state. The distinction is load-bearing and
is enforced by a mechanical check: a whole-of-victim-plus-evidence manifest must be **byte-identical before and after**
a full restore-and-validate cycle. This is the P4 analogue of the Article XVI read-only-gate property, applied to the
restore path.

## What P4 delivers

| # | Deliverable | Task |
| --- | --- | --- |
| 1 | Two frozen contracts: `restore-report.md` (the verdict record) and `promotion-gate.md` (validate-vs-promote + sandbox isolation) | E001 |
| 2 | `bin/lab-restore-db` — PITR of PostgreSQL to a target LSN into an isolated sandbox cluster | E002 |
| 3 | `bin/lab-restore-fs` — ZFS clone restore of the filesystem subtree at the resolved snapshot | E003 |
| 4 | `bin/lab-restore` — orchestrator: one coordinate → both layers restored to it → cross-layer skew reported | E004 |
| 5 | `bin/lab-validate` — row/byte/schema comparison of restored state against the oracle manifest | E005 |
| 6 | `bin/lab-verdict` — the 4-level consistency verdict, emitted per `restore-report.md` | E006 |
| 7 | `bin/lab-promote` — the guarded promotion gate: clean verdict + explicit authorization; lab simulation only | E007 |
| 8 | Wiring: oracle↔reality agreement check + the read-only-w.r.t.-victim safety property | E008 |
| 9 | Loop-closing headline (true coordinate → clean) + discrimination negatives | E009 |
| 10 | `bin/lab-verify-p4` tiered gate; prior hashes re-verified; read-only + regression; P4 handoff | E010 |

## Target environment

Unchanged and confirmed by the P0→P3.1 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- DuckDB as the read-only view layer (no new third-party runtime in P4).
- Deploy root `/home/mlasota/thesis`. Config `etc/lab.env`.
- Gates green: `lab-verify` **18/18**, `lab-verify-p1` **24/24**, `lab-verify-p1.1` **16/16**, `lab-verify-p2`
  **18/18**, `lab-verify-p2.1` **16/16**, `lab-verify-p3` **19/19**, `lab-verify-p3.1` **16/16**, all exit 0.
- Sixteen constitutional articles in force (through Article XVI, read-only verification gates).

## Two entry conditions (do not skip)

1. `bin/lab-ready` exits 0 (ADR-P1.1-4), **and** the incident P4 restores has passed `bin/lab-ledger-account`
   exactly-once (ADR-P2-7). P4 refuses to restore against an unreconciled ledger.
2. The git working tree is clean before any provenance-bearing or results-bearing artefact is produced (Article XIV).
3. P4 restores only against an `arm-coordinate` (or the ground-truth coordinate) whose `selection_inputs` no-peek
   check passed — never against a coordinate that read the injection log or oracle optimum (P3 carry-forward note).

## Run one task per invocation

```bash
cd /home/mlasota/thesis
<executor> --print "$(cat sdd/prompts/execute-P4.md)

TASK_TO_EXECUTE: E001
MODE: DRY_RUN"
```

Review the dry-run bundle, then re-run with `MODE: EXECUTE`. Proceed `E001 -> E010`, one task per call. **Do not batch
tasks** — batching lets the agent optimise across boundaries and is how a green self-report hid a real defect in
earlier tranches (the P0.1 hatch, the P1 `harness_commit`, the P2 `xid` substitution, the P3 impossible-green
regression).
