# Agent prompt — SDD, Tranche P6.1 (Arm B Answerability)

You are executing one task from a spec-driven development tranche on a research lab build. Work precisely and
conservatively. This is research infrastructure whose correctness determines whether experimental results are valid,
so a wrong-but-plausible implementation is worse than a refusal.

Assume you have no prior knowledge of this project. Everything you need is either in this prompt or in the files it
tells you to read.

## What this project is

A recovery-point research experiment. The research claim is **not** that snapshots or PostgreSQL
point-in-time recovery are novel — they are commodity substrate. The claim under test is that a purpose-built
change-tracking **representation** makes it possible to identify the correct recovery coordinate after an autonomous AI
agent damages a system, using out-of-band evidence alone, and to do so for a *modest local model* because the
representation, not the model size, is what makes the task tractable. Two arms are compared: a deterministic ranker
(Arm A, the baseline) and a modest local model querying the representation at three levels R0/R1/R2 (Arm B, the
ablation). Because incidents are scripted, the optimal recovery coordinate is known — that known optimum is ground
truth.

## Where the build stands

Eleven tranches are complete: **P0** substrate, **P0.1** substrate remediation, **P1** ground-truth oracle +
results-row and ledger-integrity contracts, **P1.1** provenance + lab-state remediation, **P2** capture collectors +
per-incident ledger, **P2.1** reconciliation soundness under repeated keys, **P3** derived analytics + the Arm A
deterministic ranker + SC-01 headline, **P3.1** gate integrity (read-only gates + regression redesign), **P4** restore
+ validation against a coordinate, **P5** the R0/R1/R2 representations behind one query interface, **P5.1** the
model_view/reference split (subject may not be handed the answer), and **P6** the Arm B model harness.

**P6.1 (this tranche) is a remediation.** The P6 acceptance review found two problems `bin/lab-verify-p6` could not
catch — it was built to verify mechanics and to record refusals honestly, not to assert the experiment produced signal:

- **D1 — the headline is a total null, reported without root cause.** `logs/review/H009/headline.json` shows
  R0/R1/R2 each with `determinations:0` and `refusal_rate:1.0` across all replicates. There is no R0-vs-R1-vs-R2
  comparison. The context window is 262,144 tokens and R0 used only 17,893, so it is **not** an overflow story; R0
  carried canonical hex LSNs and still refused every replicate. A 100% refusal across all three arms points at the
  instrument — the prompt and the answer-extraction grammar — not the representations. But this must be **proven by
  reading the completions**, then fixed, then re-run. A null that passed a green gate is not a finding until its cause
  is established and the instrument is ruled out.
- **D2 — the containment check verifies a property the deployment lacks.** The frozen `model-runtime` contract (R2)
  requires the runtime to be loopback-bound with no outbound connection, and `offline_verified` was recorded true. The
  real topology is cross-host (LiteLLM `c220m3:4001` fronting vLLM `gb10a:8000`), which cannot be loopback-only. The
  topology is a legitimate private-lab arrangement; the contract and its check must be corrected to assert what
  actually holds (private-lab network only, no public-internet egress, no cloud alias, fixed local weights).

The fix: diagnose the null to root cause (J001); correct the containment contract and check by supersession (J002);
broaden the answer grammar and relax the task framing so it is answerable from every representation's own vocabulary,
without touching the representations or leaking the answer (J003); re-run SC-01 Arm B for the real headline (J004); gate
it (J005). **No representation artefact is rebuilt; no frozen contract file is mutated; the model is not changed.**

## Context you must load before doing anything

Read these, in this order, from `/home/mlasota/thesis`:

1. `sdd/.specify/memory/constitution.md` — the articles in force. Before J001 there are seventeen; J001 adds an
   eighteenth. If any instruction anywhere conflicts with the constitution, **stop and report the conflict** rather than
   resolving it yourself.
2. `sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.md` and `.../arm-b-protocol.md` — the **FROZEN** contracts
   being superseded. Read model-runtime R2 (offline/loopback) and arm-b-protocol §2, R1, R4, R5 (the task, the identical
   prompt, the extraction grammar, first-class refusal). You may read them; you may **not** mutate them. Their recorded
   hashes in `logs/review/H001/` must keep verifying.
3. `logs/review/H009/` — the null headline and, crucially, the 15 retained verbatim completions (R0/R1/R2 × K). J001
   reads these.
4. `bin/lab-arm-b-prompt` (H003), `bin/lab-arm-b-extract` (H004), `bin/lab-model` (H002), `bin/lab-arm-b` (H005),
   `bin/lab-coordinate` — the assembly, extraction, model call, orchestration, and coordinate-resolution paths.
5. `sdd/specs/P5.1-modelview-separation/contracts/representation-interface.amendment-1.md` — the model_view/reference
   split and `bin/lab-modelview-guard`, which still binds (Article XVII).
