"""lab-scale-generate (P10 Q002): deterministic synthetic scaling of the frozen SC-01 incident.

Pads SC-01 with LEGITIMATE activity only (single-row INSERT/UPDATE transactions on the
same relation, p2_probe) so the model-visible R0 view reaches a pre-registered canonical
token target, while the true recovery point stays fixed. Construction is governed by
scale-generator.md read with scale-generator.amendment-1.md (ADR-P10-6):

* Placement is onset-blind. `draw_stream(seed, n, slots)` sees only the seed, the event
  count and the WAL-room slots of the captured ledger. It never receives the injection
  log, the oracle, or any provenance field.
* Padding goes only where the captured WAL has physical room: the unused tail of each
  WAL segment. Real records keep their bytes and LSNs; padded LSNs are unique, 8-byte
  aligned, realistically spaced and monotone in commit order, so every ledger check
  (P2.1 bijection, lab-ledger-verify unique/monotone/in-range) holds without special cases.
* Padded commits are recorded in workload-manifest.jsonl at the workload driver's next
  existing checkpoint, exactly as the driver records its own commits. No new manifest
  commit_lsn value is introduced below the injection LSN, so the oracle optimum cannot move.
* The frozen P3/P5 pipeline is run unchanged, in-process, against the padded evidence
  root. Four P3/P1 wrappers ignore EVIDENCE_ROOT overrides, so they are never invoked as
  commands here; `_guard_padded_root` refuses any pipeline step whose evidence dir is not
  under incidents/scaled/ (ADR-P10-10).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lab_p10 import (
    ANCHOR_TARGET, INCIDENT, SCALE_TARGETS, SEED, TARGET_TOLERANCE, root, scaled_root,
    sha256_file,
)
from lsn import lsn_int, lsn_norm, lsn_text_from_int

GENERATOR_VERSION = "p10-scale-gen-1"
P_INSERT = 0.25
KEY_BASE = 88000704
TAIL_MIN_ROOM = 1 << 20
RELATION = "p2_probe"
SIZE_INSERT = 0x90
SIZE_UPDATE = 0x70
SIZE_COMMIT = 0x30
COPY_FILES = (
    "incident.json", "injection.json", "injection_log.json", "snapshots.json",
    "fs_diff.tsv", "fs_hashes.tsv", "session.json", "generate-commands.json",
)
DERIVED = ("db.jsonl", "workload.jsonl", "workload-manifest.jsonl")
REPS = ("R0", "R1", "R2")


class ScaleError(SystemExit):
    pass


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise ScaleError(1)


# --- time helpers ------------------------------------------------------------------

def ts_us(text: str) -> int:
    t = text.replace("Z", "+00:00")
    if " " in t and "T" not in t:
        t = t.replace(" ", "T", 1)
    if t.endswith("+00"):
        t += ":00"
    dt = datetime.fromisoformat(t)
    return int(dt.timestamp()) * 1_000_000 + dt.microsecond


def pg_ts(us: int) -> str:
    """wal2json/PostgreSQL rendering: trailing fractional zeros trimmed, '+00' zone."""
    dt = datetime.fromtimestamp(us // 1_000_000, tz=timezone.utc)
    frac = f"{us % 1_000_000:06d}".rstrip("0")
    base = dt.strftime("%Y-%m-%d %H:%M:%S")
    return f"{base}.{frac}+00" if frac else f"{base}+00"


def dumps(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# --- the frozen real incident (read-only) -------------------------------------------

def real_evidence_dir() -> Path:
    return Path(os.environ["EVIDENCE_ROOT"]) / "SC-01" / INCIDENT


def load_real() -> dict:
    ed = real_evidence_dir()
    db_lines = (ed / "db.jsonl").read_text(encoding="utf-8").splitlines()
    wl_lines = (ed / "workload.jsonl").read_text(encoding="utf-8").splitlines()
    man_lines = (ed / "workload-manifest.jsonl").read_text(encoding="utf-8").splitlines()
    db = [json.loads(x) for x in db_lines]
    return {
        "dir": ed,
        "db_lines": db_lines, "db": db,
        "wl_lines": wl_lines, "wl": [json.loads(x) for x in wl_lines],
        "man_lines": man_lines, "man": [json.loads(x) for x in man_lines],
        "incident": json.loads((ed / "incident.json").read_text(encoding="utf-8")),
    }


def window_grid(real: dict) -> dict:
    """Same bucketing as lab_analytics: origin = first heartbeat, SC01_WINDOW_S seconds,
    trimmed after the last window holding a non-heartbeat change. Ledger-only inputs."""
    from lab_p3_util import scenario_config
    window_s = int(scenario_config().get("SC01_WINDOW_S", "2"))
    hb = os.environ.get("HEARTBEAT_TABLE", "lab_heartbeat")
    ddl = os.environ.get("DDL_AUDIT_TABLE", "lab_ddl_audit")
    hbs = [ts_us(r["timestamp"]) for r in real["db"] if r.get("action") == "I" and r.get("table") == hb]
    t0 = min(hbs)
    # lab_analytics keeps windows up to the last one holding a change OR a DDL event.
    active = [ts_us(r["timestamp"]) for r in real["db"]
              if (r.get("action") in {"I", "U", "D"} and r.get("table") not in {hb, ddl})
              or (r.get("action") == "I" and r.get("table") == ddl)]
    last_active = max((t - t0) // (window_s * 1_000_000) for t in active)
    return {"t0_us": t0, "window_s": window_s, "n_windows": int(last_active) + 1,
            "span_end_us": t0 + (int(last_active) + 1) * window_s * 1_000_000}


def ledger_groups(real: dict) -> list[dict]:
    """Consecutive real db.jsonl lines sharing one commit timestamp (file order is
    commit order), with the line index of each group's last record."""
    groups: list[dict] = []
    for i, r in enumerate(real["db"]):
        t = ts_us(r["timestamp"])
        n = lsn_int(r["lsn"])
        if groups and groups[-1]["t_us"] == t:
            g = groups[-1]
            g["last_line"] = i
            g["lsn_min"] = min(g["lsn_min"], n)
            g["lsn_max"] = max(g["lsn_max"], n)
        else:
            groups.append({"t_us": t, "last_line": i, "lsn_min": n, "lsn_max": n})
    return groups


