# ADR-P11-2: a missing P10 verdict is not a verdict class

Status: accepted during R003 after the consistency gate stopped on source
line 21. The failed check is retained in
`logs/review/R003/consistency-failure.json`.

P10 source line 21 has `outcome=run_failure`, a chosen position of 8053068776
and `verdict=null`. Its detail traceback ends at `lab-verdict failed`.
The full-set audit must include this superseded submission. It now scores
`incorrect_safe` through the same P4 cache and padded lost-row rule.

The initial comparison incorrectly treated null as a previous verdict class.
Apply A2's consistency requirement to unchanged coordinates with an existing
scored P10 verdict. Retain and list unchanged coordinates without a previous
score as not comparable. They remain in the full audit and safety test and
remain excluded from primary analysis by the pre-registered last-attempt rule.

This fixes the gate's domain, not the grammar, a verdict, an analysis metric
or sample selection. The original grammar and analysis digests stay frozen.
The separate execution clarification `consistency.amendment-1.md` is pinned
in `runtime/p11-execution-amendments.json`. The negative test still flips a
real, previously scored unchanged-coordinate verdict and must be rejected.
