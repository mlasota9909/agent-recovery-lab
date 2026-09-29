# Spec — P1: Ground Truth, Results Contract and Run Harness

**Feature ID:** P1-ground-truth-harness
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P0 (accepted after P0.1 remediation)
**Blocks:** P2 (capture collectors), P3 (analytics + Arm A ranker), P4 (restore + validation), P6 (Arm B harness)

## 1. Purpose

Build the **instruments**, not the intelligence. P1 delivers the ground-truth oracle, the results row, the ledger
integrity assertions and the two-phase run harness. Every reported number is produced through what
this tranche freezes.

P1 contains no analytics, no ranking function, no representations and no model. It ends with a **null run**: a
complete end-to-end execution using a stub analysis component, appending a schema-valid results row containing the
ground-truth optimum.

## 2. Problem statement

Three failures are prevented by building this before any analysis logic exists.

**Subjective scoring.** Single-reviewer scoring is subjective, and "correct" recovery needs a defined
adjudication. Because the incident is scripted, the optimal coordinate is *known*, and every
result can be an objective distance from it rather than an author-assigned score on an ordinal scale.

**Confounded ablation.** The research claim is a comparison of representations at fixed scenario and fixed model. If
each arm regenerates its own baseline and its own concurrent legitimate workload, the arms differ by more than the
representation and the comparison is worthless. The harness must therefore separate *generating* an incident from
*evaluating* an arm against it, so one incident can be replayed to many arms over byte-identical evidence.

**Plausible-but-wrong analysis.** Analysis code can look right and still be wrong. The oracle
and the results logger are the test harness that catches this, so they must exist first. This project is about
agent-induced failure; it must not be undone by one.

A fourth, discovered during P0.1 review: the replication slot lives in `PGDATA` and therefore **rewinds** on a T1 or
T2 reset, while the host-side ledger is append-only and does **not**. Reset therefore desynchronises slot position
from ledger contents, and whether that yields duplicated or orphaned LSN ranges currently depends on incident-scoping
discipline being followed perfectly by hand. P1 makes it a mechanical assertion.

## 3. Scope

### In scope

- The **results row contract**: every field, type, unit and nullability rule, frozen.
- The **ledger integrity contract**: per-incident LSN idempotency and range containment, frozen.
- The **ground-truth oracle**: computation of the optimal coordinate for SC-01 from the injection log, the
  `pre_injection` snapshot and the recorded LSN bounds, plus the manifest needed to score outcome error.
- The **legitimate-work manifest**: what the concurrent workload committed, so retained good work can be scored.
- SC-01's **steady-state workload** and **injector**, as separate identities (`lab_app`, `lab_agent`), sufficient to
  generate one real incident. No other scenario's damage logic.
- The **two-phase harness**: `lab-generate-incident` and `lab-evaluate-arm`, with an incident id as the join key.
- A **reset barrier** that mechanically waits for consumer catch-up instead of relying on an operator instruction.
- A **stub analysis component** with a deliberately trivial strategy, used to prove the instrument end to end.
- A **stub restore/validate** sufficient for the loop-closing assertion; real restore is P4.
- **Re-measurement of full-cycle time** post-reset-guard, and a stratified sample-size plan derived from it.
- Results storage as append-only JSONL on the host, queryable in place.

### Out of scope

- Derived analytics, change-burst density, anomaly scoring, candidate generation, the ranking function (P3).
- The naive comparator's calibration; P1 records the field, P3 populates it meaningfully.
- Representations R0/R1/R2 and any retrieval interface (P5).
- Any language model (P6). Nothing in P1 may call a model.
- Real point-in-time restore into a sandbox and row/byte validation (P4). P1 stubs these behind the same interface.
- SC-02, SC-03 and SC-04 damage logic (P8).
- Physical air-gap, WORM immutability, tamper-evident logging (recorded limitation, not built).

## 4. Requirements

### FR-1 Results row contract
FR-1.1 A single frozen contract MUST define every results field, its type, its unit and whether it may be null.
FR-1.2 The row MUST carry `incident_id` so arms and replicates group correctly during analysis; without it the
ablation is not analysable.
FR-1.3 The row MUST carry both **coordinate error** (LSN distance and wall-clock distance) and **outcome error**
(legitimate rows and bytes lost, damaged rows and bytes retained), because a coordinate can be near-optimal and still
produce a bad outcome.
FR-1.4 The row MUST carry the naive-comparator coordinate and its errors in the same row, so every run is legible
against the baseline it must beat.
FR-1.5 The row MUST carry telemetry that the later ablation depends on: `evidence_bytes_presented` and
`token_count`, nullable in P1 and populated from P5 onward.
FR-1.6 The row MUST carry provenance of the run itself: harness commit hash, reset tier used, `pre_injection` and
`post_capture` snapshot names, run timestamp, and the arm/ranker/model identifier.
FR-1.7 Rows MUST be appended, never mutated. A results file, once written, is read-only.
FR-1.8 A schema validator MUST exist and MUST reject a row with a missing required field, a wrong type, or an
out-of-range value. It MUST NOT coerce.

