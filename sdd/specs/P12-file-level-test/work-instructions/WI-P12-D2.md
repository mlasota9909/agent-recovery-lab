# WI-P12-D2 — File-level pipeline, part 2: reference, checks, comparators, controls, freeze

Carry out the remaining parts of `WI-P12-D.md`. Read it, the P12 spec and plan (ADR-8 to ADR-12) first. Part 1 is
complete (`lib/lab_fl_intervals.py`, `lib/lab_fl_inputs.py`, `lib/lab_fl_prompt.py`, `lib/lab_fl_rules.py`).
Note: `lib/lab_validate.py` `expected_fingerprints()` already reads the reference snapshot from `oracle.json`.

## Scope
- `lib/lab_fl_reference.py`, `bin/lab-fl-reference` (ADR-8).
- `lib/lab_fl_check.py`, `bin/lab-fl-check` (ADR-9), reusing the existing restore path with a snapshot coordinate.
- `lib/lab_fl_comparators.py`, `bin/lab-fl-rank`, `bin/lab-fl-naive` (ADR-10).
- `bin/lab-fl-controls` (spec AC-6).
- `contracts/fl-checks.md`, `contracts/fl-analysis-plan.md` (ADR-12), `bin/lab-fl-freeze` writing
  `contracts/frozen-hashes.json` (refuses to overwrite).
- Tests with synthetic fixtures for reference and manifest, every verdict v2 branch, both comparators, and that the
  reference and manifest are read only by scoring code.

## Do not
Same as `WI-P12-D.md`.

## Report
Files added, formats, test results, and any decision the plan does not fix.
