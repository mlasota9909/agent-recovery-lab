"""P13 offline checks: workload records, reconciliation keys, gate checks and damage counting. No lab commands."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

with patch.dict(os.environ, {"DDL_AUDIT_TABLE": "lab_ddl_audit", "HEARTBEAT_TABLE": "lab_heartbeat"}):
    import lab_dbscen_study as study
    import lab_generate_dbscen as gen
    import lab_validate_dbscen as val
    from lab_ledger_account import map_ops

SC03_INJECTION = {"ops": [
    {"op_index": i, "sql": sql, "lsn_before": f"0/D00{i}000", "commit_lsn": f"0/D00{i}8F0", "xid": 900 + i,
     "t_start": f"2026-10-03T00:00:0{2 * i}Z", "t_end": f"2026-10-03T00:00:0{2 * i + 1}Z", "principal": "lab_agent"}
    for i, sql in enumerate(("ALTER TABLE public.sc03_orders DROP COLUMN status",
                             "ALTER TABLE public.sc03_orders DROP CONSTRAINT sc03_amount_positive",
                             "ALTER TABLE public.sc03_orders ALTER COLUMN amount TYPE text USING amount::text"))]}
SC04_INJECTION = {"ops": [
    {"row_id": rid, "xid": 1000 + i, "commit_lsn": f"0/E00{i}0F0", "lsn_before": f"0/E00{i}000",
     "t": f"2026-10-03T00:00:{10 + i}Z", "principal": "lab_agent"} for i, rid in enumerate((71, 4, 130))]}


def ledger_dml(xid, table, action, rid, lsn):
    return {"xid": xid, "table": table, "action": action, "lsn": lsn, "columns": [{"name": "id", "value": rid}]}


def ledger_ddl(xid, tag, ident, lsn):
    return {"xid": xid, "table": "lab_ddl_audit", "action": "I", "lsn": lsn,
            "columns": [{"name": "command_tag", "value": tag}, {"name": "object_identity", "value": ident}]}


class WorkloadRecord(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"DDL_AUDIT_TABLE": "lab_ddl_audit", "HEARTBEAT_TABLE": "lab_heartbeat"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_sc03_schema_changes_map_to_audit_records(self):
        rows = gen.injected_workload_rows("SC-03", SC03_INJECTION)
        self.assertEqual([r["action"] for r in rows], ["ALTER"] * 3)
        ops = [gen.workload_record(r) for r in gen.combined_workload(rows)]
        ledger = [ledger_ddl(op["xid"], "ALTER TABLE", "public.sc03_orders", f"0/D00{i}8F0") for i, op in enumerate(ops)]
        ledger.append(ledger_ddl(900, "DROP TABLE COLUMN", "public.sc03_orders.status", "0/D0008F0"))
        coverage = map_ops(ops, ledger)
        self.assertEqual((coverage["mapped"], coverage["gaps"], coverage["duplicates"]), (3, [], []))

    def test_sc04_updates_map_to_row_changes(self):
        rows = gen.injected_workload_rows("SC-04", SC04_INJECTION)
        ops = [gen.workload_record(r) for r in gen.combined_workload(rows)]
        ledger = [ledger_dml(op["xid"], "sc04_items", "U", op["natural_key"], "0/E000000") for op in ops]
        coverage = map_ops(ops, ledger)
        self.assertEqual((coverage["mapped"], coverage["gaps"]), (3, []))

    def test_unrecorded_damage_is_a_gap_not_silence(self):
        rows = gen.injected_workload_rows("SC-04", SC04_INJECTION)
        ops = [gen.workload_record(r) for r in gen.combined_workload(rows)]
        coverage = map_ops(ops, [])
        self.assertEqual(len(coverage["gaps"]), 3)

    def test_manifest_holds_legitimate_changes_only(self):
        legit = [{"xid": 5, "table": "sc04_items", "action": "U", "natural_key": 9, "commit_lsn": "0/E0000F0",
                  "principal": "lab_app", "wall_clock": "t", "row_ids": [9], "row_count": 1}]
        ddl = [{"xid": 6, "action": "CREATE", "command_tag": "CREATE TABLE", "object_identity": "public.p2_alt",
                "commit_lsn": "0/F000000", "principal": "lab_app"}]
        combined = gen.combined_workload(legit, gen.injected_workload_rows("SC-04", SC04_INJECTION), ddl)
        self.assertEqual([r["op_index"] for r in combined], list(range(5)))
        manifest = gen.legitimate_manifest(combined)
        self.assertEqual([(m["relation"], m["row_ids"]) for m in manifest], [("sc04_items", [9])])
        self.assertNotIn("injected", gen.workload_record(combined[0]))


class GateChecks(unittest.TestCase):
    def window(self, wid, start, end):
        return {"window_id": wid, "t_start": f"2026-10-03T00:00:{start:02d}.000000Z",
                "t_end": f"2026-10-03T00:00:{end:02d}.000000Z"}

    def test_sane_windows_pass(self):
        self.assertEqual(study.window_problems([self.window(0, 0, 1), self.window(1, 2, 3)]), [])

    def test_negative_long_or_unordered_windows_fail(self):
        self.assertTrue(study.window_problems([self.window(-2, 0, 1), self.window(0, 2, 3)]))
        self.assertTrue(study.window_problems([self.window(0, 0, 1), self.window(1, 2, 40)]))
        self.assertTrue(study.window_problems([self.window(0, 4, 5), self.window(1, 2, 3)]))


class DamageCounting(unittest.TestCase):
    def test_sc03_units(self):
        units = gen.damage_manifest("SC-03", SC03_INJECTION)["units"]
        intact = ("id bigint", "amount numeric(12,2)", "status text")
        self.assertEqual(val.sc03_damage(intact, {"sc03_orders_pkey", "sc03_amount_positive"}, units), [])
        first = ("id bigint", "amount numeric(12,2)")
        self.assertEqual(len(val.sc03_damage(first, {"sc03_orders_pkey", "sc03_amount_positive"}, units)), 1)
        all_three = ("id bigint", "amount text")
        self.assertEqual(len(val.sc03_damage(all_three, {"sc03_orders_pkey"}, units)), 3)

    def test_sc04_units_count_damaged_values_even_after_later_appends(self):
        units = gen.damage_manifest("SC-04", SC04_INJECTION)["units"]
        values = {71: "mal-71.", 4: "legit-4..", 130: "legit-130"}
        self.assertEqual([m["object"] for m in val.sc04_damage(values, units)], ["public.sc04_items:71"])

    def test_work_lost_uses_the_sc01_rule(self):
        manifest = [{"commit_lsn": "0/100", "row_count": 1}, {"commit_lsn": "0/200", "row_count": 2},
                    {"commit_lsn": "0/300", "row_count": 4}]
        self.assertEqual(val.legitimate_lost(manifest, chosen=0x150, reference=0x250), (2, 6))
        self.assertEqual(val.legitimate_lost(manifest, chosen=0x260, reference=0x250), (0, 4))


class LockSafeCheck(unittest.TestCase):
    """A copy stopped inside an uncommitted schema change holds the table's lock: SC-03 reads catalogs only."""

    def test_sc03_never_reads_the_damaged_table_and_every_query_has_timeouts(self):
        import json
        import tempfile
        queries = []

        def fake_psql(port, sql):
            queries.append(sql)
            if "pg_attribute" in sql:
                return "id bigint\namount numeric(12,2)\nstatus text"
            if "pg_constraint" in sql:
                return "sc03_orders_pkey\nsc03_amount_positive"
            raise AssertionError("unexpected query: " + sql)

        with tempfile.TemporaryDirectory() as tmp:
            root, ev = Path(tmp) / "restore", Path(tmp) / "evidence"
            root.mkdir(); ev.mkdir()
            (root / "report.partial.json").write_text(json.dumps(
                {"restore_target": {"sandbox_port": 55432}, "coordinate": {"lsn_int": 0x200}}))
            (ev / "oracle-manifest.json").write_text(json.dumps(
                {"optimum_lsn": "0/100", "damage": gen.damage_manifest("SC-03", SC03_INJECTION)}))
            (ev / "workload-manifest.jsonl").write_text("")
            with patch.object(val, "psql", fake_psql), patch.object(val, "restore_root", return_value=root), \
                    patch.object(val, "evidence_dir", return_value=ev), \
                    patch.object(val, "file_block", return_value={"mismatches": []}), \
                    patch.object(val, "write_json"):
                out = val.validate("SC-03_X", "ab-512")
        self.assertEqual(out["summary"]["damage_units_retained"], 0)
        self.assertTrue(queries and all(q.startswith(val.TIMEOUTS) for q in queries))
        self.assertFalse(any("FROM public.sc03_orders" in q for q in queries))


