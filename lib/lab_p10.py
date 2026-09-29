"""P10 token-scaling: shared constants, frozen-contract checks, prior-evidence manifest.

Read-only on every prior artefact (Article XVI). The only P10 writers are the scale
generator (incidents/scaled/), the sweep (results/scaling-runs*.jsonl), the analysis
(thesis/analysis/p10-*), and review bundles (logs/review/Q00N/).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from lab_redaction import manifest_entry  # ADR-M002

TRANCHE = "P10"
SPEC_DIR = Path("sdd") / "specs" / "P10-token-scaling"
CONTRACT_FILES = (
    "scale-generator.md",
    "scale-generator.amendment-1.md",
    "scaling-analysis-plan.md",
    "scaling-analysis-plan.amendment-1.md",
)
ANALYSIS_PLAN_FILES = ("scaling-analysis-plan.md", "scaling-analysis-plan.amendment-1.md")

SCENARIO = "SC-01"
INCIDENT = "SC-01_20260824T091611Z"
SEED = 42
SCALE_TARGETS = (10_000, 50_000, 100_000, 200_000, 250_000, 500_000, 1_000_000)
ANCHOR_TARGET = 10_000
PRIMARY_REPS = ("R0", "R2")
DEFAULT_K = 5
TARGET_TOLERANCE = 0.02
P9_SWEEP_SHA256 = "7b9a33aaa4cb3f3b089ff549fedc3ded6dd8feb0b69f7a5743197a75b98cd391"

# Frozen P9 decoding budget (ADR-P9-3); a request must fit prompt + completion budget.
MAX_TOKENS = 8192

# ADR-P10-8: each model's served window, pinned in the P9 registry identity
# (Gemma/Qwen backend_identity.max_model_len) or the P6.1 runtime pin (DeepSeek).
CONTEXT_WINDOWS = {
    "gb10a-deepseek-v4-flash": 262_144,
    "gympc-gemma4-26b": 100_352,
    "alienware-qwen38-27b": 196_608,
}
MODEL_SHORT = {
    "gb10a-deepseek-v4-flash": "deepseek",
    "gympc-gemma4-26b": "gemma",
    "alienware-qwen38-27b": "qwen",
}


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parent.parent)


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def contracts_dir() -> Path:
    return root() / SPEC_DIR / "contracts"


def frozen_hashes_path() -> Path:
    return contracts_dir() / "frozen-hashes.json"


def contract_digests(names=CONTRACT_FILES) -> dict[str, str]:
    return {n: sha256_file(contracts_dir() / n) for n in names}


def frozen_hashes_ok() -> dict:
    pinned = json.loads(frozen_hashes_path().read_text(encoding="utf-8"))["contracts"]
    live = contract_digests(tuple(pinned))
    rows = {n: {"pinned": pinned[n], "live": live[n], "match": pinned[n] == live[n]} for n in pinned}
    return {"ok": all(r["match"] for r in rows.values()), "contracts": rows}


def analysis_plan_digest() -> str:
    """Single digest over the analysis plan and its amendment, in fixed order."""
    parts = [f"{n}:{sha256_file(contracts_dir() / n)}" for n in ANALYSIS_PLAN_FILES]
    return sha256_text("\n".join(parts) + "\n")


def scaling_runs_path() -> Path:
    return root() / "results" / "scaling-runs.jsonl"


def scaling_detail_path() -> Path:
    return root() / "results" / "scaling-runs-detail.jsonl"


def scaled_root(target: int) -> Path:
    return root() / "incidents" / "scaled" / f"sc01-s{target}"


# --- prior-evidence manifest (Article XVI / AC-P10-12) -----------------------------

# strict: no file may be added, modified, re-moded or deleted.
# append_only: baseline files must be unchanged; new files allowed (P4 restore cache).
STRICT_ROOTS = (
    "evidence",
    "var/repr",
    "thesis/analysis",
    "thesis/related-work",
    "results/fixtures",
)
STRICT_FILES_GLOBS = (
    "results/SC-01.jsonl", "results/SC-02.jsonl", "results/SC-03.jsonl", "results/SC-04.jsonl",
    "results/matrix.jsonl", "results/superseded_manifest.json", "results/sweep-runs.jsonl",
    "runtime/p9-model-set.json", "runtime/p9-model-verify.json", "runtime/p9-readonly-baseline.json",
    "runtime/p9-throughput.json",
)
APPEND_ONLY_ROOTS = ("var/restore",)
# P10's own designated outputs inside a strict root (WI-Q005). Any other addition is a violation.
P10_ALLOWED_STRICT_ADDITIONS = frozenset({"thesis/analysis/p10-scaling.md", "thesis/analysis/p10-scaling.json"})


def _entry(path: Path) -> str:
    st = path.stat()
    return f"{sha256_file(path)} mode={st.st_mode & 0o777:04o} size={st.st_size}"


def _tree(rel_root: str) -> dict[str, str]:
    base = root() / rel_root
    out: dict[str, str] = {}
    if not base.is_dir():
        return out
    for p in sorted(base.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out[p.relative_to(root()).as_posix()] = _entry(p)
    return out


def prior_manifest() -> dict:
    strict: dict[str, str] = {}
    for r in STRICT_ROOTS:
        strict.update(_tree(r))
    for f in STRICT_FILES_GLOBS:
        p = root() / f
        if p.is_file():
            strict[f] = _entry(p)
    for spec in sorted((root() / "sdd" / "specs").glob("P[0-9]*")):
        if spec.name.startswith("P10"):
            continue
        strict.update(_tree((spec / "contracts").relative_to(root()).as_posix()))
    append_only: dict[str, str] = {}
    for r in APPEND_ONLY_ROOTS:
        append_only.update(_tree(r))
    strict_digest = sha256_text("\n".join(f"{k} {v}" for k, v in sorted(strict.items())) + "\n")
    return {
        "captured_utc": utc(),
        "strict": strict,
        "append_only": append_only,
        "strict_count": len(strict),
        "append_only_count": len(append_only),
        "strict_digest": strict_digest,
        "p9_sweep_sha256": sha256_file(root() / "results" / "sweep-runs.jsonl"),
    }


def compare_manifest(before: dict, after: dict) -> dict:
    # ADR-M002: a recorded entry for a redacted file is read as its redacted entry.
    strict = {k: manifest_entry(k, v) for k, v in before["strict"].items()}
    if strict != before["strict"]:
        before = dict(before, strict=strict,
                      strict_digest=sha256_text("\n".join(f"{k} {v}" for k, v in sorted(strict.items())) + "\n"))
    changed = sorted(k for k in before["strict"] if k in after["strict"] and after["strict"][k] != before["strict"][k])
    deleted = sorted(k for k in before["strict"] if k not in after["strict"])
    added_all = sorted(k for k in after["strict"] if k not in before["strict"])
    added = [k for k in added_all if k not in P10_ALLOWED_STRICT_ADDITIONS]
    ao_changed = sorted(k for k in before["append_only"]
                        if k in after["append_only"] and after["append_only"][k] != before["append_only"][k])
    ao_deleted = sorted(k for k in before["append_only"] if k not in after["append_only"])
    ao_added = sorted(k for k in after["append_only"] if k not in before["append_only"])
    sweep_ok = after["p9_sweep_sha256"] == before["p9_sweep_sha256"] == P9_SWEEP_SHA256
    ok = not (changed or deleted or added or ao_changed or ao_deleted) and sweep_ok
    return {
        "ok": ok,
        "strict_digest_before": before["strict_digest"],
        "strict_digest_after": after["strict_digest"],
        "strict_identical": before["strict_digest"] == after["strict_digest"],
        "prior_files_byte_identical": not changed and not deleted,
        "strict_changed": changed, "strict_deleted": deleted, "strict_added": added,
        "p10_designated_additions": [k for k in added_all if k in P10_ALLOWED_STRICT_ADDITIONS],
        "append_only_changed": ao_changed, "append_only_deleted": ao_deleted,
        "append_only_added_count": len(ao_added),
        "p9_sweep_sha256": after["p9_sweep_sha256"], "p9_sweep_unchanged": sweep_ok,
    }


def baseline_path() -> Path:
    return root() / "logs" / "review" / "Q001" / "prior-evidence-manifest.json"


# --- Article XXI pre-registration anchor --------------------------------------------

def preregistration_path() -> Path:
    return root() / "logs" / "review" / "Q001" / "preregistration.json"


def _parse_utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def prereg_check(results_dir: Path | None = None) -> dict:
    """Plan digest unchanged AND pre-registration earlier than every scaling-runs* file
    (by file mtime and by each row's own recorded time)."""
    results_dir = results_dir or (root() / "results")
    out: dict = {"results_dir": str(results_dir)}
    p = preregistration_path()
    if not p.is_file():
        return {**out, "ok": False, "reason": f"{p} missing: plan not pre-registered"}
    pre = json.loads(p.read_text(encoding="utf-8"))
    pinned = json.loads(frozen_hashes_path().read_text(encoding="utf-8"))
    live = analysis_plan_digest()
    out["plan_digest_live"] = live
    out["plan_digest_preregistered"] = pre["analysis_plan_digest"]
    out["plan_digest_pinned"] = pinned.get("analysis_plan_digest")
    out["plan_digest_ok"] = live == pre["analysis_plan_digest"] == pinned.get("analysis_plan_digest")
    t_pre = _parse_utc(pre["preregistered_utc"])
    out["preregistered_utc"] = pre["preregistered_utc"]
    files = sorted(results_dir.glob("scaling-runs*"))
    violations = []
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if mtime <= t_pre:
            violations.append({"file": f.name, "why": "mtime not after pre-registration",
                               "mtime_utc": mtime.strftime("%Y-%m-%dT%H:%M:%S.%fZ")})
    # fail closed: every C5 row must join a detail record carrying row_utc > pre-registration
    main_f, det_f = results_dir / "scaling-runs.jsonl", results_dir / "scaling-runs-detail.jsonl"
    if main_f.is_file():
        det_ts: dict[str, list[str]] = {}
        if det_f.is_file():
            for line in det_f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = json.loads(line)
                    det_ts.setdefault(d.get("scale_run_id"), []).append(d.get("row_utc"))
        main_count: dict[str, int] = {}
        for line in main_f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                k = json.loads(line).get("scale_run_id")
                main_count[k] = main_count.get(k, 0) + 1
        for sid, n in sorted(main_count.items()):
            if len(det_ts.get(sid) or []) != n:
                violations.append({"file": main_f.name, "scale_run_id": sid,
                                   "why": f"{n} row attempt(s) but {len(det_ts.get(sid) or [])} detail record(s): "
                                          "every attempt must pair one timestamped detail (fails closed)"})
        for i, line in enumerate(main_f.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            sid = json.loads(line).get("scale_run_id")
            ts_list = det_ts.get(sid) or []
            if not ts_list or any(not t for t in ts_list):
                violations.append({"file": main_f.name, "line": i + 1, "scale_run_id": sid,
                                   "why": "row has no timestamped detail record (fails closed)"})
                continue
            first = min(ts_list)
            if _parse_utc(first) <= t_pre:
                violations.append({"file": main_f.name, "line": i + 1, "scale_run_id": sid,
                                   "why": "row time not after pre-registration", "row_utc": first})
    out["scaling_files"] = [f.name for f in files]
    out["frozen_before_data"] = not violations
    out["violations"] = violations
    out["ok"] = out["plan_digest_ok"] and out["frozen_before_data"]
    return out
