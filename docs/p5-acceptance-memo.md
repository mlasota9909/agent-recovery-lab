# P5 acceptance memo

P5 representations closed at F010 with `bin/lab-verify-p5` **19/19**. The
representations (R0/R1/R2) are sound: deterministically built, provenance-blind,
and R2's evidence-bytes on the recovery probe are a small fraction of R0's.

The P5.1 review found a latent confound in the *interface surface*: the frozen
`representation-interface` envelope co-located `content` with `answer`, and for
`PB-6-candidate-windows` that `answer` is the recovery coordinate. P5 is
accepted **only after** this P5.1 remediation.

```json
{
  "remediated_defect": "answer-key-in-subject-view",
  "headline_probe": "PB-6-candidate-windows",
  "p5_accepted_only_after": "P5.1",
  "p5_gate": "bin/lab-verify-p5",
  "p5_1_gate": "bin/lab-verify-p5.1",
  "headline_incident": "SC-01_20260824T091611Z",
  "headline_db_jsonl_sha256": "bf21fff2c7c71b39a150d15c9d097c797006139497c51b5a865414433a1ac7dd",
  "article_xvii": true,
  "model_view_keys": [
    "incident_id",
    "representation",
    "probe_id",
    "params",
    "content",
    "telemetry"
  ]
}
```

## Status

- Article XVII is in force: the subject-visible surface excludes the reference answer.
- `bin/lab-repr-modelview` is the only object P6 may pass to a model.
- `bin/lab-modelview-guard` mechanically refuses any model view carrying `answer`,
  a structured coordinate field, or a provenance token.
- `bin/lab-repr-query` (F005) is unchanged; the original `representation-interface.md`
  is byte-identical.
- The F009 headline is reported on **PB-6**. R0/R1/R2 artefacts are byte-identical
  to the P5 close.
