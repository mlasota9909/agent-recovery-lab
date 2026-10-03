"""Check every hash in the database-level replication's freeze against the files kept here."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
frozen = json.loads((HERE / "frozen-hashes.json").read_text())
incident = frozen["incident_id"]
moved = {f"logs/run/{incident}/": HERE / "run" / incident, "evidence/SC-01/": HERE / "evidence",
         "runtime/p9-model-set.json": HERE / "model-set.json"}


def locate(path):
    for prefix, target in moved.items():
        if path == prefix:
            return target
        if prefix.endswith("/") and path.startswith(prefix):
            return target / path[len(prefix):]
    return ROOT / path


bad = 0
for path, digest in sorted(frozen["files"].items()):
    target = locate(path)
    ok = target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest
    bad += not ok
    print(("ok   " if ok else "FAIL ") + path)
rows = [json.loads(line) for line in (HERE / "results" / f"sc01-replication-{incident}.jsonl").read_text().splitlines() if line]
print(f"{len(rows)} study rows; planned {frozen['planned_units']}; incident {incident}")
sys.exit(1 if bad or len(rows) != frozen["planned_units"] else 0)
