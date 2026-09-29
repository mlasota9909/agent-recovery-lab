"""lab-capture-workload: seedable mixed DML+DDL. Principal is a written label only."""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from lab_paths import current_incident, env, evidence_dir

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3
PROBE = "p2_probe"
ALT = "p2_alt"


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def emit(obj: dict) -> None:
    print(json.dumps(obj, sort_keys=True))


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ssh_psql(sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", env("VM_SSH"),
         f"sudo -n -u postgres psql -X -qAt -v ON_ERROR_STOP=1 -p {env('PG_PORT')} -d {env('DB_NAME')}"],
        input=sql, text=True, capture_output=True, check=False,
    )


def ensure_probe() -> None:
    sql = f"""
CREATE TABLE IF NOT EXISTS public.{PROBE} (
  id bigint PRIMARY KEY,
  v text NOT NULL
);
ALTER TABLE public.{PROBE} REPLICA IDENTITY FULL;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.{PROBE} TO lab_app;
GRANT SELECT, DELETE ON public.{PROBE} TO lab_agent;
GRANT CREATE ON SCHEMA public TO lab_app;
TRUNCATE TABLE public.{PROBE};
DROP TABLE IF EXISTS public.{ALT};
"""
    proc = ssh_psql(sql)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: probe schema: {proc.stderr.strip()}")


def plan_ops(seed: int, n: int) -> list[dict]:
    rng = random.Random(seed)
    live: list[int] = []
    ops: list[dict] = []
    # Reserve last 3 ops for CREATE/ALTER/DROP so DDL is present and deterministic.
    dml_n = n - 3
    if dml_n < 1:
        die(EXIT_USAGE, "usage: --ops must be >= 4")
    next_id = 10_000_000 + seed * 1_000_000
    for i in range(dml_n):
        if not live or rng.random() < 0.55:
            action = "I"
            kid = next_id
            next_id += 1
            live.append(kid)
            principal = "lab_app"
        elif rng.random() < 0.7:
            action = "U"
            kid = rng.choice(live)
            principal = "lab_app"
        else:
            action = "D"
            kid = live.pop(rng.randrange(len(live)))
            principal = "lab_agent" if rng.random() < 0.5 else "lab_app"
        ops.append({
            "op_index": i,
            "table": PROBE,
            "action": action,
            "natural_key": kid,
            "principal": principal,
            "command_tag": None,
            "object_identity": None,
        })
    ops.append({
        "op_index": dml_n, "table": ALT, "action": "CREATE",
        "natural_key": None, "principal": "lab_app",
        "command_tag": "CREATE TABLE", "object_identity": f"public.{ALT}",
    })
    ops.append({
        "op_index": dml_n + 1, "table": ALT, "action": "ALTER",
        "natural_key": None, "principal": "lab_app",
        "command_tag": "ALTER TABLE", "object_identity": f"public.{ALT}",
    })
    ops.append({
        "op_index": dml_n + 2, "table": ALT, "action": "DROP",
        "natural_key": None, "principal": "lab_app",
        "command_tag": "DROP TABLE", "object_identity": f"public.{ALT}",
    })
    return ops


def plan_repeated_keys(seed: int) -> list[dict]:
    """Seeded repeated-key profile: cross-txn U, same-txn U, delete-reinsert, interleaved principals."""
    rng = random.Random(seed)
    base = 88_000_000 + (seed % 1000) * 100
    k0, k1, k2, k3 = base, base + 1, base + 2, base + 3
    # Shuffle only the insert order of the four keys so the seed is load-bearing
    # without dropping any required pattern.
    keys = [k0, k1, k2, k3]
    rng.shuffle(keys)
    k0, k1, k2, k3 = keys
    ops: list[dict] = []

    def add(action: str, kid: int | None, principal: str, table: str = PROBE,
            command_tag: str | None = None, object_identity: str | None = None,
            txn_group: str | None = None, v_marker: str | None = None) -> None:
        rec: dict = {
            "op_index": len(ops),
            "table": table,
            "action": action,
            "natural_key": kid,
            "principal": principal,
            "command_tag": command_tag,
            "object_identity": object_identity,
            "txn_group": txn_group,
        }
        if v_marker is not None:
            rec["v_marker"] = v_marker
        ops.append(rec)

    add("I", k0, "lab_app")
    add("I", k1, "lab_app")
    add("I", k2, "lab_app")
    add("I", k3, "lab_app")
    # Same natural key updated in two separate transactions.
    add("U", k0, "lab_app", v_marker=f"u{k0}a")
    add("U", k0, "lab_app", v_marker=f"u{k0}b")
    # Same natural key updated twice in one transaction.
    add("U", k1, "lab_app", txn_group="same-txn-u", v_marker=f"u{k1}a")
    add("U", k1, "lab_app", txn_group="same-txn-u", v_marker=f"u{k1}b")
    # Delete then reinsert of one primary key.
    add("D", k2, "lab_agent")
    add("I", k2, "lab_app")
    # Interleaved lab_app / lab_agent on a shared key.
    add("U", k3, "lab_app", v_marker=f"u{k3}a")
    add("D", k3, "lab_agent")
    add("I", k3, "lab_app")
    # DDL so C-3 is exercised on this profile too.
    add("CREATE", None, "lab_app", table=ALT,
        command_tag="CREATE TABLE", object_identity=f"public.{ALT}")
    add("ALTER", None, "lab_app", table=ALT,
        command_tag="ALTER TABLE", object_identity=f"public.{ALT}")
    add("DROP", None, "lab_app", table=ALT,
        command_tag="DROP TABLE", object_identity=f"public.{ALT}")
    return ops


