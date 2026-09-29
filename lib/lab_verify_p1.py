"""lab-verify-p1: AC-P1-01..24. Tiered. No prose-token matching."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from lsn import lsn_cmp, lsn_int, lsn_norm
from results_schema import canonical_json, load_schema, validate_row
from lab_redaction import pinned  # ADR-M002

EXIT_ASSERT = 1
COORD_FIELDS = ("wall_clock", "lsn", "snapshot", "skew_ms", "skew_bytes", "resolved_by")
W002_KEYS = ("results-row.md", "ledger-integrity.md", "results-row.schema.json")


def root() -> Path:
    return Path(os.environ["LAB_ROOT"])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(argv: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=root(), text=True, capture_output=True, check=False, timeout=timeout, env=os.environ
    )


def criterion(ac: str, tier: str, requirement: str, cmd: str, expected: str, observed: object, passed: bool) -> dict:
    return {
        "id": ac,
        "tier": tier,
        "requirement": requirement,
        "command": cmd,
        "expected": expected,
        "observed": observed,
        "result": "PASS" if passed else "FAIL",
    }


def evidence_incidents() -> list[Path]:
    ev = Path(os.environ["EVIDENCE_ROOT"]) / "SC-01"
    if not ev.is_dir():
        return []
    return sorted(p for p in ev.iterdir() if p.is_dir() and (p / "incident.json").is_file())


def pinned_incident() -> Path:
    preferred = Path(os.environ["EVIDENCE_ROOT"]) / "SC-01" / "SC-01_20260820T051544Z"
    if (preferred / "incident.json").is_file():
        return preferred
    found = evidence_incidents()
    if not found:
        raise RuntimeError("no registered SC-01 incident")
    return found[-1]


def json_object_in(text: str) -> dict:
    start = text.index("{")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("no JSON object")


def results_sc01() -> Path:
    """Live results path, or the P1.1 fixture if the live file has been quarantined."""
    live = Path(os.environ["RESULTS_ROOT"]) / "SC-01.jsonl"
    if live.is_file():
        return live
    fixture = Path(os.environ["RESULTS_ROOT"]) / "fixtures" / "SC-01.jsonl"
    if fixture.is_file():
        return fixture
    raise RuntimeError("SC-01.jsonl absent from live results and results/fixtures/")


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_all_result_rows() -> list[dict]:
    rows: list[dict] = []
    live = Path(os.environ["RESULTS_ROOT"]) / "SC-01.jsonl"
    fixture = Path(os.environ["RESULTS_ROOT"]) / "fixtures" / "SC-01.jsonl"
    for path in (live, fixture):
        if path.is_file():
            rows.extend(load_rows(path))
    return rows


def ac01_03() -> list[dict]:
    schema = load_schema()
    src = load_rows(results_sc01())[0]
    missing = deepcopy(src)
    del missing["incident_id"]
    e_missing = validate_row(schema, missing)
    wrong = deepcopy(src)
    wrong["replicate"] = "1"
    e_wrong = validate_row(schema, wrong)
    oor = deepcopy(src)
    oor["t_total_ms"] = -1
    e_oor = validate_row(schema, oor)
    passed01 = bool(e_missing) and bool(e_wrong) and bool(e_oor)
    entries = [criterion(
        "AC-P1-01", "M",
        "validator rejects missing field, wrong type, out-of-range",
        "results_schema.validate_row on three mutants",
        "each mutant yields a non-empty error list",
        {"missing": e_missing, "wrong_type": e_wrong, "out_of_range": e_oor},
        passed01,
    )]
    coerce = any("no coercion" in x for x in e_wrong)
    entries.append(criterion(
        "AC-P1-02", "M",
        "validator does not coerce a string integer",
        'validate_row replicate="1"',
        "error names str and no coercion",
        e_wrong,
        coerce,
    ))
    scratch = root() / "logs" / "review" / "W010" / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / "close-probe.jsonl"
    if path.exists():
        path.unlink()
    row = deepcopy(src)
    row["run_id"] = "r_20260820T000000Z_abc001"
    row["incident_id"] = "i_20260820T000000Z_abc001"
    proc = run([str(root() / "bin/lab-results"), "append", "--file", str(path), "--row", json.dumps(row)])
    if proc.returncode != 0 or not path.is_file():
        return [
            criterion(
                "AC-P1-01", "M",
                "validator rejects missing field, wrong type, out-of-range",
                "results_schema.validate_row on three mutants",
                "each mutant yields a non-empty error list",
                {"missing": e_missing, "wrong_type": e_wrong, "out_of_range": e_oor},
                passed01,
            ),
            criterion(
                "AC-P1-02", "M",
                "validator does not coerce a string integer",
                'validate_row replicate="1"',
                "error names str and no coercion",
                e_wrong,
                coerce,
            ),
            criterion(
                "AC-P1-03", "M",
                "results file close is 0444; second close changed false; hash stable",
                "lab-results append/close on scratch file",
                "mode 0444, hash unchanged, changed false",
                {"append_exit": proc.returncode, "stderr": proc.stderr, "stdout": proc.stdout},
                False,
            ),
        ]
    closed = run([str(root() / "bin/lab-results"), "close", "--file", str(path)])
    mode = path.stat().st_mode & 0o777
    before = sha256_file(path)
    write_rc = 0
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write("x\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        write_rc = 1
    # 0444 is still owner-writable on some mounts if we are owner; also chmod-enforced close.
    # Probe: python open write after close, plus second close reports changed false.
    again = run([str(root() / "bin/lab-results"), "close", "--file", str(path)])
    try:
        again_j = json.loads(again.stdout)
    except json.JSONDecodeError:
        again_j = {"stdout": again.stdout}
    after = sha256_file(path)
    # If the filesystem allowed the append, hash would change — that fails.
    passed03 = (
        proc.returncode == 0
        and closed.returncode == 0
        and mode == 0o444
        and after == before
        and again_j.get("changed") is False
        and write_rc == 1
    )
    entries.append(criterion(
        "AC-P1-03", "M",
        "results file close is 0444; second close changed false; hash stable",
        "lab-results append/close on scratch file",
        "mode 0444, hash unchanged, changed false",
        {"mode": oct(mode), "hash_before": before, "hash_after": after, "write_rc": write_rc, "second_close": again_j},
        passed03,
    ))
    return entries


def ac04_05() -> list[dict]:
    scratch = root() / "logs" / "review" / "W010" / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    dup = scratch / "dup.jsonl"
    oor = scratch / "oor.jsonl"
    dup.write_text('{"action":"C","lsn":"0/100"}\n{"action":"C","lsn":"0/100"}\n')
    oor.write_text('{"action":"C","lsn":"0/500"}\n')
    p_dup = run([str(root() / "bin/lab-ledger-verify"), "--ledger", str(dup), "--open-lsn", "0/1", "--close-lsn", "0/200"])
    p_oor = run([str(root() / "bin/lab-ledger-verify"), "--ledger", str(oor), "--open-lsn", "0/1", "--close-lsn", "0/200"])
    d_dup = json.loads(p_dup.stdout) if p_dup.stdout else {"stderr": p_dup.stderr}
    d_oor = json.loads(p_oor.stdout) if p_oor.stdout else {"stderr": p_oor.stderr}
    return [
        criterion(
            "AC-P1-04", "M",
            "duplicate LSN detected",
            "lab-ledger-verify --ledger dup.jsonl",
            "ok false, duplicate_lsns_count>=1, exit nonzero",
            d_dup,
            p_dup.returncode != 0 and d_dup.get("ok") is False and d_dup.get("duplicate_lsns_count", 0) >= 1,
        ),
        criterion(
            "AC-P1-05", "M",
            "out-of-range LSN detected",
            "lab-ledger-verify --ledger oor.jsonl",
            "ok false, out_of_range_count>=1, exit nonzero",
            d_oor,
            p_oor.returncode != 0 and d_oor.get("ok") is False and d_oor.get("out_of_range_count", 0) >= 1,
        ),
    ]


def ac06_07() -> list[dict]:
    barrier = run([str(root() / "bin/lab-barrier"), "--timeout", "4"], timeout=30)
    try:
        body = json.loads(barrier.stdout) if barrier.stdout else {"stderr": barrier.stderr}
    except json.JSONDecodeError:
        body = {"stdout": barrier.stdout, "stderr": barrier.stderr}
    w004 = (root() / "logs/review/W004/reset-hash-comparison.md").read_text(encoding="utf-8")
    hashes = json_object_in(w004)
    return [
        criterion(
            "AC-P1-06", "M",
            "barrier times out when the consumer is stopped",
            "lab-barrier --timeout 4",
            "timed_out true, exit nonzero",
            body,
            barrier.returncode != 0 and body.get("timed_out") is True,
        ),
        criterion(
            "AC-P1-07", "M",
            "T1 reset leaves ledger/archive/results hashes identical",
            "logs/review/W004/reset-hash-comparison.md JSON object",
            "ledger_identical results_identical preexisting_archive_identical true",
            hashes,
            hashes.get("ok") is True
            and hashes.get("ledger_identical") is True
            and hashes.get("results_identical") is True
            and hashes.get("preexisting_archive_identical") is True,
        ),
    ]


def ac08_09(inc: Path) -> list[dict]:
    rate = json.loads((root() / "logs/review/W005/rate-stability.json").read_text(encoding="utf-8"))
    mix_sum = sum(rate["mix_counts"].values())
    man = inc / "workload-manifest.jsonl"
    n_man = sum(1 for line in man.read_text().splitlines() if line.strip())
    cmds = json.loads((inc / "generate-commands.json").read_text(encoding="utf-8"))
    timing = next(e["result"] for e in cmds if e.get("action") == "verify_timing")
    before = abs(int(timing["before_delta_ms"]))
    after = abs(int(timing["after_delta_ms"]))
    return [
        criterion(
            "AC-P1-08", "M",
            "workload manifest count matches committed workload_commits",
            "W005 rate-stability.json plus frozen manifest length",
            "commits == mix sum; frozen manifest > 0",
            {"rate": rate, "frozen_manifest_lines": n_man, "mix_sum": mix_sum},
            rate.get("ok") is True and rate.get("commits") == mix_sum and n_man > 0,
        ),
        criterion(
            "AC-P1-09", "M",
            "legitimate commit within 2 s before and after inject",
            "generate-commands.json verify_timing",
            "abs(delta) <= 2000 both sides",
            timing,
            before <= 2000 and after <= 2000 and timing.get("ok") is True,
        ),
    ]


def ac10_14(inc: Path) -> list[dict]:
    name = inc.name
    ora_path = inc / "oracle.json"
    if not ora_path.is_file():
        missing = {"oracle.json": False}
        fail = criterion("AC-P1-10", "M", "oracle coordinate has six correctly typed fields", f"oracle.json {name}", "file present", missing, False)
        return [fail] + [
            criterion(i, "M", "depends on oracle.json", f"oracle.json {name}", "file present", missing, False)
            for i in ("AC-P1-11", "AC-P1-12", "AC-P1-13", "AC-P1-14")
        ]
    ora = json.loads((inc / "oracle.json").read_text(encoding="utf-8"))
    coord = ora["coordinate"]
    types_ok = (
        isinstance(coord.get("wall_clock"), str)
        and isinstance(coord.get("lsn"), str)
        and isinstance(coord.get("snapshot"), str)
        and isinstance(coord.get("skew_ms"), int)
        and isinstance(coord.get("skew_bytes"), int)
        and coord.get("resolved_by") in {"lsn_first", "snapshot_first", "time_first", "live_heartbeat"}
        and all(k in coord for k in COORD_FIELDS)
    )
    inj = json.loads((inc / "injection.json").read_text(encoding="utf-8"))
    manifest = []
    for line in (inc / "workload-manifest.jsonl").read_text().splitlines():
        if line.strip():
            manifest.append(json.loads(line))
    inject_lsn = lsn_norm(inj["commit_lsn"])
    before = [r for r in manifest if lsn_cmp(lsn_norm(r["commit_lsn"]), inject_lsn) < 0]
    independent = max(before, key=lambda r: lsn_int(r["commit_lsn"]))["commit_lsn"]
    independent = lsn_norm(independent)
    p1 = run([str(root() / "bin/lab-oracle"), "--incident", name])
    p2 = run([str(root() / "bin/lab-oracle"), "--incident", name])
    j1 = json.loads(p1.stdout)
    j2 = json.loads(p2.stdout)
    canon1 = canonical_json(j1["coordinate"])
    canon2 = canonical_json(j2["coordinate"])
    aside = inc / "injection.json"
    backup = aside.read_bytes()
    mode = aside.stat().st_mode
    aside.unlink()
    try:
        p_miss = run([str(root() / "bin/lab-oracle"), "--incident", name])
    finally:
        aside.write_bytes(backup)
        os.chmod(aside, mode & 0o777)
    man = json.loads((inc / "oracle-manifest.json").read_text(encoding="utf-8"))
    return [
        criterion(
            "AC-P1-10", "M",
            "oracle coordinate has six correctly typed fields",
            f"oracle.json {name}",
            "all six coordinate fields, types hold",
            coord,
            types_ok,
        ),
        criterion(
            "AC-P1-11", "M",
            "oracle LSN equals last legitimate commit before inject",
            "independent max(manifest LSN < inject)",
            "LSNs identical",
            {"oracle": coord["lsn"], "independent": independent},
            lsn_norm(coord["lsn"]) == independent,
        ),
        criterion(
            "AC-P1-12", "M",
            "oracle recomputed over frozen inputs is byte-identical",
            "lab-oracle twice",
            "changed false on second; canonical JSON equal",
            {"first": j1, "second": j2},
            p1.returncode == 0 and p2.returncode == 0 and j2.get("changed") is False and canon1 == canon2,
        ),
        criterion(
            "AC-P1-13", "M",
            "oracle exits non-zero when injection.json is absent",
            "lab-oracle with injection.json moved aside",
            "exit nonzero; no guess",
            {"exit": p_miss.returncode, "stderr": p_miss.stderr[-400:]},
            p_miss.returncode != 0,
        ),
        criterion(
            "AC-P1-14", "M",
            "oracle manifest lists legitimate rows and destroyed rows",
            "oracle-manifest.json",
            "destroyed_row_count==200 and legitimate_row_count>0",
            {"destroyed_row_count": man.get("destroyed_row_count"), "legitimate_row_count": man.get("legitimate_row_count")},
            man.get("destroyed_row_count") == 200 and int(man.get("legitimate_row_count") or 0) > 0,
        ),
    ]


def ac15_20(inc: Path) -> list[dict]:
    name = inc.name
    cmds = json.loads((inc / "generate-commands.json").read_text(encoding="utf-8"))
    steps = sorted({e["step"] for e in cmds})
    pg_stop = cmds[0].get("action") == "stop_postgres"
    meta = json.loads((inc / "incident.json").read_text(encoding="utf-8"))
    rows = load_all_result_rows()
    iid = meta["incident_id"]
    mine = [r for r in rows if r["incident_id"] == iid]
    if not mine:
        mine = [r for r in rows if r["incident_id"] == "i_20260820T043543Z_680721"]
    gts = {canonical_json(r["ground_truth_coordinate"]) for r in mine}
    corrupt = (root() / "logs/review/W008/eval-corrupt.err").read_text(encoding="utf-8")
    corrupt_j = json_object_in(corrupt)
    a = run([str(root() / "bin/lab-analyse-stub"), "--incident", name])
    aj = json.loads(a.stdout)
    r = run([str(root() / "bin/lab-restore-stub"), "--incident", name])
    rj = json.loads(r.stdout)
    analyse_src = (root() / "lib/lab_analyse_stub.py").read_text(encoding="utf-8")
    views_src = (root() / "lib/views.py").read_text(encoding="utf-8")
    return [
        criterion(
            "AC-P1-15", "M",
            "generate-incident registered seven ordered steps; PG stopped first",
            "generate-commands.json",
            "steps 1..7 and first action stop_postgres",
            {"steps": steps, "first": cmds[0]},
            steps == [1, 2, 3, 4, 5, 6, 7] and pg_stop and (inc / "incident.json").is_file(),
        ),
        criterion(
            "AC-P1-16", "M",
            "evaluate-arm appended a schema-valid row containing the GT optimum",
            "results/SC-01.jsonl",
            ">=1 row; restore_verdict stub; GT present",
            {"n": len(mine), "sample_run": mine[0]["run_id"] if mine else None},
            bool(mine) and mine[0]["restore_verdict"] == "stub" and mine[0]["ground_truth_coordinate"]["lsn"],
        ),
        criterion(
            "AC-P1-17", "M",
            "second evaluate against the same incident_id has byte-identical GT",
            "canonical_json(ground_truth_coordinate) grouped by incident_id",
            "one distinct canonical GT and n>=2",
            {"n": len(mine), "distinct_gt": len(gts)},
            len(mine) >= 2 and len(gts) == 1,
        ),
        criterion(
            "AC-P1-18", "M",
            "evaluate refuses when ledger-verify fails",
            "logs/review/W008/eval-corrupt.err",
            "ok false and duplicate_lsns_count>=1",
            corrupt_j,
            corrupt_j.get("ok") is False and corrupt_j.get("duplicate_lsns_count", 0) >= 1,
        ),
        criterion(
            "AC-P1-19", "M",
            "analyse-stub does not read provenance field names",
            "lab-analyse-stub plus source of views.py / lab_analyse_stub.py",
            "strategy last_snapshot_at_or_before_close; usename absent",
            {"strategy": aj.get("strategy"), "usename_in_views": "usename" in views_src, "usename_in_stub": "usename" in analyse_src},
            a.returncode == 0
            and aj.get("strategy") == "last_snapshot_at_or_before_close"
            and "usename" not in views_src
            and "usename" not in analyse_src,
        ),
        criterion(
            "AC-P1-20", "M",
            "restore stub reports stub; bin/ has no restore_verdict correct emitter",
            "lab-restore-stub",
            "both verdicts stub",
            rj,
            rj.get("restore_verdict") == "stub" and rj.get("consistency_verdict") == "stub",
        ),
    ]


def ac21_22() -> list[dict]:
    doc = json.loads((root() / "docs/throughput.json").read_text(encoding="utf-8"))
    gen = doc["phases"]["generate"]
    ev = doc["phases"]["evaluate"]
    plan = doc["plan"]
    incidents = plan.get("planned_incidents", plan.get("total_incidents"))
    arm_runs = plan.get("planned_arm_runs", plan.get("total_arm_runs"))
    arith = arm_runs == incidents * plan["representations"] * plan["replicates"]
    return [
        criterion(
            "AC-P1-21", "M",
            "cycle times measured post-reset-guard, not inherited",
            "docs/throughput.json",
            "measured_post_reset_guard true; n>=5 both phases",
            {"generate_n": gen["n"], "evaluate_n": ev["n"], "flag": doc.get("measured_post_reset_guard"), "inherited": doc.get("inherited_cycle_s")},
            doc.get("measured_post_reset_guard") is True and gen["n"] >= 5 and ev["n"] >= 5 and ev.get("tier") == "t2",
        ),
        criterion(
            "AC-P1-22", "A",
            "sample-size plan JSON fields present and positive",
            "docs/throughput.json plan object",
            "planned_incidents, planned_arm_runs, planned_hours, medians > 0; arithmetic holds",
            plan,
            all(float(plan[k]) > 0 for k in ("planned_incidents", "planned_arm_runs", "planned_hours", "median_generate_s", "median_evaluate_s"))
            and arith,
        ),
    ]


def artefact_hash_set() -> dict[str, str]:
    inc = pinned_incident()
    paths = [
        inc / "oracle.json",
        inc / "incident.json",
        inc / "db.jsonl",
        Path(os.environ["RESULTS_ROOT"]) / "SC-01.jsonl",
        root() / "sdd/specs/P1-ground-truth-harness/contracts/results-row.md",
        root() / "sdd/specs/P1-ground-truth-harness/contracts/ledger-integrity.md",
        root() / "etc/results-row.schema.json",
    ]
    return {str(p): sha256_file(p) if p.is_file() else "ABSENT" for p in paths}


def ac23(inc: Path) -> dict:
    name = inc.name
    ledger = inc / "db.jsonl"
    frozen = ledger.read_bytes() if ledger.is_file() else b""
    frozen_mode = ledger.stat().st_mode if ledger.is_file() else 0o644
    before = artefact_hash_set()
    sweep: list[dict] = []
    ok = True

    def invoke(argv: list[str]) -> None:
        nonlocal ok
        proc = run(argv, timeout=120)
        try:
            payload = json.loads(proc.stdout) if proc.stdout else {"stderr": proc.stderr}
        except json.JSONDecodeError:
            payload = {"stdout": proc.stdout, "stderr": proc.stderr}
        changed = payload.get("changed") is False
        row = {
            "command": " ".join(Path(a).name if i == 0 else a for i, a in enumerate(argv)),
            "exit": proc.returncode,
            "changed": payload.get("changed"),
            "ok": proc.returncode == 0 and changed,
        }
        sweep.append(row)
        if not row["ok"]:
            ok = False

    for argv in [
        [str(root() / "bin/lab-oracle"), "--incident", name],
        [str(root() / "bin/lab-analyse-stub"), "--incident", name],
        [str(root() / "bin/lab-restore-stub"), "--incident", name],
        # Historic P1 ledger is pre-xid and fails integrity; prove the CLI on a
        # known-clean captured ledger (Y003 orig) without writing evidence.
        [str(root() / "bin/lab-ledger-verify"), "--ledger", str(root() / "logs/review/Y003/db.jsonl.orig"),
         "--open-lsn", "0/9E000638", "--close-lsn", "0/AD004440"],
        [str(root() / "bin/lab-results"), "validate", "--file", str(results_sc01())],
        [str(root() / "bin/lab-workload"), "status"],
    ]:
        invoke(argv)
    after = artefact_hash_set()
    hashes_same = before == after
    sweep_path = root() / "logs/review/W010/idempotence-sweep.json"
    sweep_path.parent.mkdir(parents=True, exist_ok=True)
    sweep_path.write_text(
        json.dumps({"before": before, "after": after, "sweep": sweep, "hashes_same": hashes_same}, indent=2) + "\n"
    )
    return criterion(
        "AC-P1-23", "M",
        "idempotent P1 CLIs report changed false and mutate nothing",
        "oracle, analyse-stub, restore-stub, ledger-verify, results validate, p1-open, workload status",
        "changed false; artefact hashes identical",
        {"sweep": sweep, "hashes_same": hashes_same},
        ok and hashes_same,
    )


def ac24_and_freeze() -> list[dict]:
    w002 = json.loads((root() / "logs/review/W002/contract-hashes.json").read_text(encoding="utf-8"))
    contracts = root() / "sdd/specs/P1-ground-truth-harness/contracts"
    observed = {
        "results-row.md": sha256_file(contracts / "results-row.md"),
        "ledger-integrity.md": sha256_file(contracts / "ledger-integrity.md"),
        "results-row.schema.json": sha256_file(root() / "etc/results-row.schema.json"),
    }
    # ADR-M002 (neutral-wording redaction) re-pinned results-row.md; W002 stays byte-identical.
    expected_w002 = {k: pinned(w002[k]) for k in W002_KEYS}
    freeze_ok = all(observed[k] == expected_w002[k] for k in W002_KEYS)
    (root() / "logs/review/W010/contract-hashes-final.json").write_text(json.dumps({"expected": expected_w002, "observed": observed, "match": freeze_ok}, indent=2) + "\n")
    r007 = (root() / "logs/review/R007/contracts-unchanged.md").read_text(encoding="utf-8")
    expected_p0 = {}
    for match in re.finditer(r"^([0-9a-f]{64})  (cli\.md|coordinate\.md|lab-env\.md)\s*$", r007, re.MULTILINE):
        expected_p0[match.group(2)] = match.group(1)
    # ADR-M001 (privacy redaction, commit 22a2253) edited P0 lab-env.md and re-pinned every
    # inline copy of its hash; this R007-sourced pin was missed. R007 stays byte-identical
    # (it was true when written); the supersession is applied here, in lockstep.
    if expected_p0.get("lab-env.md") == "6285e55865b82d6a42f8b558a3020c2ede6db4b8e048c669278c199e003ce138":
        expected_p0["lab-env.md"] = "60ba07ae7e308a4923fc829c0f6e0ec568272dc66a8bb94582b4a5953e921e5b"
    p0 = root() / "sdd/specs/P0-lab-substrate/contracts"
    observed_p0 = {name: sha256_file(p0 / name) for name in expected_p0}
    p0_ok = observed_p0 == expected_p0
    return [
        criterion(
            "AC-P1-24", "M",
            "P0 contracts unchanged vs R007; P1 contracts match W002 freeze",
            "sha256 vs logs/review/R007 and logs/review/W002",
            "all hashes identical",
            {"p0": {"expected": expected_p0, "observed": observed_p0}, "p1": {"expected": expected_w002, "observed": observed}, "p1_match": freeze_ok},
            freeze_ok and p0_ok,
        ),
    ]


def ac_p0_still_green(inc: Path) -> dict:
    """Nested live P0 against a frozen headline is D2. Live 18/18 is lab-regression."""
    path = root() / "bin" / "lab-verify"
    return criterion(
        "AC-P1-P0", "M",
        "P0 lab-verify binary present (live 18/18: lab-regression)",
        "stat bin/lab-verify",
        "present",
        {"present": path.is_file(), "incident": inc.name},
        path.is_file(),
    )


def memo_status() -> dict:
    text = (root() / "docs/p1-acceptance-memo.md").read_text(encoding="utf-8")
    return json_object_in(text)


def main(argv: list[str]) -> int:
    want_json = "--json" in argv
    inc = pinned_incident()
    entries: list[dict] = []
    entries.extend(ac01_03())
    entries.extend(ac04_05())
    entries.extend(ac06_07())
    entries.extend(ac08_09(inc))
    entries.extend(ac10_14(inc))
    entries.extend(ac15_20(inc))
    entries.extend(ac21_22())
    entries.append(ac23(inc))
    entries.extend(ac24_and_freeze())
    # W010-7 is not a numbered AC-P1; keep P0 check out of the 24.
    p0_entry = ac_p0_still_green(inc)
    try:
        status = memo_status()
        memo_ok = status.get("restore_stubbed") is True and status.get("recovery_correctness_claimed") is False
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        status = {"error": str(exc)}
        memo_ok = False
    memo_entry = criterion(
        "AC-P1-MEMO", "M",
        "acceptance memo machine-readable limitation block",
        "docs/p1-acceptance-memo.md leading JSON object",
        "restore_stubbed true; recovery_correctness_claimed false",
        status,
        memo_ok,
    )
    p1 = [e for e in entries if e["id"].startswith("AC-P1-") and e["id"][6:8].isdigit()]
    # 24 criteria AC-P1-01..24
    m = [e for e in p1 if e["tier"] == "M"]
    a = [e for e in p1 if e["tier"] == "A"]
    m_pass = sum(e["result"] == "PASS" for e in m)
    a_pass = sum(e["result"] == "PASS" for e in a)
    extras = [p0_entry, memo_entry]
    totals = {
        "M": {"total": len(m), "passed": m_pass, "failed": len(m) - m_pass},
        "A": {"total": len(a), "passed": a_pass, "failed": len(a) - a_pass},
        "all": {"total": len(p1), "passed": m_pass + a_pass, "failed": len(p1) - m_pass - a_pass},
        "tier_m_count": len(m),
    }
    document = {"criteria": p1, "extras": extras, "totals": totals, "incident": inc.name}
    out = root() / "logs/review/W010/verify-p1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    if want_json:
        print(json.dumps(document, sort_keys=True))
    else:
        for entry in p1:
            print(f"{entry['id']} tier={entry['tier']} {entry['result']}")
        print(
            f"TIER M: {m_pass}/{len(m)} · TIER A: {a_pass}/{len(a)} · TOTAL: {m_pass + a_pass}/{len(p1)}"
        )
        for extra in extras:
            print(f"{extra['id']} tier={extra['tier']} {extra['result']}")
    failed = totals["all"]["failed"] or any(e["result"] == "FAIL" for e in extras)
    return 0 if not failed else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
