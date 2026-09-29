"""P4 shared helpers: sandbox paths, guest SSH, integer LSN snapshot pick, safety."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from lab_evidence_manifest import manifest_lines
from lab_paths import env, evidence_dir, lab_root
from lsn import lsn_int, lsn_norm, parse_lsn

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3

SANDBOX_PARENT = "labpool/sandbox"
SANDBOX_PORT_DEFAULT = 55432
PG_BIN = "/usr/lib/postgresql/18/bin"


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def write_text(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    tmp.replace(path)
    os.chmod(path, mode)


def write_json(path: Path, obj: object, mode: int = 0o644) -> None:
    write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n", mode)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def restore_root(incident: str, restore_of: str) -> Path:
    return lab_root() / "var" / "restore" / incident / restore_of


def review_dir(task: str) -> Path:
    path = lab_root() / "logs" / "review" / task
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_cmd(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip() + "\n")


def ssh_sudo(script: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", env("VM_SSH"), "sudo -n bash -s"],
        input=script if script.endswith("\n") else script + "\n",
        text=True, capture_output=True, check=False, timeout=timeout,
    )


def ssh_ok(script: str, timeout: int = 180, what: str = "guest command") -> str:
    proc = ssh_sudo(script, timeout=timeout)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        die(EXIT_ASSERT, f"assertion failed: {what}: {err}")
    return proc.stdout


def refuse_victim_target(kind: str, value: str) -> None:
    pgdata = env("PG_DATA")
    protected = env("MNT_PROTECTED")
    ds_pg = env("DS_PGDATA")
    ds_prot = env("DS_PROTECTED")
    ds_parent = env("DS_PARENT")
    lowered = value.strip()
    if lowered in {pgdata, protected, ds_pg, ds_prot, ds_parent}:
        die(EXIT_ASSERT, f"assertion failed: refusing {kind} against victim resource {value!r}")
    if lowered.startswith(ds_parent + "@") or lowered.startswith("labpool/victim"):
        die(EXIT_ASSERT, f"assertion failed: refusing {kind} against victim resource {value!r}")
    if "/victim/" in lowered and "/sandbox/" not in lowered:
        die(EXIT_ASSERT, f"assertion failed: refusing {kind} against victim resource {value!r}")


def sandbox_dataset(incident: str, tag: str, leaf: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", incident):
        die(EXIT_USAGE, f"usage: bad incident {incident!r}")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", tag):
        die(EXIT_USAGE, f"usage: bad sandbox tag {tag!r}")
    if leaf not in {"pgdata", "protected", "wal", "conf"}:
        die(EXIT_USAGE, f"usage: bad sandbox leaf {leaf!r}")
    return f"{SANDBOX_PARENT}/{incident}/{tag}/{leaf}"


def sandbox_mount(incident: str, tag: str, leaf: str) -> str:
    return f"/labpool/sandbox/{incident}/{tag}/{leaf}"


def ensure_sandbox_parent() -> None:
    proc = ssh_sudo(
        "if ! zfs list -H -o name labpool/sandbox >/dev/null 2>&1; then\n"
        "  zfs create -o mountpoint=/labpool/sandbox labpool/sandbox\n"
        "fi\n"
    )
    if proc.returncode != 0:
        die(EXIT_ASSERT, "assertion failed: cannot create labpool/sandbox: " + (proc.stderr or ""))


def newest_snapshot_at_or_below(records: list[dict], target_int: int) -> dict | None:
    """Integer LSN pick: newest recorded_lsn/lsn with lsn_int <= target. Never string compare."""
    eligible = []
    for rec in records:
        if rec.get("invalidated"):
            continue
        raw = rec.get("lsn") or rec.get("recorded_lsn")
        if not raw:
            continue
        try:
            n = lsn_int(str(raw))
        except ValueError:
            continue
        if n <= target_int:
            eligible.append((n, rec.get("snapshot") or "", rec))
    if not eligible:
        return None
    eligible.sort(key=lambda t: (t[0], t[1]))
    return eligible[-1][2]


def load_snapshot_records(incident: str) -> list[dict]:
    archive = Path(env("ARCHIVE_ROOT")) / incident / "snapshots.json"
    ev = evidence_dir(incident) / "snapshots.json"
    path = archive if archive.is_file() else ev
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: no snapshots.json for {incident}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        die(EXIT_ASSERT, "assertion failed: snapshots.json is not an array")
    return data


def resolve_snapshot(incident: str, target_lsn: str) -> dict:
    target_int = lsn_int(target_lsn)
    rec = newest_snapshot_at_or_below(load_snapshot_records(incident), target_int)
    cli = lab_root() / "bin" / "lab-coordinate"
    proc = subprocess.run(
        [str(cli), "--lsn", lsn_norm(target_lsn)],
        cwd=str(lab_root()), text=True, capture_output=True, check=False, env=os.environ,
    )
    coord: dict = {}
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            coord = json.loads(proc.stdout)
        except json.JSONDecodeError:
            coord = {}
    snap = (rec or {}).get("snapshot") or coord.get("snapshot")
    if not snap:
        die(EXIT_PRECOND, f"precondition failed: no snapshot at or below {target_lsn}")
    rec_lsn = (rec or {}).get("lsn") or (rec or {}).get("recorded_lsn") or coord.get("lsn")
    return {
        "snapshot": snap,
        "snapshot_lsn": rec_lsn,
        "snapshot_lsn_int": lsn_int(str(rec_lsn)) if rec_lsn else None,
        "target_lsn": lsn_norm(target_lsn),
        "target_lsn_int": target_int,
        "skew_ms": int(coord.get("skew_ms") or 0),
        "wall_clock": coord.get("wall_clock"),
        "resolved_by": coord.get("resolved_by") or "lsn_first",
        "coordinate": coord,
    }


def wal_range(start_lsn: str, end_lsn: str) -> list[str]:
    a, b = lsn_int(start_lsn), lsn_int(end_lsn)
    if b < a:
        a, b = b, a
    names: list[str] = []
    cur = a
    while cur <= b + 0x1000000:
        high = cur >> 32
        low = cur & 0xFFFFFFFF
        names.append(f"{1:08X}{high:08X}{(low // 0x1000000):08X}")
        nxt = ((cur // 0x1000000) + 1) * 0x1000000
        if nxt <= cur:
            break
        cur = nxt
        if len(names) > 64:
            break
    out, seen = [], set()
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def no_peek_ok(rec: dict) -> bool:
    flags = rec.get("selection_inputs") or {}
    return (
        flags.get("read_injection_log") is False
        and flags.get("read_oracle_optimum") is False
        and flags.get("read_provenance") is False
    )


def load_arm_coordinate(incident: str, which: str) -> dict:
    p3 = evidence_dir(incident) / "p3"
    name = {"arm_a": "arm-a-coordinate.json", "naive": "naive-coordinate.json"}[which]
    return json.loads((p3 / name).read_text(encoding="utf-8"))


def tree_clean() -> bool:
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=str(lab_root()), text=True, capture_output=True, check=False,
    )
    return proc.returncode == 0 and not proc.stdout.strip()


def git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(lab_root()), text=True, capture_output=True, check=True,
    )
    return proc.stdout.strip()


def victim_zfs_identity() -> dict:
    script = r"""
