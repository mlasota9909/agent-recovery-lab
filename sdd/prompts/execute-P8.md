# Execute P8 — Analysis Outputs & Close-out

You are executing ONE task of SDD tranche P8 in the repo at <repo>.

Read, in order, before doing anything:
1. sdd/.specify/memory/constitution.md  (all twenty articles; Article XX governs how you
   proceed without stalling)
2. sdd/specs/P8-analysis-and-closeout/spec.md
3. sdd/specs/P8-analysis-and-closeout/plan.md
4. sdd/specs/P8-analysis-and-closeout/tasks.md
5. The work instruction for the task named in TASK_TO_EXECUTE:
   sdd/specs/P8-analysis-and-closeout/work-instructions/WI-<TASK>.md

## Hard rules for this tranche
- READ-ONLY on evidence, ledgers and results rows. You append analysis artefacts under
  results/analysis/ and thesis/ only. You never rewrite a results row, a ledger, or a
  frozen contract. (Article XVI.)
- CONSUME ACTIVE TAILS ONLY. The results file has 116 physical rows; only the active
  partition (25 determinations + 25 refusals + 1 run_failure = 51) is analysable. Every
  aggregate you compute must first apply the active-partition filter and must carry the
  validity partition and supersession provenance beside it. (Article XIX: completeness
  is not validity.)
- NO TRANSCRIPTION. Every figure and table number is regenerated from the results file by
  code. No hand-typed values. A figure/table that cannot be regenerated from source fails
  its acceptance criterion. (Article XIII tier-M discipline carried into analysis.)
- REFUSALS ARE DATA. Refusal cells are observed outcomes, never dropped or imputed.
- KEEP THE SPLIT. Actionability (can a modest model act at all) and compactness (evidence
  bytes/tokens) are reported separately. Compactness is scoped to where it holds (SC-01
  scale ~140x), never claimed universal — SC-04 is a documented counter-result.
- DO NOT PROMOTE. SC-03/SC-04 are set-validated supporting scenarios; do not present them
  as full P4-validated. SC-01 and SC-02 are the P4-validated headline scenarios.
- PROVENANCE-BLIND CARRIED FORWARD. No analysis artefact may surface the `principal`/role
  field or any answer-key coordinate as an input to a representation-comparison figure.

## Determinism & governance
- Analysis is a deterministic pure function of the results file plus pinned config. Re-running
  any generator must produce byte-identical output (AC checks this).
- If you hit an internal contradiction, apply Article XX: resolve by precedence, record an
  ADR under docs/adr/, add an Article XV amendment if a frozen artefact's meaning changes,
  re-pin any derived hashes repo-wide by grep of the old digest, add the negative test, and
  continue. Log it to decision-log.md. Do not stall.

## Output discipline
- MODE: DRY_RUN — write the intended plan/diff for the task to logs/review/<TASK>/plan.md
  and change nothing else.
- MODE: EXECUTE — perform the task, write the review bundle to logs/review/<TASK>/, then stop.
- Produce exactly the artefacts and acceptance evidence named in the work instruction.
- Do not proceed to the next task.
