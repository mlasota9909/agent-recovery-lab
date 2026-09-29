# WI-P12-C — File capture, file operation records, exact file reconciliation

Goal: every incident captures file evidence completely, or stops. Read the P12 spec (FR-3, FR-4, FR-7 parser part)
and plan (ADR-2, ADR-3). Depends on WI-P12-A.

## Known defects to fix (verified)
- `lib/lab_generate_sc01.py` (fs_capture step) and `lib/lab_generate_p7.py` (fs_capture step) call
  `lab-fs-capture <incident>`; the tool requires `diff <from> <to> [--incident ID]` or `hash <snap> [--incident ID]`
  and exits 3; the generators then create empty `fs_diff.tsv`/`fs_hashes.tsv` placeholders and continue.
- `lib/lab_fs_capture.py`: dataset and mount selection follows `LAB_ACTIVE_INCIDENT`/`archive/current`, not the
  `--incident` argument.
- Loop snapshots (`bin/lab-snapshot-loop`, `lib/lab_snapshot_tick.py`) and generator snapshots (`bin/lab-snapshot`)
  are two writers with one-second names and an unlocked check-then-create; `copy_snapshots` in `lib/lab_generate_p7.py`
  replaces the evidence snapshot list with the archive list, losing loop records; a loop failure is not noticed.
- `lib/lab_ledger_account.py` rule C-7 checks only workload actions starting with `FS` (none are written) and matches
  paths as substrings of the whole diff file.
- `lib/lab_sc02.py` records churn operations without paths (`{op:"churn",n,ts}`).
- `lib/lab_validate.py` `parse_hash_lines` expects two columns; `lab-fs-capture hash` writes three
  (`snapshot<TAB>relative_path<TAB>sha256`).

## Do
1. One snapshot writer: collision-free names (UTC milliseconds plus a per-incident sequence number), a per-incident
   lock, recorded LSN and WAL switch in the P0 order, one host record per incident (`archive/<incident>/snapshots.json`)
   that is appended under the lock and copied to the evidence folder by merging, never replacing. The generators'
   labelled snapshots (open, pre_injection, post_capture) go through the same writer with their labels. A 2-second
   loop (interval from configuration, default 2) runs from before the baseline until after the damage window; the
   generator stops it and fails the incident if the loop failed or missed an interval by more than one period.
2. Generators: after the post-capture snapshot, for every consecutive pair of recorded snapshots in recorded-LSN order
   run `lab-fs-capture diff A B --incident ID`, and for every recorded snapshot run `lab-fs-capture hash S --incident
   ID`; any non-zero exit stops the incident with the tool's message. Remove the placeholder creation.
3. `lab-fs-capture`: `--incident` selects the incident's runtime (dataset, mount) authoritatively.
4. File operation records: the SC-02 legitimate churn records every operation with its path relative to the protected
   root, the operation (create, append, delete) and a UTC timestamp; the injection records its targets (the overwritten
   file and every file and directory removed, enumerated from the reference snapshot before removal). Write them to a
   separate `fs-workload.jsonl` so database accounting is unchanged.
5. Rule C-7 (exact, per plan ADR-3): place each recorded operation in the interval whose snapshot times bracket it;
   compute each path's net effect per interval; every operation with a visible net effect must match a captured
   difference of the right type in that interval, and every captured difference must be explained by a recorded
   operation (legitimate or injection). Report matched, unmatched-recorded, unexplained-captured and invisible counts.
   A scenario that declares file activity fails C-7 when matched is zero or anything is unmatched or unexplained.
6. `parse_hash_lines`: read the three-column capture format (select rows for a given snapshot) and keep the two-column
   probe format.
7. Unit tests with synthetic files for: name uniqueness under concurrent writers, record merging, generator failure
   on a capture error, C-7 exact matching (including an invisible create-then-delete and an unexplained difference),
   and parsing a real three-column line.

## Do not
- Do not run commands that contact the network, a VM, PostgreSQL, ZFS or libvirt. Do not create commits. Do not change
  database-level logic, thresholds or frozen contracts. Do not modify files outside this repository. Do not mention
  tools, assistants or the origin of the changes in any file, comment or message.

## Report
Files changed, new record formats, test results, and anything left for the live dry run to confirm.
