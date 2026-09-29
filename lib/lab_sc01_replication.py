"""Named-incident database replication; historical Primary Sweep rows stay separate."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import sys

from lab_fl_analysis import exploratory, table
from lab_fl_study import collect_unit
from lab_paths import evidence_dir, lab_root
from lab_run_common import (DECODING, OUTCOMES, REPS, append, command, incident_id, indexed,
                            json_command, load_rows, logdir, model_registry, read, result_lock,
                            result_path, save, sha, units, utc)


def location(incident):
    incident_id(incident, "SC-01")
    from lab_repr import HEADLINE
    if incident == HEADLINE:
        raise ValueError("use a fresh replication incident; the historical Primary Sweep is read-only")
    return logdir(incident) / "sc01"


def paths(incident):
    base = location(incident)
    files = [lab_root() / "runtime/p9-model-set.json", lab_root() / "etc/arm-b-prompt.txt",
             lab_root() / "lib/lab_regrammar.py", lab_root() / "lib/lab_sc01_replication.py",
             lab_root() / "lib/lab_fl_study.py", lab_root() / "lib/lab_arm_b_score.py",
             lab_root() / "run/optional/sc01-analysis-plan.md"]
    for name in ("answer-grammar.md", "answer-grammar.amendment-1.md"):
        files.append(lab_root() / "sdd/specs/P11-answer-grammar-rescore/contracts" / name)
    files += [base / rep / name for rep in REPS for name in ("model-view.json", "prompt.txt")]
    files += [evidence_dir(incident) / name for name in
              ("incident.json", "snapshots.json", "db.jsonl", "oracle.json", "oracle-manifest.json",
               "workload-manifest.jsonl", "fs_hashes.tsv")]
    files += [evidence_dir(incident) / "p3" / name for name in ("analytics.jsonl", "anomaly.jsonl", "candidates.jsonl")]
    return files


def verify(incident):
    path = location(incident) / "frozen-hashes.json"
    frozen = read(path)
    expected = {os.path.relpath(p, lab_root()): sha(p) for p in paths(incident)}
    if (frozen.get("incident_id") != incident or frozen.get("files") != expected
            or frozen.get("decoding") != DECODING or frozen.get("planned_units") != 45):
        raise ValueError("SC-01 freeze is missing or changed")
    return {**frozen, "sha256": sha(path)}


def database_answer(reply, prompt):
    from lab_regrammar import content_from_text, extract, number
    # R1 explicitly displays a safe LSN under this field name. Index those exact
    # displayed numbers; do not infer unseen window endpoints or commits.
    lines = []
    for line in content_from_text(prompt).splitlines():
        if line.strip().startswith("{"):
            record = json.loads(line)
            if "last_safe_lsn_int" in record:
                value = number(record["last_safe_lsn_int"])
                if "lsn_int" in record and number(record["lsn_int"]) != value:
                    raise ValueError("conflicting displayed recovery positions")
                record["lsn_int"] = value
                line = json.dumps(record)
        lines.append(line)
    answer = extract({"completion": reply, "content": "\n".join(lines)})
    outcome = {"accepted": "accepted", "refusal_parser": "rule_rejection", "refusal_genuine": "declined"}
    return {**answer, "outcome": outcome[answer["grammar_outcome"]]}


def arm(incident, lsn, rep="n/a"):
    from lab_snapshot_coord import resolve_lsn_from_manifest
    from lsn import lsn_norm
    coord = resolve_lsn_from_manifest(incident, lsn_norm(lsn))
    return {"incident_id": read(evidence_dir(incident) / "incident.json")["incident_id"],
            "arm": "arm_b", "selector_version": "revised-grammar", "representation": rep,
            "lsn_text": lsn_norm(lsn), "lsn_int": int(lsn), "wall_clock": coord["wall_clock"],
            "snapshot": coord["snapshot"], "chosen_candidate_id": None, "rationale": "visible locator",
            "selection_inputs": {"ledger_view": "views.analysis_view", "approx_incident_time": None,
                                 "incident_time_error_seconds": None, "read_injection_log": False,
                                 "read_oracle_optimum": False, "read_provenance": False}}


def db_check(incident, coordinate, directory):
    from lab_arm_b_score import p4_score
    from lab_p4_util import restore_root
    marker = directory / "check-started.json"
    cache = restore_root(incident, "ab-" + str(coordinate["lsn_int"])) / "report.json"
    if marker.exists() and not cache.exists():
        return {"checks_complete": False, "failure_reason": "interrupted database check; no implicit retry"}
    if not marker.exists():
        save(marker, {"coordinate": coordinate, "started_utc": utc()}, exclusive=True)
    from lab_fl_check import runtime
    with runtime(incident):
        score = p4_score(incident, coordinate)
    return {"checks_complete": True, "verdict_v1": score["restore_verdict"],
            "damage_rows_retained": score["damage_rows_retained"], "legit_rows_lost": score["legit_rows_lost"],
            "report": str(cache), "report_sha256": sha(cache)}


def gate(incident):
    from lab_modelview_guard import guard
    base = location(incident)
    if (base / "frozen-hashes.json").exists():
        raise ValueError("cannot rebuild frozen SC-01 inputs")
    report = {"ok": False, "incident_id": incident}
    try:
        configured_prompt = os.environ.get("ARM_B_PROMPT_TEMPLATE")
        if configured_prompt and os.path.realpath(configured_prompt) != str(lab_root() / "etc/arm-b-prompt.txt"):
            raise ValueError("SC-01 replication requires the canonical database prompt")
        from lab_fl_check import runtime
        with runtime(incident):
            ledger = json_command("bin/lab-ledger-account", incident)
        if ledger.get("ok") is not True:
            raise ValueError("database ledger reconciliation failed")
        report["ledger"] = ledger
        for name in ("lab-analytics", "lab-anomaly", "lab-candidates"):
            old = os.environ.get("LAB_P7_HOST_COORD")
            try:
                os.environ["LAB_P7_HOST_COORD"] = "1"
                command("bin/" + name, incident)
            finally:
                if old is None:
                    os.environ.pop("LAB_P7_HOST_COORD", None)
                else:
                    os.environ["LAB_P7_HOST_COORD"] = old
        for rep in REPS:
            command("bin/lab-repr-" + rep.lower(), incident)
        for rep in REPS:
            view = json_command("bin/lab-repr-modelview", incident, rep, "PB-6-candidate-windows", '{"top_n":3}')
            guard(view)
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
        for name, lsn, expected in (("reference", reference["lsn"], "correct"),
                                    ("earliest", snaps[0]["recorded_lsn"], "incorrect_safe"),
                                    ("post_damage", post["recorded_lsn"], "incorrect_corrupt")):
            check = db_check(incident, arm(incident, lsn_int(lsn)), base / "controls" / name)
            report["controls"].append({"control": name, "expected": expected, **check})
            if check.get("verdict_v1") != expected:
                raise ValueError("SC-01 control failed: " + name)
        report["ok"] = True
        report["files"] = {os.path.relpath(p, lab_root()): sha(p) for p in paths(incident)}
    finally:
        save(base / "gate.json", report)


def freeze(incident):
    base = location(incident)
    report = read(base / "gate.json")
    files = {os.path.relpath(p, lab_root()): sha(p) for p in paths(incident)}
    if not report.get("ok") or report.get("files") != files:
        raise ValueError("a current passing SC-01 gate is required")
    if result_path(f"sc01-replication-{incident}.jsonl").exists():
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
    path = result_path(f"sc01-replication-{incident}.jsonl")
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
            # Keep verdict v1 distinct from the file-level check schema.
            if row.get("check") and "verdict_v2" in row["check"]:
                row["check"] = {"checks_complete": False, "failure_reason": row["check"].get("failure_reason")}
                save(directory / "finished.json", row)
            append(path, row)
            print(f"Recorded SC-01 {key}: {row['outcome']}", flush=True)


def comparators(incident):
    from lab_snapshot_coord import naive_from_manifest
    from lsn import lsn_int
    frozen = verify(incident)
    path = result_path(f"sc01-comparators-{incident}.jsonl")
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
    records = indexed(load_rows(result_path(f"sc01-replication-{incident}.jsonl")),
                      {u[0] for u in units(models)}, incident, frozen["sha256"])
    comparisons = indexed(load_rows(result_path(f"sc01-comparators-{incident}.jsonl")),
                          {"rank", "naive"}, incident, frozen["sha256"])
    for row in [*records.values(), *comparisons.values()]:
        check = row.get("check") or {}
        if check.get("checks_complete"):
            if check.get("verdict_v1") not in {"correct", "incorrect_safe", "incorrect_corrupt", "not_recovered"}:
                raise ValueError("SC-01 check must use verdict v1")
            if sha(check["report"]) != check["report_sha256"]:
                raise ValueError("SC-01 check report changed after collection")
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
                          **{key: verdicts[key] for key in ("correct", "incorrect_safe", "incorrect_corrupt", "not_recovered")}})
    qrows, pairs, effects = exploratory(records, models)
    complete = (not any(c["missing"] or c["pending_checks"] for c in cells) and len(comparisons) == 2
                and all(r["outcome"] != "accepted" or (r.get("check") or {}).get("checks_complete") for r in comparisons.values()))
    directory = lab_root() / "analysis-out/sc01" / incident
    directory.mkdir(parents=True, exist_ok=True)
    unit_rows = [{"model": row["model_alias"], "input": row["representation"], "repeat": row["replicate_index"],
                  "outcome": row["outcome"], "chosen_lsn_int": (row.get("answer") or {}).get("chosen_lsn_int"),
                  **{key: (row.get("check") or {}).get(key) for key in
                     ("verdict_v1", "damage_rows_retained", "legit_rows_lost", "failure_reason")}}
                 for row in records.values()]
    for name, rows in (("cells", cells), ("comparators", list(comparisons.values())),
                       ("units", unit_rows),
                       ("exploratory-cochran", qrows), ("exploratory-mcnemar", pairs), ("exploratory-effects", effects)):
        table(directory, name, rows)
    save(directory / "summary.json", {"complete": complete, "incident_id": incident, "verdict_version": 1,
                                        "cells": cells, "units": list(records.values()), "comparators": list(comparisons.values()),
                                        "exploratory": {"cochran": qrows, "mcnemar": pairs, "effects": effects}})
    if not complete:
        raise ValueError("SC-01 analysis is incomplete; see summary.json")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident")
    parser.add_argument("--stage", choices=("all", "00", "10", "20", "30", "40", "50", "60", "70"), default="all")
    args = parser.parse_args(argv)
    from lab_run import incident as generate
    try:
        stages = ("00", "10", "20", "30", "40", "50", "60", "70") if args.stage == "all" else (args.stage,)
        name = args.incident
        for stage in stages:
            if stage in ("00", "10"):
                print(command("run/00-provision.sh" if stage == "00" else "run/10-preflight.sh", timeout=7200).stdout)
            elif stage == "20":
                if name:
                    location(name)
                else:
                    name = generate("SC-01")
            else:
                if not name:
                    raise ValueError("--incident is required for stages 30 through 70")
                if stage == "50":
                    print(command("bin/lab-p9-sweep", "--incident", name, "--revised-rules", timeout=86400).stdout)
                else:
                    {"30": gate, "40": freeze, "60": comparators, "70": analysis}[stage](name)
        return 0
    except (Exception, SystemExit) as exc:
        print("SC-01 replication failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
