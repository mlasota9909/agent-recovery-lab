"""Durable run records and verification of the file study's frozen inputs."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from lab_fl_freeze import ALIASES, CONTRACTS, DECODING, SPEC
from lab_paths import evidence_dir, lab_root

REPS = ("R0", "R1", "R2")
VERDICTS = ("correct", "extra_work_lost", "checked_damage_remains", "not_recovered")
OUTCOMES = ("accepted", "rule_rejection", "declined", "execution_failure")


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    target = path if exclusive else path.with_suffix(path.suffix + ".tmp")
    with target.open("x" if exclusive else "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    if not exclusive:
        target.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


RUN_SCOPE = re.compile(r"run|dry-run/[0-9]{8}T[0-9]{6}Z")


def run_scope():
    """The study run uses logs/run; a rehearsal uses logs/dry-run/<UTC time>."""
    scope = os.environ.get("LAB_RUN_SCOPE") or "run"
    if not RUN_SCOPE.fullmatch(scope):
        raise ValueError("LAB_RUN_SCOPE must be run or dry-run/<UTC time>")
    return scope


def logdir(incident=None):
    path = lab_root() / "logs" / run_scope()
    return path / incident if incident else path


def result_path(name):
    return Path(os.environ.get("RESULTS_ROOT") or lab_root() / "results") / name


def incident_id(value, scenario="SC-02"):
    if not re.fullmatch(r"SC-\d{2}_[A-Za-z0-9_-]+", value) or not value.startswith(scenario + "_"):
        raise ValueError(f"expected a {scenario} incident identifier")
    return value


def command(name, *args, allowed=(0,), timeout=1800, out=None):
    proc = subprocess.run([str(lab_root() / name), *map(str, args)], cwd=lab_root(),
                          capture_output=True, text=True, timeout=timeout)
    if out:
        save(out, {"argv": [name, *map(str, args)], "exit_code": proc.returncode,
                   "stdout": proc.stdout, "stderr": proc.stderr})
    if proc.returncode not in allowed:
        raise RuntimeError(f"{name} exited {proc.returncode}: {proc.stderr or proc.stdout}")
    return proc


def json_command(name, *args, **kwargs):
    return json.loads(command(name, *args, **kwargs).stdout)


def model_registry():
    path = lab_root() / "runtime/p9-model-set.json"
    override = os.environ.get("P9_MODEL_SET_JSON")
    if override and Path(override).resolve() != path.resolve():
        raise ValueError("run stages require runtime/p9-model-set.json")
    models = read(path)
    rows = models.get("models", [])
    if (models.get("template") or models.get("decoding") != DECODING or len(rows) != 3
            or {m.get("alias") for m in rows} != ALIASES
            or {m.get("slot") for m in rows} != {"M1", "M2", "M3"}):
        raise ValueError("record the three served identities before preflight; see README.md")
    if models.get("endpoint") != os.environ.get("P9_ENDPOINT"):
        raise ValueError("configured gateway differs from the recorded model set")
    for model in rows:
        slot = model["slot"]
        if (model.get("backend") != os.environ.get("P9_BACKEND_" + slot)
                or model.get("served_model") != os.environ.get("P9_SERVED_" + slot)
                or model.get("model_digest_kind") != "backend_immutable_identity"
                or not re.fullmatch(r"[0-9a-f]{64}", model.get("model_digest", ""))):
            raise ValueError(f"{slot}: site settings or served identity pin missing/inconsistent")
    return models


def freeze_path():
    return lab_root() / SPEC / "contracts/frozen-hashes.json"


def verify_freeze(incident=None):
    path = freeze_path()
    frozen = read(path)
    if incident is not None and frozen.get("incident_id") != incident:
        raise ValueError("freeze belongs to another incident")
    incident = incident_id(frozen["incident_id"])
    from lab_fs_reconcile import timestamp
    timestamp(frozen["frozen_utc"])
    expected = {f"contract:{n}": lab_root() / SPEC / "contracts" / n for n in CONTRACTS}
    expected.update({"design:spec": lab_root() / SPEC / "spec.md",
                     "design:plan": lab_root() / SPEC / "plan.md",
                     "models": lab_root() / "runtime/p9-model-set.json"})
    for rep in REPS:
        for name in ("model-view.json", "content.txt", "prompt.txt"):
            expected[f"input:{rep}/{name}"] = evidence_dir(incident) / "fl-inputs" / rep / name
    if (frozen.get("decoding") != DECODING or frozen.get("planned_units") != 45
            or set(frozen.get("files", {})) != set(expected)):
        raise ValueError("freeze has an invalid design or incomplete file list")
    for key, target in expected.items():
        pin = frozen["files"][key]
        if ((lab_root() / pin["path"]).resolve() != target.resolve()
                or pin["sha256"] != sha(target)):
            raise ValueError("frozen bytes changed: " + key)
    frozen["sha256"] = sha(path)
    return frozen


@contextmanager
def result_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def load_rows(path):
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        raise ValueError(f"partial final record in {path}; preserve it and investigate before resuming")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def indexed(rows, planned, incident, freeze_sha):
    records = {}
    for row in rows:
        key = row["unit_id"]
        if (key not in planned or key in records or row.get("incident_id") != incident
                or row.get("freeze_sha256") != freeze_sha or row.get("outcome") not in OUTCOMES):
            raise ValueError("duplicate, foreign or invalid result unit: " + key)
        records[key] = row
    return records


def append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def units(models):
    return [(f"{model['alias']}|{rep}|{k}", model, rep, k)
            for model in models for rep in REPS for k in range(5)]
