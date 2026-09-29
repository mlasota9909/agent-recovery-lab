# Execute Tranche P10 — Token-Scaling (cold-start prompt)

You are executing ONE task from SDD tranche **P10-token-scaling** in the repository rooted at `/home/mlasota/thesis`.
Everything you need is in `sdd/specs/P10-token-scaling/`. Read `spec.md`, `plan.md`, `tasks.md`, both files in `contracts/`, and the matching `work-instructions/WI-<TASK>.md` before you act.

## The research context you are serving (do not skip)

The project studies **operational recovery from autonomous-agent incidents**. A scripted incident damages a PostgreSQL + filesystem lab while legitimate work runs concurrently; evidence is captured out-of-band; the same evidence is presented three ways (R0 raw change log, R1 time-window aggregates, R2 graph + hierarchical window summaries) behind one identical, guarded `model_view` interface; a modest local model proposes a recovery coordinate that is scored objectively by restoring it and comparing against a ground-truth oracle.

P9 (already accepted, frozen) ran the R0/R1/R2 ablation on SC-01 across three local models. Result of record: the representation effect is **real but model-specific** (pooled Cochran's Q = 2.889, p = 0.236; DeepSeek needs R2, Gemma is best on R0 and refuses R2, Qwen is representation-invariant), and **no model ever produced an `incorrect_corrupt` recovery**. At SC-01's natural size R0 is ~44 KB / ~17.9 k tokens and fits every model's 262 144-token window, so "why compress?" is unanswered. **P10 answers it by scaling.**

## Standing operating agreement (Article XX — in force)

Resolve internal contradictions yourself by precedence (constitution > frozen contract + amendments > spec/plan > work instruction > convenience); record an ADR + Article XV amendment; re-pin any derived hashes in lockstep; add the negative test; continue. Log each such decision to a single end-of-run `decision-log.md`. **Halt only for:** an out-of-lab / destructive / real-data action; anything that would falsify a result, relabel evidence, drop a unit to keep a metric green, or leak provenance/answer into detection; a contradiction with no backward-compatible resolution; or a missing external credential.

## Hard rules specific to P10

1. **Read-only on prior artefacts (Article XVI).** You append to a new `results/scaling-runs.jsonl` sidecar keyed by a new `scale_run_id`; you do NOT mutate the frozen P1 results schema, the P9 `sweep-runs.jsonl`, any ledger, any representation artefact, or any banked headline. Prove the prior-evidence manifest is byte-identical before and after (AC in Q007).
2. **The true recovery point is invariant under scaling.** Padding adds only *legitimate* activity. If any padded incident's oracle optimum differs from the frozen SC-01 optimum, you have corrupted the incident — halt.
3. **Pre-registration (Article XXI).** The analysis plan is frozen in Q001 BEFORE any scaling run exists. Q005 refuses to run if the plan digest changed after data collection began. Every outcome branch has a pre-declared interpretation, including the branch where R0 reads a 1 M-token log fine.
4. **Provenance-blind + answer-blind (Articles II, XVII).** Every model input still passes the single `lab-modelview-guard` choke point. Padding must not introduce a `principal` field or any answer-key coordinate into the model-visible surface.
5. **Report whatever it shows.** If R0 degradation does not appear, that is a clean, publishable result that sharpens the "matters most for constrained local models / beyond the reliable window" framing. Do not tune padding to manufacture degradation.

## Invocation

Append exactly two lines when you run this prompt:

```
TASK_TO_EXECUTE: <Q00N>
MODE: DRY_RUN            # or EXECUTE
```

In DRY_RUN, change nothing: write the intended plan, commands, artefact list and negative test to `logs/review/<TASK>/dry-run.md` and stop. In EXECUTE, do the work, emit the review bundle, and update the checklist.