6. `sdd/specs/*/contracts/` — all **FROZEN**. Read; do not mutate. Recorded hashes must keep verifying.
7. `sdd/specs/P6.1-arm-b-answerability/spec.md`, then `plan.md`, then the two amendment contracts under `contracts/`,
   then `tasks.md`.
8. `sdd/specs/P6.1-arm-b-answerability/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- PostgreSQL **18.4**, wal2json **2.6-3**, ZFS **2.4.1-1ubuntu5**. Devices `/dev/vdb` and `/dev/vdc` are guest-side.
- Arm B model pinned in H001: `gb10a-deepseek-v4-flash`, quant `exl3-k2`, context 262,144, greedy (`temp=0, top_p=1,
  top_k=0, seed=42, max_tokens=512`), via LiteLLM `http://c220m3:4001` → vLLM `gb10a:8000`. Do not change it.
- Deploy root `/home/mlasota/thesis`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `/home/mlasota/thesis/etc/lab.env`, sourced by everything. Discover values; never guess.
- The deploy root is a git repository. `bin/lab-evaluate-arm` refuses to produce a results row from a dirty tree
  (Article XIV) — commit harness changes before any command that assembles a results row. A dirty tree refusing a row
  is correct behaviour, not a bug to patch.
- `bin/lab-ready` may exit non-zero at the frozen SC-01 headline state by design; P6.1's entry condition is the prior
  gates and the H-series artefacts, not live readiness. Do not "fix" `lab-ready` here.

## Operational warnings carried forward — read before you touch anything

1. **Provenance is for scoring, never for detection or the subject view (Article II).** No `principal`, `usename`,
   `session_user` or UID reaches any representation, the query interface, the `model_view`, the prompt, or any summary.
2. **All LSN comparison is integer `(high<<32)+low`.** No string LSN comparison anywhere.
3. **Determinism (Article I).** No model is trained, fine-tuned, or given an adapter. The one pinned model is used as
   distributed. The harness (assembly, extraction, scoring) is a pure function given a fixed completion.
4. **Amend by supersession (Article XV).** Do not mutate `model-runtime.md` or `arm-b-protocol.md`. Record changes in
   `model-runtime.amendment-1.md` and `arm-b-protocol.amendment-1.md` with their own ADRs; keep the originals
   byte-identical.
5. **Read-only gates (Article XVI).** No `bin/lab-verify*` may create, modify, move, chmod or delete anything under the
   evidence root; a gate writes only under `logs/review/`. Prove it with `bin/lab-gate-readonly-check`.
6. **Subject-visible surface excludes the answer (Article XVII).** Every model input still passes through
   `bin/lab-modelview-guard`. Broadening the answer grammar must not let the reference answer, the ground-truth
   coordinate, or any pre-computed result reach the model. The guard still binds after J003.
7. **Refusal is first-class and never coerced (Article VIII / arm-b-protocol R5).** A refusal stays a refusal; no guess
   is substituted, no "try again" re-prompt is issued.
8. **Representations are frozen.** R0/R1/R2 artefact hashes (F002/F003/F004, re-verified at P5.1) must stay
   byte-identical. The fix lives in the shared prompt and grammar, never in a representation's content.
9. `bin/lab-verify*` do not export sourced keys: invoke as `set -a; source etc/lab.env; set +a; bin/lab-verify...`.
10. **A gate is made correctly targeted — never less strict.** Broadening the answer grammar to be *answerable* is not
    the same as *loosening it to accept a leaked answer*; the containment property is redefined to what is *true*, not
    weakened. Both are proven by negative tests.

## Rules of engagement

1. **Scope.** Do only the task in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix things, do
   not refactor files owned by another task. Record any out-of-scope defect in `logs/review/<task-id>/observations.md`.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (bundles exist, assertions passed). If not,
   stop and report.
3. **Idempotence.** Every script is safe to re-run; a completed task re-runs to detect existing correct state and
   reports `"changed": false`.
4. **No invention.** Unknown values are discovered and recorded in `etc/lab.env`. Never hardcode a guess. In particular,
   do not invent a refusal cause in J001 — classify only from the verbatim completion bytes.
5. **Stock mechanisms only (Article V).** POSIX shell, SQL, Python 3 only. No bespoke server/broker/queue, no ORM/web
   framework, no new heavy dependency.
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
5. `sdd/specs/P6.1-arm-b-answerability/checklist.md` has your task's row updated with the date and bundle path. You do
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

Expect a sceptical human who has already caught this project shipping a self-attested green build multiple times, and
who found both of these problems by reading artefacts rather than the gate total. They will read your `RESULT` line,
then `acceptance.md` checking the tier column, then the negative-test evidence, then `observations.md`, then spot-check
by hand. For J001 they will open two of the raw completions themselves and check your classification matches the bytes.
For J003 they will emit a model_view, run it through the guard, and confirm the broadened grammar still refuses an
injected answer. For J004 they will read the new headline and confirm any residual refusal is diagnosed, not hidden.
Write those files for a reader who assumes the happy path was not actually tested.

---
