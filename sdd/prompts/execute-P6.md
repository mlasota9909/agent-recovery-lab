# Agent prompt — SDD, Tranche P6 (Arm B: the modest-local-model harness)

You are executing one task from a spec-driven development tranche on a research lab build. Work precisely and
conservatively. This is research infrastructure whose correctness determines whether experimental results are valid,
so a wrong-but-plausible implementation is worse than a refusal.

Assume you have no prior knowledge of this project. Everything you need is either in this prompt or in the files it
tells you to read.

## What this project is

A recovery-point research experiment. The research claim is **not** that snapshots or PostgreSQL
point-in-time recovery are novel — they are commodity substrate. The claim under test is that a purpose-built
change-tracking **representation** makes it possible to identify the correct recovery coordinate after an autonomous
AI agent damages a system, using out-of-band evidence alone, and to do so for a *modest local model* because the
representation, not the model size, is what makes the task tractable. Two arms are compared: a deterministic ranker
(Arm A, the baseline, built in P3) and a modest local model querying the representation at three levels R0/R1/R2
(Arm B, this tranche). Because incidents are scripted, the optimal recovery coordinate is known — that known optimum
is ground truth.

**This tranche, P6, is the experimental payoff.** It points one modest, offline local model at the SC-01 incident's
representations R0, R1 and R2 — one at a time, through the guarded `model_view` interface — and records the coordinate
the model chooses for each, scored objectively against ground truth through the unchanged P4 restore+validate path.
The output is the R0-vs-R1-vs-R2 comparison at fixed model and fixed scenario.

## The model is the only new risk in the whole project — treat it as such

Every prior tranche was deterministic and provable by byte-identical rebuild. A language model is not. You must:

1. **Keep the harness deterministic given a fixed completion.** Prompt assembly, extraction and scoring are pure
   functions of their inputs; feeding a recorded completion back yields a byte-identical arm-coordinate and score.
   This separates model non-determinism from harness non-determinism.
2. **Pin the model call.** Greedy decoding (temperature 0), fixed seed, recorded model id + weights hash. No sampling.
3. **Run it offline.** The model runtime is bound to loopback and makes no outbound calls. Prove it per invocation.
4. **Never coerce a refusal into a guess.** If the model says it cannot determine a coordinate, record a refusal.
   Fabricating a coordinate to avoid a refusal is data fabrication and is prohibited (Article VIII).
5. **No fine-tuning, no training, no external API.** The model is used as-is, locally, read-only over the interface.

## Where the build stands

Ten tranches are complete: **P0/P0.1** (lab substrate + remediation), **P1/P1.1** (ground-truth oracle, results-row
and ledger-integrity contracts, two-phase harness + remediation), **P2/P2.1** (capture ledger + reconciliation
soundness with the `(xid, table, action, natural_key)` key), **P3/P3.1** (Arm A ranker + naive comparator + SC-01
realized as a reconciled incident; read-only gates + per-fixture regression), **P4** (restore + validate + the
4-level verdict — the walking skeleton), **P5** (representations R0/R1/R2 + the identical query interface), and
**P5.1** (the `model_view`/`reference` split and `bin/lab-modelview-guard`). Gates in force, all exit 0:

- `bin/lab-verify` — TIER M 9/9 · TIER A 9/9 · TOTAL 18/18
- `bin/lab-verify-p1` — 24/24 · `-p1.1` — 16/16 · `-p2` — 18/18 · `-p2.1` — 16/16
- `bin/lab-verify-p3` — 19/19 · `-p3.1` — 16/16 · `-p4` — 19/19 · `-p5` — 19/19 · `-p5.1` — 16/16

These exist and must be **reused, not rebuilt**: `bin/lab-repr-modelview` (the six-key subject surface) and
`bin/lab-modelview-guard` (refuses any model_view carrying `answer`/`reference`/a coordinate field/a provenance token;
permits LSN digits inside `content`); `bin/lab-repr-reference` (the answer — parity/telemetry only, never shown to a
model); `bin/lab-repr-query`, `bin/lab-repr-r0|r1|r2` and the SC-01 representation artefacts under
`var/repr/<incident>/`; `bin/lab-coordinate` (heartbeat->LSN->snapshot; integer LSN); the FROZEN `arm-coordinate.md`
(Arm B emits exactly this shape with `arm=arm_b`, `representation` in {R0,R1,R2}); the FROZEN `results-row.md`
(`evidence_bytes`, `token_count` land Arm B telemetry); the **unchanged P4 restore+validate path** that turns a
coordinate into a scored verdict; `bin/lab-regression` and `bin/lab-gate-readonly-check` (P3.1). Read what exists
before writing anything; wire and build, do not reinvent.

