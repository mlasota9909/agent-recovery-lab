"""SC-01 concurrent lab_app workload with repeated keys. Does not truncate seed rows."""
from __future__ import annotations

import json
import os
import random
import threading
import time

from lab_capture_workload import ALT, PROBE, sql_body, ssh_psql
from lab_p3_util import EXIT_ASSERT, die, scenario_config, utc_now
from lab_paths import env

SEED_SQL = """
CREATE TABLE IF NOT EXISTS public.{rel} (
  id bigint PRIMARY KEY,
  v text NOT NULL
);
ALTER TABLE public.{rel} REPLICA IDENTITY FULL;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.{rel} TO lab_app;
GRANT SELECT, DELETE ON public.{rel} TO lab_agent;
GRANT CREATE ON SCHEMA public TO lab_app;
INSERT INTO public.{rel}(id, v)
SELECT g, 'seed' || g FROM generate_series({lo}, {hi}) AS g
ON CONFLICT (id) DO NOTHING;
"""


def ensure_sc01_seed() -> dict:
    cfg = scenario_config()
    rel = cfg.get("SC01_RELATION", PROBE)
    lo = int(cfg.get("SC01_SEED_KEY_MIN", "1"))
    hi = int(cfg.get("SC01_SEED_KEY_MAX", "400"))
    proc = ssh_psql(SEED_SQL.format(rel=rel, lo=lo, hi=hi))
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: SC-01 seed: {proc.stderr.strip()[-2000:]}")
    count = ssh_psql(f"SELECT count(*) FROM public.{rel};")
    ident = ssh_psql(
        "SELECT relreplident FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = 'public' AND c.relname = '{rel}';"
    )
    return {
        "relation": rel,
        "count": int(count.stdout.strip() or "0"),
        "replica_identity": (ident.stdout.strip() or "?"),
        "seed_min": lo,
        "seed_max": hi,
    }


def plan_sc01_app_cycle(seed: int, relation: str) -> list[dict]:
    """Repeated-key lab_app cycle: cross-txn U, same-txn double-U, delete-reinsert."""
    rng = random.Random(seed)
    base = 88_000_000 + (seed % 1000) * 100
    keys = [base, base + 1, base + 2, base + 3]
    rng.shuffle(keys)
    k0, k1, k2, k3 = keys
    ops: list[dict] = []

    def add(action: str, kid: int | None, *, txn_group: str | None = None,
            v_marker: str | None = None, table: str = relation,
            command_tag: str | None = None, object_identity: str | None = None) -> None:
        rec = {
            "op_index": len(ops),
            "table": table,
            "action": action,
            "natural_key": kid,
            "principal": env("ROLE_APP"),
            "command_tag": command_tag,
            "object_identity": object_identity,
            "txn_group": txn_group,
        }
        if v_marker is not None:
            rec["v_marker"] = v_marker
        ops.append(rec)

    add("I", k0)
    add("I", k1)
    add("I", k2)
    add("I", k3)
    add("U", k0, v_marker=f"u{k0}a")
    add("U", k0, v_marker=f"u{k0}b")
    add("U", k1, txn_group="same-txn-u", v_marker=f"u{k1}a")
    add("U", k1, txn_group="same-txn-u", v_marker=f"u{k1}b")
    add("D", k2)
    add("I", k2)
    add("U", k3, v_marker=f"u{k3}a")
    add("U", k3, v_marker=f"u{k3}b")
    return ops


def plan_sc01_ddl() -> list[dict]:
    return [
        {"op_index": 0, "table": ALT, "action": "CREATE", "natural_key": None,
         "principal": env("ROLE_APP"), "command_tag": "CREATE TABLE",
         "object_identity": f"public.{ALT}", "txn_group": None},
        {"op_index": 1, "table": ALT, "action": "ALTER", "natural_key": None,
         "principal": env("ROLE_APP"), "command_tag": "ALTER TABLE",
         "object_identity": f"public.{ALT}", "txn_group": None},
        {"op_index": 2, "table": ALT, "action": "DROP", "natural_key": None,
         "principal": env("ROLE_APP"), "command_tag": "DROP TABLE",
         "object_identity": f"public.{ALT}", "txn_group": None},
    ]


