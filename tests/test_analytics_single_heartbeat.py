"""A window holding one heartbeat is measured over its own length, not over a zero heartbeat span."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import lab_analytics

T0 = datetime(2026, 10, 3, 5, 29, 0, tzinfo=timezone.utc)


def at(seconds):
    return (T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# Two-second windows. Window 0 holds heartbeats at 0.0 and 1.0 s; window 1 holds only the heartbeat at 2.5 s, as in
# SC-03_20261003T052858Z window 18; window 2 holds the heartbeat at 4.2 s.
HEARTBEATS = [{"lsn": "0/1000", "timestamp": at(0.0)}, {"lsn": "0/2000", "timestamp": at(1.0)},
              {"lsn": "0/3000", "timestamp": at(2.5)}, {"lsn": "0/5000", "timestamp": at(4.2)}]
CHANGES = ([{"action": "U", "lsn": f"0/1{i}00", "timestamp": at(0.2 + 0.1 * i), "table": "p2_probe"} for i in range(3)]
           + [{"action": "U", "lsn": f"0/3{i}00", "timestamp": at(2.6 + 0.1 * i), "table": "p2_probe"} for i in range(8)]
           + [{"action": "D", "lsn": "0/5100", "timestamp": at(4.3), "table": "p2_probe"}])


def fake_fetch(incident, sql):
    if "FROM heartbeats" in sql:
        return [dict(r) for r in HEARTBEATS]
    if "FROM db_changes" in sql:
        return [dict(r) for r in CHANGES]
    return []


class SingleHeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)
        for name, value in (("require_lab", lambda: None), ("scenario_config", lambda: {"SC01_WINDOW_S": "2"}),
                            ("fetch", fake_fetch), ("p3_dir", lambda incident: self.out)):
            patcher = patch.object(lab_analytics, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_burst_density_per_window(self):
        lab_analytics.analytics("SC-03_TEST")
        rows = {r["window_id"]: r for r in lab_analytics.load_jsonl(self.out / "analytics.jsonl")}
        self.assertEqual([rows[i]["heartbeat_count"] for i in (0, 1, 2)], [2, 1, 1])
        self.assertAlmostEqual(rows[0]["change_burst_density"], 3 / 1.0)   # heartbeat span, as before
        self.assertAlmostEqual(rows[1]["change_burst_density"], 8 / 2)     # one heartbeat: the window's own length
        self.assertAlmostEqual(rows[2]["change_burst_density"], 1 / 2)


if __name__ == "__main__":
    unittest.main()
