"""lab-repr-r2: deterministic causal graph + template summaries. No model."""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

from lab_p3_util import EXIT_PRECOND, EXIT_USAGE, canonical_json, die, sha256_file
from lab_repr import (
    ANOMALY_THRESHOLD, artefact_blind, emit, events_by_window, fidelity_manifest,
    load_c5_windows, load_r0, load_r1, parse_incident, repr_dir, sha256_text,
    windowing_params, write_0444, write_json_0444, write_jsonl_0444,
)

BUILDER = "p5-repr-r2-2"

WINDOW_TMPL = (
    "Window {i} [{lo}..{hi}]: {n_ins} INSERT, {n_upd} UPDATE and {n_del} DELETE, most on relation {rel}; "
    "{schema}; anomaly {score}."
)
ROW_ACTIONS = {"I", "U", "D"}


def schema_changes(bucket: list[dict]) -> list[dict]:
    """Schema changes reach the change log as their command tag (CREATE TABLE, ALTER TABLE, ...)."""
    return [e for e in bucket if e.get("action") and e["action"] not in ROW_ACTIONS | {"B", "C"}]


def schema_phrase(changes: list[dict]) -> str:
    if not changes:
        return "no schema change"
    items = ", ".join(f"{e['action']} on {e['object']}" for e in changes)
    return f"{len(changes)} schema change{'s' if len(changes) > 1 else ''} ({items})"
ENTITY_TMPL = (
    "Relation {rel}: {n} changes across windows {w0}..{wk}; "
    "peak {peak} in window {pw}."
)


def _node(nid: str, ntype: str, label: str) -> dict:
    return {"id": nid, "type": ntype, "label": label}


def _edge(src: str, dst: str, etype: str) -> dict:
    return {"src": src, "dst": dst, "type": etype}


def build_graph(events: list[dict]) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add_node(nid: str, ntype: str, label: str) -> None:
        nodes[nid] = _node(nid, ntype, label)

    prev_event = None
    for i, ev in enumerate(events):
        eid = f"event:{i}"
        xid = f"txn:{ev['xid']}"
        rel = f"rel:{ev['object']}"
        row = f"row:{ev['object']}:{ev['natural_key']}"
        add_node(eid, "event", eid)
        add_node(xid, "transaction", xid)
        add_node(rel, "relation", str(ev["object"]))
        add_node(row, "row", str(ev["natural_key"]))
        edges.append(_edge(xid, rel, "modified"))
        edges.append(_edge(xid, row, "modified"))
        edges.append(_edge(eid, xid, "caused-by"))
        edges.append(_edge(row, rel, "depends-on"))
        if prev_event is not None:
            edges.append(_edge(prev_event, eid, "precedes"))
        prev_event = eid

    node_list = sorted(nodes.values(), key=lambda n: (n["type"], n["id"]))
    # Stable unique edges.
    seen = set()
    edge_list = []
    for e in edges:
        k = (e["src"], e["dst"], e["type"])
        if k not in seen:
            seen.add(k)
            edge_list.append(e)
    edge_list.sort(key=lambda e: (e["src"], e["dst"], e["type"]))
    return {"nodes": node_list, "edges": edge_list}


def dangling_edges(graph: dict) -> list[dict]:
    ids = {n["id"] for n in graph["nodes"]}
    return [e for e in graph["edges"] if e["src"] not in ids or e["dst"] not in ids]


def build_summaries(events: list[dict], r1_windows: list[dict], window_s: int, c5: list[dict]) -> list[dict]:
    grouped = events_by_window(events, c5, window_s)
    rows = []
    for w in r1_windows:
        idx = int(w["window_index"])
        bucket = grouped.get(idx, [])
        rel_counts = Counter(e["object"] for e in bucket if e["action"] in {"I", "U", "D"})
        rel = rel_counts.most_common(1)[0][0] if rel_counts else (bucket[0]["object"] if bucket else "")
        n_del = sum(1 for e in bucket if e["action"] == "D")
        n_ins = sum(1 for e in bucket if e["action"] == "I")
        n_upd = sum(1 for e in bucket if e["action"] == "U")
        ddl = schema_changes(bucket)
        score = w["anomaly_score"]
        text = WINDOW_TMPL.format(
            i=idx, lo=w["first_lsn_int"], hi=w["last_lsn_int"], n_ins=n_ins, n_upd=n_upd,
            n_del=n_del, rel=rel or "-", schema=schema_phrase(ddl), score=score,
        )
        rows.append({
            "kind": "window",
            "window_index": idx,
            "text": text,
            "n_del": n_del,
            "n_ins": n_ins,
            "n_upd": n_upd,
            "n_ddl": len(ddl),
            "n_events": len(bucket),
            "anomaly_score": score,
            "relation": rel,
        })
    by_rel: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for w in r1_windows:
        idx = int(w["window_index"])
        bucket = grouped.get(idx, [])
        counts = Counter(e["object"] for e in bucket)
        for rel, n in counts.items():
            by_rel[rel].append((idx, n))
    for rel in sorted(by_rel):
        pairs = sorted(by_rel[rel])
        total = sum(n for _, n in pairs)
        peak_w, peak_n = max(pairs, key=lambda p: (p[1], -p[0]))
        w0, wk = pairs[0][0], pairs[-1][0]
        text = ENTITY_TMPL.format(rel=rel, n=total, w0=w0, wk=wk, peak=peak_n, pw=peak_w)
        rows.append({
            "kind": "entity",
            "entity": rel,
            "entity_kind": "relation",
            "text": text,
            "n": total,
            "w0": w0,
            "wk": wk,
            "peak": peak_n,
            "peak_window": peak_w,
        })
    return rows


