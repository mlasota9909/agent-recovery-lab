# WI-P12-D — File-level test pipeline

Goal: implement the file-level test of the P12 plan (ADR-3 to ADR-12) as new, separate modules that reuse the lab's
existing helpers (configuration, evidence folders, restore, model invocation, model-view guard) without changing the
database-level pipeline. Depends on WI-P12-C (captured differences, fingerprints and file operation records exist).

## Modules and commands (new)
- `lib/lab_fl_intervals.py`, `bin/lab-fl-intervals <incident>`: intervals from the recorded snapshots (ADR-3), the
  three features per interval from `fs_diff.tsv`, the baseline and score (ADR-4), flags. Output
  `evidence/.../fl-intervals.json`.
- `lib/lab_fl_inputs.py`, `bin/lab-fl-inputs <incident> --input R0|R1|R2`: the three input constructions for the three
  highest-scoring intervals (ADR-5, ADR-6). The model view carries only the content string and the existing
  model-view keys; it must pass `bin/lab-modelview-guard` unchanged. No actor names; no reference, answer or damage
  manifest fields.
- `sdd/specs/P12-file-level-test/contracts/fl-prompt.md`: the instruction wrapper for the file task, adapted from the
  Primary Sweep wrapper (same structure: task, evidence block, answer format, refusal option): name the latest safe
  snapshot before the damaging file activity began; answer with exactly one line `COORDINATE interval=<N>` and/or
  `snapshot=<name>` and/or `ts=<ISO-8601 UTC>` (space-separated locators), or `REFUSAL <reason>`.
  `lib/lab_fl_prompt.py` assembles prompt = wrapper + one input content.
- `lib/lab_fl_rules.py`, `bin/lab-fl-read-answer`: the answer-reading rules of ADR-7, resolving only from what the
  prompt showed. Output: accepted (snapshot), rule rejection (reason), or declined (refusal reason).
- `lib/lab_fl_reference.py`, `bin/lab-fl-reference <incident>`: the reference snapshot and the damage manifest
  (ADR-8) and the list of legitimate file operations per interval. Output `fl-reference.json` (scoring only; never
  read by input builders; enforce with a test).
- `lib/lab_fl_check.py`, `bin/lab-fl-check <incident> <snapshot>`: restore through the existing restore path with a
  snapshot coordinate (files cloned at the snapshot; database replayed to that snapshot's recorded LSN), then the
  checks and verdict v2 of ADR-9; database row checks as the existing SC-02 path does. Reuse a stored report for a
  snapshot already checked. Output a report per snapshot with counts and verdict v2.
- `lib/lab_fl_comparators.py`, `bin/lab-fl-rank`, `bin/lab-fl-naive`: the two comparators of ADR-10.
- `bin/lab-fl-controls <incident>`: the four controls of spec AC-6 (reference, first post-damage snapshot, earliest
  snapshot, tampered restored file via the existing probe mechanism).
- Contracts (text, frozen before the run): `contracts/fl-inputs.md` (formats with one example each),
  `contracts/fl-answer-rules.md`, `contracts/fl-checks.md` (checks and verdict v2), `contracts/fl-analysis-plan.md`
  (ADR-12), and `contracts/frozen-hashes.json` written by a `bin/lab-fl-freeze` command.

## Tests
Synthetic fixtures (a fake incident folder with snapshot records, differences, fingerprints, file operation records
and an injection record) covering: interval building and scoring (including a zero-variance baseline), input building
for all three inputs, guard pass, every answer-reading rule branch, reference and manifest, verdict v2 for correct /
extra loss / damage retained / not recovered, and that input builders never read the reference or manifest.

## Do not
- Do not change database-level modules' behaviour, thresholds or frozen contracts. Do not run commands that contact the
  network, a VM, PostgreSQL, ZFS or libvirt. Do not create commits. Do not modify files outside this repository. Do not
  mention tools, assistants or the origin of the changes in any file, comment or message.

## Report
Files added, formats, test results, and any decision you had to take that the plan does not fix (so it can be frozen).
