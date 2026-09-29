# Spec — P3: Derived Analytics & the Arm A Deterministic Ranker

**Feature ID:** P3-analytics-ranker
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P1 (accepted), P2 (accepted), P2.1 (accepted; reconciliation sound under repeated keys)
**Blocks:** P4 (restore + validation) consumes the chosen coordinate; P5 (representations) and P6 (Arm B) are
measured against Arm A.

## 1. Purpose

Build the first layer of intelligence over the certified ledger: deterministic **derived analytics** (C5) and the
**Arm A deterministic ranker** (C7), plus the **naive comparator**. On a real SC-01 incident, Arm A must select a
recovery coordinate whose recovery-point error is materially lower than the naive comparator's, with both numbers
produced automatically by the P1 oracle and written to the results row. Everything here is deterministic,
reproducible, and provenance-blind: it is the reproducible baseline the whole experiment is measured against.

## 2. Background — what already exists

P3 is analytics and wiring over finished infrastructure. Reuse, do not rebuild:

- `bin/lab-query` — no-ETL DuckDB views over the ledger; **default views already exclude `principal`** (P2 AC-P2-14).
- `bin/lab-ledger-account` — exactly-once reconciliation; the mandatory entry gate before analytics (ADR-P2-7).
- `bin/lab-coordinate` — heartbeat→LSN→snapshot resolution (ADR-008), used to resolve every candidate's snapshot/skew.
- P1 ground-truth oracle + the two-phase `generate-incident` / `evaluate-arm` harness + `results-row.md` (FROZEN).
- P2 `bin/lab-capture`, `bin/lab-capture-workload` (generic mixed workload), snapshot loop, DDL audit.
- `bin/lab-ready`, `bin/lab-reset`, `bin/lab-slot`, `bin/lab-barrier`.

P3 adds: the SC-01 incident realization (a real injector + a concurrent repeated-key workload profile), the analytics
engine, candidate generation, the deterministic ranker, the naive comparator, and the wiring that lands both arms'
errors in the results row.

## 3. Scope

### In scope

- Two frozen contracts: `candidate-coordinate.md` (C5 output) and `arm-coordinate.md` (the shape every arm emits).
- **SC-01 realized as a reconciled incident** (bounded; SC-02..04 deferred): `bin/lab-inject-sc01` (destructive bulk
  DB record deletion, near-instant, as `lab_agent`) writing an injection log with the exact ops and wall-clock/LSN
  damage window; an SC-01 concurrent legitimate workload profile (as `lab_app`, with repeated keys so the P2.1
  concurrency regime is exercised); and the oracle parameters that make the SC-01 ground-truth optimum computable.
- `bin/lab-analytics` — per-window change-burst density, per-relation and per-path churn, deletion-volume spikes and
  DDL flags over the ledger via DuckDB, all provenance-blind.
- mean+3σ anomaly scoring against a **declared quiescent baseline window** recorded in the incident manifest.
- `bin/lab-candidates` — candidate recovery-coordinate generation emitting the frozen candidate schema.
- `bin/lab-rank` — the Arm A deterministic ranking function: declared feature weights and tie-breaks, emitting the
  frozen arm-coordinate shape; fully reproducible.
- `bin/lab-naive` — the naive comparator: last checkpoint before an approximate operator-supplied incident time, with
  a **declared, fixed** incident-time error read from scenario config.
- Wiring Arm A and naive into the P1 `evaluate-arm` phase so both recovery-point errors (LSN and rows/bytes) are
  scored by the oracle and land in the results row automatically.
- `bin/lab-verify-p3` tiered gate; re-verification of all prior contract hashes; a P3 architecture handoff.

### Out of scope

- Any change to a frozen contract, or any new field on the results row or ledger-integrity contract.
- Representation building R0/R1/R2 and the query interface for Arm B (that is **P5**).
- Any model invocation or Arm B harness (that is **P6**).
- Real point-in-time restore or restored-state validation (that is **P4**); P3 scores coordinates via the oracle,
  it does not restore.
