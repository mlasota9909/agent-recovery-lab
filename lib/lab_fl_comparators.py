"""File safe frontier and declared +20 second time estimate (P12 ADR-10)."""
from __future__ import annotations

from datetime import timedelta
import json
import sys

from lab_fl_intervals import Parser, digest, snapshot_records
from lab_fs_reconcile import timestamp
from lab_p3_util import EXIT_PRECOND, die, write_json
from lab_paths import evidence_dir
from lsn import lsn_int


def result(incident, arm, chosen, reason, **extra):
    coord = None if chosen is None else {
        "snapshot": chosen["snapshot"], "time": chosen["created_at"],
        "lsn": chosen["recorded_lsn"], "lsn_int": lsn_int(chosen["recorded_lsn"])}
    return {"schema_version": 1, "incident_id": incident, "comparator": arm,
            "outcome": "accepted" if coord else "run_failure", "coordinate": coord, "reason": reason, **extra}


def rank(incident: str) -> dict:
    directory = evidence_dir(incident)
    artifact = json.loads((directory / "fl-intervals.json").read_text(encoding="utf-8"))
    text = (directory / "snapshots.json").read_text(encoding="utf-8")
    snapshots = snapshot_records(json.loads(text))
    if (artifact["schema_version"] != 1 or artifact["incident_id"] != incident
            or artifact["source_sha256"]["snapshots.json"] != digest(text)):
        raise ValueError("invalid or stale interval artifact")
    rows = artifact["intervals"]
    if len(rows) != len(snapshots) - 1:
        raise ValueError("incomplete interval artifact")
    first = None
    for i, (row, start, end) in enumerate(zip(rows, snapshots, snapshots[1:]), 1):
        if (row["interval"] != i or row["from_snapshot"] != start["snapshot"]
                or row["to_snapshot"] != end["snapshot"] or type(row["flagged"]) is not bool
                or row["flagged"] != (row["anomaly_score"] >= 3.0)):
            raise ValueError("invalid interval boundary or flag")
        if first is None and row["flagged"]:
            first = (i, start)
    return result(incident, "rank", first[1] if first else None,
                  "start snapshot of first flagged interval" if first else "no flagged interval",
                  first_flagged_interval=first[0] if first else None)


def naive(incident: str) -> dict:
    directory = evidence_dir(incident)
    metadata = json.loads((directory / "incident.json").read_text(encoding="utf-8"))
    approx = metadata["approx_incident_time"]
    cutoff = timestamp(approx) + timedelta(seconds=20)
    snapshots = snapshot_records(json.loads((directory / "snapshots.json").read_text(encoding="utf-8")))
    eligible = [row for row in snapshots if timestamp(row["created_at"]) <= cutoff]
    return result(incident, "naive", eligible[-1] if eligible else None,
                  "latest snapshot at or before estimate" if eligible else "estimate precedes all snapshots",
                  approx_incident_time=approx, declared_error_seconds=20,
                  cutoff=cutoff.isoformat().replace("+00:00", "Z"))


def main(argv=None) -> int:
    parser = Parser(prog="lab-fl-comparators")
    parser.add_argument("arm", choices=("rank", "naive"))
    parser.add_argument("incident")
    args = parser.parse_args(argv)
    try:
        out = (rank if args.arm == "rank" else naive)(args.incident)
        write_json(evidence_dir(args.incident) / f"fl-{args.arm}.json", out)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        die(EXIT_PRECOND, "precondition failed: " + str(exc))
    print(json.dumps(out, sort_keys=True))
    return 0 if out["outcome"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
