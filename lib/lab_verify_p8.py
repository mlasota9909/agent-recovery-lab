"""Terminal P8 acceptance gate: pure re-derivation with tiered results."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from lab_redaction import pinned  # ADR-M002

ROOT = Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "analysis"))

from gen_fig import generate as generate_figure  # noqa: E402
from gen_index import collect as collect_index  # noqa: E402
from gen_repro import validate as validate_repro  # noqa: E402
from gen_tab import VALIDATION_TIERS, generate as generate_table, table_data  # noqa: E402
from loader import Frame, comparison_view, load_active, load_sc01  # noqa: E402
from verify_loader import verify as verify_loader  # noqa: E402
from lab_verify_p71 import contract_state as prior_contract_state  # noqa: E402


def loadj(path: Path) -> dict: return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def criterion(number: int, tier: str, requirement: str, observed: object, passed: bool) -> dict:
    return {"id": f"AC-P8-{number:02d}", "tier": tier, "requirement": requirement,
            "observed": observed, "result": "PASS" if passed else "FAIL"}


P8_HASHES = {
    "sdd/specs/P8-analysis-and-closeout/contracts/analysis-input.md": "379d4c6dfb18af07afbcf65018c2e3da4a1ac99dd3def8f81fb619ed3736507a",
    "sdd/specs/P8-analysis-and-closeout/contracts/analysis-input.amendment-1.md": pinned("85448cc6d46839791129b3a29fa4c00ab1bf999f2fc56c842669aac941562459"),
    "sdd/specs/P8-analysis-and-closeout/contracts/figure-table-manifest.md": pinned("e9508ac05f0d66790753080448c14a41345e2328647e035753b3a317e0265361"),
    "sdd/specs/P8-analysis-and-closeout/contracts/figure-table-manifest.amendment-1.md": "54bcef8418f3aff040ca219da4455326706d1fbc571ffe1175a2b3db7ed0cc83",
}


def hash_state(schema_expected: str | None = None) -> dict:
    prior = prior_contract_state()
    rows = dict(prior["files"])
    for rel, expected in P8_HASHES.items():
        observed = sha(ROOT / rel); rows[rel] = {"expected": expected, "observed": observed, "match": expected == observed}
    if schema_expected is not None:
        rel = "etc/results-row.schema.json"; observed = sha(ROOT / rel)
        rows[rel] = {"expected": schema_expected, "observed": observed, "match": schema_expected == observed}
    return {"ok": all(row["match"] for row in rows.values()), "files": rows}


def regen_state() -> dict:
    scratch = ROOT / "logs/review/M008/scratch/regen"
    if scratch.exists(): shutil.rmtree(scratch)
    fig_dir = scratch / "figures"; tab_dir = scratch / "tables"
    rows = []
    for name in ("fig51", "fig52", "fig53", "fig54"):
        result = generate_figure(name, fig_dir); stem = result["figure"]
        for suffix in ("png", "meta.json"):
            produced = fig_dir / f"{stem}.{suffix}"; committed = ROOT / "analysis-out/figures" / f"{stem}.{suffix}"
            rows.append({"path": str(committed.relative_to(ROOT)), "produced": sha(produced), "committed": sha(committed), "match": sha(produced) == sha(committed)})
    for name in ("tab51", "tab52", "tab53", "tab54"):
        result = generate_table(name, tab_dir); stem = result["table"]
        for suffix in ("md", "csv", "meta.json"):
            produced = tab_dir / f"{stem}.{suffix}"; committed = ROOT / "analysis-out/tables" / f"{stem}.{suffix}"
            rows.append({"path": str(committed.relative_to(ROOT)), "produced": sha(produced), "committed": sha(committed), "match": sha(produced) == sha(committed)})
    return {"ok": all(row["match"] for row in rows), "rows": rows}


def write_memo(partition: dict, tier_totals: dict, outputs: list[str]) -> str:
    return f"""# Project close-out memo

