#!/usr/bin/env python3
"""P0 acceptance verification with mechanical and attested tiers (R004)."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ["LAB_ROOT"])
REVIEW = ROOT / "logs" / "review"
ATTESTED_PATH = ROOT / "etc" / "acceptance-attested.json"


def command(argv: list[str], timeout: int = 180) -> tuple[int, str, str]:
    completed = subprocess.run(
        argv, cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=False
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def criterion(
    ac: str,
    tier: str,
    requirement: str,
    cmd: str,
    expected: str,
    observed: object,
    passed: bool,
) -> dict[str, object]:
    return {
        "id": ac,
        "tier": tier,
        "requirement": requirement,
        "command": cmd,
        "expected": expected,
        "observed": observed,
        "result": "PASS" if passed else "FAIL",
    }


def env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / "etc/lab.env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[key] = value
    return values


def load_attested() -> dict[str, dict]:
    if not ATTESTED_PATH.is_file():
        return {}
    return json.loads(ATTESTED_PATH.read_text(encoding="utf-8"))


def lsn_int(lsn: str) -> int:
    if not re.fullmatch(r"[0-9A-F]+/[0-9A-F]+", lsn):
        raise ValueError(f"invalid LSN {lsn!r}")
    high, low = lsn.split("/")
    return (int(high, 16) << 32) + int(low, 16)


def ssh_psql(env: dict[str, str], sql: str) -> tuple[int, str, str]:
    remote = (
        "sudo -n -u postgres psql -X -v ON_ERROR_STOP=1 -At "
        f"-p {shlex.quote(env['PG_PORT'])} -d {shlex.quote(env['DB_NAME'])} "
        f"-c {shlex.quote(sql)}"
    )
    return command(["ssh", "-o", "BatchMode=yes", env["VM_SSH"], remote])


def identity_value(record: dict, column: str) -> object:
    for item in record.get("identity") or []:
        if item.get("name") == column:
            return item.get("value")
    return None


def column_value(record: dict, column: str) -> object:
    for item in record.get("columns") or []:
        if item.get("name") == column:
            return item.get("value")
    return None


def ac6_live(env: dict[str, str]) -> tuple[bool, object]:
    marker = f"r004-ac6-{int(time.time())}"
    old_payload = marker + "-old"
    new_payload = marker + "-new"
    insert = (
        "INSERT INTO lab_ledger (created_at, amount, payload, row_version) "
        f"VALUES (clock_timestamp(), 9.09, '{old_payload}', 1) RETURNING id"
    )
    rc, row_id, err = ssh_psql(env, insert)
    row_id = next((line for line in row_id.splitlines() if re.fullmatch(r"[0-9]+", line)), "")
    if rc != 0 or not row_id:
        return False, {"error": "insert failed", "stderr": err, "stdout": row_id}
    ssh_psql(env, f"UPDATE lab_ledger SET payload = '{new_payload}' WHERE id = {row_id}")
    ssh_psql(env, f"DELETE FROM lab_ledger WHERE id = {row_id}")
    time.sleep(5)
    incident = json.loads(command([str(ROOT / "bin/lab-incident"), "--current"])[1])
    stream = Path(incident["evidence_dir"]) / "db.jsonl"
    if not stream.is_file():
        return False, {"error": f"missing {stream}"}
    update_rec = delete_rec = None
    for line in stream.read_text(encoding="utf-8").splitlines():
        if marker not in line:
            continue
        rec = json.loads(line)
        if rec.get("action") == "U" and rec.get("table") == "lab_ledger":
            update_rec = rec
        if rec.get("action") == "D" and rec.get("table") == "lab_ledger":
            delete_rec = rec
    ok = (
        update_rec is not None
        and delete_rec is not None
        and identity_value(update_rec, "payload") == old_payload
        and identity_value(delete_rec, "payload") == new_payload
    )
    return ok, {
        "row_id": row_id,
        "old_payload": old_payload,
        "new_payload": new_payload,
        "update_identity_payload": identity_value(update_rec, "payload") if update_rec else None,
        "delete_identity_payload": identity_value(delete_rec, "payload") if delete_rec else None,
        "update": update_rec,
        "delete": delete_rec,
    }


def ac14_live(env: dict[str, str]) -> tuple[bool, object]:
    sql = (
        "SELECT to_char(at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), "
        "lsn::text FROM lab_heartbeat ORDER BY id DESC LIMIT 20"
    )
    rc, out, err = ssh_psql(env, sql)
    if rc != 0 or not out:
        return False, {"error": "heartbeat query failed", "stderr": err}
    rows = [line.split("|") for line in out.splitlines() if line]
    # psql -At default separator is | 
    parsed = []
    for row in reversed(rows):
        if len(row) != 2:
            return False, {"error": f"unexpected row {row!r}"}
        parsed.append({"at": row[0], "lsn": row[1], "lsn_int": lsn_int(row[1])})
    if len(parsed) < 8:
        return False, {"error": "fewer than 8 heartbeat rows", "rows": parsed}
    lsn_ok = all(parsed[i]["lsn_int"] < parsed[i + 1]["lsn_int"] for i in range(len(parsed) - 1))
    from datetime import datetime, timezone

    def parse_ts(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    newest_age = (datetime.now(timezone.utc) - parse_ts(parsed[-1]["at"])).total_seconds()
    intervals = [
        (parse_ts(parsed[i + 1]["at"]) - parse_ts(parsed[i]["at"])).total_seconds()
        for i in range(len(parsed) - 1)
    ]
    # 1 Hz with tolerance: mean in [0.5, 1.5], no gap above 3s, newest row fresh.
    mean = sum(intervals) / len(intervals)
    interval_ok = 0.5 <= mean <= 1.5 and max(intervals) <= 3.0 and newest_age <= 3.0
    return lsn_ok and interval_ok, {
        "count": len(parsed),
        "mean_interval_s": mean,
        "max_interval_s": max(intervals),
        "newest_age_s": newest_age,
        "lsn_strictly_monotonic": lsn_ok,
        "first_lsn": parsed[0]["lsn"],
        "last_lsn": parsed[-1]["lsn"],
    }


def main() -> int:
    want_json = "--json" in sys.argv
    env = env_values()
    attested = load_attested()
    entries: list[dict[str, object]] = []

    keys = (
        "VM_NAME", "VM_ADDR", "DEV_A", "DEV_B", "ZPOOL", "DS_PARENT",
        "DS_PGDATA", "DS_PROTECTED", "PG_VERSION", "PG_DATA", "LAB_ROOT",
        "EVIDENCE_ROOT", "ARCHIVE_ROOT", "RESULTS_ROOT", "ROLE_APP",
        "ROLE_AGENT", "SLOT_NAME",
    )
    violations: list[str] = []
    skip = {"lab-discover", "lab-verify", "lab-verify.py", "lab-repomix-backup"}
    for script in sorted((ROOT / "bin").iterdir()):
        if not script.is_file() or script.name in skip:
            continue
        text = script.read_text(encoding="utf-8")
        for key in keys:
            value = env[key]
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(value)}(?![A-Za-z0-9_])", text):
                violations.append(f"{script.relative_to(ROOT)}:{key}={value}")
    required = all(env.get(key) for key in keys)
    entries.append(criterion(
        "AC-1", "M",
        "configured values are consumed; environment literals do not leak into downstream scripts",
        "configured-value literal sweep of bin/ (excluding lab-discover)",
        "all required lab.env keys present; zero downstream literals",
        {"required_keys_present": required, "violations": violations},
        required and not violations,
    ))

    ac2 = attested.get("AC-2", {})
    entries.append(criterion(
        "AC-2", "A",
        "guest-side device attachment",
        "etc/lab.env DEV_LOCATION and etc/acceptance-attested.json AC-2",
        "DEV_LOCATION=guest",
        {"lab_env": env.get("DEV_LOCATION"), "attested": ac2},
        env.get("DEV_LOCATION") == "guest" and ac2.get("DEV_LOCATION") == "guest",
    ))

    ac3 = attested.get("AC-3", {})
    snap = float(ac3.get("snapshot_seconds", 99))
    roll = float(ac3.get("rollback_seconds", 99))
    entries.append(criterion(
        "AC-3", "A",
        "recursive snapshot <2s; rollback <5s",
        "etc/acceptance-attested.json AC-3 (from logs/review/T002/timings.md)",
        "snapshot_seconds<2 and rollback_seconds<5",
        ac3,
        snap < float(ac3.get("snapshot_limit_seconds", 2))
        and roll < float(ac3.get("rollback_limit_seconds", 5)),
    ))

    ac4_text = (REVIEW / "T013" / "snapshot-read-proof.txt").read_text(encoding="utf-8") if (
        REVIEW / "T013" / "snapshot-read-proof.txt"
    ).is_file() else ""
    ac4 = attested.get("AC-4", {})
    entries.append(criterion(
        "AC-4", "A",
        "deleted content read through .zfs/snapshot",
        "logs/review/T013/snapshot-read-proof.txt plus attested deleted_content",
        ac4.get("deleted_content", ""),
        {"proof": ac4_text.strip(), "attested": ac4},
        bool(ac4.get("deleted_content")) and ac4["deleted_content"] in ac4_text,
    ))

    diff_path = REVIEW / "T013" / "zfs-diff-parsed.json"
    types: list[str] = []
    if diff_path.is_file():
        types = sorted({row.get("change_type") for row in json.loads(diff_path.read_text())})
    ac5 = attested.get("AC-5", {})
    entries.append(criterion(
        "AC-5", "A",
        "create, modify, delete, rename parsed",
        "logs/review/T013/zfs-diff-parsed.json change_type set",
        "+ - M R",
        {"observed_types": types, "attested": ac5},
        types == ["+", "-", "M", "R"] or set(types) == {"+", "-", "M", "R"},
    ))

    ok6, obs6 = ac6_live(env)
    entries.append(criterion(
        "AC-6", "M",
        "decoded UPDATE and DELETE carry full old-tuple column values",
        "live UPDATE then DELETE on lab_ledger; read incident db.jsonl",
        "identity.payload equals the pre-change column value on UPDATE and DELETE",
        obs6,
        ok6,
    ))

    ddl_path = REVIEW / "T014" / "ddl-ordering-proof.json"
    ddl_ok = False
    ddl_obs: object = {"error": "missing ddl-ordering-proof.json"}
    if ddl_path.is_file():
        ddl = json.loads(ddl_path.read_text(encoding="utf-8"))
        markers = [item.get("marker") for item in ddl.get("timeline", []) if item.get("marker")]
        lsns = [item.get("record_lsn") for item in ddl.get("timeline", []) if item.get("record_lsn")]
        ddl_ok = (
            all(m in markers for m in attested.get("AC-7", {}).get("markers", []))
            and lsns == sorted(lsns, key=lsn_int)
        )
        ddl_obs = {"markers": markers, "record_lsns": lsns}
    entries.append(criterion(
        "AC-7", "A",
        "CREATE and DROP are ordered with DML",
        "logs/review/T014/ddl-ordering-proof.json timeline LSNs",
        "ddl-before/between/after markers present; record_lsn strictly ordered",
        ddl_obs,
        ddl_ok,
    ))

    ow = (REVIEW / "T007" / "overwrite-checksums.txt").read_text(encoding="utf-8") if (
        REVIEW / "T007" / "overwrite-checksums.txt"
    ).is_file() else ""
    ac8 = attested.get("AC-8", {})
    entries.append(criterion(
        "AC-8", "A",
        "overwrite is refused non-zero",
        "logs/review/T007/overwrite-checksums.txt refusal_exit and checksum",
        f"refusal_exit={ac8.get('refusal_exit')} and before==after checksum",
        {"attested": ac8, "contains_exit": f"refusal_exit={ac8.get('refusal_exit')}" in ow,
         "contains_checksum": ac8.get("checksum", "missing") in ow},
        f"refusal_exit={ac8.get('refusal_exit')}" in ow
        and ac8.get("checksum", "") in ow
        and ow.count(ac8.get("checksum", "never")) >= 2,
    ))

    ac9 = attested.get("AC-9", {})
    entries.append(criterion(
        "AC-9", "A",
        "successive incident archive scopes are disjoint",
        "etc/acceptance-attested.json AC-9",
        "incidents_disjoint true",
        ac9,
        ac9.get("incidents_disjoint") is True,
    ))

    rc, out, err = command([str(ROOT / "bin/lab-slot"), "--check"])
    try:
        slot = json.loads(out)
    except json.JSONDecodeError:
        slot = {"stdout": out, "stderr": err}
    entries.append(criterion(
        "AC-10", "M",
        "slot lag fails closed: consumer active, retention below warning, not invalidated",
        "bin/lab-slot --check",
        "exit 0, active, not over_threshold",
        slot,
        rc == 0 and isinstance(slot, dict) and slot.get("active") is True
        and slot.get("over_threshold") is False
        and slot.get("check") == "ok",
    ))

    ac11 = attested.get("AC-11", {})
    principals = ac11.get("principals") or []
    entries.append(criterion(
        "AC-11", "A",
        "app and agent changes distinguishable",
        "etc/acceptance-attested.json AC-11 principals",
        "lab_app and lab_agent",
        ac11,
        set(principals) == {env.get("ROLE_APP"), env.get("ROLE_AGENT")},
    ))

    rc, out, err = command([str(ROOT / "bin/lab-isolation-test")])
    try:
        isolation = json.loads(out)
    except json.JSONDecodeError:
        isolation = {"stdout": out, "stderr": err}
    rc_e, out_e, err_e = command([str(ROOT / "bin/lab-isolation-test"), "--enumerate"])
    try:
        enumeration = json.loads(out_e)
    except json.JSONDecodeError:
        enumeration = {"stdout": out_e, "stderr": err_e}
    entries.append(criterion(
        "AC-12", "M",
        "each victim principal is denied host stores; command surface enumerated",
        "bin/lab-isolation-test && bin/lab-isolation-test --enumerate",
        "both suites PASS, enumerate >= 12",
        {"isolation": isolation.get("summary"), "enumerate": enumeration.get("summary")},
        rc == 0 and rc_e == 0
        and isolation.get("summary", {}).get("result") == "PASS"
        and enumeration.get("summary", {}).get("result") == "PASS"
        and enumeration.get("summary", {}).get("total", 0) >= 12,
    ))

    rc, out, err = command([str(ROOT / "bin/lab-isolation-test"), "--regression"], timeout=300)
    try:
        regression = json.loads(out)
    except json.JSONDecodeError:
        regression = {"stdout": out, "stderr": err}
    entries.append(criterion(
        "AC-13", "M",
        "host-side grant produces FAIL; revoke restores PASS",
        "bin/lab-isolation-test --regression",
        "three phases PASS/FAIL/PASS",
        regression.get("summary") if isinstance(regression, dict) else regression,
        rc == 0 and isinstance(regression, dict)
        and regression.get("summary", {}).get("result") == "PASS",
    ))

    ok14, obs14 = ac14_live(env)
    entries.append(criterion(
        "AC-14", "M",
        "heartbeat about 1 Hz with strictly monotonic LSNs (integer compare)",
        "SELECT last 20 lab_heartbeat rows; mean interval and lsn_int",
        "mean interval in [0.5, 1.5]s; LSN strictly increasing by (high<<32)+low",
        obs14,
        ok14,
    ))

    rc, out, err = command([str(ROOT / "bin/lab-snapshots")])
    try:
        snapshots = json.loads(out)
    except json.JSONDecodeError:
        snapshots = []
    anchored = [row for row in snapshots if not row.get("invalidated", False)
                and row.get("operations") == ["zfs_snapshot", "pg_current_wal_lsn", "pg_switch_wal"]]
    entries.append(criterion(
        "AC-15", "M",
        "valid snapshot manifest records LSN and forced WAL switch",
        "bin/lab-snapshots",
        "at least one valid anchor",
        {"valid_anchors": anchored[-3:]},
        rc == 0 and bool(anchored),
    ))

    coordinate: object = {"error": "no valid snapshot available"}
    rc_c = 2
    if anchored:
        rc_c, out, err = command([str(ROOT / "bin/lab-coordinate"), "--snapshot", anchored[-1]["snapshot"]])
        try:
            coordinate = json.loads(out)
        except json.JSONDecodeError:
            coordinate = {"stdout": out, "stderr": err}
    entries.append(criterion(
        "AC-16", "M",
        "newest eligible snapshot; skew_ms and skew_bytes reported",
        "bin/lab-coordinate --snapshot <latest-valid>",
        "snapshot, skew_ms, skew_bytes, lsn present",
        coordinate,
        rc_c == 0 and isinstance(coordinate, dict)
        and all(key in coordinate for key in ("snapshot", "skew_ms", "skew_bytes", "lsn")),
    ))

    ac17 = attested.get("AC-17", {})
    entries.append(criterion(
        "AC-17", "A",
        "T0/T1/T2 expected state; evidence intact",
        "etc/acceptance-attested.json AC-17 t1_elapsed_ms from T012",
        "t1_elapsed_ms recorded as a positive integer",
        ac17,
        isinstance(ac17.get("t1_elapsed_ms"), int) and ac17["t1_elapsed_ms"] > 0,
    ))

    idempotent = [
        ["bin/lab-discover"],
        ["bin/lab-zfs-init"],
        ["bin/lab-pgdata-relocate"],
        ["bin/lab-schema-init"],
        ["bin/lab-wal-config"],
        ["bin/lab-slot", "--create"],
        ["bin/lab-identities"],
        ["bin/lab-heartbeat", "--start"],
    ]
    sweep: list[dict[str, object]] = []
    for argv in idempotent:
        rc, out, err = command([str(ROOT / part) if i == 0 else part for i, part in enumerate(argv)])
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            payload = {"stdout": out, "stderr": err}
        sweep.append({"command": " ".join(argv), "exit_code": rc, "observed": payload})
    sweep_ok = all(
        row["exit_code"] == 0 and isinstance(row["observed"], dict)
        and row["observed"].get("changed") is False for row in sweep
    )
    entries.append(criterion(
        "AC-18", "M",
        "idempotence sweep of T001–T010 setup CLIs",
        "every command exits 0 and reports changed:false",
        "changed:false",
        sweep,
        sweep_ok,
    ))

    m = [e for e in entries if e["tier"] == "M"]
    a = [e for e in entries if e["tier"] == "A"]
    m_pass = sum(e["result"] == "PASS" for e in m)
    a_pass = sum(e["result"] == "PASS" for e in a)
    totals = {
        "M": {"total": len(m), "passed": m_pass, "failed": len(m) - m_pass},
        "A": {"total": len(a), "passed": a_pass, "failed": len(a) - a_pass},
        "all": {"total": len(entries),
                "passed": m_pass + a_pass,
                "failed": len(entries) - m_pass - a_pass},
    }
    document = {"criteria": entries, "totals": totals}
    if want_json:
        print(json.dumps(document, sort_keys=True))
    else:
        for entry in entries:
            print(f"{entry['id']} tier={entry['tier']} {entry['result']}")
        print(
            f"TIER M: {m_pass}/{len(m)} PASS · TIER A: {a_pass}/{len(a)} PASS · "
            f"TOTAL: {m_pass + a_pass}/{len(entries)}"
        )
    return 0 if totals["all"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
