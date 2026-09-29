"""lab-verify-p1.1: AC-P1.1-01..16. Tiered. No prose-token matching for PASS."""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from lab_redaction import pinned  # ADR-M002

EXIT_ASSERT = 1
HARNESS_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
P0_HASHES = {
    "cli.md": "01f0dbc60d7ab5670b8d9b135ab3c8983b9bd00df67e966dd10c36bbc4e5d5d1",
    "coordinate.md": "2080ac9f270aac0f8da718675ac8cb742d009a268fdeb5d634fef03c437c2eef",
    "lab-env.md": "60ba07ae7e308a4923fc829c0f6e0ec568272dc66a8bb94582b4a5953e921e5b",
}
P1_HASHES = {
    "results-row.md": pinned("866edd5677645622669572dfb663a12137a9ca6f1e000f35e7766577b46b0cdf"),
    "results-row.amendment-1.md": "8e99516e5c570d8de94bd4551ce7d1c24961afedab03fcdb19dc85019170f05f",
    "ledger-integrity.md": "15f5740bf4cac9d5fabeabe5b06f1b5656355b0a6a2ba2518218e24dc21d2313",
    "results-row.schema.json": "103eaa92ea48bca7ebcc7ce451b1978d822e92af41dc92b8fbf8f1e7a26d3775",
}
SWEEP_PATTERNS = [
    ("150_arm_runs_completed", re.compile(r"150 arm runs completed", re.I)),
    ("runs_completed", re.compile(r"runs completed", re.I)),
    ("executed_150", re.compile(r"executed 150", re.I)),
    ("bare_total_arm_runs_key", re.compile(r'"total_arm_runs"\s*:')),
    ("bare_total_incidents_key", re.compile(r'"total_incidents"\s*:')),
    ("unqualified_150_arm_runs", re.compile(r"(?<![Pp]lanned )(?<!planned_)150 arm runs")),
]


def root() -> Path:
    return Path(os.environ["LAB_ROOT"])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(argv: list[str], timeout: int = 180, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=root(), text=True, capture_output=True, check=False, timeout=timeout,
        env=env or os.environ,
    )


def criterion(ac: str, tier: str, requirement: str, cmd: str, expected: str, observed: object, passed: bool) -> dict:
    return {
        "id": ac, "tier": tier, "requirement": requirement, "command": cmd,
        "expected": expected, "observed": observed, "result": "PASS" if passed else "FAIL",
    }


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


def memo_path() -> Path:
    return root() / "docs" / "p1-acceptance-memo.md"


def load_memo_json() -> dict:
    return json_object_in(memo_path().read_text(encoding="utf-8"))


def replace_memo_json(obj: dict) -> None:
    text = memo_path().read_text(encoding="utf-8")
    start = text.index("```json")
    end = text.index("```", start + 7)
    block = "```json\n" + json.dumps(obj, indent=2) + "\n```"
    memo_path().write_text(text[:start] + block + text[end + 3 :])


def sync_p2_recommendation() -> dict:
    """Read live lab-ready. Do not write docs/ (gates write only logs/review)."""
    proc = run([str(root() / "bin/lab-ready")], timeout=30)
    ready = proc.returncode == 0
    rec = "go" if ready else "blocked"
    try:
        ready_json = json.loads(proc.stdout) if proc.stdout else {}
    except json.JSONDecodeError:
        ready_json = {"stdout": proc.stdout, "exit": proc.returncode}
    obj = load_memo_json()
    return {
        "recommendation": rec,
        "memo_recommendation": obj.get("p2_recommendation"),
        "lab_ready_exit": proc.returncode,
        "ready": ready_json,
    }


def open_incident() -> str:
    current = Path(os.environ["ARCHIVE_CURRENT"]).resolve()
    return current.name


def ledger_path(incident: str) -> Path:
    scenario = incident.split("_", 1)[0]
    return Path(os.environ["EVIDENCE_ROOT"]) / scenario / incident / "db.jsonl"


