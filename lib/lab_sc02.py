"""SC-02 filesystem mass-deletion + overwrite, with overlapping file-churn confounder."""
from __future__ import annotations

import json
import os
import shlex
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, die, ssh_psql, utc_now, write_json, write_jsonl
from lab_p7 import ssh
from lab_paths import env, evidence_dir, lab_root
from lab_sc01_workload import ConcurrentApp
import lab_sc02_layout as layout
from lab_fs_workload import record_operations
from lab_snapshot_tick import snapshot_lock, ledger_path, load_array
from lsn import lsn_norm

_protected = os.environ.get("INC_PROTECTED")
if not _protected:
    raise SystemExit("precondition failed: INC_PROTECTED is required for SC-02; shared path fallback is forbidden")
TREE = f"{_protected}/{layout.TREE}"
CONFIG = f"{_protected}/{layout.CONFIG}"
RECORDS = f"{_protected}/{layout.RECORDS}"
BUILD = f"{_protected}/{layout.BUILD}"
OVERWRITE = f"{_protected}/{layout.OVERWRITE}"


def _pg(sql: str) -> str:
    proc = ssh_psql(sql)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: psql: {proc.stderr.strip()[-500:]}")
    return proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""


def prepare(incident: str) -> dict:
    script = (
        f"sudo -n mkdir -p {CONFIG} {_protected}/{layout.NESTED} {BUILD} && "
        f"sudo -n bash -c 'for i in $(seq 1 12); do echo seed-$i > {RECORDS}/f$i.txt; done' && "
        f"sudo -n bash -c 'echo readme > {_protected}/{layout.README}' && "
        f"sudo -n bash -c 'echo initial > {OVERWRITE}' && "
        f"sudo -n chown -R {env('OS_USER_APP')}:{env('OS_USER_APP')} {TREE} && "
        f"sudo -n chmod -R a+rwX {TREE}"
    )
    proc = ssh(script, timeout=30)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: SC-02 seed tree: {proc.stderr.strip() or proc.stdout.strip()}")
    return {
        "baseline_s": 60,
        "after_s": 4,
        "tps": 6.0,
        "mix": "lab_app-file-churn+lab_app-dml+lab_agent-rm-overwrite",
        "tree": TREE,
        "baseline_started": utc_now(),
    }


class _FileChurn:
    def __init__(self, incident: str) -> None:
        self.incident = incident
        self.stop_event = threading.Event()
        self.ops: list[dict] = []
        self.thread: threading.Thread | None = None
        self.error: str | None = None
        self.n = 0

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="sc02-fs", daemon=True)
        self.thread.start()

    def stop(self) -> list[dict]:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                die(EXIT_ASSERT, "assertion failed: SC-02 file churn did not stop")
        if self.error:
            die(EXIT_ASSERT, self.error)
        return list(self.ops)

    def _run(self) -> None:
        user = env("OS_USER_APP")
        try:
            while not self.stop_event.is_set():
                n = self.n
                self.n += 1
                operations = [{"path": f"{layout.BUILD}/t{n}.txt", "operation": "create", "kind": "file"}]
                commands = [f"printf 'body-{n}\\n' > {shlex.quote(BUILD + f'/t{n}.txt')}"]
                if n > 0:
                    operations.append({"path": f"{layout.BUILD}/t{n-1}.txt", "operation": "append", "kind": "file"})
                    commands.append(f"printf 'mut-{n}\\n' >> {shlex.quote(BUILD + f'/t{n-1}.txt')}")
                if n >= 3:
                    operations.append({"path": f"{layout.BUILD}/t{n-3}.txt", "operation": "delete", "kind": "file"})
                    commands.append(f"rm -- {shlex.quote(BUILD + f'/t{n-3}.txt')}")
                with snapshot_lock(self.incident):
                    self.ops.extend(record_operations(self.incident, operations, "legitimate"))
                    script = "set -euo pipefail; " + "; ".join(commands)
                    proc = ssh(f"sudo -n -u {shlex.quote(user)} bash -c {shlex.quote(script)}", timeout=15)
                    if proc.returncode:
                        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
                self.stop_event.wait(0.4)
        except BaseException as exc:
            self.error = f"assertion failed: sc02 file churn: {exc}"


