# FROZEN CONTRACT — statistical-analysis-plan (P9, PRE-REGISTERED)

Status: FROZEN at N001 under Article XXI BEFORE any sweep row exists. Digest pinned.
N005 refuses to run if this digest changed after the first sweep row was generated.

## 1. Primary outcome
Per (representation x model) cell: determination_rate = determinations / K, and
(for determinations only) the P4-scored verdict distribution over
{correct, incorrect-safe, incorrect-corrupt, not-recovered}, plus damage_rows_retained
and legit_rows_lost against the oracle.

## 2. Pairing unit
The incident. All arms/representations/models decide against the SAME frozen SC-01
(and SC-02) incident ledger, so comparisons are PAIRED on the incident. Paired
differences are the primary comparison (shared-incident variance reduction).

## 3. Pre-registered hypotheses and tests
- H1 (representation effect): determination_rate differs across R0/R1/R2.
  Test: Cochran's Q across the three representations on the binary determination
  outcome (paired over replicate+incident), then pairwise McNemar with Holm correction.
- H2 (model-invariance): the R2>=R0 determination_rate ordering holds within EACH model.
  Reported per model with bootstrap 95% CIs on the R2-R0 rate difference
  (10,000 resamples, seed pinned). Declared invariant IFF the CI lower bound for
  (R2 - R0) is > 0 for every model.
- Effect size: Cliff's delta for rate differences; report magnitude, not only sign.
- Multiple comparisons: Holm-Bonferroni across the pairwise representation tests
  (family = the 3 pairwise comparisons per model).

## 4. Pre-declared interpretations (report-what-it-shows, Article XXI.3)
- If H1 holds and H2 holds: "representation governs modest-model actionability,
  invariant across tested models/families" — scoped to SC-01(/02), K=5, 3 models.
- If H1 holds but H2 fails (e.g. advantage collapses on the larger model):
  "representation benefit is inversely related to model capability; largest exactly
  where the operator is constrained to a small local model" — this STRENGTHENS the
  data-residency / operator-assist argument and MUST be reported as such.
- If H1 fails: "no detectable representation effect on determination at this scale" —
  reported honestly; the compactness and validity-methodology contributions stand.

## 5. Sample-size honesty
K=5 x 3 models is a feasibility/proof-of-concept scale, NOT a powered study. The report
MUST state this and MUST NOT attach universal language to n=1 scenario evidence.
No result is upgraded to "significant" without the pre-registered test and its CI.

## 6. Exploratory section
Any non-pre-registered analysis is placed under a clearly labelled
"Exploratory (not pre-registered)" heading and cannot override Section 4.
