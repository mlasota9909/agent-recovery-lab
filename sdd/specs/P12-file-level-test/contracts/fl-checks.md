# File-level reference, checks, comparators and controls (P12 ADR-8 to ADR-10)

This contract is independent of the database-level verdict v1 contracts. File
commands use the existing incident evidence directory. JSON artifacts carry
`incident_id` and a schema version; source evidence is never rewritten.

## Reference

`bin/lab-fl-reference <incident>` writes `fl-reference.json` (schema 1).
It reads `snapshots.json`, `fs_hashes.tsv`, `fs_diff.tsv`, `fs-workload.jsonl`
and `injection.json`. Snapshot validation and ordering are those of fl-inputs.md.
Reference = the latest snapshot with recorded time strictly before `t_start`,
regardless of any older oracle coordinate or injection reference label.

The artifact contains `coordinate` (snapshot, time, lsn, lsn_int),
`reference_fingerprints` (relative path to SHA-256), `damage_manifest`
(path, sha256, target_indices), `legitimate_intervals` and `source_sha256`.
Fingerprints are the capture format: snapshot, relative path, SHA-256, tab
separated, without a header. All inventories are validated; only reference
fingerprints provide expected file bytes. Injection `fs_ops` supply targets.
File targets must exist in the reference. Recursive directory deletion expands
only to descendants separated by `/`, never a substring match. Overlapping
targets produce one manifest entry per regular file. Empty directories add no
file entry. An empty damage manifest is a precondition failure.

Exact C-7 must pass on the recorded intentions and differences. Every intention
has `source` (legitimate or injection), `kind` (file or directory), `operation`,
`path` and UTC `ts`. Per-interval legitimate regular-file intentions retain their
original index, time, path, operation and visibility. A create followed by delete
within one interval is invisible; all intentions contributing to a visible net
change count individually, including repeated appends. This is the C-7
convention, not a count of unique paths. Directory operations are excluded from
legitimate file loss. Boundaries use `(from_time, to_time]`.

Only scoring and controls consume the reference and its manifest. Interval
construction, inputs, prompts, answer reading and comparators do not read them.
The checker rebuilds the reference in memory and demands exact equality before
use, rejecting changed source evidence or edited derived truth.

## Restore and checks

`bin/lab-fl-check <incident> <snapshot>` restores files with the existing
filesystem clone function using the **exact named snapshot**, and restores the
database with the existing PITR function to that snapshot's recorded LSN.
It selects the explicit incident's runtime, never the current incident's runtime.
Equal-LSN snapshots remain distinct filesystem choices. It requires the database
restore's stopped-at-target check and its selected target LSN to agree.

P12 reports are `fl-checks/<snapshot>.json` (schema 2). Host restore details and
the existing `fs_probe.tsv` live under `var/restore/<incident>/fl_<digest>/`.
The guest sandbox is torn down after checks, including failures. Cleanup errors
are retained and produce a failing command/control; they do not rewrite measured
counts. An incident lock serializes checking and report reuse.

Every reference file is compared with its restored bytes. A missing manifest
file and a changed manifest fingerprint are both retained damage. Each damaged
file counts once, even if targeted several times. Nonmanifest differences are
reported for diagnosis; workload loss is measured from intentions, so later
legitimate changes are not classified as damage. Legitimate file loss sums visible
operations in intervals strictly after the selected boundary through the reference
boundary. Later selections have zero loss against this reference.

The database row and column checks follow SC-02's existing path: read restored
IDs and DDL; compare destroyed/legitimate ID sets from `oracle-manifest.json`;
count workload rows with `chosen_lsn < commit_lsn <= reference_lsn`. Use the file
reference's recorded LSN as the endpoint, without changing the database oracle.
Keep the analytical count of all rows after the choice as a separate diagnostic.
As before, fewer columns classify as damage, other DDL differences as loss.
Missing or invalid evidence fails before restore; malformed row LSNs fail checks.

The existing two-column `fs_probe.tsv` accepts path/hash or hash/path, as well as
sha256sum lines. Relative paths resolve within the sandbox. Absolute probe paths
must lie inside that sandbox. A probe may not override a reference fingerprint.
Probe mismatches count as retained file damage, deduplicated against the manifest.
Failed remote reads are failed checks, never successful missing-file observations.

`summary` counts are `damage_files_retained`, `damage_rows_retained`,
`legit_file_operations_lost`, `legit_rows_lost`, `schema_damage`, `schema_loss`
and `probe_mismatches`. Verdict order:

1. Failed restore or incomplete checks: `not_recovered`, with null counts and a
   failure reason. Unmeasured counts are never zero-filled.
2. Any retained file/row/schema damage: `checked_damage_remains`.
3. Otherwise any legitimate file/row/schema loss: `extra_work_lost`.
4. Otherwise: `correct`.

Reports also carry the coordinate, restore details, filesystem/database checks,
input digests, cache key and probe digest. A repeated snapshot reuses its stored
report, including failure reports, only when evidence and probe digests agree.
Changed evidence or probes cause refusal rather than silently reusing stale data.
Use a fresh incident to repeat collection after evidence changes.

## Comparators and controls

`bin/lab-fl-rank <incident>` reads `fl-intervals.json` and `snapshots.json`.
It takes the start snapshot of the first flagged interval in chronological order,
not the highest score. No flag yields `run_failure`, a null coordinate and exit 1.
`bin/lab-fl-naive <incident>` reads only `incident.json` and `snapshots.json`.
It adds **+20 seconds** to `approx_incident_time` and chooses the latest recorded
snapshot at or before that cutoff. A cutoff before all snapshots is a run failure;
one after the last snapshot picks the last. There is no error override or hidden
onset lookup. Missing evidence is a precondition failure.

They write `fl-rank.json` and `fl-naive.json` (schema 1), including comparator,
outcome, coordinate or null, reason, and the flag index or estimate parameters.
Accepted points are checked separately by lab-fl-check.

`bin/lab-fl-controls <incident>` writes `fl-controls.json`: reference = correct;
first snapshot strictly after injection `t_end` = checked damage remains;
earliest = extra work lost; separately restored reference with altered bytes =
checked damage remains and a positive probe mismatch count. The altered restore
uses a manifest file and the existing probe mechanism, with its own cache entry
`fl-checks/control-tampered.json`. The ordinary reference cache stays independent.
Every control is retained; any failed expectation exits 1. No post-damage snapshot
is a precondition failure, and an earliest snapshot that loses no work fails the
control rather than being substituted with a different choice.

Successful commands exit 0, precondition failures exit 2, usage errors exit 3.
Measured wrong recovery points are valid check outputs and exit 0; not recovered
and cleanup failure exit 1. Derived reference/comparator/control files can be
deterministically regenerated; cached check reports are not overwritten.
