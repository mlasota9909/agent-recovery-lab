"""Offline configuration, relocation and archive-boundary regression checks."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from lab_config import load_env, write_local_env

HOME_PATH = re.compile(rb"/" + rb"home/[^\s`\"'<>]+")
# WI-P12-A forbids editing frozen contracts. These exact original bytes are the
# only exceptions; a new path or any change to an exempt file fails the scan.
FROZEN_EXCEPTIONS = {
    "sdd/specs/P0-lab-substrate/contracts/cli.md":
        "01f0dbc60d7ab5670b8d9b135ab3c8983b9bd00df67e966dd10c36bbc4e5d5d1",
    "sdd/specs/P0-lab-substrate/contracts/lab-env.md":
        "60ba07ae7e308a4923fc829c0f6e0ec568272dc66a8bb94582b4a5953e921e5b",
    "sdd/specs/P4-restore-validation/contracts/restore-report.md":
        "451ca3028497feaabcaafbc77a162130023ef60edf17c07718a4a9e64556d71d",
}


def source_files() -> list[str]:
    raw = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
    )
    return sorted(set(os.fsdecode(name) for name in raw.split(b"\0") if name))


class SourcePortabilityTests(unittest.TestCase):
    def test_no_absolute_home_paths_except_unchanged_frozen_contracts(self):
        violations = []
        for name in source_files():
            # Run records are verbatim data from the reference checkout, not source;
            # records/P12/verify.py checks them against the freeze.
            if name.startswith("records/"):
                continue
            data = (ROOT / name).read_bytes()
            if name in FROZEN_EXCEPTIONS:
                self.assertEqual(hashlib.sha256(data).hexdigest(), FROZEN_EXCEPTIONS[name], name)
            elif HOME_PATH.search(data):
                violations.append(name)
        self.assertEqual(violations, [], "absolute home paths: " + ", ".join(violations))

    def test_path_detector_rejects_a_new_checkout_literal(self):
        self.assertIsNotNone(HOME_PATH.search(b"/" + b"home/example/checkout/bin/run"))
        self.assertIsNone(HOME_PATH.search(b"<repo>/bin/run"))

    def test_all_frozen_contracts_are_unchanged(self):
        names = subprocess.check_output(["git", "ls-files", "-z", "sdd/specs/*/contracts/*"], cwd=ROOT)
        for raw in names.split(b"\0"):
            if raw:
                name = os.fsdecode(raw)
                expected = subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT)
                self.assertEqual((ROOT / name).read_bytes(), expected, name)

    def test_output_and_local_config_ignore_rules(self):
        ignored = ["etc/lab.local.env", "runtime/p9-model-set.json"]
        visible = ["etc/lab.env", "runtime/p9-model-set.template.json"]
        for folder in ("evidence", "archive", "results", "logs", "var", "runtime", "basebackup", "analysis-out"):
            ignored.extend([folder + "/run.txt", folder + "/nested/run.txt"])
            visible.append(folder + "/.gitkeep")
        for name in ignored + visible:
            proc = subprocess.run(["git", "check-ignore", "--no-index", "-q", name], cwd=ROOT)
            self.assertEqual(proc.returncode, 0 if name in ignored else 1, name)

    def test_local_example_documents_every_configuration_key(self):
        keys = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", (ROOT / "etc/lab.env").read_text(), re.M))
        documented = set(re.findall(r"^# ([A-Z][A-Z0-9_]*)=", (ROOT / "etc/lab.local.env.example").read_text(), re.M))
        self.assertFalse(keys - documented, sorted(keys - documented))


class RelocatedCheckoutTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "var/portability-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch, prefix="checkout ' $ ")
        self.addCleanup(self.temporary.cleanup)
        self.checkout = Path(self.temporary.name)
        for name in ("etc/lab.env", "etc/systemd/lab-consumer@.service", "lib/lab_config.py",
                     "lib/lab_env_overrides.sh", "bin/lab-wal-receive", "bin/lab-wal-receiver-key",
                     "bin/lab-consumer-unit"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        self.env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}

    def shell_config(self, extra="", env=None):
        script = 'set -aeu; source "$1/etc/lab.env"; ' + extra + 'env -0'
        proc = subprocess.run(["bash", "-c", script, "config", str(self.checkout)],
                              cwd=ROOT, env=env or self.env, capture_output=True, check=True)
        return dict(row.decode().split("=", 1) for row in proc.stdout.split(b"\0") if row)

    def python_config(self):
        proc = subprocess.run([sys.executable, "-c",
                               'import json; from lab_config import load_env; print(json.dumps(load_env()))'],
                              cwd=ROOT, env=dict(self.env, PYTHONPATH=str(self.checkout / "lib")),
                              capture_output=True, text=True, check=True)
        return json.loads(proc.stdout)

    def test_defaults_follow_checkout_from_unrelated_working_directory(self):
        shell, python = self.shell_config(), self.python_config()
        expected = {"LAB_ROOT": self.checkout, "EVIDENCE_ROOT": self.checkout / "evidence",
                    "ARCHIVE_ROOT": self.checkout / "archive", "ARCHIVE_CURRENT": self.checkout / "archive/current",
                    "RESULTS_ROOT": self.checkout / "results", "BASEBACKUP_ROOT": self.checkout / "basebackup"}
        for key, value in expected.items():
            self.assertEqual(shell[key], str(value))
            self.assertEqual(python[key], str(value))
        self.assertEqual(shell["RESULTS_GLOB"], "results/*.jsonl")
        self.assertFalse((self.checkout / "etc/lab.local.env").exists())

    def test_local_values_and_dependent_defaults_match_in_both_loaders(self):
        local = self.checkout / "etc/lab.local.env"
        local.write_text('VM_NAME="test vm"\nPG_VERSION=19\nARCHIVE_ROOT="$LAB_ROOT/custom archive"\n'
                         'P9_ENDPOINT="http://127.0.0.1:4321"\nHOST_ARCHIVE_USER=archive-test\n')
        shell, python = self.shell_config(), self.python_config()
        for key in ("VM_NAME", "PG_VERSION", "PG_DATA", "ARCHIVE_ROOT", "ARCHIVE_CURRENT", "P9_ENDPOINT", "HOST_ARCHIVE_USER"):
            self.assertEqual(shell[key], python[key], key)
        self.assertEqual(shell["ARCHIVE_CURRENT"], str(self.checkout / "custom archive/current"))
        self.assertEqual(shell["PG_DATA"], "/var/lib/postgresql/19/main")
        self.assertEqual(shell["VM_NAME"], "test vm")

    def test_existing_scratch_override_precedence(self):
        (self.checkout / "etc/lab.local.env").write_text('EVIDENCE_ROOT="$LAB_ROOT/site evidence"\n')
        scratch = str(self.checkout / "scratch evidence")
        shell = self.shell_config('source "$1/lib/lab_env_overrides.sh"; ', dict(self.env, _LAB_OV_EVIDENCE_ROOT=scratch))
        self.assertEqual(shell["EVIDENCE_ROOT"], scratch)

    def test_site_writer_keeps_template_and_quotes_values(self):
        template = (self.checkout / "etc/lab.env").read_bytes()
        local = self.checkout / "etc/lab.local.env"
        local.write_text('# keep this comment\nVM_NAME=old\nVM_ADDR=192.0.2.3\n')
        value = "name with ' quotes and $(literal)"
        self.assertTrue(write_local_env({"VM_NAME": value}, self.checkout))
        self.assertFalse(write_local_env({"VM_NAME": value}, self.checkout))
        self.assertEqual(self.shell_config()["VM_NAME"], value)
        self.assertIn("# keep this comment", local.read_text())
        self.assertIn("VM_ADDR=192.0.2.3", local.read_text())
        self.assertEqual(local.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.checkout / "etc/lab.env").read_bytes(), template)

    def receive(self, command, payload=b"wal bytes", **extra):
        return subprocess.run([str(self.checkout / "bin/lab-wal-receive")], input=payload,
                              env=dict(self.env, SSH_ORIGINAL_COMMAND=command, **extra),
                              cwd=ROOT, capture_output=True)

    def test_receiver_uses_own_archive_and_preserves_append_protections(self):
        archive = self.checkout / "custom archive"
        incident = archive / "SC-01_test"
        incident.mkdir(parents=True)
        (archive / "current").symlink_to(incident.name)
        (self.checkout / "etc/lab.local.env").write_text('ARCHIVE_ROOT="$LAB_ROOT/custom archive"\n')
        segment = "000000010000000000000001"
        result = self.receive("append " + segment, LAB_ROOT=str(ROOT), ARCHIVE_ROOT=str(ROOT / "archive"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((incident / segment).read_bytes(), b"wal bytes")
        self.assertEqual((incident / segment).stat().st_mode & 0o777, 0o444)
        self.assertEqual(self.receive("append " + segment, b"overwrite").returncode, 42)
        self.assertEqual((incident / segment).read_bytes(), b"wal bytes")
        self.assertNotEqual(self.receive("append ../escape").returncode, 0)
        (archive / "current").unlink()
        (archive / "current").symlink_to(self.checkout)
        self.assertNotEqual(self.receive("append " + segment).returncode, 0)
        self.assertFalse((self.checkout / segment).exists())

    def test_key_printer_quotes_checkout_and_only_prints(self):
        kind = b"ssh-ed25519"
        blob = len(kind).to_bytes(4, "big") + kind + (32).to_bytes(4, "big") + bytes(range(32))
        key = kind.decode() + " " + base64.b64encode(blob).decode() + " public-test"
        proc = subprocess.run([str(self.checkout / "bin/lab-wal-receiver-key")], input=key,
                              text=True, capture_output=True, cwd=ROOT, env=self.env, check=True)
        match = re.match(r'command="((?:\\.|[^"\\])*)",', proc.stdout)
        self.assertIsNotNone(match)
        command = re.sub(r"\\(.)", r"\1", match[1])
        self.assertEqual(shlex.split(command), [str(self.checkout / "bin/lab-wal-receive")])
        for option in ("no-port-forwarding", "no-X11-forwarding", "no-agent-forwarding", "no-pty"):
            self.assertIn(option, proc.stdout)
        self.assertTrue(proc.stdout.endswith(key + "\n"))
        self.assertFalse((self.checkout / "archive").exists())

    def test_systemd_unit_printer_resolves_template(self):
        (self.checkout / "etc/lab.local.env").write_text("HOST_ARCHIVE_USER=archive-test\n")
        proc = subprocess.run([str(self.checkout / "bin/lab-consumer-unit")], cwd=ROOT, env=self.env,
                              text=True, capture_output=True, check=True)
        self.assertIn('User=archive-test\n', proc.stdout)
        self.assertIn('WorkingDirectory=' + str(self.checkout) + '\n', proc.stdout)
        self.assertIn(str(self.checkout / "bin/lab-consumer").replace("$", "$$"), proc.stdout)
        self.assertNotIn("@LAB_", proc.stdout)
        self.assertNotIn("EnvironmentFile=", proc.stdout)


if __name__ == "__main__":
    unittest.main()
