"""Three file-level inputs over the same three highest-scoring intervals."""
from __future__ import annotations

import json
import math
import sys
from pathlib import PurePosixPath

from lab_fl_intervals import FEATURES, Parser, digest, read_differences
from lab_fl_rules import BOUNDARY_KEYS, visible_index
from lab_modelview_guard import guard
from lab_p3_util import EXIT_PRECOND, die, write_json, write_text
from lab_paths import evidence_dir

INPUTS = ("R0", "R1", "R2")


def json_line(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def boundary(row: dict) -> dict:
    return {key: row[key] for key in BOUNDARY_KEYS}


def select_intervals(artifact: dict) -> list[dict]:
    if artifact["schema_version"] != 1:
        raise ValueError("unsupported interval schema")
    rows = artifact["intervals"]
    visible_index(json_line({"intervals": [boundary(row) for row in rows]}))
    for number, row in enumerate(rows, 1):
        if row["interval"] != number:
            raise ValueError("interval artifact must contain every interval starting at 1")
        score = row["anomaly_score"]
        if type(score) not in (int, float) or not math.isfinite(score):
            raise ValueError("anomaly scores must be finite numbers")
        if set(row["counts"]) != set(FEATURES) or any(
                type(value) is not int or value < 0 for value in row["counts"].values()):
            raise ValueError("invalid interval file counts")
    chosen = sorted(rows, key=lambda row: (-row["anomaly_score"], row["interval"]))[:3]
    return sorted(chosen, key=lambda row: row["interval"])


def most_changed_directory(differences: list[dict]) -> str:
    """The parent directory with the most captured changes (ties: alphabetical first); "." when none.

    This mirrors the database-level Written Summaries, which name the table with the most changes."""
    counts: dict[str, int] = {}
    for diff in differences:
        paths = diff["path"].split(" -> ") if diff["change_type"] == "R" else [diff["path"]]
        for path in paths:
            parent = str(PurePosixPath(path).parent)
            counts[parent] = counts.get(parent, 0) + 1
    if not counts:
        return "."
    return min(counts, key=lambda d: (-counts[d], d))


def build(incident: str, representation: str) -> dict:
    if representation not in INPUTS:
        raise ValueError("input must be R0, R1 or R2")
    directory = evidence_dir(incident)
    artifact = json.loads((directory / "fl-intervals.json").read_text(encoding="utf-8"))
    if artifact["incident_id"] != incident:
        raise ValueError("interval artifact belongs to a different incident")
    selected = select_intervals(artifact)
    text = (directory / "fs_diff.tsv").read_text(encoding="utf-8")
    if digest(text) != artifact["source_sha256"]["fs_diff.tsv"]:
        raise ValueError("differences changed; rebuild fl-intervals.json")
    differences = read_differences(text)
    by_pair = {(row["from_snapshot"], row["to_snapshot"]): [] for row in artifact["intervals"]}
    for diff in differences:
        pair = (diff["from_snapshot"], diff["to_snapshot"])
        if pair not in by_pair:
            raise ValueError("difference lies outside recorded intervals")
        by_pair[pair].append(diff)
    lines = [json_line({"intervals": [boundary(row) for row in selected]})]
    for row in selected:
        changes = sorted(by_pair[(row["from_snapshot"], row["to_snapshot"])],
                         key=lambda diff: (diff["path"], diff["change_type"]))
        if representation == "R0":
            lines.extend(json_line({**boundary(row), "change_type": diff["change_type"], "path": diff["path"]})
                         for diff in changes)
        elif representation == "R1":
            lines.append(json_line({"interval": row["interval"], "anomaly_score": row["anomaly_score"],
                                    "last_safe_snapshot": row["from_snapshot"]}))
        else:
            counts = row["counts"]
            lines.append(f"Interval {row['interval']} [{row['from_time']} .. {row['to_time']}]: "
                         f"{counts['files_deleted']} files deleted, {counts['files_modified']} modified, "
                         f"{counts['files_created']} created under {json_line(most_changed_directory(changes))}; "
                         f"anomaly {json_line(row['anomaly_score'])}.")
    view = {"content": "\n".join(lines), "incident_id": incident, "params": {"top_n": 3},
            "probe_id": "FL-intervals", "representation": representation, "telemetry": {}}
    guard(view)
    return view


def main(argv=None) -> int:
    from lab_fl_prompt import assemble

    parser = Parser(prog="lab-fl-inputs")
    parser.add_argument("incident")
    parser.add_argument("--input", required=True, choices=INPUTS)
    args = parser.parse_args(argv)
    try:
        view = build(args.incident, args.input)
        prompt = assemble(view)
        out = evidence_dir(args.incident) / "fl-inputs" / args.input
        write_json(out / "model-view.json", view)
        write_text(out / "content.txt", view["content"])
        write_text(out / "prompt.txt", prompt)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        die(EXIT_PRECOND, f"precondition failed: {exc}")
    print(json.dumps(view, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
