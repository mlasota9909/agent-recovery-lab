"""D002: realize one reconciled SC-01 incident. Reuses P1/P2 collectors; never lab-capture stop."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from lab_p3_util import (
    EXIT_ASSERT, EXIT_PRECOND, canonical_json, die, env, point_current, require_lab,
    results_incident_id, run_bin, run_json, scenario_config, ssh_psql, utc_now,
    write_json, write_jsonl, write_text,
)
from lab_paths import evidence_dir, lab_root
from lab_sc01_workload import ConcurrentApp, apply_group, ensure_sc01_seed, plan_sc01_ddl
from lsn import lsn_int, lsn_norm


def bin_path(name: str) -> str:
    return str(lab_root() / "bin" / name)


def empty_ledger_files(incident: str) -> None:
    ed = evidence_dir(incident)
    ed.mkdir(parents=True, exist_ok=True)
    for name in ("workload.jsonl",):
        path = ed / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
            os.chmod(path, 0o644)


def replica_identity(relation: str) -> str:
    proc = ssh_psql(
        "SELECT relreplident FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname='public' AND c.relname='{relation}';"
    )
    return (proc.stdout.strip() or "").lower()[:1]


def set_replica_identity(relation: str, mode: str) -> None:
    sql = f"ALTER TABLE public.{relation} REPLICA IDENTITY {mode};"
    proc = ssh_psql(sql)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: REPLICA IDENTITY {mode}: {proc.stderr.strip()}")


def generate(log: list[dict]) -> dict:
    require_lab()
    cfg = scenario_config()
    relation = cfg.get("SC01_RELATION", "p2_probe")
    t0 = time.monotonic()

    def add(entry: dict) -> None:
        entry["elapsed_ms"] = int(round((time.monotonic() - t0) * 1000))
        log.append(entry)

    seed = ensure_sc01_seed()
    add({"step": 0, "action": "seed", "result": seed})
    if seed["count"] < int(cfg.get("SC01_INJECT_ROWS", "200")):
        die(EXIT_PRECOND, f"precondition failed: seed count {seed['count']} < inject rows")
    cleanup = ssh_psql(
        f"DELETE FROM public.{relation} WHERE id >= 88000000; "
        "DROP TABLE IF EXISTS public.p2_alt;"
    )
    if cleanup.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: key-range cleanup: {cleanup.stderr.strip()}")

    from lab_incident_runtime import stop_finished_incident_clusters
    for stopped in stop_finished_incident_clusters():
        add({"step": 0, "action": "stop_finished_incident_cluster", "result": stopped})
    allocated = run_json("lab-incident", ["--new", "--scenario", "SC-01"])
    incident = allocated["incident"]
    add({"step": 1, "action": "incident_new", "result": allocated})
    empty_ledger_files(incident)
    # The heartbeat may still target an earlier (now stopped) incident cluster.
    # Point it at the site cluster and wait for readiness before capture starts.
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
    open_snap = run_json("lab-snapshot", ["--label", "open", "--incident", incident])
    add({"step": 3, "action": "snapshot_open", "result": open_snap})
    try:
        capture = run_bin("lab-capture", ["start", incident], timeout=90)
        add({"step": 2, "action": "capture_start", "exit": capture.returncode,
             "stdout": capture.stdout[-1500:], "stderr": capture.stderr[-500:]})
        if capture.returncode != 0:
            die(EXIT_ASSERT, f"assertion failed: lab-capture start: {capture.stderr.strip() or capture.stdout.strip()}")
        baseline_s = int(cfg.get("SC01_BASELINE_S", "10"))
        after_s = int(cfg.get("SC01_AFTER_INJECT_S", "4"))
        tps = float(cfg.get("SC01_WORKLOAD_TPS", "8"))
        wseed = int(cfg.get("SC01_WORKLOAD_SEED", "7"))
        app = ConcurrentApp(wseed, relation, tps)
        baseline_started = utc_now()
        app.start()
        add({"step": 4, "action": "workload_start", "tps": tps, "seed": wseed})
        time.sleep(baseline_s)
        pre = run_json("lab-snapshot", ["--label", "pre_injection", "--incident", incident])
        add({"step": 5, "action": "snapshot_pre_injection", "result": pre})
        inj = run_json("lab-inject-sc01", [incident, "--relation", relation,
                                           "--rows", cfg.get("SC01_INJECT_ROWS", "200")])
        add({"step": 6, "action": "inject", "result": inj})
        time.sleep(after_s)
        app_rows = app.stop()
        add({"step": 7, "action": "workload_stop", "app_ops": len(app_rows)})
        ddl_planned = plan_sc01_ddl()
        ddl_rows = apply_group(ddl_planned)
        add({"step": 7, "action": "ddl", "ops": len(ddl_rows)})
        post = run_json("lab-snapshot", ["--label", "post_capture", "--incident", incident])
        add({"step": 7, "action": "snapshot_post_capture", "result": post})
        from lab_capture import stop_snapshot_loop
        stop_snapshot_loop(incident, check=True, required_from=baseline_started,
                           required_until=post["created_at"])

        inj_doc = json.loads((evidence_dir(incident) / "injection_log.json").read_text(encoding="utf-8"))
        inj_ops = inj_doc["ops"]
        for rec in inj_ops:
            rec["commit_lsn"] = inj_doc["commit_lsn"]
            rec["operation"] = "delete"
            rec["row_ids"] = [rec["natural_key"]]
            rec["row_count"] = 1
            rec["relation"] = rec.get("table")
        combined = []
        for rec in app_rows + inj_ops + ddl_rows:
            combined.append(rec)
        combined.sort(key=lambda r: (lsn_int(r["commit_lsn"]) if r.get("commit_lsn") else 0, r.get("xid") or 0, r.get("natural_key") or 0))
        for i, rec in enumerate(combined):
            rec["op_index"] = i
        ed = evidence_dir(incident)
        write_jsonl(ed / "workload.jsonl", [{k: v for k, v in rec.items()
                                             if k not in {"operation", "row_ids", "row_count", "relation", "commit_lsn"}}
                                            for rec in combined])
        # P1 oracle manifest (legitimate commits only).
        man = []
        for rec in app_rows:
            if rec.get("commit_lsn") and rec.get("action") in {"I", "U", "D"}:
                man.append({
                    "commit_lsn": rec["commit_lsn"],
                    "commit_ts": rec["wall_clock"],
                    "operation": rec.get("operation"),
                    "relation": rec.get("relation") or rec.get("table"),
                    "row_ids": rec.get("row_ids") or ([rec["natural_key"]] if rec.get("natural_key") is not None else []),
                    "row_count": rec.get("row_count") or 1,
                    "principal": rec.get("principal"),
                })
        write_jsonl(ed / "workload-manifest.jsonl", man)

        from lab_file_evidence import capture_file_evidence
        capture_file_evidence(incident, log, runner=run_bin)

        barrier = run_bin("lab-barrier", [], timeout=150)
        add({"step": 9, "action": "barrier", "exit": barrier.returncode})
        from lab_generate_incident import window_ledger
        dropped = window_ledger(ed / "db.jsonl", open_snap["recorded_lsn"], post["recorded_lsn"])
        add({"step": 9, "action": "ledger_window", "dropped": dropped,
             "open": open_snap.get("recorded_lsn"), "close": post.get("recorded_lsn")})
        account = run_json("lab-ledger-account", [incident], timeout=60)
        add({"step": 10, "action": "ledger_account", "result": account})
        if account.get("gaps") != 0 or account.get("duplicates") != 0 or not account.get("ok"):
            die(EXIT_ASSERT, "assertion failed: SC-01 incident did not reconcile exactly-once: " + canonical_json(account))

        ora = run_json("lab-oracle", ["--incident", incident], timeout=60)
        add({"step": 11, "action": "oracle", "result": ora})

        def coord_snap(name: str) -> dict:
            raw = run_json("lab-coordinate", ["--snapshot", name])
            return {k: raw[k] for k in ("wall_clock", "lsn", "snapshot", "skew_ms", "skew_bytes", "resolved_by")}

        rec = {
            "incident_id": results_incident_id(incident),
            "archive_incident": incident,
            "scenario_id": "SC-01",
            "relation": relation,
            "open_coordinate": coord_snap(open_snap["snapshot"]),
            "close_coordinate": coord_snap(post["snapshot"]),
            "snapshot_open": open_snap["snapshot"],
            "snapshot_pre_injection": pre["snapshot"],
            "snapshot_post_capture": post["snapshot"],
            "workload_rate_tps": tps,
            "workload_mix": "repeated-keys:lab_app+sc01-inject:lab_agent",
            "oracle_coordinate": ora.get("coordinate"),
            "ledger_integrity_ok": True,
            "quiescent_baseline": {
                "t_start": baseline_started,
                "t_end": inj_doc["t_start"],
                "lsn_start": open_snap.get("recorded_lsn"),
                "lsn_end_exclusive": inj_doc["lsn_start"],
                "declared_in": "etc/scenarios/sc01.env",
                "window_s": int(cfg["SC01_WINDOW_S"]),
                "baseline_s": baseline_s,
            },
            "naive_time_error_seconds": int(cfg["SC01_NAIVE_TIME_ERROR_SECONDS"]),
            "approx_incident_time": pre.get("created_at") or pre.get("lsn_recorded_at"),
            "workload_seed": wseed,
            "analytics_version": cfg.get("SC01_ANALYTICS_VERSION", "p3-analytics-1"),
            "ledger_account": {"ops": account["ops"], "mapped": account["mapped"],
                               "gaps": account["gaps"], "duplicates": account["duplicates"]},
        }
        write_json(ed / "incident.json", rec)
        write_json(ed / "generate-commands.json", log)
        return rec

    finally:
        from lab_capture import stop_snapshot_loop
        stop_snapshot_loop(incident)


def main(argv: list[str]) -> int:
    log: list[dict] = []
    rec = generate(log)
    print(json.dumps({"ok": True, "changed": True, **rec}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