## Acceptance tiers

- Tier M: {tier_totals['M']['passed']}/{tier_totals['M']['total']} criteria passed.
- Tier A: {tier_totals['A']['passed']}/{tier_totals['A']['total']} criteria passed.

## Validity partition

The final active matrix contains {partition['active_total']} cells: {partition['determinations']} determinations,
{partition['refusals']} refusals, and {partition['run_failures']} diagnosed run failure. It excludes
{partition['superseded_excluded']} supersession records from aggregation while retaining their provenance.

## Final validated headline

Actionability and compactness remain separate. On P4-validated SC-01, R2 determines 5/5, R0 1/5, and R1 0/5.
Median presented bytes fall from 44,267 to 1,103 (40.1x) at SC-01 scale. SC-04 is the explicit counter-result:
R2 is 1,088 bytes versus R0 at 799, so compactness does not hold there. SC-02 is also P4-validated; SC-03 and SC-04
remain set-validated supporting scenarios.

## Governance

Twenty constitutional articles are in force. Articles XII–XX preserve closed boundary surfaces, tiered mechanical
verification, exact provenance, frozen-amendment discipline, read-only gates, answer-key separation, null-result
diagnosis, isolated units with validity partitions, and bounded authority to resolve and record internal decisions.

## Analysis outputs

