# P12 — Plan and Architecture Decisions

## Approach

The file-level test is a separate test built from the same parts as the database-level test: an incident with scripted
damage and concurrent legitimate work, host-side evidence, three input constructions, a model procedure, two
comparators without a model, restore in a sandbox, and checks against a script-derived reference. The recovery unit is
a recorded ZFS snapshot, because file state can only be restored to a snapshot.

The lab is rebuilt in a fresh repository and a fresh VM by scripts, and the P12 run goes through those scripts.

## ADRs

- ADR-1 Scenario. SC-02 as defined in scenarios/sc02 and lib/lab_sc02.py, with the tree layout of
  lib/lab_sc02_layout.py: a protected tree `workspace` with `config/` (a README and `settings.txt`), `records/`
  (twelve files `f1.txt`-`f12.txt` and `nested/`) and `build/`. Legitimate file churn in `build/`: each change set
  creates `t<n>.txt`, appends to the previous file and deletes `t<n-3>.txt`, then pauses 0.4 s; a change set waits
  for any snapshot in progress, so the achieved period is longer and is measured from `fs-workload.jsonl`.
  Database work runs at 6 transactions per second. The injection overwrites `config/settings.txt` and removes
  `records/` recursively; 60 s baseline, 4 s after. Model inputs show these paths, so the names carry no role label,
  as in the database-level test, where damage and legitimate work share one relation name.
- ADR-2 Snapshots. One recorded snapshot every 2 s from before the baseline (the loop starts with evidence
  capture) until 4 s after the injection ends,
  plus the generator's open, pre-injection and post-capture snapshots, all through one writer with collision-free
  names (UTC milliseconds plus a sequence number) and one host record per incident. Each snapshot keeps the P0 order:
  snapshot, recorded LSN, WAL switch.
- ADR-3 Intervals and visibility. Interval i is the span between recorded snapshots i-1 and i, carrying both names,
  recorded times and recorded LSNs. A file operation is visible when its net effect between the two snapshots is a
  change (a file created and deleted inside one interval is invisible); C-7 requires every visible recorded operation
  to appear in its interval's differences and every captured difference to be explained by a recorded operation.
- ADR-4 Anomaly score. Per interval: files deleted, modified and created. Baseline: intervals that end before the
  recorded injection start (the known-onset rule of the database-level test, stated as the same limitation). Score:
  the largest standardised deviation across the three features, with the standard deviation floored at 1 operation;
  flagged at 3 or more.
- ADR-5 Selection for inputs. As PB-6: the three intervals with the highest scores, ties to the earlier interval.
- ADR-6 Inputs. Raw Log Excerpts: every captured difference in those intervals, one JSON line each
  (interval, from and to snapshot, from and to time, change type, path relative to the protected root), ordered by
  interval then path. Structured Summaries: one JSON row per interval (interval, anomaly score, last safe snapshot =
  the interval's start snapshot). Written Summaries: one templated sentence per interval ("Interval N [t0 .. t1]:
  d files deleted, m modified, c created under <top directory>; anomaly s."). Every input begins with the same one-line catalogue of the selected intervals' boundaries (interval, from and
  to snapshot, from and to time; no log positions, scores or reference), so that every locator type can be
  resolved from visible evidence in every input. Written Summaries name the parent directory with the most
  changes, mirroring the database-level template's most-changed table. Same instruction wrapper for all three.
- ADR-7 Answer reading. Exactly one COORDINATE line and no REFUSAL line. Locators: `interval=N` resolves to the start
  snapshot of interval N (interval N must be visible); `snapshot=<name>` resolves to that snapshot (must be visible);
  `ts=<ISO-8601 UTC>` resolves to the latest visible snapshot recorded at or before it. Each locator resolves
  independently; accepted if at least one resolves and all resolved agree; otherwise a rule rejection.
- ADR-8 Reference and damage manifest. Reference = the latest recorded snapshot whose recorded time is before the
  injection start. Damage manifest = the injection's targets expanded against the reference snapshot's fingerprints.
- ADR-9 Checks and verdict v2. Restore = the protected dataset cloned at the chosen snapshot, and the database replayed
  to that snapshot's recorded LSN. Damage retained = any manifest file missing or not matching its reference
  fingerprint. Legitimate file loss = the number of legitimate file operations visible in the intervals after the
  chosen snapshot up to the reference. Database checks run as for SC-02 before (row loss for the concurrent database
  work). Verdict v2: any retained damage (file or database) = checked damage remains; else any loss = extra work lost;
  else correct; failed restore = not recovered. Verdict v1 and its records are unchanged.
- ADR-10 Comparators. Fixed-rule ranker: the latest snapshot before the first flagged interval (the "safe frontier");
  if none is flagged, it records a run failure as the database-level ranker did. Time estimate: the approximate
  incident time recorded by the generator plus a declared 20 s error, resolved to the latest recorded snapshot at or
  before it.
- ADR-11 Models and settings. The Primary Sweep models, gateway and decoding (temperature 0, top-p 1, seed 42,
  8,192 output tokens); identities verified against the recorded digests before the run.
- ADR-12 Analysis. Primary, descriptive: per model and input, counts of accepted, rejected, declined, correct,
  extra work lost, checked damage remains, not recovered; file and row loss. Exploratory tests as in the Primary Sweep.
  Frozen before the first call.

## Sizing

One incident; 45 model calls; two comparator points; at most 47 restores plus four controls.

## No new constitutional article

The existing articles apply (provenance only for scoring, the model-view guard, read-only gates, frozen contracts).
