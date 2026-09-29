# P8 — Plan

## Design stance
P8 is downstream-only. It never mutates the experiment. Its integrity property is the analysis
analogue of every prior tranche's discipline: numbers are regenerated from source, not transcribed;
only the active partition is consumed; the validity partition rides beside every aggregate.

## Task graph
- M001 Freeze analysis-input contract + figure/table manifest (two frozen artefacts).
- M002 Build deterministic, provenance-blind analysis loader (active-partition filter).
- M003 Generate result figures.           (independent after M002)
- M004 Generate result tables.            (independent after M002)
- M005, M006 Reserved; outside the scope of this repository.
- M007 Close-out: backup-prefix rename, reproducibility manifest, ADR/constitution index.
- M008 Final gate + project close-out memo.

## Architecture decisions
- ADR-P8-1  Analysis reads results/*.jsonl active tails only; never results/fixtures/ and never
            superseded rows. Loader enforces; refusal is a hard error, not a warning.
- ADR-P8-2  Figures/tables are pure functions of loader output + pinned matplotlib/pandas config;
            re-run must be byte-identical (seedless, sorted, fixed fonts/dpi). Any nondeterminism
            (timestamps in metadata) is stripped to a fixed value.
- ADR-P8-3  Provenance-blindness carried forward: the comparison loader view excludes `principal`
            and any answer-key coordinate field; only bytes/tokens/verdict/refusal are exposed.
- ADR-P8-4  Backup-prefix rename is a reversible tooling change (thesis-p1-* -> thesis-*); the old
            dated backup is retained; byte-identity to latest is asserted before and after.
- ADR-P8-5  If P8 analysis surfaces a defect class the gates missed, that becomes Article XXI via
            the standard remediation path; P8 itself is a forward build under the twenty in force.

## Anti-goals (do NOT do here)
- Do NOT re-run the experiment, regenerate scenarios, or touch ledgers/coordinates.
- Do NOT promote SC-03/SC-04 to P4-validated.
- Do NOT compute a single blended "R2 wins" headline; keep actionability and compactness separate.
- Do NOT transcribe any reported number by hand — generate it.

## Note to the next agent (anti-inversion)
This is the terminal build tranche. There is no P9 experiment to defer to. The only thing that
follows P8 is human review of the generated outputs. Do not copy an anti-goal forward
as if a later tranche exists.
