# P11 analysis amendment 1: denominators, stopping and missing results

Authority: Articles XIII, XV, XVIII, XIX, XX and XXI.
Decision: ADR-P11-1-contracts. Frozen at R001 before any re-parse.
Supersedes ambiguities in A1/A2/A4 and the universal wording in A3.1/A5.
The original plan remains unchanged and is consumed with this amendment.

## P1. Units and denominators

Core analysis uses the last joined P10 attempt per planned unit, following
P10's attempt rule, plus all authorised R004 submissions. Historical attempts
are re-parsed and separately reported. No new selection based on verdict.
Recovery accuracy and safe-or-better rate both divide by accepted, successfully
scored submissions. Acceptance divides by every current submitted unit plus
any confirmatory submissions, including failures. Report all numerator and
denominator counts, refusals and failures. Infeasible P10 units are displayed
as infeasible, not zero-accuracy trials. Never score a harness failure as a
model refusal. Stop the scoring task on an infrastructure error, retaining its
failure record, and repair it before analysis.

## P2. Bootstrap and evaluability

Use 10,000 resamples and seed 42. H4 pools accepted anchor outcomes across the
three models, `correct=1`, other scored verdicts `=0`. Reuse the unchanged P9
`bootstrap_paired_diff` with `(outcome, 0)` pairs for its mean and 95% interval.
The zero column is a mathematical device, not a paired experimental arm.
H1-R independently resamples accepted anchor and S* samples, using the existing
P10 `bootstrap_two_sample` routine and P9 percentile-index convention. Replicate
numbers at different scales do not imply a paired trial. The effect is anchor
accuracy minus S* accuracy. Bonferroni divides 0.05 by three: each two-sided
interval has confidence 98.33333333333333%. A positive lower limit supports
degradation for that model. Report differences and both limits even if null.

H4 is evaluable only with at least five accepted anchor submissions per model.
H1-R is evaluable per model only with at least five accepted submissions at
both endpoints. Global H1-R HOLDS if any evaluable comparison has a positive
lower limit; it is NULL only if all three are evaluable and none does.
Otherwise it is NOT_EVALUABLE. H4 likewise uses NOT_EVALUABLE for insufficient
data, never a fabricated numerical interval. Keep partial descriptive metrics.
Fixed greedy seed-42 repeats are not independent incident replications;
bootstrap intervals describe this recorded set and cannot establish population
generalisability or an equivalence claim.

## P3. One finite confirmatory batch

For each of the six anchor/S* R0 cells, compute `N = max(0, 5 - accepted)` from
R003 selected rows. If any N is positive, R004 makes exactly N authorised new
submissions for that cell, using the frozen prompt, model identity and decoding.
It never retries model refusals until success. This is one finite batch, not
optional stopping on a favourable score. If refusals leave fewer than five
accepted, report the shortfall and apply P2. Infrastructure failures are
retained and cannot be relabelled. Missing external credentials block the
affected calls. No unplanned cell or infeasible prompt is submitted.

## P4. Interpretations

Retain A3.2 and A3.3 verbatim. A3.3 is also the claim-withdrawal wording when
H4 is NOT_EVALUABLE, with the missing-data explanation immediately before it.
Replace A3.1 with this bounded, verbatim wording:

> With the answer-grammar instrument repaired, raw-evidence recovery is correct
> at small scale on this incident and model set. No loss of R0 accuracy was
> detected between the tested anchor and upper within-window points. Combined
> with P10's H2, the compact representation's demonstrated advantage at scale
> is feasibility, not within-window precision.

If H4 HOLDS and H1-R is NOT_EVALUABLE, emit instead:

> With the answer-grammar instrument repaired, raw-evidence recovery is correct
> at small scale on this incident and model set. The within-window degradation
> question remains not evaluable because too few answers could be scored at
> the required endpoints. P10's feasibility finding remains unchanged.

A non-significant difference cannot prove no degradation anywhere in a context
window. If H1-R is NULL, state that no degradation was detected at the tested
endpoints and that this does not establish equivalence. If H3-R fails, report
every affected occurrence and revisit the earlier safety claim. Never treat a
failed safety hypothesis as a reason to hide a row or make the gate green.

## P5. Reproduction and immutable inputs

The analysis verifies the R001 digests, per-row digests, input hashes and
production times before calculating metrics. Derived JSON, Markdown and SVG
contain no regeneration timestamp and must rebuild byte-identically. Inherit
P10's canonical R0/R2 size curves and fixed context limits from its recorded
rows; draw them anew in the P11 figure without touching P10's figure.

P11 preserves every pre-existing experimental artefact, including prior review
bundles. New P11 review outputs and negative copies live under logs/review/R001
through R007 or logs/review/P11. Prior gate code runs unchanged in an isolated
copy under that tree so its fixed output paths cannot overwrite prior records.
Its actual failed checks stay failed. A pre-existing red P10 gate cannot be
waived as green or repaired by rewriting its recorded result. P11 cannot claim
full close-out while AC-P11-13 requires an unmet prior gate.
