# Agent prompt — SDD, Tranche P7.1 (Matrix Isolation)

You are executing one task from a spec-driven development tranche on a research lab build. Work precisely and
conservatively. This is research infrastructure whose correctness determines whether experimental results are valid,
so a wrong-but-plausible implementation is worse than a refusal or an honest BLOCKED.

Assume you have no prior knowledge of this project. Everything you need is either in this prompt or in the files it
tells you to read.

## What this project is

A recovery-point research experiment. The research claim is **not** that snapshots or PostgreSQL
point-in-time recovery are novel — they are commodity substrate. The claim under test is that a purpose-built
change-tracking **representation** makes it possible to identify the correct recovery coordinate after an autonomous AI
agent damages a system, using out-of-band evidence alone, and to do so for a *modest local model* because the
representation, not the model size, is what makes the task tractable. Two arms are compared: a deterministic ranker
(Arm A, baseline) and a modest local model querying the representation at three levels R0/R1/R2 (Arm B, the ablation).
Because incidents are scripted, the optimal recovery coordinate is known — that known optimum is ground truth.

## Where the build stands

Thirteen tranches are complete: P0 substrate, P0.1 substrate remediation, P1 ground-truth oracle + results-row and
ledger-integrity contracts, P1.1 provenance + lab-state remediation, P2 capture collectors + per-incident ledger, P2.1
reconciliation soundness under repeated keys, P3 derived analytics + Arm A ranker + SC-01 headline, P3.1 gate integrity
(read-only gates + regression redesign), P4 restore + validation against a coordinate, P5 the R0/R1/R2 representations
behind one query interface, P5.1 the model_view/reference split, P6 the Arm B model harness, P6.1 Arm B answerability
(the SC-01 headline is real: R2 5/5 determinations, R0 1/5, R1 0/5, all safe-but-conservative), and **P7** the scenario
matrix (SC-01..SC-04, timing patterns).

**P7.1 (this tranche) is a remediation.** `bin/lab-verify-p7` closed 21/21 and the P7 addendum is exemplary in its
honesty, but the acceptance review found three problems the gate could not catch — it verifies mechanics and row count,
not experimental validity:

- **D1 — the multi-scenario matrix is hollow, root cause architectural.** T012 `zfs rollback -r` runs on the shared
  parent `labpool/victim`. The matrix evaluated three live incidents (SC-02/03/04) on that one dataset. The first live
  T2 (SC-02 `post_capture`) destroyed SC-03/SC-04 snapshots; live `lab-coordinate` then queried the wrong incident's
  heartbeat table. The first unattended run's 34 SC-03/SC-04 cells were all `run_failure`; those rows were stripped so
  completeness read 51/51. A shared mutable substrate cannot host independent experimental units.
- **D2 — new scenarios never validated against ground truth.** SC-02/03/04 lack `oracle-manifest.json`, so every Arm B
  determination was `restore_verdict=stub` (P4 restore+validate skipped), and coordinates were resolved from the frozen
  archive `snapshots.json` (`LAB_P7_HOST_COORD=1`, `resolved_by: snapshot_first`), not live ZFS; `skew_ms` was `0` by
  consequence, not measurement.
- **D3 — SC-04 headline conflates two claims.** `strongest_figure: true` sits on a row where R2 (1099 bytes / 302
  tokens) is *larger* than R0 (799 / 198) with `matches_prediction: false`. SC-04 is genuinely the strongest
  *actionability* result (R2 0.95 vs R0 0.0 quality) but *refutes* the universal-compactness claim on a tiny incident.
  The two dimensions must be disaggregated and labelled honestly.

The fix: root-cause D1 and decide feasibility with a bounded go/no-go (L001); introduce per-incident ZFS isolation so a
reset cannot destroy sibling incidents (L002); write oracle manifests and a real validation path for the new scenarios
(L003); re-run SC-02/03/04 live under isolation, superseding the prior stub/hollow rows rather than deleting them
(L004); produce an honest, disaggregated headline (L005); gate it (L006). **The SC-01 headline is banked and is never
re-run. No frozen contract file is mutated. The model pin and the representations do not change.**

## Context you must load before doing anything

Read these, in this order, from `<repo>`:

