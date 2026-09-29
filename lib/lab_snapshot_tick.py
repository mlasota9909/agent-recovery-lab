"""One locked snapshot writer and append-only incident manifest."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from lab_incident_runtime import incident_runtime
from lab_paths import current_incident, env, evidence_dir
from lsn import lsn_int, lsn_norm


def _ssh(script: str, runtime: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", runtime["VM_SSH"], script],
        text=True, capture_output=True, check=False, timeout=60,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def capture_lsn(runtime: dict) -> tuple[str, str, str]:
    """Capture the LSN/time before switching WAL, after the snapshot."""
    sql = """WITH captured AS MATERIALIZED (
        SELECT pg_current_wal_lsn() AS lsn, clock_timestamp() AS captured_at
    ) SELECT lsn::text,
        to_char(captured_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        pg_switch_wal()::text FROM captured;"""
    proc = _ssh(
        "sudo -n -u postgres psql -X -v ON_ERROR_STOP=1 -At -F '\t' "
        f"-p {shlex.quote(runtime['PG_PORT'])} -d {shlex.quote(runtime['DB_NAME'])} "
        f"-c {shlex.quote(sql)}", runtime,
    )
    if proc.returncode:
        raise RuntimeError(f"assertion failed: cannot capture WAL LSN: {proc.stderr.strip()}")
    parts = proc.stdout.strip().split("\t")
    if len(parts) != 3:
        raise RuntimeError(f"assertion failed: unexpected LSN capture output {proc.stdout!r}")
    return lsn_norm(parts[0]), parts[1], lsn_norm(parts[2])


def zfs_snapshot(name: str, runtime: dict) -> None:
    proc = _ssh(f"sudo -n zfs snapshot -r {shlex.quote(runtime['DS_PARENT'] + '@' + name)}", runtime)
    if proc.returncode:
        raise RuntimeError(f"assertion failed: zfs snapshot failed: {proc.stderr.strip()}")


def ledger_path(incident: str) -> Path:
    return Path(env("ARCHIVE_ROOT")) / incident / "snapshots.json"


@contextmanager
def snapshot_lock(incident: str):
    """Serialize snapshots and file mutations at interval boundaries."""
    directory = ledger_path(incident).parent
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".snapshots.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def load_array(path: Path) -> list:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("assertion failed: snapshots.json is not an array")
    return data


def save_array(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".snapshots.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(records, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def ordered_snapshots(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda r: (
        lsn_int(r.get("recorded_lsn") or r.get("lsn")) if r.get("recorded_lsn") or r.get("lsn") else -1,
        r.get("created_at") or r.get("wall_clock") or "",
        r.get("sequence", 0),
    ))


def _merge_evidence(incident: str, records: list[dict]) -> list[dict]:
    path = evidence_dir(incident) / "snapshots.json"
    merged = {r["snapshot"]: r for r in load_array(path)}
    for row in records:
        rec = {**merged.get(row["snapshot"], {}), **row}
        rec["wall_clock"] = rec.get("created_at") or rec.get("wall_clock") or rec.get("lsn_recorded_at")
        rec["lsn"] = rec.get("recorded_lsn", rec.get("lsn"))
        merged[row["snapshot"]] = rec
    rows = ordered_snapshots(list(merged.values()))
    save_array(path, rows)
    return rows


def merge_snapshot_records(incident: str) -> list[dict]:
    with snapshot_lock(incident):
        return _merge_evidence(incident, load_array(ledger_path(incident)))


def unique_snapshot_name(incident: str, prefix: str, records: list[dict]) -> tuple[str, int]:
    """Reserve the sequence under snapshot_lock, including failed attempts."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", prefix):
        raise ValueError("precondition failed: unsafe SNAP_PREFIX")
    path = ledger_path(incident).parent / ".snapshot-sequence"
    previous = int(path.read_text()) if path.is_file() else 0
    sequence = max(previous, max((r.get("sequence", 0) for r in records), default=0)) + 1
    with path.open("w") as handle:
        handle.write(str(sequence) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:-3] + "Z"
    return f"{prefix}{stamp}_{sequence:06d}", sequence


_CAPTURE = object()


def append_anchored_snapshot(incident: str, lsn: str | None | object = _CAPTURE,
                             *, label: str = "loop") -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", label):
        raise ValueError("usage: invalid snapshot label")
    runtime = incident_runtime(incident)
    with snapshot_lock(incident):
        records = load_array(ledger_path(incident))
        name, sequence = unique_snapshot_name(incident, runtime["SNAP_PREFIX"], records)
        zfs_snapshot(name, runtime)
        wall = utc_now()
        if lsn is _CAPTURE:
            recorded, captured_at, switched = capture_lsn(runtime)
        else:
            # Synthetic negative checks can still write a null anchor.
            recorded = lsn_norm(str(lsn)) if lsn is not None else None
            captured_at, switched = wall, None
        rec = {
            "incident": incident, "snapshot": name, "sequence": sequence, "label": label,
            "created_at": wall, "wall_clock": wall, "recorded_lsn": recorded, "lsn": recorded,
            "lsn_recorded_at": captured_at, "wal_switch_lsn": switched,
            "operations": ["zfs_snapshot", "pg_current_wal_lsn", "pg_switch_wal"],
        }
        records.append(rec)
        save_array(ledger_path(incident), records)
        _merge_evidence(incident, records)
        return rec


def null_lsn_scan(path: Path) -> list:
    return [r for r in load_array(path) if r.get("recorded_lsn", r.get("lsn")) is None]


def lsns_monotonic(path: Path) -> bool:
    values = [lsn_int(r.get("recorded_lsn") or r["lsn"]) for r in load_array(path)]
    return all(a <= b for a, b in zip(values, values[1:]))


def main(argv=None) -> int:
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(3, "usage: " + message + "\n")

    def label_value(value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value):
            raise argparse.ArgumentTypeError("invalid snapshot label")
        return value

    parser = Parser()
    parser.add_argument("--incident")
    parser.add_argument("--label", required=True, type=label_value)
    args = parser.parse_args(argv)
    try:
        rec = append_anchored_snapshot(args.incident or os.environ.get("LAB_ACTIVE_INCIDENT")
                                       or current_incident(), label=args.label)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps({"ok": True, "changed": True, **rec}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
