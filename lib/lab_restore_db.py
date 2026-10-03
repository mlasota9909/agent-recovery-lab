"""E002: PITR into a guest sandbox cluster. Never touches the victim cluster."""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import subprocess
import sys
import time
from pathlib import Path

from lab_p4_util import (
    EXIT_ASSERT,
    EXIT_PRECOND,
    EXIT_USAGE,
    PG_BIN,
    SANDBOX_PORT_DEFAULT,
    append_cmd,
    die,
    ensure_sandbox_parent,
    env,
    lab_root,
    refuse_victim_target,
    resolve_snapshot,
    review_dir,
    sandbox_dataset,
    sandbox_mount,
    ssh_ok,
    ssh_sudo,
    victim_zfs_identity,
    wal_range,
)
from lab_paths import evidence_dir
from lsn import lsn_int


def lsn_text_from_int(value: int) -> str:
    return f"{value >> 32:X}/{value & 0xFFFFFFFF:X}"


def sandbox_port(tag: str | None = None) -> int:
    base = int(os.environ.get("SANDBOX_PORT") or SANDBOX_PORT_DEFAULT)
    if not tag:
        return base
    import zlib
    return base + (zlib.crc32(tag.encode("utf-8")) % 200)


def tag_for(incident: str, lsn_int_v: int, restore_of: str | None) -> str:
    if restore_of:
        return restore_of.replace("/", "_")
    return f"lsn_{lsn_int_v}"


def dataset_exists(name: str) -> bool:
    proc = ssh_sudo(f"zfs list -H -o name '{name}' >/dev/null 2>&1")
    return proc.returncode == 0


def sandbox_pgdata_path(incident: str, tag: str) -> str:
    """Preserve PG_DATA's discovered path relative to its ZFS dataset mount."""
    source_mount = ssh_ok(
        f"zfs get -H -o value mountpoint '{env('DS_PGDATA')}'",
        what="discover pgdata dataset mountpoint",
    ).strip()
    relative = posixpath.relpath(env("PG_DATA"), source_mount)
    if relative == ".":
        return sandbox_mount(incident, tag, "pgdata")
    if relative == ".." or relative.startswith("../") or relative.startswith("/"):
        die(EXIT_ASSERT, "assertion failed: PG_DATA escapes DS_PGDATA mountpoint")
    return posixpath.join(sandbox_mount(incident, tag, "pgdata"), relative)


def stop_sandbox(pgdata: str, port: int, log: Path) -> None:
    refuse_victim_target("pg_ctl stop", pgdata)
    # A fresh clone carries the source cluster's postmaster.pid, and pg_ctl stop
    # signals whatever process that file names. Stop only a postmaster whose
    # working directory is this sandbox.
    cmd = (
        f"if [ -d '{pgdata}' ]; then "
        f"pid=$(head -n 1 '{pgdata}/postmaster.pid' 2>/dev/null || true); "
        "case $pid in ''|*[!0-9]*) pid= ;; esac; "
        f"if [ -n \"$pid\" ] && [ \"$(readlink -f /proc/$pid/cwd 2>/dev/null)\" = \"$(readlink -f '{pgdata}')\" ]; then "
        f"sudo -n -u postgres {PG_BIN}/pg_ctl -D '{pgdata}' -m fast stop >/dev/null 2>&1 || true; "
        "fi; fi"
    )
    append_cmd(log, f"pg_ctl stop sandbox {pgdata} port={port}")
    ssh_sudo(cmd)


def teardown(incident: str, tag: str, log: Path) -> None:
    ds = f"labpool/sandbox/{incident}/{tag}"
    if not ds.startswith("labpool/sandbox/"):
        die(EXIT_ASSERT, f"assertion failed: teardown refuses {ds}")
    pgdata = sandbox_pgdata_path(incident, tag)
    stop_sandbox(pgdata, sandbox_port(tag), log)
    append_cmd(log, f"zfs destroy -r {ds}")
    ssh_sudo(f"if zfs list -H -o name '{ds}' >/dev/null 2>&1; then zfs destroy -r '{ds}'; fi\n")


