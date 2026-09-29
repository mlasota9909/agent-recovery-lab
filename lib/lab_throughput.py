"""lab-throughput: measure generate-incident and evaluate-arm after the reset guard."""
from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3

INHERITED_S = 49.335
MIN_REPEATS = 5
EVAL_TIER = "t2"
GENERATE_STEPS = ("reset", "barrier", "workload", "snapshot", "inject", "capture", "oracle")
EVALUATE_STEPS = ("reset", "barrier", "analysis", "restore", "results_append")


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def env(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        die(EXIT_PRECOND, f"precondition failed: {key} missing from lab.env")
    return v


def bin_path(name: str) -> str:
    return str(Path(os.environ["LAB_ROOT"]) / "bin" / name)


def host_conditions() -> dict:
    load1, load5, load15 = os.getloadavg()
    nproc = os.cpu_count() or 0
    return {
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "loadavg_1": load1,
        "loadavg_5": load5,
        "loadavg_15": load15,
        "nproc": nproc,
    }


def stats(values: list[float]) -> dict:
    if not values:
        die(EXIT_ASSERT, "assertion failed: no measurements")
    return {
        "n": len(values),
        "median_s": statistics.median(values),
        "min_s": min(values),
        "max_s": max(values),
        "sd_s": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


def load_doc(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "measured_post_reset_guard": True,
        "inherited_cycle_s": INHERITED_S,
        "phases": {},
        "plan": {},
        "host_conditions": [],
    }


def write_doc(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    os.chmod(path, 0o644)


def generate_step_seconds(archive_incident: str, wall_s: float) -> dict[str, float]:
    path = Path(env("EVIDENCE_ROOT")) / "SC-01" / archive_incident / "generate-commands.json"
    if not path.is_file():
        return {"remainder": wall_s}
    log = json.loads(path.read_text(encoding="utf-8"))
    marks = []
    for entry in log:
        if "elapsed_ms" in entry:
            marks.append((entry.get("action"), entry["elapsed_ms"] / 1000.0))
    buckets: dict[str, float] = {k: 0.0 for k in GENERATE_STEPS}
    prev = 0.0
    mapping = {
        "stop_postgres": "reset",
        "reset": "reset",
        "incident_new": "barrier",
        "open_coordinate": "barrier",
        "barrier": "barrier",
        "workload_start": "workload",
        "baseline_wait_s": "workload",
        "snapshot_pre_injection": "snapshot",
        "inject": "inject",
        "verify_timing": "inject",
        "workload_stop": "capture",
        "snapshot_post_capture": "capture",
        "close": "capture",
        "ledger_window": "capture",
        "ledger_verify": "capture",
        "oracle": "oracle",
    }
    if marks:
        for action, t in marks:
            dt = max(0.0, t - prev)
            bucket = mapping.get(action, "remainder")
            buckets[bucket] = buckets.get(bucket, 0.0) + dt
            prev = t
        remainder = max(0.0, wall_s - prev)
        if remainder:
            buckets["remainder"] = buckets.get("remainder", 0.0) + remainder
    else:
        buckets["remainder"] = wall_s
    return buckets


def evaluate_step_seconds(payload: dict, wall_s: float) -> dict[str, float]:
    steps_ms = payload.get("steps_ms") or {}
    buckets = {k: steps_ms.get(k, 0) / 1000.0 for k in EVALUATE_STEPS}
    accounted = sum(buckets.values())
    buckets["remainder"] = max(0.0, wall_s - accounted)
    return buckets


def latest_evaluable_incident() -> str:
    evidence = Path(env("EVIDENCE_ROOT")) / "SC-01"
    archive = Path(env("ARCHIVE_ROOT"))
    candidates = []
    for d in evidence.iterdir() if evidence.is_dir() else []:
        if not (d / "incident.json").is_file():
            continue
        snaps_path = archive / d.name / "snapshots.json"
        if not snaps_path.is_file():
            continue
        rows = json.loads(snaps_path.read_text(encoding="utf-8"))
        valid = [
            r for r in rows
            if r.get("label") == "post_capture" and not r.get("invalidated")
        ]
        if valid:
            candidates.append(d.name)
    if not candidates:
        die(EXIT_PRECOND, "precondition failed: no registered incident with a valid post_capture snapshot")
    return sorted(candidates)[-1]


def run_generate() -> dict:
    t0 = time.monotonic()
    proc = subprocess.run(
        [bin_path("lab-generate-incident"), "--scenario", "SC-01"],
        text=True, capture_output=True, check=False, env=os.environ,
    )
    wall_s = time.monotonic() - t0
    if proc.returncode != 0:
        die(
            EXIT_ASSERT,
            "assertion failed: lab-generate-incident: "
            + (proc.stderr.strip() or proc.stdout.strip()),
        )
    payload = json.loads(proc.stdout)
    archive = payload["archive_incident"]
    return {
        "archive_incident": archive,
        "incident_id": payload["incident_id"],
        "wall_s": wall_s,
        "steps_s": generate_step_seconds(archive, wall_s),
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def run_evaluate(incident: str) -> dict:
    t0 = time.monotonic()
    proc = subprocess.run(
        [bin_path("lab-evaluate-arm"), "--incident", incident, "--arm", "stub", "--tier", EVAL_TIER],
        text=True, capture_output=True, check=False, env=os.environ,
    )
    wall_s = time.monotonic() - t0
    if proc.returncode != 0:
        die(
            EXIT_ASSERT,
            "assertion failed: lab-evaluate-arm: "
            + (proc.stderr.strip() or proc.stdout.strip()),
        )
    payload = json.loads(proc.stdout)
    return {
        "archive_incident": incident,
        "incident_id": payload["incident_id"],
        "run_id": payload.get("run_id"),
        "wall_s": wall_s,
        "t_total_ms": payload.get("t_total_ms"),
        "t_to_coordinate_ms": payload.get("t_to_coordinate_ms"),
        "tier": EVAL_TIER,
        "steps_s": evaluate_step_seconds(payload, wall_s),
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def median_steps(runs: list[dict], keys: tuple[str, ...]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in list(keys) + ["remainder"]:
        vals = [r["steps_s"].get(key, 0.0) for r in runs if "steps_s" in r]
        if vals:
            out[key] = statistics.median(vals)
    return out


def step_sum_ok(runs: list[dict], rel_tol: float = 0.15, abs_tol_s: float = 5.0) -> bool:
    for run in runs:
        accounted = sum(run["steps_s"].values())
        wall = run["wall_s"]
        if not math.isclose(accounted, wall, rel_tol=rel_tol, abs_tol=abs_tol_s):
            return False
    return True


def derive_plan(doc: dict) -> dict:
    gen = doc["phases"].get("generate") or {}
    ev = doc["phases"].get("evaluate") or {}
    med_g = float(gen.get("median_s") or 0)
    med_e = float(ev.get("median_s") or 0)
    if med_g <= 0 or med_e <= 0:
        return doc.get("plan") or {}
    damage_classes_core = 2
    timing_patterns_core = 1
    incident_replicates = 5
    representations = 3
    arm_replicates = 5
    total_incidents = damage_classes_core * timing_patterns_core * incident_replicates
    total_arm_runs = total_incidents * representations * arm_replicates
    planned_s = total_incidents * med_g + total_arm_runs * med_e
    planned_hours = planned_s / 3600.0
    worst_s = total_incidents * float(gen["max_s"]) + total_arm_runs * float(ev["max_s"])
    return {
        "total_incidents": total_incidents,
        "representations": representations,
        "replicates": arm_replicates,
        "total_arm_runs": total_arm_runs,
        "planned_hours": planned_hours,
        "worst_case_hours": worst_s / 3600.0,
        "median_generate_s": med_g,
        "median_evaluate_s": med_e,
        "arithmetic": "total_arm_runs = incidents × representations × replicates",
        "core_cells": "SC-01 + SC-02, near-instant timing, R0/R1/R2",
        "inherited_cycle_s": INHERITED_S,
        "delta_generate_minus_inherited_s": med_g - INHERITED_S,
        "delta_evaluate_minus_inherited_s": med_e - INHERITED_S,
    }


def phase_record(existing: dict | None, new_runs: list[dict], keys: tuple[str, ...], extra: dict) -> dict:
    runs = list((existing or {}).get("runs") or [])
    runs.extend(new_runs)
    walls = [r["wall_s"] for r in runs]
    rec = {
        **extra,
        **stats(walls),
        "runs": runs,
        "step_medians_s": median_steps(runs, keys),
        "steps_sum_within_tolerance": step_sum_ok(new_runs),
    }
    return rec


def main(argv: list[str]) -> int:
    phase = None
    repeats = None
    i = 0
    while i < len(argv):
        if argv[i] == "--phase" and i + 1 < len(argv):
            phase = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--repeats" and i + 1 < len(argv):
            try:
                repeats = int(argv[i + 1])
            except ValueError:
                die(EXIT_USAGE, "usage: lab-throughput --phase generate|evaluate --repeats <n>")
            i += 2
            continue
        die(EXIT_USAGE, "usage: lab-throughput --phase generate|evaluate --repeats <n>")
    if phase not in {"generate", "evaluate"} or repeats is None:
        die(EXIT_USAGE, "usage: lab-throughput --phase generate|evaluate --repeats <n>")
    if repeats < 2:
        die(
            EXIT_USAGE,
            "a median requires multiple repeats; refuse --repeats 1 "
            f"(minimum {MIN_REPEATS})",
        )
    if repeats < MIN_REPEATS:
        die(EXIT_USAGE, f"usage: --repeats must be >= {MIN_REPEATS} (a single measurement is not a measurement)")

    root = Path(os.environ["LAB_ROOT"])
    out_path = root / "docs" / "throughput.json"
    doc = load_doc(out_path)
    conditions = host_conditions()
    doc.setdefault("host_conditions", []).append(conditions)
    doc["measured_post_reset_guard"] = True
    doc["inherited_cycle_s"] = INHERITED_S

    new_runs: list[dict] = []
    if phase == "generate":
        for _ in range(repeats):
            new_runs.append(run_generate())
        doc.setdefault("phases", {})["generate"] = phase_record(
            doc.get("phases", {}).get("generate"), new_runs, GENERATE_STEPS, {}
        )
    else:
        incident = latest_evaluable_incident()
        for _ in range(repeats):
            new_runs.append(run_evaluate(incident))
        doc.setdefault("phases", {})["evaluate"] = phase_record(
            doc.get("phases", {}).get("evaluate"),
            new_runs,
            EVALUATE_STEPS,
            {"tier": EVAL_TIER, "archive_incident": incident},
        )

    doc["plan"] = derive_plan(doc)
    plan = doc["plan"] or {}
    for key in (
        "total_incidents",
        "total_arm_runs",
        "planned_hours",
        "median_generate_s",
        "median_evaluate_s",
        "replicates",
        "representations",
    ):
        if key in plan:
            doc[key] = plan[key]
    write_doc(out_path, doc)
    print(json.dumps({
        "ok": True,
        "changed": True,
        "phase": phase,
        "repeats_this_invocation": repeats,
        "runs_recorded": len((doc["phases"].get(phase) or {}).get("runs") or []),
        "median_s": (doc["phases"].get(phase) or {}).get("median_s"),
        "min_s": (doc["phases"].get(phase) or {}).get("min_s"),
        "max_s": (doc["phases"].get(phase) or {}).get("max_s"),
        "sd_s": (doc["phases"].get(phase) or {}).get("sd_s"),
        "measured_post_reset_guard": True,
        "throughput_json": str(out_path),
        "plan": doc["plan"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
