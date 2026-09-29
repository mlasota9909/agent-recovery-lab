"""File interval features and known-onset baseline scoring (P12 ADR-3/4)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys

from lab_fs_reconcile import relative_path, timestamp
from lab_paths import evidence_dir
from lab_p3_util import EXIT_PRECOND, EXIT_USAGE, die, write_json
from lab_snapshot_tick import ordered_snapshots
from lsn import lsn_norm

FEATURES = ("files_deleted", "files_modified", "files_created")
THRESHOLD = 3.0
NAME = re.compile(r"[A-Za-z0-9._-]+\Z")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(EXIT_USAGE, "usage: " + message + "\n")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_records(records: list[dict]) -> list[dict]:
    if not isinstance(records, list) or len(records) < 2:
        raise ValueError("at least two recorded snapshots are required")
    clean = []
    for row in records:
        name = row["snapshot"]
        if not isinstance(name, str) or not NAME.fullmatch(name) or row.get("invalidated"):
            raise ValueError("invalid or invalidated snapshot")
        time = timestamp(row.get("created_at") or row.get("wall_clock") or row["lsn_recorded_at"])
        lsn = lsn_norm(row.get("recorded_lsn") or row["lsn"])
        clean.append({"snapshot": name, "created_at": time.isoformat().replace("+00:00", "Z"),
                      "recorded_lsn": lsn})
    clean = ordered_snapshots(clean)
    times = [timestamp(row["created_at"]) for row in clean]
    if len({row["snapshot"] for row in clean}) != len(clean) or any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("snapshot names must be unique and times increasing in recorded-LSN order")
    return clean


def read_differences(text: str) -> list[dict]:
    rows, seen = [], set()
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            raise ValueError("fs_diff.tsv requires four columns")
        start, end, change, path = parts
        if change not in {"-", "M", "+", "R"}:
            raise ValueError("unknown file change type")
        if change == "R":
            paths = path.split(" -> ")
            if len(paths) != 2:
                raise ValueError("rename requires exactly old_path -> new_path")
        else:
            paths = [path]
        for item in paths:
            relative_path(item)
        key = tuple(parts)
        if key in seen:
            raise ValueError("duplicate captured difference")
        seen.add(key)
        rows.append({"from_snapshot": start, "to_snapshot": end, "change_type": change, "path": path})
    return rows


def file_inventory(text: str, names: set[str]) -> dict[str, set[str]]:
    inventory = {name: set() for name in names}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError("fs_hashes.tsv requires snapshot, path, hash")
        name, path, value = parts
        relative_path(path)
        if name not in inventory or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise ValueError("invalid fingerprint snapshot or SHA-256")
        if path in inventory[name]:
            raise ValueError("duplicate snapshot fingerprint path")
        inventory[name].add(path)
    return inventory


def build_intervals(snapshots: list[dict], differences: list[dict], hashes: str, injection_start: str) -> dict:
    snapshots = snapshot_records(snapshots)
    onset = timestamp(injection_start)
    inventory = file_inventory(hashes, {row["snapshot"] for row in snapshots})
    rows, pairs = [], {}
    for number, (start, end) in enumerate(zip(snapshots, snapshots[1:]), 1):
        row = {"interval": number, "from_snapshot": start["snapshot"], "to_snapshot": end["snapshot"],
               "from_time": start["created_at"], "to_time": end["created_at"],
               "from_lsn": start["recorded_lsn"], "to_lsn": end["recorded_lsn"],
               "counts": dict.fromkeys(FEATURES, 0)}
        rows.append(row)
        pairs[(start["snapshot"], end["snapshot"])] = row
    for diff in differences:
        pair = (diff["from_snapshot"], diff["to_snapshot"])
        if pair not in pairs:
            raise ValueError("difference does not belong to consecutive recorded snapshots")
        before, after = inventory[pair[0]], inventory[pair[1]]
        counts = pairs[pair]["counts"]
        path, change = diff["path"], diff["change_type"]
        if change == "-" and path in before:
            counts["files_deleted"] += 1
        elif change == "+" and path in after:
            counts["files_created"] += 1
        elif change == "M" and (path in before or path in after):
            counts["files_modified"] += 1
        elif change == "R":
            old, new = path.split(" -> ")
            counts["files_deleted"] += int(old in before)
            counts["files_created"] += int(new in after)
    baseline = [row for row in rows if timestamp(row["to_time"]) < onset]
    if not baseline:
        raise ValueError("no intervals end before injection start")
    stats = {}
    for feature in FEATURES:
        values = [row["counts"][feature] for row in baseline]
        sigma = statistics.pstdev(values)
        stats[feature] = {"mean": statistics.mean(values), "stddev": sigma, "scale": max(1.0, sigma)}
    for row in rows:
        deviations = {key: (row["counts"][key] - stats[key]["mean"]) / stats[key]["scale"] for key in FEATURES}
        row.update(standardised_deviations=deviations, anomaly_score=max(deviations.values()))
        row["flagged"] = row["anomaly_score"] >= THRESHOLD
    return {"schema_version": 1, "threshold": THRESHOLD,
            "baseline": {"rule": "interval_end_before_injection_start", "injection_start": injection_start,
                         "intervals": [row["interval"] for row in baseline], "statistics": stats},
            "intervals": rows}


def build(incident: str) -> dict:
    directory = evidence_dir(incident)
    sources = {name: (directory / name).read_text(encoding="utf-8") for name in
               ("snapshots.json", "fs_diff.tsv", "fs_hashes.tsv", "injection.json")}
    result = build_intervals(json.loads(sources["snapshots.json"]), read_differences(sources["fs_diff.tsv"]),
                             sources["fs_hashes.tsv"], json.loads(sources["injection.json"])["t_start"])
    result.update(incident_id=incident, source_sha256={name: digest(text) for name, text in sources.items()})
    return result


def main(argv=None) -> int:
    parser = Parser(prog="lab-fl-intervals")
    parser.add_argument("incident")
    args = parser.parse_args(argv)
    try:
        result = build(args.incident)
        write_json(evidence_dir(args.incident) / "fl-intervals.json", result)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        die(EXIT_PRECOND, f"precondition failed: {exc}")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
