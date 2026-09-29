# ADR-P5.1-2 — Split `model_view` from `reference` by supersession

**Status:** accepted
**Date:** 2026-08-25
**Tranche:** P5.1
**Related:** ADR-P5.1-1 (the confound), ADR-P5.1-3 (guard), Article XV, Article XVII

## Decision

Do not delete `answer`. Move it out of the subject-visible surface.

The `answer` object is useful: it is the parity reference that confirms all three representations are asked to support the same result, and it anchors telemetry. The defect is only that it lives in the same envelope a subject might be shown.

By Article XV the frozen `representation-interface.md` is not mutated. `representation-interface.amendment-1.md` defines two projections over the unchanged internal envelope produced by `bin/lab-repr-query`:

- **`model_view`** = `{incident_id, representation, probe_id, params, content, telemetry}` — the **only** object P6 may pass to a model. It carries no `answer`.
- **`reference`** = `{incident_id, representation, probe_id, answer}` — used solely by parity and telemetry tests, never handed to a subject.

`bin/lab-repr-modelview` emits the first; `bin/lab-repr-reference` emits the second. Both are thin wrappers over `bin/lab-repr-query`. `bin/lab-repr-query` (F005) stays byte-identical so frozen F005 review artefacts remain valid and no representation logic is re-implemented.

## Consequences

P6 MUST consume `bin/lab-repr-modelview` (and pass the result through `bin/lab-modelview-guard`) as its only model input. Using the full query envelope is an Article XVII violation.
