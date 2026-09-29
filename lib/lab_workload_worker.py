"""Guest-side SC-01 legitimate workload. Runs as lab_app. Do not invoke from the host."""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time

SENTINEL = "LAB_WL_DONE"


class Psql:
    def __init__(self) -> None:
        env = os.environ.copy()
        env["PGAPPNAME"] = "lab-workload"
        self.proc = subprocess.Popen(
            [
                "stdbuf",
                "-o0",
                "-e0",
                "psql",
                "-X",
                "-At",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-p",
                os.environ["PG_PORT"],
                "-d",
                os.environ["DB_NAME"],
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
            env=env,
        )
        if self.proc.stdin is None or self.proc.stdout is None:
            raise SystemExit("psql pipes missing")

    def run(self, sql: str) -> list[str]:
        if self.proc.poll() is not None:
            err = self.proc.stderr.read() if self.proc.stderr else ""
            raise SystemExit(f"psql exited: {err}")
        payload = sql.rstrip().rstrip(";") + f";\nSELECT '{SENTINEL}';\n"
        self.proc.stdin.write(payload)
        self.proc.stdin.flush()
        lines: list[str] = []
        while True:
            line = self.proc.stdout.readline()
            if line == "":
                err = self.proc.stderr.read() if self.proc.stderr else ""
                raise SystemExit(f"psql closed: {err}")
            text = line.rstrip("\n")
            if text == SENTINEL:
                break
            if text != "":
                lines.append(text)
        return lines


def dml_cte(rng: random.Random, op: str) -> str:
    pick = (
        "SELECT id FROM public.orders WHERE id >= ("
        "  SELECT COALESCE(min(id), 0) + floor(random() * GREATEST(max(id) - min(id) + 1, 1))::bigint"
        "  FROM public.orders"
        ") ORDER BY id LIMIT 1"
    )
    if op == "insert":
        amount = f"{rng.randint(1, 999)}.99"
        payload = f"w-{rng.randint(0, 10**9)}"
        return (
            "ins AS ("
            f" INSERT INTO public.orders (amount, payload) VALUES ({amount}, '{payload}') RETURNING id"
            "), dml AS ("
            " INSERT INTO public.order_notes (order_id, body) SELECT id, 'note' FROM ins RETURNING order_id AS id"
            ")"
        )
    if op == "update":
        return (
            "dml AS ("
            " UPDATE public.orders SET payload = payload || '-u', amount = amount + 0.01 "
            f" WHERE id = ({pick}) RETURNING id)"
        )
    return (
        "dml AS ("
        f" DELETE FROM public.orders WHERE id = ({pick}) RETURNING id)"
    )


def one(db: Psql, rng: random.Random, ops: list[str], weights: list[int], manifest: str) -> None:
    op = rng.choices(ops, weights=weights, k=1)[0]
    cte = dml_cte(rng, op)
    sql = f"""
BEGIN;
WITH {cte},
logged AS (
  INSERT INTO public.workload_commits
    (commit_lsn, commit_ts, operation, relation, row_ids, row_count)
  SELECT pg_current_wal_lsn(),
         clock_timestamp(),
         '{op}',
         'orders',
         COALESCE(array_agg(id) FILTER (WHERE id IS NOT NULL), ARRAY[]::bigint[]),
         COUNT(id)::integer
  FROM dml
  RETURNING commit_lsn, commit_ts, operation, relation, row_ids, row_count
)
SELECT json_build_object(
  'commit_lsn', upper(logged.commit_lsn::text),
  'commit_ts', to_char(logged.commit_ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
  'operation', logged.operation,
  'relation', logged.relation,
  'row_ids', logged.row_ids,
  'row_count', logged.row_count
)::text
FROM logged;
COMMIT;
"""
    lines = db.run(sql)
    if not lines:
        return
    rec = json.loads(lines[-1])
    rec["commit_lsn"] = str(rec["commit_lsn"]).upper()
    with open(manifest, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def main() -> int:
    tps = float(os.environ["SC01_TPS"])
    mix = os.environ["SC01_MIX"]
    manifest = os.environ["MANIFEST"]
    role = os.environ.get("ROLE_APP", "lab_app")
    parts = dict(p.split(":") for p in mix.split(","))
    ops = ["insert", "update", "delete"]
    weights = [int(parts[name]) for name in ops]
    interval = 1.0 / tps
    rng = random.Random(1)
    db = Psql()
    who = db.run("SELECT current_user")
    if not who or who[0] != role:
        sys.stderr.write(f"identity {who!r} is not {role}\n")
        return 1
    with open(os.path.expanduser("~/identity-proof.txt"), "w", encoding="utf-8") as fh:
        fh.write(who[0] + "\n")
    next_t = time.monotonic()
    while True:
        one(db, rng, ops, weights, manifest)
        next_t += interval
        delay = next_t - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            next_t = time.monotonic()


if __name__ == "__main__":
    raise SystemExit(main())
