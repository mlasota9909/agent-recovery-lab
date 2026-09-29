# SDD Package, Tranche P0.1 (P0 Remediation)

Remediation tranche. Same format as P0: **GitHub Spec Kit** layout extended with a `work-instructions/` tier below
`tasks.md`. This package does **not** replace P0; it sits alongside it and repairs three defects and two hygiene
items found in the P0 acceptance review.

Unpack so that it merges into the existing `<repo>/sdd`. Nothing in `specs/P0-lab-substrate/` is
edited by this package — P0's contracts stay frozen. What changes is implementation under `bin/`, the acceptance
runner, and the constitution (one appended amendment).

## Why this tranche exists

The P0 build is good work and most of it stands. Three findings block acceptance:

| ID | Finding | Severity |
| --- | --- | --- |
| F-1 | `bin/lab-wal-receive` — the forced command that *is* the out-of-band boundary — contains a conditional branch that reads a file under `EVIDENCE_ROOT` when a sentinel file is present. Shut today, unverified by any criterion, and unacceptable in a boundary component. | Blocker |
| F-2 | The replication slot retained ~436 MB of WAL with no consumer attached and `active=false`, while AC-10 passed because it only asserts retention is *bounded*. At the configured 8 GB cap the slot invalidates and the evidence stream breaks mid-matrix. | Blocker |
| F-3 | Nine of eighteen acceptance criteria are satisfied by searching an agent-authored markdown file for a token, via `return token in text and "FAIL" not in text`. The headline "18/18 PASS" conflates mechanical verification with self-attestation, and is brittle in a silly direction: a legitimate observation containing the word FAIL flips a criterion red. | Blocker |
| F-4 | T012's "refuse to roll back while PostgreSQL is live" guard was never exercised — the test binary could not run because guest `/tmp` is `noexec`, so the case was skipped. | Should-fix |
| F-5 | `${PG_DATA}.pre-zfs` remains on the guest; exact OS and PostgreSQL versions are not pinned in a machine-readable artefact. | Hygiene |

## Target environment

Unchanged from P0. Host `r740core` (Ubuntu Server, KVM, ext4 root), victim guest `thesisvm01`, deploy root
`<repo>`, config `etc/lab.env`, agent has sudo on host and keyless SSH with sudo into the guest.
Confirmed by the P0 build: Ubuntu 26.04 guest, PostgreSQL 18.4, devices `/dev/vdb` and `/dev/vdc` attached to the
guest (`DEV_LOCATION=guest`).

## Install

```bash
# on r740core, as mlasota
cd <repo>
# unpack this package so that it merges into ./sdd
ls sdd/specs/P0.1-remediation/tasks.md   # sanity check
```

## Execute

One task per invocation, in order, dry run first. Do not batch.

```bash
cd <repo>

# read-only dry run, changes nothing
<executor> --print "$(cat sdd/prompts/execute-remediation.md)

TASK_TO_EXECUTE: R001
MODE: DRY_RUN"

# then for real
<executor> --force "$(cat sdd/prompts/execute-remediation.md)

TASK_TO_EXECUTE: R001
MODE: EXECUTE"
```

Order: `R001 -> R002 -> R003 -> R004 -> R005 -> R006`. R004 and R005 may run in either order or in parallel with
R003. R006 is the gate and must run last.

## What you review after each task

Read `sdd/specs/P0.1-remediation/work-instructions/WI-Rnnn.md` -> *Review bundle*, then check
`<repo>/logs/review/Rnnn/` exists and its `acceptance.md` rows are tier-labelled. Tick the row in
`sdd/specs/P0.1-remediation/checklist.md` yourself. The agent does not own the `Reviewed` column.

## Layout added by this package

```
sdd/
  README-P0.1.md
  .specify/memory/constitution-amendment-001.md   <- appended to the constitution by R001
  prompts/execute-remediation.md
  specs/P0.1-remediation/
    spec.md
    plan.md
    tasks.md
    checklist.md
    work-instructions/WI-R001..WI-R006.md
```

## Stop conditions

Halt and report rather than improvise if: the P0 review bundles are absent, `bin/lab-wal-receive` differs
structurally from what `plan.md` describes, removing the hatch breaks the legitimate append path, the slot cannot be
dropped because a consumer is attached, or any acceptance test in a work instruction fails. Silent degradation is a
constitution violation (Article VIII).
