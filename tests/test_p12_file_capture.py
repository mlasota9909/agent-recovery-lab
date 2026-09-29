"""Offline snapshot, file capture, file workload and C-7 regression checks."""
from __future__ import annotations

import contextlib
import io
import hashlib
import json
import multiprocessing
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import lab_capture as capture
import lab_file_evidence as evidence
import lab_fs_capture as fs
import lab_generate_p7 as p7
import lab_generate_sc01 as sc01
import lab_snapshot_loop as loop
import lab_snapshot_tick as tick
from lab_fs_reconcile import reconcile_file_operations
from lab_incident_runtime import incident_runtime
from lab_ledger_account import fs_coverage
from lab_paths import evidence_dir
from lab_validate import parse_hash_lines

INCIDENT = "SC-02_20260929T000000Z"


def snap(name, seconds, lsn):
    ts = f"2026-09-29T00:00:{seconds:02d}.000000Z"
    return {"snapshot": name, "created_at": ts, "recorded_lsn": lsn, "label": "loop"}


def op(path, action, seconds):
    return {"path": path, "operation": action, "ts": f"2026-09-29T00:00:{seconds:02d}.000000Z"}


def diff(path, change, a="a", b="b"):
    return {"from_snapshot": a, "to_snapshot": b, "path": path, "change_type": change}


def result(code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


REAL_RUN = subprocess.run


def refuse_lab_commands(args, *rest, **kwargs):
    """Tests run against the real checkout path, so never let a lab or VM command through."""
    argv = [str(a) for a in (args if isinstance(args, (list, tuple)) else [args])]
    first = argv[0] if argv else ""
    if first == "ssh" or any(first.startswith(str(ROOT / d)) for d in ("bin", "provision", "run")):
        raise AssertionError("test attempted a lab command: " + " ".join(argv)[:200])
    return REAL_RUN(args, *rest, **kwargs)


class ScratchTest(unittest.TestCase):
    def setUp(self):
        guard = patch.object(subprocess, "run", side_effect=refuse_lab_commands)
        guard.start()
        self.addCleanup(guard.stop)
        scratch = ROOT / "var/p12-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env_patch = patch.dict(os.environ, {
            "LAB_ROOT": str(ROOT), "ARCHIVE_ROOT": str(self.root / "archive"),
            "EVIDENCE_ROOT": str(self.root / "evidence"), "SNAP_PREFIX": "s_",
        })
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.ed = evidence_dir(INCIDENT)
        self.ed.mkdir(parents=True)

    def manifest(self, incident=INCIDENT):
        rows = [snap("a", 0, "0/9"), snap("b", 2, "0/10"), snap("c", 4, "0/11")]
        tick.save_array(tick.ledger_path(incident), [rows[2], rows[0], rows[1]])
        return rows


