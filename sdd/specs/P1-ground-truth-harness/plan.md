# Plan — P1: Ground Truth, Results Contract and Run Harness

Architecture and locked decisions. Tasks implement this; they do not re-litigate it. Where a work instruction and this
plan disagree, this plan wins and the discrepancy is an observation to report.

## 1. Where P1 sits

```
P0  substrate ............ VM, ZFS, Postgres+logical decoding, out-of-band evidence, coordinate, reset  [DONE]
P0.1 remediation ......... boundary hardened, consumer supervised, verification tiered                  [DONE]
P1  instruments .......... oracle, results contract, ledger integrity, two-phase harness, null run      [THIS]
P2  capture .............. db.jsonl, snapshots.json, fs_diff.tsv, fs_hashes.tsv, DuckDB views
P3  analytics + Arm A .... burst density, anomaly scoring, candidates, ranker, naive comparator
P4  restore .............. real PITR into sandbox, row/byte/schema validation, promotion gate
P5  representations ...... R0 flat, R1 temporal, R2 graph+summaries, identical query interface
P6  Arm B ................ modest local model harness over the representations
```

P1's job is to make P3, P4, P5 and P6 **substitutions rather than rewrites**. Every stub it ships implements the
interface its real successor will implement.

## 2. Architecture decisions

### ADR-P1-1: The results row is a frozen contract, written before the harness

Problem: adding a results field later means re-running everything already run, because rows must be comparable across
the whole matrix.

Decision: `contracts/results-row.md` is authored and frozen in W002, before any harness code exists. Later tranches
may **append** fields with a documented default of `null`; they may never rename, retype or repurpose a field, and
they may never make a previously-nullable field required.

Consequence: W002 is the most expensive task to get wrong and the cheapest to get right. It is reviewed line by line.

### ADR-P1-2: Two phases, joined by an incident id

Problem: if each arm regenerates the incident, the arms differ by more than the representation and the ablation is
confounded.

Decision: strictly separate `lab-generate-incident` from `lab-evaluate-arm`. An incident is a durable, addressable
artefact identified by `incident_id`. Arms are evaluated against it. Every results row carries the `incident_id`.

```
lab-generate-incident --scenario SC-01
  -> reset t0|t1 -> barrier -> baseline -> workload start
     -> snapshot pre_injection -> inject -> capture stop
     -> snapshot post_capture -> register incident
  -> {"incident_id": "...", ...}

lab-evaluate-arm --incident <id> --arm stub --tier t2
  -> reset t2 -> barrier -> analyse -> restore+validate -> append results row
  -> {"run_id": "...", ...}          # repeatable, N times, same incident
```

Consequence: the acceptance criterion that matters most in this tranche is AC-P1-17 — a second arm evaluated against
the same incident reproduces the ground-truth coordinate **byte-identically**. That single assertion is the empirical
proof that the fixed-incident property holds and therefore that the ablation is valid.

### ADR-P1-3: The oracle is the only component permitted to read provenance

Problem: the ledger records which principal caused each change. That fact is necessary for scoring and fatal for
detection — an analysis component that can see `usename = lab_agent` has been handed the answer key, and every
subsequent result is meaningless.

Decision: two views over the same ledger.

| View | Contains provenance | Consumed by |
| --- | --- | --- |
| `scoring` | yes | the oracle, and nothing else |
| `analysis` | no | analysis stub (P1), ranker (P3), representations (P5), model (P6) |

Enforcement is a negative test, not a comment: strip provenance from the analysis view and assert the selected
coordinate does not change (AC-P1-19). This test is inherited and re-run by P3, P5 and P6.

### ADR-P1-4: Ledger integrity is asserted mechanically, because reset desynchronises the slot

Problem, discovered in P0.1 review: the replication slot lives in `PGDATA` and rewinds on a T1 or T2 reset. The
host-side ledger is append-only and does not rewind. Whether that produces duplicate or orphaned LSN ranges therefore
depends on incident-scoping discipline being perfect by hand, every time, for hundreds of unattended runs.

Decision: two invariants, asserted by `bin/lab-ledger-verify`, and the harness refuses to evaluate an arm when they
fail.

1. **Idempotency** — within one incident, no LSN appears more than once.
2. **Containment** — the ledger's LSN range lies within the incident's recorded open and close coordinates.

Both are one-pass checks over data that already exists. Cheap, and the difference between an evidence store that is
provably clean and one that is merely hoped to be clean.

### ADR-P1-5: The catch-up wait becomes a barrier, not an instruction

Problem: P0.1's handoff says "after T1 the slot rewinds; wait for `lab-slot --check` 0 before capture." That is a race
condition documented as a human habit, and the run matrix will execute hundreds of unattended cycles.

Decision: `bin/lab-barrier` polls `lab-slot --check` to a bounded timeout and exits non-zero on timeout. Every reset
inside the harness is followed by the barrier. It never proceeds on a degraded slot, and it never sleeps a fixed
guessed interval.

