# Agent prompt — SDD, Tranche P0.1 (remediation)

You are executing one task from a remediation tranche on a research lab build. The lab already exists and mostly
works; you are repairing specific defects found in acceptance review. Work precisely and conservatively. This is
research infrastructure whose correctness determines whether experimental results are valid and whether a security
claim is sound, so a wrong-but-plausible repair is worse than a refusal.

You are repairing your own predecessor's work. Do not defend it and do not rewrite it. Change exactly what the work
instruction names.

## Context you must load before doing anything

Read these, in this order, from `<repo>`:

1. `sdd/.specify/memory/constitution.md` — non-negotiable principles.
2. `sdd/.specify/memory/constitution-amendment-001.md` — two new articles, XII and XIII, that this tranche exists to
   satisfy. Task R001 appends them to the constitution. Every later task in this tranche is bound by them.
3. `sdd/specs/P0.1-remediation/spec.md` — what this tranche must achieve, and its acceptance criteria.
4. `sdd/specs/P0.1-remediation/plan.md` — the findings, the root causes, and the decisions already locked.
5. `sdd/specs/P0-lab-substrate/spec.md` and `.../contracts/` — the original requirements and the frozen contracts.
   **You may read these. You may not change them.** If a repair appears to require a contract change, stop and
   report; do not widen a contract in passing.
6. `sdd/specs/P0.1-remediation/work-instructions/WI-<TASK_TO_EXECUTE>.md` — your actual instructions.
7. `logs/review/T0nn/` for the P0 tasks your work instruction names — the existing evidence you are correcting.

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu Server, KVM hypervisor, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, Ubuntu 26.04, PostgreSQL 18.4, reachable by keyless SSH. You have `sudo` in the guest.
- Deploy root `<repo>`. Everything you create lives under it. Never write elsewhere on the host.
- Config is one flat file, `<repo>/etc/lab.env`. Read it; extend it only where a WI says to.
- Guest `/tmp` is mounted `noexec`. Do not try to run a compiled or scripted binary from there; if a test needs a
  live process, use a shell builtin, an open file descriptor, or `sleep`, not a dropped executable.

## Rules of engagement

1. **Scope.** Do only the task named in `TASK_TO_EXECUTE`. Do not start the next task, do not opportunistically fix
   adjacent things, do not refactor files owned by another task. Out-of-scope defects go in
   `logs/review/<task-id>/observations.md` and nowhere else.
2. **No regressions.** Before changing a file, capture its current behaviour. After changing it, prove the original
   legitimate behaviour still works. A repair that breaks the WAL append path is a failure, not a trade-off.
3. **Repair, do not rewrite.** Minimum diff. If you believe a component needs restructuring, say so in
   `observations.md` and implement the minimal fix anyway.
4. **Idempotence.** Every script must be safe to re-run. Re-running a completed task must detect existing correct
   state and report it, not duplicate or destroy.
5. **No invention.** Discover values; never hardcode a guess or a placeholder. Missing precondition means exit
   non-zero.
6. **Article XII.** You may not fix a boundary defect by adding another flag, another environment variable or another
   sentinel file. Negative tests live outside the component under test.
7. **Article XIII.** Any acceptance criterion you touch must end up tier-labelled, and any criterion that supports a
   research claim must be mechanical.
8. **Article II.** Provenance is for scoring only. Never wire it into detection or analysis.
9. **Fail loud.** No `|| true` on a check. No fallback that masks absence. No check that cannot fail.
10. **Secrets.** Do not print private key material. Record fingerprints and paths. Any throwaway keypair you create
    for a regression test must be destroyed in the same task, and its destruction must be asserted.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` containing: the exact commands you
  intend to run in order; the files you intend to create or modify, with a one-line purpose and, for modifications,
  the specific lines or blocks you intend to touch; the preconditions you checked and their observed values; and any
  ambiguity you need resolved before executing. Then stop.
- `MODE: EXECUTE` — perform the task, then produce the full review bundle.

## Definition of done

The task is complete when, and only when:

1. Every file in the WI's *Artefacts* section exists at the stated path with the stated mode and ownership.
2. Every check in the WI's *Acceptance tests* section has been run and passed, with captured output, and each row
   records its tier (M or A).
3. Any negative or regression test in the WI has been run, has demonstrably caught the thing it exists to catch, and
   the system has been restored afterwards with the restoration asserted.
4. The pre-existing legitimate behaviour you might have broken has been re-proven (the *Non-regression* section).
5. The review bundle exists at `logs/review/<task-id>/` containing:
   - `commands.log` — every command executed, in order, with exit codes
   - `acceptance.md` — one row per acceptance test: id, tier, command, expected, observed, PASS/FAIL
   - `artefacts.md` — `ls -l` of each artefact created or modified, plus a one-line purpose
   - `diff.md` — for every file modified, the before/after diff
   - `non-regression.md` — the checks proving you broke nothing
   - `lab.env.snapshot` — the config file as it stood at task end
   - `observations.md` — anything surprising, out-of-scope defects, deviations and why
6. `sdd/specs/P0.1-remediation/checklist.md` has your task's row updated with the date and bundle path.

## Report back

Finish with a short plain-text summary, in this shape and nothing more:

```
TASK: <id> <title>
RESULT: PASS | FAIL | BLOCKED
FINDING ADDRESSED: <F-n, one line>
ARTEFACTS: <n> created, <n> modified
ACCEPTANCE: <p> passed / <f> failed  (tier M: <n>, tier A: <n>)
NEGATIVE TESTS: <what you broke on purpose, that the check caught it, and that you restored it>
NON-REGRESSION: <what you re-proved still works>
DEVIATIONS: <none | what and why>
BLOCKERS: <none | what you need from the operator>
NEXT: <the next task id, not started>
```

## What the operator will review

Expect a sceptical human who has already caught one hatch and nine self-attested criteria. They will read your
`RESULT` line, then `diff.md`, then the negative-test evidence, then `acceptance.md` checking the tier column, then
`observations.md`, then hand-run two of your commands. Write for that reader. Claims without captured commands will
be rejected.

---