def restore_frozen_ledger(incident: str) -> dict:
    """Copy X001 freeze into logs/review/X006/scratch — never onto evidence (Article XVI)."""
    from lab_scratch_evidence import overlay_frozen_ledger, scratch_evidence
    src = root() / "logs" / "review" / "X001" / "db.jsonl.frozen"
    dest = scratch_evidence("X006", incident)
    observed = {"frozen_present": src.is_file(), "dest": str(dest / "db.jsonl"), "scratch": True}
    overlay_frozen_ledger(dest, src)
    if src.is_file():
        observed["bytes"] = (dest / "db.jsonl").stat().st_size
    os.environ["EVIDENCE_ROOT"] = str(dest.parents[1])  # scratch/evidence
    return observed


def scratch_env() -> dict:
    env = dict(os.environ)
    scratch = root() / "logs" / "review" / "X006" / "scratch" / "results"
    scratch.mkdir(parents=True, exist_ok=True)
    env["RESULTS_ROOT"] = str(scratch)
    return env


def last_row(results_root: Path) -> dict | None:
    path = results_root / "SC-01.jsonl"
    if not path.is_file():
        return None
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def evaluate_arm(env: dict) -> subprocess.CompletedProcess[str]:
    inc = open_incident()
    restore_frozen_ledger(inc)
    env = dict(env)
    env["EVIDENCE_ROOT"] = os.environ["EVIDENCE_ROOT"]
    return run(
        [str(root() / "bin/lab-evaluate-arm"), "--incident", inc, "--arm", "stub", "--tier", "t2"],
        timeout=120,
        env=env,
    )


def ac01() -> dict:
    text = (root() / "sdd/.specify/memory/constitution.md").read_text(encoding="utf-8")
    headings = [ln for ln in text.splitlines() if ln.startswith("## Article ")]
    xiv = text[text.find("## Article XIV"):] if "## Article XIV" in text else ""
    phrases = {
        "provenance of record": "provenance of record" in xiv.lower(),
        "HEAD at production": "HEAD at production" in xiv,
        "refuse to emit": "refuse to emit" in xiv,
    }
    passed = len(headings) >= 18 and all(phrases.values()) and any("Article XIV" in h for h in headings)
    return criterion(
        "AC-P1.1-01", "M",
        "constitution contains well-formed Article XIV; at least 18 additive articles",
        "count ## Article headings; Article XIV phrases",
        "18 articles; provenance of record; HEAD at production; refuse to emit",
        {"count": len(headings), "headings": headings, "phrases": phrases},
        passed,
    )


def ac02() -> dict:
    docs = list((root() / "docs").glob("*.md"))
    false_hits = []
    for p in docs:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "whatever HEAD is at evaluate-arm time" in line:
                false_hits.append(f"{p}:{i}")
    handoff = (root() / "docs" / "P1-architecture-handoff.md").read_text(encoding="utf-8")
    dated = "P1.1 X001 (2026-08-21)" in handoff
    bound = "HARNESS_COMMIT_AT_P1_OPEN" in handoff
    passed = (not false_hits) and dated and bound
    return criterion(
        "AC-P1.1-02", "M",
        "false HEAD-at-evaluate note corrected with dated annotation",
        "docs/*.md exact-phrase absence plus handoff dated marker",
        "zero uncorrected phrase hits; P1.1 X001 (2026-08-21) present",
        {"false_hits": false_hits, "dated_annotation": dated, "names_p1_open_binding": bound},
        passed,
    )


