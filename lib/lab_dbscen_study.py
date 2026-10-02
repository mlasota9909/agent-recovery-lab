"""P13: the SC-03 and SC-04 studies, with the SC-01 replication's method and separate records per scenario.

Inputs, prompt, answer-reading rules, models, decoding, repeats, comparators and analysis are the SC-01 replication's
(lab_sc01_replication.py, frozen and unchanged). The scenario-specific parts are the generator
(lab_generate_dbscen.py), the checker (lab_validate_dbscen.py) and three gate checks that refuse a broken incident:
analytics windows out of order or too long, an empty input, or damage missing from the evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import sys

from lab_fl_analysis import exploratory, table
from lab_fl_study import collect_unit
from lab_paths import evidence_dir, lab_root
from lab_run_common import (DECODING, OUTCOMES, REPS, append, command, incident_id, indexed, json_command,
                            load_rows, logdir, model_registry, read, result_lock, result_path, run_scope, save,
                            sha, units, utc)
from lab_sc01_replication import arm, database_answer

SCENARIOS = {"SC-03": "sc03", "SC-04": "sc04"}
WINDOW_SPAN_LIMIT_S = 4.0   # twice the 2-second window of etc/scenarios/sc01.env
VERDICTS = ("correct", "incorrect_safe", "incorrect_corrupt", "not_recovered")


def scenario_of(incident):
    scenario = str(incident).split("_", 1)[0]
    if scenario not in SCENARIOS:
        raise ValueError("expected an SC-03 or SC-04 incident identifier")
    return incident_id(incident, scenario)


def tag(incident):
    return SCENARIOS[scenario_of(incident).split("_", 1)[0]]


def location(incident):
    return logdir(incident) / tag(incident)


def results_name(incident, kind):
    return f"{tag(incident)}-{kind}-{incident}.jsonl"


def paths(incident):
    base = location(incident)
    files = [lab_root() / "runtime/p9-model-set.json", lab_root() / "etc/arm-b-prompt.txt",
             lab_root() / "lib/lab_regrammar.py", lab_root() / "lib/lab_sc01_replication.py",
             lab_root() / "lib/lab_fl_study.py", lab_root() / "lib/lab_dbscen_study.py",
             lab_root() / "lib/lab_generate_dbscen.py", lab_root() / "lib/lab_validate_dbscen.py",
             lab_root() / "run/optional/sc03-sc04-analysis-plan.md"]
    for name in ("answer-grammar.md", "answer-grammar.amendment-1.md"):
        files.append(lab_root() / "sdd/specs/P11-answer-grammar-rescore/contracts" / name)
    files += [base / rep / name for rep in REPS for name in ("model-view.json", "prompt.txt")]
    files += [evidence_dir(incident) / name for name in
              ("incident.json", "snapshots.json", "db.jsonl", "oracle.json", "oracle-manifest.json",
               "workload.jsonl", "workload-manifest.jsonl", "injection.json", "fs_hashes.tsv")]
    files += [evidence_dir(incident) / "p3" / name for name in ("analytics.jsonl", "anomaly.jsonl")]
    # Candidates exist only when a window is flagged; the ranker then has nothing to choose from (stage 60).
    candidates = evidence_dir(incident) / "p3" / "candidates.jsonl"
    if candidates.exists():
        files.append(candidates)
    return files


def verify(incident):
    path = location(incident) / "frozen-hashes.json"
    frozen = read(path)
    expected = {os.path.relpath(p, lab_root()): sha(p) for p in paths(incident)}
    if (frozen.get("incident_id") != incident or frozen.get("files") != expected
            or frozen.get("decoding") != DECODING or frozen.get("planned_units") != 45):
        raise ValueError(f"{scenario_of(incident)[:5]} freeze is missing or changed")
    return {**frozen, "sha256": sha(path)}


def dbscen_score(incident, coordinate):
    """Restore the point into a sandbox, compare it with the reference and assemble the report (as p4_score)."""
    from lab_arm_b_score import reject_peek, score_from_report
    from lab_p3_util import run_bin
    from lab_p4_util import restore_root, write_json
    reject_peek(coordinate)
    restore_of = f"ab-{int(coordinate['lsn_int'])}"
    root = restore_root(incident, restore_of)
    report_path = root / "report.json"
    if report_path.is_file():
        return score_from_report(json.loads(report_path.read_text(encoding="utf-8")), cached=True)
    coord_path = root / "arm-coordinate.json"
    coord_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(coord_path, coordinate)
    proc = run_bin("lab-restore", [incident, str(coord_path), "--restore-of", restore_of])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "lab-restore failed")
    try:
        for name in ("lab-validate-dbscen", "lab-verdict"):
            proc = run_bin(name, [incident, restore_of])
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or f"{name} failed")
        return score_from_report(json.loads(report_path.read_text(encoding="utf-8")), cached=False)
    finally:
        run_bin("lab-restore", [incident, str(coord_path), "--restore-of", restore_of, "--teardown"])


def db_check(incident, coordinate, directory):
    from lab_fl_check import runtime
    from lab_p4_util import restore_root
    marker = directory / "check-started.json"
    cache = restore_root(incident, "ab-" + str(coordinate["lsn_int"])) / "report.json"
    if marker.exists() and not cache.exists():
        return {"checks_complete": False, "failure_reason": "interrupted database check; no implicit retry"}
    if not marker.exists():
        save(marker, {"coordinate": coordinate, "started_utc": utc()}, exclusive=True)
    with runtime(incident):
        score = dbscen_score(incident, coordinate)
    return {"checks_complete": True, "verdict_v1": score["restore_verdict"],
            "damage_units_retained": score["damage_rows_retained"], "legit_rows_lost": score["legit_rows_lost"],
            "report": str(cache), "report_sha256": sha(cache)}


def window_problems(windows):
    """Refuse windows that are out of order, negative or longer than twice the window length."""
    from datetime import datetime
    problems = []
    ids = [w["window_id"] for w in windows]
    if not ids or ids != sorted(ids) or ids[0] < 0:
        problems.append("windows are not numbered from zero in order")
    previous = None
    for w in windows:
        if not w.get("t_start") or not w.get("t_end"):
            continue
        start = datetime.fromisoformat(w["t_start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(w["t_end"].replace("Z", "+00:00"))
        if (end - start).total_seconds() > WINDOW_SPAN_LIMIT_S:
            problems.append(f"window {w['window_id']} spans {(end - start).total_seconds():.1f} s")
        if previous is not None and start < previous:
            problems.append(f"window {w['window_id']} starts before the previous one")
        previous = start
    return problems


def damage_in_evidence(incident):
    """Every injected operation must be an evidence event; returns (injected, found)."""
    from lab_repr import load_blind_events
    injection = read(evidence_dir(incident) / "injection.json")
    xids = [int(op["xid"]) & 0xFFFFFFFF for op in injection["ops"]]
    events, _ = load_blind_events(incident)
    found = Counter(int(e["xid"]) & 0xFFFFFFFF for e in events if e.get("xid") is not None)
    return len(xids), sum(1 for x in xids if found[x] > 0)


def first_damage_position(incident):
    """The log position of the first damaging change record, inside its transaction and before its commit."""
    from lab_repr import load_blind_events
    from lsn import lsn_int, lsn_norm
    injection = read(evidence_dir(incident) / "injection.json")
    first = min(injection["ops"], key=lambda o: lsn_int(lsn_norm(o["commit_lsn"])))
    xid = int(first["xid"]) & 0xFFFFFFFF
    events, _ = load_blind_events(incident)
    positions = [int(e["lsn_int"]) for e in events if e.get("xid") is not None and (int(e["xid"]) & 0xFFFFFFFF) == xid]
    if not positions:
        raise ValueError("the first damaging change is not in the evidence")
    return min(positions)


def damage_shown(incident, view):
    """Information only: does an input show a position at or after the first damaging commit?"""
    from lsn import lsn_int, lsn_norm
    first = lsn_int(lsn_norm(read(evidence_dir(incident) / "oracle.json")["first_damage_commit_lsn"]))
    positions = []
    for line in str(view.get("content") or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            record = json.loads(line)
            for key in ("lsn_int", "last_safe_lsn_int"):
                if key in record:
                    positions.append(int(record[key]))
        elif line.startswith("Window ") and "[" in line:
            span = line.split("[", 1)[1].split("]", 1)[0]
            positions += [int(x) for x in span.split("..") if x.strip().isdigit()]
    return any(p >= first for p in positions)


def gate(incident):
    from lab_modelview_guard import guard
    base = location(incident)
    if (base / "frozen-hashes.json").exists():
        raise ValueError("cannot rebuild frozen inputs")
    report = {"ok": False, "incident_id": incident}
    try:
        configured_prompt = os.environ.get("ARM_B_PROMPT_TEMPLATE")
        if configured_prompt and os.path.realpath(configured_prompt) != str(lab_root() / "etc/arm-b-prompt.txt"):
            raise ValueError("the studies require the canonical database prompt")
        from lab_fl_check import runtime
        with runtime(incident):
            ledger = json_command("bin/lab-ledger-account", incident)
        if ledger.get("ok") is not True:
            raise ValueError("database ledger reconciliation failed")
        report["ledger"] = ledger
        injected, found = damage_in_evidence(incident)
        report["damage_in_evidence"] = {"injected": injected, "found": found}
        if injected == 0 or found != injected:
            raise ValueError(f"damaging operations missing from the evidence: {found} of {injected}")
        # A candidates file from an earlier gate attempt must not survive a run that flags no window.
        (evidence_dir(incident) / "p3" / "candidates.jsonl").unlink(missing_ok=True)
        for name in ("lab-analytics", "lab-anomaly", "lab-candidates"):
            old = os.environ.get("LAB_P7_HOST_COORD")
            try:
                os.environ["LAB_P7_HOST_COORD"] = "1"
                command("bin/" + name, incident)
                if name == "lab-candidates":
                    report["candidates"] = {"ok": True}
            except RuntimeError as exc:
                # Same rule as SC-01: no window at or above the threshold leaves the ranker without candidates.
                if name != "lab-candidates" or "no anomalous window" not in str(exc):
                    raise
                report["candidates"] = {"ok": False, "reason": "no anomalous window"}
            finally:
                if old is None:
                    os.environ.pop("LAB_P7_HOST_COORD", None)
                else:
                    os.environ["LAB_P7_HOST_COORD"] = old
        windows = [json.loads(line) for line in (evidence_dir(incident) / "p3/analytics.jsonl").read_text().splitlines()
                   if line.strip()]
        problems = window_problems(windows)
        report["windows"] = {"count": len(windows), "problems": problems}
        if problems:
            raise ValueError("analytics windows refused: " + "; ".join(problems[:5]))
        for rep in REPS:
            command("bin/lab-repr-" + rep.lower(), incident)
        report["damage_shown"] = {}
        for rep in REPS:
            view = json_command("bin/lab-repr-modelview", incident, rep, "PB-6-candidate-windows", '{"top_n":3}')
            guard(view)
            if not str(view.get("content") or "").strip():
                raise ValueError(f"{rep} input is empty")
            report["damage_shown"][rep] = damage_shown(incident, view)
            save(base / rep / "model-view.json", view)
            command("bin/lab-arm-b-prompt", "--incident", incident, "--representation", rep,
                    "--out", base / rep / "prompt.txt")
        from lab_fl_intervals import snapshot_records
        from lab_fs_reconcile import timestamp
        from lsn import lsn_int
        snaps = snapshot_records(read(evidence_dir(incident) / "snapshots.json"))
        end = timestamp(read(evidence_dir(incident) / "injection.json")["t_end"])
        post = next(s for s in snaps if timestamp(s["created_at"]) > end)
        reference = read(evidence_dir(incident) / "oracle.json")["coordinate"]
        report["controls"] = []
        # The second control stops inside the first damaging transaction: an uncommitted change is not in the copy.
        for name, position, expected in (("reference", lsn_int(reference["lsn"]), "correct"),
                                         ("inside_damage", first_damage_position(incident), "correct"),
                                         ("earliest", lsn_int(snaps[0]["recorded_lsn"]), "incorrect_safe"),
                                         ("post_damage", lsn_int(post["recorded_lsn"]), "incorrect_corrupt")):
            check = db_check(incident, arm(incident, position), base / "controls" / name)
            report["controls"].append({"control": name, "expected": expected, **check})
            if check.get("verdict_v1") != expected:
                raise ValueError("control failed: " + name)
        report["ok"] = True
        report["files"] = {os.path.relpath(p, lab_root()): sha(p) for p in paths(incident)}
    finally:
        save(base / "gate.json", report)


def freeze(incident):
    base = location(incident)
    report = read(base / "gate.json")
    files = {os.path.relpath(p, lab_root()): sha(p) for p in paths(incident)}
    if not report.get("ok") or report.get("files") != files:
        raise ValueError("a current passing gate is required")
    if result_path(results_name(incident, "study")).exists():
        raise ValueError("cannot freeze after study collection")
    model_registry()
    pre = read(logdir() / "preflight.json")
    if not pre.get("ok") or pre.get("model_set_sha256") != sha(lab_root() / "runtime/p9-model-set.json"):
        raise ValueError("passing preflight required")
    save(base / "frozen-hashes.json", {"incident_id": incident, "frozen_utc": utc(), "files": files,
                                       "decoding": DECODING, "planned_units": 45}, exclusive=True)


def study(incident):
    frozen = verify(incident)
    planned = units(model_registry()["models"])
    path = result_path(results_name(incident, "study"))
    with result_lock(path):
        done = indexed(load_rows(path), {u[0] for u in planned}, incident, frozen["sha256"])
        for key, model, rep, k in planned:
            if key in done:
                continue
            verify(incident)
            directory = location(incident) / "units" / model["slot"] / rep / f"k{k}"
            row = collect_unit(incident, frozen, model, rep, k, directory,
                               verify=lambda: verify(incident), reader=database_answer,
                               checker=lambda answer: db_check(incident, arm(incident, answer["chosen_lsn_int"], rep), directory),
                               prompt_path=location(incident) / rep / "prompt.txt")
            if row.get("check") and "verdict_v2" in row["check"]:
                row["check"] = {"checks_complete": False, "failure_reason": row["check"].get("failure_reason")}
                save(directory / "finished.json", row)
            append(path, row)
            print(f"Recorded {scenario_of(incident)[:5]} {key}: {row['outcome']}", flush=True)


def comparators(incident):
    from lab_snapshot_coord import naive_from_manifest
    from lsn import lsn_int
    frozen = verify(incident)
    path = result_path(results_name(incident, "comparators"))
    with result_lock(path):
        done = indexed(load_rows(path), {"rank", "naive"}, incident, frozen["sha256"])
        for name in ("rank", "naive"):
            if name in done:
                continue
            directory = location(incident) / "comparators" / name
            finished = directory / "finished.json"
            if finished.exists():
                row = read(finished)
                indexed([row], {name}, incident, frozen["sha256"])
            else:
                row = {"unit_id": name, "incident_id": incident, "freeze_sha256": frozen["sha256"], "check": None}
                try:
                    if name == "rank":
                        coord = json_command("bin/lab-rank", incident)["coordinate"]
                    else:
                        meta = read(evidence_dir(incident) / "incident.json")
                        resolved = naive_from_manifest(incident, meta["approx_incident_time"], 20)
                        coord = arm(incident, lsn_int(resolved["lsn"]))
                    row.update(outcome="accepted", coordinate=coord)
                    row["check"] = db_check(incident, coord, directory)
                except (Exception, SystemExit) as exc:
                    if row.get("outcome") == "accepted":
                        row["check"] = {"checks_complete": False, "failure_reason": str(exc)}
                    else:
                        row.update(outcome="execution_failure", failure_reason=str(exc))
                save(finished, row, exclusive=True)
            append(path, row)


def analysis(incident):
    frozen = verify(incident)
    models = read(lab_root() / "runtime/p9-model-set.json")["models"]
    records = indexed(load_rows(result_path(results_name(incident, "study"))),
                      {u[0] for u in units(models)}, incident, frozen["sha256"])
    comparisons = indexed(load_rows(result_path(results_name(incident, "comparators"))),
                          {"rank", "naive"}, incident, frozen["sha256"])
    for row in [*records.values(), *comparisons.values()]:
        check = row.get("check") or {}
        if check.get("checks_complete"):
            if check.get("verdict_v1") not in VERDICTS:
                raise ValueError("checks must use verdict v1")
            if sha(check["report"]) != check["report_sha256"]:
                raise ValueError("check report changed after collection")
    cells = []
    for model in models:
        for rep in REPS:
            rows = [records[key] for key in (f"{model['alias']}|{rep}|{k}" for k in range(5)) if key in records]
            counts = Counter(r["outcome"] for r in rows)
            checks = [r["check"] for r in rows if r.get("check") and r["check"].get("checks_complete")]
            verdicts = Counter(c["verdict_v1"] for c in checks)
            cells.append({"model": model["alias"], "input": rep, "planned": 5, "missing": 5 - len(rows),
                          **{key: counts[key] for key in OUTCOMES}, "pending_checks": counts["accepted"] - len(checks),
                          "accepted_rate": counts["accepted"] / 5, "correct_rate": verdicts["correct"] / 5,
                          "correct_given_accepted": verdicts["correct"] / counts["accepted"] if counts["accepted"] else None,
                          **{key: verdicts[key] for key in VERDICTS}})
    qrows, pairs, effects = exploratory(records, models)
    complete = (not any(c["missing"] or c["pending_checks"] for c in cells) and len(comparisons) == 2
                and all(r["outcome"] != "accepted" or (r.get("check") or {}).get("checks_complete") for r in comparisons.values()))
    directory = lab_root() / "analysis-out" / tag(incident) / incident
    directory.mkdir(parents=True, exist_ok=True)
    unit_rows = [{"model": row["model_alias"], "input": row["representation"], "repeat": row["replicate_index"],
                  "outcome": row["outcome"], "chosen_lsn_int": (row.get("answer") or {}).get("chosen_lsn_int"),
                  **{key: (row.get("check") or {}).get(key) for key in
                     ("verdict_v1", "damage_units_retained", "legit_rows_lost", "failure_reason")}}
                 for row in records.values()]
    for name, rows in (("cells", cells), ("comparators", list(comparisons.values())), ("units", unit_rows),
                       ("exploratory-cochran", qrows), ("exploratory-mcnemar", pairs), ("exploratory-effects", effects)):
        table(directory, name, rows)
    save(directory / "summary.json", {"complete": complete, "incident_id": incident, "verdict_version": 1,
                                        "cells": cells, "units": list(records.values()), "comparators": list(comparisons.values()),
                                        "exploratory": {"cochran": qrows, "mcnemar": pairs, "effects": effects}})
    if not complete:
        raise ValueError("analysis is incomplete; see summary.json")


def generate(scenario):
    from lab_run import ensure_no_open_incident
    ensure_no_open_incident()
    scope = logdir() / SCENARIOS[scenario]
    marker = scope / "incident-started.json"
    if marker.exists():
        raise ValueError("incident generation was already attempted; inspect " + str(marker.relative_to(lab_root())))
    if (scope / "latest-incident.json").exists():
        raise ValueError("this run already has an incident; resume its numbered stages")
    save(marker, {"scenario": scenario, "started_utc": utc()}, exclusive=True)
    output = json_command("bin/lab-generate-dbscen", "--scenario", scenario, out=scope / "incident-generation.json",
                          timeout=3600)
    name = incident_id(output["archive_incident"], scenario)
    save(scope / "latest-incident.json", {"incident_id": name, "scenario": scenario}, exclusive=True)
    print(name, flush=True)
    return name


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=tuple(SCENARIOS), required=True)
    parser.add_argument("--incident")
    parser.add_argument("--stage", choices=("all", "00", "10", "20", "30", "40", "50", "60", "70"), default="all")
    args = parser.parse_args(argv)
    try:
        stages = ("00", "10", "20", "30", "40", "50", "60", "70") if args.stage == "all" else (args.stage,)
        if run_scope() != "run" and set(stages) - {"20", "30"}:
            raise ValueError("a dry-run scope runs only the incident and gate stages")
        name = args.incident
        if name and not name.startswith(args.scenario + "_"):
            raise ValueError("--incident does not belong to --scenario")
        for stage in stages:
            if stage in ("00", "10"):
                print(command("run/00-provision.sh" if stage == "00" else "run/10-preflight.sh", timeout=7200).stdout)
            elif stage == "20":
                name = name or generate(args.scenario)
                location(name)
            else:
                if not name:
                    raise ValueError("--incident is required for stages 30 through 70")
                {"30": gate, "40": freeze, "50": study, "60": comparators, "70": analysis}[stage](name)
        return 0
    except (Exception, SystemExit) as exc:
        print(f"{args.scenario} study failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
