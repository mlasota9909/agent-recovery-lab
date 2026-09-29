# P9 EXECUTION PROMPT — Model Sweep + Statistics

You are executing ONE task of SDD tranche P9 against the lab at
`<repo>` on host r740core (victim VM thesisvm01; local model
endpoint c220m3:4001 proxying vllm on gb10a:8000).

## What the project is (cold-start context)
A lab that scripts an autonomous-agent disaster against a real PostgreSQL + filesystem
(with concurrent legitimate workload), captures an out-of-band exactly-once evidence
ledger, presents that evidence three ways (R0 flat log, R1 time-window summaries,
R2 deterministic graph+summaries) behind ONE identical query interface, and has three
deciders propose a recovery coordinate that is then restored into a sandbox and scored
against a ground-truth oracle:
- Naive baseline (last checkpoint before an operator time estimate)
- Arm A (deterministic ranker over the evidence)
- Arm B (a modest, contained, local LLM reading ONE representation through a guard)

Prior validated result (SC-01, P6.1/P7.1): representation governs whether the modest
model can act at all — R2 5/5 determinations, R0 1/5, R1 0/5 — determinations are
safe-but-conservative. This was validated through the real P4 restore+validate path
against the oracle.

## Why P9 exists
Three research-grounded gaps in the current evidence base:
1. Single model = over-claim risk. A sweep across model sizes/families tests whether
   the representation effect is model-invariant.
2. The R0/R1/R2 ordering could be dismissed as a prompt/tokenizer artefact of one
   model. Replicating across DIFFERENT tokenizers/families is the strongest safeguard.
3. K=5 rates are reported without uncertainty. A pre-registered statistics pass
   (paired differences, bootstrap CIs, effect sizes, Holm correction) is required.

## Constitution (21 articles in force after this tranche's N001)
All prior articles I–XX remain binding. Especially:
- Article II: detection/deciders are provenance-blind (never read who made a change).
- Article VIII: a refusal is recorded data; never coerce a guess.
- Article X (+P6.1 amendment): model is contained — private-lab endpoint, no public
  egress during invocation, pinned local alias (never a cloud alias), weights hash pinned.
- Article XV: amend frozen contracts by supersession; never silently deviate; re-pin
  every derived hash in lockstep (grep the old digest repo-wide).
- Article XVI: verification/analysis is read-only w.r.t. evidence, ledgers, results.
- Article XVII: what the model sees (model_view) excludes the reference answer.
- Article XVIII: a null/negative result must be root-caused and the instrument ruled
  out before it is reported as a finding.
- Article XIX: independent units are isolated; completeness is not validity; a failed
  unit is superseded, never deleted.
- Article XXI (added by N001): the statistical analysis plan is pre-registered and
  frozen before data collection; results are reported whatever they show.

## Standing operating agreement (Article XX — resolve, don't stall)
Resolve internal spec contradictions yourself by precedence
(constitution > frozen contract+amendments > spec/plan > work instruction > convenience):
record an ADR + a hash-frozen amendment, re-pin derived hashes, add the negative test,
and CONTINUE. Batch all such decisions into a single end-of-run `decision-log.md`.
HALT only for: (a) destructive / out-of-lab / real-data actions; (b) anything that would
falsify results, relabel evidence, drop a unit to keep a metric green, or leak provenance
into detection; (c) a contradiction with NO backward-compatible resolution; (d) a needed
external credential. Everything else: decide, log, proceed.

## How to execute
- Do exactly ONE task (the TASK_TO_EXECUTE below). Read its work instruction at
  `sdd/specs/P9-model-sweep-statistics/work-instructions/WI-<TASK>.md`.
- In DRY_RUN: print the plan, the files you would write, and the commands — change nothing.
- In EXECUTE: do the work, run every acceptance test AND its negative test, write the
  review bundle to `logs/review/<TASK>/`, commit clean (Article XIV: refuse to record
  results rows from a dirty tree), and update the checklist.
- Report a per-criterion tier table (M = mechanically re-derived, A = attested on a
  machine-readable field). No single undifferentiated pass total.

TASK_TO_EXECUTE and MODE are appended below.
