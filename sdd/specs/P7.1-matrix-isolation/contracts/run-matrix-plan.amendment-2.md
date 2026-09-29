# Amendment 2 to the P7.1 run-matrix plan

Supersedes: `run-matrix-plan.amendment-1.md` clause A6 and `incident-isolation.md`
section 8, to the narrow extent of the results-row schema enum only.

Exact superseded clause from `run-matrix-plan.amendment-1.md` A6 (verbatim):

> The scenario roster, the timing patterns, the mandatory-confounder rule, the results-row schema, the `reset_tier`
> enum, Arm A's 3σ threshold (SC-02's no-3σ `run_failure` remains a genuine reported finding), and every prior frozen
> contract. This amendment changes reporting and resolution discipline, not the experiment's design.

Exact superseded clause from `incident-isolation.md` section 8 (verbatim):

> The results-row schema and its `reset_tier` enum (`t0|t1|t2`) are unchanged.

References: `ADR-P7.1-6`, `results-row.amendment-1.md`. Frozen: yes.

## Change
The "results-row schema is unchanged" assertions in A6 and section 8 are amended: the
coordinate `resolved_by` enum receives exactly one additive value, `live_heartbeat`, per
`results-row.amendment-1.md`. No other part of the schema changes. All other guarantees of
A6 and section 8 (row shape, field set, immutability of prior rows, provenance withheld
from detection) remain in force.
