"""Descriptive tables and explicitly exploratory paired acceptance comparisons."""
from __future__ import annotations

from collections import Counter
import csv
import json
from statistics import median

from lab_fl_check import COUNT_KEYS
from lab_fs_reconcile import timestamp
from lab_p9_statlib import bootstrap_paired_diff, cliffs_delta, cochran_q, holm, mcnemar_exact
from lab_paths import lab_root
from lab_run_common import (OUTCOMES, REPS, VERDICTS, indexed, load_rows, read, result_path,
                            save, sha, units, verify_freeze)

LIMITS = ("Exploratory tests; descriptive outcomes are primary. One incident and five deterministic repeats "
          "per cell are a feasibility study, not independent incident replication or a powered population study. "
          "Known onset defines the baseline; this does not estimate unknown-onset detection. "
          "Inference is limited to this incident, file workload, models and inputs.")


def validate_check(row):
    check = row.get("check")
    if row["outcome"] != "accepted":
        if check is not None:
            raise ValueError("unaccepted unit has a check verdict")
        return
    if not check or not check.get("checks_complete"):
        return
    if check.get("verdict_v2") not in VERDICTS or set(check.get("summary", {})) != set(COUNT_KEYS):
        raise ValueError("invalid verdict v2 check summary")
    values = check["summary"].values()
    if any(v is not None and (type(v) is not int or v < 0) for v in values):
        raise ValueError("invalid check counts")
    if check["verdict_v2"] != "not_recovered" and any(v is None for v in values):
        raise ValueError("successful check has unmeasured counts")
    if check.get("report"):
        if sha(check["report"]) != check["report_sha256"]:
            raise ValueError("check report changed after collection")
        report = read(check["report"])
        if (report.get("incident_id") != row["incident_id"] or report.get("schema_version") != 2
                or report.get("summary") != check["summary"] or report.get("verdict_v2") != check["verdict_v2"]):
            raise ValueError("embedded verdict does not match check report")
        selected = (row.get("answer") or {}).get("snapshot") or (row.get("selection") or {}).get("coordinate", {}).get("snapshot")
        if report.get("coordinate", {}).get("snapshot") != selected:
            raise ValueError("check report is for a different selected snapshot")


def descriptive(records, models):
    cells, losses, unit_rows = [], [], []
    for model in models:
        alias = model["alias"]
        for rep in REPS:
            planned = [f"{alias}|{rep}|{k}" for k in range(5)]
            rows = [records[key] for key in planned if key in records]
            counts = Counter(r["outcome"] for r in rows)
            checked = [r for r in rows if r["outcome"] == "accepted"
                       and r.get("check", {}).get("checks_complete")]
            verdicts = Counter(r["check"]["verdict_v2"] for r in checked)
            cell = {"model": alias, "input": rep, "planned": 5, "recorded": len(rows),
                    "missing": 5 - len(rows), **{key: counts[key] for key in OUTCOMES},
                    **{key: verdicts[key] for key in VERDICTS},
                    "pending_checks": counts["accepted"] - len(checked),
                    "cleanup_failures": sum(bool(r["check"].get("cleanup_error")) for r in checked),
                    "accepted_numerator": counts["accepted"], "accepted_denominator": 5,
                    "correct_numerator": verdicts["correct"], "correct_denominator": 5,
                    "correct_given_accepted_denominator": counts["accepted"],
                    "accepted_rate": counts["accepted"] / 5, "correct_rate": verdicts["correct"] / 5,
                    "correct_given_accepted": verdicts["correct"] / counts["accepted"] if counts["accepted"] else None}
            cells.append(cell)
            for metric in COUNT_KEYS:
                values = [r["check"]["summary"][metric] for r in checked
                          if r["check"]["verdict_v2"] != "not_recovered"
                          and r["check"]["summary"][metric] is not None]
                losses.append({"model": alias, "input": rep, "metric": metric, "n_measured": len(values),
                               "sum": sum(values) if values else None, "median": median(values) if values else None,
                               "min": min(values) if values else None, "max": max(values) if values else None})
            for k, key in enumerate(planned):
                row = records.get(key, {})
                check = row.get("check") or {}
                unit_rows.append({"model": alias, "input": rep, "repeat": k, "unit_id": key,
                                  "outcome": row.get("outcome", "missing"),
                                  "snapshot": (row.get("answer") or {}).get("snapshot"),
                                  "verdict_v2": check.get("verdict_v2") if check.get("checks_complete") else None,
                                  **{metric: check.get("summary", {}).get(metric) for metric in COUNT_KEYS},
                                  "failure_reason": row.get("failure_reason") or check.get("failure_reason")})
    return cells, losses, unit_rows


