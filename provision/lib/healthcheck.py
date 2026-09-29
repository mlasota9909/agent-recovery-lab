"""Run the live P0 subset against the recorded provisioning scope."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import provision as p

ROOT = Path(__file__).resolve().parents[2]


def main():
    entries = []
    omitted = {
        "AC-3": "Snapshot/rollback timing review is not imported from the original lab.",
        "AC-4": "Historical snapshot-read proof; run T013 for a new review bundle.",
        "AC-5": "Historical filesystem difference proof; run T013 for a new review bundle.",
        "AC-7": "Historical interleaved DDL/DML review; run T014 for a new review bundle.",
        "AC-9": "Successive incident/reset archive scoping is outside this one fresh provisioning scope.",
        "AC-11": "Historical two-principal provenance review is not reused.",
        "AC-17": "Destructive reset review is deferred; the three undamaged reset labels are provisioned.",
    }

    def check(identifier, description, function):
        try:
            ok, observed = function()
            entry = {"id": identifier, "description": description, "result": "PASS" if ok else "FAIL", "observed": observed}
        except Exception as exc:
            entry = {"id": identifier, "description": description, "result": "FAIL", "error": str(exc)}
        entries.append(entry)
        print(f"{entry['result']}: {identifier}: {description}", flush=True)
        return entry["result"] == "PASS"

    def command(name, *args, predicate=lambda value: value.get("ok") is True, timeout=300):
        result = p.call([ROOT / "bin" / name, *args], check=False, timeout=timeout)
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            payload = {"stdout": result.stdout}
        observed = {"command": [name, *args], "exit_code": result.returncode, "output": payload, "stderr": result.stderr}
        return result.returncode == 0 and predicate(payload), observed

    def setup():
        p.ENV = p.load_env(ROOT)
        p.validate()
        data = p.check_domain()
        scope = json.loads((p.STATE / "baseline.json").read_text())
        if scope["vm_uuid"] != data["uuid"] or Path(p.ENV["ARCHIVE_CURRENT"]).resolve() != Path(scope["archive_dir"]).resolve():
            raise RuntimeError("Active archive is not this replica's provisioning scope")
        return True, {"vm_uuid": data["uuid"], "incident": scope["incident"]}

    def anchors():
        result = p.call([ROOT / "bin/lab-snapshots"])
        rows = json.loads(result.stdout)
        valid = [r for r in rows if not r.get("invalidated") and
                 r.get("operations") == ["zfs_snapshot", "pg_current_wal_lsn", "pg_switch_wal"] and
                 re.fullmatch(r"[0-9A-F]+/[0-9A-F]+", r.get("recorded_lsn", ""))]
        labels = {p.ENV[k] for k in ("SNAP_PRISTINE", "SNAP_PRE_INJECTION", "SNAP_POST_CAPTURE")}
        return labels <= {r.get("label") for r in valid}, valid

    def coordinate():
        ok, rows = anchors()
        if not ok:
            return False, {"error": "No valid reset anchors"}
        latest = rows[-1]
        return command("lab-coordinate", "--lsn", latest["recorded_lsn"],
                       predicate=lambda value: value.get("snapshot") == latest["snapshot"] and
                       all(k in value for k in ("lsn", "skew_ms", "skew_bytes")))

    def archive():
        # Prove that an actual PostgreSQL segment, not a channel test file,
        # reaches the host following pg_switch_wal().
        remote = ["sudo", "-n", "-u", "postgres", "psql", "-X", "-At", "-v", "ON_ERROR_STOP=1",
                  "-p", p.ENV["PG_PORT"], "-d", p.ENV["DB_NAME"], "-c",
                  "SELECT pg_walfile_name(pg_current_wal_lsn()); SELECT pg_switch_wal();"]
        segment = p.guest(*remote).stdout.splitlines()[0]
        if not re.fullmatch(r"[0-9A-F]{24}", segment):
            return False, {"error": "Invalid PostgreSQL segment name", "segment": segment}
        path = Path(p.ENV["ARCHIVE_CURRENT"]) / segment
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if path.is_file() and path.stat().st_size == 16 * 1024 * 1024:
                return True, {"segment": segment, "bytes": path.stat().st_size}
            time.sleep(1)
        return False, {"error": "WAL archive delivery timed out", "segment": segment}

    def idempotence():
        rows = []
        for name, args in (
            ("lab-discover", []), ("lab-zfs-init", []), ("lab-pgdata-relocate", []),
            ("lab-schema-init", []), ("lab-wal-config", []), ("lab-slot", ["--create"]),
            ("lab-identities", []), ("lab-heartbeat", ["--start"]),
        ):
            ok, observed = command(name, *args, predicate=lambda value: value.get("changed") is False)
            rows.append({"ok": ok, **observed})
        return all(row["ok"] for row in rows), rows

    try:
        if check("AC-1", "Current configuration and replica ownership", setup):
            spec = importlib.util.spec_from_file_location("p0_verify", ROOT / "bin/lab-verify.py")
            legacy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(legacy)
            check("AC-2", "Live discovery confirms guest device attachment", lambda: command(
                "lab-discover", predicate=lambda value: value.get("ok") is True and value.get("DEV_LOCATION") == "guest"))
            check("AC-6", "Decoded UPDATE and DELETE carry before-images", lambda: legacy.ac6_live(p.ENV))
            check("archive", "PostgreSQL WAL segment reaches the host", archive)
            check("AC-8", "Restricted append channel refuses overwrite and invalid commands", lambda: command(
                "lab-isolation-test", "--enumerate", predicate=lambda value:
                value.get("summary", {}).get("result") == "PASS" and value.get("summary", {}).get("total", 0) >= 12))
            check("AC-10", "Slot active, valid, bounded and below retention/free-space limits", lambda: command(
                "lab-slot", "--assert-healthy", predicate=lambda value: value.get("healthy") is True))
            check("AC-12", "Victim principals cannot access host stores", lambda: command(
                "lab-isolation-test", predicate=lambda value: value.get("summary", {}).get("result") == "PASS"))
            check("AC-13", "Deliberate isolation regression fails, then passes after revoke", lambda: command(
                "lab-isolation-test", "--regression", predicate=lambda value: value.get("summary", {}).get("result") == "PASS"))
            check("AC-14", "Live heartbeat cadence and monotonic LSNs", lambda: legacy.ac14_live(p.ENV))
            check("AC-15", "All reset labels have ordered snapshot/LSN/WAL anchors", anchors)
            check("AC-16", "LSN resolves to the newest snapshot with reported skew", coordinate)
            check("AC-18", "Repeated P0 setup reports changed:false", idempotence)
        # Run the readiness gate even when an earlier acceptance check failed.
        check("lab-ready", "Read-only readiness gate", lambda: command("lab-ready", predicate=lambda value: value.get("ready") is True))
    except Exception as exc:
        entries.append({"id": "suite", "result": "FAIL", "error": str(exc)})
    finally:
        ok = bool(entries) and all(row["result"] == "PASS" for row in entries)
        document = {"ok": ok, "suite": "P0 fresh-lab subset", "criteria": entries,
                    "omitted": omitted, "historical_attestations_used": False,
                    "recorded_at": datetime.now(timezone.utc).isoformat()}
        directory = ROOT / "logs/provision"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / ("health-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
        p.record(path, document)
        print(json.dumps({"ok": ok, "summary": str(path)}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