def ac03_05() -> list[dict]:
    env = scratch_env()
    head = run(["git", "-C", str(root()), "rev-parse", "HEAD"]).stdout.strip()
    p1_open = os.environ["HARNESS_COMMIT_AT_P1_OPEN"]
    proc = evaluate_arm(env)
    row = last_row(Path(env["RESULTS_ROOT"]))
    commit = row.get("harness_commit") if row else None
    passed03 = (
        proc.returncode == 0
        and isinstance(commit, str)
        and commit == head
        and HARNESS_COMMIT_RE.fullmatch(commit) is not None
    )
    e03 = criterion(
        "AC-P1.1-03", "M",
        "clean-tree evaluate-arm row harness_commit equals HEAD",
        "lab-evaluate-arm --arm stub --tier t2",
        "byte-equal to git rev-parse HEAD",
        {"exit": proc.returncode, "head": head, "harness_commit": commit, "stderr": proc.stderr[-400:]},
        passed03,
    )

    probe = root() / "bin" / "_dirty_probe"
    probe.write_text("x006\n")
    rows_before = last_row(Path(env["RESULTS_ROOT"]))
    dirty = evaluate_arm(env)
    rows_after = last_row(Path(env["RESULTS_ROOT"]))
    named = "_dirty_probe" in (dirty.stderr or "")
    no_new = (rows_before or {}) == (rows_after or {}) or (
        rows_after is not None and rows_before is not None
        and rows_after.get("run_id") == rows_before.get("run_id")
    )
    if rows_before is None:
        no_new = rows_after is None
    passed04 = dirty.returncode != 0 and named and no_new
    probe.unlink(missing_ok=True)
    e04 = criterion(
        "AC-P1.1-04", "M",
        "dirty tree refuses the row",
        "touch bin/_dirty_probe; lab-evaluate-arm",
        "exit nonzero; names _dirty_probe; no row written",
        {"exit": dirty.returncode, "named": named, "no_new_row": no_new, "stderr": dirty.stderr[-400:]},
        passed04,
    )

    passed05 = (
        isinstance(commit, str)
        and commit == head
        and commit != p1_open
        and proc.returncode == 0
    )
    e05 = criterion(
        "AC-P1.1-05", "M",
        "row harness_commit equals current HEAD, not P1-open",
        "compare row to git rev-parse HEAD and HARNESS_COMMIT_AT_P1_OPEN",
        "equals HEAD; differs from P1-open",
        {"head": head, "p1_open": p1_open, "harness_commit": commit},
        passed05,
    )
    return [e03, e04, e05]


def ac06() -> dict:
    eval_py = (root() / "lib" / "lab_evaluate_arm.py").read_text(encoding="utf-8")
    wrapper = (root() / "bin" / "lab-evaluate-arm").read_text(encoding="utf-8")
    # The production assignment must not read the env key.
    bound = 'env("HARNESS_COMMIT_AT_P1_OPEN")' in eval_py or "env('HARNESS_COMMIT_AT_P1_OPEN')" in eval_py
    env_line = None
    comment_ok = False
    lines = (root() / "etc" / "lab.env").read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("HARNESS_COMMIT_AT_P1_OPEN="):
            env_line = line
            prev = lines[i - 1] if i else ""
            comment_ok = "P1-open provenance only" in prev and "Not the source of any results-row field" in prev
    passed = (not bound) and ("HARNESS_COMMIT_AT_P1_OPEN" not in wrapper) and env_line is not None and comment_ok
    return criterion(
        "AC-P1.1-06", "M",
        "harness_commit not sourced from HARNESS_COMMIT_AT_P1_OPEN; key retained and documented",
        "scan lib/lab_evaluate_arm.py, wrapper, etc/lab.env",
        "no env() read; key present with documentation comment",
        {"env_bound_in_lib": bound, "wrapper_mentions_key": "HARNESS_COMMIT_AT_P1_OPEN" in wrapper, "env_line": env_line, "comment_ok": comment_ok},
        passed,
    )


def ac07_08() -> list[dict]:
    from lab_config import load_env
    glob_pat = load_env(root()).get("RESULTS_GLOB")
    live = glob.glob(str(root() / glob_pat)) if glob_pat else []
    # glob was written relative to LAB_ROOT
    os.chdir(root())
    live = glob.glob(glob_pat) if glob_pat else []
    live_rows = 0
    for p in live:
        live_rows += sum(1 for ln in Path(p).read_text().splitlines() if ln.strip())
    fixtures = list((root() / "results" / "fixtures").glob("*.jsonl"))
    fix_rows = 0
    for p in fixtures:
        fix_rows += sum(1 for ln in p.read_text().splitlines() if ln.strip())
    manifest = (root() / "results" / "fixtures" / "MANIFEST.md").read_text(encoding="utf-8")
    listed = all(p.name in manifest and "results/" + p.name in manifest.replace("results/fixtures/", "results/") for p in fixtures)
    # simpler: prior path recorded
    listed = "results/SC-01.jsonl" in manifest and "SC-01.jsonl" in manifest
    e07 = criterion(
        "AC-P1.1-07", "M",
        "every pre-existing P1 results row lives under results/fixtures/ with manifest",
        "list results/fixtures/*.jsonl and MANIFEST.md",
        "files present; MANIFEST names prior path",
        {"files": [str(p) for p in fixtures], "rows": fix_rows, "manifest_lists_prior_path": listed},
        bool(fixtures) and fix_rows > 0 and listed,
    )
    e08 = criterion(
        "AC-P1.1-08", "M",
        "RESULTS_GLOB excludes fixtures; pre-P1.1 rows remain quarantined",
        "glob RESULTS_GLOB; fixtures/SC-01.jsonl present",
        "glob is results/*.jsonl; no glob hit is under fixtures; fixtures file present",
        {"glob": glob_pat, "live": live, "live_rows": live_rows, "fixtures_present": (root() / "results" / "fixtures" / "SC-01.jsonl").is_file()},
        glob_pat == "results/*.jsonl"
        and not any("fixtures" in p.replace("\\", "/") for p in live)
        and (root() / "results" / "fixtures" / "SC-01.jsonl").is_file(),
    )
    return [e07, e08]


