# Spec — P5: Representations R0 / R1 / R2 & the Identical Query Interface

**Feature ID:** P5-representations
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P0/P0.1 (substrate), P1 (results row), P2/P2.1 (certified ledger), P3 (SC-01 incident + analytics +
arm-coordinate contract), P3.1 (read-only gates + regression), P4 (restore+validate harness).
**Blocks:** P6 (Arm B model harness) points a modest local model at this interface; P7 (run matrix) drives R0/R1/R2 at
scale. P5 is where the research contribution is built.

## 1. Purpose

Build three representations of one certified evidence ledger and expose them behind **one query interface that is
identical across all three**. The research claim is that a purpose-built change representation, not model size, is what
makes recovery-point identification tractable for a modest local model. P5 constructs the representations that claim
depends on:

- **R0** — flat chronological event log (the naive representation).
- **R1** — structured temporal ledger with derived per-window aggregates.
- **R2** — a deterministic causal graph plus hierarchical per-window and per-entity summaries (GraphRAG-style
  retrieval, but constructed by fixed rules and templates, never by a model).

The ablation is clean only if a consumer cannot distinguish the representations except by content; the contribution is
only honest if each representation is a deterministic, complete, reconciling, provenance-blind function of the ledger.
Both are enforced mechanically here.

## 2. Background — what already exists

P5 is construction-and-serving over finished, certified infrastructure. Reuse, do not rebuild:

- The P2 append-only ledger and its **default provenance-blind view** (principal-free), and `bin/lab-query`/DuckDB.
- The P2 derived analytics: per-window change-burst density, deletion volume, file churn, and the mean+3sigma anomaly
  score (C5). R1 aggregates and R2 summaries are built from these plus the raw events, not recomputed differently.
- `bin/lab-ledger-account` (reconciliation entry gate); the reconciled **SC-01 incident** (P3).
- `bin/lab-coordinate` (heartbeat->LSN->snapshot; integer LSN, newest snapshot with LSN <= target).
- FROZEN `results-row.md` (`evidence_bytes`, `token_count`) and FROZEN `arm-coordinate.md` (`representation` field).
- `bin/lab-ready`, `bin/lab-reset`, `bin/lab-slot`, `bin/lab-barrier`; `bin/lab-regression`,
  `bin/lab-gate-readonly-check` (P3.1).

P5 adds: the two contracts, the three representation builders, the identical query interface, the determinism/fidelity/
blindness verification, the parity test, the telemetry, the headline, and the gate.

## 3. Scope

### In scope

- Two frozen contracts: `representation-interface.md` (request/response envelope + fixed probe set) and
  `representation-fidelity.md` (determinism / completeness / reconciliation / blindness + the fidelity manifest).
- `bin/lab-repr-r0` — serialize the incident's provenance-blind events to a canonical, ordered flat log.
- `bin/lab-repr-r1` — build the structured temporal ledger with derived per-window aggregates.
- `bin/lab-repr-r2` — build the deterministic causal graph (nodes: sessions, transactions, relations, rows, files,
  processes; edges: caused-by, modified, precedes, depends-on) plus hierarchical per-window and per-entity summaries
  rendered from fixed templates over exact aggregates.
- `bin/lab-repr-query` — the single query interface answering the fixed probe set identically across R0/R1/R2, with
  per-probe telemetry (`evidence_bytes` exact, `token_estimate` via a pinned tokenizer).
- Determinism (byte-identical rebuild), fidelity (R1/R2 reconcile to R0/ledger; no omission, no fabrication),
  provenance-blindness (no principal token), and the identical-interface parity assertion.
- The SC-01 headline: all three answer the recovery-relevant probe faithfully; the R0-vs-R2 evidence-bytes/token delta
  is demonstrated (the contribution measurement).
- `bin/lab-verify-p5` tiered read-only gate; prior contract-hash re-verification; regression; a P5 handoff.

### Out of scope

- Any model invocation or the Arm B harness (that is **P6**). P5 builds the interface a model will later use; it uses
  no model itself.
