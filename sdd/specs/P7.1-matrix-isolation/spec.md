# Spec — P7.1: Matrix Isolation (make the multi-scenario result real, not hollow)

**Feature ID:** P7.1-matrix-isolation
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P7 (accepted, pending this remediation)
**Blocks:** P8 (analysis) — P8 must consume a validity-partitioned matrix with real, validated
new-scenario results (or an explicitly FALLBACK-scoped preliminary set), not a hollow 51/51.

## 1. Purpose

Turn the P7 matrix from complete-but-hollow into either (FULL) a live, ground-truth-validated multi-scenario result
under per-incident isolation, or (FALLBACK) an honest SC-01-anchored headline with SC-02/03/04 presented as bounded
preliminary findings — the choice made by a bounded feasibility decision in L001 that protects the writing timeline.
Close the architectural root cause (shared-pool reset destroying sibling incidents), validate the new scenarios
against ground truth, report completeness beside a validity partition, and disaggregate the SC-04 headline into its
actionability and compactness dimensions. Add the constitutional principle that completeness is not validity and that
independent units on shared substrate must be isolated.

## 2. Problem statement

**D1 — hollow matrix, architectural root cause.** T012 `zfs rollback -r` on the shared parent `labpool/victim`
destroyed SC-03/SC-04 snapshots when SC-02's live T2 ran; live `lab-coordinate` then queried the wrong incident's
heartbeat table. The first unattended run's 34 SC-03/SC-04 cells were all `run_failure`; those rows were stripped so
`total_rows` stayed 51. Completeness passed over a matrix that did not run.

**D2 — new scenarios unvalidated.** SC-02/03/04 lack `oracle-manifest.json`; determinations were `restore_verdict=stub`
(P4 skipped), coordinates archive-resolved (`resolved_by: snapshot_first`), `skew_ms` `0` by consequence not
measurement.

**D3 — SC-04 headline conflates two claims.** `strongest_figure: true` with `matches_prediction: false`,
`evidence_bytes_r2: 1099` > `evidence_bytes_r0: 799`, `token_r2: 302` > `token_r0: 198`. SC-04 is the strongest
*actionability* result (R2 0.95 vs R0 0.0) and simultaneously *refutes* universal compactness on a tiny incident.

## 3. Scope

### In scope

- **Article XIX** added: independent experimental units on shared mutable substrate must be isolated so operating on
  one cannot alter another's recorded state; completeness is reported with a validity partition; an infrastructurally
  failed unit is superseded (retained), never silently deleted.
- **L001** root-cause diagnosis of the shared-pool destroy from the P7 addendum + commits, and a bounded **go/no-go**
  (FULL vs FALLBACK) with the operator countersigning; ADR-P7.1-1..5.
- **`incident-isolation.md`** (new frozen contract): per-incident dataset subtree, transient per-incident cluster,
  reset scoped to the incident subtree, `zfs rollback -r` on the shared parent refused; the isolation invariant.
- **`run-matrix-plan.amendment-1.md`** (Article XV supersession): live-coordinate resolution for re-run cells;
  completeness + validity partition; supersede-not-delete; real P4/set validation for new scenarios.
- **L002** per-incident isolation implementation + the sibling-safety negative test.
- **L003** `oracle-manifest.json` for SC-02 (single-coordinate) wired to the unchanged P4 path; a defined
  set-validation verdict for SC-03/SC-04 (precision/recall of the malicious set + earliest-safe bound).
- **L004** live re-run of SC-02/03/04 under isolation; prior stub/hollow cells superseded (retained with pointers);
  `matrix-completeness.json` with the validity partition.
- **L005** honest, disaggregated headline: SC-01 the sole P4-validated headline; SC-04 stated as strongest
  actionability gap AND a compactness counter-example; compactness reframed as scale-dependent.
- **L006** `bin/lab-verify-p7.1` gate; re-derived `-p7` consistent with the amendment; old->new criterion mapping;
  acceptance memo.

### Out of scope

- Re-running or regenerating the SC-01 headline incident (banked; hashes must re-verify).
- Editing any frozen contract file (supersede by amendment; `incident-isolation.md` is new, not an edit).
- Lowering Arm A's 3σ threshold (SC-02's no-3σ `run_failure` is a genuine finding).
- Changing the model pin or any representation artefact.
- Reading `principal` in any path (Article II).
- Making any criterion pass by weakening what it checks.