def copy_wal(incident: str, start_lsn: str, end_lsn: str, wal_mnt: str, log: Path) -> list[str]:
    archive = Path(env("ARCHIVE_ROOT")) / incident
    names = wal_range(start_lsn, end_lsn)
    present = []
    ssh_ok(f"mkdir -p '{wal_mnt}' && chmod 0755 '{wal_mnt}'", what="mkdir wal")
    host_tmp = lab_root() / "var" / "sandbox" / incident / "wal-stage"
    host_tmp.mkdir(parents=True, exist_ok=True)
    for name in names:
        src = archive / name
        if src.is_file():
            present.append(name)
            dest = host_tmp / name
            if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
                dest.write_bytes(src.read_bytes())
    if not present:
        die(EXIT_PRECOND, f"precondition failed: no WAL segments for {start_lsn}..{end_lsn} in {archive}")
    append_cmd(log, f"rsync wal {present[0]}..{present[-1]} -> {wal_mnt}")
    proc = subprocess.run(
        ["rsync", "-a", str(host_tmp) + "/", f"{env('VM_SSH')}:/tmp/p4-wal-{incident}/"],
        text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        die(EXIT_ASSERT, "assertion failed: rsync wal: " + (proc.stderr or proc.stdout or ""))
    ssh_ok(
        f"mkdir -p '{wal_mnt}' && cp -a /tmp/p4-wal-{incident}/. '{wal_mnt}/' "
        f"&& chown -R postgres:postgres '{wal_mnt}' && chmod 0755 '{wal_mnt}'",
        what="install wal into sandbox",
    )
    return present


def write_sandbox_conf(pgdata: str, wal_mnt: str, port: int, target_lsn: str) -> str:
    conf = (
        f"data_directory = '{pgdata}'\n"
        f"hba_file = '{pgdata}/pg_hba.conf'\n"
        f"ident_file = '{pgdata}/pg_ident.conf'\n"
        f"port = {port}\n"
        f"listen_addresses = 'localhost,{env('VM_ADDR')}'\n"
        f"unix_socket_directories = '{pgdata}'\n"
        "archive_mode = off\n"
        f"restore_command = 'cp {wal_mnt}/%f %p'\n"
        f"recovery_target_lsn = '{target_lsn}'\n"
        "recovery_target_inclusive = on\n"
        "recovery_target_action = 'pause'\n"
        "recovery_target_timeline = 'latest'\n"
        "hot_standby = on\n"
        "wal_level = logical\n"
        "max_wal_senders = 4\n"
        "max_replication_slots = 4\n"
        "logging_collector = on\n"
        "log_filename = 'sandbox.log'\n"
        "log_directory = 'log'\n"
    )
    hba = (
        "local   all             postgres                                peer\n"
        "host    all             postgres        127.0.0.1/32            trust\n"
        f"host    all             postgres        {env('VM_ADDR')}/32     trust\n"
        f"host    all             postgres        {env('HOST_PG_CIDR')}        trust\n"
    )
    return f"""
set -euo pipefail
PGDATA='{pgdata}'
mkdir -p "$PGDATA/log"
rm -f "$PGDATA/postmaster.pid" "$PGDATA/postmaster.pid.old"
cat > "$PGDATA/postgresql.conf" <<'EOF'
{conf}EOF
cat > "$PGDATA/pg_hba.conf" <<'EOF'
{hba}EOF
: > "$PGDATA/pg_ident.conf"
touch "$PGDATA/recovery.signal"
chown -R postgres:postgres "$PGDATA"
chmod 0700 "$PGDATA"
"""


def wait_replay(port: int, target_int: int, timeout_s: int = 90) -> dict:
    sql = "SELECT pg_last_wal_replay_lsn()::text, pg_is_in_recovery();"
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        proc = ssh_sudo(
            f"sudo -n -u postgres {PG_BIN}/psql -X -qAt -h 127.0.0.1 -p {port} "
            f"-d {env('DB_NAME')} -c \"{sql}\""
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parts = proc.stdout.strip().replace("|", "\t").split("\t")
            replay = parts[0].strip()
            inrec = parts[1].strip() if len(parts) > 1 else ""
            last = {"replay_lsn": replay, "in_recovery": inrec in {"t", "true", "on", "1"}}
            try:
                if lsn_int(replay) >= target_int:
                    return last
            except ValueError:
                pass
        time.sleep(1)
    die(EXIT_ASSERT, f"assertion failed: sandbox did not reach target LSN; last={last}")
    return last


def injection_commit(ev: Path, inj: dict) -> tuple[int, str]:
    """Position of the injection's commit record, and where it was read.

    injection.json records commit_lsn from pg_current_wal_lsn() read before COMMIT. That is a bound, and it can lie
    before the transaction's own change records. The decoded change log holds the commit record itself, so it is
    used when present. A target at or after the commit record replays it; a target before it does not.
    """
    xid = inj.get("xid")
    log = ev / "db.jsonl"
    if xid is not None and log.is_file():
        with log.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("action") == "C" and str(rec.get("xid")) == str(xid) and rec.get("lsn"):
                    return lsn_int(rec["lsn"]), "change_log"
    return lsn_int(inj["commit_lsn"]), "recorded_bound"


def beyond_target_absent(incident: str, target_int: int, port: int) -> dict:
    ev = evidence_dir(incident)
    inj = json.loads((ev / "injection.json").read_text(encoding="utf-8"))
    inj_lsn, inj_source = injection_commit(ev, inj)
    destroyed = [int(x) for x in inj.get("row_ids") or []][:1]
    rel = inj.get("relation") or os.environ.get("SC01_RELATION") or "p2_probe"
    rid = destroyed[0] if destroyed else None
    present = None
    if rid is not None:
        sql = f"SELECT COUNT(*) FROM public.{rel} WHERE id = {rid};"
        proc = ssh_sudo(
            f"sudo -n -u postgres {PG_BIN}/psql -X -qAt -h 127.0.0.1 -p {port} "
            f"-d {env('DB_NAME')} -c \"{sql}\""
        )
        if proc.returncode == 0:
            present = int(proc.stdout.strip() or "0")
    if target_int < inj_lsn:
        ok = present is None or present >= 1
        kind = "before_inject"
    else:
        ok = present is None or present == 0
        kind = "at_or_after_inject"
    return {
        "kind": kind,
        "row_id": rid,
        "present": present,
        "absent_ok": ok,
        "inject_lsn_int": inj_lsn,
        "inject_lsn_source": inj_source,
    }


def restore_db(
    incident: str,
    lsn_int_v: int,
    restore_of: str | None,
    log: Path,
) -> dict:
    target = lsn_text_from_int(lsn_int_v)
    resolved = resolve_snapshot(incident, target)
    snap = resolved["snapshot"]
    origin = f"{env('DS_PGDATA')}@{snap}"
    tag = tag_for(incident, lsn_int_v, restore_of)
    pgdata_ds = sandbox_dataset(incident, tag, "pgdata")
    pgdata_mount = sandbox_mount(incident, tag, "pgdata")
    pgdata = sandbox_pgdata_path(incident, tag)
    wal_mnt = sandbox_mount(incident, tag, "wal")
    port = sandbox_port(tag)
    refuse_victim_target("zfs clone dest", pgdata_ds)
    refuse_victim_target("sandbox pgdata", pgdata)

    before = victim_zfs_identity()
    ensure_sandbox_parent()

    if dataset_exists(pgdata_ds):
        changed = False
        state = "exists"
    else:
        changed = True
        state = "created"
        ssh_ok(
            f"zfs create -p -o mountpoint=/labpool/sandbox/{incident}/{tag} "
            f"labpool/sandbox/{incident}/{tag}",
            what="create sandbox tag dataset",
        )
        append_cmd(log, f"zfs clone {origin} {pgdata_ds} mountpoint={pgdata_mount}")
        ssh_ok(
            f"zfs clone -o mountpoint='{pgdata_mount}' '{origin}' '{pgdata_ds}'",
            what="zfs clone pgdata snapshot into sandbox",
        )
        ssh_ok(f"mkdir -p '{wal_mnt}'", what="mkdir wal mount")

    start_lsn = str(resolved["snapshot_lsn"] or "1/D8000000")
    start_int = max(0, lsn_int(start_lsn) - 0x2000000)
    start_lsn = f"{start_int >> 32:X}/{start_int & 0xFFFFFFFF:X}"
    segs = copy_wal(incident, start_lsn, target, wal_mnt, log)

    stop_sandbox(pgdata, port, log)
    ssh_ok(write_sandbox_conf(pgdata, wal_mnt, port, target), what="write sandbox recovery conf")
    append_cmd(log, f"{PG_BIN}/pg_ctl -D {pgdata} start (sandbox only, port {port})")
    start = ssh_sudo(
        f"sudo -n -u postgres {PG_BIN}/pg_ctl -D '{pgdata}' -l '{pgdata}/log/startup.log' "
        f"start -o \"-p {port} -c unix_socket_directories={pgdata}\""
    )
    if start.returncode != 0:
        # Interrupted recovery from a previous kill: destroy the clone and retry once.
        append_cmd(log, f"pg_ctl start failed; recreating clone {pgdata_ds}")
        teardown(incident, tag, log)
        ssh_ok(
            f"zfs create -p -o mountpoint=/labpool/sandbox/{incident}/{tag} "
            f"labpool/sandbox/{incident}/{tag}",
            what="recreate sandbox tag dataset",
        )
        ssh_ok(
            f"zfs clone -o mountpoint='{pgdata_mount}' '{origin}' '{pgdata_ds}'",
            what="reclone pgdata snapshot",
        )
        ssh_ok(f"mkdir -p '{wal_mnt}'", what="mkdir wal mount")
        segs = copy_wal(incident, start_lsn, target, wal_mnt, log)
        ssh_ok(write_sandbox_conf(pgdata, wal_mnt, port, target), what="rewrite sandbox recovery conf")
        start = ssh_sudo(
            f"sudo -n -u postgres {PG_BIN}/pg_ctl -D '{pgdata}' -l '{pgdata}/log/startup.log' "
            f"start -o \"-p {port} -c unix_socket_directories={pgdata}\""
        )
        changed = True
        state = "recreated"
    if start.returncode != 0:
        logtail = ssh_sudo(
            f"tail -80 '{pgdata}/log/startup.log' '{pgdata}/log/sandbox.log' 2>/dev/null || true"
        )
        die(
            EXIT_ASSERT,
            "assertion failed: sandbox pg_ctl start: "
            + (start.stderr or start.stdout or "")
            + "\n"
            + (logtail.stdout or ""),
        )

    replay = wait_replay(port, lsn_int_v)
    beyond = beyond_target_absent(incident, lsn_int_v, port)
    after = victim_zfs_identity()
    if after["sha256"] != before["sha256"]:
        die(EXIT_ASSERT, "assertion failed: victim zfs identity changed during restore-db")

    replay_int = lsn_int(replay["replay_lsn"])
    stopped = replay_int >= lsn_int_v  # reached target; pause should not overshoot far
    result = {
        "ok": True,
        "changed": changed,
        "state": state,
        "incident": incident,
        "target_lsn": target,
        "target_lsn_int": lsn_int_v,
        "replay_lsn": replay["replay_lsn"],
        "replay_lsn_int": replay_int,
        "stopped_at_target": bool(stopped and beyond.get("absent_ok")),
        "beyond_target_absent": bool(beyond.get("absent_ok")),
        "beyond": beyond,
        "snapshot": snap,
        "restore_target": {
            "sandbox_pgdata": pgdata,
            "sandbox_port": port,
            "fs_clone_dataset": None,
            "pgdata_dataset": pgdata_ds,
            "tag": tag,
        },
        "victim_zfs_before": before["sha256"],
        "victim_zfs_after": after["sha256"],
        "wal_segments": segs,
        "in_recovery": replay.get("in_recovery"),
    }
    from lab_p4_util import write_json, write_text
    rd = review_dir("E002") if log.parent.name == "E002" else None
    if rd is not None:
        write_json(rd / "replay-target.json", {
            "target_lsn_int": lsn_int_v,
            "replay_lsn_int": replay_int,
            "stopped_at_target": bool(result["stopped_at_target"]),
            "beyond_target_absent": bool(result["beyond_target_absent"]),
            "replay_lsn": replay["replay_lsn"],
            "target_lsn": target,
        })
        write_text(rd / "victim-untouched.txt", (
            f"before {before['sha256']}\n"
            f"after  {after['sha256']}\n"
            f"identical {before['sha256'] == after['sha256']}\n"
        ))
    return result


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-restore-db")
    p.add_argument("incident")
    p.add_argument("lsn_int", type=int)
    p.add_argument("--restore-of", default=None)
    p.add_argument("--teardown", action="store_true")
    p.add_argument("--task", default="E002")
    args = p.parse_args(argv)
    log = review_dir(args.task) / "commands.log"
    if args.teardown:
        tag = tag_for(args.incident, args.lsn_int, args.restore_of)
        teardown(args.incident, tag, log)
        print(json.dumps({"ok": True, "torn_down": True, "tag": tag}, sort_keys=True))
        return 0
    out = restore_db(args.incident, args.lsn_int, args.restore_of, log)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
