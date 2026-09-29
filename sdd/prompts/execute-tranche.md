# Agent prompt — SDD, Tranche P0

You are executing one task from a spec-driven development tranche on a research lab build. Work precisely and
conservatively. This is research infrastructure whose correctness determines whether experimental results are valid,
so a wrong-but-plausible implementation is worse than a refusal.

## Context you must load before doing anything

Read these, in this order, from `<repo>`:

1. `sdd/.specify/memory/constitution.md` — non-negotiable principles. If an instruction anywhere conflicts with the
   constitution, stop and report the conflict instead of resolving it yourself.
2. `sdd/specs/P0-lab-substrate/spec.md` — what this tranche must achieve, and its acceptance criteria.
3. `sdd/specs/P0-lab-substrate/plan.md` — the architecture and the decisions already locked. Do not re-litigate them.
4. `sdd/specs/P0-lab-substrate/tasks.md` — the ordered task list, dependencies, and what each task owns.
5. `sdd/specs/P0-lab-substrate/contracts/` — frozen interfaces. You may read them; you may not change them.
6. `sdd/specs/P0-lab-substrate/work-instructions/WI-<TASK_TO_EXECUTE>.md` — your actual instructions.

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu Server, KVM hypervisor, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- Deploy root `<repo>`. Everything you create lives under it. Never write elsewhere on the host.
- `/dev/vdb` and `/dev/vdc` are expected to be disks **inside `thesisvm01`**. T001 proves or disproves this.
- Config is one flat file, `<repo>/etc/lab.env`, created by T001 and sourced by everything after.

## Rules of engagement

1. **Scope.** Do only the task named in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix
   things, do not refactor files owned by another task. If you find a defect outside your scope, record it in
   `logs/review/<task-id>/observations.md` and continue.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (their review bundles exist and their
   assertions passed). If not, stop and report.
3. **Idempotence.** Every script you write must be safe to re-run. Re-running a completed task must not destroy
   state or duplicate data; it should detect existing correct state and report it.
4. **No invention.** If a value is unknown (an IP, a version, a device path), discover it and record it in
   `etc/lab.env`. Never hardcode a guess, never substitute a placeholder, never assume a default that the WI did not
   state. Missing precondition means exit non-zero.
5. **Prohibitions.** Constitution Article V lists mechanisms that are banned outright. If you find yourself about to
   write a WAL parser, a filesystem event daemon, or `zfs send` plumbing, you have misread the task.
6. **Provenance.** Article II. Provenance exists for scoring only. Never wire it into detection or analysis.
7. **Fail loud.** No `|| true` on a check. No fallback that masks absence. No check that cannot fail.
8. **Secrets.** Do not print private keys. Record fingerprints and paths, not key material.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` containing: the exact commands you
  intend to run in order, the files you intend to create with a one-line purpose each, the preconditions you checked
  and their observed values, and any ambiguity you need resolved before executing. Then stop.
- `MODE: EXECUTE` — perform the task, then produce the full review bundle.

## Definition of done

The task is complete when, and only when, all of the following hold:

1. Every file listed in the WI's *Artefacts* section exists at the stated path with the stated mode and ownership.
2. Every check in the WI's *Acceptance tests* section has been run and passed, with captured output.
3. Any negative/regression test in the WI has been run and demonstrably FAILED the thing it is meant to catch,
   proving the check works.
4. The review bundle exists at `logs/review/<task-id>/` containing:
   - `commands.log` — every command executed, in order, with exit codes
   - `acceptance.md` — one row per acceptance test: id, command, expected, observed, PASS/FAIL
   - `artefacts.md` — `ls -l` of each artefact created, plus a one-line purpose
   - `lab.env.snapshot` — the config file as it stood at task end
   - `observations.md` — anything surprising, any out-of-scope defect, any deviation and why
5. `sdd/specs/P0-lab-substrate/checklist.md` has your task's row updated with the date and the bundle path.

## Report back

Finish with a short plain-text summary, in this shape and nothing more:

```
TASK: <id> <title>
RESULT: PASS | FAIL | BLOCKED
ARTEFACTS: <n> files
ACCEPTANCE: <p> passed / <f> failed
NEGATIVE TESTS: <what you broke on purpose, and that the check caught it>
DEVIATIONS: <none | what and why>
BLOCKERS: <none | what you need from the operator>
NEXT: <the next task id, not started>
```

## What the operator will review

Expect the human to read, in this order: your `RESULT` line, then `acceptance.md`, then the negative-test evidence,
then `observations.md`, then spot-check two artefacts by hand. Write those files for a sceptical reader who assumes
the happy path was not actually tested.

---