def tail_slots(real: dict, grid: dict) -> list[dict]:
    """Slots between consecutive commit-time groups where the captured WAL has at least
    TAIL_MIN_ROOM bytes of physical room (the unused tail of a WAL segment)."""
    groups = ledger_groups(real)
    n = len(groups)
    prefix_max, m = [], -1
    for g in groups:
        m = max(m, g["lsn_max"])
        prefix_max.append(m)
    suffix_min, m = [0] * n, 1 << 62
    for i in range(n - 1, -1, -1):
        m = min(m, groups[i]["lsn_min"])
        suffix_min[i] = m
    slots = []
    for j in range(n - 1):
        lo, hi = prefix_max[j], suffix_min[j + 1]
        a = max(groups[j]["t_us"], grid["t0_us"])
        b = min(groups[j + 1]["t_us"], grid["span_end_us"])
        if b - a >= 2 and hi - lo >= TAIL_MIN_ROOM:
            slots.append({"slot": len(slots), "after_line": groups[j]["last_line"],
                          "t_lo_us": a, "t_hi_us": b, "lsn_lo": lo, "lsn_hi": hi})
    if not slots:
        fail("assertion failed: no WAL-tail slot with room for padding")
    return slots


def checkpoints(real: dict) -> list[tuple[int, str, str]]:
    cps = sorted({(ts_us(m["commit_ts"]), m["commit_ts"], lsn_norm(m["commit_lsn"])) for m in real["man"]})
    return cps


# --- onset-blind placement -----------------------------------------------------------

