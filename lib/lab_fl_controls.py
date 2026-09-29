"""Four file-level acceptance controls on isolated snapshot restores."""
from __future__ import annotations

import json
import sys

from lab_fl_check import check
from lab_fl_intervals import Parser, snapshot_records
from lab_fl_reference import load as load_reference
from lab_fs_reconcile import timestamp
from lab_p3_util import write_json
from lab_paths import evidence_dir


def controls(incident: str) -> dict:
    directory = evidence_dir(incident)
    reference = load_reference(incident)
    injection = json.loads((directory / "injection.json").read_text(encoding="utf-8"))
    snapshots = snapshot_records(json.loads((directory / "snapshots.json").read_text(encoding="utf-8")))
    post = next((row for row in snapshots if timestamp(row["created_at"]) > timestamp(injection["t_end"])), None)
    if post is None:
        raise ValueError("no snapshot after injection end")
    cases = (("reference", reference["coordinate"]["snapshot"], "correct"),
             ("first_post_damage", post["snapshot"], "checked_damage_remains"),
             ("earliest", snapshots[0]["snapshot"], "extra_work_lost"),
             ("tampered", reference["coordinate"]["snapshot"], "checked_damage_remains"))
    rows = []
    for name, snapshot, expected in cases:
        report = check(incident, snapshot, tamper=name == "tampered")
        ok = report["verdict_v2"] == expected and not report.get("cleanup_error")
        if name == "tampered":
            ok = ok and report["summary"]["probe_mismatches"] > 0
        rows.append({"control": name, "snapshot": snapshot, "expected": expected,
                     "actual": report["verdict_v2"], "summary": report["summary"], "ok": ok})
    out = {"schema_version": 1, "incident_id": incident, "ok": all(row["ok"] for row in rows), "controls": rows}
    write_json(directory / "fl-controls.json", out)
    return out


def main(argv=None) -> int:
    parser = Parser(prog="lab-fl-controls")
    parser.add_argument("incident")
    args = parser.parse_args(argv)
    try:
        out = controls(args.incident)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("precondition failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(out, sort_keys=True))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
