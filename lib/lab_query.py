"""lab-query: DuckDB views bound to ledger files in place. No ETL store of record."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from lab_paths import current_incident, env, evidence_dir

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3

DDL_TABLE = "lab_ddl_audit"
HB_TABLE = "lab_heartbeat"

# Default views never project principal (Article II / contract §5).
VIEWS_SQL = """
CREATE OR REPLACE VIEW db_changes AS
SELECT action, lsn, timestamp, schema, "table", columns, identity, pk
FROM read_json_auto('{db_jsonl}', format='newline_delimited', union_by_name=true, ignore_errors=true)
WHERE action IN ('I', 'U', 'D')
  AND coalesce("table", '') NOT IN ('{hb}', '{ddl}');

CREATE OR REPLACE VIEW heartbeats AS
SELECT action, lsn, timestamp, schema, "table", columns, pk
FROM read_json_auto('{db_jsonl}', format='newline_delimited', union_by_name=true, ignore_errors=true)
WHERE action = 'I' AND "table" = '{hb}';

CREATE OR REPLACE VIEW ddl_events AS
SELECT action, lsn, timestamp, schema, "table", columns, pk
FROM read_json_auto('{db_jsonl}', format='newline_delimited', union_by_name=true, ignore_errors=true)
WHERE action = 'I' AND "table" = '{ddl}';

CREATE OR REPLACE VIEW snapshots AS
SELECT snapshot, wall_clock, lsn
FROM read_json('{snapshots}', format='array');

CREATE OR REPLACE VIEW fs_diff AS
SELECT snap_from, snap_to, change_type, path
FROM read_csv('{fs_diff}', delim='\\t', header=false, auto_detect=false, ignore_errors=true, null_padding=true,
              columns={{'snap_from': 'VARCHAR', 'snap_to': 'VARCHAR', 'change_type': 'VARCHAR', 'path': 'VARCHAR'}});

CREATE OR REPLACE VIEW fs_hashes AS
SELECT snapshot, path, sha256
FROM read_csv('{fs_hashes}', delim='\\t', header=false, auto_detect=false, ignore_errors=true, null_padding=true,
              columns={{'snapshot': 'VARCHAR', 'path': 'VARCHAR', 'sha256': 'VARCHAR'}});
"""


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def duckdb_bin() -> str:
    path = os.environ.get("DUCKDB_BIN") or env("DUCKDB_BIN")
    if not Path(path).is_file():
        die(EXIT_PRECOND, f"precondition failed: DuckDB binary missing at {path}")
    return path


def views_sql(incident: str) -> str:
    ed = evidence_dir(incident)
    files = {
        "db_jsonl": str(ed / "db.jsonl"),
        "snapshots": str(ed / "snapshots.json"),
        "fs_diff": str(ed / "fs_diff.tsv"),
        "fs_hashes": str(ed / "fs_hashes.tsv"),
        "hb": os.environ.get("HEARTBEAT_TABLE", HB_TABLE),
        "ddl": os.environ.get("DDL_AUDIT_TABLE", DDL_TABLE),
    }
    for key in ("db_jsonl", "snapshots", "fs_diff", "fs_hashes"):
        p = Path(files[key])
        if not p.is_file():
            die(EXIT_PRECOND, f"precondition failed: ledger file missing {p}")
    return VIEWS_SQL.format(**files)


def run_sql(incident: str, sql: str) -> str:
    preamble = views_sql(incident)
    script = preamble + "\n" + sql.strip().rstrip(";") + ";\n"
    proc = subprocess.run(
        [duckdb_bin(), "-json", "-c", script],
        text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: duckdb: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def main(argv: list[str]) -> int:
    if len(argv) == 1:
        incident, sql = current_incident(), argv[0]
    elif len(argv) == 2:
        incident, sql = argv
    else:
        die(EXIT_USAGE, "usage: lab-query <incident> \"<sql>\"")
    if "COPY " in sql.upper() or "CREATE TABLE" in sql.upper():
        die(EXIT_USAGE, "usage: lab-query is read-only; COPY/CREATE TABLE against the ledger is refused")
    out = run_sql(incident, sql)
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
