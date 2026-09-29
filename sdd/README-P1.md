# SDD Package, Tranche P1 (Ground Truth, Results Contract, Run Harness)

Same format as P0 and P0.1: **GitHub Spec Kit** layout, extended with a `work-instructions/` tier below `tasks.md`
that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `/home/mlasota/thesis/sdd`. Nothing under `specs/P0-lab-substrate/` or
`specs/P0.1-remediation/` is edited. P0's three contracts stay frozen; this tranche **adds** two new frozen
contracts and appends keys to `etc/lab.env`.

## Why this tranche exists, and why it is second

P1 builds no intelligence. It builds the **instruments**: the ground-truth oracle, the results row, and the
two-phase run harness. Everything measured for the rest of the project is measured through what P1 freezes here.

The reason this comes before analytics, representations and models is blunt: a coding agent will happily produce a
plausible-but-wrong analysis engine, and the only defence is an oracle and a results logger that already exist and
can catch it. This project studies agent-induced failure; do not let an agent-induced failure produce its results.

If P1 lands properly, the results are a matter of plotting. If it does not, later weeks are spent re-running
experiments.

## What P1 must deliver

| # | Deliverable | Why it is load-bearing |
| --- | --- | --- |
| 1 | **Results row contract** (`contracts/results-row.md`) | Every reported number is a field in this row. Adding a field later means re-running everything that came before. |
| 2 | **Ledger integrity contract** (`contracts/ledger-integrity.md`) | The slot lives in `PGDATA` and rewinds on T1/T2; the host ledger does not. Without an idempotency assertion the evidence store is hopefully-clean rather than provably-clean. |
| 3 | **Ground-truth oracle** | The objective optimum. Without it, success is a 4-point scale scored by hand, which is subjective. |
| 4 | **Two-phase harness** (`generate-incident` / `evaluate-arm`) | Makes the ablation valid: one incident, many arms, byte-identical evidence. |
| 5 | **Null run** | End-to-end proof with stub analysis, so the instrument is verified before anything is plugged into it. |
| 6 | **Re-measured cycle time** | Replaces an open-ended sample target with a measured, stratified sample-size plan. |

## Target environment

Unchanged and confirmed by the P0/P0.1 builds:

- Host `r740core`, Ubuntu 26.04 LTS, kernel 7.0.0-29-generic, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, same OS, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- Deploy root `/home/mlasota/thesis`. Config `etc/lab.env`.
- `bin/lab-verify` reports **TIER M 9/9 · TIER A 9/9 · TOTAL 18/18**, exit 0.

## A correction to the P0.1 handoff

`docs/P0.1-architecture-handoff.md` ends with:

> "P1 must not build: ground-truth oracle, results row schema, analytics, ranking, representations, model harness,
> restore verification, scenario damage logic."

The first two items are wrong — they are carried over from P0's anti-goals list. **The ground-truth oracle and the
results row schema are precisely what P1 exists to build.** The rest of that sentence stands. Task W001 corrects the
handoff so a future agent is not misled.

## Install

```bash
# on r740core, as mlasota
cd /home/mlasota/thesis
# unpack this package so that it merges into ./sdd
ls sdd/specs/P1-ground-truth-harness/tasks.md   # sanity check
```

## Execute

One task per invocation, in order, dry run first. **Do not batch.** Batching lets the agent optimise across task
boundaries, collapse the contracts, and leaves you unable to tell which layer broke.

```bash
cd /home/mlasota/thesis

# read-only dry run, changes nothing
<executor> --print "$(cat sdd/prompts/execute-P1.md)

TASK_TO_EXECUTE: W001
MODE: DRY_RUN"

# then for real
<executor> --force "$(cat sdd/prompts/execute-P1.md)

TASK_TO_EXECUTE: W001
MODE: EXECUTE"
```

Order: `W001 → W002 → W003 → W004 → W005 → W006 → W007 → W008 → W009 → W010`.
`W006` and `W007` may run in parallel with each other. `W010` is the gate and runs last.

## What you review after each task

Open `sdd/specs/P1-ground-truth-harness/work-instructions/WI-Wnnn.md`, read its *Review bundle* and *Operator review
checklist*, then check `/home/mlasota/thesis/logs/review/Wnnn/` exists and its `acceptance.md` rows are
**tier-labelled** per Article XIII. Tick the row in `sdd/specs/P1-ground-truth-harness/checklist.md` yourself — the
agent does not own the `Reviewed` column.

The two tasks worth reading line by line are **W002** (the results row contract, because it is expensive to change
later) and **W005** (the oracle, because every downstream number is scored against it).

## Layout added by this package

```
sdd/
  README-P1.md
  prompts/execute-P1.md
  specs/P1-ground-truth-harness/
    spec.md
    plan.md
    tasks.md
    checklist.md
    contracts/results-row.md          <- new frozen contract
    contracts/ledger-integrity.md     <- new frozen contract
    work-instructions/WI-W001..WI-W010.md
```

## Anti-goals for P1

Do not build, in P1: derived analytics, the ranking function, the naive comparator's tuning, representations
(R0/R1/R2), the model harness, real restore verification beyond the loop-closing stub, or the scenario damage logic
for SC-02/03/04. P1 implements **SC-01's** injection only, and only as far as is needed to generate a real incident
for the oracle to score. If a task appears to require one of the above, it has been misread.
