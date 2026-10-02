"""lab-generate-dbscen: one reconciled SC-03 or SC-04 incident in an isolated cluster (P13).

Follows lab-generate-p7 for isolation, capture, snapshots, file evidence and reconciliation, and the SC-01 generator
for timing and records, with three differences from the earlier SC-03/SC-04 path:
- the scenario table is seeded before the open snapshot, so the seed is outside the captured window;
- baseline, after-injection and window settings are SC-01's (etc/scenarios/sc01.env);
- every injected operation is written to workload.jsonl, so reconciliation must map the damage and the evidence
  events include it, exactly as for SC-01.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from lab_generate_p7 import empty_ledger_files, freeze_common
from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, env, require_lab, results_incident_id, run_bin, run_json,
    scenario_config, ssh_psql, utc_now, write_json, write_jsonl,
)
from lab_paths import evidence_dir, lab_root
from lab_p7 import HEADLINE, resolve_lsn
from lab_sc01_workload import ConcurrentApp, apply_group, ensure_sc01_seed, plan_sc01_ddl
from lab_scenario import load_definition
from lsn import lsn_int, lsn_norm

SCENARIOS = ("SC-03", "SC-04")
SC03_TABLE = "sc03_orders"
SC04_TABLE = "sc04_items"


def scenario_module(scenario: str):
    if scenario == "SC-03":
        import lab_sc03 as module
    elif scenario == "SC-04":
        import lab_sc04 as module
    else:
        die(EXIT_USAGE, "usage: lab-generate-dbscen --scenario SC-03|SC-04")
    return module


def injected_workload_rows(scenario: str, injection: dict) -> list[dict]:
    """The injected operations in the workload-record shape that reconciliation keys on."""
    rows = []
    for op in injection["ops"]:
        common = {"principal": op["principal"], "xid": int(op["xid"]) & 0xFFFFFFFF,
                  "commit_lsn": lsn_norm(op["commit_lsn"]), "injected": True}
        if scenario == "SC-03":
            rows.append({**common, "action": "ALTER", "command_tag": "ALTER TABLE",
                         "object_identity": f"public.{SC03_TABLE}", "table": SC03_TABLE, "natural_key": None,
                         "wall_clock": op["t_end"]})
        else:
            rows.append({**common, "action": "U", "table": SC04_TABLE, "natural_key": int(op["row_id"]),
                         "wall_clock": op["t"]})
    return rows


def legitimate_manifest(rows: list[dict]) -> list[dict]:
    """Every legitimate data change, as for SC-01's workload-manifest.jsonl."""
    out = []
    for rec in rows:
        if rec.get("injected") or not rec.get("commit_lsn") or rec.get("action") not in {"I", "U", "D"}:
            continue
        out.append({
            "commit_lsn": rec["commit_lsn"],
            "commit_ts": rec.get("wall_clock"),
            "operation": rec.get("operation"),
            "relation": rec.get("relation") or rec.get("table"),
            "row_ids": rec.get("row_ids") or ([rec["natural_key"]] if rec.get("natural_key") is not None else []),
            "row_count": rec.get("row_count") or 1,
            "principal": rec.get("principal"),
        })
    return out


def combined_workload(*groups: list[dict]) -> list[dict]:
    combined = [dict(rec) for group in groups for rec in group]
    combined.sort(key=lambda r: (lsn_int(r["commit_lsn"]) if r.get("commit_lsn") else 0, r.get("xid") or 0,
                                 str(r.get("natural_key") if r.get("natural_key") is not None else "")))
    for i, rec in enumerate(combined):
        rec["op_index"] = i
    return combined


def workload_record(rec: dict) -> dict:
    return {k: v for k, v in rec.items()
            if k not in {"operation", "row_ids", "row_count", "relation", "commit_lsn", "injected"}}


def damage_manifest(scenario: str, injection: dict) -> dict:
    ops = injection["ops"]
    if scenario == "SC-03":
        return {"table": SC03_TABLE, "units": [
            {"unit": "status_column_dropped", "statement": ops[0]["sql"], "commit_lsn": lsn_norm(ops[0]["commit_lsn"])},
            {"unit": "amount_rule_dropped", "statement": ops[1]["sql"], "commit_lsn": lsn_norm(ops[1]["commit_lsn"])},
            {"unit": "amount_type_changed", "statement": ops[2]["sql"], "commit_lsn": lsn_norm(ops[2]["commit_lsn"])},
        ]}
    return {"table": SC04_TABLE, "units": [
        {"unit": f"row_{int(op['row_id'])}", "row_id": int(op["row_id"]), "damaging_value": f"mal-{int(op['row_id'])}",
         "commit_lsn": lsn_norm(op["commit_lsn"])} for op in ops]}