def sql_body(op: dict) -> str:
    kid = op["natural_key"]
    if op["action"] == "I":
        return f"INSERT INTO public.{PROBE}(id, v) VALUES ({kid}, 's{kid}');"
    if op["action"] == "U":
        marker = op.get("v_marker") or f"u{kid}"
        return f"UPDATE public.{PROBE} SET v = '{marker}' WHERE id = {kid};"
    if op["action"] == "D":
        return f"DELETE FROM public.{PROBE} WHERE id = {kid};"
    if op["action"] == "CREATE":
        return f"DROP TABLE IF EXISTS public.{ALT}; CREATE TABLE public.{ALT} (id int PRIMARY KEY);"
    if op["action"] == "ALTER":
        return f"ALTER TABLE public.{ALT} ADD COLUMN IF NOT EXISTS v text;"
    if op["action"] == "DROP":
        return f"DROP TABLE public.{ALT};"
    die(EXIT_ASSERT, f"unknown action {op['action']}")


def sql_for_group(ops: list[dict]) -> str:
    role = ops[0]["principal"]
    echoes = "".join(f"\\echo OP {op['op_index']}\n" for op in ops)
    bodies = "\n".join(sql_body(op) for op in ops)
    return (
        f"{echoes}"
        f"BEGIN;\nSET ROLE {role};\n{bodies}\n"
        f"SELECT txid_current();\nRESET ROLE;\nCOMMIT;\n"
    )


def txn_groups(ops: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for op in ops:
        gid = op.get("txn_group")
        if gid is None or not groups or groups[-1][0].get("txn_group") != gid:
            groups.append([op])
        else:
            groups[-1].append(op)
    return groups


def apply_ops(ops: list[dict]) -> list[dict]:
    sql = "SET client_min_messages = warning;\n" + "".join(
        sql_for_group(g) for g in txn_groups(ops)
    )
    proc = ssh_psql(sql)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: workload apply: {proc.stderr.strip()[-2000:]}")
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
    out = []
    for op in ops:
        rec = {k: v for k, v in op.items() if k not in {"txn_group", "v_marker"}}
        rec["xid"] = xids.get(op["op_index"])
        rec["wall_clock"] = now
        out.append(rec)
        if rec["xid"] is None:
            die(EXIT_ASSERT, f"assertion failed: no xid captured for op {op['op_index']}")
    return out


def compared_fields(op: dict) -> dict:
    return {k: op[k] for k in ("op_index", "table", "action", "natural_key", "principal",
                               "command_tag", "object_identity")}


def main(argv: list[str]) -> int:
    incident = None
    seed = 1
    n = 500
    apply = True
    profile = "default"
    i = 0
    while i < len(argv):
        if argv[i] == "--seed" and i + 1 < len(argv):
            seed = int(argv[i + 1]); i += 2; continue
        if argv[i] == "--ops" and i + 1 < len(argv):
            n = int(argv[i + 1]); i += 2; continue
        if argv[i] == "--profile" and i + 1 < len(argv):
            profile = argv[i + 1]; i += 2; continue
        if argv[i] == "--no-apply":
            apply = False; i += 1; continue
        if argv[i] == "--apply":
            apply = True; i += 1; continue
        if incident is None and not argv[i].startswith("--"):
            incident = argv[i]; i += 1; continue
        die(EXIT_USAGE, "usage: lab-capture-workload <incident> [--seed N] [--ops N] [--profile default|repeated-keys] [--apply|--no-apply]")
    if incident is None:
        incident = current_incident()
    if profile not in {"default", "repeated-keys"}:
        die(EXIT_USAGE, "usage: --profile must be default or repeated-keys")
    ensure_probe()
    planned = plan_repeated_keys(seed) if profile == "repeated-keys" else plan_ops(seed, n)
    if apply:
        rows = apply_ops(planned)
    else:
        rows = [{**{k: v for k, v in op.items() if k not in {"txn_group", "v_marker"}},
                 "xid": None, "wall_clock": None} for op in planned]
    path = evidence_dir(incident) / "workload.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for rec in rows:
            handle.write(json.dumps(rec, sort_keys=True) + "\n")
    principals = sorted({r["principal"] for r in rows})
    emit({
        "ok": True,
        "changed": True,
        "incident": incident,
        "profile": profile,
        "seed": seed,
        "ops": len(rows),
        "applied": apply,
        "output": str(path),
        "principals": principals,
        "ddl": sum(1 for r in rows if r["action"] in {"CREATE", "ALTER", "DROP"}),
        "compared_fields": ["op_index", "table", "action", "natural_key", "principal",
                            "command_tag", "object_identity"],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
