"""lab-inject-sc01: near-instant bulk DELETE as lab_agent. Lab-contained."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from lab_paths import env, evidence_dir
from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, require_lab, scenario_config,
    scenario_relations, ssh_psql, write_json,
)
from lsn import lsn_norm

CITATION = (
    "Ruan et al., 2024; Naihin et al., 2023 — destructive database write / "
    "agent tool-call irreversibility"
)


def pg_lsn() -> str:
    proc = ssh_psql("SELECT pg_current_wal_lsn();")
    if proc.returncode != 0:
        die(EXIT_PRECOND, f"precondition failed: cannot read WAL LSN: {proc.stderr.strip()}")
    return lsn_norm(proc.stdout.strip().splitlines()[-1].upper())


def pg_clock() -> str:
    proc = ssh_psql(
        "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', "
        "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"');"
    )
    if proc.returncode != 0:
        die(EXIT_PRECOND, f"precondition failed: cannot read clock: {proc.stderr.strip()}")
    return proc.stdout.strip().splitlines()[-1]


def inject(incident: str, relation: str, n: int) -> dict:
    require_lab()
    allowed = scenario_relations()
    if relation not in allowed:
        die(EXIT_ASSERT, f"assertion failed: refusing non-scenario relation {relation!r}; allowed={sorted(allowed)}")
    lsn_start = pg_lsn()
    t_start = pg_clock()
    sql = (
        f"SELECT current_user;\n"
        f"BEGIN;\n"
        f"DELETE FROM public.{relation} WHERE id IN "
        f"(SELECT id FROM public.{relation} ORDER BY id LIMIT {int(n)}) "
        f"RETURNING id;\n"
        f"SELECT txid_current();\n"
        f"SELECT pg_current_wal_lsn();\n"
        f"COMMIT;\n"
        f"SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', "
        f"'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"');\n"
    )
    proc = ssh_psql(sql, role=env("ROLE_AGENT"))
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: inject: {proc.stderr.strip()[-2000:]}")
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if len(lines) < 4:
        die(EXIT_ASSERT, f"assertion failed: unexpected inject output: {lines!r}")
    who = lines[0]
    if who != env("ROLE_AGENT"):
        die(EXIT_ASSERT, f"assertion failed: injector connected as {who!r}")
    t_end = lines[-1]
    lsn_end = lsn_norm(lines[-2].upper())
    xid = int(lines[-3]) & 0xFFFFFFFF
    ids: list[int] = []
    for item in lines[1:-3]:
        if item.isdigit():
            ids.append(int(item))
    if len(ids) != n:
        die(EXIT_ASSERT, f"assertion failed: DELETE RETURNING produced {len(ids)} ids, expected {n}")
    remaining = ssh_psql(
        f"SELECT count(*) FROM public.{relation} WHERE id IN ({','.join(str(i) for i in ids)});"
    )
    if remaining.returncode != 0 or remaining.stdout.strip() != "0":
        die(EXIT_ASSERT, f"assertion failed: destroyed ids still present: {remaining.stdout.strip()}")
    ops = [{
        "op_index": i,
        "table": relation,
        "action": "D",
        "natural_key": kid,
        "principal": env("ROLE_AGENT"),
        "xid": xid,
        "command_tag": None,
        "object_identity": None,
        "wall_clock": t_end,
    } for i, kid in enumerate(ids)]
    rec = {
        "scenario_id": "SC-01",
        "damage_class": scenario_config().get("SC01_ORACLE_DAMAGE_CLASS", "database data"),
        "timing_pattern": scenario_config().get("SC01_ORACLE_TIMING_PATTERN", "near-instant"),
        "archetype_citation": CITATION,
        "principal": env("ROLE_AGENT"),
        "relation": relation,
        "sql": f"DELETE FROM public.{relation} WHERE id IN (SELECT id FROM public.{relation} ORDER BY id LIMIT {n})",
        "commit_lsn": lsn_end,
        "commit_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "server_clock": t_end,
        "rows_destroyed": len(ids),
        "row_ids": ids,
        "row_bytes": [64] * len(ids),
        "destroyed_bytes": 64 * len(ids),
        "xid": xid,
        "ops": ops,
        "affected_natural_keys": ids,
        "t_start": t_start,
        "t_end": t_end,
        "lsn_start": lsn_start,
        "lsn_end": lsn_end,
        "incident": incident,
    }
    ed = evidence_dir(incident)
    ed.mkdir(parents=True, exist_ok=True)
    write_json(ed / "injection_log.json", rec)
    # P1 oracle still reads injection.json
    write_json(ed / "injection.json", rec)
    print(json.dumps({
        "ok": True,
        "changed": True,
        "incident": incident,
        "injection_log": str(ed / "injection_log.json"),
        "commit_lsn": rec["commit_lsn"],
        "rows_destroyed": rec["rows_destroyed"],
        "principal": rec["principal"],
        "xid": xid,
        "lsn_start": lsn_start,
        "lsn_end": lsn_end,
        "t_start": t_start,
        "t_end": t_end,
    }, sort_keys=True))
    return rec


def main(argv: list[str]) -> int:
    require_lab()
    cfg = scenario_config()
    incident = None
    relation = cfg.get("SC01_RELATION", "p2_probe")
    n = int(cfg.get("SC01_INJECT_ROWS") or os.environ.get("SC01_INJECT_ROWS", "200"))
    i = 0
    while i < len(argv):
        if argv[i] in {"--incident", "--relation", "--rows"} and i + 1 >= len(argv):
            die(EXIT_USAGE, "usage: lab-inject-sc01 <incident> [--relation NAME] [--rows N]")
        if argv[i] == "--incident":
            incident = argv[i + 1]; i += 2; continue
        if argv[i] == "--relation":
            relation = argv[i + 1]; i += 2; continue
        if argv[i] == "--rows":
            n = int(argv[i + 1]); i += 2; continue
        if incident is None and not argv[i].startswith("--"):
            incident = argv[i]; i += 1; continue
        die(EXIT_USAGE, "usage: lab-inject-sc01 <incident> [--relation NAME] [--rows N]")
    if not incident:
        die(EXIT_USAGE, "usage: lab-inject-sc01 <incident> [--relation NAME] [--rows N]")
    inject(incident, relation, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
