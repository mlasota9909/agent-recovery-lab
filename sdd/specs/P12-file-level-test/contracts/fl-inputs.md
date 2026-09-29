# File-level intervals and inputs (P12 ADR-3 to ADR-6)

## Commands and artifacts

`bin/lab-fl-intervals <incident>` reads only `snapshots.json`, `fs_diff.tsv`,
`fs_hashes.tsv` and `injection.json` in the existing incident evidence directory.
It writes `fl-intervals.json` and emits that JSON on stdout. Snapshot records are
ordered with the existing recorded-LSN ordering, then checked for unique names
and strictly increasing UTC times. Invalidated or unanchored records fail.
Time precedence is `created_at`, `wall_clock`, then `lsn_recorded_at`; LSN precedence
is `recorded_lsn`, then `lsn`. Times are normalised to ISO-8601 UTC with `Z`.

Intervals are numbered from 1. Interval N joins recorded snapshots N-1 and N;
the file-operation boundary convention is `(from_time, to_time]`, as in C-7.
Each interval stores `interval`, `from_snapshot`, `to_snapshot`, `from_time`,
`to_time`, `from_lsn`, `to_lsn`, `counts`, `standardised_deviations`,
`anomaly_score` and `flagged`. Empty intervals remain present with zero counts.

The artifact has `schema_version: 1`, `incident_id`, `threshold: 3.0`,
`source_sha256` (hashes of the four source texts), `baseline` and `intervals`.
`baseline` contains `rule: interval_end_before_injection_start`, `injection_start`
from `injection.json.t_start`, the baseline interval numbers and `statistics`.
Each statistic has `mean`, `stddev` and `scale`. This uses known onset solely for
baseline selection, retaining the database-level test's stated limitation.
No injection target, actor or reference coordinate is projected into inputs.

The three features are `files_deleted`, `files_modified` and `files_created`.
Differences are four-column, headerless TSV: from snapshot, to snapshot, change
type, relative path. Fingerprints are three-column, headerless TSV: snapshot,
relative file path, SHA-256. Blank lines are ignored. Bad columns, noncanonical or
absolute paths, unknown snapshots, nonadjacent differences and duplicate records
fail. All recorded snapshots participate, including snapshots with equal LSNs.

Decisions needed beyond the plan:

- Features count regular files. The captured fingerprint inventories identify
  regular files: `-` uses the start inventory, `+` the end inventory, `M` their
  union. Directory differences remain in R0 but do not inflate file counts.
  Complete successful capture is a prerequisite; inventories are not reconstructed
  from workload intentions. Empty inventories are valid for empty file trees.
- A captured `R` row remains a single raw row with `old_path -> new_path`;
  scoring counts one deletion/creation for each regular-file endpoint. More than
  one arrow separator fails as ambiguous. SC-02 itself has no renames.
- Standard deviation is the population statistic (divide by N). Scale is
  `max(stddev, 1.0)`. Scores are the maximum **signed** `(count - mean) / scale`,
  without clipping, absolute values or rounding. Flagging is inclusive at 3.
  A single baseline interval is valid; no baseline intervals is a precondition
  failure. Only intervals ending strictly before injection start enter baseline.

## Input construction

`bin/lab-fl-inputs <incident> --input R0|R1|R2` reads only `fl-intervals.json`
and `fs_diff.tsv` as incident inputs. It verifies the differences' stored digest
and refuses stale differences. It never opens reference, oracle, damage-manifest,
injection or workload files. All three representations select the same top three
intervals by descending full-precision score, ties to the earlier interval.
If fewer than three intervals exist, all available intervals are selected.
Display order is increasing interval number.

The command writes `fl-inputs/<R>/model-view.json`, `content.txt` and `prompt.txt`
under the incident evidence directory, and prints the model-view JSON. Repeating
a command deterministically replaces its derived files; source evidence is not
modified. The unchanged model-view guard validates the view before any output.
Missing or invalid evidence exits 2, usage errors exit 3, guard rejection exits 1.

The model-view keys are exactly the existing keys: `content` (string),
`incident_id`, `params` (`{"top_n":3}`), `probe_id` (`FL-intervals`),
`representation` (`R0`, `R1`, `R2`) and `telemetry` (`{}`). Metadata is not
inserted into the prompt. Each prompt uses the same `fl-prompt.md` wrapper and
exactly one content string. Prompt boundary markers are reserved and cannot occur
inside content. No reference, answer, damage-manifest or actor fields are emitted.

Each content starts with **one common JSONL catalogue** of the selected interval
boundaries. This is an explicit additional format decision: it exposes both
snapshot names and their times for answer reading, including empty intervals,
without relying on any hidden snapshot lookup. The catalogue contains only
`interval`, `from_snapshot`, `to_snapshot`, `from_time`, `to_time` for each selected
interval; it carries no LSNs, scores, flags, onset time or reference. Only these
catalogued snapshots and intervals can resolve locators, in every representation.

The examples below each show one selected interval; production catalogues contain
up to three. JSON is compact ASCII JSONL, followed by the representation body.

### R0 — Raw Log Excerpts

Every captured difference of each selected interval is included once. Rows carry
exactly its interval boundaries, change type and relative path. Order is interval,
then path, then change type for equal paths. No truncation or row cap applies.

```jsonl
{"intervals":[{"interval":3,"from_snapshot":"s2","to_snapshot":"s3","from_time":"2026-09-29T00:00:04Z","to_time":"2026-09-29T00:00:06Z"}]}
{"interval":3,"from_snapshot":"s2","to_snapshot":"s3","from_time":"2026-09-29T00:00:04Z","to_time":"2026-09-29T00:00:06Z","change_type":"M","path":"sc02-work/keep/will-overwrite.txt"}
{"interval":3,"from_snapshot":"s2","to_snapshot":"s3","from_time":"2026-09-29T00:00:04Z","to_time":"2026-09-29T00:00:06Z","change_type":"-","path":"sc02-work/victim/f1.txt"}
```

### R1 — Structured Summaries

Exactly one JSON row per selected interval: interval number, anomaly score and
`last_safe_snapshot`, meaning that interval's start snapshot. This is the ADR-6
per-interval convention, not an assertion that the snapshot is safe overall.

```jsonl
{"intervals":[{"interval":3,"from_snapshot":"s2","to_snapshot":"s3","from_time":"2026-09-29T00:00:04Z","to_time":"2026-09-29T00:00:06Z"}]}
{"interval":3,"anomaly_score":4.0,"last_safe_snapshot":"s2"}
```

### R2 — Written Summaries

Exactly one templated sentence per selected interval. The directory named is the
parent directory with the most captured changes in that interval (ties: alphabetical
first; both ends of a rename count), mirroring the database-level template, which names
the table with the most changes. Empty intervals use `.` (the protected root). Directory names
are JSON-quoted; scores use their full JSON numeric spelling.

```text
{"intervals":[{"interval":3,"from_snapshot":"s2","to_snapshot":"s3","from_time":"2026-09-29T00:00:04Z","to_time":"2026-09-29T00:00:06Z"}]}
Interval 3 [2026-09-29T00:00:04Z .. 2026-09-29T00:00:06Z]: 4 files deleted, 1 modified, 0 created under "sc02-work/victim"; anomaly 4.0.
```
