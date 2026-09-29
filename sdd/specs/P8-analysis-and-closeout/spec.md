# P8 — Analysis Outputs & Project Close-out — Specification

## Purpose
Turn the frozen, P7.1-validated results into reproducible analysis outputs and close the project.
P8 is the bridge from a proven experimental apparatus to its reported results, plus the
housekeeping that makes the whole build reproducible.

## Background (state at P8 entry)
- Results file: 116 physical rows; active partition = 51 (25 determinations, 25 refusals,
  1 diagnosed run_failure). Superseded/hollow rows retained for provenance, excluded from
  aggregates.
- Coordinate schema carries `resolved_by in {lsn_first, snapshot_first, time_first, live_heartbeat}`
  (ADR-P7.1-6); schema digest 103eaa92 pinned in 19 gate/reverify files.
- Validated scenarios: SC-01 (P4-validated headline), SC-02 (P4-validated). Supporting:
  SC-03, SC-04 (set-validated: precision/recall + earliest-safe bound + legitimate-DML sacrifice).
- SC-01 arm result: R2 5/5 determinations (refusal 0.0), R0 1/5 (0.8), R1 0/5 (1.0).
- Headline is disaggregated: actionability (R2 enables action, R0 mostly refuses, R1 refuses)
  vs compactness (R2 40.1x smaller than R0 at SC-01 scale; larger than R0 on tiny SC-04 —
  documented counter-result, compactness_holds=false for SC-04).

## Functional requirements
- FR-1  A frozen analysis-input contract defines exactly which rows are consumable (active
        partition), and mandates that every aggregate carries the validity partition and
        supersession provenance.
- FR-2  A frozen figure/table manifest lists every reported artefact, its source query, and
        its regeneration command. No result is reported that is not in the manifest.
- FR-3  A deterministic analysis loader reads the results file, applies the active-partition
        filter, refuses to aggregate superseded/hollow rows, and is provenance-blind for
        representation-comparison outputs.
- FR-4  All result figures are generated from the loader output by code; each is regenerable
        byte-identically and traces to named rows.
- FR-5  All result tables are generated the same way (matrix summary, per-scenario verdicts,
        R0/R1/R2 comparison, refusal rates).
- FR-6  Reserved; outside the scope of this repository.
- FR-7  Reserved; outside the scope of this repository.
- FR-8  Close-out: tranche-neutral backup prefix (reversible tooling fix), a consolidated
        ADR + constitution index, and a reproducibility manifest (env, versions, weights hash,
        seeds, commit) sufficient to re-run the whole pipeline.
- FR-9  A final gate re-verifies all prior frozen hashes, the active-partition arithmetic, and
        that every reported number regenerates from source; produces the project close-out memo.

## Acceptance criteria (tier M = mechanically re-derived, tier A = attested on machine-readable field)
- AC-P8-01 (M) analysis-input contract frozen; hash recorded; example query returns exactly the
           51 active rows and refuses on a superseded row.
- AC-P8-02 (M) figure/table manifest frozen; every entry has a source query + regen command;
           manifest hash recorded.
- AC-P8-03 (M) loader returns 51 active rows from 116 physical; partition = {det:25, ref:25, fail:1};
           negative test: injecting a superseded row into the aggregate set makes the loader refuse.
- AC-P8-04 (M) loader is provenance-blind for comparison outputs; negative test: exposing `principal`
           to a comparison figure input makes the guard fire.
- AC-P8-05 (M) every result figure regenerates byte-identically on re-run; each carries its source
           row ids and the validity partition.
- AC-P8-06 (M) SC-01 actionability figure reproduces R2 5/5, R0 1/5, R1 0/5 from the rows.
- AC-P8-07 (M) compactness table shows R2 40.1x < R0 at SC-01 and R2 > R0 at SC-04 with
           compactness_holds=false for SC-04; both derived from row bytes/tokens.
- AC-P8-08 (M) per-scenario verdict table labels SC-01/SC-02 P4-validated and SC-03/SC-04
           set-validated; negative test: relabelling SC-03 as P4-validated fails the check.
- AC-P8-09 (A) reserved; outside the scope of this repository.
- AC-P8-10 (A) reserved; outside the scope of this repository.
- AC-P8-11 (M) reproducibility manifest present and complete (model id+quant+weights sha256,
           seed, decoding params, commit, env, ZFS/pg versions); a missing required field fails.
- AC-P8-12 (M) backup prefix is tranche-neutral; dated backup and latest are byte-identical
           (same sha256); negative test: a mismatched pair fails.
- AC-P8-13 (M) all prior frozen contract hashes re-verify unchanged (including schema 103eaa92).
- AC-P8-14 (M) ADR/constitution index lists all twenty articles and every ADR file; a missing
           ADR file referenced by an amendment fails the index check.
- AC-P8-15 (M) close-out memo generated; records tier totals, validity partition, and the
           final validated headline; no undifferentiated pass total.
