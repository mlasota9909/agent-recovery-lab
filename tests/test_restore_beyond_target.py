"""The restore's beyond-target probe places the damage at its commit record, not at the recorded pre-commit bound."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import lab_restore_db as restore

# Shape of SC-01_20261003T042542Z: the recorded bound (0/2C000000) lies before the deletion's own records; the last
# DELETE is at 0/2C007EE0, another transaction commits at 0/2C007F30 and the deletion commits at 0/2C007F60.
INJECTION = {"commit_lsn": "0/2C000000", "xid": 1126, "row_ids": [1, 2], "relation": "p2_probe"}
CHANGE_LOG = [
    {"lsn": "0/2C007F30", "action": "B", "xid": 1127},
    {"lsn": "0/2C007F30", "action": "C", "xid": 1127},
    {"lsn": "0/2C007F60", "action": "B", "xid": 1126},
    {"lsn": "0/2C001028", "action": "D", "xid": 1126, "object": "p2_probe"},
    {"lsn": "0/2C007EE0", "action": "D", "xid": 1126, "object": "p2_probe"},
    {"lsn": "0/2C007F60", "action": "C", "xid": 1126},
]


def lsn(text):
    high, low = text.split("/")
    return (int(high, 16) << 32) | int(low, 16)


class BeyondTargetTests(unittest.TestCase):
    def setUp(self):
        self.ev = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.ev, ignore_errors=True)
        (self.ev / "injection.json").write_text(json.dumps(INJECTION))
        (self.ev / "db.jsonl").write_text("".join(json.dumps(r) + "\n" for r in CHANGE_LOG))
        for name, value in (("evidence_dir", lambda incident: self.ev), ("env", lambda key: "labdb")):
            patcher = patch.object(restore, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def probe(self, target, rows_present):
        result = subprocess.CompletedProcess([], 0, stdout=f"{rows_present}\n", stderr="")
        with patch.object(restore, "ssh_sudo", return_value=result):
            return restore.beyond_target_absent("SC-01_TEST", lsn(target), 55432)

    def test_target_inside_the_uncommitted_deletion_expects_the_row(self):
        out = self.probe("0/2C007EE0", 1)
        self.assertTrue(out["absent_ok"])
        self.assertEqual(out["kind"], "before_inject")
        self.assertEqual((out["inject_lsn_int"], out["inject_lsn_source"]), (lsn("0/2C007F60"), "change_log"))

    def test_target_at_the_commit_record_expects_the_row_gone(self):
        self.assertTrue(self.probe("0/2C007F60", 0)["absent_ok"])
        self.assertFalse(self.probe("0/2C007F60", 1)["absent_ok"])

    def test_target_before_the_damage_expects_the_row(self):
        self.assertTrue(self.probe("0/2B000638", 1)["absent_ok"])
        self.assertFalse(self.probe("0/2B000638", 0)["absent_ok"])

    def test_without_a_change_log_the_recorded_bound_is_used(self):
        (self.ev / "db.jsonl").unlink()
        out = self.probe("0/2C007EE0", 1)
        self.assertEqual((out["inject_lsn_int"], out["inject_lsn_source"]), (lsn("0/2C000000"), "recorded_bound"))
        self.assertFalse(out["absent_ok"])


if __name__ == "__main__":
    unittest.main()
