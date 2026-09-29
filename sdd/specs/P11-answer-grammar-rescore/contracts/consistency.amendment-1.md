# P11 execution clarification 1: unchanged but never scored

Authority: Articles XV, XIX and XX; ADR-P11-2-unscored-attempts.
Scope: A2 CONSISTENCY and WI-R003 step 3 only. No grammar, metric, selection
rule, hypothesis, statistical method or interpretation changes.

A missing (`null`) P10 verdict following `run_failure` is not a verdict
class. All such retained completion occurrences must still be re-parsed and
scored. If their position is unchanged, list them separately as
`unchanged_without_previous_score`. They cannot satisfy or violate equality
with a previous verdict that does not exist. They are not removed from the
audit or safety check. The frozen last-attempt rule still determines whether
an occurrence enters the primary analysis.

Every unchanged coordinate with an actual P10 verdict must retain exactly
that verdict class. A previously scored unchanged verdict changed to any
different class, including null, remains a fatal consistency error.
