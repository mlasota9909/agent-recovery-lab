# Optional SC-01 replication

One fresh named database incident, three Primary Sweep models, R0/R1/R2 and five
repeats (45 calls). Use temperature 0, top-p 1, seed 42 and 8,192 output tokens.
Preserve the database prompt and inputs; apply the revised P11 answer grammar
to every representation. Freeze inputs, grammar, check implementation, model set
and this plan before collection. Keep historical results and verdict v1 unchanged.
Index R1's explicitly displayed `last_safe_lsn_int` as a visible LSN, just as an
explicit `lsn_int` is indexed. This field-name adaptation uses only the supplied
content, for every representation; it adds no hidden positions. The revised
window/predecessor and timestamp/explicit-commit requirements stay unchanged.

Report planned, missing, accepted, rule rejected, declined and execution failures
per model/input. Report accepted verdict v1 counts (correct, incorrect_safe,
incorrect_corrupt, not_recovered), row damage/loss per unit and pending checks.
Store comparators separately. Missing units and pending checks prevent completion.
One invocation per unit; interrupted calls without retained replies are execution
failures and are never replaced. Saved replies may be processed after restart.

Exploratory binary acceptance comparisons use Cochran's Q, exact pairwise McNemar
with Holm correction within each model's three pairs, and the R2 minus R0 paired
bootstrap (10,000 resamples, seed 42, 95% percentile interval) and Cliff's delta.
Exclude missing units and execution failures from paired tests and count those
exclusions. Empty comparisons have null estimates. This single incident with
deterministic repeats does not establish population effects.
