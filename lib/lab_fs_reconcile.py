"""Exact C-7 reconciliation of file intentions against adjacent snapshot intervals."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import PurePosixPath

from lab_snapshot_tick import ordered_snapshots


def timestamp(raw: str) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("file timestamps must be UTC strings")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("file timestamps must be UTC")
    return value


def relative_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw or any(c in raw for c in "\t\r\n"):
        raise ValueError("invalid relative path")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or str(path) != raw:
        raise ValueError("path must be canonical and relative to the protected root")
    return raw


def reconcile_file_operations(snapshots: list[dict], operations: list[dict],
                              differences: list[dict], *, declared: bool) -> dict:
    matched = invisible = 0
    unmatched, unexplained, errors = [], [], []
    grouped = defaultdict(list)
    try:
        snapshots = ordered_snapshots(snapshots)
        names = [s["snapshot"] for s in snapshots]
        times = [timestamp(s.get("created_at") or s.get("wall_clock") or s["lsn_recorded_at"])
                 for s in snapshots]
        if len(set(names)) != len(names) or any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError("snapshot names/times must be unique and times increasing in recorded-LSN order")
    except (KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "rule": "C-7", "matched": 0, "invisible": 0,
                "unmatched_recorded": len(operations), "unexplained_captured": len(differences),
                "fs_ops": len(operations), "errors": [str(exc)], "vacuous": False}
    intervals = {(a, b): i for i, (a, b) in enumerate(zip(names, names[1:]))}
    for index, op in enumerate(operations):
        try:
            path = relative_path(op["path"])
            ts = timestamp(op["ts"])
            operation = op["operation"]
            if operation not in {"create", "append", "overwrite", "delete"}:
                raise ValueError("unknown file operation")
            interval = next((i for i in range(len(times) - 1) if times[i] < ts <= times[i + 1]), None)
            if interval is None:
                raise ValueError("operation outside recorded snapshot intervals")
            grouped[(interval, path)].append((ts, index, op))
        except (KeyError, TypeError, ValueError) as exc:
            unmatched.append({"op_index": index, "reason": str(exc)})

    captured = defaultdict(list)
    for index, diff in enumerate(differences):
        try:
            interval = intervals[(diff["from_snapshot"], diff["to_snapshot"])]
            path = relative_path(diff["path"])
            if diff["change_type"] not in {"+", "-", "M", "R"}:
                raise ValueError("unknown captured change type")
            captured[(interval, path, diff["change_type"])].append(index)
        except (KeyError, TypeError, ValueError) as exc:
            unexplained.append({"diff_index": index, "reason": str(exc)})
    explained = set()
    parent_changes = set()
    for (interval, path), rows in grouped.items():
        rows.sort(key=lambda row: (row[0], row[1]))
        initial = rows[0][2]["operation"] != "create"
        exists = initial
        valid = True
        for _, _, op in rows:
            action = op["operation"]
            if action == "create":
                valid = valid and not exists
                exists = True
            elif action == "delete":
                valid = valid and exists
                exists = False
            else:
                valid = valid and exists
            if action in {"create", "delete"}:
                # Membership changes affect exactly the immediate parent directory.
                parent_changes.add((interval, str(PurePosixPath(path).parent), "M"))
        if not valid:
            unmatched.extend({"op_index": row[1], "path": path, "reason": "inconsistent operation sequence"}
                             for row in rows)
            continue
        if not initial and not exists:
            invisible += len(rows)
            continue
        change = "+" if not initial else "-" if not exists else "M"
        keys = [(interval, path, change)]
        # Removing and recreating an existing object may be represented as -/+.
        actions = [row[2]["operation"] for row in rows]
        replacement = initial and exists and "delete" in actions and "create" in actions
        if replacement and not captured.get(keys[0]):
            keys = [(interval, path, "-"), (interval, path, "+")]
        if all(captured.get(key) for key in keys):
            matched += len(rows)
            explained.update(captured[key][0] for key in keys)
        else:
            unmatched.extend({"op_index": row[1], "path": path, "interval": interval + 1,
                              "expected": change} for row in rows)
    for key in parent_changes:
        if captured.get(key):
            explained.add(captured[key][0])
    already_unexplained = {row["diff_index"] for row in unexplained}
    for index, diff in enumerate(differences):
        if index not in explained and index not in already_unexplained:
            unexplained.append({"diff_index": index, **diff})
    if declared and matched == 0:
        errors.append("declared file activity has zero matched operations")
    return {
        "ok": not unmatched and not unexplained and not errors,
        "rule": "C-7", "fs_ops": len(operations), "matched": matched,
        "unmatched_recorded": len(unmatched), "unexplained_captured": len(unexplained),
        "invisible": invisible, "vacuous": not declared and not operations and not differences,
        "unmatched_recorded_detail": unmatched, "unexplained_captured_detail": unexplained,
        "errors": errors,
    }