def exploratory(records, models):
    qrows, pairs, effects, pooled = [], [], [], []
    def excluded_units(aliases, reps):
        rows = [records.get(f"{alias}|{rep}|{k}") for alias in aliases for rep in reps for k in range(5)]
        return {"missing_units": sum(row is None for row in rows),
                "execution_failures": sum(row is not None and row["outcome"] == "execution_failure" for row in rows)}
    for model in models:
        alias = model["alias"]
        blocks = []
        for k in range(5):
            values = []
            for rep in REPS:
                row = records.get(f"{alias}|{rep}|{k}")
                values.append(None if row is None or row["outcome"] == "execution_failure"
                              else int(row["outcome"] == "accepted"))
            blocks.append(values)
        complete = [row for row in blocks if None not in row]
        pooled.extend(complete)
        qrows.append({"model": alias, **cochran_q(complete), "planned_blocks": 5,
                      "excluded_blocks": 5 - len(complete), **excluded_units([alias], REPS)})
        model_pairs = []
        for a, b in ((0, 1), (0, 2), (1, 2)):
            paired = [(row[a], row[b]) for row in blocks if row[a] is not None and row[b] is not None]
            result = mcnemar_exact(sum(x == 1 and y == 0 for x, y in paired),
                                   sum(x == 0 and y == 1 for x, y in paired)) if paired else {
                                       "b": 0, "c": 0, "n_discordant": 0, "p": None}
            model_pairs.append({"model": alias, "comparison": f"{REPS[a]}/{REPS[b]}",
                                "blocks": len(paired), "excluded_blocks": 5 - len(paired),
                                **excluded_units([alias], (REPS[a], REPS[b])), **result})
        # Keep the planned three-comparison family even when a comparison is empty.
        adjusted = holm({row["comparison"]: row["p"] if row["p"] is not None else 1.0 for row in model_pairs})
        for row in model_pairs:
            row.update(adjusted[row["comparison"]] if row["p"] is not None else
                       {"p_raw": None, "p_holm": None, "reject_at_0.05": None})
        pairs.extend(model_pairs)
        paired = [(row[2], row[0]) for row in blocks if row[0] is not None and row[2] is not None]
        effect = bootstrap_paired_diff(paired, seed=42, n_resamples=10000)
        effect.update(cliffs_delta([x for x, _ in paired], [y for _, y in paired]))
        point, lower = effect["point"], effect["ci_low"]
        effects.append({"model": alias, "comparison": "R2-R0", **effect,
                        **excluded_units([alias], ("R0", "R2")),
                        "excluded_blocks": 5 - len(paired), "ci_lower_exceeds_zero": lower > 0 if lower is not None else None,
                        "observed_direction": None if point is None else "R2>R0" if point > 0 else "R2<R0" if point < 0 else "equal"})
    qrows.append({"model": "pooled", **cochran_q(pooled), "planned_blocks": 5 * len(models),
                  **excluded_units([m["alias"] for m in models], REPS),
                  "excluded_blocks": 5 * len(models) - len(pooled)})
    return qrows, pairs, effects