def write_reference(incident: str, scenario: str, injection: dict) -> dict:
    """The reference is the position the injection recorded just before its first damaging statement."""
    ed = evidence_dir(incident)
    first = min(injection["ops"], key=lambda o: lsn_int(lsn_norm(o["commit_lsn"])))
    before = lsn_norm(injection["ops"][0]["lsn_before"])
    if lsn_int(before) >= lsn_int(lsn_norm(first["commit_lsn"])):
        die(EXIT_ASSERT, "assertion failed: reference is not before the first damaging commit")
    coordinate = resolve_lsn(before)
    damage = damage_manifest(scenario, injection)
    write_json(ed / "oracle.json", {"incident": incident, "scenario_id": scenario, "coordinate": coordinate,
                                    "computed_from": "injection ops[0].lsn_before, resolved with lab-coordinate",
                                    "first_damage_commit_lsn": lsn_norm(first["commit_lsn"]), "damage": damage})
    write_json(ed / "oracle-manifest.json", {"incident": incident, "scenario_id": scenario,
                                             "optimum_lsn": before, "first_damage_commit_lsn": lsn_norm(first["commit_lsn"]),
                                             "damage": damage})
    return coordinate


def generate(scenario: str, log: list[dict]) -> dict:
    require_lab()
    if scenario not in SCENARIOS:
        die(EXIT_USAGE, "usage: lab-generate-dbscen --scenario SC-03|SC-04")
    cfg = scenario_config()
    module = scenario_module(scenario)
    def_path = lab_root() / "scenarios" / scenario.lower().replace("-", "") / "definition.json"
    definition = load_definition(def_path)
    t0 = time.monotonic()

    def add(entry: dict) -> None:
        entry["elapsed_ms"] = int(round((time.monotonic() - t0) * 1000))
        log.append(entry)

    port_base = int(env("INCIDENT_PORT_BASE"))
    if (os.environ.get("LAB_ACTIVE_INCIDENT") or os.environ.get("LAB_SITE_SCOPE") != "1"
            or "/inc_" in env("DS_PARENT")
            or port_base <= int(env("PG_PORT")) < port_base + int(env("INCIDENT_PORT_COUNT"))):
        die(EXIT_PRECOND, "precondition failed: generation must start from the site cluster, "
                          "not from an incident runtime")
    ensure_sc01_seed()
    relation = cfg.get("SC01_RELATION", "p2_probe")
    cleanup = ssh_psql(f"DELETE FROM public.{relation} WHERE id >= 88000000; DROP TABLE IF EXISTS public.p2_alt;")
    if cleanup.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: key-range cleanup: {cleanup.stderr.strip()}")
    cur = Path(env("ARCHIVE_CURRENT"))
    if cur.exists() or cur.is_symlink():
        old = cur.resolve().name
        if old and old != HEADLINE:
            run_bin("lab-consumer", ["stop", old], timeout=60)
            add({"step": 0, "action": "stop_throwaway_consumer", "incident": old})
    from lab_incident_runtime import stop_finished_incident_clusters
    for stopped in stop_finished_incident_clusters():
        add({"step": 0, "action": "stop_finished_incident_cluster", "result": stopped})
    slot = run_json("lab-slot", ["--create"], timeout=90)
    add({"step": 0, "action": "slot_ensure", "result": slot})
    allocated = run_json("lab-incident", ["--new", "--scenario", scenario])
    incident = allocated["incident"]
    if not incident.startswith(scenario + "_"):
        die(EXIT_ASSERT, f"assertion failed: allocator returned {incident!r} for {scenario}")
    add({"step": 1, "action": "incident_new", "result": allocated})
    iid = results_incident_id(incident)
    isolated = run_json("lab-incident-dataset", ["create", "--incident", incident, "--id", iid], timeout=600)
    runtime = Path(isolated["runtime"])
    for raw in runtime.read_text(encoding="utf-8").splitlines():
        if raw and "=" in raw:
            key, value = raw.split("=", 1)
            os.environ[key] = value
    os.environ.pop("LAB_SITE_SCOPE", None)
    os.environ.update({
        "LAB_ACTIVE_INCIDENT": incident,
        "DS_PARENT": os.environ["INC_DS"],
        "DS_PGDATA": os.environ["INC_DS"] + "/pgdata",
        "DS_PROTECTED": os.environ["INC_DS"] + "/protected",
        "PG_DATA": os.environ["INC_PGDATA"],
        "PG_PORT": os.environ["INC_PG_PORT"],
        "MNT_PROTECTED": os.environ["INC_PROTECTED"],
        "SLOT_NAME": os.environ["INC_SLOT"],
    })
    add({"step": 1, "action": "incident_isolation", "result": isolated})
    consumer = run_bin("lab-consumer", ["start", incident], timeout=120)
    if consumer.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: isolated consumer: {consumer.stderr.strip() or consumer.stdout.strip()}")
    empty_ledger_files(incident)
    heartbeat = run_bin("lab-heartbeat", ["--start"], timeout=60)
    add({"step": 1, "action": "heartbeat_start", "exit": heartbeat.returncode})
    if heartbeat.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: lab-heartbeat --start: {heartbeat.stderr.strip() or heartbeat.stdout.strip()}")
    for attempt in range(45):
        if run_bin("lab-ready", [], timeout=30).returncode == 0:
            break
        time.sleep(2)
    else:
        die(EXIT_PRECOND, "precondition failed: lab-ready never reached 0 after incident allocation")
    add({"step": 1, "action": "lab_ready_wait", "attempts": attempt + 1})

    # Seed the scenario table before the open snapshot: outside the captured window, inside every snapshot.
    prep = module.prepare(incident)
    add({"step": 0, "action": "prepare", "result": {k: v for k, v in prep.items() if k != "baseline_started"}})
    open_snap = run_json("lab-snapshot", ["--label", "open", "--incident", incident])
    add({"step": 3, "action": "snapshot_open", "result": open_snap})
    try:
        capture = run_bin("lab-capture", ["start", incident], timeout=90)
        add({"step": 2, "action": "capture_start", "exit": capture.returncode,
             "stdout": (capture.stdout or "")[-1500:], "stderr": (capture.stderr or "")[-500:]})
        if capture.returncode != 0:
            die(EXIT_ASSERT, f"assertion failed: lab-capture start: {capture.stderr.strip() or capture.stdout.strip()}")
        baseline_s = int(cfg.get("SC01_BASELINE_S", "10"))
        after_s = int(cfg.get("SC01_AFTER_INJECT_S", "4"))
        tps = float(cfg.get("SC01_WORKLOAD_TPS", "8"))
        wseed = int(cfg.get("SC01_WORKLOAD_SEED", "7"))
        app = ConcurrentApp(wseed, relation, tps)
        baseline_started = utc_now()
        app.start()
        confounder = module.start_confounder(incident)
        add({"step": 4, "action": "workload_start", "tps": tps, "seed": wseed, "scenario_workload": prep.get("mix")})
        time.sleep(baseline_s)
        pre = run_json("lab-snapshot", ["--label", "pre_injection", "--incident", incident])
        add({"step": 5, "action": "snapshot_pre_injection", "result": pre})
        injection = module.inject(incident)
        add({"step": 6, "action": "inject", "result": {k: injection[k] for k in injection if k not in {"ops", "malicious_set"}}})
        time.sleep(after_s)
        scenario_rows = module.stop_confounder(confounder)
        app_rows = app.stop()
        ddl_rows = apply_group(plan_sc01_ddl())
        add({"step": 7, "action": "workload_stop", "app_ops": len(app_rows), "scenario_ops": len(scenario_rows),
             "ddl_ops": len(ddl_rows)})
        post = run_json("lab-snapshot", ["--label", "post_capture", "--incident", incident])
        add({"step": 7, "action": "snapshot_post_capture", "result": post})
        from lab_capture import stop_snapshot_loop
        stop_snapshot_loop(incident, check=True, required_from=baseline_started, required_until=post["created_at"])

        injected = injected_workload_rows(scenario, injection)
        combined = combined_workload(app_rows, scenario_rows, injected, ddl_rows)
        ed = evidence_dir(incident)
        write_jsonl(ed / "workload.jsonl", [workload_record(r) for r in combined])
        write_jsonl(ed / "workload-manifest.jsonl", legitimate_manifest(combined))
        reference = write_reference(incident, scenario, injection)
        add({"step": 11, "action": "reference", "result": reference})
        extra = {
            "quiescent_baseline": {
                "t_start": baseline_started,
                "t_end": injection["t_start"],
                "lsn_start": open_snap.get("recorded_lsn"),
                "lsn_end_exclusive": injection["lsn_start"],
                "declared_in": "etc/scenarios/sc01.env",
                "window_s": int(cfg.get("SC01_WINDOW_S", "2")),
                "baseline_s": baseline_s,
            },
            "naive_time_error_seconds": int(cfg.get("SC01_NAIVE_TIME_ERROR_SECONDS", "20")),
            "approx_incident_time": pre.get("created_at") or pre.get("lsn_recorded_at"),
            "workload_seed": wseed,
            "analytics_version": cfg.get("SC01_ANALYTICS_VERSION", "p3-analytics-1"),
            "injected_operations": len(injected),
            "generator": "lab-generate-dbscen",
        }
        return freeze_common(incident, scenario, definition, log, open_snap, pre, post, tps,
                             f"repeated-keys:lab_app+{prep.get('mix')}", reference, extra)
    finally:
        from lab_capture import stop_snapshot_loop
        stop_snapshot_loop(incident)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--scenario":
        die(EXIT_USAGE, "usage: lab-generate-dbscen --scenario SC-03|SC-04")
    log: list[dict] = []
    rec = generate(argv[1], log)
    print(json.dumps({"ok": True, "changed": True, **rec}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
