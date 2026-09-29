"""lab-p7-measure-cycle: re-measure generate_incident and evaluate_arm_t2 (>=3 each).

Throwaway SC-01 generates do not touch the frozen headline ledger
SC-01_20260824T091611Z. evaluate_arm_t2 times T2 reset + lab-rank with no
results append (must not mutate results/SC-01.jsonl).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, run_bin, run_json, write_json
from lab_p7 import HEADLINE, frozen_sc01_hashes, point_current, recover_after_t2, root, stats
from lab_paths import env

MIN_N = 3
INHERITED = 49.335


def before_sc01() -> dict:
    return frozen_sc01_hashes()


def assert_sc01_untouched(before: dict) -> None:
    after = frozen_sc01_hashes()
    if after["db_jsonl_sha256"] != before["db_jsonl_sha256"]:
        die(EXIT_ASSERT, "assertion failed: frozen SC-01 ledger hash changed during measurement")
    if after["results_sha256"] != before["results_sha256"]:
        die(EXIT_ASSERT, "assertion failed: banked SC-01 results hash changed during measurement")


def measure_evaluate_t2(n: int, incident: str) -> list[dict]:
    from lab_evaluate_arm import stop_postgres
    runs = []
    point_current(incident)
    for i in range(n):
        t0 = time.monotonic()
        stop_postgres()
        reset = run_bin("lab-reset", ["--tier", "t2"], timeout=1800)
        if reset.returncode != 0:
            die(EXIT_ASSERT, f"assertion failed: lab-reset t2: {reset.stderr.strip() or reset.stdout.strip()}")
        recov = recover_after_t2(incident)
        if recov["barrier_exit"] != 0:
            die(EXIT_ASSERT, f"assertion failed: lab-barrier: {recov['barrier_stderr']}")
        naive = run_bin("lab-naive", [incident], timeout=120)
        if naive.returncode != 0:
            die(EXIT_ASSERT, f"assertion failed: lab-naive: {naive.stderr.strip() or naive.stdout.strip()}")
        wall = time.monotonic() - t0
        runs.append({
            "i": i + 1,
            "wall_s": wall,
            "reset_exit": reset.returncode,
            "naive_ok": True,
            "results_appended": False,
            "incident": incident,
        })
    return runs


def measure_generate(n: int) -> tuple[list[dict], list[str]]:
    runs = []
    throwaways = []
    for i in range(n):
        t0 = time.monotonic()
        proc = run_bin("lab-generate-p7", ["--scenario", "SC-02"], timeout=600)
        wall = time.monotonic() - t0
        if proc.returncode != 0:
            die(EXIT_ASSERT, f"assertion failed: lab-generate-p7 SC-02: {proc.stderr.strip()[-2000:] or proc.stdout.strip()[-2000:]}")
        payload = json.loads(proc.stdout)
        archive = payload["archive_incident"]
        if archive.startswith("SC-01") or archive == HEADLINE:
            die(EXIT_ASSERT, "assertion failed: generate reused or created an SC-01 incident")
        throwaways.append(archive)
        run_bin("lab-capture", ["stop", archive], timeout=90)
        run_bin("lab-slot", ["--create"], timeout=90)
        runs.append({
            "i": i + 1,
            "wall_s": wall,
            "archive_incident": archive,
            "incident_id": payload.get("incident_id"),
            "headline_untouched": True,
        })
    return runs, throwaways


def restore_headline() -> dict:
    # Do not T2 the frozen headline: its post_capture snapshot is already
    # invalidated, and T2 would be a guest rollback of SC-01.
    point_current(HEADLINE)
    run_bin("lab-consumer", ["stop", HEADLINE], timeout=60)
    return {"pointed_at": HEADLINE, "t2_attempted": False}


def gen_runs_from_incidents(incidents: list[str]) -> list[dict]:
    runs = []
    for i, archive in enumerate(incidents, start=1):
        path = Path(env("EVIDENCE_ROOT")) / "SC-02" / archive / "generate-commands.json"
        if not path.is_file():
            path = evidence_fallback(archive)
        rows = json.loads(path.read_text(encoding="utf-8"))
        elapsed = [r.get("elapsed_ms") for r in rows if isinstance(r.get("elapsed_ms"), (int, float))]
        if not elapsed:
            die(EXIT_ASSERT, f"assertion failed: no elapsed_ms in {path}")
        wall = max(elapsed) / 1000.0
        meta = json.loads((path.parent / "incident.json").read_text(encoding="utf-8"))
        runs.append({
            "i": i, "wall_s": wall, "archive_incident": archive,
            "incident_id": meta.get("incident_id"), "headline_untouched": True,
            "source": "generate-commands.json max elapsed_ms",
        })
    return runs


def evidence_fallback(archive: str) -> Path:
    from lab_paths import evidence_dir
    return evidence_dir(archive) / "generate-commands.json"


def main(argv: list[str]) -> int:
    n = MIN_N
    reuse: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--n" and i + 1 < len(argv):
            n = int(argv[i + 1])
            i += 2
            continue
        if argv[i] == "--reuse-generates" and i + 1 < len(argv):
            reuse = [x for x in argv[i + 1].split(",") if x]
            i += 2
            continue
        die(EXIT_USAGE, "usage: lab-p7-measure-cycle [--n 3] [--reuse-generates INC,...]")
    if n < MIN_N:
        die(EXIT_USAGE, f"usage: --n must be >= {MIN_N}")
    before = before_sc01()
    run_bin("lab-consumer", ["stop", "SC-01_20260826T064107Z"], timeout=60)
    if reuse:
        if len(reuse) < n:
            die(EXIT_USAGE, "--reuse-generates needs >= n incidents")
        gen_runs = gen_runs_from_incidents(reuse[:n] if len(reuse) == n else reuse[-n:])
        throwaways = [r["archive_incident"] for r in gen_runs]
    else:
        gen_runs, throwaways = measure_generate(n)
    if throwaways:
        point_current(throwaways[-1])
        run_bin("lab-slot", ["--create"], timeout=90)
        run_bin("lab-heartbeat", ["--start"], timeout=60)
        run_bin("lab-consumer", ["start", throwaways[-1]], timeout=90)
        time.sleep(3)
    ready = run_bin("lab-ready", [], timeout=30)
    ready_payload = {}
    try:
        ready_payload = json.loads(ready.stdout)
    except json.JSONDecodeError:
        ready_payload = {"stdout": ready.stdout, "stderr": ready.stderr, "exit": ready.returncode}
    if throwaways:
        run_bin("lab-capture", ["stop", throwaways[-1]], timeout=90)
        run_bin("lab-consumer", ["stop", throwaways[-1]], timeout=60)
        run_bin("lab-slot", ["--create"], timeout=90)
    eval_incident = throwaways[-1] if throwaways else HEADLINE
    eval_runs = measure_evaluate_t2(n, eval_incident)
    restored = restore_headline()
    assert_sc01_untouched(before)
    gen_s = [r["wall_s"] for r in gen_runs]
    ev_s = [r["wall_s"] for r in eval_runs]
    doc = {
        "inherited_cycle_s_not_used_as_budget": INHERITED,
        "generate_incident": {**stats(gen_s), "runs": gen_runs, "throwaway_incidents": throwaways},
        "evaluate_arm_t2": {**stats(ev_s), "runs": eval_runs, "results_appended": False},
        "lab_ready_during_throwaway": {"exit": ready.returncode, "ok": ready_payload.get("ok"),
                                       "incident": ready_payload.get("incident")},
        "headline_restored": restored,
        "sc01_ledger_sha256": before["db_jsonl_sha256"],
        "sc01_results_sha256": before["results_sha256"],
    }
    out = root() / "logs/review/K001/throughput.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, doc)
    print(json.dumps({"ok": True, "changed": True, "path": str(out),
                      "generate_mean_s": doc["generate_incident"]["mean_s"],
                      "evaluate_arm_t2_mean_s": doc["evaluate_arm_t2"]["mean_s"],
                      "lab_ready_exit": ready.returncode}, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