class PositionOrder(unittest.TestCase):
    def test_heartbeats_order_by_number_across_a_hex_digit_boundary(self):
        import lab_analytics
        rows = [{"lsn": "E404/14000208"}, {"lsn": "E404/1C000028"}, {"lsn": "E404/9000028"}]
        self.assertEqual([r["lsn"] for r in lab_analytics.by_position(rows)],
                         ["E404/9000028", "E404/14000208", "E404/1C000028"])
        self.assertEqual(sorted(r["lsn"] for r in rows)[0], "E404/14000208")   # the text order the views gave


class DamageShown(unittest.TestCase):
    def test_reads_positions_from_each_input(self):
        oracle = {"first_damage_commit_lsn": "0/D0006D8"}
        with patch.object(study, "read", return_value=oracle), patch.object(study, "evidence_dir", return_value=Path("/x")):
            r1 = {"content": '{"anomaly_score":3.4,"last_safe_lsn_int":167773800,"window_index":9}\n'}
            r2 = {"content": "Window 15 [218108216..218110408]: 1 DELETE on relation p2_probe, 1 INSERT; anomaly 0.9.\n"}
            r0 = {"content": '{"action":"U","lsn_int":201333128,"object":"p2_probe"}\n'}
            self.assertEqual([study.damage_shown("SC-03_X", v) for v in (r1, r2, r0)], [False, True, False])


if __name__ == "__main__":
    unittest.main()