## 4. Functional requirements

- **FR-1 Isolation principle.** The constitution gains Article XIX (isolation of units + completeness-is-not-validity +
  supersede-not-delete).
- **FR-2 Root cause of record + decision.** L001 records the shared-pool destroy as the D1 root cause from the addendum
  and commit history, and a FULL/FALLBACK decision with a stated time-budget basis, countersigned by the operator.
- **FR-3 Per-incident isolation.** Each incident owns `labpool/victim/inc_<id>/{pgdata,protected}` with its own
  transient cluster; reset is scoped to the incident subtree; `bin/lab-reset` refuses a target that resolves to the
  shared parent or outside the named incident's subtree; SC-01 reset is refused.
- **FR-4 Isolation invariant proven.** Reset/teardown of one incident leaves every sibling incident's snapshots,
  data, and heartbeat byte-identical (L002 negative test).
- **FR-5 Live coordinates for re-run.** Re-run cells resolve coordinates against the incident's own live cluster
  (`resolved_by: live_heartbeat`) with a measured `skew_ms`; the archive `snapshot_first` path is not used for a cell
  with a live cluster.
- **FR-6 Ground-truth validation of new scenarios.** SC-02 carries an `oracle-manifest.json` and scores through the
  unchanged P4 restore+validate path (verdict never `stub`); SC-03/SC-04 score through the L003 set-validation path
  (precision/recall + earliest-safe bound), a defined non-stub verdict.
- **FR-7 Completeness with validity partition.** `matrix-completeness.json` reports `total_rows ==
  total_planned_runs` **and** `{determinations, refusals, run_failures, superseded, stub_validations}` with a `cause`
  on each non-determination; any undiagnosed `run_failure` or any silently removed cell fails the gate.
- **FR-8 Supersede, never delete.** Prior stub/hollow cells are retained; replacement rows carry `supersedes` and
  predecessors carry `superseded_by` (or a `superseded_manifest.json` records irrecoverable predecessors and their
  cause). Nothing is deleted to improve a count.
- **FR-9 Honest disaggregated headline.** `headline.json` reports, per scenario, the actionability dimension
  (determination/refusal rate, P4/set verdict, quality) and the compactness dimension (evidence_bytes, tokens) as
  **separate** fields; `strongest_figure` is replaced by dimensioned labels (`strongest_actionability_gap`,
  `compactness_holds: bool`); SC-04's `compactness_holds:false` is stated, not hidden; SC-01 is the sole P4-validated
  headline.
