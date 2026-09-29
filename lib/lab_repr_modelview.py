"""Project lab-repr-query onto model_view / reference. Do not modify lab_repr_query."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from lab_p3_util import EXIT_ASSERT, EXIT_USAGE, die
from lab_paths import lab_root
from lab_repr import PROBE_IDS, REPR_IDS, probe_params_for

MODEL_VIEW_KEYS = (
    "content",
    "incident_id",
    "params",
    "probe_id",
    "representation",
    "telemetry",
)
REFERENCE_KEYS = ("answer", "incident_id", "probe_id", "representation")


def probe_params(probe: str) -> dict:
    if probe == "PB-1-window-events":
        return {"window_index": 15}
    if probe in {"PB-3-entity-churn", "PB-6-candidate-windows"}:
        return {"top_n": 3}
    if probe == "PB-5-entity-activity":
        return {"entity": "p2_probe"}
    return {}


def project_model_view(payload: dict, params: dict) -> dict:
    return {
        "content": payload["content"],
        "incident_id": payload["incident_id"],
        "params": params,
        "probe_id": payload["probe_id"],
        "representation": payload["representation"],
        "telemetry": payload["telemetry"],
    }


def project_reference(payload: dict) -> dict:
    return {
        "answer": payload["answer"],
        "incident_id": payload["incident_id"],
        "probe_id": payload["probe_id"],
        "representation": payload["representation"],
    }


def _run_query(incident: str, representation: str, probe: str, params: dict) -> dict:
    root = lab_root()
    argv = [
        str(root / "bin" / "lab-repr-query"),
        "--incident", incident,
        "--representation", representation,
        "--probe", probe,
        "--params", json.dumps(params, sort_keys=True, separators=(",", ":")),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(argv, cwd=str(root), text=True, capture_output=True, check=False, env=env)
    if proc.returncode != 0:
        die(proc.returncode if proc.returncode in {1, 2, 3} else EXIT_ASSERT,
            proc.stderr.strip() or proc.stdout.strip() or "lab-repr-query failed")
    return json.loads(proc.stdout)


def model_view(incident: str, representation: str, probe: str, params: dict | None = None) -> dict:
    params = dict(params) if params is not None else probe_params_for(incident, probe)
    payload = _run_query(incident, representation, probe, params)
    return project_model_view(payload, params)


def reference(incident: str, representation: str, probe: str, params: dict | None = None) -> dict:
    params = dict(params) if params is not None else probe_params_for(incident, probe)
    payload = _run_query(incident, representation, probe, params)
    return project_reference(payload)


def emit(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"


def _parse_argv(argv: list[str]) -> tuple[str, str, str, dict]:
    if len(argv) < 3:
        die(EXIT_USAGE, "usage: <incident> <representation> <probe> [params-json]")
    incident, representation, probe = argv[0], argv[1], argv[2]
    if probe not in PROBE_IDS:
        die(EXIT_USAGE, f"unknown probe {probe!r}")
    if representation not in REPR_IDS:
        die(EXIT_USAGE, f"unknown representation {representation!r}")
    if len(argv) >= 4:
        params = json.loads(argv[3])
        if not isinstance(params, dict):
            die(EXIT_USAGE, "usage: params must be a JSON object")
    else:
        params = probe_params_for(incident, probe)
    return incident, representation, probe, params


def main_modelview(argv: list[str]) -> int:
    incident, representation, probe, params = _parse_argv(argv)
    sys.stdout.write(emit(model_view(incident, representation, probe, params)))
    return 0


def main_reference(argv: list[str]) -> int:
    incident, representation, probe, params = _parse_argv(argv)
    sys.stdout.write(emit(reference(incident, representation, probe, params)))
    return 0


IGNORED_MODELVIEW = frozenset({"content", "telemetry"})


def _skeleton(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _skeleton(v) if k not in IGNORED_MODELVIEW else type(v).__name__ for k, v in obj.items()}
    if isinstance(obj, list):
        return [_skeleton(obj[0])] if obj else []
    return type(obj).__name__


def _diff(a: object, b: object, path: str = "") -> list[str]:
    diffs = []
    if type(a) is not type(b):
        return [f"{path}: type {type(a).__name__} vs {type(b).__name__}"]
    if isinstance(a, dict):
        if set(a) != set(b):
            diffs.append(f"{path}: keys {sorted(set(a) ^ set(b))}")
        for k in sorted(set(a) & set(b)):
            diffs.extend(_diff(a[k], b[k], f"{path}.{k}" if path else k))
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{path}: len {len(a)} vs {len(b)}")
        elif a:
            diffs.extend(_diff(a[0], b[0], f"{path}[]"))
    elif a != b:
        diffs.append(f"{path}: {a!r} vs {b!r}")
    return diffs


def parity_modelview(incident: str) -> dict:
    rows = []
    ok = True
    for probe in PROBE_IDS:
        params = probe_params(probe)
        views = {rep: model_view(incident, rep, probe, params) for rep in REPR_IDS}
        skel = {rep: _skeleton(views[rep]) for rep in REPR_IDS}
        diffs = _diff(skel["R0"], skel["R1"]) + _diff(skel["R0"], skel["R2"])
        for rep in REPR_IDS:
            extra = sorted(set(views[rep]) - set(MODEL_VIEW_KEYS))
            if extra:
                diffs.append(f"{rep}: extra keys {extra}")
            if "answer" in views[rep] or "reference" in views[rep]:
                diffs.append(f"{rep}: answer/reference present")
        match = not diffs
        ok = ok and match
        rows.append({
            "probe_id": probe,
            "structural_match": match,
            "ignored_fields": sorted(IGNORED_MODELVIEW),
            "diffs": diffs,
        })
    return {
        "ok": ok,
        "incident": incident,
        "ignored_fields": sorted(IGNORED_MODELVIEW),
        "probes": rows,
    }


if __name__ == "__main__":
    die(EXIT_USAGE, "use bin/lab-repr-modelview or bin/lab-repr-reference")
