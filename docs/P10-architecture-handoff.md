# P10 architecture handoff — Token-scaling of the recovery-point task

Date: 2026-09-24
Status: P10 executed in full (Q001–Q007). There is no P11.

## Execution against `sdd/prompts/execute-P10.md`

P10 was run from the tranche prompt `sdd/prompts/execute-P10.md`. Its seven tasks were
executed in order, each as `TASK_TO_EXECUTE: Q00N` / `MODE: EXECUTE`. Every task has an
invocation record, a review bundle and a checklist tick (`logs/review/Q00N/`).

- **Standing agreement.** The prompt's Article XX agreement was applied throughout:
  contradictions were resolved by precedence, with an ADR and a frozen amendment for each.
  Escalations were limited to the prompt's halt reasons (models offline; a destructive
  lab reset not performed).
- **Hard rules.** All five were met: sidecar-only and read-only prior artefacts;
  invariant recovery point; plan pre-registered before data; guarded, provenance- and
  answer-blind inputs; report whatever it shows.
- **Where to check it.** The clause-by-clause map is `logs/review/P10/execute-P10-compliance.md`,
  and the batched decisions are in `logs/review/P10/decision-log.md`.

## Result of record

P10 asked the question P9 left open: *if the raw change log already fits in the context
window, why compress it?* It answered by scaling. SC-01 was padded with synthetic
legitimate activity until the raw-evidence prompt (R0) grew from its natural 19 435 to
999 333 canonical tokens. The true recovery point and the damage were held fixed. Three
local models were asked the same question on R0 and on the compact graph-summary
representation (R2) at seven pre-registered sizes, K = 5 each: 210 cells in all.

Pre-registered result (plan frozen at 02:36:05Z, before any data; regenerates
byte-identically):

| hypothesis | result | what it says |
| --- | --- | --- |
| **H2** hard-limit divergence | **HOLDS** | At 500k and 1M, R0 was `infeasible_context` in 30/30 cells (it cannot be sent to any model); R2 was submittable in 30/30. |
| **H3** safety under scale | **HOLDS** | 0 `incorrect_corrupt` among 87 accepted recoveries. No chosen point retained damage. |
| **H1** within-window degradation | **NOT EVALUABLE** | At each model's largest within-window scale (S*), 0 R0 answers were accepted by the frozen P6.1 parser, for every model; DeepSeek's anchor also had none. |

Because H1 is existential over the three models and not evaluable, **no A4 interpretation
is selectable, and none is emitted** (plan amendment P4). This is reported as it is
(Article XXI.3).

**Why H1 could not be evaluated (Article XVIII root cause).** At scale the models name the
right event with several locators: `lsn=X ts=T`, or one LSN written in both hex and integer
form. The frozen P6.1 extractor requires every locator to resolve to *exactly* the same
LSN, and it resolves timestamps at heartbeat (~1 s) granularity. So these answers are
recorded as `refusal_parser`. P9 had the same pattern at natural size. It is an instrument
property and is not reported as a finding about the models.

**Exploratory, labelled, non-binding** (the rule was defined after seeing the data). 30 of
33 parser-rejected answers name one event that was in the prompt. Re-scored at that event:

| model | anchor | S* |
| --- | --- | --- |
| Gemma | 5/5 correct | 5/5 correct |
| Qwen | 5/5 correct | 5/5 correct |
| DeepSeek | 0/5 correct | 2/4 correct |

No model loses accuracy inside its window. That is the shape of A4 branch 2
("feasibility, not within-window accuracy"), but it cannot be claimed as the
pre-registered conclusion.

**The honest shape.** The two representations behave very differently as the incident
grows:

- **R0** grows ×51.4 and crosses each model's usable window (window − 8 192):
  - Gemma-4-26B at 100k (limit 92 160);
  - Qwen3.8-27B at 200k (188 416);
  - DeepSeek-V4-Flash at 500k (253 952).
- **R2** stays at 248 canonical tokens at every tested scale (308–396 model tokens). The
  frozen PB-6 interface shows three window summaries and a digit run is one canonical
  token. Nothing was special-cased.
- **Precision.** R2 answers are safe but conservative (Qwen and DeepSeek accept at every
  scale). Gemma declines R2 at every scale, as in P9.

