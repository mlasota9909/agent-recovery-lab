"""E004: one coordinate → DB PITR + FS clone, record skew, report skeleton."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lab_p4_util import (
    EXIT_ASSERT,
    EXIT_USAGE,
    die,
    load_arm_coordinate,
    no_peek_ok,
    resolve_snapshot,
    restore_root,
    review_dir,
    victim_plus_evidence_manifest,
    write_json,
)
from lab_restore_db import restore_db, teardown as teardown_db
from lab_restore_fs import restore_fs, teardown_fs
from lsn import lsn_int, lsn_norm


def newest_snapshot_fixture_39_310() -> dict:
    """AC-P4-05: 3/9 vs 3/10 must use integer order (3/10 > 3/9)."""
    from lab_p4_util import newest_snapshot_at_or_below
    recs = [
        {"snapshot": "snap_3_9", "lsn": "3/9"},
        {"snapshot": "snap_3_10", "lsn": "3/10"},
    ]
    pick = newest_snapshot_at_or_below(recs, lsn_int("3/10"))
    string_wrong = sorted(["3/9", "3/10"])[-1]  # string: 3/9 > 3/10
    return {
        "integer_pick": (pick or {}).get("snapshot"),
        "integer_ok": (pick or {}).get("snapshot") == "snap_3_10",
        "string_sort_last": string_wrong,
        "string_would_pick_3_9": string_wrong == "3/9",
    }


def load_coordinate(path: Path, restore_of: str) -> dict:
    rec = json.loads(path.read_text(encoding="utf-8"))
    if restore_of == "ground_truth":
        coord = rec.get("coordinate") or rec
        lsn = coord.get("lsn") or rec.get("lsn_text") or rec.get("lsn")
        if not lsn:
            die(EXIT_USAGE, "usage: ground_truth coordinate missing lsn")
        return {
            "lsn_text": lsn,
            "lsn_int": rec.get("lsn_int") or lsn_int(lsn),
            "snapshot": coord.get("snapshot"),
            "selection_inputs": {},
        }
    # Arm coordinates and throwaway tags (e005neg, too_late, …) all require no-peek.
    if rec.get("selection_inputs") is not None or restore_of in {"arm_a", "naive", "arm_b"}:
        if not no_peek_ok(rec):
            die(EXIT_ASSERT, "assertion failed: arm coordinate failed no-peek; restore refused")
        return rec
    lsn = rec.get("lsn_text") or rec.get("lsn") or (rec.get("coordinate") or {}).get("lsn")
    if not lsn:
        die(EXIT_USAGE, f"usage: restore_of {restore_of} missing lsn")
    return {
        "lsn_text": lsn,
        "lsn_int": rec.get("lsn_int") or lsn_int(lsn),
        "snapshot": rec.get("snapshot"),
        "selection_inputs": rec.get("selection_inputs") or {},
    }


def restore(incident: str, coord_path: Path, restore_of: str, task: str = "E004") -> dict:
    rec = load_coordinate(coord_path, restore_of)
    lsn_text = rec["lsn_text"]
    resolved = resolve_snapshot(incident, lsn_text)
    log = review_dir(task) / "commands.log"
    before = victim_plus_evidence_manifest()
    db = restore_db(incident, int(rec["lsn_int"]), restore_of, log)
    fs = restore_fs(incident, resolved["snapshot"], restore_of, log)
    target = db["restore_target"]
    target["fs_clone_dataset"] = fs["clone_dataset"]
    target["fs_mount"] = fs["mountpoint"]
    partial = {
        "incident_id": incident,
        "restore_of": restore_of,
        "coordinate": {
            "lsn_text": lsn_norm(lsn_text),
            "lsn_int": int(rec["lsn_int"]),
            "snapshot": resolved["snapshot"],
            "skew_ms": resolved["skew_ms"],
        },
        "restore_target": target,
        "selector_provenance": {
            "restored_against_arm": restore_of if restore_of != "ground_truth" else None,
            "arm_no_peek_ok": True if restore_of == "ground_truth" else no_peek_ok(rec),
        },
        "safety": {"manifest_before": before["combined_sha256"]},
        "db_restore": {k: db[k] for k in ("replay_lsn", "replay_lsn_int", "stopped_at_target", "snapshot")},
        "fs_restore": {"clone_dataset": fs["clone_dataset"], "mountpoint": fs["mountpoint"]},
    }
    outdir = restore_root(incident, restore_of)
    write_json(outdir / "report.partial.json", partial)
    skew = {
        "target_lsn_int": int(rec["lsn_int"]),
        "snapshot": resolved["snapshot"],
        "snapshot_lsn_int": resolved["snapshot_lsn_int"],
        "skew_ms": resolved["skew_ms"],
    }
    write_json(review_dir(task) / "skew.json", skew)
    partial["skew"] = skew
    return partial


def teardown(incident: str, restore_of: str, task: str = "E004") -> None:
    log = review_dir(task) / "commands.log"
    teardown_db(incident, restore_of, log)
    teardown_fs(incident, restore_of, log)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-restore")
    p.add_argument("incident")
    p.add_argument("coordinate_json")
    p.add_argument("--restore-of", required=True)
    p.add_argument("--teardown", action="store_true")
    p.add_argument("--task", default="E004")
    p.add_argument("--lsn-order-fixture", action="store_true")
    args = p.parse_args(argv)
    if args.lsn_order_fixture:
        print(json.dumps(newest_snapshot_fixture_39_310(), sort_keys=True))
        return 0 if newest_snapshot_fixture_39_310()["integer_ok"] else EXIT_ASSERT
    if args.teardown:
        teardown(args.incident, args.restore_of, args.task)
        print(json.dumps({"ok": True, "torn_down": True}, sort_keys=True))
        return 0
    path = Path(args.coordinate_json)
    out = restore(args.incident, path, args.restore_of, args.task)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
