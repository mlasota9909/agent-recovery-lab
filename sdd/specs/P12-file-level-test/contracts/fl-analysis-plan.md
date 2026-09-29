# File-level design and analysis plan (P12 ADR-11 and ADR-12)

## Design and freeze

One fresh SC-02 incident, three inputs R0/R1/R2, three Primary Sweep models and
five repeats indexed 0..4: 45 planned units, plus the fixed-rule ranker and time
estimate. Models are gb10a-deepseek-v4-flash, gympc-gemma4-26b and
alienware-qwen38-27b, with recorded identities from runtime/p9-model-set.json.
Use the Primary Sweep gateway configuration and temperature 0, top-p 1, seed 42,
8,192 output tokens uniformly. Verify actual served identities against the recorded
digests before collection. A freeze records identities; it does not verify servers.

Before the first call, `bin/lab-fl-freeze <incident>` writes this directory's
`frozen-hashes.json` using exclusive creation; it refuses to overwrite. All five
P12 contracts, the spec and plan, the model set, and each built model-view JSON,
content text and assembled prompt are pinned with SHA-256 over exact bytes.
Input files must match fresh construction and pass the unchanged model-view guard.
The model set must contain recorded identities, not the committed empty template.
Paths in the freeze are relative to the checkout; the incident, UTC freeze time,
planned unit count and decoding are recorded. Existing `fl-study-runs*` files in
the default or configured results directory prevent freezing, even if empty.
No forced overwrite is supported. Freeze hashes must be checked before study
calls and analysis. Study orchestration performs that enforcement and records each
call's start time after the freeze. No calls are part of the freeze command.

## Primary descriptive reporting

For each model/input cell report all five planned units and counts of accepted,
rule rejected, declined and execution failures. Missing planned units are listed
explicitly; they are never refusals. Preserve every attempt and failure; a resumed
run skips recorded units. No outcome-driven replacement or retry is permitted.

For accepted answers report counts of correct, extra work lost, checked damage
remains and not recovered, using only verdict v2. Accepted = the sum of those
four verdict counts once checking is complete. Accepted but unchecked points
remain explicitly pending and prevent a final complete analysis. Rejections,
declines and execution failures have no restore verdict. Report accepted/5 and
correct/5 alongside correct/accepted with explicit denominators.

Report retained file damage, retained row damage, lost legitimate file operations
and lost legitimate rows per accepted unit, plus sums, medians and ranges per cell
over successfully checked units. Never turn null counts from failed checks into
zeroes. File loss counts operations, not unique files. Schema counts remain
visible diagnostics. Duplicate selected snapshots may share one check report;
each planned unit still contributes once to cell counts. Record the two comparator
coordinates, verdicts and loss counts separately; do not pool them with model units.
Controls are validation evidence, not study observations.

## Exploratory tests

All tests are exploratory; descriptive outcomes above are primary. Follow the
Primary Sweep comparisons on binary acceptance (accepted = 1, rejected/declined
= 0): Cochran's Q across inputs, pooled over model/repeat blocks and per model;
exact pairwise McNemar for R0/R1, R0/R2 and R1/R2, with Holm correction within
each model's three-comparison family at alpha .05. Pair by incident/model/repeat;
exclude incomplete blocks and execution failures from tests only, while retaining
their counts beside every aggregate. Report tested block counts and exclusions.

For each model report the paired R2 minus R0 acceptance difference with a 95%
percentile bootstrap interval, 10,000 paired resamples, seed 42, and Cliff's delta
on binary acceptance with magnitude. Empty comparisons yield null estimates, not
zero evidence of an effect. With no discordance McNemar p = 1 and with no variation
Cochran's Q = 0, p = 1. Describe whether each interval's lower bound exceeds zero;
do not promote a common ordering to a primary confirmatory claim.

Report the observed directions and uncertainty even if they disagree across
models. One incident and five deterministic repeats per cell are a feasibility
study, not independent incident replication or a powered population study.
Do not generalise beyond this incident, file workload, models and inputs. Known
onset defines the baseline, so this does not estimate unknown-onset detection.
Additional analyses must be marked exploratory and cannot replace the primary
descriptive tables. Keep database-level studies and verdict v1 records unchanged.
