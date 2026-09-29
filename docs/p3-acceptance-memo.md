# P3 acceptance memo

P3 analytics and Arm A closed at D010 with `bin/lab-verify-p3` **17/19**. The two red
criteria were gate-integrity defects, not an analytics miss. P3 is accepted **only after**
this P3.1 remediation.

```json
{
  "gate_mutates_evidence": true,
  "impossible_nested_regression": true,
  "resolutions": [
    "article_xvi",
    "readonly_enforced_by_manifest",
    "regression_against_fixtures"
  ],
  "p3_accepted_only_after": "P3.1",
  "d010_gate": "17/19",
  "p3_1_gate": "bin/lab-verify-p3.1",
  "headline_incident": "SC-01_20260824T091611Z",
  "headline_db_jsonl_sha256": "bf21fff2c7c71b39a150d15c9d097c797006139497c51b5a865414433a1ac7dd"
}
```

## Status

- Article XVI is in force: verification gates are read-only over the evidence root.
- `bin/lab-gate-readonly-check` enforces a before/after SHA-256 manifest (mode + size).
- Nested live prior gates against the frozen headline are replaced by `bin/lab-regression`
  against pinned fixtures under `fixtures/regression/`.
- `bin/lab-verify-p3` is honest green (19/19) under that redesign.
- The SC-01 headline `db.jsonl` is byte-identical to the D010 pre-nested freeze.