class SnapshotTests(ScratchTest):
    def test_label_cli_usage_errors_keep_exit_three(self):
        for argv in ([], ["--label", "bad/label"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit) as exc:
                tick.main(argv)
            self.assertEqual(exc.exception.code, 3)

    def test_concurrent_writers_reserve_unique_names_and_preserve_all_records(self):
        fixed = datetime(2026, 9, 29, tzinfo=timezone.utc)

        class FrozenDatetime:
            @staticmethod
            def now(_tz):
                return fixed

        with patch.object(tick, "datetime", FrozenDatetime), \
             patch.object(tick, "incident_runtime", return_value={"SNAP_PREFIX": "s_"}), \
             patch.object(tick, "zfs_snapshot"), \
             patch.object(tick, "capture_lsn", return_value=("0/10", fixed.isoformat(), "0/20")):
            ctx = multiprocessing.get_context("fork")
            processes = [ctx.Process(target=tick.append_anchored_snapshot, args=(INCIDENT,),
                                     kwargs={"label": "open" if i == 0 else "loop"}) for i in range(12)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(10)
                self.assertFalse(process.is_alive())
                self.assertEqual(process.exitcode, 0)
        rows = tick.load_array(tick.ledger_path(INCIDENT))
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({r["snapshot"] for r in rows}), 12)
        self.assertEqual([r["sequence"] for r in rows], list(range(1, 13)))
        self.assertTrue(all(r["snapshot"].startswith("s_20260929T000000000Z_") for r in rows))
        self.assertEqual(rows, tick.load_array(self.ed / "snapshots.json"))

    def test_snapshot_precedes_lsn_and_wal_anchor(self):
        order = []
        with patch.object(tick, "incident_runtime", return_value={"SNAP_PREFIX": "s_"}), \
             patch.object(tick, "zfs_snapshot", side_effect=lambda *a: order.append("snapshot")), \
             patch.object(tick, "capture_lsn", side_effect=lambda *a: (order.append("anchor") or
                                                                        ("0/10", tick.utc_now(), "0/20"))):
            row = tick.append_anchored_snapshot(INCIDENT, label="pre_injection")
        self.assertEqual(order, ["snapshot", "anchor"])
        self.assertEqual(row["wal_switch_lsn"], "0/20")
        self.assertEqual(row["operations"], ["zfs_snapshot", "pg_current_wal_lsn", "pg_switch_wal"])
        self.assertEqual(row["label"], "pre_injection")

    def test_failed_snapshot_does_not_record_and_does_not_reuse_sequence(self):
        with patch.object(tick, "incident_runtime", return_value={"SNAP_PREFIX": "s_"}), \
             patch.object(tick, "zfs_snapshot", side_effect=RuntimeError("snapshot failed")):
            with self.assertRaisesRegex(RuntimeError, "snapshot failed"):
                tick.append_anchored_snapshot(INCIDENT)
        self.assertEqual(tick.load_array(tick.ledger_path(INCIDENT)), [])
        with patch.object(tick, "incident_runtime", return_value={"SNAP_PREFIX": "s_"}), \
             patch.object(tick, "zfs_snapshot"):
            row = tick.append_anchored_snapshot(INCIDENT, "0/10")
        self.assertEqual(row["sequence"], 2)

    def test_merge_keeps_legacy_loop_records_and_labels_without_duplicates(self):
        self.manifest()
        tick.save_array(self.ed / "snapshots.json", [
            {"snapshot": "legacy-loop", "wall_clock": "2026-09-29T00:00:01.000000Z", "lsn": "0/A"},
            {"snapshot": "b", "wall_clock": "old", "lsn": "0/10", "retained": True},
        ])
        p7.copy_snapshots(INCIDENT)
        p7.copy_snapshots(INCIDENT)
        rows = tick.load_array(self.ed / "snapshots.json")
        self.assertEqual([r["snapshot"] for r in rows], ["a", "legacy-loop", "b", "c"])
        self.assertTrue(rows[2]["retained"])
        self.assertEqual(rows[2]["label"], "loop")


class CaptureTests(ScratchTest):
    def test_all_pairs_and_hashes_in_numeric_lsn_order(self):
        self.manifest()
        calls = []
        def run(name, args, **kw):
            calls.append((name, args))
            return result()
        evidence.capture_file_evidence(INCIDENT, [], runner=run)
        expected = [["diff", "a", "b"], ["diff", "b", "c"],
                    ["hash", "a"], ["hash", "b"], ["hash", "c"]]
        self.assertEqual(calls, [("lab-fs-capture", args + ["--incident", INCIDENT]) for args in expected])

    def test_diff_and_hash_errors_stop_capture_with_original_message(self):
        self.manifest()
        for failing in ("diff", "hash"):
            calls = []
            def run(name, args, **kw):
                calls.append(args)
                return result(7, stderr="capture failed exactly") if args[0] == failing else result()
            with self.subTest(failing=failing), contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as exc:
                    evidence.capture_file_evidence(INCIDENT, [], runner=run)
                self.assertEqual(exc.exception.code, 7)
                self.assertEqual(err.getvalue().strip(), "capture failed exactly")
                self.assertEqual(calls[-1][0], failing)
        self.assertFalse((self.ed / "fs_diff.tsv").exists())
        self.assertFalse((self.ed / "fs_hashes.tsv").exists())

    def test_p7_generator_freeze_fails_before_accounting_on_capture_error(self):
        self.manifest()
        with patch.object(capture, "stop_snapshot_loop") as stop, \
             patch.object(p7, "run_bin", return_value=result(1, stderr="diff failure")) as run, \
             patch.object(p7, "run_json") as account, contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit):
                p7.freeze_common(INCIDENT, "SC-02", {}, [], {}, {}, {}, 6, "", {}, {})
        stop.assert_called_once_with(INCIDENT, check=True)
        account.assert_not_called()
        self.assertEqual(run.call_args.args[1], ["diff", "a", "b", "--incident", INCIDENT])
        self.assertIn("diff failure", err.getvalue())

    def test_sc01_generator_fails_before_accounting_and_cleans_up_loop(self):
        incident = INCIDENT.replace("SC-02", "SC-01")
        self.manifest(incident)
        ed = evidence_dir(incident)
        ed.mkdir(parents=True)
        (ed / "injection_log.json").write_text(json.dumps({"ops": [], "commit_lsn": "0/10"}))
        app = Mock()
        app.stop.return_value = []
        def run_json(name, args, **kwargs):
            if name == "lab-incident":
                return {"incident": incident}
            if name == "lab-snapshot":
                return snap("a", 0, "0/10")
            if name == "lab-inject-sc01":
                return {}
            self.fail("unexpected generator stage after capture failure: " + name)
        def run(name, args, **kwargs):
            return result(1, stderr="hash or diff failure") if name == "lab-fs-capture" else result()
        with contextlib.ExitStack() as stack:
            for name, value in (("require_lab", None), ("scenario_config", {}), ("ensure_sc01_seed", {"count": 500}),
                                ("ssh_psql", result()), ("ConcurrentApp", app), ("apply_group", []),
                                ("plan_sc01_ddl", [])):
                stack.enter_context(patch.object(sc01, name, return_value=value))
            stack.enter_context(patch("lab_incident_runtime.stop_finished_incident_clusters", return_value=[]))
            stack.enter_context(patch.object(sc01.time, "sleep"))
            stack.enter_context(patch.object(sc01, "run_bin", side_effect=run))
            stack.enter_context(patch.object(sc01, "run_json", side_effect=run_json))
            stop = stack.enter_context(patch.object(capture, "stop_snapshot_loop"))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            with self.assertRaises(SystemExit):
                sc01.generate([])
            self.assertTrue(any(call.kwargs.get("check") for call in stop.call_args_list))
            self.assertEqual(stop.call_args_list[-1], unittest.mock.call(incident))

    def test_capture_uses_explicit_incident_dataset_and_relative_paths(self):
        runtime = {"DS_PROTECTED": "pool/right/protected", "MNT_PROTECTED": "/right/protected"}
        with patch.object(fs, "incident_runtime", return_value=runtime) as selected, \
             patch.object(fs, "ssh", return_value=result(stdout="M\t/right/protected/a.txt\n")) as ssh, \
             contextlib.redirect_stdout(io.StringIO()):
            fs.cmd_diff(INCIDENT, "a", "b")
        selected.assert_called_once_with(INCIDENT)
        self.assertIn("pool/right/protected@a", ssh.call_args.args[0])
        self.assertEqual((self.ed / "fs_diff.tsv").read_text(), "a\tb\tM\ta.txt\n")

    def test_hash_uses_explicit_mount_and_produces_real_three_column_format(self):
        runtime = {"MNT_PROTECTED": "/right/protected", "VM_SSH": "selected"}
        digest = "a" * 64
        with patch.object(fs, "incident_runtime", return_value=runtime), \
             patch.object(fs.subprocess, "run", return_value=result(stdout=f"dir/file.txt\t{digest}\n")) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            fs.cmd_hash(INCIDENT, "snap_1")
        self.assertIn("/right/protected/.zfs/snapshot/snap_1", run.call_args.kwargs["input"])
        text = (self.ed / "fs_hashes.tsv").read_text()
        self.assertEqual(text, f"snap_1\tdir/file.txt\t{digest}\n")
        self.assertEqual(parse_hash_lines(text, "snap_1"), [("dir/file.txt", digest)])
        self.assertEqual(parse_hash_lines(text, "other"), [])
        with self.assertRaises(ValueError):
            parse_hash_lines(text)

    def test_capture_failure_writes_no_placeholder(self):
        with patch.object(fs, "incident_runtime", return_value={"DS_PROTECTED": "right"}), \
             patch.object(fs, "ssh", return_value=result(1, stderr="cannot diff")), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                fs.cmd_diff(INCIDENT, "a", "b")
        self.assertFalse((self.ed / "fs_diff.tsv").exists())

    def test_hash_capture_on_synthetic_files_runs_real_hasher_and_parser(self):
        mount = self.root / "protected"
        tree = mount / ".zfs/snapshot/s_test"
        (tree / "nested").mkdir(parents=True)
        (tree / "nested/file.txt").write_bytes(b"synthetic content\n")
        runtime = {"MNT_PROTECTED": str(mount), "VM_SSH": "unused"}
        local_run = subprocess.run
        def local_hash(args, **kwargs):
            self.assertEqual(args[0], "ssh")
            return local_run(["bash", "-s"], input=kwargs["input"], text=True, capture_output=True)
        with patch.object(fs, "incident_runtime", return_value=runtime), \
             patch.object(fs.subprocess, "run", side_effect=local_hash), \
             contextlib.redirect_stdout(io.StringIO()):
            fs.cmd_hash(INCIDENT, "s_test")
        self.assertEqual(parse_hash_lines((self.ed / "fs_hashes.tsv").read_text(), "s_test"),
                         [("nested/file.txt", hashlib.sha256(b"synthetic content\n").hexdigest())])

    def test_explicit_runtime_overrides_both_active_incident_and_current(self):
        checkout = self.root / "checkout"
        (checkout / "etc").mkdir(parents=True)
        (checkout / "lib").mkdir()
        (checkout / "runtime/incidents").mkdir(parents=True)
        shutil.copy(ROOT / "etc/lab.env", checkout / "etc/lab.env")
        shutil.copy(ROOT / "lib/lab_incident_env.sh", checkout / "lib/lab_incident_env.sh")
        values = {"ARCHIVE_INCIDENT": INCIDENT, "INC_ID": "i_requested",
                  "INC_DS": "pool/requested", "INC_PGDATA": "/requested/pgdata",
                  "INC_PROTECTED": "/requested/protected", "INC_PG_PORT": "5555",
                  "INC_PG_SOCKET": "/run/postgresql", "INC_SLOT": "requested_slot", "INC_HEARTBEAT_PORT": "5555"}
        (checkout / "runtime/incidents/i_requested.env").write_text(
            "".join(f"{key}={value}\n" for key, value in values.items()))
        with patch.dict(os.environ, {"LAB_ROOT": str(checkout), "LAB_ACTIVE_INCIDENT": "SC-03_wrong",
                                     "INC_DS": "pool/wrong", "DS_PROTECTED": "pool/wrong/protected",
                                     "MNT_PROTECTED": "/wrong", "ARCHIVE_CURRENT": str(self.root / "wrong-current")}):
            runtime = incident_runtime(INCIDENT)
            self.assertEqual(runtime["DS_PROTECTED"], "pool/requested/protected")
            self.assertEqual(runtime["MNT_PROTECTED"], "/requested/protected")
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                incident_runtime("SC-03_missing")


