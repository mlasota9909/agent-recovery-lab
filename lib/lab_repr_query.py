"""lab-repr-query: identical probe interface over R0/R1/R2. Read-only. No model."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, canonical_json, die
from lab_repr import (
    ANOMALY_THRESHOLD, PROBE_IDS, REPR_IDS, emit, events_by_window, load_c5_windows,
    load_r0, load_r1, load_r2, token_scan, windowing_params,
)
from lab_tokenize import telemetry_for

ENVELOPE_KEYS = (
    "incident_id", "representation", "probe_id", "answer", "content", "telemetry",
)


def _load_facts(incident: str) -> dict:
    events, r0 = load_r0(incident)
    windows, r1 = load_r1(incident)
    graph, summaries, r2 = load_r2(incident)
    c5 = load_c5_windows(incident)
    params = windowing_params(incident)
    grouped = events_by_window(events, c5, params["window_s"])
    return {
        "events": events, "windows": windows, "graph": graph, "summaries": summaries,
        "grouped": grouped, "r0": r0, "r1": r1, "r2": r2,
    }


def _win(facts: dict, idx: int) -> dict:
    for w in facts["windows"]:
        if int(w["window_index"]) == int(idx):
            return w
    die(EXIT_ASSERT, f"assertion failed: unknown window_index {idx}")
    return {}


def _earliest_anomaly(facts: dict) -> dict:
    anomalous = [w for w in facts["windows"] if float(w["anomaly_score"]) >= ANOMALY_THRESHOLD]
    if anomalous:
        return min(anomalous, key=lambda w: int(w["window_index"]))
    # Contract R2: every probe must still answer. SC-01 always has a 3σ hit so
    # this branch is new-scenario only; Arm A (lab-rank) still refuses.
    if not facts["windows"]:
        die(EXIT_ASSERT, "assertion failed: no anomalous window")
    return max(
        facts["windows"],
        key=lambda w: (float(w["anomaly_score"]), -int(w["window_index"])),
    )


def _entity_counts(facts: dict) -> list[dict]:
    counts: Counter[str] = Counter()
    kinds: dict[str, str] = {}
    for e in facts["events"]:
        action = e["action"]
        if action in {"I", "U", "D"}:
            counts[e["object"]] += 1
            kinds[e["object"]] = "relation"
        else:
            counts[e["object"]] += 1
            kinds[e["object"]] = "relation" if "." in str(e["object"]) else "file"
    rows = [
        {"entity": ent, "kind": kinds[ent], "change_count": n}
        for ent, n in counts.items()
    ]
    rows.sort(key=lambda r: (-int(r["change_count"]), r["kind"], r["entity"]))
    return rows


def _last_safe(facts: dict, window_index: int) -> int:
    prev = [w for w in facts["windows"] if int(w["window_index"]) < int(window_index)]
    if prev:
        return int(max(prev, key=lambda w: int(w["window_index"]))["last_lsn_int"])
    w = _win(facts, window_index)
    return int(w["first_lsn_int"]) - 1


def _answer(probe_id: str, params: dict, facts: dict) -> dict:
    if probe_id == "PB-1-window-events":
        if "window_index" not in params:
            die(EXIT_USAGE, "usage: PB-1-window-events requires params.window_index")
        idx = int(params["window_index"])
        w = _win(facts, idx)
        return {
            "window_index": idx,
            "event_count": int(w["event_count"]),
            "first_lsn_int": int(w["first_lsn_int"]),
            "last_lsn_int": int(w["last_lsn_int"]),
        }
    if probe_id == "PB-2-deletion-density":
        rows = [
            {
                "window_index": int(w["window_index"]),
                "delete_count": int(w["delete_count"]),
                "anomaly_score": float(w["anomaly_score"]),
            }
            for w in facts["windows"]
        ]
        rows.sort(key=lambda r: int(r["window_index"]))
        return {"windows": rows}
    if probe_id == "PB-3-entity-churn":
        top_n = int(params.get("top_n", 5))
        return {"entities": _entity_counts(facts)[:top_n]}
    if probe_id == "PB-4-earliest-anomaly":
        w = _earliest_anomaly(facts)
        return {
            "window_index": int(w["window_index"]),
            "first_lsn_int": int(w["first_lsn_int"]),
            "last_lsn_int": int(w["last_lsn_int"]),
            "anomaly_score": float(w["anomaly_score"]),
        }
    if probe_id == "PB-5-entity-activity":
        if "entity" not in params:
            die(EXIT_USAGE, "usage: PB-5-entity-activity requires params.entity")
        entity = str(params["entity"])
        matching = [e for e in facts["events"] if str(e["object"]) == entity]
        if not matching:
            return {
                "entity": entity, "kind": "relation", "change_count": 0,
                "first_lsn_int": 0, "last_lsn_int": 0,
            }
        kind = "relation"
        return {
            "entity": entity,
            "kind": kind,
            "change_count": len(matching),
            "first_lsn_int": int(min(e["lsn_int"] for e in matching)),
            "last_lsn_int": int(max(e["lsn_int"] for e in matching)),
        }
    if probe_id == "PB-6-candidate-windows":
        top_n = int(params.get("top_n", 3))
        ranked = sorted(
            facts["windows"],
            key=lambda w: (-float(w["anomaly_score"]), int(w["window_index"])),
        )[:top_n]
        return {
            "candidates": [
                {
                    "window_index": int(w["window_index"]),
                    "last_safe_lsn_int": _last_safe(facts, int(w["window_index"])),
                    "anomaly_score": float(w["anomaly_score"]),
                }
                for w in ranked
            ]
        }
    die(EXIT_USAGE, f"unknown probe_id {probe_id!r}; expected one of {PROBE_IDS}")
    return {}


def _content(representation: str, probe_id: str, params: dict, facts: dict, answer: dict) -> str:
    if representation == "R0":
        return _content_r0(probe_id, params, facts, answer)
    if representation == "R1":
        return _content_r1(probe_id, params, facts, answer)
    return _content_r2(probe_id, params, facts, answer)


def _events_for_window(facts: dict, idx: int) -> list[dict]:
    return list(facts["grouped"].get(int(idx), []))


def _content_r0(probe_id: str, params: dict, facts: dict, answer: dict) -> str:
    if probe_id == "PB-1-window-events":
        rows = _events_for_window(facts, int(answer["window_index"]))
    elif probe_id == "PB-2-deletion-density":
        rows = [e for e in facts["events"] if e["action"] == "D"]
    elif probe_id == "PB-3-entity-churn":
        keep = {r["entity"] for r in answer["entities"]}
        rows = [e for e in facts["events"] if e["object"] in keep]
    elif probe_id == "PB-4-earliest-anomaly":
        rows = _events_for_window(facts, int(answer["window_index"]))
    elif probe_id == "PB-5-entity-activity":
        rows = [e for e in facts["events"] if str(e["object"]) == str(answer["entity"])]
    else:
        idxs = [int(c["window_index"]) for c in answer["candidates"]]
        rows = [e for idx in idxs for e in _events_for_window(facts, idx)]
    return "".join(canonical_json(r) + "\n" for r in rows)


def _content_r1(probe_id: str, params: dict, facts: dict, answer: dict) -> str:
    if probe_id == "PB-1-window-events":
        rows = [_win(facts, int(answer["window_index"]))]
    elif probe_id == "PB-2-deletion-density":
        rows = [
            {k: w[k] for k in ("window_index", "delete_count", "anomaly_score", "event_count")}
            for w in facts["windows"]
        ]
    elif probe_id == "PB-3-entity-churn":
        rows = list(answer["entities"])
    elif probe_id == "PB-4-earliest-anomaly":
        w = _win(facts, int(answer["window_index"]))
        rows = [{k: w[k] for k in ("window_index", "first_lsn_int", "last_lsn_int",
                                   "delete_count", "anomaly_score", "event_count")}]
    elif probe_id == "PB-5-entity-activity":
        rows = [answer]
    else:
        rows = list(answer["candidates"])
    return "".join(canonical_json(r) + "\n" for r in rows)


def _content_r2(probe_id: str, params: dict, facts: dict, answer: dict) -> str:
    summaries = facts["summaries"]
    if probe_id in {"PB-1-window-events", "PB-4-earliest-anomaly"}:
        idx = int(answer["window_index"])
        rows = [s for s in summaries if s.get("kind") == "window" and int(s["window_index"]) == idx]
        # Include the immediately prior window for context (still tiny vs R0).
        prev = [s for s in summaries if s.get("kind") == "window" and int(s["window_index"]) == idx - 1]
        rows = prev + rows
    elif probe_id == "PB-2-deletion-density":
        rows = [s for s in summaries if s.get("kind") == "window"]
    elif probe_id in {"PB-3-entity-churn", "PB-5-entity-activity"}:
        keep = {answer["entity"]} if probe_id == "PB-5-entity-activity" else {r["entity"] for r in answer["entities"]}
        rows = [s for s in summaries if s.get("kind") == "entity" and s.get("entity") in keep]
    else:
        idxs = {int(c["window_index"]) for c in answer["candidates"]}
        rows = [s for s in summaries if s.get("kind") == "window" and int(s["window_index"]) in idxs]
    return "\n".join(s["text"] for s in rows) + ("\n" if rows else "")


def query(incident: str, representation: str, probe_id: str, params: dict | None = None) -> dict:
    if representation not in REPR_IDS:
        die(EXIT_USAGE, f"unknown representation {representation!r}; expected R0/R1/R2")
    if probe_id not in PROBE_IDS:
        die(EXIT_USAGE, f"unknown probe_id {probe_id!r}; expected one of {list(PROBE_IDS)}")
    params = params or {}
    facts = _load_facts(incident)
    answer = _answer(probe_id, params, facts)
    content = _content(representation, probe_id, params, facts, answer)
    hits = token_scan(content, roles=True) + token_scan(canonical_json(answer), roles=True)
    if hits:
        die(EXIT_ASSERT, f"assertion failed: provenance token in response {hits[:5]}")
    payload = {
        "incident_id": incident,
        "representation": representation,
        "probe_id": probe_id,
        "answer": answer,
        "content": content,
        "telemetry": telemetry_for(content),
    }
    return payload


def response_bytes(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"


def main(argv: list[str]) -> int:
    incident = None
    representation = None
    probe_id = None
    params: dict = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in {"--incident", "-i"} and i + 1 < len(argv):
            incident = argv[i + 1]; i += 2; continue
        if a in {"--representation", "-r"} and i + 1 < len(argv):
            representation = argv[i + 1]; i += 2; continue
        if a in {"--probe", "--probe-id", "-p"} and i + 1 < len(argv):
            probe_id = argv[i + 1]; i += 2; continue
        if a == "--params" and i + 1 < len(argv):
            params = json.loads(argv[i + 1]); i += 2; continue
        die(EXIT_USAGE, "usage: lab-repr-query --incident ID --representation R0|R1|R2 --probe ID [--params JSON]")
    if not incident or not representation or not probe_id:
        die(EXIT_USAGE, "usage: lab-repr-query --incident ID --representation R0|R1|R2 --probe ID [--params JSON]")
    payload = query(incident, representation, probe_id, params)
    sys.stdout.write(response_bytes(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
