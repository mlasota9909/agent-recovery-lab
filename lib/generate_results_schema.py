#!/usr/bin/env python3
"""W002: derive etc/results-row.schema.json from the frozen results-row contract.

Not a bin/ CLI. Invoked as: python3 lib/generate_results_schema.py
Idempotent: existing correct artefacts yield {"changed": false}.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "sdd/specs/P1-ground-truth-harness/contracts/results-row.md"
LEDGER = ROOT / "sdd/specs/P1-ground-truth-harness/contracts/ledger-integrity.md"
COORDINATE = ROOT / "sdd/specs/P0-lab-substrate/contracts/coordinate.md"
SCHEMA_PATH = ROOT / "etc/results-row.schema.json"
ENV_PATH = ROOT / "etc/lab.env"
HASH_PATH = ROOT / "logs/review/W002/contract-hashes.json"

COORDINATE_FIELD_ORDER = (
    "wall_clock",
    "lsn",
    "snapshot",
    "skew_ms",
    "skew_bytes",
    "resolved_by",
)


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def parse_md_field_rows(text: str, start_marker: str, end_marker: str | None) -> list[dict[str, str]]:
    if start_marker not in text:
        die(2, f"precondition failed: marker {start_marker!r} absent")
    body = text.split(start_marker, 1)[1]
    if end_marker:
        body = body.split(end_marker, 1)[0]
    rows: list[dict[str, str]] = []
    for line in body.splitlines():
        if not line.startswith("| `"):
            continue
        m = re.match(r"^\| `([^`]+)` \| (.*) \| (yes|no) \|", line)
        if not m:
            die(1, f"assertion failed: could not parse field row: {line!r}")
        name, type_cell, nullable = m.group(1), m.group(2).strip(), m.group(3)
        rows.append({"name": name, "type": type_cell, "nullable": nullable})
    return rows


def enums_from(type_cell: str) -> list[str] | None:
    if "enum" not in type_cell:
        return None
    values = re.findall(r"`([^`]+)`", type_cell)
    if not values:
        die(1, f"assertion failed: enum type with no values: {type_cell!r}")
    return values


def json_type_of(type_cell: str, nullable: bool) -> dict:
    """Map a contract type cell to a JSON-Schema-like property dict."""
    cell = type_cell.strip()
    enums = enums_from(cell)
    spec: dict = {"nullable": nullable, "contract_type": cell}

    if "coordinate object" in cell:
        spec["json_type"] = "object"
        spec["coordinate"] = True
        return spec

    if cell.startswith("boolean"):
        spec["json_type"] = "boolean"
        return spec

    if cell.startswith("object"):
        spec["json_type"] = "object"
        return spec

    if "number" in cell:
        spec["json_type"] = "number"
        if "> 0" in cell:
            spec["exclusiveMinimum"] = 0
        return spec

    if cell.startswith("integer") or "integer" in cell.split(",")[0]:
        spec["json_type"] = "integer"
        if ">= 1" in cell:
            spec["minimum"] = 1
        elif ">= 0" in cell:
            spec["minimum"] = 0
        return spec

    if enums:
        spec["json_type"] = "string"
        spec["enum"] = enums
        return spec

    # strings, including patterned ones
    spec["json_type"] = "string"
    if "40 hex" in cell:
        spec["pattern"] = r"^[0-9a-f]{40}$"
    elif "SC-0[1-4]" in cell:
        spec["pattern"] = r"^SC-0[1-4]$"
    elif "r_<UTC compact>_<6 hex>" in cell:
        spec["pattern"] = r"^r_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{6}$"
    elif "i_<UTC compact>_<6 hex>" in cell:
        spec["pattern"] = r"^i_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{6}$"
    elif "ISO 8601" in cell:
        spec["pattern"] = (
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
        )
    return spec


def coordinate_properties() -> dict:
    rows = parse_md_field_rows(COORDINATE.read_text(encoding="utf-8"), "## Fields", "## Resolution rules")
    # coordinate.md column is Required (yes/no), not Null?. parse_md_field_rows maps that
    # third column into "nullable". Invert: Required=yes means nullable=False.
    names = [r["name"] for r in rows]
    if names != list(COORDINATE_FIELD_ORDER):
        die(
            1,
            "assertion failed: coordinate.md field order/name mismatch: " + str(names),
        )
    required = {r["name"]: r["nullable"] for r in rows}
    if any(required[n] != "yes" for n in COORDINATE_FIELD_ORDER):
        die(1, "assertion failed: a P0 coordinate field is not marked required")
    props = {}
    for row in rows:
        name = row["name"]
        cell = row["type"]
        if name == "wall_clock":
            props[name] = {
                "json_type": "string",
                "nullable": False,
                "pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$",
                "contract_type": cell,
            }
        elif name == "lsn":
            props[name] = {
                "json_type": "string",
                "nullable": False,
                "pattern": r"^[0-9A-F]+/[0-9A-F]+$",
                "contract_type": cell,
            }
        elif name == "snapshot":
            props[name] = {
                "json_type": "string",
                "nullable": False,
                "contract_type": cell,
            }
        elif name in {"skew_ms", "skew_bytes"}:
            props[name] = {
                "json_type": "integer",
                "nullable": False,
                "minimum": 0,
                "contract_type": cell,
            }
        elif name == "resolved_by":
            props[name] = {
                "json_type": "string",
                "nullable": False,
                "enum": ["lsn_first", "snapshot_first", "time_first", "live_heartbeat"],
                "contract_type": cell,
            }
        else:
            die(1, f"assertion failed: unexpected coordinate field {name}")
    return props


def extract_example_row(text: str) -> dict:
    m = re.search(r"## Example row\n\n```json\n(.*?)\n```", text, re.DOTALL)
    if not m:
        die(2, "precondition failed: example row JSON block absent")
    return json.loads(m.group(1))


def build_schema() -> dict:
    text = CONTRACT.read_text(encoding="utf-8")
    rows = parse_md_field_rows(text, "## Fields", "## Validation rules")
    if not rows:
        die(1, "assertion failed: no field rows parsed from results-row.md")
    coord_props = coordinate_properties()
    fields = []
    for row in rows:
        spec = json_type_of(row["type"], row["nullable"] == "yes")
        spec["name"] = row["name"]
        if spec.get("coordinate"):
            spec["required_coordinate_fields"] = list(COORDINATE_FIELD_ORDER)
            spec["coordinate_properties"] = coord_props
        fields.append(spec)
    schema = {
        "title": "results-row",
        "source_contract": str(CONTRACT.relative_to(ROOT)),
        "coordinate_contract": str(COORDINATE.relative_to(ROOT)),
        "field_count": len(fields),
        "coordinate_field_count": len(COORDINATE_FIELD_ORDER),
        "fields": fields,
        "example_row": extract_example_row(text),
    }
    return schema


def js_type_ok(value, json_type: str) -> bool:
    if json_type == "string":
        return isinstance(value, str)
    if json_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if json_type == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and not isinstance(value, bool))
    if json_type == "boolean":
        return isinstance(value, bool)
    if json_type == "object":
        return isinstance(value, dict)
    return False


def validate_value(spec: dict, value, path: str, errors: list[str]) -> None:
    if value is None:
        if not spec.get("nullable"):
            errors.append(f"{path}: required but null")
        return
    jtype = spec["json_type"]
    if not js_type_ok(value, jtype):
        errors.append(
            f"{path}: expected {jtype}, got {type(value).__name__} (no coercion)"
        )
        return
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{path}: {value!r} not in {spec['enum']}")
    if "minimum" in spec and isinstance(value, int) and value < spec["minimum"]:
        errors.append(f"{path}: {value} < minimum {spec['minimum']}")
    if "exclusiveMinimum" in spec and isinstance(value, (int, float)) and value <= spec["exclusiveMinimum"]:
        errors.append(f"{path}: {value} not > {spec['exclusiveMinimum']}")
    if "pattern" in spec and isinstance(value, str) and not re.fullmatch(spec["pattern"], value):
        errors.append(f"{path}: {value!r} does not match {spec['pattern']}")
    if spec.get("coordinate"):
        if not isinstance(value, dict):
            errors.append(f"{path}: coordinate is not an object")
            return
        for cname in COORDINATE_FIELD_ORDER:
            if cname not in value:
                errors.append(f"{path}.{cname}: missing required coordinate field")
        extra = set(value) - set(COORDINATE_FIELD_ORDER)
        if extra:
            errors.append(f"{path}: unexpected coordinate keys {sorted(extra)}")
        cprops = spec["coordinate_properties"]
        for cname, cspec in cprops.items():
            if cname in value:
                validate_value(cspec, value[cname], f"{path}.{cname}", errors)


def validate_row(schema: dict, row: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(row, dict):
        return ["row is not an object"]
    by_name = {f["name"]: f for f in schema["fields"]}
    for spec in schema["fields"]:
        name = spec["name"]
        if name not in row:
            if not spec.get("nullable"):
                errors.append(f"{name}: missing required field")
            continue
        validate_value(spec, row[name], name, errors)
    extra = set(row) - set(by_name)
    if extra:
        errors.append(f"unexpected fields: {sorted(extra)}")
    return errors


def write_if_changed(path: Path, text: str, mode: int) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        os.chmod(path, mode)
        return False
    path.write_text(text, encoding="utf-8")
    os.chmod(path, mode)
    return True


def env_get(text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    if not m:
        return None
    return m.group(1)


def append_env_keys(schema_path: Path) -> bool:
    text = ENV_PATH.read_text(encoding="utf-8")
    wanted = {
        "RESULTS_SCHEMA": str(schema_path),
        "RESULTS_FILE_MODE": "0444",
        "BARRIER_TIMEOUT_S": "120",
    }
    changed = False
    if not text.endswith("\n"):
        text += "\n"
        changed = True
    for key, value in wanted.items():
        existing = env_get(text, key)
        if existing is None:
            text += f"{key}={value}\n"
            changed = True
        elif existing != value:
            die(1, f"assertion failed: {key} is {existing!r}, expected {value!r}")
    if changed:
        ENV_PATH.write_text(text, encoding="utf-8")
        os.chmod(ENV_PATH, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    return changed


def main() -> int:
    if not CONTRACT.is_file() or CONTRACT.stat().st_size == 0:
        die(2, f"precondition failed: {CONTRACT} missing or empty")
    if not LEDGER.is_file() or LEDGER.stat().st_size == 0:
        die(2, f"precondition failed: {LEDGER} missing or empty")
    schema = build_schema()
    example_errors = validate_row(schema, schema["example_row"])
    if example_errors:
        die(1, "assertion failed: example row does not validate:\n" + "\n".join(example_errors))
    encoded = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    schema_changed = write_if_changed(SCHEMA_PATH, encoded, 0o644)
    hashes = {
        "results-row.md": sha256_file(CONTRACT),
        "ledger-integrity.md": sha256_file(LEDGER),
        "results-row.schema.json": sha256_file(SCHEMA_PATH),
        "field_count": schema["field_count"],
        "coordinate_field_count": schema["coordinate_field_count"],
        "coordinate_typed_fields": [
            f["name"] for f in schema["fields"] if f.get("coordinate")
        ],
    }
    hash_text = json.dumps(hashes, indent=2, sort_keys=True) + "\n"
    hashes_changed = write_if_changed(HASH_PATH, hash_text, 0o644)
    env_changed = append_env_keys(SCHEMA_PATH)
    changed = schema_changed or hashes_changed or env_changed
    print(
        json.dumps(
            {
                "ok": True,
                "changed": changed,
                "field_count": schema["field_count"],
                "coordinate_typed_fields": hashes["coordinate_typed_fields"],
                "schema": str(SCHEMA_PATH),
                "example_valid": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
