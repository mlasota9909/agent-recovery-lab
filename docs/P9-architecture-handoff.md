# P9 architecture handoff — Model Sweep + Statistics

Date: 2026-09-01
Status: P9 accepted; the tranche is analysis + one small forward experiment.

## Result of record

P9 replicated the R0/R1/R2 representation ablation on SC-01 across **three distinct local
models / families / tokenizers** through the identical guarded interface, analysed it under
a **pre-registered** statistics plan frozen before any data existed (Article XXI).

**The headline is a null under the pre-registered primary test, and it is reported as such
(Article XXI.3).** The pooled Cochran's Q across R0/R1/R2 is not significant (Q = 2.889,
df = 2, p = 0.236). The pre-registered interpretation for that branch is emitted verbatim:
*"no detectable representation effect on determination at this scale."*

The Article XVIII root-cause (labelled Exploratory, not pre-registered) is the important
finding: **the pooled null masks two strong, opposing per-model effects.** The
single-model R0 < R1 < R2 ordering from P6.1 does **not** replicate as a uniform ordering.

## The sweep

`results/sweep-runs.jsonl` — 45 rows, SHA-256
`7b9a33aaa4cb3f3b089ff549fedc3ded6dd8feb0b69f7a5743197a75b98cd391`.
45 cells = SC-01 × {R0, R1, R2} × {DeepSeek-V4-Flash, Gemma-4-26B, Qwen3.8-27B} × K=5.
Partition: **28 determinations, 17 refusals, 0 run failures.** Every invocation
containment-verified; every completion `finish_reason=stop` (no truncation).

| representation | DeepSeek-V4-Flash | Gemma-4-26B | Qwen3.8-27B |
| --- | --- | --- | --- |
| R0 (flat log)      | 2/5 det — both `incorrect_safe` | 4/5 det — **all `correct`** | 5/5 det — **all `correct`** |
| R1 (time-window)   | 0/5 det | 2/5 det — `incorrect_safe` | 5/5 det — `incorrect_safe` |
| R2 (graph+summary) | 5/5 det — `incorrect_safe` | **0/5 — refuses entirely** | 5/5 det — `incorrect_safe` |

- No determination anywhere was `incorrect_corrupt` — every model that acted stayed safe.
- The DeepSeek column reproduces J004's SC-01 pattern (R2 ≫ R0 > R1) within replicate
  variance; greedy decoding over the 17.9k-token R0 context is not bit-identical run to run
  (J004 R0 was 1/5; this run 2/5).

## Pre-registered statistics (`analysis-out/analysis/p9-statistics.{json,md}`)