## The sweep

`results/scaling-runs.jsonl` holds the frozen C5 keys; `results/scaling-runs-detail.jsonl`
holds diagnostics keyed by `scale_run_id`. The latest attempt per cell supersedes earlier
ones, and superseded rows are retained (Article XIX). All 210 planned cells are present;
the per-scale validity partition is in `logs/review/Q007/close-out-memo.md`.

| outcome | count |
| --- | --- |
| accepted | 87 |
| refusal_genuine | 35 |
| refusal_parser | 33 |
| infeasible_context | 55 |
| run_failure | 0 |

Supersessions, all retained:

- 140 Gemma/Qwen `run_failure` rows from while their hosts were offline. They were
  re-run after restoration and identity verification.
- 2 DeepSeek 100k cells lost to a dirty tree mid-sweep (my error). They were re-run.
- 4 Gemma R2 rows relabelled `refusal_parser` → `refusal_genuine` under C3. The recorded
  completions were reused, with no new model call.

**Containment.** All 157 model submissions were containment-verified: DeepSeek 62, Qwen
50, Gemma 45. There was no public egress, and every completion ended with
`finish_reason=stop`.

## How the incident was scaled (ADR-P10-6)

- **Held fixed.** SC-01's true recovery point (`1/E1000000`) and its damaging DELETE
  (xid 26870, 200 rows, from `1/E1000848`) are untouched.
- **What padding is.** Legitimate single-row INSERT/UPDATE transactions on `p2_probe`.
- **Where it goes.** Only where the captured WAL has physical room: the unused tail of
  each 16 MiB segment, 11 slots and 8.73 s of the 40 s window grid. Within a segment,
  real records are 48–160 bytes apart, and `lab-ledger-verify` demands unique, monotone,
  in-range commit LSNs.
- **Placement.** A seeded stream that sees only `(seed, n, slots)`.
- **Bookkeeping.** Each padded commit is recorded at the workload driver's next existing
  manifest checkpoint, the same coarse rule the driver applies to itself. No new
  `commit_lsn` value lands below the injection, so the oracle optimum is invariant **by
  construction**. It is re-checked on every emitted incident with the pure
  `lab_oracle.select_optimum`. The live `lab-coordinate` heartbeat table has drifted
  since P1, so it is not used for this check.
- **Byte preservation.** Every real ledger line stays byte-identical. P2/P2.1
  reconciliation rules C-1…C-7 and `lab-ledger-verify` pass at every scale.
- **Calibration.** The padding count is calibrated to the pre-registered R0 size within
  ±2%. The 10k target is the natural incident, because padding only adds.
- **Onset-blindness has a stated limit.** Placement and materialisation never see the
  onset. The count is calibrated through the frozen view, whose P3 anomaly baseline uses
  the declared injection start (as in P9). A decoy-onset control leaves placement
  byte-identical and moves the count by 2.0%.
- **Determinism.** Two rebuilds of all 7 targets are byte-identical (31 files each).
  Digests are in `runtime/p10-scaled-manifest.json`; the bulk padded incidents
  (`incidents/scaled/`) are gitignored and regenerable.
- **Known cues.** Padding is identifiable in principle (separate xid and row-id ranges).
  The damage's relative position in the R0 prompt moves from 3.7% to 14–16%, and the
  third visible window changes (14 → 10 → 3 → 5). Both are recorded per scale.

## How a cell is scored (ADR-P10-7, ADR-P10-8)

- **Feasibility.** The backend's own chat-aware `/tokenize` count plus the frozen 8 192
  completion budget, against the pinned window:

  | model | window |
  | --- | --- |
  | DeepSeek-V4-Flash | 262 144 |
  | Qwen3.8-27B | 196 608 |
  | Gemma-4-26B | 100 352 |

  Over-window cells are never sent. DeepSeek's and Gemma's counts reproduce P9's recorded
  `prompt_tokens` exactly. Qwen's messages-mode count is 42 tokens high; no cell lies
  within 21 000 tokens of its limit, so no outcome depends on it.
- **S\*.** Fixed per model by a pre-submission preflight: DeepSeek 250k, Qwen 100k,
  Gemma 50k. It is re-validated from the recorded counts and timing.
