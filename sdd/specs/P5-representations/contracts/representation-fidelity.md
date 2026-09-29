# FROZEN CONTRACT — Representation Fidelity (determinism, completeness, reconciliation, blindness)

**Contract ID:** representation-fidelity
**Frozen by:** F001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV).
**Produced by:** each representation builder (F002/F003/F004) emits a fidelity manifest; verified in F006.
**Consumed by:** the F006 fidelity checks, the F009 headline, and the operator.

## 1. Purpose

A representation is only admissible as an experimental treatment if it is an honest, reproducible function of the
ledger. This contract states the properties every representation must satisfy and the manifest each must emit so those
properties are mechanically checkable. Without this, a representation could appear to "help the model" simply because
it silently dropped the confusing legitimate traffic, or invented an anomaly, or leaked the principal — any of which
would make the ablation meaningless.

## 2. Hard rules (every representation must satisfy all six)

- **F1 — determinism.** A representation is a pure, deterministic function of the reconciled ledger for one incident.
  Rebuilding it from the same ledger yields a **byte-identical** artefact. No timestamps-of-build, no random ordering,
  no model. `content_hash` in the manifest is the SHA-256 of the canonical artefact and is stable across rebuilds.
- **F2 — completeness (no omission).** Every event in the reconciled ledger for the incident is represented. For R0
  the serialized event count equals the ledger event count exactly. R1 and R2 derive from the same event set; none may
  silently drop events.
- **F3 — reconciliation (no fabrication).** Every aggregate in R1 and every count asserted in an R2 summary reconciles
  **exactly** to the underlying R0/ledger events. A summary stating "N deletes in window W" must be backed by exactly
  N delete events in window W. `reconciles=true` means every aggregate and every summary figure was checked against the
  events and matched.
- **F4 — provenance-blind (Article II).** No `principal`, `usename`, `session_user` or UID token appears anywhere in
  the artefact, any summary, any node/edge label, or any field. Built only from the default provenance-blind ledger
  view. `provenance_blind=true` means a structured scan and a token scan both found none.
- **F5 — no model in construction (Article I/V).** No language model or ML inference is invoked to build any
  representation. R2 summaries are rendered from fixed string templates over exact aggregates. `built_by_model=false`
  is mandatory; the command log for the build contains no model invocation.
- **F6 — incident-scoped.** One representation set per `incident_id`. A representation never blends events from two
  incidents. `incident_id` in the manifest names the single incident represented.

## 3. Fidelity manifest schema (one JSON object per representation per incident)

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | the single incident represented (F6) |
| `representation` | string | `R0` / `R1` / `R2` |
| `builder_version` | string | the exact builder that produced the artefact |
| `source_ledger_hash` | string | SHA-256 of the reconciled ledger the representation was built from |
| `content_hash` | string | SHA-256 of the canonical representation artefact (stable across rebuilds — F1) |
| `event_count` | integer | events represented; for R0 equals the ledger event count (F2) |
| `ledger_event_count` | integer | events in the source ledger for this incident (F2 comparison basis) |
| `reconciles` | boolean | every R1 aggregate / R2 summary figure matched the underlying events (F3) |
| `provenance_blind` | boolean | no principal token anywhere (F4) |
| `built_by_model` | boolean | MUST be `false` (F5) |

## 4. Admissibility

A representation is **admissible** for use as an experimental treatment (i.e. usable by P6/P7) iff its manifest has:
`event_count == ledger_event_count`, `reconciles=true`, `provenance_blind=true`, `built_by_model=false`, and a
`content_hash` that reproduces on rebuild. Any representation failing any of these is rejected by the harness and must
not be fed to a model. This is the machine-readable definition of "an honest representation".

## 5. Example (illustrative, non-normative)

```json
{
  "incident_id": "SC-01-20260825T0100Z-a1",
  "representation": "R2",
  "builder_version": "p5-repr-r2-1",
  "source_ledger_hash": "sha256:4d1a...",
  "content_hash": "sha256:9c02...",
  "event_count": 5127,
  "ledger_event_count": 5127,
  "reconciles": true,
  "provenance_blind": true,
  "built_by_model": false
}
```

## 6. Change control

Frozen at F001 and hash-recorded in `logs/review/F001/`. Later changes supersede via
`representation-fidelity.amendment-N.md` with its own ADR; this file stays byte-identical (Article XV).
