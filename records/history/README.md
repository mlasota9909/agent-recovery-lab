# Earlier runs

Runs kept for reference. None is the experiment of record, which is `records/experiment/`.

| Folder | What it holds | Why it was set aside |
| --- | --- | --- |
| `SC01-replication/` | Row-deletion study on reclab01 | Run before the experiment was a single run on one VM |
| `P12/` | File-deletion study on reclab01, its fresh-clone reproduction on reclab02, rehearsals and superseded attempts | Run before the experiment was a single run on one VM |
| `SC03-study/` | Schema-change study on reclab01 | Run before the experiment was a single run on one VM |
| `SC04-study/` | Row-update study on reclab01 | Run before the experiment was a single run on one VM |
| `attempt-1/` | Fresh clone at 09eb0ec on reclab03: file-deletion, row-deletion and schema-change studies | The row-deletion check recorded a copy identical to the reference as not recovered; fixed in 1e81d9e |
| `attempt-2/` | Fresh clone at 1e81d9e on reclab04: file-deletion, row-deletion and schema-change studies | A window holding one heartbeat scored about 941 million in the schema-change study; fixed in 066c169 |
| `attempt-3/` | Fresh clone at 066c169 on reclab05: all four studies | Written Summaries counted only deletions and inserts, so they could not describe updates or schema changes; fixed in 633952f |

Each earlier study folder keeps its own `verify.py`. The attempts use the layout of `records/experiment/`. They ran on
the earlier commits named above, so their frozen code files match those commits rather than the current code, and
they are kept as produced.