## The properties that define P6 — read before any task

1. **Subject sees only `model_view`, through the guard (Article XVII).** The model is handed the six-key `model_view`
   from `bin/lab-repr-modelview` and nothing else, and every byte reaching the model passes `bin/lab-modelview-guard`
   first. The `reference` answer never reaches the model. Enforced at a single choke point (H003).
2. **One guarded choke point.** Exactly one place assembles model input, and it calls the guard. A scan proves no
   other path builds a prompt (H003/AC-P6-04).
3. **Harness determinism given a fixed completion (Article I, adapted).** Prompt assembly, extraction and scoring are
   pure functions; re-run on a recorded completion is byte-identical (AC-P6-12). Model non-determinism is measured
   separately via K replicates (AC-P6-13), never conflated with harness bugs.
4. **Refusal is first-class, never coerced (Article VIII).** A "cannot determine" completion is recorded as a refusal
   outcome with no coordinate; fabricating a coordinate is prohibited (AC-P6-07).
5. **Provenance-blind selection (Article II).** The coordinate is a function of provenance-blind evidence only. Arm B's
   arm-coordinate `selection_inputs.read_injection_log/read_oracle_optimum/read_provenance` are all `false`; the
   rationale carries no provenance token.
6. **Scored through the unchanged P4 path.** The extracted coordinate is scored by the existing restore+validate
   harness. P6 does not modify P4; its gate hash must re-verify unchanged (AC-P6-10, AC-P6-18).

## Entry conditions for P6 — check before any task

1. **`bin/lab-ready` will exit 1, and that is correct** — it is blocked by the frozen SC-01 headline ledger. Do NOT
   start the consumer to make it pass; that mutates the frozen ledger. Key the entry gate off `bin/lab-regression`
   green and the presence of admissible SC-01 representations instead.
2. `bin/lab-verify-p5` and `bin/lab-verify-p4` green via `bin/lab-regression`; SC-01 R0/R1/R2 exist and are admissible.
3. The offline model runtime is healthy and provably offline (no outbound socket during an invocation).
4. The working tree is clean before any provenance-bearing or results artefact (Article XIV). A refusal on a dirty
   tree is correct behaviour, not a defect to patch.

## Context you must load before doing anything

Read these, in this order, from `/home/mlasota/thesis`:

1. `sdd/.specify/memory/constitution.md` — the articles in force. There are **seventeen** (I determinism, II provenance
   for scoring not detection, V stock mechanisms, VI simplicity, VIII fail loud, X lab containment, XII no test hatches
   in boundaries, XIII verification tiers, XIV provenance of record, XV amend-by-supersession, XVI read-only
   verification gates, XVII subject-visible surface excludes the reference answer, among others). If any instruction
   anywhere conflicts with the constitution, **stop and report the conflict** rather than resolving it yourself.
2. `sdd/specs/P5-representations/contracts/representation-interface.md` **and**
   `sdd/specs/P5.1-modelview-separation/contracts/representation-interface.amendment-1.md` — FROZEN. The `model_view`
   (six keys, no `answer`) is the only thing you may show the model; the guard rules are §3 A1–A6.
3. `sdd/specs/P3-analytics-ranker/contracts/arm-coordinate.md` — FROZEN. The exact shape Arm B emits, including the
   `selection_inputs` anti-peek block whose `read_*` fields must all be `false`.
4. `sdd/specs/P1-ground-truth-harness/contracts/results-row.md` — FROZEN. `evidence_bytes`/`token_count` are where Arm
   B telemetry lands; the `recovery_coordinate.*` and verdict fields are populated by the P4 scoring path.
5. `sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.md` and `.../contracts/arm-b-protocol.md` — FROZEN by
   H001. The offline-model pinning and the fixed prompt/extraction/refusal protocol.