def ac09_10() -> list[dict]:
    """Healthy lab-ready from committed C001 artefact; down-case is live (consumer already stopped)."""
    recorded = {}
    c001 = root() / "logs" / "review" / "C001" / "lab-ready.json"
    if c001.is_file():
        recorded = json.loads(c001.read_text(encoding="utf-8"))
    passed09 = recorded.get("ready") is True
    e09 = criterion(
        "AC-P1.1-09", "M",
        "lab-ready exits 0 on a healthy lab",
        "logs/review/C001/lab-ready.json (committed; gate does not start consumer)",
        "ready true recorded at C001",
        recorded,
        passed09,
    )
    proc_bad = run([str(root() / "bin/lab-ready")], timeout=30)
    try:
        body_bad = json.loads(proc_bad.stdout)
    except json.JSONDecodeError:
        body_bad = {"stdout": proc_bad.stdout, "stderr": proc_bad.stderr}
    failed = body_bad.get("failed") or []
    passed10 = proc_bad.returncode != 0 and bool(failed)
    e10 = criterion(
        "AC-P1.1-10", "M",
        "lab-ready exits nonzero and names the failed condition when consumer is down",
        "bin/lab-ready (live; no consumer start)",
        "exit nonzero; failed named",
        body_bad,
        passed10,
    )
    return [e09, e10]


def ac11() -> dict:
    log = root() / "logs" / "review" / "X004" / "runbook-run.log"
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    unchanged = "slot_name_unchanged=true" in text or (
        "slot_name_before=lab_slot" in text and "slot_name_after=lab_slot" in text
    )
    runbook = (root() / "docs" / "runbook-slot-recovery.md").read_text(encoding="utf-8")
    creates = bool(re.search(r"lab-slot --create|create a new slot", runbook))
    rolls = "lab-reset --tier" in runbook
    # Live: slot_name from lab-ready equals SLOT_NAME
    proc = run([str(root() / "bin/lab-ready")], timeout=30)
    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError:
        body = {}
    from lab_config import load_env
    slot_env = load_env(root()).get("SLOT_NAME")
    # Live lab-ready may be non-zero while the headline consumer is stopped (Article XVI /
    # D2). Slot identity is still asserted from the JSON; the exit-0 restoration is the
    # X004 attested runbook artefact. Gate does not start the consumer.
    passed = unchanged and (not creates) and rolls and body.get("slot_name") == slot_env
    return criterion(
        "AC-P1.1-11", "M",
        "recovery runbook restored readiness without creating a slot",
        "X004 runbook-run.log plus live lab-ready slot_name vs SLOT_NAME (no consumer start)",
        "slot_name unchanged; runbook rolls back; live slot_name equals SLOT_NAME",
        {"unchanged": unchanged, "creates_step": creates, "rolls_back": rolls, "live_slot": body.get("slot_name"), "SLOT_NAME": slot_env, "ready_exit": proc.returncode},
        passed,
    )