### FR-2 Ledger integrity across reset
FR-2.1 Within one incident, no LSN may appear more than once in the ledger.
FR-2.2 The ledger's LSN range MUST be contained within the incident's recorded open and close coordinates.
FR-2.3 An integrity CLI MUST assert FR-2.1 and FR-2.2 and exit non-zero on violation.
FR-2.4 Evidence capture MUST NOT begin until the consumer has caught up after a reset. This MUST be a mechanical
barrier in the harness, not an operator instruction.
FR-2.5 A T1 or T2 reset MUST leave the host-side ledger, WAL archive and results store intact.

### FR-3 Ground-truth oracle
FR-3.1 For SC-01 the optimum MUST be computed as the commit LSN of the last legitimate transaction before the
malicious DELETE, resolved into a full coordinate triple per the frozen `coordinate.md`.
FR-3.2 The oracle MUST be deterministic: recomputing it over the same frozen incident MUST produce a byte-identical
coordinate.
FR-3.3 The oracle MAY read provenance fields; it is the only component permitted to (Article II).
FR-3.4 The oracle MUST emit a **manifest** sufficient to score outcome error: the set of legitimately committed rows
at the optimum and the set of rows the injection destroyed.
FR-3.5 The oracle MUST fail non-zero rather than guess if the injection log is absent, incomplete, or inconsistent
with the ledger.
FR-3.6 The oracle MUST record which inputs it used, so a reader can audit how the optimum was derived.

### FR-4 Legitimate-work manifest
FR-4.1 The steady-state workload MUST record what it committed, with commit LSN, as it runs.
FR-4.2 The manifest MUST allow "legitimate rows lost" to be computed exactly, not estimated.
FR-4.3 Workload rate and mix MUST be recorded per incident so runs are comparable.
FR-4.4 Some legitimate commits MUST land in the seconds immediately before and after the injection; this is what
makes "just restore earlier" costly and the problem non-trivial.

### FR-5 Two-phase harness
FR-5.1 `lab-generate-incident` MUST perform, in order: reset, baseline capture, workload start, `pre_injection`
snapshot, injection, capture stop, `post_capture` snapshot, incident registration.
FR-5.2 `lab-evaluate-arm` MUST perform, in order: reset to the requested tier, analysis (stub in P1), restore and
validate (stub in P1), results append.
FR-5.3 `lab-evaluate-arm` MUST be re-runnable any number of times against the same `incident_id`.
FR-5.4 Re-running `lab-evaluate-arm` against the same incident MUST produce a **byte-identical ground-truth
coordinate** in every appended row. This is the assertion that proves the fixed-incident property holds.
FR-5.5 The harness MUST refuse to evaluate an arm against an incident whose integrity assertions fail.
FR-5.6 The harness MUST stop PostgreSQL before invoking reset, per the P0.1 guard, and confirm the cluster is back up
afterwards.

### FR-6 Stub components
FR-6.1 The analysis stub MUST implement the same interface the P3 ranker will implement, so P3 is a substitution and
not a rewrite.
FR-6.2 The analysis stub MUST NOT read provenance fields, and a negative test MUST prove this by stripping provenance
and asserting the selected coordinate is unchanged (Article II).
FR-6.3 The restore/validate stub MUST implement the P4 interface and MUST report an explicit `stub` verdict, never a
fabricated clean result.

### FR-7 Throughput and sampling
FR-7.1 Full-cycle time MUST be re-measured **after** the P0.1 reset guard, separately for generate-incident and
evaluate-arm, since the guard added a cluster stop/start that the inherited 49.335 s figure predates.
FR-7.2 A stratified sample-size plan MUST be derived from the measured cycle times and recorded as a machine-readable
artefact, replacing an open-ended sample target.
FR-7.3 The plan MUST state per-cell replicate counts and the total run count, with the time budget that justifies it.

### NFR
NFR-1 Every capability is a CLI under `bin/`, text in, JSON out (Article IV).
NFR-2 Every script idempotent; pre-existing correct state reported as `"changed": false`.
NFR-3 POSIX shell, SQL, Python 3 only. No new runtime dependency beyond DuckDB for in-place querying.
NFR-4 No outbound network calls. No model invocation anywhere in P1.
NFR-5 Nothing outside `/home/mlasota/thesis` written on the host.

