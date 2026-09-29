# ADR-P8-1 — Hash-pinned corrected SC-01 batch supplements the active matrix

Status: accepted 2026-08-28

## Context

P8 must regenerate the accepted SC-01 actionability result (R2 5/5, R0 1/5, R1 0/5). The results ledger is banked
and byte-frozen but predates the P6.1 J004 answerability rerun. L005 therefore correctly established the J004 batch as
the SC-01 result of record. The P8 analysis-input contract, frozen at M001, otherwise limits consumption to active
matrix tails, which contain SC-02/03/04 only.

## Decision

Keep the 51-row active matrix rule unchanged for every matrix aggregate. Add one narrowly scoped supplemental source:
the three hash-pinned J004 `replicates.json` files, only for SC-01 headline/actionability, compactness, and coordinate
error outputs. Every such artefact carries both the matrix validity partition and explicit J004 source identifiers and
hashes. No evidence or result row is migrated or relabelled.

## Consequences

The corrected accepted headline is regenerable without rewriting historical rows. Any hash drift in J004 fails the
loader. No other review artefact becomes an analysis input.
