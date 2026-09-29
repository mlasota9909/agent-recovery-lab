"""lab-p10-explore — EXPLORATORY (not pre-registered; Article XXI.2), Article XVIII follow-up.

The frozen P6.1 extractor accepts a multi-locator COORDINATE line only if every locator
resolves, through the live heartbeat lookup, to the same LSN. A timestamp resolves at
heartbeat granularity, so an `lsn=X ts=T` pair that names ONE event is rejected as
"locators resolve inconsistently" (refusal_parser). That is an instrument property.

Corrected rule, applied only here: a parser-rejected answer is *evidence-consistent* iff
its locators are exactly one `lsn` and one `ts` that match the same event line (its
`lsn_text`/`lsn_int` and `wall_clock`) in the prompt the model was shown. Such an answer is
re-scored at that LSN through the same scoring path as the sweep (P4 on real rows + P4's
rule on padded manifest rows). Results go to results/scaling-runs-exploratory.jsonl, keyed
by scale_run_id. They never alter scaling-runs.jsonl or the pre-registered branch.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from lab_p10 import INCIDENT, root, scaled_root, scaling_detail_path, scaling_runs_path, utc
from lsn import lsn_int, lsn_norm

RULE = ("evidence-consistent COORDINATE line: every lsn locator (hex or integer form) equals one presented "
        "R0 event's LSN and every ts locator equals that event's wall_clock (exploratory, defined post hoc)")


def exploratory_path() -> Path:
    return root() / "results" / "scaling-runs-exploratory.jsonl"


def _iso(ts: str) -> str:
    return ts.replace("+00:00", "Z")


def consistent_lsn(completion: str, prompt: str) -> tuple[int | None, str]:
    """All locators on the single COORDINATE line identify one presented R0 event. Covers the
    shapes the strict P6.1 grammar rejects: lsn+ts pairs and the same LSN written in both hex
    and integer form (+ ts). Window locators are out of scope (not an event locator)."""
    import re
    from lab_arm_b_extract import LSN_HEX_RE, LSN_INT_RE, TS_RE, tagged_lines
    from lsn import lsn_int
    coords, refusals = tagged_lines(completion or "")
    if len(coords) != 1 or refusals:
        return None, "not exactly one COORDINATE line"
    line = coords[0][1]
    if re.search(r"window=", line):
        return None, "window locator present"
    lsns = {lsn_int(h) for h in LSN_HEX_RE.findall(line)} | {int(x) for x in LSN_INT_RE.findall(line)}
    tss = {_iso(t) for t in TS_RE.findall(line)}
    if len(lsns) != 1 or len(tss) > 1:
        return None, "locators do not name a single LSN and at most one timestamp"
    target = next(iter(lsns))
    content = prompt.split("<<<ARM_B_CONTENT", 1)[1].split("ARM_B_CONTENT>>>", 1)[0]
    for ln in content.splitlines():
        if not ln.startswith("{"):
            continue
        ev = json.loads(ln)
        if int(ev.get("lsn_int", -1)) == target and (not tss or _iso(ev.get("wall_clock", "")) in tss):
            return target, "all locators name the same presented event"
    return None, "locators do not name one presented event"


def run() -> dict:
    import lab_p10_sweep as S
    from lab_arm_b_extract import resolve_lsn
    S.REAL_EVIDENCE_ROOT = os.environ["EVIDENCE_ROOT"]
    rows = {}
    for line in scaling_runs_path().read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["scale_run_id"]] = r
    det = {}
    for line in scaling_detail_path().read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            det[d["scale_run_id"]] = d
    done = set()
    if exploratory_path().is_file():
        done = {json.loads(x)["scale_run_id"] for x in exploratory_path().read_text().splitlines() if x.strip()}
    optimum = lsn_int("1/E1000000")
    n = 0
    for sid, r in sorted(rows.items()):
        if r["outcome"] != "refusal_parser" or sid in done:
            continue
        d = det.get(sid, {})
        prompt = (scaled_root(int(r["scale_target"])) / "prompts" / f"{r['representation']}.prompt").read_text()
        lsn, why = consistent_lsn(d.get("raw_completion") or "", prompt)
        rec = {"scale_run_id": sid, "rule": RULE, "evidence_consistent": lsn is not None, "why": why,
               "corrected_lsn_int": lsn, "verdict": None, "row_utc": utc()}
        if lsn is not None:
            c = resolve_lsn(f"{lsn >> 32:X}/{lsn & 0xFFFFFFFF:X}")
            arm = {"lsn_int": int(c["lsn_int"]), "lsn_text": c["lsn_text"], "wall_clock": c["wall_clock"],
                   "snapshot": c["snapshot"],
                   "selection_inputs": {"read_injection_log": False, "read_oracle_optimum": False,
                                        "read_provenance": False}}
            p4 = S.p4_score_real(arm)
            pad = S.padded_rows_lost(int(r["scale_target"]), int(c["lsn_int"]), optimum)
            verdict = p4["restore_verdict"]
            if verdict == "correct" and pad > 0:
                verdict = "incorrect_safe"
            rec.update({"verdict": verdict, "damage_rows_retained": int(p4["damage_rows_retained"]),
                        "legit_rows_lost": int(p4["legit_rows_lost"]) + pad,
                        "p4_restore_verdict": p4["restore_verdict"], "padded_legit_rows_lost": pad})
        with exploratory_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
        n += 1
    return {"new_records": n}


def main(argv: list[str]) -> int:
    print(json.dumps(run(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
