"""Resolve file recovery locators solely from the displayed interval catalogue."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

CONTENT_BEGIN = "<<<FL_CONTENT"
CONTENT_END = "FL_CONTENT>>>"
BOUNDARY_KEYS = ("interval", "from_snapshot", "to_snapshot", "from_time", "to_time")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z")
NAME = re.compile(r"[A-Za-z0-9._-]+\Z")


def utc_time(value: str) -> datetime:
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise ValueError("timestamp must be ISO-8601 UTC with Z or +00:00")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def visible_index(content: str) -> dict:
    """Only the first, explicit boundary record defines visible locators."""
    lines = content.splitlines()
    if not lines:
        raise ValueError("missing visible interval catalogue")
    catalogue = json.loads(lines[0])
    if not isinstance(catalogue, dict) or set(catalogue) != {"intervals"}:
        raise ValueError("expected visible interval catalogue")
    rows = catalogue["intervals"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty or invalid visible interval catalogue")
    intervals, snapshots, times = {}, {}, {}
    previous = None
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(BOUNDARY_KEYS):
            raise ValueError("invalid visible interval fields")
        number = row["interval"]
        if type(number) is not int or number < 1 or number in intervals:
            raise ValueError("invalid or duplicate visible interval")
        start, end = utc_time(row["from_time"]), utc_time(row["to_time"])
        if start >= end:
            raise ValueError("visible interval times must increase")
        if previous and (number <= previous["interval"] or start < utc_time(previous["to_time"])):
            raise ValueError("visible intervals must be ordered and nonoverlapping")
        if previous and number == previous["interval"] + 1 and (
                row["from_snapshot"] != previous["to_snapshot"] or start != utc_time(previous["to_time"])):
            raise ValueError("consecutive visible intervals must share a boundary")
        for side, time in (("from", start), ("to", end)):
            name = row[side + "_snapshot"]
            if not isinstance(name, str) or not NAME.fullmatch(name):
                raise ValueError("invalid visible snapshot name")
            if name in snapshots and snapshots[name] != time:
                raise ValueError("conflicting visible snapshot times")
            if time in times and times[time] != name:
                raise ValueError("multiple visible snapshots have the same recorded time")
            snapshots[name], times[time] = time, name
        intervals[number] = row["from_snapshot"]
        previous = row
    return {"intervals": intervals, "snapshots": snapshots}


def resolve(token: str, index: dict) -> dict:
    result = {"token": token, "resolved_snapshot": None, "discard_reason": None}
    try:
        if "=" not in token:
            raise ValueError("malformed locator: expected key=value")
        key, value = token.split("=", 1)
        if key == "interval":
            if not re.fullmatch(r"[0-9]+", value) or int(value) not in index["intervals"]:
                raise ValueError("interval is invalid or not visible")
            snapshot = index["intervals"][int(value)]
        elif key == "snapshot":
            if value not in index["snapshots"]:
                raise ValueError("snapshot is not visible")
            snapshot = value
        elif key == "ts":
            time = utc_time(value)
            eligible = [(recorded, name) for name, recorded in index["snapshots"].items() if recorded <= time]
            if not eligible:
                raise ValueError("no visible snapshot at or before timestamp")
            snapshot = max(eligible)[1]
        else:
            raise ValueError("unrecognised locator key")
        result["resolved_snapshot"] = snapshot
    except ValueError as exc:
        result["discard_reason"] = str(exc)
    return result


def extract(inputs: dict) -> dict:
    completion, content = inputs["completion"], inputs["content"]
    if not isinstance(completion, str) or not isinstance(content, str):
        raise ValueError("completion and content must be text")
    result = {"outcome": "rule_rejection", "snapshot": None, "reason": "", "locators": []}
    # Revised (P11) reading: exactly one COORDINATE line and no REFUSAL line is an answer; exactly one REFUSAL line
    # and no COORDINATE line is a decline; surrounding text is allowed; anything else is a rule rejection.
    tagged = [(m.group(1), (m.group(2) or "").strip()) for m in
              (re.match(r"^(COORDINATE|REFUSAL):?(?:\s+(.*))?$", line.strip()) for line in completion.splitlines())
              if m]
    coordinates = [body for tag, body in tagged if tag == "COORDINATE"]
    refusals = [body for tag, body in tagged if tag == "REFUSAL"]
    if len(refusals) == 1 and not coordinates:
        result["outcome"] = "declined"
        result["reason"] = refusals[0]
        return result
    if len(coordinates) != 1 or refusals:
        result["reason"] = ("expected exactly one COORDINATE line and no REFUSAL line, or one REFUSAL line; found "
                            f"{len(coordinates)} COORDINATE and {len(refusals)} REFUSAL")
        return result
    body = coordinates[0]
    try:
        index = visible_index(content)
    except (ValueError, KeyError, TypeError) as exc:
        result["reason"] = "invalid visible evidence: " + str(exc)
        return result
    result["locators"] = [resolve(token, index) for token in body.split()]
    resolved = {row["resolved_snapshot"] for row in result["locators"] if row["resolved_snapshot"] is not None}
    if not resolved:
        result["reason"] = "no locator resolves from the visible evidence"
    elif len(resolved) != 1:
        result["reason"] = "resolved locators identify distinct snapshots"
    else:
        result.update(outcome="accepted", snapshot=resolved.pop(), reason="all resolved locators agree")
    return result


def content_from_text(text: str) -> str:
    """Accept a saved prompt, model-view JSON, or the exact content string."""
    try:
        obj = json.loads(text)
    except ValueError:
        obj = None
    if isinstance(obj, dict) and "content" in obj:
        if not isinstance(obj["content"], str):
            raise ValueError("model-view content must be text")
        return obj["content"]
    if CONTENT_BEGIN in text or CONTENT_END in text:
        if text.count(CONTENT_BEGIN) != 1 or text.count(CONTENT_END) != 1:
            raise ValueError("ambiguous prompt content boundaries")
        before, body = text.split(CONTENT_BEGIN, 1)
        if CONTENT_END in before or not body.startswith("\n"):
            raise ValueError("invalid prompt content boundaries")
        content, _ = body[1:].split(CONTENT_END, 1)
        if not content.endswith("\n"):
            raise ValueError("invalid prompt content boundaries")
        return content[:-1]
    return text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="lab-fl-read-answer")
    parser.add_argument("--completion", type=Path, required=True)
    parser.add_argument("--view", type=Path, required=True, help="saved prompt, model-view JSON or content")
    args = parser.parse_args(argv)
    try:
        result = extract({"completion": args.completion.read_text(encoding="utf-8"),
                          "content": content_from_text(args.view.read_text(encoding="utf-8"))})
    except (OSError, ValueError, TypeError) as exc:
        print(f"lab-fl-read-answer: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
