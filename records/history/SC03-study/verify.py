"""Check the SC-03 study's records: every frozen hash, the planned study rows and every check report the rows name."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
frozen = json.loads((HERE / "frozen-hashes.json").read_text())
incident = frozen["incident_id"]
moved = {f"logs/run/{incident}/": HERE / "run" / incident, "evidence/SC-03/": HERE / "evidence",
         f"var/restore/{incident}/": HERE / "checks" / incident, "runtime/p9-model-set.json": HERE / "model-set.json"}


def locate(path):
    path = path.split("/agent-recovery-lab/", 1)[-1]
    for prefix, target in moved.items():
        if path == prefix:
            return target
        if prefix.endswith("/") and path.startswith(prefix):
            return target / path[len(prefix):]
    return ROOT / path


def matches(path, digest):
    target = locate(path)
    return target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest


bad = 0
for path, digest in sorted(frozen["files"].items()):
    ok = matches(path, digest)
    bad += not ok
    print(("ok   " if ok else "FAIL ") + path)


def load(name):
    return [json.loads(line) for line in (HERE / "results" / name).read_text().splitlines() if line]


rows = load(f"sc03-study-{incident}.jsonl")
others = load(f"sc03-comparators-{incident}.jsonl")
gate = json.loads((HERE / "run" / incident / "sc03" / "gate.json").read_text())
checks = [r["check"] for r in rows + others if r.get("check")] + gate["controls"]
reports = sum(matches(c["report"], c["report_sha256"]) for c in checks)
print(f"{len(rows)} study rows; planned {frozen['planned_units']}; {reports} of {len(checks)} check reports match; "
      f"incident {incident}")
sys.exit(1 if bad or len(rows) != frozen["planned_units"] or reports != len(checks) else 0)
