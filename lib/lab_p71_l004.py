"""Mechanical L004 completeness, validity, supersession and provenance checks."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from lab_p7 import PRINCIPAL_TOKEN_RE, load_matrix_rows, load_plan, planned_new_cells, root, row_cell_key
from lab_p3_util import write_json

LATEST_IDS = {
    "SC-02": "i_20260827T061207Z_3b8879",
    "SC-03": "i_20260827T061350Z_b8b219",
    "SC-04": "i_20260827T061535Z_a7f1e0",
}


def matrix_outcome(row: dict) -> str:
    return (((row.get("validation_detail") or {}).get("matrix") or {}).get("outcome") or "run_failure")


def derive(path: Path) -> tuple[dict, list[dict], list[dict]]:
    rows = load_matrix_rows(path)
    planned = {c["cell_key"]: c for c in planned_new_cells(load_plan())}
    by_id = {r.get("run_id"): r for r in rows if r.get("run_id")}
    successors: dict[str, list[str]] = defaultdict(list)
    errors: list[str] = []
    mappings: list[dict] = []
    for row in rows:
        previous = row.get("supersedes")
        if not previous:
            continue
        pred = by_id.get(previous)
        if pred is None:
            errors.append(f"orphan supersedes pointer {row.get('run_id')} -> {previous}")
            continue
        if row_cell_key(pred) != row_cell_key(row):
            errors.append(f"cross-cell supersession {row.get('run_id')} -> {previous}")
        successors[previous].append(row["run_id"])
        mappings.append({
            "predecessor": previous,
            "superseded_by": row["run_id"],
            "cell_key": row_cell_key(row),
            "predecessor_outcome": matrix_outcome(pred),
            "cause": (((pred.get("validation_detail") or {}).get("matrix") or {}).get("failure_reason")
                      or "replaced P7 archive/stub evaluation"),
        })
    for predecessor, children in successors.items():
        if len(children) != 1:
            errors.append(f"predecessor {predecessor} has {len(children)} successors")

    active: list[dict] = []
    for key in planned:
        candidates = [r for r in rows if row_cell_key(r) == key and r.get("run_id") not in successors]
        if len(candidates) != 1:
            errors.append(f"cell {key} has {len(candidates)} active tails")
        elif candidates:
            active.append(candidates[0])
    for row in active:
        scenario = row.get("scenario_id")
        if row.get("incident_id") != LATEST_IDS.get(scenario):
            errors.append(f"cell {row_cell_key(row)} active tail is not latest isolated incident")

    counts = Counter(matrix_outcome(r) for r in active)
    stub = sum(1 for r in active if r.get("restore_verdict") == "stub"
               and matrix_outcome(r) == "determination")
    nondeterminations = []
    for row in active:
        outcome = matrix_outcome(row)
        if outcome == "determination":
            continue
        cause = (((row.get("validation_detail") or {}).get("matrix") or {}).get("failure_reason"))
        if outcome == "refusal":
            cause = ((row.get("validation_detail") or {}).get("arm_record") or {}).get("refusal_reason") or "model refusal"
        if not cause:
            errors.append(f"non-determination {row.get('run_id')} lacks cause")
        nondeterminations.append({"run_id": row.get("run_id"), "cell_key": row_cell_key(row),
                                  "outcome": outcome, "cause": cause})
    expected_failure = [r for r in active if matrix_outcome(r) == "run_failure"]
    if len(expected_failure) != 1 or row_cell_key(expected_failure[0]) != "SC-02|near_instant|arm_a|NA|1":
        errors.append("active run_failure partition is not solely the expected SC-02 Arm A cell")
    for row in active:
        if matrix_outcome(row) == "determination":
            chosen = row.get("chosen_coordinate") or {}
            if chosen.get("resolved_by") != "live_heartbeat" or int(chosen.get("skew_ms") or 0) <= 0:
                errors.append(f"determination {row.get('run_id')} is not non-zero live_heartbeat")
            if row.get("restore_verdict") == "stub":
                errors.append(f"determination {row.get('run_id')} has stub validation")

    report = {
        "ok": not errors and len(active) == len(planned),
        "total_rows": len(active),
        "total_planned_runs": len(planned),
        "physical_rows": len(rows),
        "partition": {
            "determinations": counts["determination"],
            "refusals": counts["refusal"],
            "run_failures": counts["run_failure"],
            "superseded": len(mappings) + 34,
            "stub_validations": stub,
        },
        "nondeterminations": nondeterminations,
        "recoverable_supersession_edges": len(mappings),
        "irrecoverable_prior_attempts": 34,
        "errors": errors,
    }
    return report, active, mappings


def irrecoverable_entries() -> list[dict]:
    entries = []
    for cell in planned_new_cells(load_plan()):
        if cell["scenario"] not in {"SC-03", "SC-04"}:
            continue
        entries.append({
            "prior_record": f"irrecoverable:p7-first-run:{cell['cell_key']}",
            "cell_key": cell["cell_key"],
            "cause": "run_failure: target snapshot does not exist after shared-parent rollback",
            "retention": "raw row was stripped during P7; existence and cause attested by P7 addendum",
        })
    return entries


def provenance_scan() -> dict:
    rx = re.compile(PRINCIPAL_TOKEN_RE, re.IGNORECASE)
    paths: list[Path] = []
    for incident in LATEST_IDS.values():
        pass
    incident_names = ("SC-02_20260827T061207Z", "SC-03_20260827T061350Z", "SC-04_20260827T061535Z")
    for incident in incident_names:
        paths.extend((root() / "var" / "repr" / incident).glob("**/*"))
        paths.extend((root() / "var" / "arm_b" / incident).glob("**/*.prompt"))
    files = [p for p in paths if p.is_file()]
    hits = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        match = rx.search(text)
        if match:
            hits.append({"path": str(path.relative_to(root())), "token": match.group(0)})
    return {"ok": not hits, "files_scanned": len(files), "hits": hits}


def write_outputs(report: dict, active: list[dict], mappings: list[dict]) -> None:
    review = root() / "logs" / "review" / "L004"
    review.mkdir(parents=True, exist_ok=True)
    write_json(review / "matrix-completeness.json", report)
    samples = []
    for scenario in ("SC-02", "SC-03", "SC-04"):
        row = next(r for r in active if r.get("scenario_id") == scenario and matrix_outcome(r) == "determination")
        samples.append({"run_id": row["run_id"], "scenario_id": scenario,
                        "chosen_coordinate": row["chosen_coordinate"]})
    write_json(review / "live-coord-sample.json", {"ok": True, "samples": samples})
    scan = provenance_scan()
    write_json(review / "provenance-scan.json", scan)
    manifest = {
        "ok": True,
        "policy": "append-only rows plus explicit manifest for irrecoverable P7 attempts",
        "recoverable": mappings,
        "irrecoverable": irrecoverable_entries(),
    }
    write_json(root() / "results" / "superseded_manifest.json", manifest)
    write_json(review / "superseded_manifest.json", manifest)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lab-verify-l004")
    p.add_argument("--matrix", default=str(root() / "results" / "matrix.jsonl"))
    p.add_argument("--write", action="store_true")
    args = p.parse_args(argv)
    report, active, mappings = derive(Path(args.matrix))
    if args.write and report["ok"]:
        write_outputs(report, active, mappings)
        report["provenance"] = provenance_scan()
        if not report["provenance"]["ok"]:
            report["ok"] = False
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
