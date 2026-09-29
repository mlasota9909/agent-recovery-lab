"""lab-fs-capture: zfs diff walker + .zfs/snapshot tree hasher. JSON on stdout."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from lab_paths import current_incident, env, evidence_dir, lab_root

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3
CHANGE_TYPES = {"+", "-", "M", "R"}


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def emit(obj: dict) -> None:
    print(json.dumps(obj, sort_keys=True))


def ssh(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", env("VM_SSH"), script],
        text=True, capture_output=True, check=False,
    )


def diff_path(incident: str) -> Path:
    return evidence_dir(incident) / "fs_diff.tsv"


def hash_path(incident: str) -> Path:
    return evidence_dir(incident) / "fs_hashes.tsv"


def existing_diff_pairs(path: Path) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    if not path.is_file():
        return pairs
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            pairs.add((parts[0], parts[1]))
    return pairs


def existing_hash_snaps(path: Path) -> set[str]:
    snaps: set[str] = set()
    if not path.is_file():
        return snaps
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        snaps.add(line.split("\t", 1)[0])
    return snaps


def zfs_diff_rows(snap_from: str, snap_to: str) -> list[tuple[str, str]]:
    ds = env("DS_PROTECTED")
    proc = ssh(f"sudo -n zfs diff -H '{ds}@{snap_from}' '{ds}@{snap_to}'")
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: zfs diff: {proc.stderr.strip() or proc.stdout.strip()}")
    # Reuse the P0 parser for quoting/renames.
    parse = subprocess.run(
        [sys.executable, str(lab_root() / "bin" / "lab-zfs-diff-json")],
        input=proc.stdout, text=True, capture_output=True, check=False,
    )
    if parse.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: zfs diff parse: {parse.stderr.strip()}")
    entries = json.loads(parse.stdout)
    rows = []
    for item in entries:
        ctype = item["change_type"]
        if ctype not in CHANGE_TYPES:
            die(EXIT_ASSERT, f"assertion failed: unsupported change type {ctype!r}")
        path = item["path"]
        if ctype == "R" and item.get("old_path"):
            path = f"{item['old_path']} -> {item['path']}"
        rows.append((ctype, path))
    return rows


def cmd_diff(incident: str, snap_from: str, snap_to: str) -> int:
    out = diff_path(incident)
    if (snap_from, snap_to) in existing_diff_pairs(out):
        emit({"ok": True, "changed": False, "action": "diff", "incident": incident,
              "snap_from": snap_from, "snap_to": snap_to, "output": str(out)})
        return 0
    rows = zfs_diff_rows(snap_from, snap_to)
    lines = [f"{snap_from}\t{snap_to}\t{ctype}\t{path}\n" for ctype, path in rows]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)
        handle.flush()
        os.fsync(handle.fileno())
    emit({"ok": True, "changed": True, "action": "diff", "incident": incident,
          "snap_from": snap_from, "snap_to": snap_to, "rows": len(rows),
          "output": str(out)})
    return 0


def cmd_hash(incident: str, snap: str) -> int:
    out = hash_path(incident)
    if snap in existing_hash_snaps(out):
        emit({"ok": True, "changed": False, "action": "hash", "incident": incident,
              "snapshot": snap, "output": str(out)})
        return 0
    mount = env("MNT_PROTECTED")
    if not all(c.isalnum() or c in "._-" for c in snap):
        die(EXIT_USAGE, f"usage: unsafe snapshot name {snap!r}")
    remote = (
        "set -euo pipefail\n"
        f"root='{mount}/.zfs/snapshot/{snap}'\n"
        'test -d "$root" || { echo "precondition failed: snapshot root missing: $root" >&2; exit 2; }\n'
        'python3 - "$root" <<\'PY\'\n'
        "import hashlib, os, sys\n"
        "root = sys.argv[1]\n"
        "for directory, directories, filenames in os.walk(root):\n"
        "    directories[:] = [d for d in sorted(directories) if d != '.zfs']\n"
        "    for filename in sorted(filenames):\n"
        "        path = os.path.join(directory, filename)\n"
        "        if not os.path.isfile(path) or os.path.islink(path):\n"
        "            continue\n"
        "        digest = hashlib.sha256()\n"
        "        with open(path, 'rb') as handle:\n"
        "            for block in iter(lambda: handle.read(1024 * 1024), b''):\n"
        "                digest.update(block)\n"
        "        rel = os.path.relpath(path, root)\n"
        "        print(rel + '\\t' + digest.hexdigest())\n"
        "PY\n"
    )
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", env("VM_SSH"),
         "sudo -n bash -s"],
        input=remote, text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: tree hash: {proc.stderr.strip() or proc.stdout.strip()}")
    lines = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        rel, digest = line.split("\t", 1)
        lines.append(f"{snap}\t{rel}\t{digest}\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)
        handle.flush()
        os.fsync(handle.fileno())
    emit({"ok": True, "changed": True, "action": "hash", "incident": incident,
          "snapshot": snap, "rows": len(lines), "output": str(out)})
    return 0


def main(argv: list[str]) -> int:
    incident = None
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--incident" and i + 1 < len(argv):
            incident = argv[i + 1]
            i += 2
            continue
        args.append(argv[i])
        i += 1
    if incident is None:
        incident = current_incident()
    if not args:
        die(EXIT_USAGE, "usage: lab-fs-capture diff <snap_from> <snap_to> | hash <snap> [--incident ID]")
    if args[0] == "diff":
        if len(args) != 3:
            die(EXIT_USAGE, "usage: lab-fs-capture diff <snap_from> <snap_to> [--incident ID]")
        return cmd_diff(incident, args[1], args[2])
    if args[0] == "hash":
        if len(args) != 2:
            die(EXIT_USAGE, "usage: lab-fs-capture hash <snap> [--incident ID]")
        return cmd_hash(incident, args[1])
    die(EXIT_USAGE, "usage: lab-fs-capture diff <snap_from> <snap_to> | hash <snap> [--incident ID]")
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