for ds in labpool/victim labpool/victim/pgdata labpool/victim/protected; do
  echo "DS $ds $(zfs get -H -o value guid,createtxg $ds | tr '\t' ' ')"
  zfs list -H -t snapshot -o name,guid "$ds" 2>/dev/null | awk '{print "SNAP "$0}'
done
"""
    proc = ssh_sudo(script)
    if proc.returncode != 0:
        die(EXIT_ASSERT, "assertion failed: cannot read victim zfs identity: " + (proc.stderr or ""))
    return {"text": proc.stdout, "sha256": sha256_text(proc.stdout)}


def evidence_tree_hash() -> str:
    lines = manifest_lines()
    return sha256_text("\n".join(lines) + "\n")


def victim_plus_evidence_manifest() -> dict:
    zfs = victim_zfs_identity()
    ev = evidence_tree_hash()
    blob = zfs["sha256"] + "\n" + ev + "\n"
    return {
        "zfs_sha256": zfs["sha256"],
        "evidence_sha256": ev,
        "combined_sha256": sha256_text(blob),
    }


def grep_log_forbidden(log_text: str) -> list[str]:
    hits = []
    pgdata = env("PG_DATA")
    for line in log_text.splitlines():
        if re.search(r"\bzfs\s+rollback\b", line) and "sandbox" not in line:
            hits.append(line)
        if re.search(r"\b(pg_ctl|systemctl)\b", line) and pgdata in line:
            hits.append(line)
        if "systemctl" in line and re.search(r"postgresql@.*main", line) and "sandbox" not in line:
            hits.append(line)
    return hits
