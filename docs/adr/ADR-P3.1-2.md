# ADR-P3.1-2 — Regression runs against pinned fixtures, not the live headline

**Status:** accepted  
**Date:** 2026-08-24  
**Tranche:** P3.1  
**Related:** ADR-P3.1-1 (D2), Article XVI

## Decision

The valid intent behind `AC-P3-18` is "prove the prior instruments still work after new code lands." The wrong implementation was to run them against the one incident that must stay frozen.

**Fix.** Capture, once, a small real incident per prior tranche, reconcile it clean (`gaps=0`, `duplicates=0`), and hold it **read-only** under `fixtures/regression/<tranche>/` as that tranche's regression fixture. `bin/lab-regression` places each fixture into the live-equivalent state its gate expects (working copies under `logs/review/`, never under the evidence root) and runs the gate against it. The headline incident is never used for regression.

Fixtures are synthetic lab data (Article X). They are captured through the normal pipeline, not hand-authored, so a gate exercising a fixture exercises real artefacts.

## Why per-tranche fixtures rather than one shared fixture

Each gate expects a different lab state:

- P0 `lab-verify` wants a live draining slot (consumer active, retained WAL below threshold).
- P1/P1.1 want a registered incident with oracle artefacts and a ledger that `lab-ledger-verify` will accept.
- P2/P2.1 want a reconciled ledger (exactly-once mapping).
- P3 wants analytics inputs over a closed, reconciled SC-01-shaped ledger — but **not** the headline, whose numbers are frozen.

One fixture cannot satisfy all simultaneously. That confusion produced D2. Separate fixtures keep each gate's precondition honest.

## Live-equivalent state without mutating evidence

`bin/lab-regression` copies a fixture into `logs/review/<id>/scratch/<tranche>/` and points `EVIDENCE_ROOT` / `ARCHIVE_*` at that scratch tree for the gate subprocess. Consumer WAL, if needed, appends in scratch. The real evidence root, including the SC-01 headline, is byte-identical before and after (ADR-P3.1-3).
