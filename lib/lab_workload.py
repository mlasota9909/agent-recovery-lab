"""lab-workload: legitimate SC-01 activity as lab_app, with a commit manifest."""
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3

WORKER_NAME = "lab-workload-worker.py"
PID_NAME = "lab-workload.pid"
TAIL_PID_NAME = "workload-tail.pid"


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def env(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        die(EXIT_PRECOND, f"precondition failed: {key} missing from lab.env")
    return v


def ssh(args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", env("VM_SSH"), args]
    p = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if check and p.returncode != 0:
        die(EXIT_PRECOND, f"precondition failed: ssh: {p.stderr.strip() or p.stdout.strip()}")
    return p


def psql_as_postgres(sql: str) -> str:
    p = ssh(
        f"sudo -n -u postgres psql -X -v ON_ERROR_STOP=1 -At -p {shlex.quote(env('PG_PORT'))} "
        f"-d {shlex.quote(env('DB_NAME'))} -c {shlex.quote(sql)}"
    )
    return p.stdout.strip()


def current_incident() -> tuple[str, str]:
    cur = Path(env("ARCHIVE_CURRENT"))
    if not cur.is_symlink():
        die(EXIT_PRECOND, "precondition failed: ARCHIVE_CURRENT is not a symlink")
    incident = Path(os.readlink(cur)).name
    scenario = incident.split("_", 1)[0]
    return scenario, incident


def evidence_dir() -> Path:
    scenario, incident = current_incident()
    path = Path(env("EVIDENCE_ROOT")) / scenario / incident
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=None)
def guest_home(user: str) -> str:
    result = ssh(f"getent passwd {shlex.quote(user)}")
    fields = result.stdout.strip().split(":")
    if len(fields) != 7 or not fields[5].startswith("/"):
        die(EXIT_PRECOND, f"precondition failed: no home directory for {user}")
    return fields[5]


def manifest_paths() -> tuple[Path, str]:
    host = evidence_dir() / "workload-manifest.jsonl"
    guest = f"{guest_home(env('OS_USER_APP'))}/workload-manifest.jsonl"
    return host, guest


def guest_worker_path() -> str:
    return f"{guest_home(env('OS_USER_APP'))}/{WORKER_NAME}"


def guest_pid_path() -> str:
    return f"{guest_home(env('OS_USER_APP'))}/{PID_NAME}"


def pid_running() -> int | None:
    pid_path = shlex.quote(guest_pid_path())
    probe = ssh(
        f"if sudo -n test -f {pid_path}; then sudo -n cat {pid_path}; fi",
        check=True,
    )
    raw = probe.stdout.strip()
    if not raw.isdigit():
        return None
    pid = int(raw)
    chk = ssh(f"sudo -n kill -0 {pid} && echo yes || echo no")
    return pid if chk.stdout.strip() == "yes" else None


def host_tail_pid_path() -> Path:
    return evidence_dir() / TAIL_PID_NAME


def stop_tailer() -> None:
    path = host_tail_pid_path()
    if not path.is_file():
        return
    raw = path.read_text(encoding="utf-8").strip()
    path.unlink(missing_ok=True)
    if not raw.isdigit():
        return
    pid = int(raw)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def start_tailer(host_manifest: Path, guest_manifest: str) -> None:
    stop_tailer()
    host_manifest.write_bytes(b"")
    log = evidence_dir() / "workload-tail.log"
    out = host_manifest.open("ab")
    err = log.open("ab")
    proc = subprocess.Popen(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            env("VM_SSH"),
            f"sudo -n -u {shlex.quote(env('OS_USER_APP'))} stdbuf -oL tail -n +1 -F {shlex.quote(guest_manifest)}",
        ],
        stdout=out,
        stderr=err,
        start_new_session=True,
    )
    host_tail_pid_path().write_text(str(proc.pid) + "\n", encoding="utf-8")


def install_worker() -> str:
    src = Path(os.environ["LAB_ROOT"]) / "lib" / "lab_workload_worker.py"
    dest = guest_worker_path()
    tmp = "/var/tmp/lab-workload-worker.py"
    subprocess.run(
        ["scp", "-o", "BatchMode=yes", str(src), f"{env('VM_SSH')}:{tmp}"],
        check=True,
        capture_output=True,
        text=True,
    )
    user = env("OS_USER_APP")
    ssh(
        f"sudo -n cp {shlex.quote(tmp)} {shlex.quote(dest)} && "
        f"sudo -n chown {shlex.quote(user)}:{shlex.quote(user)} {shlex.quote(dest)} && "
        f"sudo -n chmod 0644 {shlex.quote(dest)}"
    )
    return dest