## 5. Acceptance criteria

Tier per Article XIII. **Tier M** = mechanically re-derived. **Tier A** = attested against a machine-readable field.

| AC | Tier | Criterion |
| --- | --- | --- |
| AC-P1-01 | M | `contracts/results-row.md` exists; a validator rejects a row missing a required field, one with a wrong type, and one with an out-of-range value |
| AC-P1-02 | M | Validator does **not** coerce: a string where an integer is required fails rather than being cast |
| AC-P1-03 | M | Results file is append-only and mode 0444 once closed; an attempted in-place edit fails |
| AC-P1-04 | M | `bin/lab-ledger-verify` detects a deliberately duplicated LSN within an incident and exits non-zero |
| AC-P1-05 | M | `bin/lab-ledger-verify` detects a ledger LSN outside the incident's open/close range and exits non-zero |
| AC-P1-06 | M | The reset barrier blocks until `lab-slot --check` exits 0; with a stopped consumer the barrier times out non-zero rather than proceeding |
| AC-P1-07 | M | A T1 reset leaves ledger, archive and results byte-identical (hash compared before and after) |
| AC-P1-08 | M | SC-01 workload manifest records every legitimate commit with its LSN; count matches the database |
| AC-P1-09 | M | At least one legitimate commit lands within 2 s before, and one within 2 s after, the injection commit |
| AC-P1-10 | M | Oracle emits a coordinate triple valid against the frozen `coordinate.md`, all six required fields correct types |
| AC-P1-11 | M | Oracle optimum equals the commit LSN of the last legitimate transaction before the injection, cross-checked independently from the workload manifest |
| AC-P1-12 | M | Oracle recomputed over the same frozen incident produces a **byte-identical** coordinate |
| AC-P1-13 | M | Oracle exits non-zero when the injection log is removed; it does not guess |
| AC-P1-14 | M | Oracle manifest allows exact computation of legitimate rows at optimum and rows destroyed by injection |
| AC-P1-15 | M | `lab-generate-incident` completes end to end and registers an incident id; all seven ordered steps evidenced |
| AC-P1-16 | M | `lab-evaluate-arm` appends one schema-valid results row containing the ground-truth optimum |
| AC-P1-17 | M | A second `lab-evaluate-arm` against the same `incident_id`, without regenerating, appends a row whose ground-truth coordinate is byte-identical to the first |
| AC-P1-18 | M | Harness refuses to evaluate an arm when `lab-ledger-verify` fails |
| AC-P1-19 | M | Analysis stub's selected coordinate is unchanged when provenance fields are stripped from its input view |
| AC-P1-20 | M | Restore/validate stub reports verdict `stub`; no code path can emit a clean verdict in P1 |
| AC-P1-21 | M | Generate-incident and evaluate-arm cycle times measured post-reset-guard, recorded in JSON, not inherited |
| AC-P1-22 | A | Sample-size plan artefact exists stating per-cell replicates, total N, and the time budget; asserted on JSON fields |
| AC-P1-23 | M | Every P1 CLI is idempotent: a second invocation reports `"changed": false` and mutates nothing |
| AC-P1-24 | M | The three P0 contracts are unchanged, verified by SHA-256 against `logs/review/R007/contracts-unchanged.md` |

## 6. Traceability

| Requirement group | Serves | Rationale |
| --- | --- | --- |
| FR-3, FR-4 | SC-01; RQ5 | the optimum is computed, not judged |
| FR-1 | All scenarios; results | every metric is a named field tied to an RQ |
| FR-5 | Ablation validity | the comparison is objective distance, and arms share one incident |
| FR-7 | Run matrix | sample size is a measured, stratified plan |
| FR-2 | Evidence credibility | integrity is asserted mechanically |
| FR-6.2 | Experimental validity | Provenance leak would invalidate the entire experiment |

## 7. Known limitations

1. Restore and validation are stubbed in P1; the loop-closing test that feeds the known-correct coordinate into a
   real restore is P4's acceptance criterion. Until then no claim about recovery correctness is supported.
2. The oracle is scenario-specific by design. SC-01 has a single clean optimum; SC-03 and SC-04 deliberately do not,
   and their oracles must define a different optimum (earliest malicious commit plus a corrupted-row set). P1 builds
   only SC-01's.
3. Cycle-time measurement is taken on an otherwise idle host. Concurrent load would reduce throughput, so the
   sample-size plan states a floor rather than a guarantee.
4. `token_count` and `evidence_bytes_presented` are present but null through P1–P4; they become meaningful in P5.
