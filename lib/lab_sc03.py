"""SC-03 staged destructive DDL with interleaved legitimate DML."""
from __future__ import annotations

import time

from lab_p3_util import EXIT_ASSERT, die, ssh_psql, utc_now, write_json, write_jsonl
from lab_paths import env, evidence_dir, lab_root
from lab_p7_app import DmlLoop
from lsn import lsn_int, lsn_norm

REL = "sc03_orders"


def _pg(sql: str, role: str | None = None) -> str:
    proc = ssh_psql(sql, role=role)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: psql: {proc.stderr.strip()[-1500:]}")
    return proc.stdout.strip()


def prepare(incident: str) -> dict:
    sql = f"""
DROP TABLE IF EXISTS public.{REL};
CREATE TABLE public.{REL} (
  id bigint PRIMARY KEY,
  amount numeric(12,2) NOT NULL,
  status text NOT NULL DEFAULT 'open',
  CONSTRAINT sc03_amount_positive CHECK (amount > 0)
);
ALTER TABLE public.{REL} REPLICA IDENTITY FULL;
ALTER TABLE public.{REL} OWNER TO lab_agent;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.{REL} TO lab_app;
INSERT INTO public.{REL}(id, amount, status)
SELECT g, 10.00, 'open' FROM generate_series(1, 80) g;
"""
    proc = ssh_psql(sql)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: SC-03 seed: {proc.stderr.strip()[-1500:]}")
    return {
        "baseline_s": 6,
        "after_s": 3,
        "tps": 5.0,
        "mix": "lab_app-dml-interleaved+lab_agent-staged-ddl",
        "relation": REL,
        "baseline_started": utc_now(),
    }


def start_confounder(incident: str) -> dict:
    app = DmlLoop(
        f"UPDATE public.{REL} SET amount = amount + 0.01 WHERE id = {{id}};",
        5.0, REL, id_mod=80,
    )
    app.start()
    return {"app": app, "incident": incident}


def stop_confounder(handle: dict) -> list[dict]:
    rows = handle["app"].stop()
    if len(rows) < 1:
        die(EXIT_ASSERT, "assertion failed: SC-03 confounder produced no DML")
    return rows


def inject(incident: str) -> dict:
    ed = evidence_dir(incident)
    sql_text = (lab_root() / "scenarios" / "sc03" / "inject.sql").read_text(encoding="utf-8")
    statements = [s.strip() for s in sql_text.splitlines() if s.strip() and not s.strip().startswith("--")]
    ops = []
    window_start = None
    for i, stmt in enumerate(statements):
        lsn_before = lsn_norm(_pg("SELECT pg_current_wal_lsn();").upper())
        t0 = utc_now()
        if window_start is None:
            window_start = lsn_before
        out = _pg(
            "SELECT current_user;\nBEGIN;\n"
            + stmt + ";\n"
            "SELECT txid_current();\nSELECT pg_current_wal_lsn();\nCOMMIT;\n",
            role=env("ROLE_AGENT"),
        )
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if not lines or lines[0] != env("ROLE_AGENT"):
            die(EXIT_ASSERT, f"assertion failed: SC-03 DDL not as lab_agent: {lines[:3]!r}")
        xid = int(lines[-2]) & 0xFFFFFFFF
        lsn_end = lsn_norm(lines[-1].upper())
        ops.append({
            "op_index": i,
            "sql": stmt,
            "lsn_before": lsn_before,
            "commit_lsn": lsn_end,
            "xid": xid,
            "t_start": t0,
            "t_end": utc_now(),
            "principal": env("ROLE_AGENT"),
        })
        time.sleep(2.0)
    rec = {
        "incident": incident,
        "scenario_id": "SC-03",
        "principal": env("ROLE_AGENT"),
        "t_start": ops[0]["t_start"],
        "t_end": ops[-1]["t_end"],
        "lsn_start": window_start,
        "lsn_end": ops[-1]["commit_lsn"],
        "commit_lsn": ops[0]["commit_lsn"],
        "timing_pattern": "slow",
        "ops": ops,
        "first_ddl_lsn_before": ops[0]["lsn_before"],
    }
    write_json(ed / "injection.json", rec)
    write_json(ed / "injection_log.json", rec)
    return rec


def oracle(incident: str, inj: dict, app_rows: list, open_snap: dict, pre: dict, post: dict) -> dict:
    from lab_p7 import resolve_lsn
    ed = evidence_dir(incident)
    first_before = lsn_norm(inj["ops"][0]["lsn_before"])
    first_commit = lsn_norm(inj["ops"][0]["commit_lsn"])
    coord = resolve_lsn(first_before)
    sacrificed = []
    for rec in app_rows or []:
        lsn = rec.get("commit_lsn")
        if not lsn:
            continue
        n = lsn_int(lsn_norm(lsn))
        if n >= lsn_int(first_before):
            sacrificed.append({
                "xid": rec.get("xid"),
                "commit_lsn": lsn_norm(lsn),
                "natural_key": rec.get("natural_key"),
                "action": rec.get("action"),
            })
    ddl_n = len(inj["ops"])
    payload = {
        "coordinate": coord,
        "single_coord_optimum_lsn": first_before,
        "first_destructive_ddl_commit_lsn": first_commit,
        "legit_dml_sacrificed": len(sacrificed),
        "legit_dml_sacrificed_ops": sacrificed,
        "ddl_ops_retained": 0,
        "ddl_ops_total": ddl_n,
        "computed_from": "injection ops[].lsn_before of first DDL; ledger-scored app DML with lsn >= that",
        "incident_extra": {
            "single_coord_optimum_lsn": first_before,
            "legit_dml_sacrificed": len(sacrificed),
            "ddl_ops_total": ddl_n,
        },
    }
    man = []
    for rec in app_rows or []:
        if rec.get("commit_lsn"):
            man.append({
                "commit_lsn": rec["commit_lsn"],
                "commit_ts": rec.get("wall_clock"),
                "operation": rec.get("operation"),
                "relation": rec.get("relation") or rec.get("table"),
                "row_ids": rec.get("row_ids") or [],
                "row_count": rec.get("row_count") or 1,
                "principal": rec.get("principal"),
            })
    write_jsonl(ed / "workload-manifest.jsonl", man)
    write_json(ed / "oracle.json", {"incident": incident, "coordinate": coord, "sc03": payload})
    write_json(ed / "sc03-oracle.json", payload)
    if len(sacrificed) == 0:
        die(EXIT_ASSERT, "assertion failed: SC-03 legit_dml_sacrificed=0 but confounder ran through the window")
    return payload
