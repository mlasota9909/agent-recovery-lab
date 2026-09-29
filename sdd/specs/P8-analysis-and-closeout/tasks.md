# P8 — Tasks

| ID   | Title | Depends on | AC covered |
|------|-------|-----------|------------|
| M001 | Freeze analysis-input contract + figure/table manifest | - | AC-P8-01, AC-P8-02 |
| M002 | Deterministic provenance-blind analysis loader | M001 | AC-P8-03, AC-P8-04 |
| M003 | Generate result figures | M002 | AC-P8-05, AC-P8-06 |
| M004 | Generate result tables | M002 | AC-P8-07, AC-P8-08 |
| M005 | Reserved (outside repository scope) | M003, M004 | AC-P8-09 |
| M006 | Reserved (outside repository scope) | M002 | AC-P8-10 |
| M007 | Close-out: backup prefix, repro manifest, ADR/const index | M002 | AC-P8-11, AC-P8-12, AC-P8-14 |
| M008 | Final gate + project close-out memo | M001-M007 | AC-P8-13, AC-P8-15 |

Run one task per invocation. M003/M004/M006 independent after M002.
