"""E003: zfs clone of a snapshot into labpool/sandbox. Never rollback the victim."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lab_p4_util import (
    EXIT_ASSERT,
    EXIT_USAGE,
    append_cmd,
    die,
    ensure_sandbox_parent,
    env,
    refuse_victim_target,
    review_dir,
    sandbox_dataset,
    sandbox_mount,
    ssh_ok,
    ssh_sudo,
    victim_zfs_identity,
)


def dataset_exists(name: str) -> bool:
    return ssh_sudo(f"zfs list -H -o name '{name}' >/dev/null 2>&1").returncode == 0


def teardown_fs(incident: str, tag: str, log: Path) -> None:
    ds = sandbox_dataset(incident, tag, "protected")
    if not ds.startswith("labpool/sandbox/"):
        die(EXIT_ASSERT, f"assertion failed: teardown refuses {ds}")
    append_cmd(log, f"zfs destroy {ds}")
    ssh_sudo(f"if zfs list -H -o name '{ds}' >/dev/null 2>&1; then zfs destroy '{ds}'; fi\n")


def restore_fs(incident: str, snapshot: str, tag: str, log: Path) -> dict:
    if not snapshot.startswith("s_"):
        die(EXIT_USAGE, f"usage: snapshot name {snapshot!r}")
    origin = f"{env('DS_PROTECTED')}@{snapshot}"
    dest = sandbox_dataset(incident, tag, "protected")
    mnt = sandbox_mount(incident, tag, "protected")
    refuse_victim_target("zfs clone dest", dest)
    refuse_victim_target("clone mount", mnt)
    before = victim_zfs_identity()
    snaps_before = ssh_ok(
        f"zfs list -H -t snapshot -o name {env('DS_PROTECTED')}",
        what="list protected snapshots",
    )
    ensure_sandbox_parent()
    ssh_ok(
        f"zfs create -p -o mountpoint=/labpool/sandbox/{incident}/{tag} "
        f"labpool/sandbox/{incident}/{tag} 2>/dev/null || true",
        what="ensure sandbox tag dataset",
    )
    if dataset_exists(dest):
        changed = False
    else:
        append_cmd(log, f"zfs clone {origin} {dest} mountpoint={mnt}")
        ssh_ok(
            f"zfs clone -o mountpoint='{mnt}' '{origin}' '{dest}'",
            what="zfs clone protected snapshot",
        )
        changed = True
    after = victim_zfs_identity()
    snaps_after = ssh_ok(
        f"zfs list -H -t snapshot -o name {env('DS_PROTECTED')}",
        what="list protected snapshots after",
    )
    if after["sha256"] != before["sha256"]:
        die(EXIT_ASSERT, "assertion failed: victim zfs identity changed during restore-fs")
    if snaps_before != snaps_after:
        die(EXIT_ASSERT, "assertion failed: victim snapshot list changed during restore-fs")
    return {
        "ok": True,
        "changed": changed,
        "snapshot": snapshot,
        "clone_dataset": dest,
        "mountpoint": mnt,
        "victim_zfs_before": before["sha256"],
        "victim_zfs_after": after["sha256"],
        "snapshot_list_unchanged": True,
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-restore-fs")
    p.add_argument("incident", nargs="?", default="")
    p.add_argument("snapshot", nargs="?", default="")
    p.add_argument("--tag", default="fs")
    p.add_argument("--teardown", action="store_true")
    p.add_argument("--destroy-dataset", default=None)
    p.add_argument("--task", default="E003")
    args = p.parse_args(argv)
    log = review_dir(args.task) / "commands.log"
    if args.destroy_dataset:
        ds = args.destroy_dataset
        if not ds.startswith("labpool/sandbox/"):
            die(EXIT_ASSERT, f"assertion failed: teardown refuses {ds}")
        ssh_sudo(f"if zfs list -H -o name '{ds}' >/dev/null 2>&1; then zfs destroy '{ds}'; fi\n")
        print(json.dumps({"ok": True, "destroyed": ds}, sort_keys=True))
        return 0
    if args.teardown:
        teardown_fs(args.incident, args.tag, log)
        print(json.dumps({"ok": True, "torn_down": True, "tag": args.tag}, sort_keys=True))
        return 0
    if args.snapshot == "labpool/victim" or args.snapshot.startswith("labpool/victim"):
        die(EXIT_ASSERT, "assertion failed: refusing restore-fs against a victim dataset name")
    out = restore_fs(args.incident, args.snapshot, args.tag, log)
    from lab_p4_util import write_json, write_text
    if args.task == "E003":
        write_json(review_dir("E003") / "clone.json", {
            "snapshot": out["snapshot"],
            "clone_dataset": out["clone_dataset"],
            "mountpoint": out["mountpoint"],
            "changed": out["changed"],
        })
        write_text(review_dir("E003") / "victim-untouched.txt", (
            f"before {out['victim_zfs_before']}\n"
            f"after  {out['victim_zfs_after']}\n"
            f"identical {out['victim_zfs_before'] == out['victim_zfs_after']}\n"
            f"snapshot_list_unchanged {out['snapshot_list_unchanged']}\n"
        ))
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