### ADR-P1-6: Cycle time is re-measured, never inherited

Problem: the 49.335 s full-cycle figure predates P0.1's reset guard, which forces a cluster stop and start. Any
sample-size plan built on it is optimistic, and that number drives the run plan.

Decision: W009 re-measures, separately for generate-incident and evaluate-arm, on an idle host, with at least five
repetitions reporting median and worst case. The stratified sample-size plan is derived from the measured
`evaluate-arm` cost, because arms dominate the matrix.

Consequence, and it is a favourable one: because arms re-evaluate a frozen incident under T2, arm cost should be far
below incident cost. The plan should therefore show that the ablation is cheap and the incidents are the budget.

### ADR-P1-7: Results are append-only JSONL, queried in place

Decision: one JSONL file per scenario under `RESULTS_ROOT`, one row per run, closed files mode 0444. DuckDB reads
JSONL natively, so analysis in P7 needs no ETL, no schema migration and no server.

Rejected: SQLite (a schema migration surface), a results table inside the victim database (rewinds on reset, and would
place results inside the blast radius), CSV (no typing, and quoting pain with nested coordinates).

### ADR-P1-8: Stubs report `stub`, never a fabricated success

Decision: the analysis stub selects a coordinate by a declared trivial strategy (the last snapshot before the
incident close coordinate) and labels itself `arm=stub`. The restore/validate stub returns verdict `stub`. No code
path in P1 can emit a clean restore verdict — Article VIII forbids a check that cannot fail, and it equally forbids a
success that was not earned.

## 3. Component map

| ID | Component | Owns | CLI | Task |
| --- | --- | --- | --- | --- |
| C1 | Results contract | field set, types, units, nullability | — | W002 |
| C2 | Results writer + validator | append, validate, immutability | `lab-results` | W003 |
| C3 | Ledger integrity | idempotency, containment | `lab-ledger-verify` | W004 |
| C4 | Reset barrier | bounded wait for consumer catch-up | `lab-barrier` | W004 |
| C5 | SC-01 workload | legitimate commits + manifest | `lab-workload` | W005 |
| C6 | SC-01 injector | the scripted DELETE, as `lab_agent` | `lab-inject` | W006 |
| C7 | Ground-truth oracle | optimum + scoring manifest | `lab-oracle` | W007 |
| C8 | Incident generator | phase 1, seven ordered steps | `lab-generate-incident` | W008 |
| C9 | Arm evaluator | phase 2, repeatable | `lab-evaluate-arm` | W008 |
| C10 | Analysis stub | P3 interface, no provenance | `lab-analyse-stub` | W008 |
| C11 | Restore stub | P4 interface, verdict `stub` | `lab-restore-stub` | W008 |
| C12 | Throughput + sampling | measured cycle times, plan | `lab-throughput` | W009 |
| C13 | P1 acceptance runner | AC-P1-01..24, tiered | `lab-verify-p1` | W010 |

## 4. Data layout added by P1

```
/home/mlasota/thesis/
  evidence/<scenario>/<incident_id>/
    incident.json            # open/close coordinates, workload params, snapshot names   (W008)
    injection.json           # what the injector did, verbatim, with commit LSN          (W006)
    workload-manifest.jsonl  # every legitimate commit with LSN                          (W005)
    oracle.json              # optimum coordinate + inputs used                          (W007)
    oracle-manifest.json     # rows legitimate at optimum, rows destroyed                (W007)
  results/
    SC-01.jsonl              # append-only, one row per run                              (W003)
  docs/
    sample-size-plan.md      # stratified plan derived from measured cycle time          (W009)
    throughput.json          # measured medians and worst cases                          (W009)
```

## 5. What P1 deliberately does not do

No derived analytics. No candidate generation. No ranking weights. No representations. No model. No real restore. No
SC-02/03/04 damage logic. No calibration of the naive comparator beyond recording its field.

If a task appears to need one of these, it has been misread — record the apparent need as an observation and continue
within scope.

## 6. Risks specific to this tranche

| Risk | Mitigation |
| --- | --- |
| Results contract churns after P3 starts producing rows | Freeze in W002 before any harness code; append-only amendment rule; W010 hash-verifies it |
| Oracle silently disagrees with the workload manifest | AC-P1-11 cross-checks the optimum against the manifest by an independent path, not the oracle's own computation |
| Provenance leaks into analysis during P3 | The negative test is written in P1 (AC-P1-19) and inherited, so the leak breaks a pre-existing test rather than going unnoticed |
| Reset guard makes the matrix slower than planned | ADR-P1-6 re-measures before the plan is written; arms run under T2 to keep the dominant cost low |
| An agent "helpfully" implements P3 analytics inside the stub | Article VI and the anti-goals list; W008's acceptance asserts the stub's strategy is the declared trivial one |
