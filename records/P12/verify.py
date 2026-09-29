"""Check every hash in the study of record's freeze against the files kept here."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
frozen = json.loads((HERE / "study/frozen-hashes.json").read_text())
moved = {"evidence/SC-02/": HERE / "study/evidence", "runtime/p9-model-set.json": HERE / "study/model-set.json"}


def locate(path):
    for prefix, target in moved.items():
        if path == prefix:
            return target
        if prefix.endswith("/") and path.startswith(prefix):
            return target / path[len(prefix):]
    return ROOT / path


bad = 0
for key, entry in sorted(frozen["files"].items()):
    path = locate(entry["path"])
    ok = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    bad += not ok
    print(("ok   " if ok else "FAIL ") + key)
rows = [json.loads(line) for line in (HERE / "study/results/fl-study-runs.jsonl").read_text().splitlines() if line]
print(f"{len(rows)} study rows; planned {frozen['planned_units']}; incident {frozen['incident_id']}")
sys.exit(1 if bad or len(rows) != frozen["planned_units"] else 0)
