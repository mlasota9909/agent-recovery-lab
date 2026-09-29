"""P10 negative tests. Each mutates a SCRATCH copy from outside the component under test
(Article XII spirit) and asserts the real check refuses. Scratch lives under
incidents/scaled/_neg/ (gitignored) or logs/review/<task>/scratch/. Nothing prior is touched.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

from lab_p10 import INCIDENT, MAX_TOKENS, root, scaled_root

NEG_ROOT_NAME = "_neg"


def neg_dir(name: str) -> Path:
    d = root() / "incidents" / "scaled" / NEG_ROOT_NAME / name
    if d.exists():
        shutil.rmtree(d)
    d.parent.mkdir(parents=True, exist_ok=True)
    return d


def copy_incident(target: int, name: str) -> Path:
    d = neg_dir(name)
    shutil.copytree(scaled_root(target), d)
    for p in d.rglob("*"):
        if p.is_file():
            os.chmod(p, 0o644)
    return d


def ev(d: Path) -> Path:
    return d / "evidence" / "SC-01" / INCIDENT


def _lines(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines()


def _write(p: Path, lines: list[str]) -> None:
    p.write_text("".join(x + "\n" for x in lines), encoding="utf-8")


# --- Q001: pre-registration ordering --------------------------------------------------

def neg_prereg_order(review: Path) -> dict:
    from lab_p10 import prereg_check, preregistration_path, _parse_utc
    scratch = review / "scratch" / "results"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    f = scratch / "scaling-runs.jsonl"
    f.write_text('{"scale_run_id":"throwaway"}\n', encoding="utf-8")
    t_pre = _parse_utc(json.loads(preregistration_path().read_text())["preregistered_utc"]).timestamp()
    os.utime(f, (t_pre - 3600, t_pre - 3600))
    r = prereg_check(scratch)
    f.unlink()
    return {"test": "prereg-order", "expect": "frozen_before_data=false, ok=false",
            "observed": {"frozen_before_data": r["frozen_before_data"], "ok": r["ok"], "violations": r["violations"]},
            "pass": (r["frozen_before_data"] is False and r["ok"] is False), "throwaway_deleted": not f.exists()}


# --- Q002: damage injected into padding -> refused ----------------------------------------

def neg_damage(target: int) -> dict:
    from lab_p10_scale import check, load_real
    from lsn import lsn_int, lsn_text_from_int
    out = {"test": "damage-in-padding", "target": target, "variants": []}
    real = load_real()
    for variant in ("recorded-as-damage", "silent-destructive-op"):
        d = copy_incident(target, f"damage-{variant}")
        e = ev(d)
        rows = [json.loads(x) for x in _lines(d / "padding-rows.jsonl")]
        opt = lsn_int("1/E1000000")
        # an early padded transaction (before the optimum) is turned into a DELETE of a real row
        victim = [r for r in rows if lsn_int(r["manifest_commit_lsn"]) < opt][-1]   # closest before optimum
        db = _lines(e / "db.jsonl")
        for i, line in enumerate(db):
            rec = json.loads(line)
            if rec.get("xid") == victim["xid"] and rec["action"] in {"I", "U"}:
                rec = {"action": "D", "xid": rec["xid"], "timestamp": rec["timestamp"], "lsn": rec["lsn"],
                       "schema": "public", "table": "p2_probe",
                       "identity": [{"name": "id", "type": "bigint", "value": 88000701},
                                    {"name": "v", "type": "text", "value": "u88000701b"}],
                       "pk": [{"name": "id", "type": "bigint"}]}
                db[i] = json.dumps(rec, separators=(",", ":"))
                break
        _write(e / "db.jsonl", db)
        wl = _lines(e / "workload.jsonl")
        for i, line in enumerate(wl):
            o = json.loads(line)
            if o.get("xid") == victim["xid"]:
                o.update({"action": "D", "natural_key": 88000701})
                wl[i] = json.dumps(o, separators=(",", ":"))
        _write(e / "workload.jsonl", wl)
        if variant == "recorded-as-damage":
            inj = json.loads((e / "injection.json").read_text())
            inj["commit_lsn"] = lsn_text_from_int(int(victim["commit_lsn_int"]))
            inj["row_ids"] = [88000701] + inj["row_ids"]
            inj["rows_destroyed"] = inj["rows_destroyed"] + 1
            (e / "injection.json").write_text(json.dumps(inj, indent=2, sort_keys=True) + "\n")
        r = check(d, real)
        out["variants"].append({
            "variant": variant, "check_ok": r["ok"], "optimum": r["optimum"],
            "optimum_invariant": r["optimum_invariant"], "padded_legit_kinds_only": r["padded_legit_kinds_only"],
            "padded_touch_padded_rows_only": r["padded_touch_padded_rows_only"],
            "copied_files_identical": r["copied_files_identical"],
            "refused": r["ok"] is False})
    rec_var = out["variants"][0]
    out["pass"] = all(v["refused"] for v in out["variants"]) and rec_var["optimum_invariant"] is False
    return out


def neg_generator_refuses(target: int) -> dict:
    """Drive the real emit() path with a patched materialise that adds one damage row, and
    a patched output root; assert emit refuses and leaves only a *.rejected copy."""
    import lab_p10_scale as G
    scratch_root = root() / "incidents" / "scaled" / NEG_ROOT_NAME / "emit"
    if scratch_root.exists():
        shutil.rmtree(scratch_root)
    orig_scaled, orig_mat = G.scaled_root, G.materialise

    def patched_root(t):
        return scratch_root / f"sc01-s{t}"

    def patched_materialise(real, events, slots):
        pad = orig_mat(real, events, slots)
        # turn the first padded change into a DELETE of a real legitimate row
        for s, lines in pad["per_slot"].items():
            if lines:
                rec = json.loads(lines[1])
                rec = {"action": "D", "xid": rec["xid"], "timestamp": rec["timestamp"], "lsn": rec["lsn"],
                       "schema": "public", "table": "p2_probe",
                       "identity": [{"name": "id", "type": "bigint", "value": 88000701}],
                       "pk": [{"name": "id", "type": "bigint"}]}
                lines[1] = json.dumps(rec, separators=(",", ":"))
                xid = rec["xid"]
                for j, w in enumerate(pad["wl"]):
                    o = json.loads(w)
                    if o["xid"] == xid:
                        o.update({"action": "D", "natural_key": 88000701})
                        pad["wl"][j] = json.dumps(o, separators=(",", ":"))
                break
        return pad

    G.scaled_root, G.materialise = patched_root, patched_materialise
    refused, msg = False, ""
    try:
        G.emit(target)
    except SystemExit as exc:
        refused, msg = True, str(exc)
    finally:
        G.scaled_root, G.materialise = orig_scaled, orig_mat
    final = patched_root(target)
    return {"test": "generator-refuses-damage", "target": target, "refused": refused,
            "final_emitted": final.exists(), "rejected_kept": final.with_name(final.name + ".rejected").exists(),
            "pass": refused and not final.exists()}


# --- Q003: duplicate padded LSN; parity; principal in padding ------------------------

def neg_duplicate_lsn(target: int) -> dict:
    from lab_ledger_account import map_ops
    from lab_ledger_verify import verify
    from lab_repr import strip_keys
    d = copy_incident(target, "dup-lsn")
    e = ev(d)
    db = _lines(e / "db.jsonl")
    real = set(_lines(scaled_root(target).parent / "sc01-s10000" / "evidence" / "SC-01" / INCIDENT / "db.jsonl"))
    idx = next(i for i, x in enumerate(db) if x not in real and json.loads(x)["action"] == "B")
    triple = db[idx:idx + 3]
    db[idx + 3:idx + 3] = triple          # duplicate one padded transaction (same LSNs)
    _write(e / "db.jsonl", db)
    recs = [json.loads(x) for x in db]
    inc = json.loads((e / "incident.json").read_text())
    lv = verify(recs, inc["open_coordinate"]["lsn"], inc["close_coordinate"]["lsn"], INCIDENT)
    cov = map_ops([strip_keys(json.loads(x)) for x in _lines(e / "workload.jsonl")], recs)
    return {"test": "duplicate-padded-lsn", "target": target, "duplicated_lsn": json.loads(triple[0])["lsn"],
            "ledger_verify_duplicate_lsns": lv["duplicate_lsns_count"], "ledger_verify_ok": lv["ok"],
            "reconciliation_duplicates": len(cov["duplicates"]),
            "pass": lv["duplicate_lsns_count"] >= 1 and not lv["ok"] and len(cov["duplicates"]) >= 1}


def neg_parity_model_field(target: int) -> dict:
    import subprocess
    from lab_repr_modelview import MODEL_VIEW_KEYS, _diff, _skeleton
    env = os.environ.copy()
    env.update({"EVIDENCE_ROOT": str(scaled_root(target) / "evidence"),
                "LAB_REPR_ROOT": str(scaled_root(target) / "repr"),
                "PYTHONPATH": str(root() / "lib")})
    views = {}
    for rep in ("R0", "R2"):
        p = subprocess.run([str(root() / "bin" / "lab-repr-modelview"), INCIDENT, rep, "PB-6-candidate-windows",
                            '{"top_n":3}'], text=True, capture_output=True, env=env, check=True)
        views[rep] = json.loads(p.stdout)
    clean = _diff(_skeleton(views["R0"]), _skeleton(views["R2"]))
    tampered = dict(views["R2"])
    tampered["model_id"] = "gb10a-deepseek-v4-flash"
    diffs = _diff(_skeleton(views["R0"]), _skeleton(tampered)) + \
        ([f"R2: extra keys {sorted(set(tampered) - set(MODEL_VIEW_KEYS))}"] if set(tampered) - set(MODEL_VIEW_KEYS) else [])
    scratch = root() / "incidents" / "scaled" / NEG_ROOT_NAME / "parity-view.json"
    scratch.parent.mkdir(parents=True, exist_ok=True)
    scratch.write_text(json.dumps(tampered, sort_keys=True) + "\n")
    g = subprocess.run([str(root() / "bin" / "lab-modelview-guard"), str(scratch)], text=True,
                       capture_output=True, env=env)
    return {"test": "parity-model-specific-field", "target": target,
            "clean_diffs_R0_vs_R2": clean, "tampered_diffs": diffs,
            "guard_exit": g.returncode, "guard_msg": (g.stderr or g.stdout).strip()[:200],
            "pass": clean == [] and bool(diffs) and g.returncode != 0}


def neg_principal_in_padding(target: int) -> dict:
    """Padding writes a provenance token into a padded row; the guarded assembly must refuse."""
    from lab_p10_scale import padded_env, _guard_padded_root, _quiet
    d = copy_incident(target, "principal")
    e = ev(d)
    real = set(_lines(scaled_root(10_000) / "evidence" / "SC-01" / INCIDENT / "db.jsonl"))
    db = _lines(e / "db.jsonl")
    # choose a padded row that lands in a visible window (window 15 at every scale)
    for i, x in enumerate(db):
        if x in real:
            continue
        rec = json.loads(x)
        if rec["action"] in {"I", "U"} and "09:16:46" <= rec["timestamp"][11:19] <= "09:16:47":
            for c in rec["columns"]:
                if c["name"] == "v":
                    c["value"] = "principal=lab_agent"
            db[i] = json.dumps(rec, separators=(",", ":"))
            break
    _write(e / "db.jsonl", db)
    shutil.rmtree(d / "repr", ignore_errors=True)
    from lab_analytics import analytics
    from lab_anomaly import anomaly
    from lab_repr_r0 import build_r0
    from lab_repr_r1 import build_r1
    from lab_repr_r2 import build_r2
    from lab_arm_b_prompt import assemble
    import io, contextlib
    refused, stage, r0_blind = False, None, None
    err = io.StringIO()
    with padded_env(d), contextlib.redirect_stderr(err):
        _guard_padded_root()
        _quiet(analytics, INCIDENT); _quiet(anomaly, INCIDENT)
        try:
            stage = "build_r0"; r0 = build_r0(INCIDENT); r0_blind = r0["provenance_blind"]
            stage = "build_r1"; build_r1(INCIDENT)
            stage = "build_r2"; build_r2(INCIDENT)
            stage = "assemble_R0"; assemble(INCIDENT, "R0", scratch_dir=d / "guard")
            stage = "assembled"
        except SystemExit:
            refused = True
    # and the Article XVII guard itself, fed the clean view with a principal token in its content
    import subprocess
    env = os.environ.copy()
    env.update({"EVIDENCE_ROOT": str(scaled_root(target) / "evidence"),
                "LAB_REPR_ROOT": str(scaled_root(target) / "repr"), "PYTHONPATH": str(root() / "lib")})
    v = subprocess.run([str(root() / "bin" / "lab-repr-modelview"), INCIDENT, "R0", "PB-6-candidate-windows",
                        '{"top_n":3}'], text=True, capture_output=True, env=env, check=True)
    view = json.loads(v.stdout)
    clean_path, bad_path = d / "view-clean.json", d / "view-principal.json"
    clean_path.write_text(json.dumps(view) + "\n")
    view["content"] = view["content"].replace('"v":"s', '"v":"principal=lab_agent s', 1)
    bad_path.write_text(json.dumps(view) + "\n")
    g_clean = subprocess.run([str(root() / "bin" / "lab-modelview-guard"), str(clean_path)], capture_output=True,
                             text=True, env=env)
    g_bad = subprocess.run([str(root() / "bin" / "lab-modelview-guard"), str(bad_path)], capture_output=True,
                           text=True, env=env)
    return {"test": "principal-in-padding", "target": target, "r0_manifest_provenance_blind": r0_blind,
            "refused_at": stage if refused else None, "refusal_message": err.getvalue().strip()[-300:],
            "assembly_refused": refused, "guard_clean_exit": g_clean.returncode,
            "guard_principal_exit": g_bad.returncode, "guard_principal_msg": (g_bad.stderr or "").strip()[:160],
            "pass": refused and g_clean.returncode == 0 and g_bad.returncode != 0}


# --- Q002: decoy-onset control (scope of onset-blindness, generator amendment A2.6) ----

def neg_onset_decoy(target: int) -> dict:
    """Move the onset P3 reads (injection_log.json lsn_start) to an early window in a decoy
    copy of the frozen evidence. (a) placement + materialisation for the real n must be
    byte-identical; (b) report how the calibrated n shifts (count depends on onset only via
    the frozen view's anomaly baseline)."""
    import lab_p10_scale as G
    real_root = Path(os.environ["EVIDENCE_ROOT"])
    base = neg_dir("onset-decoy")
    dec_ev = base / "decoy-evidence" / "SC-01" / INCIDENT
    shutil.copytree(real_root / "SC-01" / INCIDENT, dec_ev)
    for q in dec_ev.rglob("*"):
        if q.is_file():
            os.chmod(q, 0o644)
    inj_log = json.loads((dec_ev / "injection_log.json").read_text())
    real_onset = inj_log["lsn_start"]
    inj_log["lsn_start"] = "1/E3000638"          # window 17: after the declared baseline (P3 forbids earlier)
    (dec_ev / "injection_log.json").write_text(json.dumps(inj_log, indent=2, sort_keys=True) + "\n")
    rec_real = json.loads((scaled_root(target) / "generator-record.json").read_text())
    n_real = rec_real["n_padded"]
    real = G.load_real()
    os.environ["EVIDENCE_ROOT"] = str(base / "decoy-evidence")
    try:
        decoy = G.load_real()
        grid = G.window_grid(decoy); slots = G.tail_slots(decoy, grid)
        pad = G.materialise(decoy, G.draw_stream(42, n_real, slots), slots)
        merged = G.merged_db(decoy, slots, pad)
        ed = scaled_root(target) / "evidence" / "SC-01" / INCIDENT
        same_db = merged == _lines(ed / "db.jsonl")
        same_wl = decoy["wl_lines"] + pad["wl"] == _lines(ed / "workload.jsonl")
        same_man = decoy["man_lines"] + pad["man"] == _lines(ed / "workload-manifest.jsonl")
        log: list = []
        n_decoy, rec = G.calibrate(target, 42, base / "work", decoy, log)
        from lab_repr import HEADLINE  # noqa: F401
        an = [json.loads(x) for x in _lines(base / "work" / "evidence" / "SC-01" / INCIDENT / "p3" / "anomaly.jsonl")]
        top_decoy = [int(w["window_id"]) for w in sorted(an, key=lambda w: (-float(w["anomaly_score"]), int(w["window_id"])))[:3]]
    finally:
        os.environ["EVIDENCE_ROOT"] = str(real_root)
    return {"test": "onset-decoy-control", "target": target, "real_onset_lsn_start": real_onset,
            "decoy_onset_lsn_start": "1/E3000638",
            "placement_identical_for_fixed_n": {"n": n_real, "db.jsonl": same_db, "workload.jsonl": same_wl,
                                                "workload-manifest.jsonl": same_man},
            "calibrated_n_real": n_real, "calibrated_n_decoy": n_decoy,
            "n_relative_shift": round((n_decoy - n_real) / max(n_real, 1), 4),
            "visible_windows_real": rec_real.get("visible_windows"), "visible_windows_decoy": top_decoy,
            "r0_tokens_decoy": rec["prompts"]["R0"]["canonical_tokens"],
            "pass": same_db and same_wl and same_man}


# --- Q004: mislabelled infeasible cell ----------------------------------------------

def validate_rows(rows: list[dict]) -> list[str]:
    """Reject any row whose outcome contradicts the feasibility rule (plan amendment P3)."""
    bad = []
    for r in rows:
        over = r.get("model_prompt_tokens") is not None and \
            int(r["model_prompt_tokens"]) + MAX_TOKENS > int(r["context_window"])
        if r["outcome"] == "infeasible_context" and not over:
            bad.append(f"{r['scale_run_id']}: infeasible_context but request fits the window")
        if r["outcome"] in {"refusal_genuine", "refusal_parser", "accepted"} and over:
            bad.append(f"{r['scale_run_id']}: {r['outcome']} but request exceeds the window (should be infeasible_context)")
        if r["outcome"] == "accepted" and (r.get("verdict") is None or r.get("chosen_lsn_int") is None):
            bad.append(f"{r['scale_run_id']}: accepted without verdict/chosen coordinate")
        if r["outcome"] != "accepted" and r.get("verdict") is not None:
            bad.append(f"{r['scale_run_id']}: verdict on a non-accepted row")
    return bad


def neg_mislabel(rows: list[dict]) -> dict:
    over = [r for r in rows if r["outcome"] == "infeasible_context"]
    if not over:
        return {"test": "mislabel-infeasible-as-refusal", "pass": False, "why": "no infeasible row to tamper"}
    t = dict(over[0])
    t["outcome"] = "refusal_genuine"
    bad = validate_rows([t])
    return {"test": "mislabel-infeasible-as-refusal", "tampered": t["scale_run_id"], "rejections": bad,
            "clean_rows_rejections": len(validate_rows(rows)), "pass": bool(bad)}


def main(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="lab-p10-negative")
    p.add_argument("test", choices=("prereg", "damage", "emit", "dup-lsn", "parity", "principal", "mislabel", "onset-decoy"))
    p.add_argument("--target", type=int, default=50_000)
    p.add_argument("--review", default=None)
    a = p.parse_args(argv)
    review = Path(a.review) if a.review else root() / "logs" / "review" / "Q001"
    t0 = time.monotonic()
    if a.test == "prereg":
        r = neg_prereg_order(review)
    elif a.test == "damage":
        r = neg_damage(a.target)
    elif a.test == "emit":
        r = neg_generator_refuses(a.target)
    elif a.test == "dup-lsn":
        r = neg_duplicate_lsn(a.target)
    elif a.test == "parity":
        r = neg_parity_model_field(a.target)
    elif a.test == "principal":
        r = neg_principal_in_padding(a.target)
    elif a.test == "onset-decoy":
        r = neg_onset_decoy(a.target)
    else:
        from lab_p10 import scaling_runs_path
        rows = [json.loads(x) for x in scaling_runs_path().read_text().splitlines() if x.strip()]
        r = neg_mislabel(rows)
    r["seconds"] = round(time.monotonic() - t0, 1)
    print(json.dumps(r, indent=2, sort_keys=True, default=str))
    return 0 if r.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