def start_confounder(incident: str) -> dict:
    app = ConcurrentApp(11, os.environ.get("SC01_RELATION") or "p2_probe", 6.0)
    fs = _FileChurn(incident)
    app.start()
    fs.start()
    return {"app": app, "fs": fs, "incident": incident}


def stop_confounder(handle: dict) -> list[dict]:
    app_rows = handle["app"].stop()
    fs_ops = handle["fs"].stop()
    write_json(evidence_dir(handle["incident"]) / "sc02-fs-churn.json", {"ops": fs_ops, "n": len(fs_ops)})
    if len(fs_ops) < 1:
        die(EXIT_ASSERT, "assertion failed: SC-02 confounder produced no file churn")
    return app_rows



def enumerate_damage_targets(reference_root: str) -> list[dict]:
    """Expand every removed file and directory from the locked reference."""
    script = """import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
removed = root / sys.argv[2]
overwrite = root / sys.argv[3]
if not removed.is_dir() or not overwrite.is_file():
    raise SystemExit('reference damage targets are absent')
rows = [{'path': str(overwrite.relative_to(root)), 'operation': 'overwrite', 'kind': 'file'}]
for path in sorted([removed, *removed.rglob('*')], key=lambda p: (-len(p.parts), str(p))):
    rows.append({'path': str(path.relative_to(root)), 'operation': 'delete',
                 'kind': 'directory' if path.is_dir() else 'file'})
print(json.dumps(rows))
"""
    proc = ssh("sudo -n python3 -c " + shlex.quote(script) + " " + shlex.quote(reference_root)
               + " " + shlex.quote(layout.RECORDS) + " " + shlex.quote(layout.OVERWRITE), timeout=30)
    if proc.returncode:
        die(EXIT_ASSERT, "assertion failed: SC-02 reference enumeration: " + (proc.stderr.strip() or proc.stdout.strip()))
    return json.loads(proc.stdout)


def inject(incident: str) -> dict:
    ed = evidence_dir(incident)
    lsn_start = lsn_norm(_pg("SELECT pg_current_wal_lsn();").upper())
    # Lock across reference enumeration, intention recording, and damage so no
    # snapshot can divide a recorded batch from its effects.
    with snapshot_lock(incident):
        snaps = [r for r in load_array(ledger_path(incident)) if not r.get("invalidated")]
        if not snaps:
            die(EXIT_ASSERT, "assertion failed: SC-02 injection has no reference snapshot")
        reference = max(snaps, key=lambda r: r["created_at"])
        reference_root = f"{_protected}/.zfs/snapshot/{reference['snapshot']}"
        targets = enumerate_damage_targets(reference_root)
        t_start = utc_now()
        fs_ops = record_operations(incident, targets, "injection")
        script = lab_root() / "scenarios" / "sc02" / "inject.sh"
        text = script.read_text(encoding="utf-8")
        import subprocess
        p = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", env("VM_SSH"),
             f"sudo -n -u {shlex.quote(env('OS_USER_AGENT'))} env "
             f"OVERWRITE={shlex.quote(OVERWRITE)} RECORDS={shlex.quote(RECORDS)} bash -s"],
            input=text, text=True, capture_output=True, check=False, timeout=30,
        )
        if p.returncode != 0:
            die(EXIT_ASSERT, f"assertion failed: SC-02 inject: {p.stderr.strip() or p.stdout.strip()}")
        t_end = utc_now()
    lsn_end = lsn_norm(_pg("SELECT pg_current_wal_lsn();").upper())
    check = ssh(
        f"test -d {RECORDS} && echo STILL || echo GONE; "
        f"grep -q OVERWRITE {OVERWRITE} && echo OW || echo NO",
        timeout=15,
    )
    rec = {
        "incident": incident,
        "scenario_id": "SC-02",
        "principal": env("ROLE_AGENT"),
        "t_start": t_start,
        "t_end": t_end,
        "lsn_start": lsn_start,
        "lsn_end": lsn_end,
        "commit_lsn": lsn_end,
        "timing_pattern": "near_instant",
        "ops": ["recursive_delete", "overwrite"],
        "inject_stdout": p.stdout.strip(),
        "reference_snapshot": reference["snapshot"],
        "fs_ops": fs_ops,
        "guest_check": check.stdout.strip(),
        "tree": TREE,
    }
    write_json(ed / "injection.json", rec)
    write_json(ed / "injection_log.json", rec)
    return rec


