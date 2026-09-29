"""Scoring-only reference, expanded damage targets and visible legitimate work."""
from __future__ import annotations

from collections import defaultdict
import json
import sys

from lab_fl_intervals import Parser, digest, file_inventory, read_differences, snapshot_records
from lab_fs_reconcile import reconcile_file_operations, relative_path, timestamp
from lab_p3_util import EXIT_PRECOND, die, write_json
from lab_paths import evidence_dir
from lab_validate import parse_hash_lines
from lsn import lsn_int

SOURCES = ("snapshots.json", "fs_diff.tsv", "fs_hashes.tsv", "fs-workload.jsonl", "injection.json")


def coordinate(snapshot: dict) -> dict:
    return {"snapshot": snapshot["snapshot"], "time": snapshot["created_at"],
            "lsn": snapshot["recorded_lsn"], "lsn_int": lsn_int(snapshot["recorded_lsn"])}


def build_reference(snapshots, differences, hashes, operations, injection) -> dict:
    snapshots = snapshot_records(snapshots)
    onset = timestamp(injection["t_start"])
    eligible = [s for s in snapshots if timestamp(s["created_at"]) < onset]
    if not eligible:
        raise ValueError("no snapshot strictly before injection start")
    reference = eligible[-1]
    file_inventory(hashes, {s["snapshot"] for s in snapshots})
    fingerprints = dict(parse_hash_lines(hashes, snapshot=reference["snapshot"]))
    targets = injection["fs_ops"]
    if not isinstance(targets, list) or not targets:
        raise ValueError("injection requires recorded file targets")
    manifest = {}
    for index, target in enumerate(targets):
        path = relative_path(target["path"])
        kind = target["kind"]
        if target["operation"] not in {"delete", "overwrite"} or kind not in {"file", "directory"}:
            raise ValueError("unsupported damage target")
        if kind == "directory" and target["operation"] != "delete":
            raise ValueError("directory damage must be recursive deletion")
        matches = [p for p in fingerprints if p == path] if kind == "file" else [
            p for p in fingerprints if p.startswith(path + "/")]
        if kind == "file" and not matches:
            raise ValueError("damage target file absent from reference fingerprints: " + path)
        for match in matches:
            row = manifest.setdefault(match, {"path": match, "sha256": fingerprints[match], "target_indices": []})
            row["target_indices"].append(index)
    if not manifest:
        raise ValueError("damage manifest has no reference files")
    for op in operations:
        if op.get("source") not in {"legitimate", "injection"} or op.get("kind") not in {"file", "directory"}:
            raise ValueError("file intentions require source and kind")
    reconciliation = reconcile_file_operations(snapshots, operations, differences, declared=True)
    if not reconciliation["ok"]:
        raise ValueError("file evidence fails C-7: " + json.dumps(reconciliation, sort_keys=True))
    times = [timestamp(s["created_at"]) for s in snapshots]
    groups = defaultdict(list)
    for index, op in enumerate(operations):
        ts = timestamp(op["ts"])
        interval = next(i for i in range(1, len(times)) if times[i-1] < ts <= times[i])
        groups[(interval, op["path"])].append((ts, index, op))
    visible = set()
    for rows in groups.values():
        rows.sort(key=lambda row: (row[0], row[1]))
        # Same net-effect convention as C-7: create then delete is invisible.
        if rows[0][2]["operation"] != "create" or rows[-1][2]["operation"] != "delete":
            visible.update(index for _, index, _ in rows)
    intervals = []
    for i, (start, end) in enumerate(zip(snapshots, snapshots[1:]), 1):
        rows = [{"op_index": index, "ts": op["ts"], "path": op["path"],
                 "operation": op["operation"], "visible": index in visible}
                for (number, _), group in groups.items() if number == i
                for _, index, op in group if op["source"] == "legitimate" and op["kind"] == "file"]
        rows.sort(key=lambda row: (timestamp(row["ts"]), row["op_index"]))
        intervals.append({"interval": i, "from_snapshot": start["snapshot"], "to_snapshot": end["snapshot"],
                          "operations": rows, "visible_operations": sum(row["visible"] for row in rows)})
    return {"schema_version": 1, "coordinate": coordinate(reference),
            "reference_fingerprints": fingerprints, "damage_manifest": [manifest[p] for p in sorted(manifest)],
            "legitimate_intervals": intervals}


def build(incident: str) -> dict:
    directory = evidence_dir(incident)
    sources = {name: (directory / name).read_text(encoding="utf-8") for name in SOURCES}
    result = build_reference(json.loads(sources["snapshots.json"]), read_differences(sources["fs_diff.tsv"]),
                             sources["fs_hashes.tsv"],
                             [json.loads(line) for line in sources["fs-workload.jsonl"].splitlines() if line.strip()],
                             json.loads(sources["injection.json"]))
    result.update(incident_id=incident, source_sha256={name: digest(text) for name, text in sources.items()})
    return result


def load(incident: str) -> dict:
    result = json.loads((evidence_dir(incident) / "fl-reference.json").read_text(encoding="utf-8"))
    if result != build(incident):
        raise ValueError("reference is stale or invalid; rebuild fl-reference.json")
    return result


def main(argv=None) -> int:
    parser = Parser(prog="lab-fl-reference")
    parser.add_argument("incident")
    args = parser.parse_args(argv)
    try:
        result = build(args.incident)
        write_json(evidence_dir(args.incident) / "fl-reference.json", result)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        die(EXIT_PRECOND, "precondition failed: " + str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
