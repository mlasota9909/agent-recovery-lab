# ADR-P8-2 — Report the measured SC-01 compactness ratio

Status: accepted 2026-08-28

## Context

The P8 manifest and work package repeat an estimated “~140x” SC-01 compactness claim. The hash-pinned corrected J004
source measures median presented bytes of 44,267 for R0 and 1,103 for R2, yielding 40.1333x. A 140x number cannot be
regenerated from the accepted source and must not be reported.

## Decision

Generate and report the exact source-derived ratio (40.1x when rounded to one decimal place). Preserve the qualitative
claim that compactness holds at SC-01 scale and the SC-04 counter-result that it is not universal.

## Consequences

The frozen figure/table manifest is superseded only for the stale scalar. The source query, output, and disaggregated
interpretation do not change.
