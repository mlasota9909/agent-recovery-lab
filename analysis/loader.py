#!/usr/bin/env python3
"""Deterministic active-tail loader and guarded comparison view for P8."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from lab_p71_l004 import derive, matrix_outcome  # noqa: E402
from lab_p7 import row_cell_key  # noqa: E402

FORBIDDEN_COMPARISON_KEYS = {
    "principal", "role", "role_name", "ground_truth_coordinate", "oracle_coordinate",
    "answer_key", "incident_open_coordinate", "incident_close_coordinate",
}
PERMITTED_COMPARISON_COLUMNS = (
    "source_row_id", "scenario", "representation", "replicate", "evidence_bytes",
    "prompt_tokens", "refusal", "verdict", "coordinate_error_bytes", "outcome",
)
SC01_HASHES = {
    "R0": "bae0027550deeb1645bfe66b51aba368603bc6a85554a73a33776b087077ad52",
    "R1": "34d8b0019927fdf9885d9d11173d453938a676df034de4d734d1194f7511d118",
    "R2": "17f04c10806df1137ca20068af9dff9a9e72dd962cfea577855cf2de2ac97f2d",
}


@dataclass(frozen=True)
class Frame:
    rows: tuple[dict, ...]
    metadata: dict

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(sorted({key for row in self.rows for key in row}))

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Iterator[dict]:
        return iter(self.rows)

    def where(self, **equal: object) -> "Frame":
        return Frame(tuple(row for row in self.rows if all(row.get(k) == v for k, v in equal.items())), self.metadata)


def _lsn_int(value: str | None) -> int | None:
    if not value or "/" not in value:
        return None
    high, low = value.split("/", 1)
    return (int(high, 16) << 32) + int(low, 16)


def _sort_key(row: dict) -> tuple:
    rep_order = {"none": 0, "R0": 1, "R1": 2, "R2": 3, "n/a": 4}
    return (row.get("scenario_id", ""), rep_order.get(row.get("representation"), 9),
            int(row.get("replicate") or 0), row_cell_key(row), row.get("run_id", ""))


def load_active(matrix_path: Path | str | None = None, injected_rows: Iterable[dict] = ()) -> Frame:
    path = Path(matrix_path or ROOT / "results/matrix.jsonl").resolve()
    fixtures = (ROOT / "results/fixtures").resolve()
    if path == fixtures or fixtures in path.parents:
        raise ValueError(f"fixtures input is forbidden: {path}")
    report, active, mappings = derive(path)
    if not report["ok"]:
        raise ValueError("active matrix invalid: " + "; ".join(report["errors"]))
    superseded_ids = {m["predecessor"] for m in mappings}
    active_ids = {row["run_id"] for row in active}
    for row in injected_rows:
        run_id = row.get("run_id")
        if run_id in superseded_ids or row.get("supersedes") or row.get("superseded_by"):
            raise ValueError(f"superseded row refused: {run_id}")
        if run_id not in active_ids:
            raise ValueError(f"non-active injected row refused: {run_id}")
    manifest = json.loads((ROOT / "results/superseded_manifest.json").read_text(encoding="utf-8"))
    metadata = {
        "validity_partition": {
            "active_total": len(active),
            "determinations": report["partition"]["determinations"],
            "refusals": report["partition"]["refusals"],
            "run_failures": report["partition"]["run_failures"],
            "superseded_excluded": report["partition"]["superseded"],
        },
        "supersession_provenance": sorted(
            list(manifest.get("recoverable") or []) + list(manifest.get("irrecoverable") or []),
            key=lambda x: (x.get("cell_key", ""), x.get("predecessor", x.get("prior_record", ""))),
        ),
        "source_row_ids": sorted(active_ids),
        "physical_rows": report["physical_rows"],
    }
    return Frame(tuple(sorted(active, key=_sort_key)), metadata)


def comparison_view(frame: Frame) -> Frame:
    for row in frame.rows:
        leaked = sorted(FORBIDDEN_COMPARISON_KEYS.intersection(row))
        # Ground-truth coordinates are expected in raw rows and are consumed only
        # here to derive an error scalar; identity/provenance fields are never expected.
        coordinate_inputs = {"ground_truth_coordinate", "oracle_coordinate", "answer_key",
                             "incident_open_coordinate", "incident_close_coordinate"}
        identity_leaks = [k for k in leaked if k not in coordinate_inputs]
        if identity_leaks:
            raise ValueError(f"forbidden comparison input columns: {identity_leaks}")
    rows = []
    for row in frame.rows:
        chosen = _lsn_int((row.get("chosen_coordinate") or {}).get("lsn"))
        ground = _lsn_int((row.get("ground_truth_coordinate") or {}).get("lsn"))
        rows.append({
            "source_row_id": row["run_id"],
            "scenario": row.get("scenario_id"),
            "representation": row.get("representation"),
            "replicate": row.get("replicate"),
            "evidence_bytes": row.get("evidence_bytes_presented"),
            "prompt_tokens": row.get("token_count"),
            "refusal": matrix_outcome(row) == "refusal",
            "verdict": row.get("restore_verdict"),
            "coordinate_error_bytes": abs(chosen - ground) if chosen is not None and ground is not None else None,
            "outcome": matrix_outcome(row),
        })
    view = Frame(tuple(rows), frame.metadata)
    if set(view.columns) != set(PERMITTED_COMPARISON_COLUMNS):
        raise ValueError(f"comparison view column drift: {view.columns}")
    return view


def load_sc01() -> Frame:
    """Load only the hash-pinned corrected J004 SC-01 supplemental batch."""
    matrix_metadata = load_active().metadata
    rows = []
    hashes = {}
    for representation in ("R0", "R1", "R2"):
        run_dir = ROOT / "logs/review/J004/runs" / representation
        source = run_dir / "replicates.json"
        observed = hashlib.sha256(source.read_bytes()).hexdigest()
        if observed != SC01_HASHES[representation]:
            raise ValueError(f"SC-01 supplemental hash mismatch: {source}")
        hashes[str(source.relative_to(ROOT))] = observed
        batch = json.loads(source.read_text(encoding="utf-8"))
        for index, record in enumerate(batch["records"]):
            result = record.get("results_row") or {}
            rows.append({
                "source_row_id": f"J004:{representation}:{index}:{record['raw_completion_sha256']}",
                "scenario": "SC-01",
                "representation": representation,
                "replicate": index + 1,
                "evidence_bytes": (run_dir / f"replicate-{index}.prompt").stat().st_size,
                "prompt_tokens": record.get("prompt_tokens"),
                "refusal": record.get("outcome") == "refusal",
                "verdict": result.get("restore_verdict") or (record.get("score") or {}).get("restore_verdict"),
                "coordinate_error_bytes": result.get("coord_error_bytes"),
                "outcome": record.get("outcome"),
            })
    metadata = dict(matrix_metadata)
    metadata["supplemental_source_hashes"] = hashes
    metadata["supplemental_source_row_ids"] = sorted(row["source_row_id"] for row in rows)
    return Frame(tuple(rows), metadata)


def report(frame: Frame) -> dict:
    return {
        "ok": len(frame) == 51,
        "row_count": len(frame),
        "physical_rows": frame.metadata["physical_rows"],
        "validity_partition": frame.metadata["validity_partition"],
        "source_row_ids": frame.metadata["source_row_ids"],
        "supersession_records": len(frame.metadata["supersession_provenance"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=ROOT / "results/matrix.jsonl")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review-dir", type=Path)
    args = parser.parse_args()
    try:
        frame = load_active(args.matrix)
        payload = report(frame)
        payload["comparison_columns"] = list(comparison_view(frame).columns)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"assertion failed: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.review_dir:
        args.review_dir.mkdir(parents=True, exist_ok=True)
        (args.review_dir / "load_active.json").write_text(
            json.dumps(report(frame), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (args.review_dir / "comparison_columns.json").write_text(
            json.dumps({"ok": True, "columns": list(comparison_view(frame).columns)}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