def draw_stream(seed: int, n: int, slots: list[dict]) -> list[dict]:
    """The first n draws of the seeded padding stream. Inputs are the seed, the count and
    the WAL-room slots only. Four rng.random() draws per event, in fixed order, so the
    padding for a smaller target is a prefix of the padding for a larger one."""
    rng = random.Random(seed)
    durs = [s["t_hi_us"] - s["t_lo_us"] - 1 for s in slots]
    total = sum(durs)
    cum, acc = [], 0
    for d in durs:
        acc += d
        cum.append(acc)
    out = []
    for i in range(n):
        u_slot, u_time, u_kind, u_target = rng.random(), rng.random(), rng.random(), rng.random()
        pick = u_slot * total
        k = 0
        while k < len(cum) - 1 and pick >= cum[k]:
            k += 1
        s = slots[k]
        t = s["t_lo_us"] + 1 + int(u_time * (s["t_hi_us"] - s["t_lo_us"] - 1))
        t = min(t, s["t_hi_us"] - 1)
        out.append({"i": i, "slot": k, "t_us": t, "u_kind": u_kind, "u_target": u_target})
    out.sort(key=lambda e: (e["t_us"], e["i"]))
    return out


# --- materialisation -----------------------------------------------------------------

def materialise(real: dict, events: list[dict], slots: list[dict]) -> dict:
    cps = checkpoints(real)
    close = real["incident"]["close_coordinate"]
    max_xid = max(int(r["xid"]) for r in real["db"])
    max_op = max(int(o["op_index"]) for o in real["wl"])
    next_lsn = {s["slot"]: s["lsn_lo"] + SIZE_COMMIT for s in slots}
    inserted: list[int] = []
    value: dict[int, str] = {}
    n_upd: dict[int, int] = {}
    per_slot: dict[int, list[str]] = {s["slot"]: [] for s in slots}
    wl_out, man_out, rows = [], [], []
    cp_i = 0
    for seq, ev in enumerate(events):
        xid = max_xid + 1 + seq
        s = slots[ev["slot"]]
        if not inserted or ev["u_kind"] < P_INSERT:
            kid = KEY_BASE + len(inserted)
            inserted.append(kid)
            action, old, new = "I", None, f"s{kid}"
            size = SIZE_INSERT
        else:
            kid = inserted[min(int(ev["u_target"] * len(inserted)), len(inserted) - 1)]
            n_upd[kid] = n_upd.get(kid, 0) + 1
            action, old, new = "U", value[kid], f"u{kid}{'a' if n_upd[kid] % 2 else 'b'}"
            size = SIZE_UPDATE
        value[kid] = new
        change = next_lsn[s["slot"]]
        commit = change + size
        nxt = commit + SIZE_COMMIT
        if nxt >= s["lsn_hi"]:
            fail(f"assertion failed: WAL-tail slot {s['slot']} out of room at {lsn_text_from_int(change)}")
        next_lsn[s["slot"]] = nxt
        ts = pg_ts(ev["t_us"])
        cols = [{"name": "id", "type": "bigint", "value": kid}, {"name": "v", "type": "text", "value": new}]
        rec = {"action": action, "xid": xid, "timestamp": ts, "lsn": lsn_text_from_int(change),
               "schema": "public", "table": RELATION, "columns": cols}
        if action == "U":
            rec["identity"] = [{"name": "id", "type": "bigint", "value": kid},
                               {"name": "v", "type": "text", "value": old}]
        rec["pk"] = [{"name": "id", "type": "bigint"}]
        bc = {"xid": xid, "timestamp": ts, "lsn": lsn_text_from_int(commit), "nextlsn": lsn_text_from_int(nxt)}
        per_slot[s["slot"]].extend([dumps({"action": "B", **bc}), dumps(rec), dumps({"action": "C", **bc})])
        while cp_i < len(cps) and cps[cp_i][0] < ev["t_us"]:
            cp_i += 1
        if cp_i < len(cps):
            cp_ts, cp_lsn = cps[cp_i][1], cps[cp_i][2]
        else:
            cp_ts, cp_lsn = close["wall_clock"], lsn_norm(close["lsn"])
        wl_out.append(dumps({"action": action, "command_tag": None, "natural_key": kid,
                             "object_identity": None, "op_index": max_op + 1 + seq,
                             "table": RELATION, "wall_clock": cp_ts, "xid": xid}))
        man_out.append(dumps({"commit_lsn": cp_lsn, "commit_ts": cp_ts,
                              "operation": "insert" if action == "I" else "update",
                              "relation": RELATION, "row_count": 1, "row_ids": [kid]}))
        rows.append({"xid": xid, "id": kid, "action": action, "t_us": ev["t_us"], "slot": s["slot"],
                     "change_lsn_int": change, "commit_lsn_int": commit, "manifest_commit_lsn": cp_lsn})
    return {"per_slot": per_slot, "wl": wl_out, "man": man_out, "rows": rows,
            "n_insert": len(inserted), "n_update": len(events) - len(inserted)}


