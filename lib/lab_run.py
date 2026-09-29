"""Independently runnable provisioning, preflight and incident gates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from lab_paths import evidence_dir, lab_root
import lab_sc02_layout as layout
from lab_run_common import (command, incident_id, json_command, logdir, model_registry,
                            read, run_scope, save, sha, utc, verify_freeze)

# Values with host-specific meaning must be explicitly supplied by the local file.
SITE_KEYS = ("VM_NAME", "VM_ADDR", "VM_SSH", "PROVISION_USER", "PROVISION_NETWORK",
             "PROVISION_STORAGE_POOL", "PROVISION_STORAGE_PATH", "PROVISION_SSH_KEY",
             "PROVISION_URI", "PROVISION_IMAGE_BASE", "LAB_HOST", "HOST_PG_CIDR",
             "HOST_ARCHIVE_USER", "CONSUMER_UNIT", "DEV_SYSTEM", "DEV_A", "DEV_B", "PG_PORT",
             "SANDBOX_PORT", "INCIDENT_PORT_BASE", "INCIDENT_PORT_COUNT", "P9_ENDPOINT",
             "MODEL_API_KEY_VAR", "MODEL_API_KEY_FILE", "LAB_HOSTS", "LAB_PRIVATE_CIDRS",
             "P9_BACKEND_M1", "P9_BACKEND_M2", "P9_BACKEND_M3",
             "P9_SERVED_M1", "P9_SERVED_M2", "P9_SERVED_M3")


def resolved_config():
    local = lab_root() / "etc/lab.local.env"
    declared = set(re.findall(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=", local.read_text(), re.M))
    missing = [key for key in SITE_KEYS if key not in declared or not os.environ.get(key)]
    # Print configuration before attempting any external check. Never print credentials.
    names = declared | set(re.findall(r"^([A-Z][A-Z0-9_]*)=",
                                     (lab_root() / "etc/lab.env").read_text(), re.M))
    secret = os.environ.get("MODEL_API_KEY_VAR")
    values = {}
    for key in sorted(names):
        value = os.environ.get(key, "")
        if key == secret or (re.search(r"PASSWORD|SECRET|TOKEN|API_KEY", key)
                             and key not in {"MODEL_API_KEY_VAR", "MODEL_API_KEY_FILE"}
                             and not key.startswith("TOKENIZER_") and key != "MODEL_MAX_TOKENS"):
            value = "<redacted>" if value else "<unset>"
        values[key] = value
        print(f"{key}={value}", flush=True)
    if missing:
        raise ValueError("set site values explicitly in etc/lab.local.env: " + ", ".join(missing))
    return values


def lab_health():
    """Read-only substrate checks; no dependency on the shared decoding slot."""
    proc = subprocess.run([sys.executable, str(lab_root() / "provision/lib/provision.py"), "check-domain"],
                          text=True, capture_output=True, timeout=180)
    if proc.returncode:
        raise RuntimeError("replica ownership: " + (proc.stderr or proc.stdout))
    commands = [
        ["sudo", "-n", "zpool", "list", "-H", "-o", "health", os.environ["ZPOOL"]],
        ["sudo", "-n", "zfs", "list", "-H", "-o", "name", os.environ["DS_PGDATA"],
         os.environ["DS_PROTECTED"], os.environ["SANDBOX_DATASET"]],
        ["sudo", "-n", "-u", "postgres", "psql", "-XAt", "-v", "ON_ERROR_STOP=1",
         "-p", os.environ["PG_PORT"], "-d", os.environ["DB_NAME"], "-c", "SELECT 1;"],
    ]
    rows = []
    for argv in commands:
        proc = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                               "-o", "ConnectTimeout=15", os.environ["VM_SSH"], shlex.join(argv)],
                              text=True, capture_output=True, timeout=90)
        if proc.returncode:
            raise RuntimeError("lab health: " + (proc.stderr or proc.stdout))
        rows.append({"argv": argv, "stdout": proc.stdout})
    if rows[0]["stdout"].strip() != "ONLINE" or rows[-1]["stdout"].strip() != "1":
        raise RuntimeError("lab health: pool or database is not healthy")
    return {"ok": True, "checks": rows, "main_cluster_lab_ready_required": False}


def provision():
    state = lab_root() / "var/provision/vm.json"
    if state.exists():
        health = command("provision/40-healthcheck.sh", allowed=(0, 1, 2), timeout=3600,
                         out=logdir() / "provision-health.json")
        if health.returncode == 0:
            print("Provisioning skipped: the existing replica passes the health check.")
            return
    proc = command("provision/all.sh", timeout=7200, out=logdir() / "provision.json")
    print(proc.stdout)


def preflight():
    from lab_p9 import backend_served_digest, host_of, is_private_host
    from lab_p9_verify_models import verify_one
    report = {"ok": False, "started_utc": utc(), "models": []}
    try:
        report["config"] = resolved_config()
        registry = model_registry()
        if not is_private_host(host_of(os.environ["P9_ENDPOINT"])):
            raise ValueError("gateway is not private")
        for model in registry["models"]:
            if not is_private_host(host_of(model["backend"])):
                raise ValueError("backend is not private: " + model["slot"])
            digest = backend_served_digest(model["backend"], model["served_model"])
            identity = digest.get("identity", {})
            matched = (digest.get("ok") is True and digest.get("model_digest") == model["model_digest"]
                       and identity.get("served_model") == model["served_model"]
                       and bool(identity.get("root")) and bool(identity.get("max_model_len")))
            row = {"alias": model["alias"], "identity": digest, "identity_matches": matched}
            report["models"].append(row)
            if not matched:
                raise ValueError("served identity differs from recorded pin: " + model["alias"])
            check = verify_one(model)
            row["containment"] = check
            if not all(check.get(key) for key in ("identity_matches", "egress_ok", "alias_ok", "decoding_ok", "smoke_ok",
                                                  "containment_verified")):
                raise ValueError("model containment/smoke failed: " + model["alias"])
        report["health"] = lab_health()
        report.update(ok=True, model_set_sha256=sha(lab_root() / "runtime/p9-model-set.json"))
    except (Exception, SystemExit) as exc:
        report["error"] = str(exc)
        raise
    finally:
        report["finished_utc"] = utc()
        save(logdir() / "preflight.json", report)
    print("Preflight passed: three matching identities, contained gateway calls and lab health.")


def ensure_no_open_incident():
    current = Path(os.environ["ARCHIVE_CURRENT"])
    if not current.is_symlink():
        if current.exists():
            raise ValueError("archive/current must be a symlink")
        return
    target = current.resolve()
    target.relative_to(Path(os.environ["ARCHIVE_ROOT"]).resolve())
    baseline = lab_root() / "var/provision/baseline.json"
    if baseline.exists() and read(baseline).get("incident") == target.name:
        return
    directory = evidence_dir(target.name)
    # The fixed generators close their capture at incident.json publication.
    if (directory / "incident.json").exists():
        meta = read(directory / "incident.json")
        if meta.get("close_coordinate") and meta.get("ledger_integrity_ok") is True:
            return
    closed = directory / "consumer-close.json"
    if closed.exists() and read(closed).get("closed") is True:
        return
    raise ValueError("an incident is already open: " + target.name)


def incident(scenario):
    ensure_no_open_incident()
    scope = logdir() if scenario == "SC-02" else logdir() / "sc01"
    marker = scope / "incident-started.json"
    if marker.exists():
        raise ValueError("incident generation was already attempted; inspect " + str(marker.relative_to(lab_root())))
    if (scope / "latest-incident.json").exists():
        raise ValueError("this run already has an incident; resume its numbered stages")
    save(marker, {"scenario": scenario, "started_utc": utc()}, exclusive=True)
    if scenario == "SC-02":
        output = json_command("bin/lab-generate-p7", "--scenario", scenario,
                              out=scope / "incident-generation.json")
    else:
        output = json_command("bin/lab-generate-sc01", out=scope / "incident-generation.json")
    name = incident_id(output["archive_incident"], scenario)
    save(scope / "latest-incident.json", {"incident_id": name, "scenario": scenario}, exclusive=True)
    print(name, flush=True)
    return name


def capture_gate(incident):
    from lab_fl_intervals import file_inventory, read_differences, snapshot_records
    from lab_fs_reconcile import reconcile_file_operations
    from lab_ledger_account import fs_coverage
    directory = evidence_dir(incident)
    snapshots = snapshot_records(read(directory / "snapshots.json"))
    differences = read_differences((directory / "fs_diff.tsv").read_text())
    inventories = file_inventory((directory / "fs_hashes.tsv").read_text(), {s["snapshot"] for s in snapshots})
    operations = [json.loads(line) for line in (directory / "fs-workload.jsonl").read_text().splitlines() if line]
    pure = reconcile_file_operations(snapshots, operations, differences, declared=True)
    integrated = fs_coverage(incident)
    if any(not r["ok"] or r["vacuous"] or r["matched"] == 0 for r in (pure, integrated)):
        raise ValueError("exact C-7 failed at the pure or ledger-account level")
    # Empty diff intervals still require a successful capture invocation in the journal.
    captures = [r for r in read(directory / "generate-commands.json") if r.get("step") == "fs_capture"]
    expected = {("diff", a["snapshot"], b["snapshot"]) for a, b in zip(snapshots, snapshots[1:])}
    expected |= {("hash", s["snapshot"]) for s in snapshots}
    successful = {tuple(r["args"][:r["args"].index("--incident")]) for r in captures if r.get("exit") == 0}
    if not expected <= successful or any(not inv for inv in inventories.values()):
        raise ValueError("incomplete capture journal or missing SC-02 snapshot fingerprints")
    for capture in captures:
        args = capture["args"]
        if capture.get("exit") != 0:
            raise ValueError("capture journal contains a failed invocation")
        receipt = json.loads(capture.get("stdout") or "{}")
        if args[0] == "hash":
            count = len(inventories[args[1]])
        else:
            count = sum(d["from_snapshot"] == args[1] and d["to_snapshot"] == args[2] for d in differences)
        if receipt.get("ok") is not True or receipt.get("rows") != count:
            raise ValueError("capture receipt count differs from stored evidence")
    injection = read(directory / "injection.json")
    paths = {(r["change_type"], r["path"]) for r in differences}
    required = {("-", path) for path in layout.RECORD_FILES}
    required |= {("-", layout.RECORDS), ("M", layout.OVERWRITE)}
    if not required <= paths or not injection.get("fs_ops"):
        raise ValueError("captured differences do not contain every SC-02 damage target")
    return {"pure_C7": pure, "ledger_C7": integrated, "snapshots": len(snapshots),
            "captured_pairs": len(snapshots) - 1, "differences": len(differences),
            "fingerprints": {key: len(value) for key, value in inventories.items()}}


def gate(incident):
    from lab_fl_inputs import build as build_input, select_intervals
    from lab_modelview_guard import guard
    incident_id(incident)
    if (lab_root() / "sdd/specs/P12-file-level-test/contracts/frozen-hashes.json").exists():
        raise ValueError("incident gate cannot rebuild inputs after freezing")
    report = {"incident_id": incident, "ok": False, "started_utc": utc()}
    try:
        report["capture"] = capture_gate(incident)
        artifact = json_command("bin/lab-fl-intervals", incident)
        selected = select_intervals(artifact)
        if not any(sum(r["counts"].values()) for r in selected):
            raise ValueError("selected intervals contain no file changes")
        report["inputs"] = []
        for rep in ("R0", "R1", "R2"):
            view = json_command("bin/lab-fl-inputs", incident, "--input", rep)
            guard(view)
            if view != build_input(incident, rep) or len(view["content"].splitlines()) < 2:
                raise ValueError("input does not contain its selected file intervals: " + rep)
            report["inputs"].append({"representation": rep, "guard": True,
                                      "content_sha256": sha(evidence_dir(incident) / "fl-inputs" / rep / "content.txt")})
        json_command("bin/lab-fl-reference", incident)
        controls = json_command("bin/lab-fl-controls", incident, allowed=(0, 1))
        report["controls"] = controls
        if not controls["ok"]:
            raise ValueError("one or more restore controls failed")
        report["ok"] = True
        report["evidence_sha256"] = gate_sources(incident)
    except (Exception, SystemExit) as exc:
        report["error"] = str(exc)
        raise
    finally:
        report["finished_utc"] = utc()
        save(logdir(incident) / "gate.json", report)
    print(json.dumps({"ok": True, "gate": str(logdir(incident) / "gate.json")}))


def gate_sources(incident):
    directory = evidence_dir(incident)
    names = ("snapshots.json", "fs_diff.tsv", "fs_hashes.tsv", "fs-workload.jsonl", "injection.json",
             "incident.json", "generate-commands.json", "fl-intervals.json", "fl-reference.json",
             "fl-controls.json", "oracle-manifest.json", "workload-manifest.jsonl")
    return {name: sha(directory / name) for name in names}


def require_gate(incident):
    report = read(logdir(incident) / "gate.json")
    if (report.get("incident_id") != incident or report.get("ok") is not True
            or report.get("evidence_sha256") != gate_sources(incident)):
        raise ValueError("passing incident gate is missing or its evidence changed")


def freeze(incident):
    require_gate(incident)
    model_registry()
    pre = read(logdir() / "preflight.json")
    if not pre.get("ok") or pre.get("model_set_sha256") != sha(lab_root() / "runtime/p9-model-set.json"):
        raise ValueError("matching successful preflight required before freezing")
    print(command("bin/lab-fl-freeze", incident).stdout)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("provision", "preflight", "incident", "gate", "freeze",
                                          "study", "comparators", "analysis"))
    parser.add_argument("incident", nargs="?")
    parser.add_argument("--scenario", choices=("SC-02", "SC-01"), default="SC-02")
    args = parser.parse_args(argv)
    try:
        if run_scope() != "run" and args.stage not in ("incident", "gate"):
            raise ValueError("a dry-run scope runs only the incident and gate stages")
        if args.stage in ("gate", "freeze", "study", "comparators"):
            incident_id(args.incident or "")
        elif args.incident:
            parser.error("this stage does not take an incident")
        if args.stage == "study":
            from lab_fl_study import study
            study(args.incident)
        elif args.stage == "comparators":
            from lab_fl_study import comparators
            comparators(args.incident)
        elif args.stage == "analysis":
            from lab_fl_analysis import analyse
            return 0 if analyse()["complete"] else 1
        elif args.stage == "incident":
            incident(args.scenario)
        elif args.stage in ("gate", "freeze"):
            globals()[args.stage](args.incident)
        else:
            globals()[args.stage]()
    except (Exception, SystemExit) as exc:
        print(f"run {args.stage} failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
