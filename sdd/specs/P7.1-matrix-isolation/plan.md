# Plan — P7.1: Matrix Isolation

## Architecture decisions (locked)

### ADR-P7.1-1 — the hollow matrix is an architectural defect, root-caused from primary evidence (Article XVIII/XIX)

`bin/lab-verify-p7` closed 21/21 and the P7 addendum is honest, but `docs/P7-architecture-handoff.addendum.md` §3.1
records the root cause plainly: T012 `zfs rollback -r` on `DS_PARENT=labpool/victim` is designed for one incident, the
matrix ran three live incidents on that shared dataset, and the first live T2 (SC-02 `post_capture`
`s_20260826T095606Z`) destroyed the SC-03/SC-04 snapshots. Live `lab-coordinate` then read whichever incident's
heartbeat had last been rolled back, so SC-03/SC-04 LSNs were not even in the live postgres. The first unattended run's
34 SC-03/SC-04 cells were `run_failure`; §3.2 records they were stripped so `total_rows` stayed 51. L001 records this
as the D1 root cause from the addendum and the cited commits (`64e11dd`, `8321ea8`), not re-derived as if unknown.

### ADR-P7.1-2 — fix isolation at the dataset level; one transient cluster at a time

The clean fix is per-incident dataset subtrees (`labpool/victim/inc_<id>/{pgdata,protected}`) so reset is scoped to
one incident and `zfs rollback -r` never touches the shared parent. Isolation is persistent at the dataset level; the
PostgreSQL cluster is transient (started against the incident's pgdata on demand, stopped at teardown), so we never run
N clusters at once and the local cost stays modest. This directly kills the D1 mechanism: a sibling's snapshots live on
a sibling subtree and are unreachable by a scoped rollback. `bin/lab-reset` is hardened to refuse a shared-parent or
cross-incident target — the refusal is the enforcement, proven load-bearing by the L002 negative test.

### ADR-P7.1-3 — validate the new scenarios against ground truth, do not extend the stub

D2 exists because SC-02/03/04 had no `oracle-manifest.json`, so P4 was skipped and coordinates came from the frozen
archive. SC-02 is a single-coordinate scenario: it gets a real `oracle-manifest.json` (pre-incident hashes/row-counts/
schema, exactly the SC-01 shape) and scores through the **unchanged** P4 restore+validate path. SC-03 (schema, staged)
and SC-04 (stealthy dispersed corruption) are by design not single-coordinate (they were `set_and_earliest` in P7): a
determination is scored by the L003 set-validation path — precision/recall of the identified malicious transaction set
plus the earliest-safe bound and the legitimate DML a single-coordinate restore would sacrifice — a defined non-stub
verdict. We do not invent an SC-01 manifest for a different scenario, and we do not fork the P4 code.

### ADR-P7.1-4 — completeness is not validity; supersede, never delete (Article XIX)

The 34 stripped rows are the exact anti-pattern Article XIX names. `run-matrix-plan.amendment-1.md` requires
`matrix-completeness.json` to carry a validity partition beside the count, every non-determination to carry a `cause`,
and every failed/replaced cell to be retained as superseded (replacement rows carry `supersedes`; predecessors carry
`superseded_by`; irrecoverable prior rows are recorded in a `superseded_manifest.json` with their cause). A green count
with an undiagnosed `run_failure` or a silently removed cell is a gate failure (AC-P7.1-12 negative test).

### ADR-P7.1-5 — disaggregate the SC-04 headline; corrected never weakened

`P7-handoff.json` sold SC-04 as `strongest_figure: true` while R2 was larger than R0 in bytes and tokens
(`matches_prediction: false`). These are two claims. **Actionability:** R2 scored 0.95 vs R0 0.0 — the largest
arm-quality gap in the matrix, and a genuine strong result (R2 lets the modest model act where R0 cannot).
**Compactness:** on a 799-byte incident, R2's graph+summary overhead made it larger — the universal-compactness claim
does not hold at small scale. `headline.json` reports the two dimensions in separate fields; `strongest_figure` is
replaced by `strongest_actionability_gap` and a per-scenario `compactness_holds` boolean; SC-04's
`compactness_holds:false` is stated. This is a correction to honesty, not a weakening: no number changes, the mislabel
is removed, and the compactness claim is scoped to where it is true (large incidents, e.g. SC-01's ~140x).

## Constitutional change

Article XIX is appended by L001:

> **Article XIX — Independent units are isolated; completeness is not validity.** When an experiment comprises multiple
> independent units (incidents, scenarios, trials) over shared mutable infrastructure, each unit MUST be isolated so
> that operating on one cannot destroy or alter the recorded state of another. A completeness metric (produced count ==
> planned count) MUST NOT be reported as evidence the experiment ran; it MUST be accompanied by a validity partition
> that separates genuine outcomes from harness/infrastructure failures, each failure carrying a diagnosed cause. A unit
> that fails for infrastructural reasons MUST be recorded as superseded — retained with a pointer to its replacement —
> never silently removed to keep a completeness metric green.

This sits alongside Articles XII–XVIII as the eighth lesson learned from review, each closing a class rather than an
instance.

## Task breakdown

| Task | Owns | Closes |
| --- | --- | --- |
| L001 | Article XIX; D1 root cause; FULL/FALLBACK decision; ADR-P7.1-1..5 | D1 root cause + timeline guard |
| L002 | `incident-isolation.md`; per-incident datasets + scoped reset; sibling-safety negative test | D1 fix |
| L003 | SC-02 `oracle-manifest.json` + P4 wiring; SC-03/04 set-validation verdict | D2 |
| L004 | live re-run SC-02/03/04 under isolation; supersede prior cells; completeness+validity partition | D1/D2 result |
| L005 | disaggregated honest headline; compactness reframed scale-dependent; SC-01 sole validated headline | D3 |
| L006 | `bin/lab-verify-p7.1` gate; re-derive `-p7`; contract-hash re-verify; mapping; memo | all |

## Sequencing

L001 first (root cause + the decision that governs whether L002–L004 run at all). L002 and L003 are independent and may
run in either order, but both precede L004 (the re-run needs isolation and the validation path). L004 then L005 (the
headline is derived from the validated rows). L006 is the gate and runs last.

```
L001 -- L002 --\
        L003 --+-- L004 -- L005 -- L006
   (L002,L003 independent; both precede L004)
```

## Risks

- **Isolation is more work than the budget allows.** Mitigated by the L001 FULL/FALLBACK gate: if isolation or the
  re-run does not fit the remaining weeks, FALLBACK anchors on SC-01 and corrects D2/D3 in documentation only, and the
  writing weeks are protected. The operator countersigns.
- **Regenerating SC-03/SC-04 perturbs SC-01.** Mitigated by AC-P7.1-16 (SC-01 `db.jsonl`/results hashes must re-verify)
  and by SC-01 being reset-refused in `incident-isolation.md`; the re-run creates new isolated subtrees and never
  touches the banked headline.
- **The set-validation verdict (L003) becomes a bespoke scorer that drifts from P4.** Mitigated by keeping SC-02 on the
  unchanged P4 path and defining SC-03/04 set-validation as a thin, tested addition with its own negative test, not a
  fork of P4.
- **A re-run cell still fails infrastructurally.** Then it is a superseded/`run_failure` row with a diagnosed cause in
  the validity partition (Article XIX), not a deletion — and that is an acceptable, honest outcome, not a gate failure,
  provided it is diagnosed and retained.
- **The disaggregated headline is read as walking back a win.** Mitigated by ADR-P7.1-5: SC-04's actionability gap is
  the *strongest* in the matrix and is stated as such; only the over-broad compactness claim is scoped to where it
  holds. The reframe strengthens the finding (representation drives actionability across scales; compactness
  is a scale-dependent bonus).

## Note for P8

P8 consumes the L004 validity-partitioned matrix and the L005 disaggregated headline. Under FULL it has SC-01 (P4-
validated) plus SC-02 (P4-validated) plus SC-03/04 (set-validated) — a genuine multi-scenario result. Under FALLBACK it
has SC-01 as the validated headline and SC-02/03/04 as bounded preliminary findings with limitations written in. Either
way, P8 must report completeness with the validity partition, never the bare count, and must carry the actionability/
compactness disaggregation into the reported results.

## ADR-P7.1-3 — D1 negative test uses a disposable parent (added mid-L002)

**Context.** WI-L002's original negative test told the agent to remove the shared-parent guard and run
`zfs rollback -r labpool/victim@…` to destroy sibling B. The executor correctly blocked: (a) plain recursive rollback of a
dataset destroys later snapshots of *that dataset*, not its children's snapshots, so the literal command would not
reproduce D1 and any claim it did would be false; (b) reproducing the real mechanism (the reset's descendant-enumeration
loop) over live `labpool/victim` places the banked SC-01 `pgdata`/`protected` in destructive scope, violating the
SC-01-untouched invariant.

**Decision.** Reproduce D1 on a disposable parent `labpool/p7_1_negative` with throwaway incidents, then destroy it;
prove the real guarded `bin/lab-reset` refuses a `labpool/victim` shared-parent request separately. Normative in
incident-isolation contract §10.

## ADR-P7.1-4 — incident runtime record + selection helper; incident-derived filesystem paths (added mid-L002)

**Context.** Review flagged that per-incident datasets alone do not achieve isolation: generation, snapshot-tick,
heartbeat, logical consumer, capture and SC-02 read flat globals (`PG_DATA`, `PG_PORT`, `DS_PARENT`, hardcoded
`/srv/protected`). Patching only `lab-reset`/generation/`lab-coordinate` would leave the rest on the shared substrate.

**Decision.** Generation writes a per-incident runtime record `runtime/incidents/<id>.env`; a single helper
`lib/lab_incident_env.sh` sourced after `etc/lab.env` by every stateful command exports the active incident's `INC_*`
overrides. Scenario filesystem targets are incident-derived via `INC_PROTECTED` (no shared `/srv/protected`); unset =
hard refusal. `etc/lab.env` is not edited; SC-01 keeps flat globals and is never given a runtime record. Normative in
incident-isolation contract §9. Raises the L002 estimate to ~2.5 d.
