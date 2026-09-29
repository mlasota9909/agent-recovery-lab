# Execute Tranche P11 — Answer-Grammar Re-Score (cold-start prompt)

You are executing ONE task from SDD tranche **P11-answer-grammar-rescore** in the repository rooted at `/home/mlasota/thesis`.
Everything you need is in `sdd/specs/P11-answer-grammar-rescore/`. Read `spec.md`, `plan.md`, `tasks.md`, both files in `contracts/`, and the matching `work-instructions/WI-<TASK>.md` before you act.

## The research context you are serving (do not skip)

The project studies operational recovery from autonomous-agent incidents. A scripted incident damages a lab; evidence is captured out-of-band and presented three ways (R0 raw change log, R1 window aggregates, R2 graph + hierarchical window summaries) behind one guarded `model_view`; a local model proposes a recovery coordinate that is scored by restoring it against a ground-truth oracle.

P10 scaled SC-01 from its natural ~19 435 to ~999 333 R0 tokens and showed R0 becomes infeasible at 500k–1M while R2 stays ~248 tokens (H2 HOLDS), with zero corrupt recoveries (H3 HOLDS). P10's within-window accuracy question (H1) was **not evaluable**: the frozen P6.1 extractor logged every within-window R0 answer as `refusal_parser` because multi-locator answers did not resolve to exactly one LSN. The extractor was flagged in the P10 handoff as "the next instrument to fix... any change needs its own pre-registered tranche." **You are that tranche.**

## The one thing that makes or breaks P11

The relaxed answer grammar MUST be frozen and pre-registered BEFORE any completion is re-parsed. It is an **instrument repair specified by a rule**, never a knob tuned until R0 looks good. Concretely the grammar:
- accepts a single resolved LSN when every locator a model offers points to the **same** event in the evidence;
- resolves a timestamp at the recorded heartbeat granularity to the unique commit LSN within that heartbeat window;
- is **answer-blind**: it resolves locators using only the evidence/view, never the oracle optimum;
- is applied **symmetrically to R0 and R2** — relaxing it for R0 only would be the knob, and a parity check fails closed if you try.

## Standing operating agreement (Article XX — in force)

Resolve internal contradictions yourself by precedence (constitution > frozen contract + amendments > spec/plan > work instruction > convenience); record an ADR + Article XV amendment; re-pin derived hashes in lockstep; add the negative test; continue. Log each decision to a single end-of-run `decision-log.md`. **Halt only for:** an out-of-lab / destructive / real-data action; anything that would falsify a result, relabel evidence to hit a metric, drop a unit, or leak provenance/answer into detection or extraction; a contradiction with no backward-compatible resolution; or a missing external credential.

## Hard rules specific to P11

1. **Read-only on ALL P10 and prior artefacts (Article XVI).** You append to a new `results/rescoring-runs.jsonl` keyed by a new `rescore_run_id`. You do NOT mutate `results/scaling-runs.jsonl`, the banked completions in `results/scaling-runs-detail.jsonl`, any ledger, representation, or banked headline. Prove byte-identity before and after (AC in R007).
2. **Re-parse ALL banked completions, not just the parser-refusals.** The new grammar can change an already-`accepted` parse or an R2 parse too. Re-parse the full P10 submitted set, and report every verdict-class change (consistency check).
3. **Pre-registration (Article XXI).** Grammar + analysis plan digests are frozen before any re-score row exists. R005 refuses to run if either digest changed after data collection began.
4. **Answer-blind extraction (Articles II, XVII).** The extractor never reads the oracle optimum to decide a parse. Negative test in R002.
5. **Report whatever it shows.** If H1-R is null (R0 does not degrade within the window), that is the expected, honest result and sharpens the feasibility-not-precision story. Do NOT manufacture a degradation.

## Invocation

Append exactly two lines when you run this prompt:

```
TASK_TO_EXECUTE: <R00N>
MODE: DRY_RUN            # or EXECUTE
```

In DRY_RUN, change nothing: write the intended plan, commands, artefact list and negative test to `logs/review/<TASK>/dry-run.md` and stop. In EXECUTE, do the work, emit the review bundle, and update the checklist. For the conditional R004, DRY_RUN must state whether the pre-registered re-run trigger fired and why.