def _groups(ops: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for op in ops:
        gid = op.get("txn_group")
        if gid is None or not groups or groups[-1][0].get("txn_group") != gid:
            groups.append([op])
        else:
            groups[-1].append(op)
    return groups


def sql_body(op: dict) -> str:
    from lab_capture_workload import sql_body as base
    if op["action"] == "CREATE":
        return f"CREATE TABLE public.{ALT} (id int PRIMARY KEY);"
    return base(op)


def sql_for_group(ops: list[dict]) -> str:
    role = ops[0]["principal"]
    echoes = "".join(f"\\echo OP {op['op_index']}\n" for op in ops)
    bodies = "\n".join(sql_body(op) for op in ops)
    return (
        f"{echoes}"
        f"BEGIN;\nSET ROLE {role};\n{bodies}\n"
        f"SELECT txid_current();\nRESET ROLE;\nCOMMIT;\n"
    )


def apply_group(ops: list[dict]) -> list[dict]:
    from lab_capture_workload import txn_groups
    sql = "SET client_min_messages = warning;\n" + "".join(
        sql_for_group(g) for g in txn_groups(ops)
    )
    proc = ssh_psql(sql)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: sc01 apply: {proc.stderr.strip()[-2000:]}")
    xids: dict[int, int] = {}
    pending: list[int] = []
    for line in proc.stdout.splitlines():
        if line.startswith("OP "):
            pending.append(int(line.split()[1]))
            continue
        if pending and line.strip().isdigit():
            xid = int(line.strip()) & 0xFFFFFFFF
            for idx in pending:
                xids[idx] = xid
            pending = []
    now = utc_now()
    lsn_proc = ssh_psql("SELECT pg_current_wal_lsn();")
    lsn = lsn_proc.stdout.strip().splitlines()[-1].upper() if lsn_proc.returncode == 0 else None
    out = []
    for op in ops:
        rec = {k: v for k, v in op.items() if k not in {"txn_group", "v_marker"}}
        rec["xid"] = xids.get(op["op_index"])
        rec["wall_clock"] = now
        rec["commit_lsn"] = lsn
        rec["operation"] = {"I": "insert", "U": "update", "D": "delete"}.get(op["action"], op["action"].lower())
        rec["row_ids"] = [op["natural_key"]] if op.get("natural_key") is not None else []
        rec["row_count"] = len(rec["row_ids"])
        rec["relation"] = op.get("table")
        if rec["xid"] is None:
            die(EXIT_ASSERT, f"assertion failed: no xid captured for op {op['op_index']}")
        out.append(rec)
    return out


class ConcurrentApp:
    """lab_app DML looping until stop(), logging P2-format ops with xid."""

    def __init__(self, seed: int, relation: str, tps: float):
        self.seed = seed
        self.relation = relation
        self.interval = 1.0 / max(tps, 0.1)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.rows: list[dict] = []
        self.thread: threading.Thread | None = None
        self.error: str | None = None
        self._seq = 0

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="sc01-app", daemon=True)
        self.thread.start()

    def stop(self) -> list[dict]:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=30)
        if self.error:
            die(EXIT_ASSERT, self.error)
        return list(self.rows)

    def _run(self) -> None:
        try:
            cycle = plan_sc01_app_cycle(self.seed, self.relation)
            # Apply the insert/setup cycle once, then loop the mutating tail.
            setup, tail = cycle[:4], cycle[4:]
            keys = [op["natural_key"] for op in setup if op.get("natural_key") is not None]
            if keys:
                ids = ",".join(str(int(k)) for k in keys)
                ssh_psql(f"DELETE FROM public.{self.relation} WHERE id IN ({ids});")
            self._apply_renumbered(setup)
            while not self.stop_event.is_set():
                self._apply_renumbered(tail)
                time.sleep(self.interval)
        except BaseException as exc:  # surface die() SystemExit too
            self.error = f"assertion failed: concurrent app: {exc}"

    def _apply_renumbered(self, ops: list[dict]) -> None:
        batch = []
        with self.lock:
            for op in ops:
                rec = dict(op)
                rec["op_index"] = self._seq
                self._seq += 1
                batch.append(rec)
        applied = apply_group(batch)
        with self.lock:
            self.rows.extend(applied)
