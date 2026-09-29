"""Incident preparation uses the site cluster even when archive/current names an incident."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INCIDENT = "SC-02_20260101T000000Z"
RUNTIME = {"ARCHIVE_INCIDENT": INCIDENT, "INC_ID": "i_20260101T000000Z_abcdef",
           "INC_DS": "labpool/victim/inc_i_20260101T000000Z_abcdef", "INC_PGDATA": "/incident/data",
           "INC_PROTECTED": "/incident/protected", "INC_PG_PORT": "56001",
           "INC_PG_SOCKET": "/var/run/postgresql", "INC_SLOT": "lab_20260101t000000z_abcdef",
           "INC_HEARTBEAT_PORT": "56001"}


class SiteScopeTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "var"
        parent.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(dir=parent))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        runtime = self.root / "runtime/incidents"
        runtime.mkdir(parents=True)
        (runtime / (RUNTIME["INC_ID"] + ".env")).write_text("".join(f"{k}={v}\n" for k, v in RUNTIME.items()))
        (self.root / "archive" / INCIDENT).mkdir(parents=True)
        (self.root / "archive/current").symlink_to(self.root / "archive" / INCIDENT)

    def select(self, **extra):
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("LAB_ACTIVE_INCIDENT", "LAB_SITE_SCOPE")}
        environment.update(LAB_ROOT=str(self.root), ARCHIVE_CURRENT=str(self.root / "archive/current"),
                           PG_PORT="5432", DS_PARENT="labpool/victim", **extra)
        proc = subprocess.run(["bash", "-c", f"source '{ROOT}/lib/lab_incident_env.sh'; rc=$?; "
                               "printf '%s %s %s\\n' \"$rc\" \"$PG_PORT\" \"$DS_PARENT\""],
                              env=environment, text=True, capture_output=True, check=False)
        return proc.stdout.split()

    def test_current_incident_is_selected_by_default(self):
        self.assertEqual(self.select(), ["0", "56001", RUNTIME["INC_DS"]])

    def test_site_scope_keeps_the_site_cluster(self):
        self.assertEqual(self.select(LAB_SITE_SCOPE="1"), ["0", "5432", "labpool/victim"])

    def test_site_scope_and_an_active_incident_are_exclusive(self):
        self.assertEqual(self.select(LAB_SITE_SCOPE="1", LAB_ACTIVE_INCIDENT=INCIDENT)[0], "2")


class FinishedClusterTests(unittest.TestCase):
    def test_every_recorded_incident_cluster_is_stopped_outside_the_site_scope(self):
        import sys
        from unittest.mock import patch
        sys.path.insert(0, str(ROOT / "lib"))
        import lab_incident_runtime as runtime
        root = Path(tempfile.mkdtemp(dir=ROOT / "var"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "runtime/incidents").mkdir(parents=True)
        for name in ("SC-02_20260101T000000Z", "SC-02_20260102T000000Z"):
            (root / "runtime/incidents" / (name + ".env")).write_text(f"ARCHIVE_INCIDENT={name}\nINC_ID=x\n")
        calls = []
        def fake(argv, env, **_):
            calls.append((argv[1:], "LAB_SITE_SCOPE" in env))
            return subprocess.CompletedProcess(argv, 0, stdout='{"changed":true,"ok":true}\n', stderr="")
        with patch.object(runtime, "lab_root", return_value=root), patch.object(runtime.subprocess, "run", side_effect=fake), \
             patch.dict(os.environ, {"LAB_SITE_SCOPE": "1"}):
            stopped = runtime.stop_finished_incident_clusters()
        self.assertEqual([c[0] for c in calls], [["stop", "--incident", "SC-02_20260101T000000Z"],
                                                  ["stop", "--incident", "SC-02_20260102T000000Z"]])
        self.assertFalse(any(c[1] for c in calls))
        self.assertEqual(len(stopped), 2)


if __name__ == "__main__":
    unittest.main()