- SC-02, SC-03, SC-04 injectors and their oracle tuning (later tranches). P3 realizes **only** SC-01.
- Any use of the provenance label, injection log or oracle optimum as a detection or ranking input (Articles I/II).

## 4. Functional requirements

- **FR-1 Contracts + entry gate.** Both P3 contracts are written and hash-frozen. The tranche opens only when
  `bin/lab-ready` exits 0 **and** the target incident has passed `bin/lab-ledger-account`; D001 records both facts.
- **FR-2 SC-01 incident.** `bin/lab-inject-sc01` applies a destructive bulk DELETE as `lab_agent` and records an
  injection log (exact ops, wall-clock/LSN damage window). The SC-01 workload runs concurrent legitimate activity as
  `lab_app` with repeated keys. A full SC-01 incident is generated (P1 harness) and passes reconciliation exactly-once.
- **FR-3 Analytics.** `bin/lab-analytics <incident>` computes, from the provenance-blind ledger views: per-window
  change-burst density, per-relation and per-path churn, deletion-volume spikes, and a DDL flag per window. Output is
  deterministic (two runs byte-identical) and written as a machine-readable artefact.
- **FR-4 Anomaly scoring.** mean+3σ scoring is computed against the quiescent baseline window declared in the incident
  manifest (a window that predates injection). The SC-01 deletion window scores anomalous; a quiescent window does not.
- **FR-5 Candidates.** `bin/lab-candidates <incident>` emits candidate records per `candidate-coordinate.md`: each
  carries integer + text LSN, resolved snapshot, skew, and the deterministic feature scores; no provenance field.
- **FR-6 Ranker (Arm A).** `bin/lab-rank <incident>` scores candidates with declared weights and tie-breaks
  (tie-break: latest safe integer LSN) and emits one `arm-coordinate` record with `arm=arm_a`, a deterministic
  rationale, and a `selection_inputs` audit block whose `read_injection_log`, `read_oracle_optimum` and
  `read_provenance` are all `false`. Same ledger → byte-identical chosen coordinate.
- **FR-7 Naive comparator.** `bin/lab-naive <incident>` selects the last checkpoint before
  `approx_incident_time + declared_error`, reading the error from scenario config, and emits an `arm-coordinate`
  record with `arm=naive`. The error parameter is fixed and declared; it is never tuned to disadvantage naive.
- **FR-8 Wiring.** The P1 `evaluate-arm` phase runs for `arm_a` and for `naive`, the oracle scores each chosen
  coordinate, and both recovery-point errors (LSN and rows/bytes) land in schema-valid results rows automatically.
- **FR-9 Headline + negatives.** On the SC-01 incident, Arm A's recovery-point error is strictly lower than naive's
  on the primary metric; the provenance-blindness negative test passes (stripping provenance leaves Arm A's coordinate
  unchanged); the no-peek audit confirms no arm read the injection log or oracle optimum.