- SC-02/03/04 representations (later tranches). P5 represents the SC-01 incident realized in P3.
- Any change to a frozen contract, or any new field on the results row / ledger-integrity / arm-coordinate contract.
- Any use of the injection log or oracle optimum in building or querying a representation (Article II).
- Coordinate *selection* (that is Arm A in P3 and Arm B in P6). P5's `PB-6` probe surfaces candidate windows; it does
  not choose the arm's final coordinate.

## 4. Functional requirements

- **FR-1 Contracts + entry gate.** Both P5 contracts are written and hash-frozen. The tranche opens only when
  `bin/lab-ready` exits 0, the target SC-01 incident has passed `bin/lab-ledger-account` exactly-once, and the default
  provenance-blind view is identified and recorded; F001 records all three.
- **FR-2 R0 flat log.** `bin/lab-repr-r0 <incident>` serializes every provenance-blind ledger event for the incident
  to a canonical, strictly LSN-ordered flat log; the event count equals the ledger event count; a fidelity manifest is
  emitted.
- **FR-3 R1 temporal aggregates.** `bin/lab-repr-r1 <incident>` builds the structured temporal ledger with derived
  per-window aggregates whose per-window counts sum exactly to the R0 total; a fidelity manifest is emitted.
- **FR-4 R2 graph + summaries.** `bin/lab-repr-r2 <incident>` builds the causal graph (every edge endpoint exists as a
  node) and hierarchical per-window/per-entity summaries rendered from fixed templates; every summary figure
  reconciles exactly to the underlying events; no model is invoked; a fidelity manifest is emitted.
- **FR-5 Identical query interface.** `bin/lab-repr-query` answers every fixed probe for R0/R1/R2 through one
  request/response envelope; `answer` schema is identical across representations per probe; `content` and `telemetry`
  differ; responses are deterministic on re-run.
- **FR-6 Determinism + fidelity + blindness.** Each representation rebuilds byte-identical; R1/R2 reconcile to
  R0/ledger counts; no principal token appears anywhere; each manifest is admissible per `representation-fidelity.md`.
- **FR-7 Interface parity.** A parity test proves the request/response envelope and probe set are structurally
  identical across R0/R1/R2, differing only in `content` and `telemetry`.
- **FR-8 Telemetry.** Each probe response records exact `evidence_bytes` and a `token_estimate` from a single declared
  pinned tokenizer; telemetry is deterministic; the values land in the results row's `evidence_bytes`/`token_count`
  fields when an arm is scored.
- **FR-9 Headline.** On SC-01, all three representations answer the recovery-relevant probe (`PB-6`/`PB-4`) with an
  answer that faithfully points at the true anomaly window, and R2 presents materially fewer `evidence_bytes` and
  tokens than R0 for that probe — the R0-vs-R2 contribution delta — all read from telemetry.
