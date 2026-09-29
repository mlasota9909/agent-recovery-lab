"""Results-row validation. No coercion. Consumed by bin/lab-results and lab-verify-p1."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

COORDINATE_ERROR_FIELDS = (
    "coord_error_bytes",
    "coord_error_ms",
    "coord_direction",
    "naive_coord_error_bytes",
    "naive_coord_error_ms",
)
OUTCOME_ERROR_FIELDS = (
    "legit_rows_lost",
    "legit_bytes_lost",
    "damage_rows_retained",
    "damage_bytes_retained",
    "fs_granularity_penalty_ms",
)
COORDINATE_FIELDS = (
    "ground_truth_coordinate",
    "chosen_coordinate",
    "naive_coordinate",
    "incident_open_coordinate",
    "incident_close_coordinate",
)


def canonical_json(obj: object) -> str:
    """Canonical JSON for byte-identity: sorted keys, no insignificant whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def load_schema(path: str | Path | None = None) -> dict:
    raw = path or os.environ.get("RESULTS_SCHEMA", "")
    if not raw:
        raise SystemExit("precondition failed: RESULTS_SCHEMA missing")
    p = Path(raw)
    if not p.is_file():
        raise SystemExit(f"precondition failed: schema {p} is absent")
    return json.loads(p.read_text(encoding="utf-8"))


def _js_type_ok(value, json_type: str) -> bool:
    if json_type == "string":
        return isinstance(value, str)
    if json_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if json_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if json_type == "boolean":
        return isinstance(value, bool)
    if json_type == "object":
        return isinstance(value, dict)
    return False


def _check_value(spec: dict, value, path: str, errors: list[str]) -> None:
    if value is None:
        if not spec.get("nullable"):
            errors.append(f"{path}: missing required field (null not allowed)")
        return
    jtype = spec["json_type"]
    if not _js_type_ok(value, jtype):
        errors.append(
            f"{path}: expected {jtype}, got {type(value).__name__} (no coercion)"
        )
        return
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{path}: {value!r} not in {spec['enum']}")
    if "minimum" in spec and isinstance(value, int) and value < spec["minimum"]:
        errors.append(f"{path}: {value} < minimum {spec['minimum']}")
    if "exclusiveMinimum" in spec and isinstance(value, (int, float)):
        if value <= spec["exclusiveMinimum"]:
            errors.append(f"{path}: {value} not > {spec['exclusiveMinimum']}")
    if "pattern" in spec and isinstance(value, str) and not re.fullmatch(spec["pattern"], value):
        errors.append(f"{path}: value does not match required pattern")
    if spec.get("coordinate"):
        if not isinstance(value, dict):
            errors.append(f"{path}: expected coordinate object")
            return
        required = spec.get("required_coordinate_fields") or []
        for cname in required:
            if cname not in value:
                errors.append(f"{path}.{cname}: missing required coordinate field")
        extra = set(value) - set(required)
        if extra:
            errors.append(f"{path}: unexpected keys {sorted(extra)}")
        cprops = spec.get("coordinate_properties") or {}
        for cname, cspec in cprops.items():
            if cname in value:
                _check_value(cspec, value[cname], f"{path}.{cname}", errors)


def type_errors(schema: dict, row: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(row, dict):
        return ["row is not a JSON object"]
    by_name = {f["name"]: f for f in schema["fields"]}
    for spec in schema["fields"]:
        name = spec["name"]
        if name not in row:
            if not spec.get("nullable"):
                errors.append(f"{name}: missing required field")
            continue
        _check_value(spec, row[name], name, errors)
    extra = set(row) - set(by_name)
    if extra:
        errors.append("unexpected fields: " + ", ".join(sorted(extra)))
    return errors


def rule_errors(row: dict) -> list[str]:
    errors: list[str] = []
    for field in COORDINATE_FIELDS:
        coord = row.get(field)
        if isinstance(coord, dict) and coord.get("resolved_by") == "live_heartbeat":
            if not isinstance(coord.get("skew_ms"), int) or coord.get("skew_ms") <= 0:
                errors.append(
                    f"amendment rule: {field} resolved_by=live_heartbeat requires skew_ms > 0"
                )
    arm = row.get("arm")
    representation = row.get("representation")
    model_id = row.get("model_id")
    if arm == "model":
        if not model_id:
            errors.append("rule 3: arm=model requires model_id")
        if representation not in {"R0", "R1", "R2"}:
            errors.append("rule 3: arm=model requires representation in R0..R2")
    if arm in {"stub", "deterministic", "naive"} and representation != "none":
        errors.append("rule 4: arm in stub|deterministic|naive requires representation=none")
    if row.get("chosen_coordinate") is None:
        for field in COORDINATE_ERROR_FIELDS + OUTCOME_ERROR_FIELDS:
            if row.get(field) is not None:
                errors.append(
                    f"rule 5: chosen_coordinate is null so {field} must be null"
                )
    if row.get("restore_verdict") == "correct":
        if row.get("damage_rows_retained") != 0 or row.get("legit_rows_lost") != 0:
            errors.append(
                "rule 6: restore_verdict=correct requires damage_rows_retained=0 "
                "and legit_rows_lost=0"
            )
    # Rule 7 is explicitly scoped to the P1 stub path. Later deterministic and
    # naive arms may carry real restore validation just like the model arm.
    if row.get("arm") == "stub":
        if row.get("restore_verdict") != "stub" or row.get("consistency_verdict") != "stub":
            errors.append(
                "rule 7: P1 requires restore_verdict=stub and consistency_verdict=stub"
            )
    return errors


def validate_row(schema: dict, row: object) -> list[str]:
    errors = type_errors(schema, row)
    if errors:
        return errors
    assert isinstance(row, dict)
    errors.extend(rule_errors(row))
    return errors


def numeric_field_names(schema: dict) -> list[str]:
    names = []
    for spec in schema["fields"]:
        if spec["json_type"] in {"integer", "number"}:
            names.append(spec["name"])
        if spec.get("coordinate"):
            for cname, cspec in spec.get("coordinate_properties", {}).items():
                if cspec.get("json_type") in {"integer", "number"}:
                    names.append(f"{spec['name']}.{cname}")
    return names
