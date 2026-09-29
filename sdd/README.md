# SDD Package, Tranche P0 (Lab Substrate)

Format: **GitHub Spec Kit** layout (`constitution -> spec -> plan -> tasks -> implement`), extended with a
**`work-instructions/` tier below `tasks.md`**. Spec Kit's known weakness is that tasks are one-liners with no
sub-task detail; every task `Tnnn` here has a matching `WI-Tnnn.md` giving exact commands, files, verification
and review bundle.

## Target environment (assumed, verified by T001)

| Thing | Value |
| --- | --- |
| Host | `r740core`, Ubuntu Server, KVM, ext4 root, ZFS packages installed |
| Victim VM | `thesisvm01`, KVM guest, keyless SSH from host already working |
| Block devices | `/dev/vdb`, `/dev/vdc` (virtio -> **inside `thesisvm01`**) |
| Deploy root | `<repo>` on the host |
| This package | `<repo>/sdd` |
| Agent rights | sudo on host; keyless SSH to `thesisvm01` with sudo in guest |
| Executor | any spec-following executor |

> **Device assumption.** `/dev/vdb` and `/dev/vdc` are virtio block devices, so they are disks attached to
> `thesisvm01`, not to the bare-metal host. That matches ADR-001 (ZFS datasets live *inside* the VM).
> **T001 verifies this and STOPS if the devices are actually on the host.** Do not let the agent guess.

## Install

```bash
# on r740core, as mlasota
mkdir -p <repo>
cd <repo>
# upload/unzip this package so that it lands at <repo>/sdd
git init -q 2>/dev/null || true
```

## Execute

Run **one task at a time**, in order. Do not paste the whole tranche in one go: the agent will optimise across
task boundaries, collapse the contracts, and you lose the ability to tell which layer broke.

```bash
cd <repo>

# read-only dry run first, no changes made
<executor> --print "$(cat sdd/prompts/execute-tranche.md)

TASK_TO_EXECUTE: T001
MODE: DRY_RUN"

# then execute for real
<executor> --force "$(cat sdd/prompts/execute-tranche.md)

TASK_TO_EXECUTE: T001
MODE: EXECUTE"
```

After each task, read `sdd/specs/P0-lab-substrate/work-instructions/WI-Tnnn.md` -> *Review bundle*, and check the
agent wrote `<repo>/logs/review/Tnnn/`. Then tick the row in `sdd/specs/P0-lab-substrate/checklist.md`.

## Order

`T001 -> T002 -> T003 -> T004 -> T005 -> T006 -> T007 -> T008 -> T009 -> T010 -> T011 -> T012 -> T013 -> T014 -> T015`

`T013` and `T014` may run in parallel with `T010`/`T011` if you want to save wall-clock; everything else is strictly
sequential.

## Layout

```
sdd/
  README.md                     <- you are here
  .specify/memory/constitution.md   <- non-negotiable principles, read by every task
  prompts/execute-tranche.md    <- the agent prompt (paste target)
  specs/P0-lab-substrate/
    spec.md                     <- WHAT: requirements + acceptance criteria
    plan.md                     <- HOW: architecture, decisions, topology
    tasks.md                    <- ordered, dependency-aware task list
    checklist.md                <- human sign-off sheet
    contracts/                  <- frozen interfaces (lab.env, coordinate, CLI)
    work-instructions/          <- WI-T001..WI-T015, the tier below tasks
```

## Stop conditions

The agent must halt and report rather than improvise if: a device is missing or already in use, `thesisvm01` is
unreachable, a PostgreSQL major version differs from what `lab.env` records, or any acceptance check in a WI fails.
Silent degradation is a constitution violation (Principle VIII).