def table(directory, name, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with (directory / (name + ".csv")).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    def cell(value):
        if value is None:
            return "null"
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(keys) + " |", "| " + " | ".join("---" for _ in keys) + " |"]
    lines.extend("| " + " | ".join(cell(row.get(key)) for key in keys) + " |" for row in rows)
    (directory / (name + ".md")).write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyse():
    frozen = verify_freeze()
    incident = frozen["incident_id"]
    models = read(lab_root() / "runtime/p9-model-set.json")["models"]
    planned = units(models)
    path, comparator_path = result_path("fl-study-runs.jsonl"), result_path("fl-comparators.jsonl")
    records = indexed(load_rows(path), {u[0] for u in planned}, incident, frozen["sha256"])
    for key, model, rep, k in planned:
        if key not in records:
            continue
        row = records[key]
        if (row.get("model_alias") != model["alias"] or row.get("representation") != rep
                or row.get("replicate_index") != k or row.get("decoding") != frozen["decoding"]
                or timestamp(row["call_started_utc"]) <= timestamp(frozen["frozen_utc"])):
            raise ValueError("result unit design or call time differs from freeze")
        if row["outcome"] != "execution_failure":
            if sha(row["model_record"]) != row["model_record_sha256"]:
                raise ValueError("retained model reply changed after collection")
            from lab_fl_rules import content_from_text, extract
            reply = read(row["model_record"])
            answer = extract({"completion": row["raw_completion"], "content": content_from_text(reply["prompt"])})
            if (reply.get("containment_verified") is not True or reply.get("completion") != row["raw_completion"]
                    or answer != row.get("answer") or answer["outcome"] != row["outcome"]):
                raise ValueError("recorded answer differs from the retained reply")
        validate_check(row)
    comparator_records = indexed(load_rows(comparator_path), {"rank", "naive"}, incident, frozen["sha256"])
    for row in comparator_records.values():
        validate_check(row)
    cells, losses, unit_rows = descriptive(records, models)
    qrows, pairs, effects = exploratory(records, models)
    comparator_rows = []
    for name in ("rank", "naive"):
        row = comparator_records.get(name, {})
        check = row.get("check") or {}
        comparator_rows.append({"comparator": name, "outcome": row.get("outcome", "missing"),
                                "coordinate": (row.get("selection") or {}).get("coordinate"),
                                "verdict_v2": check.get("verdict_v2") if check.get("checks_complete") else None,
                                **{metric: check.get("summary", {}).get(metric) for metric in COUNT_KEYS},
                                "failure_reason": row.get("failure_reason") or check.get("failure_reason")})
    count_keys = ("planned", "recorded", "missing", *OUTCOMES, *VERDICTS, "pending_checks", "cleanup_failures")
    totals = {key: sum(c[key] for c in cells) for key in count_keys}
    comparator_pending = sum(row["outcome"] == "accepted" and not (row.get("check") or {}).get("checks_complete")
                             for row in comparator_records.values())
    complete = (totals["missing"] == 0 and totals["pending_checks"] == 0 and totals["cleanup_failures"] == 0
                and len(comparator_records) == 2 and comparator_pending == 0
                and not any((r.get("check") or {}).get("cleanup_error") for r in comparator_records.values()))
    out = {"schema_version": 1, "incident_id": incident, "freeze_sha256": frozen["sha256"],
           "complete": complete, "totals": totals, "cells": cells, "losses": losses, "units": unit_rows,
           "missing_units": [key for key, *_ in planned if key not in records],
           "comparators": comparator_rows, "comparator_counts": {
               "planned": 2, "recorded": len(comparator_records), "missing": 2 - len(comparator_records),
               "pending_checks": comparator_pending,
               **{key: sum(row["outcome"] == key for row in comparator_rows) for key in OUTCOMES},
               **{key: sum(row["verdict_v2"] == key for row in comparator_rows) for key in VERDICTS},
               "cleanup_failures": sum(bool((row.get("check") or {}).get("cleanup_error"))
                                       for row in comparator_records.values())},
           "exploratory": {"cochran_q": qrows, "mcnemar_holm": pairs, "R2_minus_R0": effects},
           "source_sha256": {str(p): sha(p) if p.exists() else None for p in (path, comparator_path)},
           "limitations": LIMITS}
    directory = lab_root() / "analysis-out/fl"
    directory.mkdir(parents=True, exist_ok=True)
    for name, rows in (("cells", cells), ("losses", losses), ("units", unit_rows), ("comparators", comparator_rows),
                       ("exploratory-cochran", qrows), ("exploratory-mcnemar", pairs), ("exploratory-effects", effects)):
        table(directory, name, rows)
    save(directory / "summary.json", out)
    (directory / "summary.md").write_text(
        f"File-level study: {'complete' if complete else 'incomplete'}.\n\n"
        f"Planned {totals['planned']}; recorded {totals['recorded']}; missing {totals['missing']}; "
        f"pending checks {totals['pending_checks']}.\n\n" + LIMITS + "\n", encoding="utf-8")
    print(json.dumps({"complete": complete, "totals": totals, "output": str(directory)}, sort_keys=True))
    return out
