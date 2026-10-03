"""Check the kept records of the experiment against their freezes: every frozen file, every planned study row and every
restore report the rows, comparators and controls name. Needs no VM, no model and no network.

usage: python3 records/experiment/verify.py
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHECKOUT = re.compile(r"^.*?/agent-recovery-lab[^/]*/")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locator(study, incident, scenario):
    moved = {f"logs/run/{incident}/": study / "run" / incident, f"evidence/{scenario}/": study / "evidence",
             f"var/restore/{incident}/": study / "checks" / incident, "runtime/p9-model-set.json": HERE / "model-set.json"}

    def locate(path):
        path = CHECKOUT.sub("", path)
        for prefix, target in moved.items():
            if path == prefix:
                return target
            if prefix.endswith("/") and path.startswith(prefix):
                return target / path[len(prefix):]
        return ROOT / path
    return locate


def verify(name, results_name):
    study = HERE / name
    frozen = json.loads((study / "frozen-hashes.json").read_text())
    incident = frozen["incident_id"]
    locate = locator(study, incident, name)
    entries = [(k, v["path"], v["sha256"]) if isinstance(v, dict) else (k, k, v) for k, v in sorted(frozen["files"].items())]
    bad = 0
    for key, path, digest in entries:
        target = locate(path)
        ok = target.is_file() and sha(target) == digest
        bad += not ok
        if not ok:
            print(f"FAIL {name} {key}")
    rows = [json.loads(l) for l in (study / "results" / results_name.format(incident=incident)).read_text().splitlines() if l]
    comps = [json.loads(l) for p in (study / "results").glob("*comparators*.jsonl") for l in p.read_text().splitlines() if l]
    checks = [r["check"] for r in rows + comps if isinstance(r.get("check"), dict)]
    gate = next(iter((study / "run" / incident).rglob("gate.json")), None)
    if gate is not None:
        checks += [c for c in json.loads(gate.read_text()).get("controls") or [] if isinstance(c, dict)]
    named = [c for c in checks if c.get("report") and c.get("report_sha256")]
    reports = sum(1 for c in named if locate(c["report"]).is_file() and sha(locate(c["report"])) == c["report_sha256"])
    ok = not bad and len(rows) == frozen["planned_units"] and reports == len(named)
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {len(entries) - bad} of {len(entries)} frozen files, {len(rows)} of "
          f"{frozen['planned_units']} study rows, {reports} of {len(named)} restore reports; incident {incident}")
    return ok


results = [verify("SC-02", "fl-study-runs.jsonl"), verify("SC-01", "sc01-replication-{incident}.jsonl"),
           verify("SC-03", "sc03-study-{incident}.jsonl"), verify("SC-04", "sc04-study-{incident}.jsonl")]
sys.exit(0 if all(results) else 1)