def merged_db(real: dict, slots: list[dict], pad: dict) -> list[str]:
    after = {s["after_line"]: pad["per_slot"][s["slot"]] for s in slots}
    out: list[str] = []
    for i, line in enumerate(real["db_lines"]):
        out.append(line)
        if i in after:
            out.extend(after[i])
    return out


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(x + "\n" for x in lines), encoding="utf-8")


# --- pipeline (frozen P3/P5/P5.1, in-process, guarded) -----------------------------

@contextlib.contextmanager
def padded_env(dest: Path):
    keep = {k: os.environ.get(k) for k in ("EVIDENCE_ROOT", "LAB_REPR_ROOT")}
    os.environ["EVIDENCE_ROOT"] = str(dest / "evidence")
    os.environ["LAB_REPR_ROOT"] = str(dest / "repr")
    try:
        yield
    finally:
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _guard_padded_root() -> Path:
    from lab_paths import evidence_dir
    ed = evidence_dir(INCIDENT).resolve()
    scaled = (root() / "incidents" / "scaled").resolve()
    if scaled not in ed.parents:
        fail(f"assertion failed: pipeline evidence dir {ed} is not under {scaled}; refusing to write")
    rr = Path(os.environ["LAB_REPR_ROOT"]).resolve()
    if scaled not in rr.parents:
        fail(f"assertion failed: LAB_REPR_ROOT {rr} is not under {scaled}; refusing to write")
    return ed


def _quiet(fn, *a, **kw):
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*a, **kw)


def run_pipeline(dest: Path) -> dict:
    """analytics -> anomaly -> R0/R1/R2 -> guarded model_view -> assembled prompt, per rep."""
    from lab_analytics import analytics
    from lab_anomaly import anomaly
    from lab_repr_r0 import build_r0
    from lab_repr_r1 import build_r1
    from lab_repr_r2 import build_r2
    from lab_arm_b_prompt import assemble
    from lab_tokenize import token_estimate
    timings = {}
    with padded_env(dest):
        _guard_padded_root()
        t = time.monotonic(); _quiet(analytics, INCIDENT); timings["analytics_s"] = time.monotonic() - t
        t = time.monotonic(); _quiet(anomaly, INCIDENT); timings["anomaly_s"] = time.monotonic() - t
        t = time.monotonic()
        r0 = build_r0(INCIDENT); r1 = build_r1(INCIDENT); r2 = build_r2(INCIDENT)
        timings["repr_s"] = time.monotonic() - t
        prompts = {}
        pdir = dest / "prompts"
        pdir.mkdir(parents=True, exist_ok=True)
        for rep in REPS:
            t = time.monotonic()
            text = assemble(INCIDENT, rep, scratch_dir=dest / "guard")
            timings[f"assemble_{rep}_s"] = time.monotonic() - t
            (pdir / f"{rep}.prompt").write_text(text, encoding="utf-8")
            content = text.split("<<<ARM_B_CONTENT", 1)[1].split("ARM_B_CONTENT>>>", 1)[0]
            prompts[rep] = {
                "canonical_tokens": token_estimate(text),
                "content_canonical_tokens": token_estimate(content),
                "bytes": len(text.encode("utf-8")),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "content_lines": content.strip("\n").count("\n") + 1 if content.strip() else 0,
            }
    return {"prompts": prompts, "timings": {k: round(v, 3) for k, v in timings.items()},
            "repr": {"R0": {"event_count": r0["event_count"], "reconciles": r0["reconciles"],
                            "provenance_blind": r0["provenance_blind"], "content_hash": r0["content_hash"]},
                     "R1": {"reconciles": r1["reconciles"], "provenance_blind": r1["provenance_blind"],
                            "content_hash": r1["content_hash"]},
                     "R2": {"reconciles": r2["reconciles"], "provenance_blind": r2["provenance_blind"],
                            "content_hash": r2["content_hash"]}}}


