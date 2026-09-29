# SDD Package, Tranche P3.1 (Gate Integrity: Read-Only Verification & Regression Redesign)

Same format as P0, P0.1, P1, P1.1, P2, P2.1 and P3: **GitHub Spec Kit** layout, extended with a
`work-instructions/` tier below `tasks.md` that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `<repo>/sdd`. Nothing under any prior `specs/*/`
directory is edited, and no frozen contract changes. This tranche repairs two gate-integrity defects found in
the P3 acceptance review, and closes the class behind them with a new constitutional article.

## Why this tranche exists

P3 delivered the analytics and the Arm A ranker, and its SC-01 headline is a genuine, oracle-scored win
(0 vs 200 damaged rows retained). But `bin/lab-verify-p3` closed at **17/19**, and the review found that the two
red criteria are not a defect in the P3 work — they are a flaw in how the regression gate was designed, plus a
read-only-violation class the earlier gates share:

1. **Verification gates mutate the evidence they check.** `bin/lab-verify-p1.1` crashed with `PermissionError`
   writing the frozen `db.jsonl` (mode 0444), and `bin/lab-verify-p2` (AC-P2-17) copies a frozen `db.jsonl` onto
   the **current** evidence tree. A gate that writes to the evidence it inspects can corrupt the very artefact a
   later gate certifies, and can pass or fail for reasons unrelated to the code under test. The P2 review already
   flagged this pattern once (AC-P2-17); it has now bitten twice.

2. **The nested regression is structurally impossible to pass green.** `AC-P3-18` (and the chained `AC-P2-17`,
   `AC-P2.1-13`) re-run the *live-state* prior gates against the **frozen** SC-01 headline incident. But the
   headline ledger must be frozen — consumer stopped — to hold a stable state for scoring, while `bin/lab-verify`
   (P0) *requires* a live capture state (consumer active, slot draining, retained WAL below threshold). Those two
   conditions are mutually exclusive, so the nested re-run is **guaranteed red for state reasons, not code
   reasons**. The regression intent is valid; the implementation (point `archive/current` at the frozen headline
   and re-run live-state gates) is wrong.

Neither is fraud — the agent refused to rebuild P1 to fake green, backed up and restored the frozen ledger when a
nested gate began appending to it, and reported the caveat plainly. That honest 17/19 is preferable to a gamed
19/19. But a compromised regression signal is the one thing that could let a later real defect through, so it must
be repaired before P4 leans on it.

## What P3.1 delivers

| # | Deliverable | Closes |
| --- | --- | --- |
| 1 | New **Article XVI** — verification gates are strictly read-only over evidence | The read-only-violation class |
| 2 | **ADR-P3.1-1** recording both defects; **ADR-P3.1-2** the regression-fixture design; **ADR-P3.1-3** the read-only enforcement mechanism | The governance + design |
| 3 | Every `bin/lab-verify*` made strictly read-only over evidence, enforced by a read-only-mount assertion harness; the two known write paths (`lab-verify-p1.1` PermissionError, `lab-verify-p2` AC-P2-17 copy-onto-current) removed | Defect 1 |
| 4 | A **pinned healthy regression fixture** per prior tranche, and a redesigned regression that runs each prior gate against its own fixture; the against-headline check narrowed to read-only contract-hash + code-level assertions | Defect 2 |
| 5 | `bin/lab-verify-p3.1` gate; `bin/lab-verify-p3` re-derived to an honest green under the redesign; all prior gates green against fixtures; acceptance memo recording P3 accepted only after P3.1 | All |

## Target environment

Unchanged and confirmed by the P0..P3 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- Deploy root `<repo>`. Config `etc/lab.env`.
- Gates today: `bin/lab-verify` 18/18, `-p1` 24/24, `-p1.1` 16/16, `-p2` 18/18, `-p2.1` 16/16, `-p3` 17/19.
- `bin/lab-ready` exits 0.

## Install

```bash
# on r740core, as mlasota
cd <repo>
# unpack this package so that it merges into ./sdd
ls sdd/specs/P3.1-gate-integrity/tasks.md   # sanity check
```

## Execute

One task per invocation, in order, dry run first. **Do not batch.**

```bash
cd <repo>

# read-only dry run, changes nothing
<executor> --print "$(cat sdd/prompts/execute-P3.1.md)

TASK_TO_EXECUTE: Z001
MODE: DRY_RUN"

# then for real
<executor> --force "$(cat sdd/prompts/execute-P3.1.md)

TASK_TO_EXECUTE: Z001
MODE: EXECUTE"
```

Order: `Z001 -> Z002 -> Z003 -> Z004`. `Z004` is the gate and runs last.

## What you review after each task

Open `sdd/specs/P3.1-gate-integrity/work-instructions/WI-Znnn.md`, read its *Review bundle* and *Operator review
checklist*, then check `<repo>/logs/review/Znnn/` exists and its `acceptance.md` rows are
**tier-labelled** per Article XIII. Tick the row in `checklist.md` yourself — the agent does not own the
`Reviewed` column.

The task worth reading line by line is **Z003**, because it decides what "prior code still works" means from now
on: it either produces a regression signal that is meaningful *and* achievable, or it does not.

## Scale note

This tranche is three substantive tasks (Z001 governance, Z002 read-only enforcement + the two write-path fixes,
Z003 the regression redesign) plus the standard gate (Z004), matching the shape of the P0.1, P1.1 and P2.1
remediations.

## Anti-goals

Do not, in P3.1: change any frozen contract; add a field to the results row, ledger-integrity, candidate or
arm-coordinate contracts; build any restore, representation, retrieval interface or model call (P4+); re-fit the
Arm A ranker or the naive comparator, or re-run the SC-01 headline to change its numbers; read `principal` in any
detection, mapping or ranking path; make a gate pass by weakening what it checks. A gate must become *read-only and
correctly targeted*, never *less strict*. If a task appears to require one of these, it has been misread.