def apply_ddl() -> None:
    sql_path = Path(os.environ["LAB_ROOT"]) / "sql" / "sc01-seed.sql"
    tmp = "/var/tmp/sc01-seed.sql"
    subprocess.run(
        ["scp", "-o", "BatchMode=yes", str(sql_path), f"{env('VM_SSH')}:{tmp}"],
        check=True,
        capture_output=True,
        text=True,
    )
    ssh(
        "sudo -n -u postgres psql -X -v ON_ERROR_STOP=1 "
        f"-p {shlex.quote(env('PG_PORT'))} -d {shlex.quote(env('DB_NAME'))} "
        f"-f {shlex.quote(tmp)}"
    )


def seed_content_hash() -> dict:
    row = psql_as_postgres(
        "SELECT count(*)::text || E'\\t' || coalesce(min(id)::text,'') || E'\\t' || "
        "coalesce(max(id)::text,'') || E'\\t' || coalesce("
        " md5(string_agg(md5(id::text || ':' || amount::text || ':' || payload), '' ORDER BY id)),"
        " '') FROM public.orders"
    )
    count_s, id_min, id_max, digest = row.split("\t")
    return {
        "row_count": int(count_s),
        "id_min": int(id_min) if id_min else None,
        "id_max": int(id_max) if id_max else None,
        "content_hash": digest,
    }


def seed() -> dict:
    apply_ddl()
    want = int(env("SC01_SEED_ROWS"))
    have = int(psql_as_postgres("SELECT count(*) FROM public.orders"))
    changed = False
    if have != want:
        psql_as_postgres(
            "TRUNCATE public.order_notes, public.orders, public.workload_commits RESTART IDENTITY"
        )
        psql_as_postgres(
            "INSERT INTO public.orders (amount, payload) "
            "SELECT round((random()*1000)::numeric, 2), 'seed-' || g "
            f"FROM generate_series(1, {want}) g"
        )
        changed = True
        have = int(psql_as_postgres("SELECT count(*) FROM public.orders"))
    if have != want:
        die(EXIT_ASSERT, f"assertion failed: orders count {have} != {want}")
    manifest = seed_content_hash()
    dest = evidence_dir() / "seed-manifest.json"
    dest.write_text(json.dumps({"ok": True, "seed_rows": have, **manifest}, indent=2, sort_keys=True) + "\n")
    return {"ok": True, "changed": changed, "seed_rows": have, **manifest}


def pull_manifest() -> Path:
    host, _guest = manifest_paths()
    sql = (
        "SELECT json_build_object("
        "  'commit_lsn', upper(commit_lsn::text),"
        "  'commit_ts', to_char(commit_ts AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'),"
        "  'operation', operation,"
        "  'relation', relation,"
        "  'row_ids', row_ids,"
        "  'row_count', row_count"
        " )::text FROM public.workload_commits ORDER BY id"
    )
    raw = psql_as_postgres(sql)
    if raw:
        host.write_text(raw + "\n", encoding="utf-8")
    else:
        host.write_text("", encoding="utf-8")
    os.chmod(host, 0o644)
    return host


def start() -> None:
    apply_ddl()
    have = int(psql_as_postgres("SELECT count(*) FROM public.orders"))
    if have == 0:
        seed_info = seed()
    else:
        seed_info = {"ok": True, "changed": False, "seed_rows": have, **seed_content_hash()}
    existing = pid_running()
    if existing:
        print(json.dumps({
            **seed_info,
            "ok": True,
            "changed": False,
            "pid": existing,
            "state": "running",
        }, sort_keys=True))
        return
    install_worker()
    host_manifest, guest_manifest = manifest_paths()
    user = env("OS_USER_APP")
    dest = guest_worker_path()
    psql_as_postgres("TRUNCATE public.workload_commits RESTART IDENTITY")
    ssh(
        f"sudo -n -u {shlex.quote(user)} rm -f {shlex.quote(guest_manifest)} && "
        f"sudo -n -u {shlex.quote(user)} touch {shlex.quote(guest_manifest)}"
    )
    start_tailer(host_manifest, guest_manifest)
    remote = (
        "sudo -n -u {user} env "
        "DB_NAME={db} PG_PORT={port} SC01_TPS={tps} SC01_MIX={mix} "
        "MANIFEST={man} ROLE_APP={role} PGAPPNAME=lab-workload "
        "bash -c 'nohup python3 {dest} >>$HOME/lab-workload.log 2>&1 & echo $! > $HOME/{pid}'"
    ).format(
        user=shlex.quote(user),
        db=shlex.quote(env("DB_NAME")),
        port=shlex.quote(env("PG_PORT")),
        tps=shlex.quote(env("SC01_TPS")),
        mix=shlex.quote(env("SC01_MIX")),
        man=shlex.quote(guest_manifest),
        role=shlex.quote(env("ROLE_APP")),
        dest=shlex.quote(dest),
        pid=PID_NAME,
    )
    ssh(remote)
    time.sleep(0.4)
    pid = pid_running()
    if not pid:
        log = ssh(f"sudo -n -u {shlex.quote(user)} tail -n 40 $HOME/lab-workload.log", check=False)
        die(EXIT_ASSERT, "assertion failed: workload worker did not start: " + log.stdout + log.stderr)
    print(json.dumps({
        **seed_info,
        "ok": True,
        "changed": True,
        "pid": pid,
        "state": "running",
        "manifest": str(host_manifest),
    }, sort_keys=True))