# --- build one padded incident -------------------------------------------------------

def build(dest: Path, seed: int, n: int, real: dict | None = None) -> dict:
    real = real or load_real()
    grid = window_grid(real)
    slots = tail_slots(real, grid)
    events = draw_stream(seed, n, slots)
    pad = materialise(real, events, slots)
    if dest.exists():
        shutil.rmtree(dest)
    ed = dest / "evidence" / "SC-01" / INCIDENT
    ed.mkdir(parents=True)
    for name in COPY_FILES:
        src = real["dir"] / name
        if src.is_file():
            shutil.copyfile(src, ed / name)
    write_lines(ed / "db.jsonl", merged_db(real, slots, pad))
    write_lines(ed / "workload.jsonl", real["wl_lines"] + pad["wl"])
    write_lines(ed / "workload-manifest.jsonl", real["man_lines"] + pad["man"])
    write_oracle(ed, real)
    pipe = run_pipeline(dest)
    an = [json.loads(x) for x in (ed / "p3" / "anomaly.jsonl").read_text(encoding="utf-8").splitlines() if x]
    visible = [int(w["window_id"]) for w in sorted(an, key=lambda w: (-float(w["anomaly_score"]),
                                                                      int(w["window_id"])))[:3]]
    rec = {
        "generator_version": GENERATOR_VERSION, "seed": seed, "n_padded": n, "visible_windows": visible,
        "n_insert": pad["n_insert"], "n_update": pad["n_update"],
        "grid": grid, "slots": [{k: v for k, v in s.items()} for s in slots],
        "padded_per_slot": {str(k): len(v) // 3 for k, v in pad["per_slot"].items()},
        **pipe,
    }
    (dest / "padding-rows.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in pad["rows"]),
                                            encoding="utf-8")
    return rec


def write_oracle(ed: Path, real: dict) -> None:
    """Oracle for the padded incident with the unchanged lab_oracle rules (select_optimum,
    build_manifest_doc). The coordinate is carried from the frozen oracle ONLY if the
    recomputed optimum LSN and selected record equal the frozen ones; the live
    lab-coordinate lookup is not re-queried (it has drifted since P1; ADR-P10-6)."""
    from lab_oracle import build_manifest_doc, load_jsonl, select_optimum, sha256_file as osha
    inject = json.loads((ed / "injection.json").read_text(encoding="utf-8"))
    manifest = load_jsonl(ed / "workload-manifest.jsonl")
    inj_lsn = lsn_norm(inject["commit_lsn"])
    chosen = select_optimum(manifest, inj_lsn)
    frozen = json.loads((real["dir"] / "oracle.json").read_text(encoding="utf-8"))
    frozen_sel = frozen["inputs"]["workload-manifest.jsonl"]["selected_record"]
    same = (lsn_norm(chosen["commit_lsn"]) == lsn_norm(frozen["coordinate"]["lsn"])
            and chosen.get("commit_ts") == frozen_sel.get("commit_ts")
            and chosen.get("operation") == frozen_sel.get("operation")
            and chosen.get("row_ids") == frozen_sel.get("row_ids"))
    doc = {
        "coordinate": frozen["coordinate"] if same else None,
        "incident": INCIDENT,
        "inputs": {
            "injection.json": {"path": str(ed / "injection.json"), "sha256": osha(ed / "injection.json"),
                               "commit_lsn": inj_lsn, "rows_destroyed": inject.get("rows_destroyed")},
            "workload-manifest.jsonl": {
                "path": str(ed / "workload-manifest.jsonl"), "sha256": osha(ed / "workload-manifest.jsonl"),
                "records": len(manifest),
                "selected_record": {"commit_lsn": lsn_norm(chosen["commit_lsn"]),
                                    "commit_ts": chosen.get("commit_ts"),
                                    "operation": chosen.get("operation"), "row_ids": chosen.get("row_ids")},
            },
        },
        "optimum_matches_frozen": same,
    }
    scoring = build_manifest_doc(chosen, inject, manifest, None)
    (ed / "oracle.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ed / "oracle-manifest.json").write_text(json.dumps(scoring, indent=2, sort_keys=True) + "\n",
                                            encoding="utf-8")
    if not same:
        fail(f"assertion failed: padded optimum {chosen['commit_lsn']} != frozen "
             f"{frozen['coordinate']['lsn']} (C1.1); refusing to emit")


# --- independent invariance / integrity check ----------------------------------------

def check(dest: Path, real: dict | None = None) -> dict:
    """Re-derive C1 invariants from the emitted files only (no generator state)."""
    from lab_ledger_account import map_ops
    from lab_ledger_verify import verify
    from lab_oracle import select_optimum
    from lab_repr import strip_keys
    real = real or load_real()
    ed = dest / "evidence" / "SC-01" / INCIDENT
    res: dict = {"dest": str(dest)}
    db_lines = (ed / "db.jsonl").read_text(encoding="utf-8").splitlines()
    wl_lines = (ed / "workload.jsonl").read_text(encoding="utf-8").splitlines()
    man_lines = (ed / "workload-manifest.jsonl").read_text(encoding="utf-8").splitlines()
    # real bytes preserved, in order
    def subseq(real_lines, lines):
        it = iter(lines)
        return all(any(x == y for y in it) for x in real_lines)
    res["real_db_lines_preserved_in_order"] = subseq(real["db_lines"], db_lines)
    res["real_workload_prefix_identical"] = wl_lines[:len(real["wl_lines"])] == real["wl_lines"]
    res["real_manifest_prefix_identical"] = man_lines[:len(real["man_lines"])] == real["man_lines"]
    res["copied_files_identical"] = all(
        sha256_file(ed / f) == sha256_file(real["dir"] / f) for f in COPY_FILES if (real["dir"] / f).is_file())
    # padded records: legitimate kinds only, no provenance, no delete/DDL
    real_set = set(real["db_lines"])
    padded_db = [json.loads(x) for x in db_lines if x not in real_set]
    padded_wl = [json.loads(x) for x in wl_lines[len(real["wl_lines"]):]]
    padded_man = [json.loads(x) for x in man_lines[len(real["man_lines"]):]]
    res["padded_db_records"] = len(padded_db)
    res["padded_ops"] = len(padded_wl)
    kinds = {r["action"] for r in padded_db}
    res["padded_kinds"] = sorted(kinds)
    res["padded_legit_kinds_only"] = kinds <= {"B", "I", "U", "C"} and \
        {o["action"] for o in padded_wl} <= {"I", "U"} and \
        {m["operation"] for m in padded_man} <= {"insert", "update"} and \
        all(r.get("table") == RELATION for r in padded_db if r["action"] in {"I", "U"})
    # padding may only create/modify its own rows: a padded op on a real row is damage the
    # oracle cannot see, whether or not the injection record mentions it.
    res["padded_touch_padded_rows_only"] = all(int(o["natural_key"]) >= KEY_BASE for o in padded_wl) and \
        all(int(rid) >= KEY_BASE for m in padded_man for rid in m.get("row_ids") or []) and \
        all(int(c["value"]) >= KEY_BASE for r in padded_db if r["action"] in {"I", "U", "D"}
            for c in (r.get("columns") or []) + (r.get("identity") or []) if c.get("name") == "id")
    res["padded_no_principal"] = not any("principal" in o for o in padded_wl) and \
        not any("principal" in m for m in padded_man) and \
        not any("principal" in json.dumps(r) or "lab_app" in json.dumps(r) or "lab_agent" in json.dumps(r)
                for r in padded_db)
    # ledger integrity (P2.1 bijection + lab-ledger-verify)
    db = [json.loads(x) for x in db_lines]
    ops = [strip_keys(json.loads(x)) for x in wl_lines]
    cov = map_ops(ops, db)
    res["reconciliation"] = {"ops": cov["ops"], "mapped": cov["mapped"],
                             "gaps": len(cov["gaps"]), "duplicates": len(cov["duplicates"])}
    inc = real["incident"]
    lv = verify(db, inc["open_coordinate"]["lsn"], inc["close_coordinate"]["lsn"], INCIDENT)
    res["ledger_verify"] = {k: lv[k] for k in ("ok", "records", "duplicate_lsns_count",
                                                "out_of_range_count", "monotonic")}
    # C1.1: oracle optimum invariant (pure lab_oracle rule on the emitted manifest)
    inject = json.loads((ed / "injection.json").read_text(encoding="utf-8"))
    frozen = json.loads((real["dir"] / "oracle.json").read_text(encoding="utf-8"))
    frozen_man = json.loads((real["dir"] / "oracle-manifest.json").read_text(encoding="utf-8"))
    manifest = [json.loads(x) for x in man_lines]
    sel = frozen["inputs"]["workload-manifest.jsonl"]["selected_record"]
    try:
        chosen = select_optimum(manifest, lsn_norm(inject["commit_lsn"]))
    except SystemExit as exc:          # no legitimate commit precedes the injection: optimum undefined
        chosen = {"commit_lsn": "0/0", "undefined": str(exc)}
    res["optimum"] = {
        "frozen_lsn": frozen["coordinate"]["lsn"], "padded_lsn": lsn_norm(chosen["commit_lsn"]),
        "frozen_malicious_lsn": frozen_man["malicious_lsn"], "padded_malicious_lsn": lsn_norm(inject["commit_lsn"]),
        "selected_record_identical": all(chosen.get(k) == sel.get(k) for k in ("commit_ts", "operation", "row_ids")),
    }
    res["optimum_invariant"] = (res["optimum"]["frozen_lsn"] == res["optimum"]["padded_lsn"]
                                and res["optimum"]["frozen_malicious_lsn"] == res["optimum"]["padded_malicious_lsn"]
                                and res["optimum"]["selected_record_identical"])
    # explicit A3 assertions: padded commit_lsn values are existing driver checkpoints or
    # the close LSN, and the close LSN is not below the injection.
    cp_lsns = {c[2] for c in checkpoints(real)}
    close_lsn = lsn_norm(real["incident"]["close_coordinate"]["lsn"])
    res["padded_commit_lsns_are_checkpoints_or_close"] = all(
        lsn_norm(m["commit_lsn"]) in cp_lsns | {close_lsn} for m in padded_man)
    res["close_not_below_injection"] = lsn_int(close_lsn) >= lsn_int(inject["commit_lsn"])
    emitted = json.loads((ed / "oracle.json").read_text(encoding="utf-8"))
    res["emitted_oracle_coordinate_identical"] = emitted.get("coordinate") == frozen["coordinate"]
    res["ok"] = all([
        res["real_db_lines_preserved_in_order"], res["real_workload_prefix_identical"],
        res["real_manifest_prefix_identical"], res["copied_files_identical"],
        res["padded_legit_kinds_only"], res["padded_touch_padded_rows_only"], res["padded_no_principal"],
        res["reconciliation"]["mapped"] == res["reconciliation"]["ops"],
        res["reconciliation"]["gaps"] == 0, res["reconciliation"]["duplicates"] == 0,
        res["ledger_verify"]["ok"], res["optimum_invariant"], res["emitted_oracle_coordinate_identical"],
        res["padded_commit_lsns_are_checkpoints_or_close"], res["close_not_below_injection"],
    ])
    return res


# --- calibration to the pre-registered target ---------------------------------------

def calibrate(target: int, seed: int, work: Path, real: dict, log: list) -> tuple[int, dict]:
    """Smallest padding count whose R0 prompt reaches the target within tolerance.
    The count is a scalar intensity; positions are always the seeded prefix."""
    base = build(work, seed, 0, real)
    base_tok = base["prompts"]["R0"]["canonical_tokens"]
    log.append({"n": 0, "r0_canonical_tokens": base_tok})
    if target <= base_tok:
        return 0, base
    lo_n, lo_tok = 0, base_tok
    probe = build(work, seed, 2000, real)
    per = (probe["prompts"]["R0"]["canonical_tokens"] - base_tok) / 2000
    log.append({"n": 2000, "r0_canonical_tokens": probe["prompts"]["R0"]["canonical_tokens"]})
    n = max(1, int(round((target - base_tok) / max(per, 1e-9))))
    hi_n, hi_tok, best = None, None, None
    for _ in range(14):
        rec = build(work, seed, n, real)
        tok = rec["prompts"]["R0"]["canonical_tokens"]
        log.append({"n": n, "r0_canonical_tokens": tok})
        if abs(tok - target) <= TARGET_TOLERANCE * target:
            return n, rec
        if tok < target:
            lo_n, lo_tok = n, tok
        else:
            hi_n, hi_tok = n, tok
        if hi_n is None:
            n = int(round(n * target / tok)) + 1
        else:
            span = hi_tok - lo_tok
            n = lo_n + max(1, int(round((hi_n - lo_n) * (target - lo_tok) / span))) if span > 0 else (lo_n + hi_n) // 2
            if n >= hi_n:
                n = hi_n - 1
            if n <= lo_n:
                n = lo_n + 1
            if hi_n - lo_n <= 1:
                break
    fail(f"assertion failed: could not reach target {target} within {TARGET_TOLERANCE:.0%}: {log[-4:]}")
    return 0, {}


def emit(target: int, seed: int = SEED) -> dict:
    real = load_real()
    final = scaled_root(target)
    work = final.with_name(final.name + ".work")
    t = time.monotonic()
    log: list = []
    if target == ANCHOR_TARGET:
        n, rec = 0, build(work, seed, 0, real)   # ADR-P10-6: the anchor is the natural incident
        log.append({"n": 0, "r0_canonical_tokens": rec["prompts"]["R0"]["canonical_tokens"]})
    else:
        n, rec = calibrate(target, seed, work, real, log)
    chk = check(work, real)
    rec.update({"scale_target": target, "calibration": log, "check": chk,
                "build_seconds": round(time.monotonic() - t, 1)})
    if not chk["ok"]:
        rejected = final.with_name(final.name + ".rejected")
        if rejected.exists():
            shutil.rmtree(rejected)
        work.rename(rejected)
        (rejected / "generator-record.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
        fail(f"assertion failed: padded incident for target {target} failed invariance check; "
             f"refused (kept at {rejected})")
    if final.exists():
        shutil.rmtree(final)
    work.rename(final)
    (final / "generator-record.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return rec


def ledger_digests(dest: Path) -> dict:
    ed = dest / "evidence" / "SC-01" / INCIDENT
    return {f: sha256_file(ed / f) for f in DERIVED}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-scale-generate")
    p.add_argument("--scenario", default="SC-01", choices=("SC-01",))
    p.add_argument("--target", type=int, choices=SCALE_TARGETS)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--all", action="store_true")
    p.add_argument("--check", help="re-derive C1 invariants for an emitted padded incident dir")
    args = p.parse_args(argv)
    if args.check:
        res = check(Path(args.check))
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0 if res["ok"] else 1
    targets = SCALE_TARGETS if args.all else ([args.target] if args.target else [])
    if not targets:
        p.error("--target or --all required")
    for tg in targets:
        rec = emit(tg, args.seed)
        print(json.dumps({"target": tg, "n_padded": rec["n_padded"],
                          "r0_canonical_tokens": rec["prompts"]["R0"]["canonical_tokens"],
                          "r2_canonical_tokens": rec["prompts"]["R2"]["canonical_tokens"],
                          "check_ok": rec["check"]["ok"], "build_seconds": rec["build_seconds"],
                          "ledger": ledger_digests(scaled_root(tg))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
