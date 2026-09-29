# Plan — P3: Derived Analytics & the Arm A Deterministic Ranker

## Architecture decisions (locked)

These continue the ADR lineage (ADR-003 deterministic selection scoring; ADR-004 representation as the independent
variable; ADR-008 the cross-layer coordinate) and add the decisions specific to building the detection-and-ranking
layer.

### ADR-P3-1 — analytics and ranker are provenance-blind; only the oracle scores with provenance

The ledger records `principal` so the P1 oracle can classify a change as damage or legitimate when it computes the
ground-truth optimum. Analytics (C5) and the ranker (C7) never read it: they consume `bin/lab-query`'s default views,
which already exclude the provenance field (P2 AC-P2-14). This is Article II carried into the detection layer, and it
is what makes Arm A a fair baseline rather than a leak of the answer key. Enforced mechanically by the D009
negative test (strip provenance → chosen coordinate unchanged), not by a comment.

### ADR-P3-2 — the ranker is deterministic with a declared, versioned config

No model participates in P3. The ranker is `score = Σ wᵢ·featureᵢ` over the frozen feature set of
`candidate-coordinate.md`, with weights and tie-breaks (tie-break: latest safe integer LSN) declared in a versioned
config file recorded alongside the output. Determinism is asserted by re-run: same ledger, same config → byte-identical
chosen coordinate. This is what yields a single reproducible Arm A number and lets Arm B (P6) be judged
against it.

### ADR-P3-3 — the naive comparator is mandatory and must never be rigged

Every run carries the naive comparator: the last checkpoint before an approximate operator-supplied incident time.
The time error is a **declared, fixed** parameter in the scenario config, not a value chosen to make Arm A look good,
and it is recorded in the coordinate's `selection_inputs`. The naive comparator is the simple, readily understood baseline; the
roadmap is explicit that it must never be omitted from a run. Its presence is what makes "Arm A is better" a
meaningful sentence.

### ADR-P3-4 — anomaly scoring uses a declared quiescent baseline window, fixed before injection

mean+3σ scoring is computed against a baseline window recorded in the incident manifest that **predates** the
injection. Fitting the baseline after seeing the damage would be circular. Because `generate-incident` snapshots
`pre_injection` and records the quiescent window, the baseline is fixed by construction and the scoring is
reproducible and sound.

### ADR-P3-5 — integer LSN arithmetic everywhere (restated because it has bitten this project)

All candidate ordering and all "newest snapshot with LSN ≤ x" resolution use the 64-bit integer `(high<<32)+low`.
String comparison of LSNs is prohibited and is covered by a required `3/9` vs `3/10` test case (AC-P3-09). This is the
same class of bug P2.1 formalised; P3 restates it because candidate ordering is where it would resurface.

### ADR-P3-6 — SC-01 is realized inside P3, bounded; SC-02..04 are deferred

P3's headline test needs a real SC-01 incident, which does not yet exist (P2 used a generic workload deliberately).
P3 therefore builds a **minimal, bounded** SC-01 realization — the injector, a concurrent repeated-key workload
profile, and the oracle parameters — reusing the P1 `generate-incident` harness and P2 capture rather than inventing
new machinery. This is a conscious scoping decision, called out here so the reviewer sees it: SC-02, SC-03 and SC-04
and their oracle tuning are explicitly **not** in P3. The SC-01 realization is scoped to exactly what the headline and
provenance tests require.

### ADR-P3-7 — entry behind reconciliation; detection never peeks at the answer

Entry gate: `bin/lab-ready` exit 0 **and** the target incident has passed `bin/lab-ledger-account` (inherits
ADR-P2-7). P3 refuses to analyse an unreconciled ledger. Beyond provenance-blindness, the ranker's inputs are limited
to the provenance-blind ledger view and (for naive) the approximate incident time; it may read neither the injection
log nor the oracle optimum. Every arm coordinate records this in a machine-readable `selection_inputs` block whose
`read_injection_log`/`read_oracle_optimum`/`read_provenance` must all be `false`, and the harness rejects any arm that
sets one `true`.