- **H1** (pre-registered primary = pooled Cochran's Q): Q = 2.889, p = 0.236 → **does not hold**.
  Per model (exploratory): DeepSeek Q = 7.60, p = 0.022; Gemma Q = 6.00, p = 0.050; Qwen Q = 0, p = 1.
- **H2** (per-model bootstrap 95% CI on the R2 − R0 rate, 10 000 resamples, seed 42; holds
  IFF the CI lower bound > 0 for every model):
  DeepSeek +0.60 [+0.20, +1.00] (holds), Gemma −0.80 [−1.00, −0.40] (fails),
  Qwen 0.00 [0, 0] (fails) → **does not hold**.
- Cliff's delta (R2 vs R0): DeepSeek +0.60 (large), Gemma −0.80 (large), Qwen 0.00 (negligible).
- Pairwise McNemar (exact) + Holm across the 3 pairs per model: nothing survives Holm at
  0.05 (K=5 is under-powered for the pairwise level).
- Outcome branch ¬H1 ∧ ¬H2 → plan §4 interpretation #3 emitted verbatim; the
  universal-language lint passes; every number regenerates byte-identical.

**Reading (ADR-P9-4):** the representation effect is real but **model-specific and
directionally inconsistent** — DeepSeek needs the R2 graph, Gemma is best on the raw log and
refuses R2 outright, Qwen is representation-invariant. A pooled omnibus cancels opposing
within-group effects, so the pre-registered pooled null is the expected reading, not
evidence of no effect. The pooled reading was chosen because it is the more literal reading
of the frozen plan and the *less* favourable result; taking the per-model reading to
manufacture an "effect detected" headline is the selective-analysis move Article XXI exists
to prevent.

## Arm A vs Arm B (`analysis-out/analysis/armA-vs-armB.{json,md}`)

Arm A (deterministic ranker `p3-rank-1`) is the **correctness / backbone** layer — model-free,
bounded, always available; on SC-01 it is `incorrect_safe` (0 damage, 8 legit rows lost).
Arm B (contained modest local model over one representation) is the **interpretation /
accessibility** layer, grounded in VerifyRCA / VeriOps-Agent's decoupling of LLM generation
from a non-LLM verifier. Arm A being at least as optimal as Arm B is the expected division
of labour.

Honest note computed from the rows: `gemma/R0` and `qwen/R0` reached `correct`, i.e. more
optimal than the deterministic ranker on this incident. That does not overturn the framing —
Arm A's verdict is predictable and model-independent; Arm B's optimality is model- and
representation-dependent, exactly as the sweep shows.

Compactness cross-reference (from P8): median presented bytes 44,267 (R0) → 1,103 (R2) at
SC-01 scale, a 40.1× reduction; `compactness_holds=false` on tiny SC-04 (1,088 vs 799).

## Constitution and governance

- **Article XXI** ratified (N001): pre-registered analysis; report what it shows. 21
  articles, no duplicate number; `docs/INDEX.md` regenerated (21 articles, 16 ADR files,
  zero dangling amendment references); `analysis/gen_index.py` article count pinned 20 → 21.
- Five ADRs: **ADR-P9-1** sweep isolation (sidecar; frozen P1 schema untouched);
  **ADR-P9-2** loopback LiteLLM gateway supersedes the offline `c220m3:4001` (containment
  R2a–R2d preserved / strengthened; `bin/lab-model` and `lib/lab_model_runtime.py`
  unchanged); **ADR-P9-3** uniform `max_tokens = 8192` so reasoning models are not truncated
  (Article XVIII); **ADR-P9-4** H1 pooled-primary + Article XVIII root-cause;
  **ADR-P9-5** reconcile `etc/lab.env` `ZFS_VERSION` to the VM's actual zfsutils string
  (`2.4.1-1ubuntu5.1`; kmod unchanged) — `repro/manifest.json` stays P8-frozen.
- Full decision batch: `logs/review/P9/decision-log.md`.

## P9 environment fingerprint

- `etc/lab.env` SHA-256 `d702508bc1d4969b3bf2aa57307543e0b1849c60a276cb3b41e558c5158b3444`
- zfsutils-linux `2.4.1-1ubuntu5.1` (VM); ZFS kmod `2.4.1-1ubuntu5` (unchanged — governs behaviour)
- PostgreSQL 18.4; guest/host kernel 7.0.0-* ; the P8 `repro/manifest.json` records P8's
  environment (`lab_env_sha256 cb774481…`) and is deliberately not rewritten.

## Frozen contracts (pinned in `contracts/frozen-hashes.json`, re-verified by the gate)

| contract | SHA-256 |
| --- | --- |
| `model-sweep-plan.md` | `9c608611441dc04a1d7afd134d3a5563fc18ea5200c6975534c35a8c2f089b3d` |
| `statistical-analysis-plan.md` | `08f07d874bca67cf50d3a9082c3367014144d504fad21d0b0d2148255aa455c0` |
| `related-work-positioning.md` | `044bb3a0b0466e9ce41613ccb13f244778ef92b52a18aa502654c09b982cf4f6` |

Frozen at commit `b41d0e4` before `results/sweep-runs.jsonl` existed. `statistical-analysis-plan.md`
is a frozen contract under Article XXI.2: `bin/lab-p9-stats` refuses to run if its digest
changed after the first sweep row (proven by the N005 negative test).

## The 3-model registry (`runtime/p9-model-set.json`, verified `runtime/p9-model-verify.json`)

| slot | alias | family | param class | tokenizer fingerprint (fixed probe) | backend | digest kind |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | `gb10a-deepseek-v4-flash` (P6.1 baseline) | deepseek | ~27B MoE, exl3-k2 | 35 tokens, `tokba238d48b3ed4b05` | `203.0.113.20:8000` (RFC-1918) | `weights_sha256 c5da6dd1…` |
| M2 | `gympc-gemma4-26b` | gemma | ~26B, QAT-q4 | 58 tokens, `tok0179b3840ba64eda` | `203.0.113.31:8090` (CGNAT lab) | backend immutable identity |
| M3 | `alienware-qwen38-27b` | qwen | ~27B MTP, NVFP4 | 57 tokens, `toka2b016434398bf74` | `203.0.113.21:8010` (RFC-1918) | backend immutable identity |

3 distinct families, 3 distinct tokenizer_ids. The registry validator refuses < 3 models, a
shared `tokenizer_id`, < 2 families, or a cloud alias.

## Containment (Article X + P6.1 `model-runtime.amendment-1`, re-checked per model)

Endpoint: `http://127.0.0.1:4001` (loopback LiteLLM gateway; ADR-P9-2). For each model, in a
real inference call: R2a endpoint + backend private, R2b no public egress observed (`ss -tnp`
sampled concurrently — only peer is `127.0.0.1:4001`), R2c pinned local alias only
(`lab_p9.is_cloud_alias` refuses `*-pro`, `frontier-*`, `gemini-*`, `nemotron-*`, `glm-*`,
`kimi-*`, `arbiter`; `lab-p9-model` refuses a cloud/unregistered alias **pre-flight**),
R2d fixed weights / immutable digest. All 3 models: `containment_verified = true`.
Honest limit: the shared gateway also fronts cloud aliases and
makes its own onward connection; isolation rests on never targeting a cloud alias plus the
observed loopback-only egress of the invocation process, not on physical disconnection.

## Interface parity (anti-artefact — N003)

Model identity is not an argument to `lab-repr-modelview` or `lab-arm-b-prompt`. For a fixed
representation the guarded `model_view` and the assembled prompt are byte-identical across
every model (R0 `a6c05004…`, R1 `aaa23618…`, R2 `7f38a906…` — each single-valued over the 3
models). R0/R1/R2 artefact `content_hash` byte-identical to the P5/P5.1 close (F002/F003/F004).
The guard refuses a spliced reference answer on every representation path. Negative test:
injecting a per-model key trips the guard and changes the structural digest.

## Read-only guarantee (Article XVI / AC-P9-12)

`runtime/p9-readonly-baseline.json` captured the evidence-root manifest (567 files) and the
prior results-row file SHAs before the sweep. After P9: evidence manifest and
`results/SC-01..04.jsonl` + `results/matrix.jsonl` byte-identical. New rows live only in
`results/sweep-runs.jsonl`; new analysis only under `analysis-out/analysis` and
`analysis-out/related-work`. The frozen P1 results-row schema digest is unmoved.

## New code (all under `bin/lab-p9-*`, `lib/lab_p9*`)

| tool | purpose |
| --- | --- |
| `bin/lab-p9-modelset` (`lib/lab_p9_register.py`) | build / validate `runtime/p9-model-set.json` |
| `bin/lab-p9-verify-models` (`lib/lab_p9_verify_models.py`) | N002 per-model containment + digests + smoke |
| `bin/lab-p9-parity` (`lib/lab_p9_parity.py`) | N003 interface parity + artefact-hash re-assert |
| `bin/lab-p9-model` (`lib/lab_p9_model.py`) | guarded, contained per-model invocation (does not touch `bin/lab-model`) |
| `bin/lab-p9-sweep` (`lib/lab_p9_sweep.py`) | N004 sweep runner (resumable; run_failure rows; `--completeness`) |
| `bin/lab-p9-stats` (`lib/lab_p9_stats.py`, `lib/lab_p9_statlib.py`) | N005 pre-registered analysis (plan-drift refusal, lint) |
| `bin/lab-p9-analysis` (`lib/lab_p9_analysis.py`) | N006 Arm A/B analysis |
| `bin/lab-verify-p9` (`lib/lab_verify_p9.py`) | terminal AC-P9-01..13 tiered gate |
| `lib/lab_p9.py` | shared: registry, containment, frozen-hash checks, private-address classification |

`lib/lab_p9_statlib.py` is pure stdlib: Cochran's Q (df = 2 exact), exact McNemar,
Holm-Bonferroni, block bootstrap CI (pinned seed), Cliff's delta, chi-square SF.

## Reproduction entry points

1. `bin/lab-verify-p9` — terminal gate (`logs/review/N008/gate.json`, `hash_reverify.json`,
   `readonly-manifest-diff.json`, `regression-vs-fixtures.json`, `close-out-memo.md`)
2. `bin/lab-p9-sweep --completeness` — `logs/review/N004/sweep-completeness.json`
3. `bin/lab-p9-stats` — regenerates `analysis-out/analysis/p9-statistics.{json,md}` byte-identical
4. `bin/lab-p9-analysis --what armab` — regenerates the Arm A/B artefacts
5. `logs/review/N001..N008/acceptance.md` — per-task tier tables
6. `logs/review/P9/decision-log.md`
7. `docs/INDEX.md`, `docs/adr/ADR-P9-*.md`

## Terminal gate (N008)

`bin/lab-verify-p9` — **TIER M 11/11 · TIER A 2/2**, `ok = true`, on the committed tree.
- All 30 frozen contract digests (P0–P8 chain + the 3 P9 contracts) re-verify.
- `bin/lab-regression` **5/5** (P0 18/18, P1 24/24, P1.1 16/16, P2 18/18, P2.1 16/16);
  `lab-verify-p7`, `lab-verify-p7.1`, `lab-verify-p8` exit 0 (run read-only).
- Read-only: evidence manifest (567 files) + `results/SC-01..04.jsonl` + `results/matrix.jsonl`
  SHA-256 identical to the pre-sweep baseline.
- `logs/review/N008/{gate.json,hash_reverify.json,readonly-manifest-diff.json,regression-vs-fixtures.json,close-out-memo.md}`.

## Delivery / backup

- Tranche-neutral Repomix archive: `backups/thesis-<UTC>.md` (+ `backups/repomix-latest.md`).
- The backup set now includes `results/sweep-runs.jsonl`, `thesis/**`, and the
  `logs/review/N*` bundles (decision-log P9-N004-BACKUP-01).
- `results/sweep-runs.jsonl` SHA-256 `7b9a33aaa4cb3f3b089ff549fedc3ded6dd8feb0b69f7a5743197a75b98cd391`.
- Repomix 1.18.0; security scan PASS.
