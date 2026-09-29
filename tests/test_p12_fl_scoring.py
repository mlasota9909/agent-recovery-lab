"""Offline reference, verdict v2, comparator, control and freeze fixtures."""
from __future__ import annotations

import builtins
from contextlib import ExitStack, nullcontext
import copy
import hashlib
import io
import json
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

import lab_fl_check as check
import lab_fl_comparators as comparators
import lab_fl_controls as controls
import lab_fl_freeze as freeze
import lab_fl_inputs as inputs
import lab_fl_intervals as intervals
import lab_fl_prompt as prompt
import lab_fl_reference as reference
import lab_fl_rules as rules
from lab_modelview_guard import guard
from lab_p3_util import write_json
from lab_paths import evidence_dir

INCIDENT = "SC-02_20260930T000000Z"
VICTIM = "sc02-work/victim"
OVERWRITE = "sc02-work/keep/will-overwrite.txt"
BUILD = "sc02-work/build/"


def ts(second):
    return f"2026-09-30T00:00:{second:09.6f}Z"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Fixture(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "var/p12-fl-scoring-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.scratch = Path(temporary.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"LAB_ROOT": str(ROOT),
                                                       "EVIDENCE_ROOT": str(self.scratch / "evidence")}))
        self.directory = evidence_dir(INCIDENT)
        self.directory.mkdir(parents=True)
        self.snapshots = [{"snapshot": f"s_{i}", "created_at": ts(i * 2), "recorded_lsn": lsn}
                          for i, lsn in enumerate(("0/9", "0/A", "0/C", "0/C", "0/D"))]
        self.operations = []
        self.differences = []
        files = {f"{VICTIM}/f{i}.txt": sha(str(i)) for i in range(1, 13)}
        files.update({OVERWRITE: sha("original"), BUILD + "old": sha("old"),
                      VICTIM + "-other/keep": sha("untouched")})
        self.inventories = [files.copy()]
        self.op(BUILD + "transient", "create", .4)
        self.op(BUILD + "transient", "delete", .6)
        self.op(BUILD + "a", "create", 1)
        self.op(BUILD + "a", "append", 1.5)
        self.diff(1, "+", BUILD + "a")
        files[BUILD + "a"] = sha("a1")
        self.inventories.append(files.copy())
        self.op(BUILD + "a", "append", 3)
        self.op(BUILD + "old", "delete", 3.3)
        self.op(BUILD + "b", "create", 4)
        self.diff(2, "M", BUILD + "a")
        self.diff(2, "-", BUILD + "old")
        self.diff(2, "+", BUILD + "b")
        files[BUILD + "a"], files[BUILD + "b"] = sha("a2"), sha("b")
        del files[BUILD + "old"]
        self.inventories.append(files.copy())
        targets = []
        for path, kind, operation in ([(f"{VICTIM}/f{i}.txt", "file", "delete") for i in range(1, 13)]
                                      + [(VICTIM + "/nested", "directory", "delete"),
                                         (VICTIM, "directory", "delete"), (OVERWRITE, "file", "overwrite")]):
            targets.append(self.op(path, operation, 5.1, source="injection", kind=kind))
            self.diff(3, "M" if operation == "overwrite" else "-", path)
            if kind == "file":
                if operation == "delete":
                    del files[path]
                else:
                    files[path] = sha("damaged")
        self.inventories.append(files.copy())
        self.op(BUILD + "late", "create", 7)
        self.diff(4, "+", BUILD + "late")
        files[BUILD + "late"] = sha("late")
        self.inventories.append(files.copy())
        self.injection = {"t_start": ts(5), "t_end": ts(5.5), "fs_ops": targets,
                          "reference_snapshot": "s_0", "relation": "p2_probe"}
        self.write_sources()
        self.artifact = intervals.build(INCIDENT)
        write_json(self.directory / "fl-intervals.json", self.artifact)
        self.ref = reference.build(INCIDENT)
        write_json(self.directory / "fl-reference.json", self.ref)
        write_json(self.directory / "incident.json", {"approx_incident_time": ts(5)})
        write_json(self.directory / "oracle.json", {"coordinate": {"snapshot": "s_0"}})
        write_json(self.directory / "oracle-manifest.json", {
            "destroyed_row_ids": [], "legitimate_row_ids": [], "optimum_lsn": "0/FF"})
        self.workload = [{"commit_lsn": "0/A", "row_count": 2}, {"commit_lsn": "0/B", "row_count": 3},
                         {"commit_lsn": "0/D", "row_count": 7}]
        (self.directory / "workload-manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in self.workload))
        # All live boundaries fail unless an individual test supplies a synthetic response.
        for name in ("restore_db", "restore_fs", "ssh_sudo", "psql", "guest_hash", "teardown_db", "teardown_fs",
                     "incident_runtime"):
            self.stack.enter_context(patch.object(check, name, side_effect=AssertionError("unexpected live operation")))

    def op(self, path, operation, time, source="legitimate", kind="file"):
        row = {"path": path, "operation": operation, "ts": ts(time), "source": source, "kind": kind}
        self.operations.append(row)
        return row

    def diff(self, interval, change, path):
        self.differences.append({"from_snapshot": f"s_{interval-1}", "to_snapshot": f"s_{interval}",
                                 "change_type": change, "path": path})

    def write_sources(self):
        write_json(self.directory / "snapshots.json", list(reversed(self.snapshots)))
        write_json(self.directory / "injection.json", self.injection)
        (self.directory / "fs-workload.jsonl").write_text("".join(json.dumps(r) + "\n" for r in self.operations))
        (self.directory / "fs_diff.tsv").write_text("".join(
            "\t".join(row[k] for k in ("from_snapshot", "to_snapshot", "change_type", "path")) + "\n"
            for row in self.differences))
        (self.directory / "fs_hashes.tsv").write_text("".join(
            f"s_{i}\t{path}\t{value}\n" for i, inv in enumerate(self.inventories) for path, value in inv.items()))

    def cli(self, name, *args):
        root = getattr(self, "command_root", ROOT)
        return subprocess.run([str(root / "bin" / name), *map(str, args)], cwd=self.scratch,
                              capture_output=True, text=True, timeout=30)

    def offline_restore(self):
        state = {}
        def db(incident, lsn, tag, log):
            return {"ok": True, "target_lsn_int": lsn, "stopped_at_target": True,
                    "restore_target": {"sandbox_port": 55432}}
        def fs(incident, snapshot, tag, log):
            mount = check.sandbox_mount(incident, tag, "protected")
            state["mount"] = mount
            state["files"] = self.inventories[int(snapshot[2:])].copy()
            return {"ok": True, "snapshot": snapshot, "mountpoint": mount, "clone_dataset": "fixture"}
        def tamper(script):
            path = self.ref["damage_manifest"][0]["path"]
            self.assertIn(state["mount"] + "/" + path, script)
            state["files"][path] = sha("tampered")
            return subprocess.CompletedProcess([], 0, "", "")
        bindings = {"runtime": lambda incident: nullcontext(), "restore_db": db, "restore_fs": fs,
                    "guest_hash": lambda path: state["files"].get(path.removeprefix(state["mount"] + "/")),
                    "psql": lambda port, sql: "1\n2" if "SELECT id" in sql else "id bigint\nv text",
                    "ssh_sudo": tamper, "teardown_fs": lambda *a: None, "teardown_db": lambda *a: None,
                    "review_dir": lambda task: self.scratch,
                    "restore_root": lambda incident, tag: self.scratch / "restore" / incident / tag}
        mocks = {}
        for name, value in bindings.items():
            mocks[name] = self.stack.enter_context(patch.object(check, name, side_effect=value))
        return mocks


class ReferenceTests(Fixture):
    def test_reference_strict_time_and_manifest_expansion(self):
        self.assertEqual(self.ref["coordinate"], {"snapshot": "s_2", "time": "2026-09-30T00:00:04Z",
                                                 "lsn": "0/C", "lsn_int": 12})
        self.assertEqual(len(self.ref["damage_manifest"]), 13)
        paths = {r["path"] for r in self.ref["damage_manifest"]}
        self.assertNotIn(VICTIM + "-other/keep", paths)
        self.assertNotIn(VICTIM + "/nested", paths)
        for row in self.ref["damage_manifest"]:
            self.assertEqual(row["sha256"], self.inventories[2][row["path"]])
            self.assertEqual(len(row["target_indices"]), 2 if row["path"].startswith(VICTIM + "/") else 1)
        self.injection["t_start"] = ts(4)
        self.write_sources()
        self.assertEqual(reference.build(INCIDENT)["coordinate"]["snapshot"], "s_1")

    def test_visible_operations_include_repeated_work_and_exclude_transients(self):
        self.assertEqual([r["visible_operations"] for r in self.ref["legitimate_intervals"]], [2, 3, 0, 1])
        first = self.ref["legitimate_intervals"][0]["operations"]
        self.assertEqual([r["visible"] for r in first], [False, False, True, True])
        self.assertEqual(self.ref["legitimate_intervals"][1]["operations"][-1]["ts"], ts(4))

    def test_directory_only_target_expands_against_reference(self):
        self.injection["fs_ops"] = [{"path": VICTIM, "kind": "directory", "operation": "delete"}]
        self.write_sources()
        self.assertEqual(len(reference.build(INCIDENT)["damage_manifest"]), 12)

    def test_bad_targets_capture_and_reconciliation_fail_closed(self):
        for target in ({"path": "../bad", "kind": "file", "operation": "delete"},
                       {"path": "absent", "kind": "file", "operation": "delete"},
                       {"path": VICTIM, "kind": "directory", "operation": "overwrite"},
                       {"path": "empty", "kind": "directory", "operation": "delete"}):
            with self.subTest(target=target):
                original = self.injection
                self.injection = {**original, "fs_ops": [target]}
                self.write_sources()
                with self.assertRaises(ValueError):
                    reference.build(INCIDENT)
                self.injection = original
        self.differences.pop(0)
        self.write_sources()
        with self.assertRaisesRegex(ValueError, "C-7"):
            reference.build(INCIDENT)
        with (self.directory / "fs_hashes.tsv").open("a") as handle:
            handle.write("s_2\tbad\tinvalid\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            reference.build(INCIDENT)

    def test_reference_is_verified_and_command_is_deterministic(self):
        result = self.cli("lab-fl-reference", INCIDENT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.ref)
        self.assertEqual(result.stdout, self.cli("lab-fl-reference", INCIDENT).stdout)
        self.assertEqual(reference.load(INCIDENT), self.ref)
        changed = copy.deepcopy(self.ref)
        changed["damage_manifest"].pop()
        write_json(self.directory / "fl-reference.json", changed)
        with self.assertRaisesRegex(ValueError, "stale"):
            reference.load(INCIDENT)
        write_json(self.directory / "fl-reference.json", self.ref)
        (self.directory / "fs-workload.jsonl").write_text("")
        with self.assertRaises(ValueError):
            reference.load(INCIDENT)


class CheckTests(Fixture):
    def test_all_verdict_branches_and_damage_precedence(self):
        base = dict.fromkeys(check.COUNT_KEYS, 0)
        self.assertEqual(check.verdict_v2(False, {}), "not_recovered")
        self.assertEqual(check.verdict_v2(True, base), "correct")
        for key in ("damage_files_retained", "damage_rows_retained", "schema_damage"):
            self.assertEqual(check.verdict_v2(True, {**base, key: 1, "legit_rows_lost": 9}), "checked_damage_remains")
        for key in ("legit_file_operations_lost", "legit_rows_lost", "schema_loss"):
            self.assertEqual(check.verdict_v2(True, {**base, key: 1}), "extra_work_lost")

    def test_files_missing_and_overwritten_are_damage_but_churn_is_operation_loss(self):
        for i, lost, damaged in ((0, 5, 0), (1, 3, 0), (2, 0, 0), (3, 0, 13), (4, 0, 13)):
            fs, counts = check.file_checks(self.ref, f"s_{i}", self.inventories[i])
            self.assertEqual((counts["legit_file_operations_lost"], counts["damage_files_retained"]), (lost, damaged))
            if i == 3:
                self.assertEqual(sum(r["kind"] == "missing" for r in fs["mismatches"]), 12)
                self.assertEqual(sum(r["kind"] == "byte_hash" for r in fs["mismatches"]), 1)

    def test_database_rows_use_reference_lsn_and_existing_column_checks(self):
        self.offline_restore()
        manifest = {"destroyed_row_ids": [1, 3], "legitimate_row_ids": [4], "optimum_lsn": "0/FF"}
        report, counts = check.database_checks(55432, 9, 12, manifest, self.workload, "p2_probe")
        self.assertEqual((counts["damage_rows_retained"], counts["legit_rows_lost"]), (1, 5))
        self.assertEqual(report["p3_analytical_legit_rows_lost"], 12)
        self.assertEqual(report["missing_legitimate_row_ids"], [4])
        for ddl, damage, loss in (("id bigint", 1, 0), ("id bigint\nv text\nextra text", 0, 1)):
            with patch.object(check, "psql", side_effect=["1\n2", ddl]):
                _, counts = check.database_checks(55432, 12, 12, manifest, self.workload, "p2_probe")
                self.assertEqual((counts["schema_damage"], counts["schema_loss"]), (damage, loss))
        with self.assertRaisesRegex(ValueError, "LSN"):
            check.database_checks(55432, 9, 12, manifest, [{}], "p2_probe")
        with self.assertRaisesRegex(ValueError, "relation"):
            check.database_checks(55432, 9, 12, manifest, [], "bad;sql")

    def test_exact_snapshot_equal_lsn_report_reuse_and_cleanup(self):
        mocks = self.offline_restore()
        early = check.check(INCIDENT, "s_0")
        self.assertEqual(early["verdict_v2"], "extra_work_lost")
        self.assertEqual((early["summary"]["legit_file_operations_lost"], early["summary"]["legit_rows_lost"]), (5, 5))
        safe = check.check(INCIDENT, "s_2")
        late = check.check(INCIDENT, "s_3")
        self.assertEqual((safe["verdict_v2"], late["verdict_v2"]), ("correct", "checked_damage_remains"))
        calls = mocks["restore_db"].call_args_list
        self.assertEqual([call.args[1] for call in calls], [9, 12, 12])
        self.assertEqual([call.args[1] for call in mocks["restore_fs"].call_args_list], ["s_0", "s_2", "s_3"])
        self.assertNotEqual(safe["restore_of"], late["restore_of"])
        self.assertEqual(mocks["teardown_db"].call_count, 3)
        self.assertEqual(check.check(INCIDENT, "s_2"), safe)
        self.assertEqual(mocks["restore_db"].call_count, 3)
        with (self.directory / "workload-manifest.jsonl").open("a") as handle:
            handle.write("\n")
        with self.assertRaisesRegex(ValueError, "stale reuse"):
            check.check(INCIDENT, "s_2")

    def test_restore_and_validation_failures_are_stored_with_unmeasured_counts(self):
        mocks = self.offline_restore()
        mocks["restore_db"].side_effect = SystemExit(1)
        out = check.check(INCIDENT, "s_0")
        self.assertEqual(out["verdict_v2"], "not_recovered")
        self.assertTrue(all(value is None for value in out["summary"].values()))
        self.assertEqual(check.check(INCIDENT, "s_0"), out)
        self.assertEqual(mocks["restore_db"].call_count, 1)
        self.assertEqual(mocks["teardown_db"].call_count, 1)
        mocks["restore_db"].side_effect = None
        mocks["restore_db"].return_value = {"ok": True, "stopped_at_target": False}
        self.assertEqual(check.check(INCIDENT, "s_1")["verdict_v2"], "not_recovered")
        mocks["restore_db"].return_value = {"ok": True, "stopped_at_target": True, "target_lsn_int": 12,
                                           "restore_target": {"sandbox_port": 55432}}
        mocks["guest_hash"].side_effect = RuntimeError("failed read")
        self.assertEqual(check.check(INCIDENT, "s_2")["failure_reason"], "failed read")

    def test_unknown_snapshot_is_precondition_failure_without_live_access(self):
        with self.assertRaisesRegex(ValueError, "not recorded"):
            check.check(INCIDENT, "missing")
        out = self.cli("lab-fl-check", INCIDENT, "missing")
        self.assertEqual(out.returncode, 2, out.stderr)

    def test_probes_formats_containment_and_cache_digest(self):
        path, mount = self.scratch / "fs_probe.tsv", "/labpool/sandbox/fixture/protected"
        for text in (f"file\t{sha('ok')}\n", f"{sha('ok')}\tfile\n", f"{sha('ok')}  file\n",
                     f"{mount}/file\t{sha('ok')}\n"):
            path.write_text(text)
            self.assertEqual(check.read_probes(path, mount), {"file": sha("ok")})
        for text in ("invalid\n", f"../bad\t{sha('ok')}\n", f"/outside/file\t{sha('ok')}\n",
                     f"{mount}/../bad\t{sha('ok')}\n"):
            path.write_text(text)
            with self.assertRaises(ValueError):
                check.read_probes(path, mount)
        mocks = self.offline_restore()
        report = check.check(INCIDENT, "s_2")
        probe = check.restore_root(INCIDENT, report["restore_of"]) / "fs_probe.tsv"
        probe.write_text(f"file\t{sha('ok')}\n")
        with self.assertRaisesRegex(ValueError, "stale reuse"):
            check.check(INCIDENT, "s_2")
        self.assertEqual(mocks["restore_db"].call_count, 1)

    def test_remote_hash_failure_is_distinct_from_missing_file(self):
        for result, expected in ((subprocess.CompletedProcess([], 0, "MISSING\n", ""), None),
                                 (subprocess.CompletedProcess([], 0, sha("ok") + "  path\n", ""), sha("ok"))):
            with patch.object(check, "ssh_sudo", return_value=result):
                self.assertEqual(GUEST_HASH("/sandbox/a'b"), expected)
        with patch.object(check, "ssh_sudo", return_value=subprocess.CompletedProcess([], 1, "", "failed")):
            with self.assertRaises(RuntimeError):
                GUEST_HASH("/sandbox/file")

    def test_four_controls_and_tampered_probe_have_separate_cache(self):
        mocks = self.offline_restore()
        out = controls.controls(INCIDENT)
        self.assertTrue(out["ok"], out)
        self.assertEqual(len(out["controls"]), 4)
        self.assertEqual(out["controls"][-1]["summary"]["probe_mismatches"], 1)
        self.assertEqual(out["controls"][-1]["summary"]["damage_files_retained"], 1)
        self.assertEqual(check.check(INCIDENT, "s_2")["verdict_v2"], "correct")
        self.assertEqual(mocks["restore_db"].call_count, 4)
        self.assertEqual(controls.controls(INCIDENT), out)
        self.assertEqual(mocks["restore_db"].call_count, 4)

    def test_cleanup_failure_does_not_skip_database_cleanup_or_pass_control(self):
        mocks = self.offline_restore()
        mocks["teardown_fs"].side_effect = RuntimeError("cleanup failed")
        report = check.check(INCIDENT, "s_2")
        self.assertEqual(report["verdict_v2"], "correct")
        self.assertEqual(report["cleanup_error"], "cleanup failed")
        self.assertEqual(mocks["teardown_db"].call_count, 1)
        self.assertFalse(controls.controls(INCIDENT)["ok"])

    def test_controls_refuse_missing_post_snapshot_and_detect_wrong_verdict(self):
        self.offline_restore()
        with patch.object(controls, "check", return_value={"verdict_v2": "correct", "summary": {
                "probe_mismatches": 0}}):
            out = controls.controls(INCIDENT)
            self.assertFalse(out["ok"])
            self.assertEqual(sum(row["ok"] for row in out["controls"]), 1)
        self.injection["t_end"] = ts(20)
        self.write_sources()
        write_json(self.directory / "fl-reference.json", reference.build(INCIDENT))
        with self.assertRaisesRegex(ValueError, "after injection end"):
            controls.controls(INCIDENT)


GUEST_HASH = check.guest_hash


class ComparatorAndBoundaryTests(Fixture):
    def test_safe_frontier_uses_first_flag_not_largest_score(self):
        self.artifact["intervals"][3].update(anomaly_score=1000, flagged=True)
        write_json(self.directory / "fl-intervals.json", self.artifact)
        out = comparators.rank(INCIDENT)
        self.assertEqual((out["coordinate"]["snapshot"], out["first_flagged_interval"]), ("s_2", 3))
        self.assertEqual(self.cli("lab-fl-rank", INCIDENT).returncode, 0)
        for row in self.artifact["intervals"]:
            row.update(anomaly_score=0, flagged=False)
        write_json(self.directory / "fl-intervals.json", self.artifact)
        out = comparators.rank(INCIDENT)
        self.assertEqual((out["outcome"], out["coordinate"]), ("run_failure", None))
        self.assertEqual(self.cli("lab-fl-rank", INCIDENT).returncode, 1)
        with (self.directory / "snapshots.json").open("a") as handle:
            handle.write("\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            comparators.rank(INCIDENT)

    def test_time_estimate_fixed_positive_error_and_boundaries(self):
        for approx, snapshot in ((ts(5), "s_4"), ("2026-09-29T23:59:44Z", "s_2"),
                                 ("2026-09-29T23:59:40Z", "s_0"), ("2026-09-29T23:59:39Z", None)):
            write_json(self.directory / "incident.json", {"approx_incident_time": approx})
            result = comparators.naive(INCIDENT)
            self.assertEqual(result["declared_error_seconds"], 20)
            self.assertEqual(result["coordinate"]["snapshot"] if result["coordinate"] else None, snapshot)
            self.assertEqual(self.cli("lab-fl-naive", INCIDENT).returncode, 0 if snapshot else 1)
        write_json(self.directory / "incident.json", {})
        self.assertEqual(self.cli("lab-fl-naive", INCIDENT).returncode, 2)

    def test_reference_and_manifest_are_only_read_by_scoring(self):
        for name in ("damage-manifest.json", "fl-damage-manifest.json", "oracle-manifest.json"):
            (self.directory / name).write_text("not JSON")
        originals = [inputs.build(INCIDENT, rep) for rep in inputs.INPUTS]
        allowed = {"fl-intervals.json", "fs_diff.tsv", "fs_hashes.tsv", "injection.json", "snapshots.json", "incident.json"}
        opened = set()
        def guarded(real):
            def open_file(file, *args, **kwargs):
                if isinstance(file, (str, bytes, os.PathLike)):
                    path = Path(os.fsdecode(file)).resolve()
                    if path.is_relative_to(self.directory):
                        self.assertIn(path.name, allowed, "scoring-only evidence read")
                        opened.add(path.name)
                return real(file, *args, **kwargs)
            return open_file
        with patch.object(builtins, "open", guarded(builtins.open)), patch.object(io, "open", guarded(io.open)), \
             patch.object(os, "open", guarded(os.open)):
            intervals.build(INCIDENT)
            for rep, expected in zip(inputs.INPUTS, originals):
                view = inputs.build(INCIDENT, rep)
                self.assertEqual(view, expected)
                guard(view)
                reply = rules.extract({"completion": "COORDINATE interval=3", "content": view["content"]})
                self.assertEqual(reply["snapshot"], "s_2")
                prompt.assemble(view)
            comparators.rank(INCIDENT)
            comparators.naive(INCIDENT)
            with self.assertRaisesRegex(AssertionError, "scoring-only"):
                (self.directory / "fl-reference.json").read_text()
        self.assertEqual(opened, allowed)


class FreezeTests(Fixture):
    def prepare_freeze(self):
        self.checkout = self.scratch / "checkout"
        self.command_root = self.checkout
        shutil.copytree(ROOT / "lib", self.checkout / "lib", ignore=shutil.ignore_patterns("__pycache__"))
        (self.checkout / "etc").mkdir()
        shutil.copy2(ROOT / "etc/lab.env", self.checkout / "etc/lab.env")
        (self.checkout / "bin").mkdir()
        for name in ("reference", "check", "controls", "rank", "naive", "freeze"):
            shutil.copy2(ROOT / "bin" / ("lab-fl-" + name), self.checkout / "bin" / ("lab-fl-" + name))
        spec = self.checkout / freeze.SPEC
        shutil.copytree(ROOT / freeze.SPEC, spec)
        (spec / "contracts/frozen-hashes.json").unlink(missing_ok=True)
        self.stack.enter_context(patch.dict(os.environ, {"LAB_ROOT": str(self.checkout),
                                                       "RESULTS_ROOT": str(self.checkout / "results")}))
        for rep in inputs.INPUTS:
            view = inputs.build(INCIDENT, rep)
            out = self.directory / "fl-inputs" / rep
            write_json(out / "model-view.json", view)
            (out / "content.txt").write_text(view["content"] + "\n")
            (out / "prompt.txt").write_text(prompt.assemble(view))
        self.models = json.loads((ROOT / "runtime/p9-model-set.json").read_text())
        self.models.update(template=False, endpoint="http://127.0.0.1:4001")
        for i, row in enumerate(self.models["models"]):
            row.update(model_digest=sha(str(i)), tokenizer_id="tokenizer" + str(i))
        write_json(self.checkout / "runtime/p9-model-set.json", self.models)
        return spec / "contracts/frozen-hashes.json"

    def test_freeze_hashes_exact_bytes_inputs_identities_and_refuses_overwrite(self):
        destination = self.prepare_freeze()
        out = freeze.freeze(INCIDENT)
        self.assertEqual(out["planned_units"], 45)
        self.assertEqual(len(out["files"]), 17)
        self.assertEqual(json.loads(destination.read_text()), out)
        for rec in out["files"].values():
            self.assertFalse(Path(rec["path"]).is_absolute())
            self.assertEqual(hashlib.sha256((self.checkout / rec["path"]).read_bytes()).hexdigest(), rec["sha256"])
        before = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            freeze.freeze(INCIDENT)
        self.assertEqual(destination.read_bytes(), before)

    def test_freeze_refuses_prior_collection_template_and_stale_prompt(self):
        destination = self.prepare_freeze()
        runs = self.checkout / "results/fl-study-runs.jsonl"
        runs.parent.mkdir()
        runs.write_text("")
        with self.assertRaisesRegex(ValueError, "collection"):
            freeze.freeze(INCIDENT)
        self.assertFalse(destination.exists())
        runs.unlink()
        self.models["template"] = True
        write_json(self.checkout / "runtime/p9-model-set.json", self.models)
        with self.assertRaisesRegex(ValueError, "identities"):
            freeze.freeze(INCIDENT)
        self.models["template"] = False
        write_json(self.checkout / "runtime/p9-model-set.json", self.models)
        (self.directory / "fl-inputs/R0/prompt.txt").write_text("stale")
        with self.assertRaisesRegex(ValueError, "stale"):
            freeze.freeze(INCIDENT)
        self.assertFalse(destination.exists())

    def test_command_freeze_and_usage(self):
        destination = self.prepare_freeze()
        out = self.cli("lab-fl-freeze", INCIDENT)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(destination.is_file())
        self.assertEqual(self.cli("lab-fl-freeze", INCIDENT).returncode, 2)
        for name in ("reference", "check", "controls", "rank", "naive", "freeze"):
            self.assertEqual(self.cli("lab-fl-" + name).returncode, 3, name)


if __name__ == "__main__":
    unittest.main()