def reconcile_summaries(summaries: list[dict], events: list[dict], c5: list[dict], window_s: int) -> tuple[bool, list[str]]:
    grouped = events_by_window(events, c5, window_s)
    errors = []
    for s in summaries:
        if s["kind"] == "window":
            idx = int(s["window_index"])
            bucket = grouped.get(idx, [])
            actual_del = sum(1 for e in bucket if e["action"] == "D")
            actual_ins = sum(1 for e in bucket if e["action"] == "I")
            if int(s["n_del"]) != actual_del:
                errors.append(f"window {idx} n_del {s['n_del']} != {actual_del}")
            if int(s["n_ins"]) != actual_ins:
                errors.append(f"window {idx} n_ins {s['n_ins']} != {actual_ins}")
            actual_upd = sum(1 for e in bucket if e["action"] == "U")
            if int(s.get("n_upd", actual_upd)) != actual_upd:
                errors.append(f"window {idx} n_upd {s['n_upd']} != {actual_upd}")
            actual_ddl = len(schema_changes(bucket))
            if int(s.get("n_ddl", actual_ddl)) != actual_ddl:
                errors.append(f"window {idx} n_ddl {s['n_ddl']} != {actual_ddl}")
            if int(s["n_events"]) != len(bucket):
                errors.append(f"window {idx} n_events {s['n_events']} != {len(bucket)}")
        elif s["kind"] == "entity":
            actual = sum(1 for e in events if e["object"] == s["entity"])
            if int(s["n"]) != actual:
                errors.append(f"entity {s['entity']} n {s['n']} != {actual}")
    return (not errors), errors


def build_r2(incident: str, dest: Path | None = None) -> dict:
    try:
        events, r0 = load_r0(incident, dest)
        r1_windows, r1 = load_r1(incident, dest)
    except FileNotFoundError:
        die(EXIT_PRECOND, "precondition failed: R0/R1 missing")
    if not r0.get("provenance_blind") or not r0.get("reconciles"):
        die(EXIT_PRECOND, "precondition failed: R0 is not admissible")
    c5 = load_c5_windows(incident)
    params = windowing_params(incident)
    graph = build_graph(events)
    dangling = dangling_edges(graph)
    summaries = build_summaries(events, r1_windows, params["window_s"], c5)
    rec_ok, rec_err = reconcile_summaries(summaries, events, c5, params["window_s"])
    reconciles = rec_ok and not dangling and len(graph["nodes"]) > 0
    out = repr_dir(incident, "R2", dest)
    graph_path = out / "graph.json"
    sum_path = out / "summaries.jsonl"
    write_json_0444(graph_path, graph)
    write_jsonl_0444(sum_path, summaries)
    concat = graph_path.read_bytes() + sum_path.read_bytes()
    content_hash = __import__("hashlib").sha256(concat).hexdigest()
    blind, _hits = artefact_blind([graph_path, sum_path])
    manifest = fidelity_manifest(
        incident, "R2", BUILDER, r0["source_ledger_hash"], content_hash,
        event_count=len(events), ledger_event_count=int(r0["ledger_event_count"]),
        reconciles=reconciles, provenance_blind=blind,
        extra={"n_nodes": len(graph["nodes"]), "n_edges": len(graph["edges"]),
               "dangling": len(dangling), "summary_errors": rec_err},
    )
    # Keep extra diagnostic keys out of the contract-required set but they are allowed extras.
    write_json_0444(out / "manifest.json", manifest)
    return {
        "ok": True,
        "changed": False,
        "incident": incident,
        "representation": "R2",
        "event_count": len(events),
        "content_hash": content_hash,
        "reconciles": reconciles,
        "provenance_blind": blind,
        "built_by_model": False,
        "n_nodes": len(graph["nodes"]),
        "n_edges": len(graph["edges"]),
        "dangling": len(dangling),
        "graph": str(graph_path),
        "summaries": str(sum_path),
        "manifest": str(out / "manifest.json"),
    }


def main(argv: list[str]) -> int:
    incident, dest = parse_incident(argv)
    first = build_r2(incident, dest)
    second = build_r2(incident, dest)
    second["prior_content_hash"] = first["content_hash"]
    second["changed"] = False
    emit(second)
    return 0


if __name__ == "__main__":
    if not sys.argv[1:]:
        die(EXIT_USAGE, "usage: lab-repr-r2 <incident> [--dest DIR]")
    raise SystemExit(main(sys.argv[1:]))