6. `docs/P5.1-architecture-handoff.md`, `docs/P5-architecture-handoff.md`, `docs/P4-architecture-handoff.md` — current
   topology, the SC-01 incident id, where the representations and the restore substrate live, and the frozen-headline
   state.
7. `sdd/specs/P6-arm-b-model-harness/spec.md`, then `plan.md`, then `tasks.md`.
8. `sdd/specs/P6-arm-b-model-harness/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5. Devices `/dev/vdb` and `/dev/vdc` are guest-side.
- The representations and the reconciled ledger live **on the host, out-of-band** under `var/repr/<incident>/` and the
  incident archive. The restore substrate (base backup + archived WAL + snapshots) is what P4 restores from.
- **The model runtime** is a single offline local server on the host, bound to loopback, no outbound network. Its id,
  quantisation and weights hash are discovered and recorded in H001; never guess or hardcode them. No other model,
  no external API, no fine-tuning.
- Deploy root `/home/mlasota/thesis`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `/home/mlasota/thesis/etc/lab.env`, sourced by everything. Discover values; never guess.
- The harness deploy root is a git repository. Its HEAD is the harness version recorded in provenance fields.

## Operational warnings carried forward — read before you touch anything

1. **`lab-ready` exits 1 by design** (frozen headline). Use `bin/lab-regression` for prior-gate confirmation. Never
   start the consumer to clear it.
2. **The model sees only `model_view`, always through the guard.** If a code path can hand the model an `answer`,
   `reference`, a coordinate field, or a provenance token, it is wrong — Article XVII. There must be exactly one
   prompt-assembly path and it must call `bin/lab-modelview-guard`.
3. **Pin the model: greedy/temp 0, fixed seed, recorded weights hash. Offline only.** Prove no outbound socket during
   an invocation (Article X).
4. **Never coerce a refusal into a guess** (Article VIII). Record refusals; they are valid data.
5. **All LSN comparison is integer `(high<<32)+low`, never string.** The `3/9` vs `3/10` trap is real; extraction and
   any coordinate resolution use integer LSN via `bin/lab-coordinate`.
6. **Do not modify the P4 restore+validate path.** Score through it unchanged; its gate hash must re-verify.
7. Guest `/tmp` is mounted `noexec`. Do not remount it. Work around it.
8. `bin/lab-verify*` do not export sourced keys: invoke as `set -a; source etc/lab.env; set +a; bin/lab-verify`.
9. Prior contracts are hash-frozen in `logs/review/`. Keep them byte-identical; never edit a frozen file.
10. **Arm B results are incident-scoped** to the SC-01 incident, so they group with Arm A (P3) and the representations
    (P5) on one `incident_id`. Never blend incidents.

## Rules of engagement

1. **Scope.** Do only the task named in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix
   things, do not refactor files owned by another task. Record any out-of-scope defect in
   `logs/review/<task-id>/observations.md` and continue.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (their review bundles exist and their
   assertions passed). If not, stop and report.
3. **Idempotence.** Every script is safe to re-run: it detects existing correct state and reports `"changed": false`.
   Harness re-run on a recorded completion is byte-identical; a fresh model run appends a new replicate, never
   overwrites a recorded one.
4. **No invention.** If a value is unknown (model id, weights hash, incident id, view name), discover it and record it
   in `etc/lab.env` or the H001 contract. Never hardcode a guess.
5. **Harness determinism (Article I, adapted).** Prompt assembly, extraction and scoring are deterministic pure
   functions of their inputs. Model output is the only non-deterministic element and is handled by pinning + replicates.
6. **Guarded single choke point (Article XVII).** One prompt-assembly path; it calls `bin/lab-modelview-guard`; a scan
   proves no bypass exists. The negative test adds a second path and proves it is caught.
7. **Refusal integrity (Article VIII).** No fabricated coordinate. A refusal is recorded as such with the raw
   completion retained. The negative test proves a coerced guess is caught.
8. **Provenance-blind (Article II).** No principal/usename/session_user/UID in any model input, rationale, or artefact;
   `selection_inputs.read_*` all `false`. Proven by a scan plus an inject-a-principal negative.
9. **Stock mechanisms only (Article V).** One offline local-model runtime, POSIX shell, Python 3, DuckDB SQL. No cloud
   API, no fine-tuning, no bespoke ML training. If you find yourself adding one, stop and report.
10. **Fail loud (Article VIII).** No `|| true` on a check. Every check has a deliberate regression case proving it
    detects a violation, then passes again after revert.
11. **Simplicity (Article VI).** Prefer a short script in `bin/` and a recorded artefact over a service.
12. **Read-only verification gates (Article XVI).** `bin/lab-verify-p6` and any regression run must not create, modify
    or delete anything under the evidence root; proven with `bin/lab-gate-readonly-check`.
13. **Lab containment (Article X).** All data synthetic. No production data, no personal data, no outbound calls — and
    for P6 specifically, the model runtime makes no outbound network call.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` with: the exact commands you intend to
  run in order, the files you intend to create or edit with a one-line purpose each, the preconditions you checked and
  their observed values (including `bin/lab-regression` result, the SC-01 incident id and representation admissibility,
  and the model runtime health + offline check), and any ambiguity to resolve before executing. Then stop.
