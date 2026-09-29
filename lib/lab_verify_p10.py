"""lab-verify-p10 (Q007): terminal tiered gate for P10. Re-derives AC-P10-01..13 by invoking
the real tools on the real artefacts (never by reading prose logs). Article XVI: writes only
under logs/review/Q007/; every negative test works in memory or on copies in
logs/review/Q007/scratch/. Prints TIER M x/x · TIER A y/y · TOTAL.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from lab_p10 import (
    INCIDENT, MAX_TOKENS, P9_SWEEP_SHA256, SCALE_TARGETS, SEED, analysis_plan_digest, baseline_path,
    compare_manifest, frozen_hashes_ok, prereg_check, prior_manifest, root, scaled_root,
    scaling_detail_path, scaling_runs_path,
)

REVIEW = None


def review() -> Path:
    d = root() / "logs" / "review" / "Q007"
    d.mkdir(parents=True, exist_ok=True)
    return d


def scratch() -> Path:
    d = review() / "scratch"
    d.mkdir(parents=True, exist_ok=True)
    return d


RESULTS: list[dict] = []


def record(ac: str, tier: str, name: str, ok: bool, observed) -> None:
    RESULTS.append({"ac": ac, "tier": tier, "check": name, "ok": bool(ok), "observed": observed})
    print(f"{'PASS' if ok else 'FAIL'} [{tier}] {ac} {name}", flush=True)


def guarded(fn, *a, **kw):
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            return fn(*a, **kw), None
    except SystemExit as exc:
        return None, (err.getvalue().strip() or str(exc))[-400:]


# ------------------------------------------------------------------------------------

def ac01() -> None:
    fh = frozen_hashes_ok()
    record("AC-P10-01", "M", "contract + amendment digests match frozen-hashes.json", fh["ok"],
           {k: v["match"] for k, v in fh["contracts"].items()})
    pc = prereg_check()
    record("AC-P10-01", "M", "pre-registration precedes every scaling row (fail-closed join)",
           pc["plan_digest_ok"] and pc["frozen_before_data"],
           {"digest_ok": pc["plan_digest_ok"], "frozen_before_data": pc["frozen_before_data"],
            "violations": pc["violations"][:3]})


def ac02() -> None:
    """Re-derive every padded ledger in memory from (seed, n) and compare with the committed digests."""
    import lab_p10_scale as G
    man = json.loads((root() / "runtime" / "p10-scaled-manifest.json").read_text())
    real = G.load_real()
    grid = G.window_grid(real)
    slots = G.tail_slots(real, grid)
    rows = {}
    ok = True
    for t in SCALE_TARGETS:
        n = man["targets"][str(t)]["n_padded"]
        pad = G.materialise(real, G.draw_stream(SEED, n, slots), slots)
        dig = {
            "db.jsonl": hashlib.sha256("".join(x + "\n" for x in G.merged_db(real, slots, pad)).encode()).hexdigest(),
            "workload.jsonl": hashlib.sha256("".join(x + "\n" for x in real["wl_lines"] + pad["wl"]).encode()).hexdigest(),
            "workload-manifest.jsonl": hashlib.sha256("".join(x + "\n" for x in real["man_lines"] + pad["man"]).encode()).hexdigest(),
        }
        same = dig == man["targets"][str(t)]["ledger_sha256"]
        on_disk = G.ledger_digests(scaled_root(t)) == man["targets"][str(t)]["ledger_sha256"]
        rows[t] = {"rederived_equals_committed": same, "on_disk_equals_committed": on_disk}
        ok = ok and same and on_disk
    record("AC-P10-02", "M", "padded ledgers re-derived from (seed, n) are byte-identical to committed digests", ok, rows)


def ac03() -> None:
    import lab_p10_scale as G
    real = G.load_real()
    res = {t: G.check(scaled_root(t), real) for t in SCALE_TARGETS}
    record("AC-P10-03", "M", "every padded incident: optimum 1/E1000000 and malicious LSN invariant; check() ok",
           all(r["ok"] and r["optimum_invariant"] for r in res.values()),
           {t: {"optimum": r["optimum"]["padded_lsn"], "ok": r["ok"]} for t, r in res.items()})
    # negative: one damage row recorded in a scratch copy -> optimum moves -> refused
    d = scratch() / "damage"
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(scaled_root(200_000), d, ignore=shutil.ignore_patterns("repr", "prompts", "guard"))
    for p in d.rglob("*"):
        if p.is_file():
            os.chmod(p, 0o644)
    ed = d / "evidence" / "SC-01" / INCIDENT
    rows = [json.loads(x) for x in (d / "padding-rows.jsonl").read_text().splitlines()]
    from lsn import lsn_int, lsn_text_from_int
    victim = [r for r in rows if lsn_int(r["manifest_commit_lsn"]) < lsn_int("1/E1000000")][-1]
    inj = json.loads((ed / "injection.json").read_text())
    inj["commit_lsn"] = lsn_text_from_int(int(victim["commit_lsn_int"]))
    (ed / "injection.json").write_text(json.dumps(inj))
    neg = G.check(d, real)
    record("AC-P10-03", "M", "NEG: damage recorded inside padding -> optimum moves -> refused",
           neg["ok"] is False and neg["optimum_invariant"] is False,
           {"padded_optimum": neg["optimum"]["padded_lsn"], "ok": neg["ok"]})


def ac04() -> None:
    from lab_ledger_account import map_ops
    from lab_ledger_verify import verify
    from lab_repr import strip_keys
    out, ok = {}, True
    for t in SCALE_TARGETS:
        ed = scaled_root(t) / "evidence" / "SC-01" / INCIDENT
        db = [json.loads(x) for x in (ed / "db.jsonl").read_text().splitlines()]
        ops = [strip_keys(json.loads(x)) for x in (ed / "workload.jsonl").read_text().splitlines()]
        cov = map_ops(ops, db)
        inc = json.loads((ed / "incident.json").read_text())
        lv = verify(db, inc["open_coordinate"]["lsn"], inc["close_coordinate"]["lsn"], INCIDENT)
        good = cov["mapped"] == cov["ops"] and not cov["gaps"] and not cov["duplicates"] and lv["ok"]
        out[t] = {"mapped": cov["mapped"], "ops": cov["ops"], "gaps": len(cov["gaps"]),
                  "duplicates": len(cov["duplicates"]), "ledger_verify": lv["ok"]}
        ok = ok and good
    record("AC-P10-04", "M", "exactly-once reconciliation + lab-ledger-verify on every padded ledger", ok, out)
    ed = scaled_root(500_000) / "evidence" / "SC-01" / INCIDENT
    lines = (ed / "db.jsonl").read_text().splitlines()
    real = set((scaled_root(10_000) / "evidence" / "SC-01" / INCIDENT / "db.jsonl").read_text().splitlines())
    i = next(k for k, x in enumerate(lines) if x not in real and json.loads(x)["action"] == "B")
    dup = lines[:i + 3] + lines[i:i + 3] + lines[i + 3:]
    db = [json.loads(x) for x in dup]
    inc = json.loads((ed / "incident.json").read_text())
    lv = verify(db, inc["open_coordinate"]["lsn"], inc["close_coordinate"]["lsn"], INCIDENT)
    cov = map_ops([strip_keys(json.loads(x)) for x in (ed / "workload.jsonl").read_text().splitlines()], db)
    record("AC-P10-04", "M", "NEG: duplicated padded LSN detected (in memory)",
           lv["duplicate_lsns_count"] >= 1 and len(cov["duplicates"]) >= 1,
           {"duplicate_lsns": lv["duplicate_lsns_count"], "reconciliation_duplicates": len(cov["duplicates"])})


def _modelview(t: int, rep: str) -> dict:
    env = os.environ.copy()
    env.update({"EVIDENCE_ROOT": str(scaled_root(t) / "evidence"), "LAB_REPR_ROOT": str(scaled_root(t) / "repr"),
                "PYTHONPATH": str(root() / "lib")})
    p = subprocess.run([str(root() / "bin" / "lab-repr-modelview"), INCIDENT, rep, "PB-6-candidate-windows",
                        '{"top_n":3}'], text=True, capture_output=True, env=env, check=True)
    return json.loads(p.stdout)


def _guard(view: dict, name: str) -> int:
    f = scratch() / name
    f.write_text(json.dumps(view) + "\n")
    return subprocess.run([str(root() / "bin" / "lab-modelview-guard"), str(f)], capture_output=True).returncode


def ac05() -> None:
    from lab_repr_modelview import _diff, _skeleton
    out, ok = {}, True
    for t in (10_000, 200_000, 1_000_000):
        v0, v2 = _modelview(t, "R0"), _modelview(t, "R2")
        d = _diff(_skeleton(v0), _skeleton(v2))
        out[t] = d
        ok = ok and not d
    record("AC-P10-05", "M", "model_view R0 vs R2 differ only by content/telemetry", ok, out)
    v2 = _modelview(1_000_000, "R2")
    v2["model_id"] = "gb10a-deepseek-v4-flash"
    d = _diff(_skeleton(_modelview(1_000_000, "R0")), _skeleton(v2))
    g = _guard(v2, "parity-neg.json")
    record("AC-P10-05", "M", "NEG: model-specific field -> parity diff + guard refuses", bool(d) and g != 0,
           {"diffs": d, "guard_exit": g})


def ac06_07() -> None:
    from lab_p10_negative import validate_rows
    rows = [json.loads(x) for x in scaling_runs_path().read_text().splitlines() if x.strip()]
    latest = {}
    for r in rows:
        latest[r["scale_run_id"]] = r
    bad = validate_rows(list(latest.values()))
    record("AC-P10-06", "M", "every row's outcome agrees with the feasibility rule (prompt + 8192 vs window)",
           not bad, bad[:5])
    big = [r for r in latest.values() if r["scale_target"] >= 500_000]
    r0 = [r for r in big if r["representation"] == "R0"]
    r2 = [r for r in big if r["representation"] == "R2"]
    ok = bool(r0) and all(r["outcome"] == "infeasible_context" for r in r0) and \
        bool(r2) and all(r["outcome"] != "infeasible_context" for r in r2)
    record("AC-P10-06", "M", "at >=500k every recorded R0 cell is infeasible_context and every R2 cell submittable",
           ok, {"r0": len(r0), "r2": len(r2), "r2_outcomes": sorted({r["outcome"] for r in r2})})
    t = next((dict(r) for r in r0), None)
    if t:
        t["outcome"] = "refusal_genuine"
        rej = validate_rows([t])
        record("AC-P10-06", "M", "NEG: over-window R0 cell relabelled refusal_genuine is rejected", bool(rej), rej)
    sub = [r for r in latest.values() if r["outcome"] not in ("infeasible_context",)]
    record("AC-P10-07", "M", "every recorded cell's model_view passed the guard (guard_pass)",
           all(r["guard_pass"] is True for r in latest.values()), {"rows": len(latest), "submitted": len(sub)})
    gv = {t: all(_guard(_modelview(t, rep), f"g-{t}-{rep}.json") == 0 for rep in ("R0", "R2")) for t in SCALE_TARGETS}
    record("AC-P10-07", "M", "live re-check: R0/R2 model views at every scale pass lab-modelview-guard", all(gv.values()), gv)
    v = _modelview(200_000, "R0")
    v["content"] = v["content"].replace('"v":"s', '"v":"principal=lab_agent s', 1)
    g = _guard(v, "principal-neg.json")
    record("AC-P10-07", "M", "NEG: provenance token in a padded row's value -> guard refuses", g != 0, {"guard_exit": g})


def ac08() -> None:
    import lab_p10
    live = analysis_plan_digest()
    bumped = scratch() / "contracts"
    if bumped.exists():
        shutil.rmtree(bumped)
    shutil.copytree(lab_p10.contracts_dir(), bumped)
    p = bumped / "scaling-analysis-plan.md"
    p.write_text(p.read_text() + "\n<!-- bumped -->\n")
    orig = lab_p10.contracts_dir
    lab_p10.contracts_dir = lambda: bumped
    try:
        pc = lab_p10.prereg_check()
        import lab_p10_stats
        halted = False
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                lab_p10_stats.run(out_dir=scratch())
        except SystemExit:
            halted = True
    finally:
        lab_p10.contracts_dir = orig
    record("AC-P10-08", "M", "NEG: bumped analysis plan -> lab-p10-stats halts (Article XXI)",
           halted and not pc["plan_digest_ok"] and analysis_plan_digest() == live,
           {"prereg_ok_with_bump": pc["plan_digest_ok"], "stats_halted": halted, "live_digest_restored": analysis_plan_digest() == live})


def ac09_10_11() -> None:
    import lab_p10_stats as T
    committed = json.loads((root() / "thesis" / "analysis" / "p10-scaling.json").read_text())
    res = T.analyse()
    same = all(json.dumps(res[k], sort_keys=True, default=str) == json.dumps(committed[k], sort_keys=True, default=str)
               for k in ("H1", "H2", "H3", "branch", "cells", "limits", "r2"))
    record("AC-P10-09", "M", "H1/H2/H3, branch and per-cell metrics recompute identical to thesis/analysis/p10-scaling.json",
           same, {"H1": res["H1"]["holds"], "H2": res["H2"]["holds"], "H3": res["H3"]["holds"], "branch": res["branch"]})
    md = (root() / "thesis" / "analysis" / "p10-scaling.md").read_text()
    verbatim = (not res["branch"]["selectable"]) or (res["branch"]["interpretation"] in md)
    record("AC-P10-09", "M", "realised A4 interpretation present verbatim (or non-selectable branch stated)", verbatim,
           {"selectable": res["branch"]["selectable"]})
    lints = {"p10-scaling.md": T.lint(md)}
    record("AC-P10-09", "M", "universal-language lint passes on the analysis report",
           all(v["ok"] for v in lints.values()), {k: v["violations"][:3] for k, v in lints.items()})
    fig = root() / "thesis" / "figures" / "FIG-P10-two-curve.png"
    regen = T.figure(T.cells(T.load()[0]), scratch() / "fig.png")
    record("AC-P10-10", "M", "two-curve figure regenerates byte-identical from scaling-runs.jsonl",
           regen["sha256"] == hashlib.sha256(fig.read_bytes()).hexdigest(),
           {"regen": regen["sha256"][:16], "committed": hashlib.sha256(fig.read_bytes()).hexdigest()[:16]})
    def adjacent(text: str) -> bool:
        lines = text.splitlines()
        idx = [i for i, l in enumerate(lines) if "FIG-P10-two-curve" in l]
        return bool(idx) and all(any(T.LIMITATION_SENTENCE[:60] in l for l in lines[max(0, i - 3):i + 4]) for i in idx)
    adj = {"p10-scaling.md": adjacent(md)}
    record("AC-P10-10", "M", "synthetic-padding limitation sentence adjacent to every headline figure reference",
           all(adj.values()), adj)
    r2 = T.r2_non_decreasing(T.cells(T.load()[0]))
    record("AC-P10-11", "A", "recorded R2 canonical tokens non-decreasing in scale", r2["non_decreasing"],
           r2["median_r2_canonical_by_scale"])
    fake = {("R2", t, "gb10a-deepseek-v4-flash"): [{"canonical_tokens": 300 - i * 10}] for i, t in enumerate(SCALE_TARGETS)}
    record("AC-P10-11", "A", "NEG: synthetic rows where R2 shrinks with scale are flagged",
           T.r2_non_decreasing(fake)["non_decreasing"] is False, T.r2_non_decreasing(fake)["median_r2_canonical_by_scale"])


def ac12() -> None:
    before = json.loads(baseline_path().read_text())
    after = prior_manifest()
    cmp = compare_manifest(before, after)
    record("AC-P10-12", "M", "prior-evidence manifest byte-identical (strict) and P9 sweep SHA-256 unchanged",
           cmp["ok"] and cmp["p9_sweep_sha256"] == P9_SWEEP_SHA256,
           {k: cmp[k] for k in ("prior_files_byte_identical", "strict_changed", "strict_deleted", "strict_added",
                                "p10_designated_additions", "append_only_changed", "append_only_added_count",
                                "p9_sweep_sha256")})
    tampered = json.loads(json.dumps(before))
    k = sorted(tampered["strict"])[0]
    tampered["strict"][k] = "0" + tampered["strict"][k][1:]
    (scratch() / "prior-manifest-tampered.json").write_text(json.dumps(tampered))
    neg = compare_manifest(tampered, after)
    record("AC-P10-12", "M", "NEG: one byte changed in a scratch copy of the prior manifest -> check fails",
           neg["ok"] is False, {"changed": neg["strict_changed"][:1]})
    rogue = json.loads(json.dumps(after))
    rogue["strict"]["thesis/analysis/undesignated.md"] = "0" * 64 + " mode=0644 size=1"
    neg2 = compare_manifest(before, rogue)
    record("AC-P10-12", "M", "NEG: an undesignated file added inside a strict root -> check fails",
           neg2["ok"] is False, {"added": neg2["strict_added"]})


def ac13() -> None:
    """Read-only only (Article XVI). The mutating live regression (bin/lab-regression) is a
    separate Q007 step (lab_p10_regression); this gate reads its recorded JSON result."""
    import lab_verify_p9 as P9
    hs = P9.hash_state()
    ro = P9.readonly_state()
    record("AC-P10-13", "M", "P0–P9 frozen contract digests re-verify (lab_verify_p9.hash_state, read-only)",
           hs["ok"], {"n": len(hs.get("files") or hs.get("contracts") or {})})
    record("AC-P10-13", "M", "P9 read-only state intact (evidence manifest + SC-01..04/matrix results vs P9 baseline)",
           ro["ok"], {k: v["baseline"] == v["now"] for k, v in ro["checks"].items()})
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + os.pathsep + str(root() / "analysis")
    env["LAB_READONLY_CHECK"] = "1"
    gates = {}
    for name in ("lab-verify-p7", "lab-verify-p7.1", "lab-verify-p8"):
        p = subprocess.run([str(root() / "bin" / name)], cwd=str(root()), text=True, capture_output=True, env=env,
                           timeout=3600)
        tail = [l for l in (p.stdout or "").strip().splitlines() if l.strip()][-1:] or [""]
        gates[name] = {"exit": p.returncode, "tail": tail[0][:160]}
    record("AC-P10-13", "M", "prior tranche gates re-run read-only (P7, P7.1, P8) green", all(g["exit"] == 0 for g in gates.values()),
           gates)
    reg = review() / "regression.json"
    r = json.loads(reg.read_text()) if reg.is_file() else {}
    record("AC-P10-13", "M", "recorded result of the separate live lab-regression step (P0..P2.1 pinned fixtures) is green",
           bool(r.get("ok")), {"file": str(reg.relative_to(root())), "summary": r.get("tail"), "exit": r.get("exit")})
    memo = review() / "close-out-memo.md"
    text = memo.read_text() if memo.is_file() else ""
    record("AC-P10-13", "M", "close-out memo carries the validity partition and the realised interpretation",
           "Validity partition" in text and "Realised interpretation" in text and "only downstream consumer" in text,
           {"memo": str(memo.relative_to(root())), "exists": memo.is_file()})


def completeness() -> None:
    """PA P7: exactly the 210 planned cells; latest attempt per cell; validity partition."""
    from lab_p10 import DEFAULT_K, MODEL_SHORT, PRIMARY_REPS
    from lab_p10_sweep import scale_run_id
    planned = {scale_run_id(t, rep, m, k) for t in SCALE_TARGETS for rep in PRIMARY_REPS
               for m in MODEL_SHORT for k in range(DEFAULT_K)}
    latest = {}
    for line in scaling_runs_path().read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            latest[r["scale_run_id"]] = r
    from collections import Counter
    part = Counter(r["outcome"] for sid, r in latest.items() if sid in planned)
    record("AC-P10-06", "M", "all 210 planned cells present (latest attempt per cell); no unplanned ids",
           set(latest) == planned and len(planned) == 210,
           {"planned": len(planned), "present": len(set(latest) & planned), "missing": len(planned - set(latest)),
            "unplanned": sorted(set(latest) - planned)[:5], "validity_partition": dict(sorted(part.items()))})


def main(argv: list[str]) -> int:
    for fn in (ac01, ac02, ac03, ac04, ac05, completeness, ac06_07, ac08, ac09_10_11, ac12, ac13):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 -- a crashing check is a failing check
            record(fn.__name__, "M", f"{fn.__name__} raised", False, f"{type(exc).__name__}: {exc}"[:300])
    m = [r for r in RESULTS if r["tier"] == "M"]
    a = [r for r in RESULTS if r["tier"] == "A"]
    mp, ap = sum(r["ok"] for r in m), sum(r["ok"] for r in a)
    summary = {"tier_m": f"{mp}/{len(m)}", "tier_a": f"{ap}/{len(a)}", "ok": mp == len(m) and ap == len(a),
               "checks": RESULTS}
    (review() / "gate.json").write_text(json.dumps(summary, indent=1, sort_keys=True, default=str) + "\n")
    print(f"TIER M {mp}/{len(m)} · TIER A {ap}/{len(a)} · TOTAL {mp + ap}/{len(m) + len(a)}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
