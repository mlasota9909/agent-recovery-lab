# P9 — PLAN

## Architecture decisions
- ADR-P9-1 (isolation of the sweep from banked results): sweep rows are APPENDED with a
  distinct `sweep_id` and, preferably, carried in a `results/sweep-runs.jsonl` sidecar
  keyed by results-row id, so the P1 frozen schema is not mutated. If a schema field is
  truly unavoidable, add it via a P1 `results-row.amendment-2.md` (Article XV) and re-pin
  the schema digest repo-wide. The WI records which path was taken.
- ADR-P9-2 (anti-artefact interface parity): all models query through the SINGLE P5.1
  model_view + guard. Model identity MUST NOT change the structure of what is sent. This
  is the mechanical safeguard against "R2 won because of one model's tokenizer".
- ADR-P9-3 (pre-registration first): the statistical-analysis-plan is frozen in N001,
  before N004 generates any row. Article XXI makes N005 refuse a post-collection plan edit.
  This closes the p-hacking class a stats tranche introduces.
- ADR-P9-4 (report-what-it-shows): the pre-declared interpretations cover H2-fails and
  H1-fails outcomes; a collapse of R2's advantage on a larger model is a VALID, reportable
  finding that strengthens the operator-assist/data-residency argument. Do not suppress it.
- ADR-P9-5 (model containment reuse): Article X + P6.1 amendment applies per model;
  N002 re-runs the egress/alias/weights-hash checks for each new model rather than
  assuming the P6.1 result transfers.
- ADR-P9-6 (read-only): Article XVI. Analysis and framing never mutate evidence, ledgers,
  representations, oracle, or prior results rows.

## Task order
N001 -> N002 -> N003 -> N004 -> N005 -> N006 -> N007 -> N008.
N002/N003 independent after N001; both precede N004. N006/N007 independent after N005.

## Note on a possible Article XXII
P9 is a forward+analysis build under 21 articles. If the audit finds a NEW failure class
the gate missed (e.g. a subtle sidecar-join integrity gap), record it and propose
Article XXII — do NOT copy a P9 anti-goal forward as if it were a future tranche's task.
There is no P10 experiment; after P9 the only consumer is human review and the
P8 outputs (which N005/N006/N007 feed).
