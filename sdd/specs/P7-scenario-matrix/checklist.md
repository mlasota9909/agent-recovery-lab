# Checklist — P7: Scenario expansion and the run matrix

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| K001 | Freeze P7 contracts; re-measure throughput; record stratified plan + entry gate | 2026-08-26 | logs/review/K001/ | [ ] |
| K002 | SC-02 filesystem mass-deletion scenario | 2026-08-26 | logs/review/K002/ | [ ] |
| K003 | SC-03 schema-damage (staged DDL) scenario | 2026-08-26 | logs/review/K003/ | [ ] |
| K004 | SC-04 stealthy-corruption scenario + precision/recall harness | 2026-08-26 | logs/review/K004/ | [ ] |
| K005 | per-scenario R0/R1/R2 build; SC-01 unchanged re-verify | 2026-08-26 | logs/review/K005/ | [ ] |
| K006 | `bin/lab-matrix` unattended orchestrator | 2026-08-26 | logs/review/K006/ | [ ] |
| K007 | execute the stratified matrix; complete results file | 2026-08-26 | logs/review/K007/ | [ ] |
| K008 | honest findings: SC-03 trade-off, SC-04 precision/recall, refusal diagnosis | 2026-08-26 | logs/review/K008/ | [ ] |
| K009 | cross-scenario headline R0-vs-R1-vs-R2 + Arm A/B/naive | 2026-08-26 | logs/review/K009/ | [ ] |
| K010 | `bin/lab-verify-p7` gate; hashes re-verified; handoff | 2026-08-26 | logs/review/K010/ | [ ] |

## Operator review order

1. `RESULT` line, `CONFOUNDER PRESENT`, `PROVENANCE-BLIND` and `UNATTENDED` lines of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check. For **K002/K003/K004**, confirm each scenario has concurrent legitimate activity overlapping the
   damage window and that a confounder-less scenario is refused; confirm ground truth is computed from the scripted
   record, not eyeballed. For **K006/K007**, confirm one schema-valid results row per run, a failed run recorded as an
   `outcome="run_failure"` row with the matrix continuing, and `total_rows = total_planned_runs`. For **K008**, confirm
   SC-03 reports the legitimate DML sacrificed and SC-04 reports precision/recall + earliest-bounded commit, from
   machine-readable fields. For **K009**, confirm SC-04 shows the largest R0-vs-R2 gap and that a hand-entered figure
   disagreeing with the results file is caught. For **K005/K010**, confirm SC-01's frozen ledger and banked results are
   byte-identical.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P7-01 | M | K001 |
| AC-P7-02 | M | K002 |
| AC-P7-03 | M | K003 |
| AC-P7-04 | M | K004 |
| AC-P7-05 | M | K002, K003, K004 |
| AC-P7-06 | M | K005 |
| AC-P7-07 | M | K005 |
| AC-P7-08 | M | K006 |
| AC-P7-09 | M | K006 |
| AC-P7-10 | M | K007 |
| AC-P7-11 | M | K007 |
| AC-P7-12 | M | K007 |
| AC-P7-13 | M | K007 |
| AC-P7-14 | M | K008 |
| AC-P7-15 | M | K008 |
| AC-P7-16 | A | K008 |
| AC-P7-17 | M | K009 |
| AC-P7-18 | M | K002 |
| AC-P7-19 | M | K010 |
| AC-P7-20 | M | K010 |
| AC-P7-21 | A | K010 |

Nineteen of twenty-one criteria are tier M. The two tier A criteria (residual-refusal diagnosis, handoff record)
assert on machine-readable fields, per Article XIII.

## Tranche exit condition

P7 is accepted when `bin/lab-verify-p7` reports every criterion PASS with per-tier totals printed separately and is
itself proven read-only over the evidence root; both P7 contracts are frozen and hash-verified; the full-cycle
throughput is re-measured and the stratified plan recorded with SC-04 fully replicated; SC-02/03/04 are defined with
mandatory overlapping confounders, computed ground truth and corpus citations; per-scenario R0/R1/R2 are admissible,
interface-parity-holding and guard-clean; SC-01's artefacts and banked results are byte-identical and referenced; the
unattended matrix is executed with one schema-valid row per run, failures recorded as rows, ledger idempotency per
incident, and `total_rows = total_planned_runs`; every arm-coordinate is provenance-blind and scored through the
unchanged P4 path where applicable; SC-03's trade-off and SC-04's precision/recall + earliest-bounded commit are
computed from committed fields; residual refusals are root-caused via Article XVIII; the cross-scenario R0-vs-R1-vs-R2
headline is produced from machine-readable fields with SC-04 foremost; all prior gates, regression and contract hashes
are unchanged; and the P7 handoff is written without anti-goal inversion.

## Note for P8

- **P8** (analysis and figures) reads the complete results file and produces every figure and table directly from
  it — the cross-scenario R0-vs-R1-vs-R2 comparison, the Arm A vs Arm B vs naive contrast, the SC-03 trade-off and the
  SC-04 precision/recall — plus the model's verbatim explanations for the operator-assistance argument. P7 produces
  the data; P8 analyses it.
