"""P5 shared representation helpers: blind events, windows, manifests, scans."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from lab_ledger_account import col_map, map_ops, rec_key
from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, canonical_json, die, load_jsonl,
    write_json, write_text,
)
from lab_paths import env, evidence_dir, lab_root
from lsn import lsn_int, lsn_norm
from provenance_fields import KEYS

HEADLINE = "SC-01_20260824T091611Z"
ANOMALY_THRESHOLD = 3.0
BLIND_VIEW = "views.analysis_view"
BLIND_VIEW_SQL = "db_changes"
PRINCIPAL_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(principal|usename|session_user|originating_uid|user_id|uid)(?![A-Za-z0-9_])",
    re.I,
)
ROLE_TOKEN_RE = re.compile(r"\b(lab_app|lab_agent)\b")
MANIFEST_FIELDS = (
    "incident_id", "representation", "builder_version", "source_ledger_hash",
    "content_hash", "event_count", "ledger_event_count", "reconciles",
    "provenance_blind", "built_by_model",
)
PROBE_IDS = (
    "PB-1-window-events",
    "PB-2-deletion-density",
    "PB-3-entity-churn",
    "PB-4-earliest-anomaly",
    "PB-5-entity-activity",
    "PB-6-candidate-windows",
)
REPR_IDS = ("R0", "R1", "R2")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def strip_keys(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: strip_keys(v) for k, v in obj.items() if k not in KEYS}
    if isinstance(obj, list):
        return [strip_keys(v) for v in obj]
    return obj


def parse_ts(ts: str) -> datetime:
    text = ts.replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    return datetime.fromisoformat(text)


def iso_utc(ts: str) -> str:
    dt = parse_ts(ts).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def token_scan(text: str, roles: bool = False) -> list[str]:
    hits = [m.group(0) for m in PRINCIPAL_TOKEN_RE.finditer(text)]
    if roles:
        hits.extend(m.group(0) for m in ROLE_TOKEN_RE.finditer(text))
    return hits


def structured_principal(obj: object, path: str = "") -> list[str]:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else k
            if k.lower() in KEYS or k.lower() in {"principal", "usename", "session_user", "uid"}:
                found.append(here)
            found.extend(structured_principal(v, here))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(structured_principal(item, f"{path}[{i}]"))
    elif isinstance(obj, str):
        if token_scan(obj):
            found.append(path or obj)
    return found


def repr_root(incident: str, dest: Path | None = None) -> Path:
    if dest is not None:
        return dest
    override = os.environ.get("LAB_REPR_ROOT")
    if override:
        return Path(override) / incident
    return lab_root() / "var" / "repr" / incident


def repr_dir(incident: str, name: str, dest: Path | None = None) -> Path:
    path = repr_root(incident, dest) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def require_reconciled(incident: str) -> dict:
    from lab_ledger_account import main as account_main
    # Re-run accounting in-process via the same functions.
    ed = evidence_dir(incident)
    ops = [strip_keys(r) for r in load_jsonl(ed / "workload.jsonl")]
    ledger = load_jsonl(ed / "db.jsonl")
    coverage = map_ops(ops, ledger)
    if coverage["mapped"] != coverage["ops"] or coverage["gaps"] or coverage["duplicates"]:
        die(EXIT_PRECOND,
            f"precondition failed: ledger not reconciled gaps={len(coverage['gaps'])} "
            f"dups={len(coverage['duplicates'])}")
    return coverage


def load_blind_events(incident: str) -> tuple[list[dict], str]:
    """Serialize the reconciled, provenance-blind mapped ledger events."""
    ed = evidence_dir(incident)
    ops = [strip_keys(r) for r in load_jsonl(ed / "workload.jsonl")]
    ledger = load_jsonl(ed / "db.jsonl")
    coverage = map_ops(ops, ledger)
    if coverage["mapped"] != coverage["ops"] or coverage["gaps"] or coverage["duplicates"]:
        die(EXIT_PRECOND, "precondition failed: ledger not reconciled")
    from collections import defaultdict
    unused: dict[tuple, list[int]] = defaultdict(list)
    for i, rec in enumerate(ledger):
        k = rec_key(rec)
        if k is not None:
            unused[k].append(i)
    events = []
    for rec_map in coverage["mapping"]:
        k = tuple(rec_map["key"])
        queue = unused.get(k) or []
        if not queue:
            die(EXIT_ASSERT, f"assertion failed: mapping key vanished {k!r}")
        rec = ledger[queue.pop(0)]
        events.append(event_from_record(rec, rec_map["key"]))
    events.sort(key=lambda e: (e["lsn_int"], e["xid"], e["object"], e["action"], str(e["natural_key"])))
    source_hash = sha256_file(ed / "db.jsonl")
    return events, source_hash


def event_from_record(rec: dict, key: list) -> dict:
    kind = key[0]
    lsn = lsn_norm(rec["lsn"])
    ts = rec.get("timestamp") or rec.get("wall_clock") or ""
    if kind == "DML":
        _, xid, table, action, kid = key
        cols = col_map(rec, "columns")
        ident = col_map(rec, "identity")
        detail = {}
        for src in (ident, cols):
            for k, v in src.items():
                if k.lower() in KEYS:
                    continue
                detail[k] = v
        return {
            "lsn_int": lsn_int(lsn),
            "lsn_text": lsn,
            "wall_clock": iso_utc(str(ts)) if ts else "",
            "action": action,
            "object": table,
            "natural_key": kid,
            "xid": int(xid),
            "detail": dict(sorted(detail.items())),
        }
    _, xid, tag, ident = key
    return {
        "lsn_int": lsn_int(lsn),
        "lsn_text": lsn,
        "wall_clock": iso_utc(str(ts)) if ts else "",
        "action": tag,
        "object": ident,
        "natural_key": ident,
        "xid": int(xid),
        "detail": {"command_tag": tag, "object_identity": ident},
    }


def load_c5_windows(incident: str) -> list[dict]:
    path = evidence_dir(incident) / "p3" / "anomaly.jsonl"
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: C5 anomaly.jsonl missing at {path}")
    rows = load_jsonl(path)
    rows.sort(key=lambda r: int(r["window_id"]))
    return rows


def pb1_window_index(incident: str) -> int:
    """PB-1's default window. SC-01 keeps 15 (the headline anomaly); other
    incidents use a window that actually exists so F006 reuse does not crash."""
    ids = [int(w["window_id"]) for w in load_c5_windows(incident)]
    if not ids:
        die(EXIT_PRECOND, "precondition failed: no C5 windows")
    if 15 in ids:
        return 15
    pos = [i for i in ids if i >= 0]
    return pos[0] if pos else ids[0]


def probe_params_for(incident: str, probe: str) -> dict:
    if probe == "PB-1-window-events":
        return {"window_index": pb1_window_index(incident)}
    if probe in {"PB-3-entity-churn", "PB-6-candidate-windows"}:
        return {"top_n": 3}
    if probe == "PB-5-entity-activity":
        return {"entity": "p2_probe"}
    return {}


def windowing_params(incident: str) -> dict:
    from lab_p3_util import scenario_config
    cfg = scenario_config()
    windows = load_c5_windows(incident)
    origin = windows[0]["t_start"] if windows else None
    return {
        "window_s": int(cfg.get("SC01_WINDOW_S", "2")),
        "origin_ts": origin,
        "analytics_version": windows[0].get("analytics_version") if windows else None,
        "n_windows": len(windows),
    }


def assign_window(event: dict, windows: list[dict], window_s: int) -> int | None:
    ts = event.get("wall_clock")
    if ts and windows:
        t0 = parse_ts(windows[0]["t_start"])
        idx = int((parse_ts(ts) - t0).total_seconds() // window_s)
        ids = {int(w["window_id"]) for w in windows}
        if idx in ids:
            return idx
        # Clip to the last declared window rather than dropping the event.
        if idx > max(ids):
            return max(ids)
        if idx < min(ids):
            return min(ids)
    n = int(event["lsn_int"])
    for w in windows:
        lo, hi = w.get("lsn_start_int"), w.get("lsn_end_int")
        if lo is not None and hi is not None and lo <= n <= hi:
            return int(w["window_id"])
    return None


def events_by_window(events: list[dict], windows: list[dict], window_s: int) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {int(w["window_id"]): [] for w in windows}
    unassigned = []
    for ev in events:
        idx = assign_window(ev, windows, window_s)
        if idx is None:
            unassigned.append(ev)
        else:
            out.setdefault(idx, []).append(ev)
    if unassigned:
        die(EXIT_ASSERT, f"assertion failed: {len(unassigned)} events not assigned to a window")
    return out


def fidelity_manifest(
    incident: str,
    representation: str,
    builder_version: str,
    source_ledger_hash: str,
    content_hash: str,
    event_count: int,
    ledger_event_count: int,
    reconciles: bool,
    provenance_blind: bool,
    extra: dict | None = None,
) -> dict:
    rec = {
        "incident_id": incident,
        "representation": representation,
        "builder_version": builder_version,
        "source_ledger_hash": source_ledger_hash,
        "content_hash": content_hash,
        "event_count": int(event_count),
        "ledger_event_count": int(ledger_event_count),
        "reconciles": bool(reconciles),
        "provenance_blind": bool(provenance_blind),
        "built_by_model": False,
    }
    if extra:
        rec.update(extra)
    return rec


def artefact_blind(paths: list[Path]) -> tuple[bool, list[str]]:
    hits = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        hits.extend(f"{path}:{h}" for h in token_scan(text, roles=True))
        try:
            if path.suffix == ".json":
                hits.extend(f"{path}:{h}" for h in structured_principal(json.loads(text)))
            elif path.suffix == ".jsonl":
                for i, line in enumerate(text.splitlines()):
                    if line.strip():
                        hits.extend(f"{path}:{i}:{h}" for h in structured_principal(json.loads(line)))
        except json.JSONDecodeError:
            pass
    return (not hits), hits


def write_0444(path: Path, text: str) -> None:
    write_text(path, text if text.endswith("\n") else text + "\n", 0o444)


def write_jsonl_0444(path: Path, rows: list[dict]) -> str:
    text = "".join(canonical_json(r) + "\n" for r in rows)
    write_0444(path, text)
    return sha256_text(text)


def write_json_0444(path: Path, obj: object) -> str:
    text = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    write_0444(path, text)
    return sha256_text(text)


def maybe_unchanged(path: Path, digest: str) -> bool:
    return path.is_file() and sha256_file(path) == digest


def load_r0(incident: str, dest: Path | None = None) -> tuple[list[dict], dict]:
    d = repr_dir(incident, "R0", dest)
    events = load_jsonl(d / "events.jsonl")
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    return events, manifest


def load_r1(incident: str, dest: Path | None = None) -> tuple[list[dict], dict]:
    d = repr_dir(incident, "R1", dest)
    windows = load_jsonl(d / "windows.jsonl")
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    return windows, manifest


def load_r2(incident: str, dest: Path | None = None) -> tuple[dict, list[dict], dict]:
    d = repr_dir(incident, "R2", dest)
    graph = json.loads((d / "graph.json").read_text(encoding="utf-8"))
    summaries = load_jsonl(d / "summaries.jsonl")
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    return graph, summaries, manifest


def emit(obj: dict) -> None:
    print(json.dumps(obj, sort_keys=True))


def parse_incident(argv: list[str]) -> tuple[str, Path | None]:
    dest = None
    incident = None
    i = 0
    while i < len(argv):
        if argv[i] in {"--dest", "--out"} and i + 1 < len(argv):
            dest = Path(argv[i + 1])
            i += 2
            continue
        if incident is None and not argv[i].startswith("--"):
            incident = argv[i]
            i += 1
            continue
        die(EXIT_USAGE, "usage: <incident> [--dest DIR]")
    if not incident:
        die(EXIT_USAGE, "usage: <incident> [--dest DIR]")
    return incident, dest
