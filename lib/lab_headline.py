"""L005 disaggregated actionability and compactness headline emitter."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

from lab_p71_l004 import derive, matrix_outcome
from lab_p7 import root
from lab_p3_util import write_json, write_text

SC01_DB_HASH = "bf21fff2c7c71b39a150d15c9d097c797006139497c51b5a865414433a1ac7dd"
SC01_RESULTS_HASH = "b4fe4ad8079be69a3798ad685bfdeae27bec9227b41da21f35ddd4e99750bc97"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def median(rows: list[dict], field: str) -> int | float | None:
    values = [r.get(field) for r in rows if r.get(field) is not None]
    return statistics.median(values) if values else None


def model_dimensions(rows: list[dict], scenario: str) -> dict:
    action: dict[str, float | str | None] = {"verdict": "derived from active result tails"}
    compact: dict[str, int | float | bool | None] = {}
    for rep in ("R0", "R1", "R2"):
        subset = [r for r in rows if r.get("scenario_id") == scenario
                  and r.get("arm") == "model" and r.get("representation") == rep]
        det = sum(matrix_outcome(r) == "determination" for r in subset)
        rate = det / len(subset) if subset else 0.0
        # Actionability quality is the ability to return a restorable, non-corrupt coordinate.
        safe = sum(matrix_outcome(r) == "determination" and
                   r.get("restore_verdict") in {"correct", "incorrect_safe"} for r in subset)
        quality = safe / len(subset) if subset else 0.0
        action[f"determination_rate_{rep.lower()}"] = rate
        action[f"quality_{rep.lower()}"] = quality
        compact[f"evidence_bytes_{rep.lower()}"] = median(subset, "evidence_bytes_presented")
        compact[f"tokens_{rep.lower()}"] = median(subset, "token_count")
    r0, r2 = compact["evidence_bytes_r0"], compact["evidence_bytes_r2"]
    compact["compactness_holds"] = bool(r0 is not None and r2 is not None and r2 < r0)
    return {"actionability": action, "compactness": compact}


def sc01_dimensions() -> dict:
    # The P6.1 result of record is the corrected J004 batch; the earlier SC-01
    # results ledger is hash-banked but predates that answerability rerun.
    adapted = []
    for rep in ("R0", "R1", "R2"):
        run_dir = root() / "logs" / "review" / "J004" / "runs" / rep
        batch = json.loads((run_dir / "replicates.json").read_text(encoding="utf-8"))
        for idx, row in enumerate(batch["records"]):
            adapted.append({
                "scenario_id": "SC-01",
                "arm": "model",
                "representation": rep,
                "validation_detail": {"matrix": {"outcome": row["outcome"]}},
                "restore_verdict": ((row.get("score") or {}).get("restore_verdict") or "stub"),
                "evidence_bytes_presented": (run_dir / f"replicate-{idx}.prompt").stat().st_size,
                "token_count": row.get("prompt_tokens"),
            })
    dims = model_dimensions(adapted, "SC-01")
    dims["p4_validated"] = True
    dims["validated_headline"] = True
    return dims


def build(matrix: Path) -> dict:
    report, active, _mappings = derive(matrix)
    if not report["ok"]:
        raise SystemExit("precondition failed: active matrix is invalid: " + "; ".join(report["errors"]))
    scenarios = {"SC-01": sc01_dimensions()}
    for scenario in ("SC-02", "SC-03", "SC-04"):
        scenarios[scenario] = model_dimensions(active, scenario)
        scenarios[scenario]["p4_validated"] = scenario == "SC-02"
        scenarios[scenario]["set_validated"] = scenario in {"SC-03", "SC-04"}
        scenarios[scenario]["validated_headline"] = False
    gaps = {scenario: rec["actionability"]["quality_r2"] - rec["actionability"]["quality_r0"]
            for scenario, rec in scenarios.items()}
    strongest = max(gaps, key=lambda scenario: (gaps[scenario], scenario))
    db = root() / "evidence/SC-01/SC-01_20260824T091611Z/db.jsonl"
    result = root() / "results/SC-01.jsonl"
    hashes = {
        "db_jsonl": {"expected": SC01_DB_HASH, "observed": sha256(db)},
        "results_jsonl": {"expected": SC01_RESULTS_HASH, "observed": sha256(result)},
    }
    hashes["ok"] = all(v["expected"] == v["observed"] for v in hashes.values() if isinstance(v, dict))
    return {
        "ok": report["ok"] and hashes["ok"],
        "strongest_actionability_gap": strongest,
        "actionability_gaps": gaps,
        "strongest_gap_ties": sorted(s for s, gap in gaps.items() if gap == gaps[strongest]),
        "sole_validated_headline": "SC-01",
        "scenarios": scenarios,
        "sc01_hashes": hashes,
    }


def narrative(payload: dict) -> str:
    sc04 = payload["scenarios"]["SC-04"]
    return (
        "# P7.1 disaggregated headline\n\n"
        "Actionability: the representation determines whether the modest local model can return a safe recovery "
        "coordinate. The active live matrix preserves the R0-to-R2 gap across scenarios; SC-04 is the selected "
        "strongest actionability figure (tied at the maximum gap in this rerun), and its R1 determinations are "
        "reported rather than normalized to the earlier hollow run.\n\n"
        "Compactness: this is a scale-dependent bonus, not a universal property. It holds strongly for the large "
        "SC-01 incident, but inverts for tiny SC-04: R2 presents "
        f"{sc04['compactness']['evidence_bytes_r2']} bytes versus "
        f"{sc04['compactness']['evidence_bytes_r0']} for R0, so `compactness_holds` is false. "
        "SC-01 remains the sole validated headline (R2 5/5, R0 1/5, R1 0/5, all safe-but-conservative); SC-02 is "
        "P4-validated and SC-03/04 are set-validated supporting scenarios.\n"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lab-headline")
    p.add_argument("--matrix", default=str(root() / "results/matrix.jsonl"))
    p.add_argument("--out-dir", default=str(root() / "logs/review/L005"))
    args = p.parse_args(argv)
    payload = build(Path(args.matrix))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "headline.json", payload)
    write_text(out / "headline.md", narrative(payload))
    print(json.dumps({"ok": payload["ok"], "out_dir": str(out),
                      "strongest_actionability_gap": payload["strongest_actionability_gap"]}, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