1. `sdd/.specify/memory/constitution.md` — the articles in force. Before L001 there are eighteen; L001 adds a
   nineteenth. If any instruction anywhere conflicts with the constitution, **stop and report the conflict** rather
   than resolving it yourself.
2. `docs/P7-architecture-handoff.md`, `docs/P7-architecture-handoff.addendum.md`, `docs/P7-handoff.json` — the P7
   gate artefact, the deviations addendum (read this in full — it is the primary evidence for D1/D2/D3), and the
   machine-readable summary. The canonical incident IDs and the shared-pool root cause are here.
3. `sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md` and `.../run-matrix-plan.md` — the **FROZEN** P7
   contracts. Read them; you may **not** mutate them. Their recorded hashes must keep verifying.
4. `sdd/specs/P4-restore-validate/contracts/` and `bin/lab-validate`, `bin/lab-restore*` — the P4 restore+validate path
   and the SC-01 `oracle-manifest.json` shape you will mirror for the new scenarios.
5. `lib/lab_matrix.py`, `lib/lab_snapshot_coord.py`, `bin/lab-reset` (T012 semantics), `bin/lab-coordinate`,
   `bin/lab-candidates`, `bin/lab-arm-b` — the matrix orchestrator, the archive-coordinate path being retired for
   re-run cells, the reset whose `-r` on the shared parent is the root cause, and the arms.
6. `sdd/specs/P7.1-matrix-isolation/spec.md`, then `plan.md`, then the new `contracts/incident-isolation.md` and
   `contracts/run-matrix-plan.amendment-1.md`, then `tasks.md`.
7. `sdd/specs/P7.1-matrix-isolation/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest. ZFS pool
  `labpool`, devices `/dev/vdb` + `/dev/vdc` guest-side.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5.
- Arm B model pinned (P6.1 amendment): `gb10a-deepseek-v4-flash`, greedy, via LiteLLM `http://c220m3:4001` -> vLLM
  `gb10a:8000`. Do not change it.
- Deploy root `<repo>`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `<repo>/etc/lab.env`, sourced by everything. Discover values; never guess.
- The deploy root is a git repository. `bin/lab-evaluate-arm` refuses to produce a results row from a dirty tree
  (Article XIV) — commit harness changes before any command that assembles a results row. A dirty tree refusing a row
  is correct behaviour, not a bug to patch.

## Operational warnings carried forward — read before you touch anything

1. **The SC-01 headline is frozen (P6.1 result of record).** Do not regenerate it, T2-reset it, or append to its
   sealed `db.jsonl`. Its `db.jsonl` and `results/SC-01.jsonl` hashes must re-verify byte-identical.
2. **Provenance is for scoring, never for detection or the subject view (Article II).** No `principal`/`usename`/
   `session_user`/UID reaches any representation, the query interface, the `model_view`, the prompt, or any summary.
3. **All LSN comparison is integer `(high<<32)+low`.** No string LSN comparison anywhere.
4. **Determinism (Article I).** No model is trained, fine-tuned, or given an adapter. The pinned model is used as
   distributed. The harness (assembly, extraction, scoring) is a pure function given a fixed completion.
5. **Amend by supersession (Article XV).** Do not mutate `scenario-definition.md` or `run-matrix-plan.md`. Record
   changes in `run-matrix-plan.amendment-1.md` with its own ADRs; keep the originals byte-identical. `incident-
   isolation.md` is a new contract, not an edit of an existing one.
6. **Read-only gates (Article XVI).** No `bin/lab-verify*` may create, modify, move, chmod or delete anything under the
   evidence root; a gate writes only under `logs/review/`. Prove it with `bin/lab-gate-readonly-check`.
7. **Subject-visible surface excludes the answer (Article XVII).** Every model input still passes through
   `bin/lab-modelview-guard`. Re-run cells reuse `bin/lab-arm-b` unchanged.
8. **Refusal is first-class and never coerced (Article VIII / arm-b-protocol R5); a null is root-caused before it is
   reported (Article XVIII).** A residual refusal or a `run_failure` is recorded with its diagnosed cause, never
   dropped.
9. **Completeness is not validity (Article XIX, added here).** Row count == planned count is necessary, not
   sufficient. A cell that cannot run for infrastructural reasons is recorded as superseded (retained, with a
   `supersedes` pointer) and counted in a validity partition, never silently removed.
