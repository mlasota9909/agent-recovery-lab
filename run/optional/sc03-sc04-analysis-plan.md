# SC-03 and SC-04 studies

One fresh named incident per scenario: SC-03 (staged schema changes) and SC-04 (scattered
small updates). Each uses the SC-01 replication's method unchanged: the same capture,
windows, anomaly score and three-period selection; R0/R1/R2 from the same builders; the
database prompt; the revised P11 answer grammar with the same `last_safe_lsn_int` indexing;
the three Primary Sweep models with temperature 0, top-p 1, seed 42 and 8,192 output
tokens; five repeats (45 calls per study). Freeze inputs, grammar, generator, checker,
driver, model set and this plan before collection.

Every accepted point is restored into an isolated copy and checked against the reference,
the position the injection recorded just before its first damaging statement. Checked
damage is counted in units: each scripted schema change still present (SC-03) or each
scripted row still holding its damaging value (SC-04). Legitimate work lost counts the
legitimate operations committed after the point and no later than the reference. Verdict
v1: correct, incorrect_safe, incorrect_corrupt, not_recovered.

Report planned, missing, accepted, rule rejected, declined and execution failures per
model/input; accepted verdict counts; damage units retained and work lost per unit; and
pending checks. Store the ranker and the time estimate (approximate incident time plus 20
seconds) separately. Missing units and pending checks prevent completion. One invocation
per unit; interrupted calls without retained replies are execution failures and are never
replaced. Saved replies may be processed after restart.

Report, for each input, whether its selected periods show a position at or after the first
damaging commit (gate record). The selection is not changed when they do not.

Exploratory binary acceptance comparisons use Cochran's Q, exact pairwise McNemar with Holm
correction within each model's three pairs, and the R2 minus R0 paired bootstrap (10,000
resamples, seed 42, 95% percentile interval) and Cliff's delta. Exclude missing units and
execution failures from paired tests and count those exclusions. Empty comparisons have
null estimates. One incident with deterministic repeats does not establish population
effects.
