"""lab-inject: SC-01 bulk DELETE as lab_agent."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3

CITATION = (
    "Ruan et al., 2024; Naihin et al., 2023 — destructive database write / "
    "agent tool-call irreversibility"
)
SQL_TEMPLATE = (
    "DELETE FROM public.orders WHERE id IN "
    "(SELECT id FROM public.orders ORDER BY id LIMIT {n}) "
    "RETURNING json_build_object('id', id, 'bytes', octet_length(payload) + octet_length(status) + 16)::text"
)


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def env(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        die(EXIT_PRECOND, f"precondition failed: {key} missing from lab.env")
    return v


def ssh(args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", env("VM_SSH"), args],
        text=True,
        capture_output=True,
        check=False,
    )
    if check and p.returncode != 0:
        die(EXIT_PRECOND, f"precondition failed: ssh: {p.stderr.strip() or p.stdout.strip()}")
    return p


def incident_paths() -> tuple[str, Path, Path]:
    cur = Path(env("ARCHIVE_CURRENT"))
    if not cur.is_symlink():
        die(EXIT_PRECOND, "precondition failed: ARCHIVE_CURRENT is not a symlink")
    incident = Path(os.readlink(cur)).name
    scenario = incident.split("_", 1)[0]
    ev = Path(env("EVIDENCE_ROOT")) / scenario / incident
    return incident, ev / "injection.json", ev / "workload-manifest.jsonl"


def workload_running() -> bool:
    p = subprocess.run(
        [str(Path(os.environ["LAB_ROOT"]) / "bin" / "lab-workload"), "status"],
        text=True,
        capture_output=True,
        check=False,
        env=os.environ,
    )
    if p.returncode != 0:
        return False
    try:
        return json.loads(p.stdout).get("running") is True
    except json.JSONDecodeError:
        return False


def parse_ts(ts: str) -> float:
    return datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()


def inject(n: int) -> dict:
    if not workload_running():
        die(
            EXIT_ASSERT,
            "assertion failed: refusing to inject into a quiet system; start lab-workload first",
        )
    user = env("OS_USER_AGENT")
    sql = SQL_TEMPLATE.format(n=n)
    before = int(
        ssh(
            f"sudo -n -u postgres psql -At -p {shlex.quote(env('PG_PORT'))} "
            f"-d {shlex.quote(env('DB_NAME'))} -c 'SELECT count(*) FROM public.orders'"
        ).stdout.strip()
    )
    wrapped = (
        "SELECT current_user; "
        f"BEGIN; {sql}; COMMIT; "
        "SELECT pg_current_wal_lsn(); "
        "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"');"
    )
    out = ssh(
        f"sudo -n -u {shlex.quote(user)} psql -X -Atq -v ON_ERROR_STOP=1 "
        f"-p {shlex.quote(env('PG_PORT'))} -d {shlex.quote(env('DB_NAME'))} "
        f"-c {shlex.quote(wrapped)}"
    ).stdout.strip().splitlines()
    if len(out) < 3:
        die(EXIT_ASSERT, f"assertion failed: unexpected inject output: {out!r}")
    who = out[0]
    if who != env("ROLE_AGENT"):
        die(EXIT_ASSERT, f"assertion failed: injector connected as {who!r}")
    lsn = out[-2].upper()
    ts_raw = out[-1]
    ids: list[int] = []
    row_bytes: list[int] = []
    for item in out[1:-2]:
        if not item.startswith("{"):
            continue
        rec = json.loads(item)
        ids.append(int(rec["id"]))
        row_bytes.append(int(rec["bytes"]))
    after = int(
        ssh(
            f"sudo -n -u postgres psql -At -p {shlex.quote(env('PG_PORT'))} "
            f"-d {shlex.quote(env('DB_NAME'))} -c 'SELECT count(*) FROM public.orders'"
        ).stdout.strip()
    )
    if len(ids) != n:
        die(EXIT_ASSERT, f"assertion failed: RETURNING produced {len(ids)} ids, expected {n}")
    id_list = ",".join(str(i) for i in ids)
    remaining = int(
        ssh(
            f"sudo -n -u postgres psql -At -p {shlex.quote(env('PG_PORT'))} "
            f"-d {shlex.quote(env('DB_NAME'))} -c "
            f"'SELECT count(*) FROM public.orders WHERE id IN ({id_list})'"
        ).stdout.strip()
    )
    if remaining != 0:
        die(EXIT_ASSERT, f"assertion failed: {remaining} destroyed ids still present")
    rec = {
        "scenario_id": "SC-01",
        "damage_class": "database data",
        "timing_pattern": "near-instant",
        "archetype_citation": CITATION,
        "principal": env("ROLE_AGENT"),
        "sql": sql,
        "commit_lsn": lsn,
        "commit_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "server_clock": ts_raw,
        "rows_destroyed": len(ids),
        "row_ids": ids,
        "row_bytes": row_bytes,
        "destroyed_bytes": sum(row_bytes),
        "count_before": before,
        "count_after": after,
    }
    _inc, inj_path, _man = incident_paths()
    inj_path.parent.mkdir(parents=True, exist_ok=True)
    inj_path.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    os.chmod(inj_path, 0o644)
    print(json.dumps({
        "ok": True,
        "changed": True,
        "injection": str(inj_path),
        "commit_lsn": rec["commit_lsn"],
        "rows_destroyed": rec["rows_destroyed"],
        "principal": rec["principal"],
        "sql": rec["sql"],
    }, sort_keys=True))
    return rec


def verify_timing() -> None:
    from lab_workload import pull_manifest

    pull_manifest()
    _inc, inj_path, man_path = incident_paths()
    if not inj_path.is_file():
        die(EXIT_PRECOND, f"precondition failed: {inj_path} absent")
    if not man_path.is_file():
        die(EXIT_PRECOND, f"precondition failed: {man_path} absent")
    inj = json.loads(inj_path.read_text())
    inj_ts = inj.get("server_clock") or inj["commit_ts"]
    t0 = parse_ts(inj_ts)
    before = after = None
    before_dt = after_dt = None
    for line in man_path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        dt = parse_ts(rec["commit_ts"]) - t0
        if -2 <= dt < 0 and (before is None or dt > before_dt):
            before, before_dt = rec, dt
        if 0 < dt <= 2 and (after is None or dt < after_dt):
            after, after_dt = rec, dt
    if before is None or after is None:
        die(
            EXIT_ASSERT,
            "assertion failed: timing window unsatisfied "
            f"(before={before is not None} after={after is not None})",
        )
    print(json.dumps({
        "ok": True,
        "changed": False,
        "before": before,
        "after": after,
        "before_delta_ms": int(round(before_dt * 1000)),
        "after_delta_ms": int(round(after_dt * 1000)),
    }, sort_keys=True))


def main(argv: list[str]) -> int:
    scenario = "SC-01"
    n = int(os.environ.get("SC01_INJECT_ROWS", "200"))
    rows_set = False
    verify = False
    i = 0
    while i < len(argv):
        if argv[i] == "--scenario" and i + 1 < len(argv):
            scenario = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--rows" and i + 1 < len(argv):
            n = int(argv[i + 1])
            rows_set = True
            i += 2
            continue
        if argv[i] == "--verify-timing":
            verify = True
            i += 1
            continue
        die(EXIT_USAGE, "usage: lab-inject --scenario SC-01 [--rows n] [--verify-timing]")
    if scenario != "SC-01":
        die(EXIT_USAGE, "only SC-01 is implemented in P1")
    if verify and not rows_set:
        # `--verify-timing` alone, or with `--scenario`, asserts the window.
        # Combined with `--rows` means inject-then-verify.
        if "--scenario" in argv and not Path(incident_paths()[1]).is_file():
            inject(n)
            time.sleep(2.2)
        verify_timing()
        return 0
    if verify:
        inject(n)
        time.sleep(2.2)
        verify_timing()
        return 0
    inject(n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