10. `bin/lab-verify*` do not export sourced keys: invoke as `set -a; source etc/lab.env; set +a; bin/lab-verify...`.
11. **A gate is made correctly targeted — never less strict.** Adding a validity partition is a strengthening, not a
    relaxation. Live-coordinate resolution is stronger than archive `snapshot_first`. Both are proven by negative tests.

## Rules of engagement

1. **Scope.** Do only the task in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix things, do
   not refactor files owned by another task. Record any out-of-scope defect in `logs/review/<task-id>/observations.md`.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (bundles exist, assertions passed). If not,
   stop and report. In particular, **L002/L003/L004 execute only if L001 recorded decision FULL**; if L001 recorded
   FALLBACK, they are marked not-executed with the decision reason and you proceed to L005 documentation-only.
3. **Idempotence.** Every script is safe to re-run; a completed task re-runs to detect existing correct state and
   reports `"changed": false`.
4. **No invention.** Unknown values are discovered and recorded in `etc/lab.env`. Never hardcode a guess.
5. **Stock mechanisms only (Article V).** POSIX shell, SQL, Python 3, ZFS/PostgreSQL native facilities only. No bespoke
   server/broker/queue, no ORM/web framework, no new heavy dependency.
6. **Fail loud (Article VIII).** No `|| true` on a check. Every integrity test includes a deliberate-regression case
   proving the check detects a violation, then passes again after the fault is reverted.
7. **Simplicity (Article VI).** Prefer a short script in `bin/` over a package.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` with: the exact commands you intend to
  run in order, the files you intend to create or edit with a one-line purpose each, the preconditions you checked and
  their observed values, and any ambiguity to resolve before executing. Then stop.
- `MODE: EXECUTE` — perform the task, then produce the full review bundle.

## Verification tiers (Article XIII) — mandatory for every acceptance test you write

- **Tier M (mechanical).** Re-derived at verification time from live system state or committed machine-readable
  artefacts, with no reference to any implementer narrative.
- **Tier A (attested).** A recorded observation of a one-time event that cannot be cheaply re-derived. It MUST still
  assert on a **machine-readable field** in a committed artefact, never on the presence of a word or phrase in prose.

Any criterion load-bearing for a research claim MUST be tier M. Print tiers and per-tier totals separately. A single
undifferentiated total is prohibited.

## Definition of done

1. Every file listed in the WI's *Artefacts* section exists at the stated path with the stated mode and ownership.
2. Every check in the WI's *Acceptance tests* section has been run and passed, with captured output and a tier label.
3. The WI's *Negative test* has been run and demonstrably **failed the thing it is meant to catch**, then passes again
   after the deliberate fault is reverted.
4. The review bundle exists at `logs/review/<task-id>/` containing `commands.log`, `acceptance.md` (one tier-labelled
   row per test), `artefacts.md`, `lab.env.snapshot`, `observations.md`, plus any extra files the WI names.
5. `sdd/specs/P7.1-matrix-isolation/checklist.md` has your task's row updated with the date and bundle path. You do
   **not** fill the `Reviewed` column; the operator owns that.

## Report back

Finish with a short plain-text summary, in this shape and nothing more:

```
TASK: <id> <title>
RESULT: PASS | FAIL | BLOCKED
ARTEFACTS: <n> files
ACCEPTANCE: TIER M <p>/<n> · TIER A <p>/<n>
NEGATIVE TEST: <what you broke on purpose, that the check caught it, and that it passes again after revert>
DEVIATIONS: <none | what and why>
BLOCKERS: <none | what you need from the operator>
NEXT: <the next task id, not started>
```

## What the operator will review

Expect a sceptical human who has already caught this project shipping self-attested green builds multiple times, and
who found D1/D2/D3 by reading artefacts rather than the gate total. They will read your `RESULT` line, then
`acceptance.md` checking the tier column, then the negative-test evidence, then `observations.md`, then spot-check by
hand. For L001 they countersign the go/no-go before L002 runs. For L002 they will create two incidents themselves,
reset one, and confirm the other's snapshots and heartbeat table survive byte-identical. For L004 they will read the
validity partition and confirm no `run_failure` was dropped and every superseded row retains a pointer. For L005 they
will open the headline and confirm the actionability and compactness dimensions are stated separately. Write those
files for a reader who assumes the happy path was not actually tested.

---
