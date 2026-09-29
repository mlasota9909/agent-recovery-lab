# SDD Package, Tranche P1.1 (Provenance & Lab-State Remediation)

Same format as P0, P0.1 and P1: **GitHub Spec Kit** layout, extended with a `work-instructions/` tier below
`tasks.md` that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `/home/mlasota/thesis/sdd`. Nothing under `specs/P0-lab-substrate/`,
`specs/P0.1-remediation/` or `specs/P1-ground-truth-harness/` is edited. All prior contracts stay hash-frozen. This
tranche repairs three defects found in the P1 acceptance review and does not add or change any frozen contract.

## Why this tranche exists

P1 delivered the instruments and its acceptance runner reported every criterion green. Review of the code and the
live end-state found three problems the gate did not:

1. **`harness_commit` names the wrong commit.** `bin/lab-evaluate-arm` writes `env("HARNESS_COMMIT_AT_P1_OPEN")` —
   the commit recorded when the tranche was *opened* at W001 — as the `harness_commit` of every results row. The
   frozen results-row contract defines that field as *"the git commit of the harness that produced this row."* So a
   row can name code that is not the code that produced it, and there is no guard against a dirty working tree. For a
   reproducibility field this is a silent falsehood, and it is exactly the class of defect that surfaces
   later when a surprising number cannot be reproduced.

2. **The lab is not in a valid capture state.** The P1 end-state shows the replication slot with
   `invalidation_reason=wal_removed` and `slot_active=false`. P2's collectors attach to that stream; starting P2 from
   an invalidated slot would produce a broken evidence ledger. "Ready for P2" was asserted in prose, not gated.

3. **The sample-size headline reads as completed work.** The memo presents `total_incidents: 10` and
   `total_arm_runs: 150` as top-line totals while `restore_stubbed: true`. Those are *planned* figures derived from
   the throughput measurement; no experimental arm has run. Left as-is they misstate the state of the project.

None of these is fraud. Two are honestly disclosed in the handoff's own notes. But each must be closed before P2,
and the first must be closed before **any** results row is used in analysis.

## What P1.1 delivers

| # | Deliverable | Closes |
| --- | --- | --- |
| 1 | New **Article XIV** — results-row provenance of record | The class behind defect 1 |
| 2 | `harness_commit` recorded from `git rev-parse HEAD` at row-production time, with a dirty-tree refusal | Defect 1 |
| 3 | Quarantine of the P1 stub rows as engineering fixtures, excluded from analysis | Defect 1 fallout |
| 4 | `bin/lab-ready` — a mechanical P2-readiness gate — plus a documented recovery runbook | Defect 2 |
| 5 | Planned-vs-completed disambiguation across the memo and plan | Defect 3 |
| 6 | `bin/lab-verify-p1.1` gate and an updated acceptance memo recording that P1 was accepted only after remediation | All |

## Target environment

Unchanged and confirmed by the P0/P0.1/P1 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- Deploy root `/home/mlasota/thesis`. Config `etc/lab.env`.
- `bin/lab-verify` reports **TIER M 9/9 · TIER A 9/9 · TOTAL 18/18**, exit 0.
- `bin/lab-verify-p1` reports **TIER M 23/23 · TIER A 1/1 · TOTAL 24/24**, exit 0.

## Install

```bash
# on r740core, as mlasota
cd /home/mlasota/thesis
# unpack this package so that it merges into ./sdd
ls sdd/specs/P1.1-provenance-labstate/tasks.md   # sanity check
```

## Execute

One task per invocation, in order, dry run first. **Do not batch.**

```bash
cd /home/mlasota/thesis

# read-only dry run, changes nothing
<executor> --print "$(cat sdd/prompts/execute-P1.1.md)

TASK_TO_EXECUTE: X001
MODE: DRY_RUN"

# then for real
<executor> --force "$(cat sdd/prompts/execute-P1.1.md)

TASK_TO_EXECUTE: X001
MODE: EXECUTE"
```

Order: `X001 -> X002 -> X003 -> X004 -> X005 -> X006`. `X004` and `X005` may run in either order once `X003` is done.
`X006` is the gate and runs last.

## What you review after each task

Open `sdd/specs/P1.1-provenance-labstate/work-instructions/WI-Xnnn.md`, read its *Review bundle* and *Operator review
checklist*, then check `/home/mlasota/thesis/logs/review/Xnnn/` exists and its `acceptance.md` rows are
**tier-labelled** per Article XIII. Tick the row in `checklist.md` yourself — the agent does not own the `Reviewed`
column.

The task worth reading line by line is **X002**, because it changes what every future results row records, and that
is expensive to get wrong.

## Anti-goals

Do not, in P1.1: change any frozen contract; add a field to the results row (the schema is frozen — quarantine by
path, not by new fields); build any analytics, ranking, representation or model; implement real restore. If a task
appears to require one of these, it has been misread.
