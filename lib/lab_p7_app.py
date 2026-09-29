"""lab_app DML loop against a declared table. Used as SC-03/SC-04 confounder."""
from __future__ import annotations

import threading
import time

from lab_p3_util import EXIT_ASSERT, die, ssh_psql, utc_now
from lab_paths import env
from lsn import lsn_norm


class DmlLoop:
    """sql may contain {id}; ids cycle 1..id_mod so workload.jsonl maps C-1."""

    def __init__(self, sql: str, tps: float, relation: str, id_mod: int):
        self.sql = sql
        self.interval = 1.0 / max(tps, 0.1)
        self.relation = relation
        self.id_mod = max(int(id_mod), 1)
        self.stop_event = threading.Event()
        self.rows: list[dict] = []
        self.thread: threading.Thread | None = None
        self.error: str | None = None
        self.seq = 0

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name=f"dml-{self.relation}", daemon=True)
        self.thread.start()

    def stop(self) -> list[dict]:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=30)
        if self.error and not self.rows:
            die(EXIT_ASSERT, self.error)
        return list(self.rows)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            rid = 1 + (self.seq % self.id_mod)
            body = self.sql.replace("{id}", str(rid))
            sql = (
                "SELECT current_user;\nBEGIN;\nSET ROLE lab_app;\n"
                + body + "\n"
                "SELECT txid_current();\nSELECT pg_current_wal_lsn();\nRESET ROLE;\nCOMMIT;\n"
            )
            proc = ssh_psql(sql)
            if proc.returncode != 0:
                # DDL may invalidate the statement mid-window (SC-03 type change). Keep going.
                time.sleep(self.interval)
                continue
            lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
            if len(lines) < 3:
                time.sleep(self.interval)
                continue
            xid = int(lines[-2]) & 0xFFFFFFFF
            lsn = lsn_norm(lines[-1].upper())
            self.seq += 1
            self.rows.append({
                "op_index": self.seq,
                "table": self.relation,
                "action": "U",
                "operation": "update",
                "natural_key": rid,
                "principal": env("ROLE_APP"),
                "xid": xid,
                "commit_lsn": lsn,
                "wall_clock": utc_now(),
                "row_ids": [rid],
                "row_count": 1,
                "relation": self.relation,
            })
            time.sleep(self.interval)