- **Verdict.** The unchanged P4 restore-validate on the frozen SC-01 archive for real
  rows, plus P4's own lost-row rule (`lab_validate` legit_vs_optimum) on padded manifest
  rows. Padding provably cannot change a verdict class; a guard flags it if it ever did.
- **Taxonomy (C3 with amendment A5).**
  - `accepted`
  - `refusal_genuine`: REFUSAL line(s), no coordinate offered
  - `refusal_parser`: offered locators rejected by the frozen P6.1 extractor
  - `infeasible_context`
  - `run_failure`: harness, containment or resolver fault, with its diagnosis

## Contradictions resolved (Article XX; each with an ADR and a frozen amendment)

| issue | resolution | record |
| --- | --- | --- |
| 10k anchor below the natural size | natural incident | ADR-P10-6, A1 |
| onset-blind interleaving vs fixed optimum vs physical LSN room | WAL-tail placement + driver-checkpoint bookkeeping | ADR-P10-6, A2 |
| live coordinate lookup has drifted | pure optimum comparison | A3 |
| physical P4 cannot see synthetic rows | P4 + P4's own rule on padded rows | ADR-P10-7, A4 |
| windows are not 262 144 for all models | per-model pinned windows + completion budget | ADR-P10-8, plan P1–P3 |
| H1 undefined cases, S*, multiple comparisons, taxonomy, scope, K, timing gate | H1 on conditional accuracy with a two-sample bootstrap; Bonferroni over 3 models | ADR-P10-9, plan P4–P10 |
| four frozen wrappers ignore `EVIDENCE_ROOT` and would write real evidence | in-process calls under a write guard | ADR-P10-10 |
| a destructive T2 reset between cells | not performed; ledger-idempotency guard asserted | A7 |

## Frozen contracts (`sdd/specs/P10-token-scaling/contracts/frozen-hashes.json`)

| file | SHA-256 |
| --- | --- |
| `scale-generator.md` (byte-identical to `thesis-sdd-P10.zip`) | `7758fd3a74aa506252f1f6dd9be12cb6cad9d176d223fb8a0f5f5c9eae45790c` |
| `scale-generator.amendment-1.md` | `8dac6439f6b5fff2e4f0bfd461af72fdfc975d1ceda838bc0695258a13a7f9a7` |
| `scaling-analysis-plan.md` (byte-identical to `thesis-sdd-P10.zip`) | `80e6ec7efd14241be0c6d5082417fc2d0a083534343ef86d8bf92bcc37b914e8` |
| `scaling-analysis-plan.amendment-1.md` | `c9f270c4172b2eb28af74b831b2e80e18bfc3cdc956e6cb6cd1504b74457c403` |

The analysis-plan digest `b4ddd9c7…` was pre-registered at 2026-09-24T02:36:05Z (freeze
commit `7d489c9`), before any `results/scaling-runs*` existed. `lab-prereg-check`,
`lab-p10-sweep`, `lab-p10-stats` and `lab-verify-p10` refuse to run on drift. The timing
gate fails closed: every row attempt must pair one timestamped detail record.

## Environment

- **Lab.** `etc/lab.env` SHA-256 `d702508b…` (unchanged since P9); PostgreSQL 18.4;
  ZFS 2.4.1.
- **Models** (restored and verified against the P9 pins: tokenizer fingerprint, served
  window, identity digest; DeepSeek weights sha256 `c5da6dd1…` re-hashed on gb10a):

  | alias | host | notes |
  | --- | --- | --- |
  | `gb10a-deepseek-v4-flash` | gb10a | swapped back from `qwen38-flash`; `qwen38-flash` container stopped, not removed; gateway alias re-added with a config backup |
  | `gympc-gemma4-26b` | gympc | |
  | `alienware-qwen38-27b` | alienware | |

- **Endpoint.** Loopback LiteLLM gateway (ADR-P9-2). Real backend URLs for token counting
  live only in the gitignored `var/model/p10-backends.json`.

## Read-only guarantee (Article XVI / AC-P10-12)

- **Baseline.** Captured at Q001 before anything was generated: 668 strict files
  (evidence root, prior results, P9 sweep, representations, banked analyses, all P0–P9
  contracts) plus the append-only P4 restore cache.