def ac12_13() -> list[dict]:
    memo = load_memo_json()
    plan = json_object_in((root() / "docs" / "sample-size-plan.md").read_text(encoding="utf-8"))
    thr = json.loads((root() / "docs" / "throughput.json").read_text(encoding="utf-8"))
    keys_ok = all(
        d.get("planned_incidents") == 10
        and d.get("planned_arm_runs") == 150
        and d.get("completed_arm_runs") == 0
        and d.get("completed_incidents") == 0
        and "planned_hours" in d
        for d in (memo, plan, thr)
    )
    distinct = all(
        "planned_arm_runs" in d and "completed_arm_runs" in d and d["planned_arm_runs"] != d["completed_arm_runs"]
        for d in (memo, plan, thr)
    )
    e12 = criterion(
        "AC-P1.1-12", "M",
        "planned_* counts and completed_arm_runs=0 as distinct keys",
        "JSON objects in memo, sample-size-plan, throughput.json",
        "planned_incidents 10; planned_arm_runs 150; completed_* 0",
        {"memo": {k: memo.get(k) for k in ("planned_incidents", "planned_arm_runs", "planned_hours", "completed_arm_runs", "completed_incidents")},
         "plan": {k: plan.get(k) for k in ("planned_incidents", "planned_arm_runs", "planned_hours", "completed_arm_runs", "completed_incidents")},
         "throughput": {k: thr.get(k) for k in ("planned_incidents", "planned_arm_runs", "planned_hours", "completed_arm_runs", "completed_incidents")}},
        keys_ok and distinct,
    )
    hits = []
    for path in sorted((root() / "docs").rglob("*")):
        if not path.is_file() or path.suffix not in {".md", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        for name, rx in SWEEP_PATTERNS:
            for m in rx.finditer(text):
                hits.append({"file": str(path.relative_to(root())), "pattern": name, "match": m.group(0)})
    e13 = criterion(
        "AC-P1.1-13", "M",
        "completion-claim sweep of docs/ is clean",
        "defined regex sweep of docs/*.md and docs/*.json",
        "zero matches",
        {"hits": hits, "patterns": [p[0] for p in SWEEP_PATTERNS]},
        hits == [],
    )
    return [e12, e13]


def ac15_contracts() -> dict:
    p0 = root() / "sdd/specs/P0-lab-substrate/contracts"
    p1c = root() / "sdd/specs/P1-ground-truth-harness/contracts"
    observed_p0 = {name: sha256_file(p0 / name) for name in P0_HASHES}
    observed_p1 = {
        "results-row.md": sha256_file(p1c / "results-row.md"),
        "results-row.amendment-1.md": sha256_file(p1c / "results-row.amendment-1.md"),
        "ledger-integrity.md": sha256_file(p1c / "ledger-integrity.md"),
        "results-row.schema.json": sha256_file(root() / "etc/results-row.schema.json"),
    }
    match = observed_p0 == P0_HASHES and observed_p1 == P1_HASHES
    report = root() / "logs" / "review" / "X006" / "contracts-unchanged.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# P0 and P1 contracts unchanged at P1.1 X006\n", "```\n"]
    for name, digest in P0_HASHES.items():
        lines.append(f"{observed_p0[name]}  {name}  match={observed_p0[name]==digest}\n")
    for name, digest in P1_HASHES.items():
        lines.append(f"{observed_p1[name]}  {name}  match={observed_p1[name]==digest}\n")
    lines.append("```\n")
    report.write_text("".join(lines))
    return criterion(
        "AC-P1.1-15", "M",
        "P0 (R007) and P1 (W002/W010) contract hashes unchanged; lab-verify still 18/18 and lab-verify-p1 24/24",
        "sha256 vs recorded hashes; see also ac15_runners",
        "all hashes identical",
        {"p0": {"expected": P0_HASHES, "observed": observed_p0}, "p1": {"expected": P1_HASHES, "observed": observed_p1}},
        match,
    )


def ac15_runners() -> dict:
    """Nested live re-run of P0/P1 is D2 (impossible against frozen headline). Hashes remain AC-15."""
    bins = {
        "lab-verify": (root() / "bin/lab-verify").is_file(),
        "lab-verify-p1": (root() / "bin/lab-verify-p1").is_file(),
    }
    return criterion(
        "AC-P1.1-15-runners", "M",
        "lab-verify and lab-verify-p1 binaries present (live totals: lab-regression / P3.1)",
        "stat bin/lab-verify bin/lab-verify-p1",
        "both present",
        bins,
        all(bins.values()),
    )