class ReconcileTests(ScratchTest):
    def setUp(self):
        super().setUp()
        self.snaps = [snap("a", 0, "0/9"), snap("b", 2, "0/10"), snap("c", 4, "0/11")]

    def check(self, ops, diffs, declared=True):
        return reconcile_file_operations(self.snaps, ops, diffs, declared=declared)

    def test_exact_visible_and_invisible_counts(self):
        ops = [op("build/new", "create", 1), op("build/new", "append", 1),
               op("build/temp", "create", 1), op("build/temp", "delete", 1),
               op("config/file", "overwrite", 3), op("records/file", "delete", 3)]
        diffs = [diff("build/new", "+"), diff("build", "M"),
                 diff("config/file", "M", "b", "c"), diff("records/file", "-", "b", "c"),
                 diff("records", "M", "b", "c")]
        report = self.check(ops, diffs)
        self.assertTrue(report["ok"], report)
        self.assertEqual((report["matched"], report["invisible"]), (4, 2))
        self.assertEqual((report["unmatched_recorded"], report["unexplained_captured"]), (0, 0))

    def test_unexplained_difference_fails_even_with_a_match(self):
        report = self.check([op("f", "append", 1)], [diff("f", "M"), diff("unknown", "-")])
        self.assertFalse(report["ok"])
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["unexplained_captured"], 1)

    def test_path_substring_wrong_type_wrong_interval_and_duplicates_fail(self):
        for differences in ([diff("f-longer", "M")], [diff("f", "+")],
                            [diff("f", "M", "b", "c")], [diff("f", "M", "a", "c")],
                            [diff("f", "M"), diff("f", "M")]):
            with self.subTest(differences=differences):
                report = self.check([op("f", "append", 1)], differences)
                self.assertFalse(report["ok"])
                self.assertGreater(report["unexplained_captured"], 0)

    def test_empty_or_only_invisible_declared_activity_fails(self):
        self.assertFalse(self.check([], [])["ok"])
        report = self.check([op("f", "create", 1), op("f", "delete", 1)], [])
        self.assertFalse(report["ok"])
        self.assertEqual(report["invisible"], 2)
        self.assertTrue(self.check([], [], declared=False)["ok"])

    def test_create_and_delete_across_intervals_are_both_visible(self):
        report = self.check([op("f", "create", 1), op("f", "delete", 3)],
                            [diff("f", "+"), diff("f", "-", "b", "c")])
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["matched"], 2)

    def test_deleted_directory_and_children_are_exact_targets(self):
        report = self.check([op("records/f", "delete", 1), op("records/nested", "delete", 1),
                             op("records", "delete", 1)],
                            [diff("records/f", "-"), diff("records/nested", "-"),
                             diff("records", "-"), diff(".", "M")])
        self.assertTrue(report["ok"], report)
        report = self.check([op("records/f", "delete", 1)], [diff("records/f", "-"), diff("other", "M")])
        self.assertFalse(report["ok"])

    def test_unbracketed_and_invalid_records_fail(self):
        for item in (op("f", "create", 0), op("f", "create", 5), op("../f", "create", 1),
                     op("/f", "append", 1), op("f", "churn", 1), {"path": "f"}):
            with self.subTest(item=item):
                self.assertEqual(self.check([item], [])["unmatched_recorded"], 1)

    def test_c7_reads_separate_file_ledger_and_refuses_missing_sc02_activity(self):
        tick.save_array(self.ed / "snapshots.json", self.snaps)
        (self.ed / "fs_diff.tsv").write_text("a\tb\tM\tf\n")
        (self.ed / "fs-workload.jsonl").write_text(json.dumps(op("f", "append", 1)) + "\n")
        self.assertTrue(fs_coverage(INCIDENT, [{"action": "I"}])["ok"])
        (self.ed / "fs-workload.jsonl").unlink()
        self.assertFalse(fs_coverage(INCIDENT)["ok"])

    def test_two_column_probe_formats_are_preserved(self):
        digest = "ab" * 32
        self.assertEqual(parse_hash_lines(f"file\t{digest}\n{digest}\tother\n{digest}  third\n"),
                         [("file", digest), ("other", digest), ("third", digest)])


