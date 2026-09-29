"""Machine-checkable scenario-definition validator (P7 / AC-P7-05)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die
from lab_paths import lab_root

SCENARIO_ID_RE = re.compile(r"^SC-0\d$")
DAMAGE_CLASS = {"filesystem_data", "database_data", "database_schema", "mixed"}
TIMING = {"near_instant", "slow", "randomized"}
GT_KIND = {"single_coordinate", "set_and_earliest"}


def _req(obj: dict, key: str, path: str, errors: list[str]) -> object:
    if key not in obj:
        errors.append(f"{path}.{key}: missing required field")
        return None
    return obj[key]


def validate_definition(doc: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["definition is not a JSON object"]
    sid = _req(doc, "scenario_id", "", errors)
    if isinstance(sid, str) and not SCENARIO_ID_RE.fullmatch(sid):
        errors.append(f"scenario_id {sid!r} does not match SC-0\\d")
    dc = _req(doc, "damage_class", "", errors)
    if dc is not None and dc not in DAMAGE_CLASS:
        errors.append(f"damage_class {dc!r} not in {sorted(DAMAGE_CLASS)}")
    tp = _req(doc, "timing_pattern", "", errors)
    if tp is not None and tp not in TIMING:
        errors.append(f"timing_pattern {tp!r} not in {sorted(TIMING)}")
    arch = _req(doc, "archetype", "", errors)
    if arch is not None and (not isinstance(arch, str) or not arch.strip()):
        errors.append("archetype must be a non-empty string")
    cites = _req(doc, "corpus_citation", "", errors)
    if cites is not None:
        if not isinstance(cites, list) or not cites or any(not isinstance(c, str) or not c.strip() for c in cites):
            errors.append("corpus_citation must be a non-empty array of strings")
    inj = _req(doc, "injection", "", errors)
    if isinstance(inj, dict):
        prin = inj.get("principal")
        if not isinstance(prin, str) or not prin.strip():
            errors.append("injection.principal must be a non-empty string")
        href = inj.get("script_ref")
        if not isinstance(href, str) or not href.strip():
            errors.append("injection.script_ref must be a path string")
    elif inj is not None:
        errors.append("injection must be an object")
    conf = _req(doc, "confounder", "", errors)
    if isinstance(conf, dict):
        cprin = conf.get("principal")
        if not isinstance(cprin, str) or not cprin.strip():
            errors.append("confounder.principal must be a non-empty string")
        sref = conf.get("spec_ref")
        if not isinstance(sref, str) or not sref.strip():
            errors.append("confounder.spec_ref must be a path string")
        overlaps = conf.get("overlaps_damage")
        if overlaps is not True:
            errors.append(
                "confounder.overlaps_damage must be true; a scenario without overlapping "
                "legitimate activity is refused (AC-P7-05)"
            )
        inj_prin = (inj or {}).get("principal") if isinstance(inj, dict) else None
        if isinstance(cprin, str) and isinstance(inj_prin, str) and cprin == inj_prin:
            errors.append("confounder.principal must be distinct from injection.principal")
    elif conf is not None:
        errors.append("confounder must be an object")
    gt = _req(doc, "ground_truth", "", errors)
    if isinstance(gt, dict):
        kind = gt.get("kind")
        if kind not in GT_KIND:
            errors.append(f"ground_truth.kind {kind!r} not in {sorted(GT_KIND)}")
        if not isinstance(gt.get("definition"), str) or not gt.get("definition", "").strip():
            errors.append("ground_truth.definition must be a non-empty string")
        if not isinstance(gt.get("computed_from"), str) or not gt.get("computed_from", "").strip():
            errors.append("ground_truth.computed_from must be a non-empty string")
    elif gt is not None:
        errors.append("ground_truth must be an object")
    sig = _req(doc, "evidence_signature", "", errors)
    if sig is not None and not isinstance(sig, dict):
        errors.append("evidence_signature must be an object")
    metrics = _req(doc, "metrics", "", errors)
    if metrics is not None:
        if not isinstance(metrics, list) or not metrics or any(not isinstance(m, str) or not m.strip() for m in metrics):
            errors.append("metrics must be a non-empty array of strings")
    return errors


def load_definition(path: Path) -> dict:
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: scenario definition missing {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(EXIT_ASSERT, f"assertion failed: {path} is not JSON: {exc}")
    errors = validate_definition(doc)
    if errors:
        die(EXIT_ASSERT, "assertion failed: scenario definition refused: " + "; ".join(errors))
    return doc


def parse_contract_examples(markdown: str) -> list[dict]:
    blocks = []
    for m in re.finditer(r"```json\s*\n(.*?)```", markdown, re.S):
        blocks.append(json.loads(m.group(1)))
    return blocks


def main(argv: list[str]) -> int:
    if not argv:
        die(EXIT_USAGE, "usage: lab-scenario-validate <definition.json> | --stdin")
    if argv == ["--stdin"]:
        import sys
        doc = json.loads(sys.stdin.read())
        errors = validate_definition(doc)
        if errors:
            print(json.dumps({"ok": False, "errors": errors}, sort_keys=True))
            return EXIT_ASSERT
        print(json.dumps({"ok": True, "errors": []}, sort_keys=True))
        return 0
    path = Path(argv[0])
    if not path.is_file():
        path = lab_root() / argv[0]
    doc = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_definition(doc)
    payload = {"ok": not errors, "path": str(path), "errors": errors}
    print(json.dumps(payload, sort_keys=True))
    return 0 if not errors else EXIT_ASSERT


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