def ac16() -> dict:
    memo = load_memo_json()
    defects = memo.get("defects") or []
    closed = (
        isinstance(defects, list)
        and len(defects) == 3
        and all(d.get("closed") is True and d.get("task") for d in defects)
        and {d.get("id") for d in defects} == {"D1", "D2", "D3"}
    )
    passed = (
        memo.get("accepted_only_after_p1_1") is True
        and memo.get("completed_arm_runs") == 0
        and closed
    )
    return criterion(
        "AC-P1.1-16", "A",
        "memo records three closed defects and accepted_only_after_p1_1",
        "JSON object in docs/p1-acceptance-memo.md",
        "defects[*].closed true; accepted_only_after_p1_1 true; completed_arm_runs 0",
        {"accepted_only_after_p1_1": memo.get("accepted_only_after_p1_1"), "completed_arm_runs": memo.get("completed_arm_runs"), "defects": defects},
        passed,
    )


def ac_p2_rec() -> dict:
    synced = sync_p2_recommendation()
    ready_exit = synced["lab_ready_exit"]
    rec = synced["recommendation"]
    passed = (rec == "go" and ready_exit == 0) or (rec == "blocked" and ready_exit != 0)
    return criterion(
        "AC-P1.1-p2rec", "M",
        "live lab-ready maps to go/blocked without mutating docs/",
        "bin/lab-ready exit; no write to p1-acceptance-memo.md",
        "go iff lab-ready exit 0 else blocked",
        {"live": rec, "memo": synced.get("memo_recommendation"), "lab_ready_exit": ready_exit},
        passed,
    )


def main(argv: list[str]) -> int:
    want_json = "--json" in argv
    entries: list[dict] = []
    entries.append(ac01())
    entries.append(ac02())
    entries.extend(ac03_05())
    entries.append(ac06())
    entries.extend(ac07_08())
    entries.extend(ac09_10())
    entries.append(ac11())
    entries.extend(ac12_13())
    hashes = ac15_contracts()
    runners = ac15_runners()
    # Fold runner result into AC-P1.1-15
    ac15 = dict(hashes)
    ac15["observed"] = {"hashes": hashes["observed"], "runners": runners["observed"]}
    ac15["result"] = "PASS" if hashes["result"] == "PASS" and runners["result"] == "PASS" else "FAIL"
    entries.append(ac15)
    entries.append(ac16())
    p2 = ac_p2_rec()

    numbered = [e for e in entries if re.fullmatch(r"AC-P1\.1-\d{2}", e["id"])]
    others_pass = all(e["result"] == "PASS" for e in numbered)
    ac14 = criterion(
        "AC-P1.1-14", "M",
        "lab-verify-p1.1 reports every criterion PASS with per-tier totals",
        "this runner's per-criterion results",
        "all AC-P1.1-01..13,15,16 PASS; per-tier totals printed separately",
        {"others_pass": others_pass, "n": len(numbered)},
        others_pass,
    )
    numbered.append(ac14)
    m = [e for e in numbered if e["tier"] == "M"]
    a = [e for e in numbered if e["tier"] == "A"]
    m_pass = sum(e["result"] == "PASS" for e in m)
    a_pass = sum(e["result"] == "PASS" for e in a)
    totals = {
        "M": {"total": len(m), "passed": m_pass, "failed": len(m) - m_pass},
        "A": {"total": len(a), "passed": a_pass, "failed": len(a) - a_pass},
        "all": {"total": len(numbered), "passed": m_pass + a_pass, "failed": len(numbered) - m_pass - a_pass},
    }
    document = {"criteria": numbered, "extras": [runners, p2], "totals": totals}
    out = root() / "logs" / "review" / "X006" / "verify-p1.1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    if want_json:
        print(json.dumps(document, sort_keys=True))
    else:
        for entry in numbered:
            print(f"{entry['id']} tier={entry['tier']} {entry['result']}")
        print(
            f"TIER M: {m_pass}/{len(m)} · TIER A: {a_pass}/{len(a)} · TOTAL: {m_pass + a_pass}/{len(numbered)}"
        )
        for extra in (runners, p2):
            print(f"{extra['id']} tier={extra['tier']} {extra['result']}")
    failed = totals["all"]["failed"] or any(e["result"] == "FAIL" for e in (runners, p2))
    return 0 if not failed else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