def oracle(incident: str, inj: dict, app_rows: list, open_snap: dict, pre: dict, post: dict) -> dict:
    ed = evidence_dir(incident)
    snaps_path = Path(env("ARCHIVE_ROOT")) / incident / "snapshots.json"
    snaps = json.loads(snaps_path.read_text(encoding="utf-8")) if snaps_path.is_file() else []
    damage_t = inj["t_start"]
    damage_lsn = lsn_norm(inj["lsn_start"])
    from lsn import lsn_int, lsn_cmp
    candidates = []
    for row in snaps:
        if row.get("invalidated"):
            continue
        rec_lsn = row.get("recorded_lsn")
        created = row.get("created_at") or row.get("lsn_recorded_at")
        if not rec_lsn or not created:
            continue
        if lsn_int(lsn_norm(rec_lsn)) <= lsn_int(damage_lsn):
            candidates.append(row)
    if not candidates:
        die(EXIT_ASSERT, "assertion failed: no CoW snapshot at or before SC-02 damage")
    chosen = max(candidates, key=lambda r: lsn_int(lsn_norm(r["recorded_lsn"])))
    from lab_p7 import resolve_lsn
    coord = resolve_lsn(lsn_norm(chosen["recorded_lsn"]))
    # Prefer the snapshot's own wall clock for the checkpoint gap.
    snap_t = chosen.get("created_at") or coord["wall_clock"]
    def parse(ts: str) -> float:
        return datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
    try:
        gap = parse(damage_t) - parse(snap_t)
    except ValueError:
        gap = parse(damage_t) - parse(coord["wall_clock"])
    db_coord = resolve_lsn(damage_lsn)
    skew_ms = abs(int(round((parse(snap_t) - parse(db_coord["wall_clock"])) * 1000)))
    payload = {
        "coordinate": coord,
        "checkpoint_snapshot": chosen.get("snapshot"),
        "checkpoint_gap_seconds": gap,
        "fs_db_skew_ms": skew_ms,
        "files_lost_if_restored_to_checkpoint": None,
        "malicious_deletions_retained_if_later": None,
        "computed_from": "archive snapshots.json recorded_lsn <= damage lsn_start",
        "incident_extra": {
            "checkpoint_gap_seconds": gap,
            "fs_db_skew_ms": skew_ms,
            "checkpoint_snapshot": chosen.get("snapshot"),
        },
    }
    man = []
    for rec in app_rows or []:
        if rec.get("commit_lsn"):
            man.append({
                "commit_lsn": rec["commit_lsn"],
                "commit_ts": rec.get("wall_clock"),
                "operation": rec.get("operation"),
                "relation": rec.get("relation") or rec.get("table"),
                "row_ids": rec.get("row_ids") or [],
                "row_count": rec.get("row_count") or 1,
                "principal": rec.get("principal"),
            })
    write_jsonl(ed / "workload-manifest.jsonl", man)
    write_json(ed / "oracle.json", {"incident": incident, "coordinate": coord, "sc02": payload})
    write_json(ed / "sc02-oracle.json", payload)
    # P4's established manifest shape. SC-02 damages filesystem state; there
    # are no malicious database rows, so the row sets are empty. Filesystem
    # truth remains in the pre-injection snapshot/fs hash evidence consumed by P4.
    manifest = {
        "destroyed_bytes": 0,
        "destroyed_row_count": 0,
        "destroyed_row_ids": [],
        "legitimate_bytes": 0,
        "legitimate_commits_at_or_before": sum(
            1 for rec in app_rows or [] if rec.get("commit_lsn")
            and lsn_int(lsn_norm(rec["commit_lsn"])) <= lsn_int(coord["lsn"])
        ),
        "legitimate_row_count": 0,
        "legitimate_row_ids": [],
        "malicious_lsn": damage_lsn,
        "optimum_lsn": coord["lsn"],
    }
    write_json(ed / "oracle-manifest.json", manifest, mode=0o444)
    return payload