def stop() -> None:
    pid = pid_running()
    user = env("OS_USER_APP")
    if pid:
        ssh(f"sudo -n kill {pid}", check=False)
        deadline = time.time() + 2
        while time.time() < deadline and pid_running():
            time.sleep(0.1)
        if pid_running():
            ssh(f"sudo -n kill -9 {pid}", check=False)
        ssh(f"sudo -n -u {shlex.quote(user)} rm -f {shlex.quote(guest_pid_path())}", check=False)
    stop_tailer()
    host = pull_manifest()
    orphans = ssh(
        f"sudo -n pgrep -u {shlex.quote(user)} -f {shlex.quote(WORKER_NAME)}",
        check=False,
    ).stdout.strip()
    print(json.dumps({
        "ok": True,
        "changed": bool(pid),
        "state": "stopped",
        "manifest": str(host),
        "orphan_pids": [int(x) for x in orphans.split() if x.isdigit()],
    }, sort_keys=True))


def status() -> None:
    pid = pid_running()
    running = pid is not None
    print(json.dumps({
        "ok": True,
        "changed": False,
        "running": running,
        "pid": pid,
        "state": "running" if running else "stopped",
    }, sort_keys=True))


def parse_ts(ts: str) -> float:
    return datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()


def load_manifest_lines() -> list[dict]:
    host, _ = manifest_paths()
    if not host.is_file():
        return []
    rows = []
    for line in host.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def check_rate() -> None:
    pull_manifest()
    rows = load_manifest_lines()
    if len(rows) < 2:
        die(EXIT_ASSERT, "assertion failed: not enough manifest lines to compute tps")
    elapsed = parse_ts(rows[-1]["commit_ts"]) - parse_ts(rows[0]["commit_ts"])
    if elapsed <= 0:
        die(EXIT_ASSERT, "assertion failed: non-positive elapsed time in manifest")
    achieved = (len(rows) - 1) / elapsed
    configured = float(env("SC01_TPS"))
    tolerance = float(env("SC01_TPS_TOLERANCE"))
    mix_tol = float(env("SC01_MIX_TOLERANCE"))
    counts = {"insert": 0, "update": 0, "delete": 0}
    for rec in rows:
        counts[rec["operation"]] = counts.get(rec["operation"], 0) + 1
    total = sum(counts.values())
    parts = dict(p.split(":") for p in env("SC01_MIX").split(","))
    mix_ok = True
    mix_observed = {}
    for op, want_s in parts.items():
        want = int(want_s) / 100.0
        got = counts.get(op, 0) / total
        mix_observed[op] = got
        if abs(got - want) > mix_tol:
            mix_ok = False
    rel = abs(achieved - configured) / configured
    payload = {
        "ok": rel <= tolerance and mix_ok,
        "changed": False,
        "configured_tps": configured,
        "achieved_tps": achieved,
        "elapsed_s": elapsed,
        "commits": len(rows),
        "tolerance": tolerance,
        "relative_error": rel,
        "mix_configured": env("SC01_MIX"),
        "mix_observed": mix_observed,
        "mix_counts": counts,
        "mix_tolerance": mix_tol,
    }
    print(json.dumps(payload, sort_keys=True))
    if rel > tolerance:
        die(EXIT_ASSERT, f"assertion failed: achieved tps {achieved:.3f} off configured {configured} by {rel:.3f}")
    if not mix_ok:
        die(EXIT_ASSERT, f"assertion failed: mix {mix_observed} off configured {env('SC01_MIX')}")


def main(argv: list[str]) -> int:
    if not argv:
        die(EXIT_USAGE, "usage: lab-workload start|stop|status|seed|pull|check-rate")
    action = argv[0]
    if action == "seed":
        print(json.dumps(seed(), sort_keys=True))
        return 0
    if action == "start":
        start()
        return 0
    if action == "stop":
        stop()
        return 0
    if action == "status":
        status()
        return 0
    if action == "pull":
        host = pull_manifest()
        print(json.dumps({"ok": True, "changed": False, "manifest": str(host)}, sort_keys=True))
        return 0
    if action == "check-rate":
        check_rate()
        return 0
    die(EXIT_USAGE, "usage: lab-workload start|stop|status|seed|pull|check-rate")
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