class LoopTests(ScratchTest):
    def test_default_interval_and_invalid_configuration(self):
        with patch.dict(os.environ, {"SNAP_INTERVAL_S": ""}):
            self.assertEqual(loop.interval_s(), 2)
        for value in ("0", "-1", "nan", "inf"):
            with patch.dict(os.environ, {"SNAP_INTERVAL_S": value}), self.assertRaises(ValueError):
                loop.interval_s()

    def test_failed_loop_persists_error_and_generator_stop_refuses_it(self):
        with patch.object(loop, "take_snapshot_tick", side_effect=RuntimeError("tick failed")), \
             patch.object(loop.signal, "signal"), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(loop.run_loop(INCIDENT), 1)
        self.assertEqual(loop.read_status(INCIDENT)["error"], "tick failed")
        self.assertFalse(loop.pid_file(INCIDENT).exists())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            capture.stop_snapshot_loop(INCIDENT, check=True)

    def test_one_period_of_lateness_is_allowed_but_larger_gap_fails(self):
        loop.check_gap(4, 2)
        with self.assertRaisesRegex(RuntimeError, "missed an interval"):
            loop.check_gap(4.001, 2)

    def test_tick_latency_violation_is_recorded_as_failure(self):
        with patch.object(loop, "take_snapshot_tick", return_value=snap("a", 0, "0/10")), \
             patch.object(loop.signal, "signal"), \
             patch.object(loop.time, "monotonic", side_effect=[0.0, 4.01]), \
             patch.dict(os.environ, {"SNAP_INTERVAL_S": "2"}), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(loop.run_loop(INCIDENT), 1)
        self.assertIn("missed an interval", loop.read_status(INCIDENT)["error"])

    def test_missing_completion_is_fatal(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            capture.stop_snapshot_loop(INCIDENT, check=True)

    def test_healthy_stop_must_cover_baseline_through_post_capture(self):
        status = {"state": "stopped", "ok": True, "ticks": 3,
                  "first_snapshot_at": "2026-09-29T00:00:01Z", "stopped_at": "2026-09-29T00:00:09Z"}
        loop.write_status(INCIDENT, status)
        capture.stop_snapshot_loop(INCIDENT, check=True, required_from="2026-09-29T00:00:02Z",
                                   required_until="2026-09-29T00:00:08Z")
        for kwargs in ({"required_from": "2026-09-29T00:00:00Z"},
                       {"required_until": "2026-09-29T00:00:10Z"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SystemExit), \
                 contextlib.redirect_stderr(io.StringIO()):
                capture.stop_snapshot_loop(INCIDENT, check=True, **kwargs)

    def run_with_durations(self, durations):
        from datetime import datetime, timedelta, timezone
        clock = [0.0]
        ticks = []
        handlers = {}
        def take(_incident):
            ticks.append(clock[0])
            created = datetime(2026, 9, 29, tzinfo=timezone.utc) + timedelta(seconds=clock[0])
            row = {"snapshot": str(len(ticks)), "created_at": created.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                   "recorded_lsn": "0/10", "label": "loop"}
            clock[0] += durations[len(ticks) - 1]
            if len(ticks) == len(durations):
                handlers[loop.signal.SIGTERM](None, None)
            return row
        def sleep(seconds):
            clock[0] += seconds
        with patch.object(loop, "take_snapshot_tick", side_effect=take), \
             patch.object(loop.signal, "signal", side_effect=lambda sig, fn: handlers.update({sig: fn})), \
             patch.object(loop.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(loop.time, "sleep", side_effect=sleep), \
             patch.dict(os.environ, {"SNAP_INTERVAL_S": "2"}), contextlib.redirect_stderr(io.StringIO()):
            return loop.run_loop(INCIDENT), [round(t, 3) for t in ticks]

    def test_late_tick_moves_the_schedule_without_carrying_lag(self):
        code, ticks = self.run_with_durations([1.6, 3.0, 1.6, 1.6])
        self.assertEqual(code, 0)
        self.assertEqual(ticks, [0, 2, 5, 7])

    def test_many_slightly_slow_ticks_do_not_accumulate_into_a_failure(self):
        code, ticks = self.run_with_durations([2.3] * 40)
        self.assertEqual(code, 0)
        self.assertEqual(loop.read_status(INCIDENT)["ticks"], 40)
        self.assertLessEqual(loop.read_status(INCIDENT)["max_gap_s"], 2.3 + 1e-9)

    def test_loop_keeps_fixed_cadence_and_records_successful_stop(self):
        clock = [0.0]
        ticks = []
        handlers = {}
        def take(_incident):
            ticks.append(clock[0])
            row = snap(str(len(ticks)), round(clock[0]), "0/10")
            clock[0] += 0.25
            if len(ticks) == 3:
                handlers[loop.signal.SIGTERM](None, None)
            return row
        def sleep(seconds):
            clock[0] += seconds
        with patch.object(loop, "take_snapshot_tick", side_effect=take), \
             patch.object(loop.signal, "signal", side_effect=lambda sig, fn: handlers.update({sig: fn})), \
             patch.object(loop.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(loop.time, "sleep", side_effect=sleep), \
             patch.dict(os.environ, {"SNAP_INTERVAL_S": "2"}):
            self.assertEqual(loop.run_loop(INCIDENT), 0)
        self.assertEqual(ticks, [0, 2, 4])
        self.assertEqual(loop.read_status(INCIDENT)["ticks"], 3)
        self.assertTrue(loop.read_status(INCIDENT)["ok"])
        self.assertFalse(loop.pid_file(INCIDENT).exists())


class WorkloadTests(ScratchTest):
    def scenario(self):
        with patch.dict(os.environ, {"INC_PROTECTED": str(self.root / "protected")}):
            import lab_sc02
        return lab_sc02

    def test_reference_enumeration_includes_files_empty_directories_and_overwrite(self):
        module = self.scenario()
        root = self.root / "reference"
        (root / "workspace/records/nested").mkdir(parents=True)
        (root / "workspace/config").mkdir()
        for i in range(1, 13):
            (root / f"workspace/records/f{i}.txt").write_text("seed")
        (root / "workspace/config/settings.txt").write_text("original")
        def local_python(command, **kw):
            args = shlex.split(command)
            self.assertEqual(args[:3], ["sudo", "-n", "python3"])
            return subprocess.run([sys.executable, *args[3:]], capture_output=True, text=True)
        with patch.object(module, "ssh", side_effect=local_python):
            rows = module.enumerate_damage_targets(str(root))
        self.assertEqual(len(rows), 15)
        self.assertEqual(sum(row["kind"] == "directory" for row in rows), 2)
        self.assertEqual(sum(row["operation"] == "overwrite" for row in rows), 1)
        self.assertEqual(sum(row["operation"] == "delete" for row in rows), 14)

    def test_churn_records_each_intended_path_separately_without_touching_database_ledger(self):
        module = self.scenario()
        churn = module._FileChurn(INCIDENT)
        calls = []
        def remote(command, **kw):
            calls.append(command)
            if len(calls) == 4:
                churn.stop_event.set()
            return result()
        with patch.object(module, "ssh", side_effect=remote), \
             patch.dict(os.environ, {"OS_USER_APP": "app"}), \
             patch.object(churn.stop_event, "wait"):
            churn._run()
        rows = [json.loads(line) for line in (self.ed / "fs-workload.jsonl").read_text().splitlines()]
        self.assertEqual([row["operation"] for row in rows],
                         ["create", "create", "append", "create", "append", "create", "append", "delete"])
        self.assertTrue(all(row["ts"].endswith("Z") and row["path"].startswith("workspace/build/") for row in rows))
        self.assertEqual(rows[-1]["path"], "workspace/build/t0.txt")
        self.assertFalse((self.ed / "workload.jsonl").exists())
        self.assertIsNone(churn.error)

    def test_failed_churn_command_is_not_silently_accepted(self):
        module = self.scenario()
        churn = module._FileChurn(INCIDENT)
        with patch.object(module, "ssh", return_value=result(1, stderr="write failed")), \
             patch.dict(os.environ, {"OS_USER_APP": "app"}):
            churn._run()
        self.assertIn("write failed", churn.error)


class ExpectedFingerprintTests(unittest.TestCase):
    def test_expected_state_is_the_reference_snapshot_not_the_restore_snapshot(self):
        import tempfile
        from lab_validate import expected_fingerprints
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp)
            (ev / "oracle.json").write_text(json.dumps({"coordinate": {"snapshot": "s_ref"}}))
            (ev / "fs_hashes.tsv").write_text(
                "s_ref\tconfig/a.txt\t" + "a" * 64 + "\n"
                "s_late\tconfig/a.txt\t" + "b" * 64 + "\n")
            snapshot, rows = expected_fingerprints(ev)
            self.assertEqual(snapshot, "s_ref")
            self.assertEqual(rows, [("config/a.txt", "a" * 64)])



if __name__ == "__main__":
    unittest.main()
