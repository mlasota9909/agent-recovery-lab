"""lab-validate-dbscen: compare an SC-03 or SC-04 sandbox restore with the reference (P13).

Writes validation.json in the format lab-verdict reads, so the verdict rules are the SC-01 ones. Checked damage is
counted in units: each scripted schema change still present (SC-03), or each scripted row that still holds its
damaging value (SC-04). Legitimate work lost and the file comparison follow lab_validate.py exactly.
"""
from __future__ import annotations

import argparse
import json
import sys

from lab_p4_util import restore_root, write_json
from lab_paths import evidence_dir
from lab_validate import expected_fingerprints, guest_sha256, hash_ids, load_jsonl, parse_hash_lines, psql, rec_lsn, rec_rows

# A copy restored to a point inside an uncommitted schema change is paused in recovery, and its startup process holds
# that transaction's exclusive lock on the table. The schema is therefore read from the catalogs, which need no lock on
# the table, and every query has lock and statement timeouts so that a wait fails instead of hanging.
TIMEOUTS = "SET lock_timeout = '10s'; SET statement_timeout = '120s'; "


def query(port: int, sql: str) -> str:
    return psql(port, TIMEOUTS + sql)
from lab_p4_util import ssh_sudo
from lsn import lsn_int, lsn_norm

EXPECTED_COLUMNS = {
    "sc03_orders": ("id bigint", "amount numeric(12,2)", "status text"),
    "sc04_items": ("id bigint", "payload text"),
}
SC03_RULE = "sc03_amount_positive"


def columns(port: int, table: str) -> tuple[str, ...]:
    out = query(port, "SELECT a.attname||' '||format_type(a.atttypid,a.atttypmod) FROM pg_attribute a "
                     "JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                     f"WHERE n.nspname='public' AND c.relname='{table}' AND a.attnum>0 AND NOT a.attisdropped "
                     "ORDER BY a.attnum;")
    return tuple(x for x in out.splitlines() if x.strip())


def sc03_damage(cols: tuple[str, ...], rules: set[str], units: list[dict]) -> list[dict]:
    present = {
        "status_column_dropped": not any(c.startswith("status ") for c in cols),
        "amount_rule_dropped": SC03_RULE not in rules,
        "amount_type_changed": "amount numeric(12,2)" not in cols,
    }
    return [{"object": "public.sc03_orders", "kind": "schema_change", "expected": "absent", "actual": u["unit"],
             "classification": "damage_retained"} for u in units if present[u["unit"]]]


def sc04_damage(values: dict[int, str], units: list[dict]) -> list[dict]:
    out = []
    for u in units:
        actual = values.get(int(u["row_id"]))
        if actual is not None and actual.startswith(u["damaging_value"]):
            out.append({"object": f"public.sc04_items:{u['row_id']}", "kind": "row_value",
                        "expected": "pre-damage value", "actual": actual, "classification": "damage_retained"})
    return out


def legitimate_lost(manifest: list[dict], chosen: int, reference: int) -> tuple[int, int]:
    """SC-01's rule: legitimate operations committed after the point and no later than the reference."""
    lost = analytical = 0
    for rec in manifest:
        n = rec_lsn(rec)
        if n is None:
            continue
        rows = rec_rows(rec)
        if n > chosen:
            analytical += rows
        if chosen < n <= reference:
            lost += rows
    return lost, analytical


def file_block(incident: str, restore_of: str, partial: dict) -> dict:
    ev = evidence_dir(incident)
    fs_mnt = partial["restore_target"].get("fs_mount") or ""
    mismatches, files_checked = [], 0
    if fs_mnt:
        listing = ssh_sudo(f"find '{fs_mnt}' -type f ! -path '*/.zfs/*' | sort")
        files_checked = len([ln for ln in listing.stdout.splitlines() if ln.strip()])
    reference_snapshot, expected = expected_fingerprints(ev)
    probe = restore_root(incident, restore_of) / "fs_probe.tsv"
    if probe.is_file():
        expected.extend(parse_hash_lines(probe.read_text()))
    for rel_or_abs, expected_hash in expected:
        path = rel_or_abs if rel_or_abs.startswith("/") else (fs_mnt.rstrip("/") + "/" + rel_or_abs.lstrip("/"))
        actual = guest_sha256(path)
        files_checked = max(files_checked, 1)
        if actual is None:
            mismatches.append({"object": path, "kind": "missing", "expected": expected_hash, "actual": "missing",
                               "classification": "legit_lost"})
        elif actual != expected_hash:
            mismatches.append({"object": path, "kind": "byte_hash", "expected": expected_hash, "actual": actual,
                               "classification": "damage_retained"})
    return {"files_checked": files_checked, "expected_snapshot": reference_snapshot, "files_compared": len(expected),
            "files_matched": files_checked - len(mismatches) if files_checked else 0, "mismatches": mismatches}


def validate(incident: str, restore_of: str) -> dict:
    partial = json.loads((restore_root(incident, restore_of) / "report.partial.json").read_text())
    port = int(partial["restore_target"]["sandbox_port"])
    ev = evidence_dir(incident)
    man = json.loads((ev / "oracle-manifest.json").read_text())
    damage = man["damage"]
    table = damage["table"]
    chosen = int(partial["coordinate"]["lsn_int"])
    reference = lsn_int(lsn_norm(man["optimum_lsn"]))

    cols = columns(port, table)
    if table == "sc03_orders":
        rules = set(query(port, "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
                                "WHERE t.relname='sc03_orders';").split())
        retained = sc03_damage(cols, rules, damage["units"])
        ids = []   # catalog checks only: the table itself may be locked by a replayed, uncommitted schema change
    else:
        raw = query(port, "SELECT id || '|' || payload FROM public.sc04_items ORDER BY id;")
        values = {int(line.split("|", 1)[0]): line.split("|", 1)[1] for line in raw.splitlines() if "|" in line}
        retained = sc04_damage(values, damage["units"])
        ids = sorted(values)
    lost, analytical = legitimate_lost(load_jsonl(ev / "workload-manifest.jsonl"), chosen, reference)

    expected_cols = EXPECTED_COLUMNS[table]
    damaged_schema = bool(retained) and table == "sc03_orders"
    schema_diffs = []
    if cols != expected_cols and not damaged_schema:
        schema_diffs.append({"object": f"public.{table}", "kind": "schema", "expected": " | ".join(expected_cols),
                             "actual": " | ".join(cols), "classification": "legit_lost"})
    fs_block = file_block(incident, restore_of, partial)
    summary = {
        "damage_rows_retained": len(retained),
        "damage_units_retained": len(retained),
        "damage_units_total": len(damage["units"]),
        "legit_rows_lost": lost,
        "files_mismatched": len(fs_block["mismatches"]),
        "schema_diffs": len(schema_diffs),
        "p3_analytical_legit_rows_lost": analytical,
    }
    out = {
        "db_validation": {"relations_checked": 1, "relations_matched": 0 if retained else 1, "mismatches": retained,
                          "relations": {table: {"row_count": len(ids), "content_hash": hash_ids(ids)}},
                          "p3_analytical_legit_rows_lost": analytical},
        "fs_validation": fs_block,
        "schema_validation": {"ddl_match": cols == expected_cols, "diffs": schema_diffs, "ddl": "\n".join(cols)},
        "summary": summary,
    }
    write_json(restore_root(incident, restore_of) / "validation.json", out)
    return out


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-validate-dbscen")
    p.add_argument("incident")
    p.add_argument("restore_of")
    args = p.parse_args(argv)
    print(json.dumps(validate(args.incident, args.restore_of), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
