"""lab-repr-parity: structural identity of the query envelope across R0/R1/R2."""
from __future__ import annotations

import json
from copy import deepcopy

from lab_p3_util import EXIT_ASSERT, die
from lab_repr import PROBE_IDS, REPR_IDS, probe_params_for
from lab_repr_query import query

IGNORED = frozenset({"content", "telemetry"})


def _skeleton(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _skeleton(v) if k not in IGNORED else type(v).__name__ for k, v in obj.items()}
    if isinstance(obj, list):
        if not obj:
            return []
        # Compare list-of-dict schema via first element + length type.
        return [_skeleton(obj[0])]
    return type(obj).__name__


def _params(probe: str) -> dict:
    if probe == "PB-1-window-events":
        return {"window_index": 15}
    if probe in {"PB-3-entity-churn", "PB-6-candidate-windows"}:
        return {"top_n": 3}
    if probe == "PB-5-entity-activity":
        return {"entity": "p2_probe"}
    return {}


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


def parity(incident: str) -> dict:
    rows = []
    ok = True
    for probe in PROBE_IDS:
        params = probe_params_for(incident, probe)
        payloads = {rep: query(incident, rep, probe, params) for rep in REPR_IDS}
        skel = {rep: _skeleton(payloads[rep]) for rep in REPR_IDS}
        diffs = _diff(skel["R0"], skel["R1"]) + _diff(skel["R0"], skel["R2"])
        # Answers themselves (not just types) must match.
        ans_ok = payloads["R0"]["answer"] == payloads["R1"]["answer"] == payloads["R2"]["answer"]
        if not ans_ok:
            diffs.append("answer values differ")
        match = not diffs
        ok = ok and match
        rows.append({
            "probe_id": probe,
            "structural_match": match,
            "ignored_fields": sorted(IGNORED),
            "diffs": diffs,
        })
    available = {rep: list(PROBE_IDS) for rep in REPR_IDS}
    return {
        "ok": ok,
        "incident": incident,
        "ignored_fields": sorted(IGNORED),
        "probes": rows,
        "availability": available,
    }


def main(argv: list[str]) -> int:
    if not argv:
        die(3, "usage: lab-repr-parity <incident>")
    rec = parity(argv[0])
    print(json.dumps(rec, indent=2, sort_keys=True))
    return 0 if rec["ok"] else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