- **After P10.** The strict set is byte-identical. The only additions are new
  `var/restore/…/ab-<lsn>` cache entries. P9 `sweep-runs.jsonl` is unchanged
  (`7b9a33aa…`).

## New code

| tool | purpose |
| --- | --- |
| `bin/lab-scale-generate` (`lib/lab_p10_scale.py`) | Q002 deterministic padding + invariance check (`--check`) |
| `bin/lab-prereg-check` (`lib/lab_p10.py`) | Article XXI gate: plan digest + fail-closed timing join |
| `bin/lab-p10-sweep` (`lib/lab_p10_sweep.py`) | Q004 sweep: preflight/S*, feasibility, contained submission, hybrid scoring, `--retry-failures`, `--reclassify`, `--completeness`, `--identity`, `--measure-overhead` |
| `bin/lab-p10-stats` (`lib/lab_p10_stats.py`) | Q005 pre-registered analysis, figure, lint |
| `bin/lab-p10-explore` (`lib/lab_p10_explore.py`) | EXPLORATORY evidence-consistent re-scoring of parser refusals |
| `bin/lab-p10-negative` (`lib/lab_p10_negative.py`) | negative tests on scratch copies |
| `bin/lab-p10-regression` (`lib/lab_p10_regression.py`) | Q007 live prior-tranche regression (mutating; outside the gate) |
| `bin/lab-verify-p10` (`lib/lab_verify_p10.py`) | Q007 terminal gate (read-only; writes only `logs/review/Q007/`) |
| `lib/lab_p10_freeze.py` | Q001 freeze + pre-registration record |

## Terminal gate (Q007)

`bin/lab-verify-p10`: **TIER M 29/30 · TIER A 2/2 · TOTAL 31/32**. Every P10 acceptance
criterion AC-P10-01…12 passes mechanically, each with its negative test. Prior tranches:

- P0–P9 frozen contract digests re-verify;
- P9's read-only state is intact;
- `lab-verify-p7`, `-p7.1` and `-p8` are green, run read-only.

The single failure is the live `lab-regression` at 4/5: P0 live, whose cause predates
P10. See "Open operator decisions" below. The P1 pin that the earlier privacy redaction
missed was fixed in lockstep.

## Reproduction entry points

1. `bin/lab-verify-p10` — the terminal gate.
2. `bin/lab-scale-generate --all` — regenerates `incidents/scaled/`; compare with
   `runtime/p10-scaled-manifest.json`.
3. `bin/lab-p10-stats` — regenerates `thesis/analysis/p10-scaling.{md,json}` and
   `thesis/figures/FIG-P10-two-curve.png` byte-identically.
4. `bin/lab-p10-sweep --completeness` — the validity partition.
5. `logs/review/Q001..Q007/acceptance.md` and `logs/review/P10/decision-log.md`.

## Delivery / backup

- **Repomix archive.** A tranche-neutral archive:
  `backups/thesis-20260924T072632Z.md` plus `backups/repomix-latest.md`. It was made with
  Repomix 1.18.0 and holds 1 950 files (≈3.0M tokens); the security scan is clean.
- **What the archive adds for P10.** The config now also includes the P10 review bundles
  (`logs/review/Q*`, `P10`), the scaling sidecars, `runtime/**` and each padded incident's
  `generator-record.json`. The bulk padded ledgers (regenerable) and scratch copies are
  excluded.
- **Git.** `backups/` is gitignored.

## Open operator decisions (not done autonomously)

1. **P0 live regression.** `lab_slot` has been invalidated (`wal_removed`) since
   2026-09-01 23:24 UTC, just after P9's terminal gate. The regression's T1 reset is then
   refused, because seven P7-era `lab-incidents` PostgreSQL clusters have been running
   since 2026-08-27. Recovering means stopping those clusters and running a T1 reset,
   which rolls back the victim and records result-row invalidations. That is a lab-state
   mutation outside P10 that could touch prior evidence, so it is referred to the
   operator.
2. **gb10a model swap.** `qwen38-flash` is stopped, not removed. To reverse it, restart
   that container and remove the re-added `gb10a-deepseek-v4-flash` alias. The gateway
   config backup is `~/k3s-setup/litellm/src/config.yaml.bak-20260924T120101`.