- **FR-10 Gate + handoff.** `bin/lab-verify-p5` runs every P5 check with per-tier totals and is itself read-only over
  the evidence root; all prior contract hashes re-verify unchanged; `bin/lab-regression` is green; a P5 handoff records
  the three representations, the identical-interface property, the deterministic-construction property, the R0-vs-R2
  delta, and states P6 builds the Arm B model harness consuming this interface.

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P5-01 | M | Both P5 contracts exist, are well-formed (example JSON parses), and are hash-frozen in `logs/review/F001/`; `lab-ready` exit 0, the SC-01 exactly-once reconciliation, and the default provenance-blind view name are recorded as the entry gate |
| AC-P5-02 | M | `bin/lab-repr-r0 <incident>` serializes events in strict integer-LSN order and its `event_count` equals the ledger event count for the incident exactly (no omission, no fabrication) |
| AC-P5-03 | M | `bin/lab-repr-r1 <incident>` produces per-window aggregates whose per-window event counts sum exactly to the R0 total, with deterministic window boundaries |
| AC-P5-04 | M | `bin/lab-repr-r2 <incident>` produces a causal graph in which every edge endpoint exists as a node, and the node/edge sets are a deterministic function of the ledger (rebuild byte-identical) |
| AC-P5-05 | M | Every R2 summary figure reconciles exactly to the underlying events (a summary stating N of some event in window W is backed by exactly N such events), and no model was invoked to build R2 (`built_by_model=false`; build command log has no model call) |
| AC-P5-06 | M | `bin/lab-repr-query` answers all six fixed probes for R0, R1 and R2; each response conforms to `representation-interface.md` (required envelope fields, correct types) and the `answer` schema is identical across the three per probe |
| AC-P5-07 | M | For a fixed probe and incident, the response is byte-identical on re-run for each representation (interface determinism, R7) |
| AC-P5-08 | M | Rebuilding each representation from the same ledger yields a byte-identical artefact; the manifest `content_hash` is unchanged across two builds (determinism, F1) |
| AC-P5-09 | M | Fidelity: R1 aggregates and R2 summaries reconcile to R0/ledger counts; a deliberately corrupted aggregate (off-by-one) is detected and the manifest reports `reconciles=false` |
| AC-P5-10 | M | Provenance-blind: a structured scan and a token scan find no `principal`/`usename`/`session_user`/UID in any R0/R1/R2 artefact, summary or query response; `provenance_blind=true` in every manifest |
| AC-P5-11 | M | Interface parity: the request/response envelope and probe set are structurally identical across R0/R1/R2 (only `content` and `telemetry` differ); a representation that adds a distinguishing structural field to a response is caught by the parity test |
| AC-P5-12 | M | Telemetry: each probe response records `evidence_bytes` equal to the exact UTF-8 byte length of `content`, deterministic on re-run |
| AC-P5-13 | M | Telemetry: each probe response records a `token_estimate` from the single declared pinned tokenizer (name+version recorded); for `PB-6`/`PB-4` (recovery-relevant), R2 `evidence_bytes` and `token_estimate` are strictly less than R0's for the same probe and incident |
| AC-P5-14 | M | **Headline:** on SC-01, R0, R1 and R2 all answer `PB-4-earliest-anomaly` (and `PB-6-candidate-windows`) with an `answer` whose window/coordinate faithfully bounds the true anomaly per the ledger, and R2 presents materially fewer `evidence_bytes`/tokens than R0 for that probe — all read from telemetry and the answer, not prose |
| AC-P5-15 | M | **Discrimination:** a representation built with a dropped anomaly window (omission) or an injected principal (blindness violation) is caught — `event_count`!=ledger or `reconciles=false` or `provenance_blind=false` — proving the fidelity/blindness checks are not rubber stamps |
| AC-P5-16 | M | Representations are incident-scoped: each manifest's `incident_id` is the single reconciled SC-01 incident, and the three representations share it so P6 can group R0/R1/R2 by incident |
| AC-P5-17 | M | `bin/lab-verify-p5` reports every criterion PASS with per-tier totals printed separately, exit 0, and is itself read-only over the evidence root (proven by `bin/lab-gate-readonly-check`) |
| AC-P5-18 | M | All prior gates still green (`lab-verify` 18/18, `-p1` 24/24, `-p1.1` 16/16, `-p2` 18/18, `-p2.1` 16/16, `-p3` 19/19, `-p3.1` 16/16, `-p4` 19/19); every prior contract hash unchanged incl. `capture-completeness.md` byte-identical; `bin/lab-regression` green against pinned fixtures |
| AC-P5-19 | A | The P5 handoff records the three representations, the identical-interface property, the deterministic-construction property, the SC-01 R0-vs-R2 evidence-bytes delta, and states P6 builds the Arm B model harness consuming this interface (asserted on machine-readable fields; anti-goal-inversion guarded) |

Eighteen of nineteen criteria are tier M. The single tier A criterion is the handoff record, which asserts on
machine-readable fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p5` green with per-tier totals and proven read-only; both P5 contracts frozen; R0/R1/R2 built as
deterministic, complete, reconciling, provenance-blind functions of the SC-01 ledger, each with an admissible fidelity
manifest; the query interface answering all six probes identically across the three with only `content`/`telemetry`
differing, proven by the parity test and byte-identical on re-run; telemetry recording exact `evidence_bytes` and a
pinned-tokenizer `token_estimate`, with R2 < R0 on the recovery-relevant probe; the headline showing all three point
faithfully at the true SC-01 anomaly window while R2 presents far fewer bytes than R0; the discrimination negative
proving fidelity/blindness are enforced; all prior gates, regression and contract hashes unchanged; the P5 handoff
written without anti-goal inversion.