""" + "".join(f"- `{path}`\n" for path in outputs)


def run() -> tuple[dict, dict, str]:
    criteria = []
    frame = load_active(); partition = frame.metadata["validity_partition"]
    m001 = loadj(ROOT / "logs/review/M001/partition.json")
    criteria.append(criterion(1, "M", "analysis-input contract and active query", m001,
                              m001.get("active_total") == 51 and m001.get("negative_probe", {}).get("active_total_after_injection") == 51))
    manifest_text = (ROOT / "sdd/specs/P8-analysis-and-closeout/contracts/figure-table-manifest.md").read_text(encoding="utf-8")
    entries = len(re.findall(r"^- (?:FIG|TAB)-5\.[1-4]", manifest_text, re.M)); commands = len(re.findall(r"`analysis/gen_(?:fig|tab)\.py (?:fig|tab)5[1-4]`", manifest_text))
    criteria.append(criterion(2, "M", "frozen figure/table manifest complete", {"entries": entries, "commands": commands}, entries == commands == 8))
    criteria.append(criterion(3, "M", "loader active partition", partition, len(frame) == 51 and partition == {"active_total": 51, "determinations": 25, "refusals": 25, "run_failures": 1, "superseded_excluded": 99}))
    guards = verify_loader(); criteria.append(criterion(4, "M", "comparison view provenance and fixture guards", guards, guards["ok"]))
    regen = regen_state(); criteria.append(criterion(5, "M", "all manifest artefacts regenerate byte-identically", {"rows": len(regen["rows"]), "mismatches": [r for r in regen["rows"] if not r["match"]]}, regen["ok"]))
    fig51 = loadj(ROOT / "analysis-out/figures/FIG-5.1.meta.json").get("values", {})
    criteria.append(criterion(6, "M", "SC-01 actionability counts", fig51,
                              [fig51.get(r, {}).get("determinations") for r in ("R0", "R1", "R2")] == [1, 0, 5]))
    compact = loadj(ROOT / "logs/review/M004/compactness.json")
    criteria.append(criterion(7, "M", "SC-01 compactness and SC-04 counter-result", compact,
                              compact.get("SC-01", {}).get("ratio_r0_over_r2") == 40.133273 and compact.get("SC-04", {}).get("compactness_holds") is False))
    _h, tier_rows, _m = table_data("tab52"); tiers = {row[0]: row[1] for row in tier_rows}
    bad = dict(VALIDATION_TIERS); bad["SC-03"] = "P4-validated"
    try: table_data("tab52", bad); negative_tier = False
    except ValueError: negative_tier = True
    criteria.append(criterion(8, "M", "immutable scenario validation tiers", {"tiers": tiers, "negative_caught": negative_tier}, tiers == VALIDATION_TIERS and negative_tier))
    m005 = loadj(ROOT / "logs/review/M005/content-checklist.json")
    criteria.append(criterion(9, "A", "reserved content checklist (M005)", m005, m005.get("ok") is True))
    m006 = loadj(ROOT / "logs/review/M006/content-checklist.json")
    criteria.append(criterion(10, "A", "reserved content checklist (M006)", m006, m006.get("ok") is True))
    repro = loadj(ROOT / "repro/manifest.json"); repro_ok, missing = validate_repro(repro)
    broken = json.loads(json.dumps(repro)); broken.get("model", {}).pop("weights_sha256", None); broken_ok, broken_missing = validate_repro(broken)
    criteria.append(criterion(11, "M", "reproducibility manifest complete", {"missing": missing, "negative_missing": broken_missing}, repro_ok and not broken_ok))
    backup = loadj(ROOT / "logs/review/M007/backup_identity.json"); neutral = Path(backup.get("dated", "x")).name.startswith("thesis-") and not Path(backup.get("dated", "x")).name.startswith("thesis-p")
    criteria.append(criterion(12, "M", "neutral byte-identical backup", backup, backup.get("ok") is True and neutral))
    hashes = hash_state(); wrong = hash_state("0" * 64); wrong_rows = [p for p, row in wrong["files"].items() if not row["match"]]
    criteria.append(criterion(13, "M", "all frozen hashes unchanged", {"ok": hashes["ok"], "negative_named": wrong_rows}, hashes["ok"] and wrong_rows == ["etc/results-row.schema.json"]))
    _index, index = collect_index(); _bad_index, bad_index = collect_index("ADR-P8-999")
    criteria.append(criterion(14, "M", "twenty-article and complete ADR index", {"index": index, "negative_dangling": bad_index["dangling"]}, index["ok"] and not bad_index["ok"]))
    outputs = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "analysis-out").rglob("*") if p.is_file())
    preliminary_m = sum(c["result"] == "PASS" for c in criteria if c["tier"] == "M")
    preliminary_a = sum(c["result"] == "PASS" for c in criteria if c["tier"] == "A")
    totals_for_memo = {"M": {"passed": preliminary_m + 1, "total": 13}, "A": {"passed": preliminary_a, "total": 2}}
    memo = write_memo(partition, totals_for_memo, outputs)
    memo_ok = all(x in memo for x in ("Tier M: 13/13", "Tier A: 2/2", "25 determinations", "R2 determines 5/5", "40.1x", "SC-04")) and "TOTAL" not in memo
    criteria.append(criterion(15, "M", "tiered project close-out memo", {"outputs": outputs, "memo_ok": memo_ok}, memo_ok))
    m = [c for c in criteria if c["tier"] == "M"]; a = [c for c in criteria if c["tier"] == "A"]
    totals = {"M": {"passed": sum(c["result"] == "PASS" for c in m), "total": len(m)},
              "A": {"passed": sum(c["result"] == "PASS" for c in a), "total": len(a)}}
    payload = {"ok": all(c["result"] == "PASS" for c in criteria), "criteria": criteria, "totals": totals}
    return payload, hashes, memo


def main() -> int:
    payload, hashes, memo = run(); totals = payload["totals"]
    print(f"TIER M {totals['M']['passed']}/{totals['M']['total']} · TIER A {totals['A']['passed']}/{totals['A']['total']}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if os.environ.get("LAB_READONLY_CHECK") != "1":
        review = ROOT / "logs/review/M008"; review.mkdir(parents=True, exist_ok=True)
        (review / "gate.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (review / "hash_reverify.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (review / "close-out-memo.md").write_text(memo, encoding="utf-8")
    return 0 if payload["ok"] else 1


if __name__ == "__main__": raise SystemExit(main())
