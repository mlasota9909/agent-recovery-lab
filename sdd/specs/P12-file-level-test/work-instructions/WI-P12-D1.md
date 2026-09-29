# WI-P12-D1 — File-level pipeline, part 1: intervals, inputs, prompt, answer reading

Carry out the parts of `WI-P12-D.md` listed here, and only these. Read `WI-P12-D.md`, the P12 spec and plan
(ADR-3 to ADR-7) first. Task C is complete: `fs_diff.tsv`, `fs_hashes.tsv`, `fs-workload.jsonl` and the merged
`snapshots.json` exist per incident (see `lib/lab_file_evidence.py`, `lib/lab_fs_reconcile.py`).

## Scope
- `lib/lab_fl_intervals.py`, `bin/lab-fl-intervals` (ADR-3, ADR-4).
- `lib/lab_fl_inputs.py`, `bin/lab-fl-inputs` (ADR-5, ADR-6), passing `bin/lab-modelview-guard` unchanged.
- `contracts/fl-prompt.md` and `lib/lab_fl_prompt.py`.
- `lib/lab_fl_rules.py`, `bin/lab-fl-read-answer` (ADR-7).
- `contracts/fl-inputs.md`, `contracts/fl-answer-rules.md`.
- Tests with synthetic fixtures for exactly these parts, including a zero-variance baseline, every answer-reading
  branch, the guard, and a test that the input builders never open reference, oracle or damage-manifest files.

## Out of scope (part 2)
Reference and damage manifest, restore and checks, verdict v2, comparators, controls, analysis plan, freeze.

## Do not
Same as `WI-P12-D.md`.

## Report
Files added, formats, test results, and any decision the plan does not fix.