- **FR-10 Gate + handoff.** `bin/lab-verify-p3` runs every P3 check with per-tier totals; all prior contract hashes
  re-verify unchanged; a P3 handoff documents the analytics feature set, the ranker weights/version, the SC-01 result,
  and correctly states P5 builds R0/R1/R2 and P6 builds Arm B.

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P3-01 | M | Both P3 contracts exist, are well-formed, and are hash-frozen in `logs/review/D001/`; `lab-ready` exit 0 and the target incident's exactly-once reconciliation are recorded as the entry gate |
| AC-P3-02 | M | `bin/lab-inject-sc01` applies a destructive bulk DELETE as `lab_agent` and writes an injection log with exact ops and the wall-clock/LSN damage window; it runs only inside the lab |
| AC-P3-03 | M | The SC-01 workload runs concurrent legitimate activity as `lab_app` with repeated keys; a full SC-01 incident is generated and passes `bin/lab-ledger-account` exactly-once (0 gaps, 0 duplicates) |
| AC-P3-04 | M | `bin/lab-analytics` computes per-window burst density, per-relation and per-path churn, and deletion-volume spikes over the ledger; two runs are byte-identical |
| AC-P3-05 | M | A DDL flag is raised for any window containing a DDL record, and not for windows without one |
| AC-P3-06 | M | mean+3σ anomaly scoring uses the quiescent baseline window declared in the incident manifest, and that window predates the injection (not fitted post-hoc) |
| AC-P3-07 | M | The SC-01 deletion window scores anomalous (above threshold); a declared quiescent window scores below threshold |
| AC-P3-08 | M | `bin/lab-candidates` emits records conforming to `candidate-coordinate.md` (integer+text LSN, resolved snapshot, skew, feature scores); no `principal`/`session_user`/`usename`/UID field is present |
| AC-P3-09 | M | Candidate ordering uses integer LSN arithmetic; an included `3/9` vs `3/10` case orders correctly (string comparison would fail it) |
| AC-P3-10 | M | `bin/lab-rank` is deterministic — two runs over the same ledger produce a byte-identical chosen coordinate; weights and tie-breaks are declared in a versioned config recorded with the output |
| AC-P3-11 | M | The chosen coordinate conforms to `arm-coordinate.md` and its `lsn_text`/`lsn_int`/`wall_clock`/`snapshot` map one-to-one onto the P1 results-row `recovery_coordinate.*` fields |
| AC-P3-12 | M | `bin/lab-naive` selects the last checkpoint before the approximate incident time; the injected time error is read from scenario config (declared, fixed) and recorded in `selection_inputs` |
| AC-P3-13 | M | Running `evaluate-arm` for `arm_a` and `naive` writes complete, schema-valid results rows with recovery-point error in LSN and in rows/bytes, both produced automatically by the oracle |
| AC-P3-14 | M | **Headline:** on the SC-01 incident, Arm A's recovery-point error is strictly lower than naive's on the primary metric (damaged rows retained, tie-broken by LSN error), both read from the results file. If Arm A does not beat naive, the task FAILs and reports a blocker — no metric is fudged |
| AC-P3-15 | M | **Article II negative:** stripping `session_user`/`usename`/UID from the ledger view handed to analytics and ranker leaves Arm A's chosen coordinate byte-identical |
| AC-P3-16 | M | The ranker reads no ground truth: `selection_inputs.read_injection_log`, `read_oracle_optimum` and `read_provenance` are all `false`, verified by a scan of the ranker's actual inputs |
| AC-P3-17 | M | `bin/lab-verify-p3` reports every criterion PASS with per-tier totals printed separately, exit 0 |
| AC-P3-18 | M | `lab-verify` 18/18, `lab-verify-p1` 24/24, `lab-verify-p1.1` 16/16, `lab-verify-p2` 18/18, `lab-verify-p2.1` 16/16 all still green; every prior contract hash unchanged (incl. `capture-completeness.md` byte-identical) |
| AC-P3-19 | A | The P3 architecture handoff records the analytics feature set, the ranker weights/version and the SC-01 Arm-A-vs-naive result, and states P5 builds R0/R1/R2 and P6 builds Arm B (asserted on machine-readable fields; anti-goal-inversion guarded) |

Eighteen of nineteen criteria are tier M. The single tier A criterion is the handoff record, which asserts on
machine-readable fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p3` green with per-tier totals; both P3 contracts frozen; SC-01 realized as a reconciled incident;
analytics + anomaly scoring deterministic and provenance-blind; candidates and the Arm A coordinate conforming to the
frozen schemas; the naive comparator declared and fixed; both arms' recovery-point errors auto-landing in the results
row; Arm A beating naive on SC-01 honestly; provenance-blindness and no-peek negative tests passing; all prior gates
and contract hashes unchanged; P3 handoff written without anti-goal inversion.