- **FR-10 SC-01 protected + gate + memo.** SC-01 `db.jsonl` and `results/SC-01.jsonl` hashes re-verify byte-identical;
  `bin/lab-verify-p7.1` runs every criterion with per-tier totals; re-verifies all prior contract hashes; runs
  `bin/lab-gate-readonly-check`; records old->new mapping and the acceptance memo "P7 accepted only after P7.1".

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P7.1-01 | M | `constitution.md` contains a well-formed Article XIX (isolation of units; completeness≠validity; supersede-not-delete); article count is 19 |
| AC-P7.1-02 | M | ADR-P7.1-1..5 recorded: root cause; isolation design; validation design; supersede-not-delete + partition; corrected-never-weakened |
| AC-P7.1-03 | A | `logs/review/L001/decision.json` records `decision` ∈ {FULL,FALLBACK} with a time-budget basis and `operator_countersigned:true`; if FALLBACK, a reason and the documentation-only plan for L005 |
| AC-P7.1-04 | M | `incident-isolation.md` exists and defines the per-incident subtree layout, transient cluster, scoped reset, and the isolation invariant; frozen with a recorded hash |
| AC-P7.1-05 | M | `bin/lab-reset` refuses (non-zero, naming the violation) any target resolving to `labpool/victim` (shared parent) or outside the named incident subtree, and refuses the SC-01 incident |
| AC-P7.1-06 | M | Two incidents A,B created with `@pre_injection`+`@post_capture`; after reset/teardown of A, B's snapshot list, `pgdata`/`protected` digest, and heartbeat digest are byte-identical (isolation invariant) |
| AC-P7.1-07 | M | NEGATIVE: an attempted `zfs rollback -r labpool/victim@…` (shared parent) is refused by `bin/lab-reset`; a scratch bypass that performs it is shown to destroy B's snapshots, proving the guard is load-bearing; revert |
| AC-P7.1-08 | M | `oracle-manifest.json` exists for SC-02; an Arm B/Arm A determination on SC-02 scores through the unchanged P4 path with a verdict in the P4 set (never `stub`) |
| AC-P7.1-09 | M | SC-03/SC-04 determinations score through the L003 set-validation path with precision/recall of the malicious set and an earliest-safe bound recorded; verdict is never `stub` for a cell that ran |
| AC-P7.1-10 | M | Re-run cells record `resolved_by: live_heartbeat` and a measured `skew_ms` (not 0-by-consequence); no re-run cell with a live cluster uses `snapshot_first` |
| AC-P7.1-11 | M | `matrix-completeness.json` reports `total_rows == total_planned_runs` over the full design AND a validity partition `{determinations,refusals,run_failures,superseded,stub_validations}` with a `cause` on each non-determination |
| AC-P7.1-12 | M | NEGATIVE: dropping one `run_failure`/superseded row to inflate the determination share makes `bin/lab-verify-p7.1` exit non-zero (completeness≠validity enforced); revert restores PASS |
| AC-P7.1-13 | M | Prior P7 stub/hollow cells are retained as superseded (replacement rows carry `supersedes`; predecessors `superseded_by`, or a `superseded_manifest.json` records irrecoverable ones with cause); nothing deleted |
| AC-P7.1-14 | M | `headline.json` reports actionability and compactness as separate per-scenario fields; `strongest_figure` replaced by `strongest_actionability_gap` + `compactness_holds`; SC-04 `compactness_holds:false` present; SC-01 is the sole P4-validated headline |
| AC-P7.1-15 | M | SC-04 actionability gap (R2 quality − R0 quality) re-derived from committed rows equals the largest arm-quality gap in the matrix, and its `compactness_holds` is false with `evidence_bytes_r2 > evidence_bytes_r0` shown |
| AC-P7.1-16 | M | SC-01 `db.jsonl` and `results/SC-01.jsonl` hashes byte-identical to the P6.1 close (banked headline untouched) |
| AC-P7.1-17 | M | Provenance-blindness (Article II): no `principal`/`usename`/`session_user`/UID in any re-run assembled prompt, representation, or summary |
| AC-P7.1-18 | M | No frozen contract file mutated (all prior hashes re-verify); old->new mapping records live-coord + partition + supersede as corrected/strengthened, none weakened |
| AC-P7.1-19 | M | Arm A's 3σ threshold unchanged; SC-02 no-3σ outcome (if reproduced) recorded as a genuine `run_failure` with cause, not patched |
| AC-P7.1-20 | M | `bin/lab-verify-p7` re-derived consistent with the amendment; `bin/lab-verify-p7.1` every criterion PASS with per-tier totals printed separately, exit 0; both pass `bin/lab-gate-readonly-check` |
| AC-P7.1-21 | A | `docs/p7-acceptance-memo.md` records the three remediated defects and `p7_accepted_only_after: "P7.1"` on machine-readable fields |

Under FALLBACK (AC-P7.1-03), AC-P7.1-08..15 are recorded as `not_executed` with the decision reason, and L005 delivers
the documentation-only corrections (D2/D3 stated as limitations, SC-01 the sole headline); AC-P7.1-04..07 (isolation)
are still attempted if feasible, else also `not_executed`. AC-P7.1-01/02/16/17/18/20/21 hold in both branches.

## 6. Definition of done

`bin/lab-verify-p7.1` green with per-tier totals; Article XIX in force; the shared-pool root cause fixed by
per-incident isolation with the invariant proven (FULL) or documented as the bounding limitation (FALLBACK); new
scenarios validated against ground truth or explicitly bounded; completeness reported with a validity partition; prior
failed cells superseded not deleted; the SC-04 headline disaggregated; SC-01 banked headline byte-identical; all frozen
contracts unchanged; no criterion weakened.
