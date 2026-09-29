"""lab-generate-p7: T0 generation for SC-02/03/04. Never regenerates SC-01."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from lab_generate_incident import window_ledger
from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, canonical_json, die, env, point_current,
    require_lab, results_incident_id, run_bin, run_json, ssh_psql, utc_now, write_json,
    write_jsonl, write_text,
)
from lab_paths import evidence_dir, lab_root
from lab_p7 import HEADLINE
from lab_sc01_workload import ConcurrentApp, apply_group, ensure_sc01_seed, plan_sc01_ddl
from lab_scenario import load_definition
from lsn import lsn_int, lsn_norm

COORD_FIELDS = ("wall_clock", "lsn", "snapshot", "skew_ms", "skew_bytes", "resolved_by")


def empty_ledger_files(incident: str) -> None:
    ed = evidence_dir(incident)
    ed.mkdir(parents=True, exist_ok=True)
    for name in ("workload.jsonl",):
        path = ed / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
            os.chmod(path, 0o644)


def coord_snap(name: str) -> dict:
    raw = run_json("lab-coordinate", ["--snapshot", name])
    return {k: raw[k] for k in COORD_FIELDS}


def copy_snapshots(incident: str) -> None:
    from lab_snapshot_tick import merge_snapshot_records
    merge_snapshot_records(incident)


def freeze_common(incident: str, scenario: str, definition: dict, log: list[dict],
                  open_snap: dict, pre: dict, post: dict, tps: float, mix: str,
                  oracle_coord: dict, extra: dict) -> dict:
    ed = evidence_dir(incident)
    from lab_capture import stop_snapshot_loop
    from lab_file_evidence import capture_file_evidence
    stop_snapshot_loop(incident, check=True)
    capture_file_evidence(incident, log, runner=run_bin)
    barrier = run_bin("lab-barrier", [], timeout=150)
    log.append({"step": "barrier", "exit": barrier.returncode})
    # Stop decode before the window cut so post-close commits cannot land in db.jsonl.
    run_bin("lab-consumer", ["stop", incident], timeout=60)
    dropped = window_ledger(ed / "db.jsonl", open_snap["recorded_lsn"], post["recorded_lsn"])
    log.append({"step": "ledger_window", "dropped": dropped,
                "open": open_snap.get("recorded_lsn"), "close": post.get("recorded_lsn")})
    account = run_json("lab-ledger-account", [incident], timeout=60)
    log.append({"step": "ledger_account", "result": account})
    if account.get("gaps") != 0 or account.get("duplicates") != 0 or not account.get("ok"):
        die(EXIT_ASSERT, "assertion failed: incident did not reconcile exactly-once: " + canonical_json(account))
    rec = {
        "incident_id": results_incident_id(incident),
        "archive_incident": incident,
        "incident_runtime": {
            key: os.environ[key] for key in (
                "INC_ID", "INC_DS", "INC_PGDATA", "INC_PROTECTED", "INC_PG_PORT",
                "INC_PG_SOCKET", "INC_SLOT", "INC_HEARTBEAT_PORT"
            )
        },
        "scenario_id": scenario,
        "timing_pattern": definition["timing_pattern"],
        "open_coordinate": coord_snap(open_snap["snapshot"]),
        "close_coordinate": coord_snap(post["snapshot"]),
        "snapshot_open": open_snap["snapshot"],
        "snapshot_pre_injection": pre["snapshot"],
        "snapshot_post_capture": post["snapshot"],
        "workload_rate_tps": tps,
        "workload_mix": mix,
        "oracle_coordinate": oracle_coord,
        "ledger_integrity_ok": True,
        "ledger_account": {"ops": account["ops"], "mapped": account["mapped"],
                           "gaps": account["gaps"], "duplicates": account["duplicates"]},
        "definition_path": str(lab_root() / "scenarios" / scenario.lower().replace("-", "") / "definition.json"),
        **extra,
    }
    write_json(ed / "incident.json", rec)
    write_json(ed / "generate-commands.json", log)
    ledger = ed / "db.jsonl"
    if ledger.is_file():
        frozen = ed / "db.jsonl.frozen"
        frozen.write_bytes(ledger.read_bytes())
        os.chmod(ledger, 0o444)
        os.chmod(frozen, 0o444)
    return rec


def generate(scenario: str, log: list[dict]) -> dict:
    require_lab()
    if scenario == "SC-01":
        die(EXIT_USAGE, "SC-01 is referenced, not generated; refuse lab-generate-p7 --scenario SC-01")
    def_path = lab_root() / "scenarios" / scenario.lower().replace("-", "") / "definition.json"
    definition = load_definition(def_path)
    if not definition["confounder"]["overlaps_damage"]:
        die(EXIT_ASSERT, "assertion failed: confounder.overlaps_damage is not true; generation refused")
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
    relation = os.environ.get("SC01_RELATION") or "p2_probe"
    cleanup = ssh_psql(
        f"DELETE FROM public.{relation} WHERE id >= 88000000; "
        "DROP TABLE IF EXISTS public.p2_alt;"
    )
    if cleanup.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: key-range cleanup: {cleanup.stderr.strip()}")
    cur = Path(env("ARCHIVE_CURRENT"))
    if cur.exists() or cur.is_symlink():
        old = cur.resolve().name
        if old and old != HEADLINE:
            # Stop the leftover consumer only. lab-capture stop drops lab_slot
            # (C009 teardown) and would make the next lab-incident --new fail.
            run_bin("lab-consumer", ["stop", old], timeout=60)
            add({"step": 0, "action": "stop_throwaway_consumer", "incident": old})
    from lab_incident_runtime import stop_finished_incident_clusters
    for stopped in stop_finished_incident_clusters():
        add({"step": 0, "action": "stop_finished_incident_cluster", "result": stopped})
    slot = run_json("lab-slot", ["--create"], timeout=90)
    add({"step": 0, "action": "slot_ensure", "result": slot})
    allocated = run_json("lab-incident", ["--new", "--scenario", scenario])
    incident = allocated["incident"]
    if incident.startswith("SC-01"):
        die(EXIT_ASSERT, "assertion failed: P7 generate produced an SC-01 incident id")
    add({"step": 1, "action": "incident_new", "result": allocated})
    # The allocator initially points the legacy consumer at the shared cluster.
    # Stop it, build the isolated cluster, select its runtime, then restart
    # decoding against the incident-specific port and slot.
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
    run_bin("lab-heartbeat", ["--start"], timeout=60)
    ready_wait = []
    for attempt in range(45):
        ready_proc = run_bin("lab-ready", [], timeout=30)
        ready_wait.append({"attempt": attempt, "exit": ready_proc.returncode})
        if ready_proc.returncode == 0:
            break
        time.sleep(2)
    else:
        die(EXIT_PRECOND, "precondition failed: lab-ready never reached 0 after incident allocation")
    add({"step": 1, "action": "lab_ready_wait", "attempts": len(ready_wait)})
    if scenario == "SC-02":
        from lab_sc02 import prepare as prep, inject as inj, start_confounder, stop_confounder, oracle as ora
    elif scenario == "SC-03":
        from lab_sc03 import prepare as prep, inject as inj, start_confounder, stop_confounder, oracle as ora
    elif scenario == "SC-04":
        from lab_sc04 import prepare as prep, inject as inj, start_confounder, stop_confounder, oracle as ora
    else:
        die(EXIT_USAGE, f"usage: unknown scenario {scenario}")

    if scenario == "SC-02":
        prep_rec = prep(incident)
        add({"step": 0, "action": "prepare", "result": prep_rec})
    open_snap = run_json("lab-snapshot", ["--label", "open", "--incident", incident])
    add({"step": 3, "action": "snapshot_open", "result": open_snap})
    try:
        capture = run_bin("lab-capture", ["start", incident], timeout=90)
        add({"step": 2, "action": "capture_start", "exit": capture.returncode,
             "stdout": (capture.stdout or "")[-1500:], "stderr": (capture.stderr or "")[-500:]})
        if capture.returncode != 0:
            die(EXIT_ASSERT, f"assertion failed: lab-capture start: {capture.stderr.strip() or capture.stdout.strip()}")
        if scenario != "SC-02":
            prep_rec = prep(incident)
            add({"step": 0, "action": "prepare", "result": prep_rec})

        # SC-02's confounder already runs ConcurrentApp on p2_probe; a second
        # instance with the same seed collides on p2_probe_pkey.
        db_app = None
        if scenario != "SC-02":
            db_app = ConcurrentApp(
                int(prep_rec.get("seed") or 11),
                os.environ.get("SC01_RELATION") or "p2_probe",
                float(prep_rec.get("tps") or 6),
            )
            db_app.start()
        prep_rec["baseline_started"] = utc_now()
        confounder = start_confounder(incident)
        add({"step": 4, "action": "confounder_start", "result": {"started": True, "db_app": db_app is not None}})
        baseline_s = int(prep_rec.get("baseline_s") or 8)
        time.sleep(baseline_s)
        pre = run_json("lab-snapshot", ["--label", "pre_injection", "--incident", incident])
        add({"step": 5, "action": "snapshot_pre_injection", "result": pre})
        inj_rec = inj(incident)
        add({"step": 6, "action": "inject", "result": {k: inj_rec[k] for k in inj_rec if k != "ops"}})
        time.sleep(int(prep_rec.get("after_s") or 4))
        scenario_rows = stop_confounder(confounder)
        app_rows = db_app.stop() if db_app is not None else []
        ddl_rows = apply_group(plan_sc01_ddl())
        add({"step": 7, "action": "confounder_stop",
             "app_ops": len(app_rows), "scenario_ops": len(scenario_rows) if isinstance(scenario_rows, list) else scenario_rows,
             "ddl_ops": len(ddl_rows)})
        post = run_json("lab-snapshot", ["--label", "post_capture", "--incident", incident])
        add({"step": 7, "action": "snapshot_post_capture", "result": post})
        from lab_capture import stop_snapshot_loop
        stop_snapshot_loop(incident, check=True, required_from=prep_rec["baseline_started"],
                           required_until=post["created_at"])

        scenario_dml = scenario_rows if isinstance(scenario_rows, list) else []
        combined = []
        for rec in app_rows + scenario_dml + ddl_rows:
            combined.append(rec)
        combined.sort(key=lambda r: (lsn_int(r["commit_lsn"]) if r.get("commit_lsn") else 0, r.get("xid") or 0))
        ed = evidence_dir(incident)
        write_jsonl(ed / "workload.jsonl", combined)

        ora_rec = ora(incident, inj_rec, scenario_rows if isinstance(scenario_rows, list) else app_rows,
                      open_snap, pre, post)
        add({"step": 11, "action": "oracle", "result": {k: ora_rec[k] for k in ora_rec if k not in {"files", "malicious_set"}}})
        extra = {
            "quiescent_baseline": {
                "t_start": prep_rec.get("baseline_started") or utc_now(),
                "t_end": inj_rec.get("t_start"),
                "lsn_start": open_snap.get("recorded_lsn"),
                "lsn_end_exclusive": inj_rec.get("lsn_start"),
                "window_s": 2,
                "baseline_s": baseline_s,
            },
            "approx_incident_time": pre.get("created_at") or pre.get("lsn_recorded_at"),
            **(ora_rec.get("incident_extra") or {}),
        }
        rec = freeze_common(
            incident, scenario, definition, log, open_snap, pre, post,
            float(prep_rec.get("tps") or 8), str(prep_rec.get("mix") or "lab_app-confounder+agent-inject"),
            ora_rec["coordinate"], extra,
        )
        return rec

    finally:
        from lab_capture import stop_snapshot_loop
        stop_snapshot_loop(incident)


def main(argv: list[str]) -> int:
    scenario = None
    i = 0
    while i < len(argv):
        if argv[i] == "--scenario" and i + 1 < len(argv):
            scenario = argv[i + 1]
            i += 2
            continue
        die(EXIT_USAGE, "usage: lab-generate-p7 --scenario SC-02|SC-03|SC-04")
    if scenario not in {"SC-02", "SC-03", "SC-04"}:
        die(EXIT_USAGE, "usage: lab-generate-p7 --scenario SC-02|SC-03|SC-04")
    rec = generate(scenario, [])
    print(json.dumps({"ok": True, "changed": True, **rec}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
