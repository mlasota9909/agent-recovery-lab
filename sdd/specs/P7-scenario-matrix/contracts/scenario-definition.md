# FROZEN CONTRACT — Scenario Definition (machine-checkable scenario schema)

**Frozen by:** K001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV).
**Authority:** Article II (provenance for scoring, not detection), Article V (stock mechanisms), Article VIII (fail
loud / refusal never coerced), Article XVIII (null results root-caused). Honours `results-row.md`, `arm-coordinate.md`,
`representation-interface.md` (+amendment-1), `arm-b-protocol.md` (+amendment-1) without modification.

## 1. Why this contract exists

Every scenario (SC-01 already realized; SC-02/03/04 built in P7) must be described by one machine-checkable object so
that: the harness can generate and score it uniformly; the confounder is provably present; the ground-truth optimum is
computed, not asserted; and the scenario's link to the documented failure mode it represents
is recorded on the artefact rather than left in free text. A scenario definition that fails this schema is refused.

## 2. Required fields

| Field | Type | Rule |
| --- | --- | --- |
| `scenario_id` | string | `SC-0\d` — matches an entry in the run-matrix plan |
| `damage_class` | enum | one of `filesystem_data`, `database_data`, `database_schema`, `mixed` |
| `timing_pattern` | enum | one of `near_instant`, `slow`, `randomized` |
| `archetype` | string | one-line description of the real-world agent failure this reproduces |
| `corpus_citation` | array | >=1 citation key(s) for the documented failure mode(s) the scenario represents; non-empty |
| `injection.principal` | string | the agent principal the damage runs as (e.g. `lab_agent`) |
| `injection.script_ref` | path | the exact malicious operations, committed to the repo, run verbatim |
| `confounder.principal` | string | the legitimate principal (e.g. `lab_app`), distinct from `injection.principal` |
| `confounder.spec_ref` | path | the concurrent legitimate workload spec; MUST overlap the damage window |
| `confounder.overlaps_damage` | bool | MUST be `true`; a scenario that is false here is refused (AC-P7-05) |
| `ground_truth.kind` | enum | `single_coordinate` (SC-01/02) or `set_and_earliest` (SC-03/04) |
| `ground_truth.definition` | string | how the optimum / malicious set is defined for this scenario |
| `ground_truth.computed_from` | string | the exact record it is computed from (scripted commit LSNs / snapshot boundary / corrupted-row set), never eyeballed |
| `evidence_signature` | object | expected per-layer signature (db / filesystem / derived / graph) if capture is working |
| `metrics` | array | the scenario-specific metric names emitted per run (see §4) |

## 3. Provenance rule (Article II) — binding

`injection.principal` and `confounder.principal` are recorded in the ledger **for scoring only**. The oracle uses them
to compute ground truth. No arm — Arm A, naive, or Arm B — may read the principal when selecting a coordinate; every
arm-coordinate produced for the scenario carries `selection_inputs.read_provenance=false`. A scenario definition does
not expose the principal to any detection path.

## 4. Ground-truth kinds and their metrics

### 4.1 `single_coordinate` (SC-01, SC-02)

The optimum is one coordinate: the latest safe point before the damage that retains maximum legitimate work.
Metrics: `coord_error_lsn` (integer-LSN delta) OR `coord_error_checkpoint` (for periodic filesystem capture),
`legit_lost`, `damage_retained`, and — for filesystem — `checkpoint_gap_seconds` (the residual between the tightest
pre-damage checkpoint and the ideal instant; a measured quantity, not a defect).

### 4.2 `set_and_earliest` (SC-03, SC-04)

There is no single coordinate that removes all damage while retaining all legitimate work; forcing one would
misrepresent the result (Article XVIII spirit). Ground truth is a **set** plus the **earliest** malicious commit.
Metrics:
- SC-03: `single_coord_optimum_lsn` (the LSN before the first destructive DDL) AND `legit_dml_sacrificed` (the
  legitimate DML committed in the migration window that a single-coordinate restore discards) AND `ddl_ops_retained`.
- SC-04: `malicious_txn_precision`, `malicious_txn_recall` (against the known malicious set), `earliest_bounded_commit`
  (the earliest malicious commit the engine correctly bounds), and `coord_error_lsn` only if forced to a single point
  (reported as a lower bound on unavoidable loss, not as success/failure).

## 5. Example (SC-04, illustrative — the real definition is committed in K004)

```json
{
  "scenario_id": "SC-04",
  "damage_class": "database_data",
  "timing_pattern": "randomized",
  "archetype": "agent makes small subtle updates to scattered rows over time, hidden among legitimate updates",
  "corpus_citation": ["Cemri2025", "Greshake2023"],
  "injection": {"principal": "lab_agent", "script_ref": "scenarios/sc04/inject.sql"},
  "confounder": {"principal": "lab_app", "spec_ref": "scenarios/sc04/workload.py", "overlaps_damage": true},
  "ground_truth": {
    "kind": "set_and_earliest",
    "definition": "exact set of maliciously-updated (row_id, xid) pairs and the earliest malicious commit LSN",
    "computed_from": "the scripted injection log of committed malicious UPDATEs, masked to the reconciled ledger"
  },
  "evidence_signature": {
    "db": "no volume spike; same principal touching unrelated rows at randomized intervals",
    "derived": "signal only emerges from per-entity and per-window aggregation, not a single window",
    "graph": "one session touching many unrelated rows dispersed in time"
  },
  "metrics": ["malicious_txn_precision", "malicious_txn_recall", "earliest_bounded_commit", "coord_error_lsn"]
}
```

## 6. Change control

Frozen at K001, hash-recorded in `logs/review/K001/`. Further change supersedes via `scenario-definition.amendment-N.md`
with its own ADR. This file stays byte-identical (Article XV).
