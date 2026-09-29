"""lab-capture: start/stop/status orchestration of existing collectors. JSON out."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lab_paths import bin_path, current_incident, env, evidence_dir, lab_root
from lab_snapshot_loop import alive_file, pid_file

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3
GROWTH_WINDOW_S = 2.0


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def emit(obj: dict) -> None:
    print(json.dumps(obj, sort_keys=True))


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=str(lab_root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=os.environ,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    text = proc.stdout.strip()
    if not text:
        return {"stderr": proc.stderr.strip(), "exit": proc.returncode}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"stdout": proc.stdout, "stderr": proc.stderr, "exit": proc.returncode}


def session_path(incident: str) -> Path:
    return evidence_dir(incident) / "session.json"


def read_session(incident: str) -> dict | None:
    path = session_path(incident)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_session(incident: str, obj: dict) -> None:
    path = session_path(incident)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def snapshot_loop_pid(incident: str) -> int | None:
    path = pid_file(incident)
    if not path.is_file():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    return pid if pid_alive(pid) else None


def start_snapshot_loop(incident: str) -> tuple[int, bool]:
    existing = snapshot_loop_pid(incident)
    if existing is not None:
        return existing, False
    log = evidence_dir(incident) / "snapshot-loop.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    child_env = os.environ.copy()
    lib = str(lab_root() / "lib")
    child_env["PYTHONPATH"] = lib + (os.pathsep + child_env["PYTHONPATH"] if child_env.get("PYTHONPATH") else "")
    proc = subprocess.Popen(
        [sys.executable, str(lab_root() / "lib" / "lab_snapshot_loop.py"), "--incident", incident],
        cwd=str(lab_root()),
        stdout=log.open("a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=child_env,
    )
    deadline = time.monotonic() + 5
    pid = None
    while time.monotonic() < deadline:
        pid = snapshot_loop_pid(incident)
        if pid is not None:
            break
        time.sleep(0.05)
    if pid is None:
        proc.poll()
        die(EXIT_ASSERT, f"assertion failed: snapshot loop did not write pid file for {incident}")
    return pid, True


def stop_snapshot_loop(incident: str) -> bool:
    pid = snapshot_loop_pid(incident)
    if pid is None:
        try:
            pid_file(incident).unlink()
        except FileNotFoundError:
            pass
        return False
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            break
        time.sleep(0.05)
    if pid_alive(pid):
        os.kill(pid, signal.SIGKILL)
    try:
        pid_file(incident).unlink()
    except FileNotFoundError:
        pass
    return True


def current_wal_lsn() -> str:
    cmd = (
        f"sudo -n -u postgres psql -X -At -p {env('PG_PORT')} -d {env('DB_NAME')} "
        f"-c 'SELECT pg_current_wal_lsn()'"
    )
    proc = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", env("VM_SSH"), cmd])
    lsn = proc.stdout.strip().upper()
    if proc.returncode != 0 or "/" not in lsn:
        die(EXIT_PRECOND, f"precondition failed: cannot read pg_current_wal_lsn: {proc.stderr.strip()}")
    return lsn


def open_coordinate() -> dict:
    lsn = current_wal_lsn()
    proc = run([str(bin_path("lab-coordinate")), "--lsn", lsn])
    coord = load_json(proc)
    if proc.returncode != 0:
        die(EXIT_PRECOND, f"precondition failed: lab-coordinate --lsn {lsn}: {proc.stderr.strip()}")
    return coord


def lab_ready() -> tuple[int, dict]:
    proc = run([str(bin_path("lab-ready"))], timeout=30)
    return proc.returncode, load_json(proc)


def require_current(incident: str) -> None:
    current = current_incident()
    if incident != current:
        die(
            EXIT_PRECOND,
            f"precondition failed: incident {incident} is not archive/current ({current})",
        )


def consumer_appending(incident: str) -> dict:
    stream = evidence_dir(incident) / "db.jsonl"
    before = stream.stat().st_size if stream.is_file() else 0
    pos1 = load_json(run([str(bin_path("lab-consumer")), "position", incident]))
    time.sleep(GROWTH_WINDOW_S)
    after = stream.stat().st_size if stream.is_file() else 0
    pos2 = load_json(run([str(bin_path("lab-consumer")), "position", incident]))
    size_grew = after > before
    flush_moved = pos1.get("confirmed_flush_lsn") != pos2.get("confirmed_flush_lsn")
    return {
        "output": str(stream),
        "bytes_before": before,
        "bytes_after": after,
        "flush_before": pos1.get("confirmed_flush_lsn"),
        "flush_after": pos2.get("confirmed_flush_lsn"),
        "appending": bool(size_grew or flush_moved),
        "growth_signal": "both" if size_grew and flush_moved else "size" if size_grew else "flush_lsn" if flush_moved else "none",
    }


def heartbeat_appending() -> dict:
    s1 = load_json(run([str(bin_path("lab-heartbeat")), "--status"]))
    t1 = (s1.get("newest") or {}).get("at")
    time.sleep(GROWTH_WINDOW_S)
    s2 = load_json(run([str(bin_path("lab-heartbeat")), "--status"]))
    t2 = (s2.get("newest") or {}).get("at")
    return {
        "unit": "lab-heartbeat.service",
        "running": s2.get("running") is True,
        "newest_before": t1,
        "newest_after": t2,
        "appending": bool(t2 and t1 and t2 > t1) or (s2.get("running") is True and not t1 and t2),
        "rows_last_60s": s2.get("rows_last_60s"),
        "output": f"guest:{env('HEARTBEAT_TABLE')} → db.jsonl",
    }


def snapshot_loop_status(incident: str) -> dict:
    pid = snapshot_loop_pid(incident)
    alive = alive_file(incident)
    mtime = alive.stat().st_mtime if alive.is_file() else None
    return {
        "pid": pid,
        "alive": pid is not None,
        "alive_stamp": alive.read_text(encoding="utf-8").strip() if alive.is_file() else None,
        "alive_mtime": mtime,
        "output": str(evidence_dir(incident) / "snapshots.json"),
    }


def collectors_status(incident: str) -> dict:
    consumer = load_json(run([str(bin_path("lab-consumer")), "status", incident]))
    # status exits 1 when unhealthy; still parse JSON
    growth = consumer_appending(incident)
    hb = heartbeat_appending()
    snap = snapshot_loop_status(incident)
    consumer_active = consumer.get("unit_state") == "active" and consumer.get("healthy") is True
    consumer_ok = consumer_active and growth["appending"]
    hb_ok = hb["running"] and hb["appending"]
    snap_ok = snap["alive"] is True
    return {
        "consumer": {
            "unit": consumer.get("unit"),
            "unit_state": consumer.get("unit_state"),
            "healthy_unit": consumer.get("healthy"),
            **growth,
            "active": consumer_ok,
        },
        "heartbeat": {**hb, "active": hb_ok},
        "snapshot_loop": {**snap, "active": snap_ok},
    }


def cmd_start(incident: str) -> int:
    require_current(incident)
    ready_exit, ready = lab_ready()
    if ready_exit != 0 or not ready.get("ready"):
        failed = ready.get("failed") or ["lab-ready"]
        payload = {
            "ok": False,
            "changed": False,
            "action": "start",
            "incident": incident,
            "ready": False,
            "failed": failed,
            "error": "lab-ready refused; naming failed readiness condition(s): " + ",".join(failed),
        }
        emit(payload)
        print(payload["error"], file=sys.stderr)
        return EXIT_PRECOND

    existing = read_session(incident)
    already = (
        existing is not None
        and existing.get("state") == "running"
        and snapshot_loop_pid(incident) is not None
        and load_json(run([str(bin_path("lab-consumer")), "status", incident])).get("unit_state") == "active"
        and load_json(run([str(bin_path("lab-heartbeat")), "--status"])).get("running") is True
    )
    if already:
        existing["changed"] = False
        emit(existing)
        return 0

    evidence_dir(incident).mkdir(parents=True, exist_ok=True)
    consumer = load_json(run([str(bin_path("lab-consumer")), "start", incident]))
    if "ok" in consumer and consumer.get("ok") is not True and "unit" not in consumer:
        die(EXIT_ASSERT, f"assertion failed: lab-consumer start: {consumer}")
    hb = load_json(run([str(bin_path("lab-heartbeat")), "--start"]))
    if hb.get("ok") is not True:
        die(EXIT_ASSERT, f"assertion failed: lab-heartbeat --start: {hb}")
    snap_pid, snap_changed = start_snapshot_loop(incident)

    growth = consumer_appending(incident)
    if not growth["appending"]:
        die(EXIT_ASSERT, "assertion failed: consumer is not appending to db.jsonl after start")
    hb_g = heartbeat_appending()
    if not hb_g["appending"]:
        die(EXIT_ASSERT, "assertion failed: heartbeat writer is not appending within 2 s after start")
    if snapshot_loop_pid(incident) is None:
        die(EXIT_ASSERT, "assertion failed: snapshot loop is not alive after start")

    coord = open_coordinate()
    session = {
        "ok": True,
        "changed": True,
        "action": "start",
        "state": "running",
        "incident": incident,
        "opened_at": utc_now(),
        "open_coordinate": coord,
        "close_coordinate": None,
        "teardown_ok": None,
        "collectors": {
            "consumer": {
                "name": "consumer",
                "unit": consumer.get("unit") or f"lab-consumer@{incident}.service",
                "output": str(evidence_dir(incident) / "db.jsonl"),
                "pid": None,
            },
            "heartbeat": {
                "name": "heartbeat",
                "unit": "lab-heartbeat.service",
                "output": hb_g["output"],
                "pid": None,
            },
            "snapshot_loop": {
                "name": "snapshot_loop",
                "unit": None,
                "pid": snap_pid,
                "output": str(evidence_dir(incident) / "snapshots.json"),
            },
        },
        "append_check": {"consumer": growth, "heartbeat": hb_g},
        "snapshot_loop_changed": snap_changed,
        "heartbeat_changed": hb.get("changed"),
    }
    write_session(incident, session)
    emit(session)
    return 0


def ledger_files(incident: str) -> list[Path]:
    ed = evidence_dir(incident)
    return [ed / n for n in ("db.jsonl", "snapshots.json", "fs_diff.tsv", "fs_hashes.tsv", "workload.jsonl")]


def sha256_file(path: Path) -> str | None:
    import hashlib
    if not path.is_file():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def cmd_stop(incident: str) -> int:
    require_current(incident)
    existing = read_session(incident)
    consumer_state = load_json(run([str(bin_path("lab-consumer")), "status", incident])).get("unit_state")
    if isinstance(consumer_state, str):
        consumer_state = consumer_state.splitlines()[0]
    hb_running = load_json(run([str(bin_path("lab-heartbeat")), "--status"])).get("running") is True
    snap_alive = snapshot_loop_pid(incident) is not None
    slot = load_json(run([str(bin_path("lab-slot")), "--status"]))
    slot_present = bool(slot.get("slot_name")) and slot.get("slot_name") == env("SLOT_NAME") and (
        slot.get("active") is True or slot.get("restart_lsn") or slot.get("confirmed_flush_lsn")
    )
    # Absent slot + collectors down → idempotent.
    if (
        (existing is None or existing.get("state") == "stopped")
        and existing is not None and existing.get("teardown_ok") is True
        and not snap_alive
        and consumer_state != "active"
        and not hb_running
    ):
        existing["changed"] = False
        write_session(incident, existing)
        emit(existing)
        return 0

    stop_snapshot_loop(incident)
    run([str(bin_path("lab-heartbeat")), "--stop"])
    # Drain while consumer still up (C009). Never skip this in the production path.
    barrier = run([str(bin_path("lab-barrier"))], timeout=int(float(os.environ.get("BARRIER_TIMEOUT_S", "120"))) + 30)
    before = {str(p): sha256_file(p) for p in ledger_files(incident)}
    run([str(bin_path("lab-consumer")), "stop", incident])
    dropped = load_json(run([str(bin_path("lab-slot")), "--drop"]))
    after = {str(p): sha256_file(p) for p in ledger_files(incident)}
    intact = before == after
    coord = None
    try:
        lsn = current_wal_lsn()
        coord = {"lsn": lsn, "note": "post-teardown; slot dropped"}
    except SystemExit:
        coord = {"lsn": None, "note": "coordinate unavailable after slot drop"}
    session = existing or {"incident": incident, "collectors": {}}
    session.update({
        "ok": True,
        "changed": True,
        "action": "stop",
        "state": "stopped",
        "incident": incident,
        "closed_at": utc_now(),
        "close_coordinate": coord,
        "teardown_ok": bool(dropped.get("ok") is True and intact),
        "barrier_exit": barrier.returncode,
        "slot_drop": dropped,
        "ledger_intact": intact,
        "ledger_sha256_before": before,
        "ledger_sha256_after": after,
    })
    write_session(incident, session)
    emit(session)
    if not intact:
        return EXIT_ASSERT
    return 0


def cmd_status(incident: str) -> int:
    require_current(incident)
    cols = collectors_status(incident)
    all_active = all(cols[k]["active"] for k in ("consumer", "heartbeat", "snapshot_loop"))
    payload = {
        "ok": True,
        "changed": False,
        "action": "status",
        "incident": incident,
        "state": "running" if all_active else "degraded",
        "collectors": cols,
        "all_active": all_active,
        "session": read_session(incident),
        "liveness": "unit_state_and_file_growth",
    }
    emit(payload)
    return 0 if all_active else EXIT_ASSERT


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in {"start", "stop", "status"}:
        die(EXIT_USAGE, "usage: lab-capture start|stop|status <incident>")
    action, incident = argv
    if action == "start":
        return cmd_start(incident)
    if action == "stop":
        return cmd_stop(incident)
    return cmd_status(incident)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
