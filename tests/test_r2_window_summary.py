"""Written Summaries count inserts, updates and deletes, and name each schema change."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import lab_repr_r2 as r2

BUCKET = ([{"action": "U", "object": "p2_probe", "xid": 1, "natural_key": 1}] * 3
          + [{"action": "I", "object": "p2_probe", "xid": 2, "natural_key": 2},
             {"action": "D", "object": "p2_probe", "xid": 3, "natural_key": 3},
             {"action": "U", "object": "sc04_items", "xid": 4, "natural_key": 29},
             {"action": "ALTER TABLE", "object": "public.sc03_orders", "xid": 5, "natural_key": None}])
WINDOWS = [{"window_index": 14, "first_lsn_int": 100, "last_lsn_int": 200, "anomaly_score": 1.5},
           {"window_index": 15, "first_lsn_int": 201, "last_lsn_int": 300, "anomaly_score": 0.2}]


class WindowSummaryTests(unittest.TestCase):
    def summaries(self):
        with patch.object(r2, "events_by_window", lambda events, c5, window_s: {14: BUCKET, 15: []}):
            return [s for s in r2.build_summaries(BUCKET, WINDOWS, 2, []) if s["kind"] == "window"]

    def test_counts_and_schema_change(self):
        w14 = self.summaries()[0]
        self.assertEqual((w14["n_ins"], w14["n_upd"], w14["n_del"], w14["n_ddl"]), (1, 4, 1, 1))
        self.assertEqual(w14["text"], "Window 14 [100..200]: 1 INSERT, 4 UPDATE and 1 DELETE, most on relation p2_probe; "
                                      "1 schema change (ALTER TABLE on public.sc03_orders); anomaly 1.5.")

    def test_quiet_window(self):
        w15 = self.summaries()[1]
        self.assertEqual(w15["text"], "Window 15 [201..300]: 0 INSERT, 0 UPDATE and 0 DELETE, most on relation -; "
                                      "no schema change; anomaly 0.2.")

    def test_reconciliation_checks_the_new_counts(self):
        rows = self.summaries()
        with patch.object(r2, "events_by_window", lambda events, c5, window_s: {14: BUCKET, 15: []}):
            ok, errors = r2.reconcile_summaries(rows, BUCKET, [], 2)
            bad = [dict(rows[0], n_upd=3)] + rows[1:]
            ok_bad, errors_bad = r2.reconcile_summaries(bad, BUCKET, [], 2)
        self.assertFalse([e for e in errors if "n_upd" in e or "n_ddl" in e])
        self.assertTrue(any("n_upd" in e for e in errors_bad))


if __name__ == "__main__":
    unittest.main()
