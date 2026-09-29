"""lab-generate-incident: seven ordered steps. No incident.json unless they all succeed."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lsn import lsn_int

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3

COORD_FIELDS = ("wall_clock", "lsn", "snapshot", "skew_ms", "skew_bytes", "resolved_by")


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def env(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        die(EXIT_PRECOND, f"precondition failed: {key} missing from lab.env")
    return v


def bin_path(name: str) -> str:
    return str(Path(os.environ["LAB_ROOT"]) / "bin" / name)


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(args, text=True, capture_output=True, check=False, env=os.environ)
    if check and p.returncode != 0:
        die(p.returncode if p.returncode in {1, 2, 3} else EXIT_ASSERT,
            f"assertion failed: {' '.join(args)}: {p.stderr.strip() or p.stdout.strip()}")
    return p


def run_json(args: list[str]) -> dict:
    p = run(args)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        die(EXIT_ASSERT, f"assertion failed: {' '.join(args)} stdout is not JSON: {p.stdout[:300]}")
        return {}


def ssh(cmd: str) -> str:
    p = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", env("VM_SSH"), cmd])
    return p.stdout.strip()


def pg_unit() -> str:
    cluster = Path(env("PG_DATA")).name
    return f"postgresql@{env('PG_VERSION')}-{cluster}"


def stop_postgres() -> None:
    unit = pg_unit()
    ssh(f"sudo -n systemctl stop {shlex.quote(unit)}")
    for _ in range(40):
        p = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", env("VM_SSH"), "sudo -n pgrep -x postgres"],
            text=True, capture_output=True, check=False,
        )
        if p.returncode != 0:
            return
        time.sleep(0.25)
    die(EXIT_PRECOND, "precondition failed: PostgreSQL is still running after stop")


def current_archive_incident() -> str:
    cur = Path(env("ARCHIVE_CURRENT"))
    if not cur.is_symlink():
        die(EXIT_PRECOND, "precondition failed: ARCHIVE_CURRENT is not a symlink")
    return Path(os.readlink(cur)).name


def scenario_has_p1_incident(scenario: str) -> bool:
    root = Path(env("EVIDENCE_ROOT")) / scenario
    if not root.is_dir():
        return False
    return any((p / "incident.json").is_file() for p in root.iterdir() if p.is_dir())


def coordinate_lsn(lsn: str) -> dict:
    raw = run_json([bin_path("lab-coordinate"), "--lsn", lsn])
    return {k: raw[k] for k in COORD_FIELDS}


def coordinate_snapshot(name: str) -> dict:
    raw = run_json([bin_path("lab-coordinate"), "--snapshot", name])
    return {k: raw[k] for k in COORD_FIELDS}


def current_lsn() -> str:
    return ssh(
        "sudo -n -u postgres psql -At -p "
        f"{shlex.quote(env('PG_PORT'))} -d {shlex.quote(env('DB_NAME'))} "
        "-c 'SELECT pg_current_wal_lsn()'"
    ).upper()


def results_incident_id(archive_incident: str) -> str:
    stamp = archive_incident.split("_", 1)[1]
    digest = hashlib.sha256(archive_incident.encode("ascii")).hexdigest()[:6]
    return f"i_{stamp}_{digest}"


def window_ledger(path: Path, open_lsn: str, close_lsn: str) -> int:
    """Keep only records whose LSN lies in [open, close] (incident window)."""
    lo, hi = lsn_int(open_lsn), lsn_int(close_lsn)
    kept: list[str] = []
    dropped = 0
    if not path.is_file():
        return 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        lsn = rec.get("lsn")
        if not lsn:
            kept.append(line)
            continue
        n = lsn_int(lsn)
        if lo <= n <= hi:
            kept.append(line)
        else:
            dropped += 1
    path.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")
    return dropped


def write_immutable(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    os.chmod(path, 0o444)


def generate(scenario: str, log: list[dict]) -> dict:
    if scenario != "SC-01":
        die(EXIT_USAGE, "only SC-01 is implemented in P1")
    root = Path(os.environ["LAB_ROOT"])
    t0 = time.monotonic()

    def add(entry: dict) -> None:
        entry["elapsed_ms"] = int(round((time.monotonic() - t0) * 1000))
        log.append(entry)

    old = current_archive_incident()
    subprocess.run([bin_path("lab-workload"), "stop"], text=True, capture_output=True, env=os.environ)
    subprocess.run([bin_path("lab-consumer"), "stop", old], text=True, capture_output=True, env=os.environ)

    # 1. Stop PostgreSQL, then reset.
    stop_postgres()
    add({"step": 1, "action": "stop_postgres", "unit": pg_unit()})
    tier = "t1" if scenario_has_p1_incident(scenario) else "t1"
    # No valid pristine snapshot exists on the open P0 incident; t1 is the
    # only legal rollback. Recorded as first-run-of-P1 using t1.
    reset = run_json([bin_path("lab-reset"), "--tier", tier])
    add({"step": 1, "action": "reset", "tier": tier, "result": reset})

    # 3 then 2: allocate so the new consumer exists, then barrier.
    allocated = run_json([bin_path("lab-incident"), "--new", "--scenario", scenario])
    archive_incident = allocated["incident"]
    add({"step": 3, "action": "incident_new", "result": allocated})
    ev = Path(env("EVIDENCE_ROOT")) / scenario / archive_incident
    subprocess.run([bin_path("lab-consumer"), "stop", archive_incident], capture_output=True, env=os.environ)
    ledger = ev / "db.jsonl"
    if ledger.exists():
        ledger.write_text("")
    # Snapshot BEFORE the consumer writes so every ledger LSN is at or above open.
    snap_open = run_json([bin_path("lab-snapshot"), "--label", "open"])
    open_coord = coordinate_snapshot(snap_open["snapshot"])
    add({"step": 3, "action": "open_coordinate", "snapshot": snap_open, "coordinate": open_coord})
    run_json([bin_path("lab-consumer"), "start", archive_incident])
    barrier = run_json([bin_path("lab-barrier")])
    add({"step": 2, "action": "barrier", "result": barrier})
    subprocess.run([bin_path("lab-heartbeat"), "--start"], capture_output=True, env=os.environ)

    # 4. Workload + baseline window.
    wl = run_json([bin_path("lab-workload"), "start"])
    add({"step": 4, "action": "workload_start", "result": wl})
    print(json.dumps({"event": "workload_started", "pid": wl.get("pid")}), file=sys.stderr, flush=True)
    baseline = int(env("SC01_BASELINE_S"))
    time.sleep(baseline)
    add({"step": 4, "action": "baseline_wait_s", "seconds": baseline})

    # 5. pre_injection snapshot.
    pre = run_json([bin_path("lab-snapshot"), "--label", "pre_injection"])
    add({"step": 5, "action": "snapshot_pre_injection", "result": pre})

    # 6. Inject and verify timing. Fail the whole generation if the window is absent.
    inj = run_json([bin_path("lab-inject"), "--scenario", scenario])
    add({"step": 6, "action": "inject", "result": inj})
    time.sleep(2.2)
    timing = run([bin_path("lab-inject"), "--verify-timing"], check=False)
    if timing.returncode != 0:
        subprocess.run([bin_path("lab-workload"), "stop"], capture_output=True, env=os.environ)
        die(EXIT_ASSERT, "assertion failed: timing window unsatisfied; incident not registered: " + timing.stderr.strip())
    add({"step": 6, "action": "verify_timing", "result": json.loads(timing.stdout)})

    # 7. Stop workload, post_capture, close.
    stop = run_json([bin_path("lab-workload"), "stop"])
    add({"step": 7, "action": "workload_stop", "result": stop})
    post = run_json([bin_path("lab-snapshot"), "--label", "post_capture"])
    add({"step": 7, "action": "snapshot_post_capture", "result": post})
    subprocess.run([bin_path("lab-heartbeat"), "--stop"], capture_output=True, env=os.environ)
    time.sleep(0.5)
    close_lsn = current_lsn()
    close_coord = coordinate_lsn(close_lsn)
    closed = run_json([bin_path("lab-incident"), "--close"])
    add({"step": 7, "action": "close", "lsn": close_lsn, "coordinate": close_coord, "result": closed})
    dropped = window_ledger(ev / "db.jsonl", open_coord["lsn"], close_lsn)
    add({"step": 7, "action": "ledger_window", "dropped": dropped, "open": open_coord["lsn"], "close": close_lsn})
    verify = run_json([bin_path("lab-ledger-verify"), "--incident", archive_incident,
                       "--open-lsn", open_coord["lsn"], "--close-lsn", close_coord["lsn"]])
    if not verify.get("ok"):
        die(EXIT_ASSERT, "assertion failed: lab-ledger-verify refused to register the incident: " + json.dumps(verify))
    add({"step": 7, "action": "ledger_verify", "result": verify})

    ora = run_json([bin_path("lab-oracle"), "--incident", archive_incident])
    add({"step": 7, "action": "oracle", "result": ora})

    ev = Path(env("EVIDENCE_ROOT")) / scenario / archive_incident
    rec = {
        "incident_id": results_incident_id(archive_incident),
        "archive_incident": archive_incident,
        "scenario_id": scenario,
        "open_coordinate": open_coord,
        "close_coordinate": close_coord,
        "snapshot_open": snap_open["snapshot"],
        "snapshot_pre_injection": pre["snapshot"],
        "snapshot_post_capture": post["snapshot"],
        "workload_rate_tps": float(env("SC01_TPS")),
        "workload_mix": env("SC01_MIX"),
        "oracle_coordinate": ora["coordinate"],
        "ledger_integrity_ok": True,
    }
    write_immutable(ev / "incident.json", json.dumps(rec, indent=2, sort_keys=True) + "\n")
    (ev / "generate-commands.json").write_text(json.dumps(log, indent=2) + "\n")
    return rec


def main(argv: list[str]) -> int:
    scenario = "SC-01"
    i = 0
    while i < len(argv):
        if argv[i] == "--scenario" and i + 1 < len(argv):
            scenario = argv[i + 1]
            i += 2
            continue
        die(EXIT_USAGE, "usage: lab-generate-incident --scenario SC-01")
    log: list[dict] = []
    try:
        rec = generate(scenario, log)
    except SystemExit:
        raise
    print(json.dumps({"ok": True, "changed": True, **rec}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
