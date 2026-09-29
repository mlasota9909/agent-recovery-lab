"""A sandbox stop never signals a postmaster running outside the sandbox."""
from __future__ import annotations

import os
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

VICTIM = {"PG_DATA": "/srv/source/pgdata", "MNT_PROTECTED": "/srv/source/protected",
          "DS_PGDATA": "labpool/victim/inc/pgdata", "DS_PROTECTED": "labpool/victim/inc/protected",
          "DS_PARENT": "labpool/victim/inc"}
FAKE_SUDO = """#!/bin/sh
while :; do
  case $1 in
    -n) shift ;;
    -u) shift 2 ;;
    *) break ;;
  esac
done
exec "$@"
"""


class SandboxStopTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "var"
        parent.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=parent))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.calls = self.tmp / "pg_ctl.calls"
        for name, text in (("sudo", FAKE_SUDO), ("pg_ctl", f"#!/bin/sh\necho \"$@\" >> '{self.calls}'\n")):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        self.pgdata = self.tmp / "sandbox/pgdata"
        self.pgdata.mkdir(parents=True)
        environment = patch.dict(os.environ, {**VICTIM, "PATH": f"{self.bin}:{os.environ['PATH']}"})
        environment.start()
        self.addCleanup(environment.stop)

    def process(self, cwd):
        proc = subprocess.Popen(["sleep", "60"], cwd=cwd)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        return proc.pid

    def stop(self):
        def local(script, timeout=180):
            return subprocess.run(["bash", "-s"], input=script + "\n", text=True, capture_output=True,
                                  timeout=timeout, check=False)
        with patch.object(restore, "ssh_sudo", side_effect=local), \
                patch.object(restore, "PG_BIN", str(self.bin)), patch.object(restore, "append_cmd"):
            restore.stop_sandbox(str(self.pgdata), 55432, self.tmp / "restore.log")
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_cloned_pid_file_of_the_source_cluster_is_never_signalled(self):
        source = self.tmp / "source"
        source.mkdir()
        (self.pgdata / "postmaster.pid").write_text(f"{self.process(source)}\n{source}\n")
        self.assertEqual(self.stop(), [])

    def test_postmaster_running_in_the_sandbox_is_stopped(self):
        (self.pgdata / "postmaster.pid").write_text(f"{self.process(self.pgdata)}\n{self.pgdata}\n")
        self.assertEqual(self.stop(), [f"-D {self.pgdata} -m fast stop"])

    def test_missing_or_malformed_pid_file_stops_nothing(self):
        self.assertEqual(self.stop(), [])
        (self.pgdata / "postmaster.pid").write_text("12x\n")
        self.assertEqual(self.stop(), [])

    def test_victim_paths_are_still_refused(self):
        with self.assertRaises(SystemExit):
            restore.stop_sandbox(VICTIM["PG_DATA"], 55432, self.tmp / "restore.log")


if __name__ == "__main__":
    unittest.main()