## No new constitutional article

P0.1, P1.1 and P2.1 each added an article because each was a remediation that surfaced a defect class (XII test
hatches, XIII verification tiers, XIV provenance of record, XV amend-by-supersession). P3 is a forward build and
surfaces no new class; it operates under the fifteen articles in force. If P3's own acceptance review finds a defect
the gate missed — the pattern so far in four of the six tranches — that is where the sixteenth article would come
from, not before.

## Task breakdown

| Task | Owns | Serves |
| --- | --- | --- |
| D001 | the two P3 contracts + entry-gate record | FR-1 |
| D002 | SC-01 injector + workload profile + oracle params → one reconciled SC-01 incident | FR-2 |
| D003 | `bin/lab-analytics` (burst density, churn, deletion spikes, DDL flag) | FR-3 |
| D004 | mean+3σ anomaly scoring against the declared quiescent baseline | FR-4 |
| D005 | `bin/lab-candidates` candidate generation to the frozen schema | FR-5 |
| D006 | `bin/lab-rank` Arm A deterministic ranker | FR-6 |
| D007 | `bin/lab-naive` naive comparator | FR-7 |
| D008 | wiring both arms into `evaluate-arm` so errors auto-land in results | FR-8 |
| D009 | headline SC-01 test + provenance-blindness + no-peek negatives | FR-9 |
| D010 | `bin/lab-verify-p3` gate; contract re-verify; P3 handoff | FR-10 |

## Sequencing

D001 first (contracts before any producer). D002 realizes the SC-01 incident and depends on D001. D003 (analytics)
and D004 (anomaly, built on analytics output) depend on a reconciled incident from D002. D005 (candidates) depends on
D003+D004. D006 (ranker) and D007 (naive) depend on D005 for candidates (naive needs the coordinate space but not the
features). D008 wires D006+D007 into the P1 harness. D009 runs the headline and negatives over the wired pipeline.
D010 gates and runs last.

```
D001 -- D002 --+-- D003 -- D004 --+
               |                   +-- D005 --+-- D006 --+
               |                              |          +-- D008 -- D009 -- D010
               |                              +-- D007 --+
               |
               (D002 also provides the reconciled incident every later task reads)
```

D006 and D007 may run in either order once D005 is complete. D008 needs both. D009 needs D008. D010 runs last.

## Risks

- **Coding-agent-generated analysis logic that is plausible but wrong** — the exact failure class this project studies.
  Mitigation: the P1 oracle and `lab-ledger-account` already exist as the test harness, so Arm A is scored against an
  independent ground truth it cannot see. D009's headline is a real comparison, not a self-check.
- **Provenance leaking into detection.** Highest-consequence correctness risk. Mitigation: ADR-P3-1 and the D009
  strip-provenance negative test; inherited from P2 AC-P2-14. If Arm A's coordinate moves when provenance is stripped,
  the ranker was cheating and the task fails.
- **The naive comparator quietly rigged** to make Arm A look good. Mitigation: ADR-P3-3 fixes the time error in
  scenario config and records it in `selection_inputs`; the operator reads it directly.
- **Fitting the anomaly baseline to the damage.** Mitigation: ADR-P3-4 fixes the baseline window before injection in
  the incident manifest.
- **String LSN comparison resurfacing in candidate ordering.** Mitigation: ADR-P3-5 and the `3/9` vs `3/10` test case.
- **Arm A failing to beat naive on SC-01.** This is treated as a real result, not a test bug: D009 FAILs and reports a
  blocker for operator investigation of the analytics/ranker rather than adjusting the comparator. On a near-instant
  bulk deletion with concurrent legitimate work, evidence-driven selection should win; if it does not, either the
  analytics are wrong or SC-01 is mis-specified — both are findings worth surfacing loudly.
- **Scope creep from SC-01 realization into a general injector framework.** Mitigation: ADR-P3-6 bounds D002 to SC-01
  only.
