"""One durable attempt per planned unit, with restart-safe reply processing."""
from __future__ import annotations

import json

from lab_fl_check import COUNT_KEYS
from lab_paths import evidence_dir
from lab_run_common import (DECODING, OUTCOMES, VERDICTS, append, command, indexed, load_rows,
                            logdir, model_registry, read, result_lock, result_path, save, sha,
                            units, utc, verify_freeze)


def failed_check(reason):
    return {"verdict_v2": "not_recovered", "summary": dict.fromkeys(COUNT_KEYS),
            "failure_reason": reason, "checks_complete": False}


def check_point(incident, snapshot, directory):
    attempt = directory / "check-started.json"
    report = evidence_dir(incident) / "fl-checks" / (snapshot + ".json")
    # A killed restore may have changed a sandbox without finishing a report.
    # Do not launch another restore as an implicit retry.
    if attempt.exists() and not report.exists():
        return failed_check("interrupted check has no report; no automatic restore retry")
    if not attempt.exists():
        save(attempt, {"snapshot": snapshot, "started_utc": utc()}, exclusive=True)
    proc = command("bin/lab-fl-check", incident, snapshot, allowed=(0, 1, 2, 3),
                   out=directory / "check-command.json")
    if not report.exists():
        return failed_check("check produced no report: " + (proc.stderr or proc.stdout))
    checked = read(report)
    if (checked.get("incident_id") != incident or checked.get("coordinate", {}).get("snapshot") != snapshot
            or checked.get("verdict_v2") not in VERDICTS or checked.get("schema_version") != 2):
        raise ValueError("invalid check report")
    # Exit 2/3 can mean a stale report was refused; never import that report.
    if proc.returncode not in (0, 1):
        return failed_check("check refused report reuse: " + (proc.stderr or proc.stdout))
    return {"report": str(report), "report_sha256": sha(report),
            "verdict_v2": checked["verdict_v2"], "summary": checked["summary"],
            "failure_reason": checked.get("failure_reason"), "cleanup_error": checked.get("cleanup_error"),
            "checks_complete": True}


def collect_unit(incident, frozen, model, rep, k, directory, *, verify=None, reader=None, checker=None,
                 prompt_path=None):
    """Shared Primary Sweep collection engine; callbacks select the answer/check rules."""
    from lab_fl_rules import extract, content_from_text
    verify = verify or (lambda: verify_freeze(incident))
    reader = reader or (lambda reply, prompt: extract({"completion": reply, "content": content_from_text(prompt)}))
    checker = checker or (lambda answer: check_point(incident, answer["snapshot"], directory))
    prompt_path = prompt_path or evidence_dir(incident) / "fl-inputs" / rep / "prompt.txt"
    base = {"schema_version": 1, "incident_id": incident, "model_alias": model["alias"],
            "representation": rep, "replicate_index": k, "unit_id": f"{model['alias']}|{rep}|{k}",
            "freeze_sha256": frozen["sha256"], "decoding": DECODING}
    started, finished = directory / "started.json", directory / "finished.json"
    if finished.exists():
        stored = read(finished)
        if any(stored.get(key) != value for key, value in base.items()):
            raise ValueError("journal belongs to a different unit or freeze")
        return stored
    row = dict(base)
    model_json = directory / "model.json"
    answer = None
    if started.exists() and any(read(started).get(key) != value for key, value in base.items()):
        raise ValueError("attempt belongs to another unit or freeze")
    try:
        verify()
        prompt = prompt_path.read_text(encoding="utf-8")
        if started.exists():
            previous = read(started)
            row["call_started_utc"] = previous["call_started_utc"]
            if not model_json.exists():
                raise RuntimeError("interrupted invocation without a saved reply; no replacement call")
        else:
            row["call_started_utc"] = utc()
            from lab_fs_reconcile import timestamp
            if timestamp(row["call_started_utc"]) <= timestamp(frozen["frozen_utc"]):
                raise ValueError("call start must follow freeze time")
            save(started, row, exclusive=True)
            command("bin/lab-p9-model", "--alias", model["alias"], "--prompt-file", prompt_path,
                    "--out", model_json, out=directory / "call-command.json", timeout=1000)
        reply = read(model_json)
        if (reply.get("containment_verified") is not True or reply.get("model_alias") != model["alias"]
                or reply.get("prompt") != prompt or reply.get("model_digest") != model["model_digest"]
                or any(reply.get(key) != value for key, value in DECODING.items())):
            raise ValueError("model response identity, prompt, decoding or containment mismatch")
        completion = reply["completion"]
        (directory / "completion.txt").write_text(completion, encoding="utf-8")
        row.update(model_record=str(model_json), model_record_sha256=sha(model_json),
                   raw_completion=completion, prompt_sha256=reply["prompt_sha256"],
                   completion_tokens=reply.get("completion_tokens"), prompt_tokens=reply.get("prompt_tokens"),
                   latency_ms=reply.get("latency_ms"), containment_verified=True)
        answer = reader(completion, prompt)
        save(directory / "answer.json", answer)
        if answer["outcome"] not in OUTCOMES[:3]:
            raise ValueError("invalid answer outcome")
        row.update(outcome=answer["outcome"], answer=answer, check=None)
        if answer["outcome"] == "accepted":
            row["check"] = checker(answer)
    except (Exception, SystemExit) as exc:
        # Acceptance is an answer property even if its restore cannot complete.
        if answer and answer.get("outcome") == "accepted":
            row.update(outcome="accepted", answer=answer, check=failed_check(str(exc)))
        else:
            row.update(outcome="execution_failure", failure_reason=str(exc), check=None)
    row["finished_utc"] = utc()
    save(finished, row, exclusive=True)
    return row