- `MODE: EXECUTE` — perform the task, then produce the full review bundle.

## Verification tiers (Article XIII) — mandatory for every acceptance test you write

- **Tier M (mechanical).** Re-derived at verification time from live system state or committed machine-readable
  artefacts, with no reference to any implementer narrative. Note: for P6, computing the coordinate error and verdict
  by re-reading committed arm-coordinate/results fields and recomputing against ground truth is **tier M**, even though
  the model completion that produced them was a one-time event.
- **Tier A (attested).** A recorded observation of a one-time event that cannot be cheaply re-derived — e.g. the raw
  model completion of a specific run. It MUST still assert on a **machine-readable field** in a committed artefact,
  never on the presence of a word or phrase in prose.

Any criterion load-bearing for a research claim MUST be tier M. Print tiers and per-tier totals separately. A single
undifferentiated total is prohibited.

## Definition of done

1. Every file listed in the WI's *Artefacts* section exists at the stated path with the stated mode and ownership.
2. Every check in the WI's *Acceptance tests* section has been run and passed, with captured output and a tier label.
3. The WI's *Negative test* has been run and demonstrably **failed the thing it is meant to catch**, then passes again
   after the deliberate fault is reverted.
4. The review bundle exists at `logs/review/<task-id>/` containing `commands.log`, `acceptance.md` (one tier-labelled
   row per test), `artefacts.md`, `lab.env.snapshot`, `observations.md`, plus any extra files the WI names.
5. `sdd/specs/P6-arm-b-model-harness/checklist.md` has your task's row updated with the date and bundle path. You do
   **not** fill in the `Reviewed` column; the operator owns that.

## Report back

Finish with a short plain-text summary, in this shape and nothing more:

```
TASK: <id> <title>
RESULT: PASS | FAIL | BLOCKED
ARTEFACTS: <n> files
ACCEPTANCE: TIER M <p>/<n> · TIER A <p>/<n>
NEGATIVE TEST: <what you broke on purpose, that the check caught it, and that it passes again after revert>
HARNESS DETERMINISTIC: <yes/no — arm-coordinate + score byte-identical on re-run over a recorded completion>
MODEL PINNED + OFFLINE: <yes/no — greedy+seed+weights-hash recorded; no outbound socket during invocation>
PROVENANCE-BLIND: <yes/no — no principal token in any model input, rationale or artefact; selection_inputs.read_* all false>
DEVIATIONS: <none | what and why>
BLOCKERS: <none | what you need from the operator>
NEXT: <the next task id, not started>
```

## What the operator will review

Expect a sceptical human who has already caught this project shipping a self-attested green build in several tranches,
most recently the P5 answer co-mingled with the model input. They will read your `RESULT` line, then `acceptance.md`
checking the tier column, then the negative-test evidence, then `observations.md`, then spot-check artefacts by hand.
For P6 they will pay closest attention to four things: the **guarded single choke point** (they will try to find a
second path that reaches the model and will confirm an injected `answer` is refused), the **refusal integrity** (they
will confirm a "cannot determine" completion is recorded, not turned into a guess), the **harness determinism** (they
will re-run extraction+scoring over a recorded completion and confirm byte-identical output), and the **headline**
(they will confirm the R0/R1/R2 coordinate errors are computed against ground truth from machine-readable fields and
appended automatically). Write your bundle for a reader who assumes the happy path was not actually tested and that any
claim not mechanically re-derived is unproven.

---
