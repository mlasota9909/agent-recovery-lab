# SDD Package, Tranche P6 (Arm B: the modest-local-model harness)

Same format as P0 through P5.1: **GitHub Spec Kit** layout, extended with a `work-instructions/` tier below `tasks.md`
that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `<repo>/sdd`. Nothing under any prior `specs/*/` directory is
edited, and every prior frozen contract — including `capture-completeness.md`, `representation-interface.md` and its
amendment-1 — stays byte-identical so its recorded hash keeps verifying.

## Why this tranche exists — this is the experimental payoff

P5 built the three representations and the identical query interface; P5.1 split the subject-visible `model_view`
(what a model may be shown) from the `reference` answer (kept only for parity/telemetry) and put a mechanical guard
between them. **P6 finally runs the experiment the whole build was for:** it points *one modest local model* at R0, R1
and R2 in turn, on the *same* SC-01 incident, and measures — objectively, against ground truth — how well the model
locates the recovery coordinate from each representation. The result is the R0-vs-R1-vs-R2 comparison at fixed model
and fixed scenario. That comparison is the research claim: the representation, not the model size, is what makes
recovery-point identification tractable for a small model.

The claim is emphatically **not** that the model is clever. It is that a purpose-built representation lets a modest,
offline model succeed on far less evidence. So P6 holds the model constant and varies only the representation — the
independent variable P5 isolated.

## The one genuinely new risk in this project: a stochastic subject

Every prior tranche was deterministic and provable by byte-identical rebuild. A language model is not. P6 handles this
head-on rather than pretending otherwise:

1. **The harness is deterministic *given a fixed completion*.** Prompt assembly, coordinate extraction and scoring are
   pure functions of (model_view, completion). Feed a recorded completion back in and you get a byte-identical
   arm-coordinate and score. This isolates *model* non-determinism from *harness* non-determinism (H004/H008/AC-P6-12).
2. **The model call is pinned.** Greedy decoding (temperature 0), a fixed seed, and the exact model id + weights hash
   are recorded, so the run is as reproducible as the runtime allows and fully declared (H002/AC-P6-02).
3. **Residual non-determinism is measured, not hidden.** K replicates per representation are run and their agreement
   reported — an honest characterisation of the stochastic subject (H009/AC-P6-13).
4. **A refusal is a first-class outcome.** The model may answer "I cannot determine a coordinate." That is recorded as
   a refusal and scored as such. It is **never** coerced into a guess (H005/AC-P6-07). Coercion would fabricate data.

## The two properties carried in from P5.1 that P6 must honour

1. **Subject sees only `model_view`, through the guard.** The model is handed the six-key `model_view` from
   `bin/lab-repr-modelview` and nothing else, and every byte that reaches the model passes `bin/lab-modelview-guard`
   first (Article XVII). The `reference` answer from `bin/lab-repr-reference` is for parity/telemetry only and never
   reaches the model.
2. **One guarded choke point.** There is exactly one place in the harness that assembles model input, and it calls the
   guard. A scan proves no other path builds a prompt (H003/AC-P6-04) — the P6 analogue of the P0.1 receiver's single
   accepted command.

## What P6 delivers

| # | Deliverable | Task |
| --- | --- | --- |
| 1 | Two frozen contracts: `model-runtime.md` (offline local model: id, weights hash, greedy+seed, localhost-only) and `arm-b-protocol.md` (fixed prompt, query protocol, extraction grammar, refusal grammar, replicate count K) | H001 |
| 2 | `bin/lab-model` — offline local-model invocation, pinned decoding, no outbound calls, real prompt/completion token counts + latency captured verbatim | H002 |
| 3 | `bin/lab-arm-b-prompt` — the single guarded prompt-assembly choke point, identical across R0/R1/R2 except `model_view.content` | H003 |
| 4 | `bin/lab-arm-b-extract` — deterministic coordinate extraction into the frozen arm-coordinate shape; unparseable/ambiguous -> refusal | H004 |
| 5 | `bin/lab-arm-b` — the refusal-aware run driver: model may decline, recorded as refusal, never coerced | H005 |
| 6 | Verbatim operator-facing explanation capture, provenance-blind, wired to `arm-coordinate.rationale` | H006 |
| 7 | Telemetry: real model prompt-token count + latency per run into the results row; distinct from P5's pinned estimate | H007 |
| 8 | Scoring wiring: extracted coordinate scored through the UNCHANGED P4 restore+validate path -> verdict + damage/legit rows | H008 |
| 9 | **Headline:** same SC-01, same model, R0/R1/R2, K replicates, objective error vs ground truth, all appended; the R0-vs-R1-vs-R2 table + discrimination negatives | H009 |
| 10 | `bin/lab-verify-p6` tiered read-only gate; prior hashes re-verified; regression; P6 handoff | H010 |

## Target environment

Unchanged and confirmed by the P0->P5.1 builds, plus the one addition P6 legitimately introduces:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- **New in P6:** one offline local-model runtime on the host, bound to loopback only, no outbound network. A modest
  model in the qwen family (the exact id, quantisation and weights hash are discovered and recorded in H001 — never
  hardcoded or guessed). No fine-tuning, no training, no external API. This is the only model in the entire project
  and it appears only here, as Arm B, read-only over `bin/lab-repr-modelview`.
- Deploy root `<repo>`. Config `etc/lab.env`.
- Gates green: `lab-verify` 18/18, `-p1` 24/24, `-p1.1` 16/16, `-p2` 18/18, `-p2.1` 16/16, `-p3` 19/19, `-p3.1` 16/16,
  `-p4` 19/19, `-p5` 19/19, `-p5.1` 16/16, all exit 0.
- **Seventeen** constitutional articles in force (through Article XVII, subject-visible surface excludes the reference
  answer).

## Entry conditions (do not skip)

1. **`bin/lab-ready` will exit 1** — this is expected and correct. It is blocked by the frozen SC-01 headline ledger
   (0444, consumer stopped) so that the reconciled incident P3/P4/P5 used stays byte-identical. P6 therefore keys its
   entry gate off **`bin/lab-regression` green** and the presence of the admissible SC-01 representations, **not** off
   live readiness. Do not start the consumer to make `lab-ready` pass — that would mutate the frozen ledger.
2. `bin/lab-verify-p5` and `bin/lab-verify-p4` must be green (via `bin/lab-regression` against their pinned fixtures),
   and the SC-01 representations R0/R1/R2 must exist and be admissible (P5 F006 manifests).
3. The offline model runtime must be healthy and **provably offline** (H002 checks this per invocation).
4. The git working tree must be clean before producing any provenance-bearing or results artefact (Article XIV).

## Run one task per invocation

```bash
cd <repo>
<executor> --print "$(cat sdd/prompts/execute-P6.md)

TASK_TO_EXECUTE: H001
MODE: DRY_RUN"
```

Review the dry-run bundle, then re-run with `MODE: EXECUTE`. Proceed `H001 -> H010`, one task per call. **Do not batch
tasks** — batching lets the agent optimise across boundaries and is how a green self-report hid a real defect in
earlier tranches (the P0.1 hatch, the P1 `harness_commit`, the P2 `xid` substitution, the P3 impossible-green
regression, the P5 answer co-mingled with the model input).