def study(incident):
    from lab_run import require_gate
    require_gate(incident)
    frozen = verify_freeze(incident)
    models = model_registry()["models"]
    planned = units(models)
    path = result_path("fl-study-runs.jsonl")
    with result_lock(path):
        done = indexed(load_rows(path), {u[0] for u in planned}, incident, frozen["sha256"])
        for key, model, rep, k in planned:
            if key in done:
                print("Already recorded: " + key, flush=True)
                continue
            # Contract drift is a batch precondition, not an execution-failure observation.
            verify_freeze(incident)
            directory = logdir(incident) / "units" / model["slot"] / rep / f"k{k}"
            row = collect_unit(incident, frozen, model, rep, k, directory)
            append(path, row)
            print(f"Recorded {key}: {row['outcome']}", flush=True)


def comparators(incident):
    from lab_run import require_gate
    require_gate(incident)
    frozen = verify_freeze(incident)
    path = result_path("fl-comparators.jsonl")
    with result_lock(path):
        done = indexed(load_rows(path), {"rank", "naive"}, incident, frozen["sha256"])
        for name in ("rank", "naive"):
            if name in done:
                print("Already recorded: " + name)
                continue
            verify_freeze(incident)
            directory = logdir(incident) / "comparators" / name
            finished = directory / "finished.json"
            if finished.exists():
                row = read(finished)
                indexed([row], {name}, incident, frozen["sha256"])
            else:
                row = {"schema_version": 1, "unit_id": name, "incident_id": incident,
                       "freeze_sha256": frozen["sha256"], "started_utc": utc(), "check": None}
                try:
                    proc = command("bin/lab-fl-" + name, incident, allowed=(0, 1),
                                   out=directory / "selection-command.json")
                    selection = json.loads(proc.stdout)
                    row["selection"] = selection
                    if selection["outcome"] != "accepted":
                        row.update(outcome="execution_failure", failure_reason=selection["reason"])
                    else:
                        row["outcome"] = "accepted"
                        row["check"] = check_point(incident, selection["coordinate"]["snapshot"], directory)
                except (Exception, SystemExit) as exc:
                    if row.get("outcome") == "accepted":
                        row["check"] = failed_check(str(exc))
                    else:
                        row.update(outcome="execution_failure", failure_reason=str(exc))
                save(finished, row, exclusive=True)
            append(path, row)
            print(f"Recorded comparator {name}: {row['outcome']}", flush=True)
