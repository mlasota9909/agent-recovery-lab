# ADR-P5.1-1 — Answer key in the subject-visible envelope (D1, D2)

**Status:** accepted
**Date:** 2026-08-25
**Tranche:** P5.1
**Related:** ADR-P5.1-2 (model_view/reference split), ADR-P5.1-3 (guard), Article XVII

This ADR records two defects found at P5 close (F010). It does not pretend either was correct. The P5 representations themselves are sound: R0/R1/R2 are deterministically built (`built_by_model=false`), provenance-blind, and R2's evidence-bytes are a small fraction of R0's. The confound is in the *interface surface*, not in the artefacts.

## Observed close

`bin/lab-verify-p5` shipped **TIER M 18/18 · TIER A 1/1 · TOTAL 19/19**. Evidence: `logs/review/F010/verify-p5.out`, `docs/P5-architecture-handoff.md`.

## D1 — the answer key is in the subject-visible envelope

**Evidence from the frozen `representation-interface` contract** (`sdd/specs/P5-representations/contracts/representation-interface.md`, F001 hash `57ba586c2d2fcc939f44e63405a5579fa1e2c43653e3ff16457e8375bfd9d5f1`):

**§4 (response envelope)** co-locates `answer` and `content`:

> `answer` | object | the structured answer to the probe — same schema per probe across all three representations
> `content` | string | the evidence the representation surfaces to support the answer (the payload a model would read)

**Hard rule R3:**

> only `content` and `telemetry` may differ. For a given probe and incident, the `representation`, `probe_id`, `answer` shape, and all envelope fields are identical in structure across R0/R1/R2.

**§5** designates `PB-6-candidate-windows` as the recovery probe:

> `PB-6-candidate-windows` is the recovery-relevant probe: it is the one P6's model uses to locate a recovery coordinate

For PB-6, `answer` is `{candidates:[{window_index, last_safe_lsn_int, anomaly_score}]}` — the recovery coordinate itself — and R3 makes that coordinate **identical across R0/R1/R2**.

**Why this voids the ablation.** P6 is meant to point a modest local model at a representation and have it *derive* a coordinate from `content`. P6 then scores that coordinate through the P4 restore+validate path against the oracle, so the interface `answer` has **no scoring role**. If P6 hands the model the full response envelope, the model reads the coordinate from `answer`, `content` becomes decorative, and the R0-vs-R1-vs-R2 comparison measures a leaked key rather than the representation. Nothing in P5 mechanically prevented that.

This is the same class as the P0.1 test hatch (Article XII), P3 provenance-in-detection (Article II), and P1 `harness_commit` (Article XIV): an unenforced separation between what a subject may see and the answer key.

## D2 — headline probe mislabel

The F009 headline was labelled `PB-4-earliest-anomaly`. The recovery probe defined by §5 is `PB-6-candidate-windows`. R2 evidence-bytes are strictly and materially smaller than R0's on **both** probes (F008 telemetry: PB-4 ratio ≈ 0.005; PB-6 ratio ≈ 0.007), so the measured property holds. The reported headline number must nevertheless be the PB-6 delta, because that is the probe P6's model uses. This is a labelling correction, not a re-run of the representations.

## What this ADR does not do

It does not rebuild R0/R1/R2. It does not mutate the frozen `representation-interface.md`. It does not delete `answer` (parity still needs it). It does not change SC-01 headline hashes.
