"""Offline run-through state, gating and statistical accounting regressions."""
from __future__ import annotations

from contextlib import ExitStack
import copy
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import lab_fl_analysis as analysis
import lab_fl_study as study
import lab_p9 as p9
import lab_run as run
import lab_run_common as common
import lab_sc01_replication as sc01
from lab_fl_check import COUNT_KEYS
from test_p12_fl_scoring import Fixture, INCIDENT


class Scratch(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "var/p12-run-tests"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"LAB_ROOT": str(self.root),
                                                       "RESULTS_ROOT": str(self.root / "results"),
                                                       "EVIDENCE_ROOT": str(self.root / "evidence"),
                                                       "ARCHIVE_ROOT": str(self.root / "archive"),
                                                       "ARCHIVE_CURRENT": str(self.root / "archive/current")}))
        self.stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("external connection")))
        self.stack.enter_context(patch.object(subprocess, "run", side_effect=AssertionError("external process")))
        self.model = {"slot": "M1", "alias": "fixture-model", "model_digest": "a" * 64}
        self.frozen = {"sha256": "b" * 64, "frozen_utc": "2026-01-01T00:00:00Z"}
        self.prompt = self.root / "prompt.txt"
        self.prompt.write_text("fixture prompt")
        self.directory = self.root / "unit"
        self.calls = []

    def invoke(self, name, *args, **kwargs):
        self.calls.append((name, args))
        if name != "bin/lab-p9-model":
            raise AssertionError("unexpected command: " + name)
        common.save(args[-1], {"completion": "COORDINATE: snapshot=safe", "model_alias": self.model["alias"],
                              "containment_verified": True, "prompt": self.prompt.read_text(),
                              "model_digest": self.model["model_digest"], "prompt_sha256": common.sha(self.prompt),
                              **common.DECODING})
        return subprocess.CompletedProcess([], 0, "", "")

    def collect(self, **kwargs):
        defaults = {"verify": lambda: self.frozen,
                    "reader": lambda *args: {"outcome": "accepted", "snapshot": "safe"},
                    "checker": lambda answer: {"checks_complete": True, "verdict_v2": "correct",
                                               "summary": dict.fromkeys(COUNT_KEYS, 0)},
                    "prompt_path": self.prompt}
        defaults.update(kwargs)
        with patch.object(study, "command", side_effect=self.invoke):
            return study.collect_unit(INCIDENT, self.frozen, self.model, "R0", 0, self.directory, **defaults)


class CollectionTests(Scratch):
    def test_completed_journal_replays_without_a_second_call(self):
        first = self.collect()
        self.assertEqual(first["outcome"], "accepted")
        self.assertEqual(first, self.collect())
        self.assertEqual(len(self.calls), 1)
        self.assertGreater(first["call_started_utc"], self.frozen["frozen_utc"])

    def test_interrupted_call_is_accounted_without_replacement(self):
        self.collect()
        (self.directory / "finished.json").unlink()
        (self.directory / "model.json").unlink()
        resumed = self.collect()
        self.assertEqual(resumed["outcome"], "execution_failure")
        self.assertIn("no replacement", resumed["failure_reason"])
        self.assertEqual(len(self.calls), 1)

    def test_interrupted_processing_reads_the_retained_reply(self):
        self.collect()
        (self.directory / "finished.json").unlink()
        resumed = self.collect()
        self.assertEqual(resumed["outcome"], "accepted")
        self.assertEqual(len(self.calls), 1)

    def test_rejections_and_declines_never_restore(self):
        for outcome in ("rule_rejection", "declined"):
            self.directory = self.root / outcome
            row = self.collect(reader=lambda *a: {"outcome": outcome, "snapshot": None},
                               checker=lambda *a: self.fail("unaccepted answer restored"))
            self.assertEqual(row["outcome"], outcome)
            self.assertIsNone(row["check"])

    def test_restore_precondition_failure_preserves_acceptance_and_nulls(self):
        def fail(answer):
            raise ValueError("restore unavailable")
        row = self.collect(checker=fail)
        self.assertEqual(row["outcome"], "accepted")
        self.assertFalse(row["check"]["checks_complete"])
        self.assertTrue(all(v is None for v in row["check"]["summary"].values()))

    def test_transport_and_containment_failures_are_not_refusals(self):
        def fail(*args, **kwargs):
            raise RuntimeError("transport failure")
        self.invoke = fail
        row = self.collect()
        self.assertEqual(row["outcome"], "execution_failure")
        self.directory = self.root / "unsafe"
        def unsafe(name, *args, **kwargs):
            Scratch.invoke(self, name, *args, **kwargs)
            reply = common.read(args[-1])
            reply["containment_verified"] = False
            common.save(args[-1], reply)
        self.invoke = unsafe
        self.assertEqual(self.collect()["outcome"], "execution_failure")

    def test_interrupted_restore_is_not_repeated(self):
        common.save(self.directory / "check-started.json", {"snapshot": "safe"})
        with patch.object(study, "command", side_effect=AssertionError("repeated restore")):
            report = study.check_point(INCIDENT, "safe", self.directory)
        self.assertFalse(report["checks_complete"])

    def test_stale_report_refusal_does_not_import_old_verdict(self):
        report_path = common.evidence_dir(INCIDENT) / "fl-checks/safe.json"
        common.save(report_path, {"schema_version": 2, "incident_id": INCIDENT,
                                  "coordinate": {"snapshot": "safe"}, "verdict_v2": "correct"})
        with patch.object(study, "command", return_value=subprocess.CompletedProcess([], 2, "", "stale cache")):
            report = study.check_point(INCIDENT, "safe", self.directory)
        self.assertFalse(report["checks_complete"])

    def test_partial_and_duplicate_result_records_fail_closed(self):
        path = self.root / "results.jsonl"
        path.write_text('{"partial":')
        with self.assertRaisesRegex(ValueError, "partial final"):
            common.load_rows(path)
        row = self.collect()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            common.indexed([row, row], {row["unit_id"]}, INCIDENT, self.frozen["sha256"])

    def test_named_database_reader_applies_revised_visible_rules(self):
        prompt = '<<<ARM_B_CONTENT\n{"lsn_int":42}\nARM_B_CONTENT>>>'
        self.assertEqual(sc01.database_answer("COORDINATE: lsn=42", prompt)["outcome"], "accepted")
        self.assertEqual(sc01.database_answer("COORDINATE: lsn=43", prompt)["outcome"], "rule_rejection")
        self.assertEqual(sc01.database_answer("REFUSAL: uncertain", prompt)["outcome"], "declined")
        structured = '{"window_index":3,"last_safe_lsn_int":42,"anomaly_score":5}'
        self.assertEqual(sc01.database_answer("COORDINATE: lsn=42", structured)["outcome"], "accepted")
        self.assertEqual(sc01.database_answer("COORDINATE: lsn=43", structured)["outcome"], "rule_rejection")
        self.assertEqual(sc01.database_answer("COORDINATE: window=3", structured)["outcome"], "rule_rejection")


class GateTests(Fixture):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("external connection")))
        self.stack.enter_context(patch.object(subprocess, "run", side_effect=AssertionError("external process")))
        rows = [{"step": "fs_capture", "exit": 0, "args": ["diff", a["snapshot"], b["snapshot"], "--incident", INCIDENT]}
                for a, b in zip(self.snapshots, self.snapshots[1:])]
        rows.extend({"step": "fs_capture", "exit": 0, "args": ["hash", s["snapshot"], "--incident", INCIDENT]}
                    for s in self.snapshots)
        for row in rows:
            args = row["args"]
            count = len(self.inventories[int(args[1][2:])]) if args[0] == "hash" else sum(
                d["from_snapshot"] == args[1] and d["to_snapshot"] == args[2] for d in self.differences)
            row["stdout"] = json.dumps({"ok": True, "rows": count})
        common.save(self.directory / "generate-commands.json", rows)

    def test_complete_capture_passes_both_C7_levels(self):
        report = run.capture_gate(INCIDENT)
        self.assertGreater(report["pure_C7"]["matched"], 0)
        self.assertEqual(report["pure_C7"], report["ledger_C7"])

    def test_missing_capture_invocation_and_missing_target_fail(self):
        path = self.directory / "generate-commands.json"
        rows = common.read(path)
        common.save(path, rows[:-1])
        with self.assertRaisesRegex(ValueError, "incomplete capture"):
            run.capture_gate(INCIDENT)
        common.save(path, rows)
        self.differences = [d for d in self.differences if d["path"] != "sc02-work/victim/f12.txt"]
        self.write_sources()
        with self.assertRaisesRegex(ValueError, "C-7"):
            run.capture_gate(INCIDENT)


class AnalysisTests(Scratch):
    def row(self, rep, k, outcome="accepted", verdict="correct"):
        return {"unit_id": f"fixture-model|{rep}|{k}", "outcome": outcome,
                "check": {"checks_complete": True, "verdict_v2": verdict,
                          "summary": dict.fromkeys(COUNT_KEYS, None if verdict == "not_recovered" else 0)}
                if outcome == "accepted" else None}

    def test_denominators_missing_pending_and_null_measurements(self):
        rows = [self.row("R0", 0), self.row("R0", 1, verdict="not_recovered"),
                self.row("R0", 2, outcome="execution_failure"), self.row("R0", 3)]
        rows[-1]["check"] = {"checks_complete": False}
        cells, losses, units = analysis.descriptive({r["unit_id"]: r for r in rows}, [self.model])
        cell = cells[0]
        self.assertEqual((cell["planned"], cell["accepted"], cell["execution_failure"], cell["missing"], cell["pending_checks"]),
                         (5, 3, 1, 1, 1))
        self.assertEqual(cell["correct_given_accepted"], 1 / 3)
        self.assertEqual(cell["correct_rate"], 1 / 5)
        self.assertEqual(losses[0]["n_measured"], 1)
        self.assertIsNone(losses[len(COUNT_KEYS)]["sum"])
        self.assertEqual(units[4]["outcome"], "missing")

    def test_no_variation_and_incomplete_block_statistics(self):
        records = {r["unit_id"]: r for rep in common.REPS for k in range(5) for r in [self.row(rep, k)]}
        q, pairs, effects = analysis.exploratory(records, [self.model])
        self.assertEqual((q[0]["Q"], q[0]["p"], q[0]["blocks"]), (0, 1, 5))
        self.assertTrue(all(p["p_holm"] == 1 for p in pairs))
        self.assertEqual((effects[0]["point"], effects[0]["ci_low"], effects[0]["ci_high"]), (0, 0, 0))
        records["fixture-model|R1|0"]["outcome"] = "execution_failure"
        del records["fixture-model|R0|1"]
        q, pairs, effects = analysis.exploratory(records, [self.model])
        self.assertEqual((q[0]["blocks"], q[0]["excluded_blocks"]), (3, 2))
        self.assertEqual(effects[0]["n_blocks"], 4)

    def test_empty_tests_are_null_and_effect_direction_is_R2_minus_R0(self):
        q, pairs, effects = analysis.exploratory({}, [self.model])
        self.assertIsNone(q[0]["Q"])
        self.assertTrue(all(p["p_holm"] is None for p in pairs))
        self.assertIsNone(effects[0]["point"])
        records = {r["unit_id"]: r for rep in common.REPS for k in range(5)
                   for r in [self.row(rep, k, "declined" if rep == "R0" else "accepted")]}
        _, pairs, effects = analysis.exploratory(records, [self.model])
        self.assertEqual(effects[0]["point"], 1)
        self.assertTrue(effects[0]["ci_lower_exceeds_zero"])
        self.assertEqual(effects[0]["delta"], 1)
        self.assertEqual(pairs[0]["p"], 0.0625)


class BoundaryTests(Scratch):
    def test_open_incident_refused_and_completed_or_provisioning_scope_allowed(self):
        archive = self.root / "archive"
        target = archive / INCIDENT
        target.mkdir(parents=True)
        (archive / "current").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "already open"):
            run.ensure_no_open_incident()
        common.save(self.root / "var/provision/baseline.json", {"incident": INCIDENT})
        run.ensure_no_open_incident()
        (self.root / "var/provision/baseline.json").unlink()
        common.save(common.evidence_dir(INCIDENT) / "incident.json", {
            "archive_incident": INCIDENT, "close_coordinate": {"lsn": "0/10"}, "ledger_integrity_ok": True})
        run.ensure_no_open_incident()

    def test_backend_digest_never_substitutes_another_served_model(self):
        response = io.BytesIO(json.dumps({"data": [{"id": "different", "root": "root", "max_model_len": 99}]}).encode())
        with patch.object(p9, "_urlopen", return_value=response):
            self.assertFalse(p9.backend_served_digest("http://fixture.invalid/v1", "requested")["ok"])

    def test_freeze_requires_exact_list_and_unchanged_bytes(self):
        from lab_fl_freeze import SPEC, CONTRACTS
        files = {f"contract:{name}": self.root / SPEC / "contracts" / name for name in CONTRACTS}
        files.update({"design:spec": self.root / SPEC / "spec.md", "design:plan": self.root / SPEC / "plan.md",
                      "models": self.root / "runtime/p9-model-set.json"})
        for rep in common.REPS:
            for name in ("model-view.json", "content.txt", "prompt.txt"):
                files[f"input:{rep}/{name}"] = common.evidence_dir(INCIDENT) / "fl-inputs" / rep / name
        for path in files.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("frozen fixture")
        document = {"incident_id": INCIDENT, "frozen_utc": self.frozen["frozen_utc"], "decoding": common.DECODING,
                    "planned_units": 45, "files": {key: {"path": str(path.relative_to(self.root)), "sha256": common.sha(path)}
                                                   for key, path in files.items()}}
        common.save(common.freeze_path(), document)
        self.assertEqual(common.verify_freeze(INCIDENT)["planned_units"], 45)
        with self.assertRaisesRegex(ValueError, "another incident"):
            common.verify_freeze("SC-02_other")
        changed = copy.deepcopy(document)
        del changed["files"]["models"]
        common.save(common.freeze_path(), changed)
        with self.assertRaisesRegex(ValueError, "incomplete file list"):
            common.verify_freeze(INCIDENT)
        common.save(common.freeze_path(), document)
        files["models"].write_text("changed")
        with self.assertRaisesRegex(ValueError, "frozen bytes changed"):
            common.verify_freeze(INCIDENT)


class SimulatedRunTests(Scratch):
    def test_45_units_comparators_resume_and_final_tables_without_external_processes(self):
        models = [{"slot": f"M{i}", "alias": f"fixture-{i}", "model_digest": str(i) * 64} for i in (1, 2, 3)]
        self.frozen.update(incident_id=INCIDENT, decoding=common.DECODING)
        common.save(self.root / "runtime/p9-model-set.json", {"models": models})
        directory = common.evidence_dir(INCIDENT)
        catalogue = {"intervals": [{"interval": 1, "from_snapshot": "safe", "to_snapshot": "later",
                                    "from_time": "2026-01-01T00:00:00Z", "to_time": "2026-01-01T00:00:02Z"}]}
        for rep in common.REPS:
            prompt = directory / "fl-inputs" / rep / "prompt.txt"
            prompt.parent.mkdir(parents=True)
            prompt.write_text(json.dumps(catalogue))
        model_calls = []
        def fake(name, *args, **kwargs):
            if name == "bin/lab-p9-model":
                alias, prompt, target = args[1], Path(args[3]), args[5]
                model_calls.append(alias)
                rep = prompt.parent.name
                completion = {"R0": "COORDINATE: snapshot=safe", "R1": "REFUSAL: uncertain", "R2": "untagged"}[rep]
                common.save(target, {"model_alias": alias, "model_digest": next(m["model_digest"] for m in models if m["alias"] == alias),
                                     "prompt": prompt.read_text(), "prompt_sha256": common.sha(prompt), "completion": completion,
                                     "containment_verified": True, **common.DECODING})
                return subprocess.CompletedProcess([], 0, "", "")
            if name == "bin/lab-fl-check":
                report = {"schema_version": 2, "incident_id": INCIDENT, "coordinate": {"snapshot": args[1]},
                          "verdict_v2": "correct", "summary": dict.fromkeys(COUNT_KEYS, 0)}
                common.save(directory / "fl-checks" / (args[1] + ".json"), report)
                return subprocess.CompletedProcess([], 0, json.dumps(report), "")
            if name in ("bin/lab-fl-rank", "bin/lab-fl-naive"):
                return subprocess.CompletedProcess([], 0, json.dumps({"outcome": "accepted", "coordinate": {"snapshot": "safe"}}), "")
            self.fail("unexpected command: " + name)
        with patch.object(run, "require_gate"), patch.object(study, "verify_freeze", return_value=self.frozen), \
                patch.object(study, "model_registry", return_value={"models": models}), \
                patch.object(study, "command", side_effect=fake), patch("sys.stdout", new=io.StringIO()):
            study.study(INCIDENT)
            study.study(INCIDENT)
            study.comparators(INCIDENT)
            study.comparators(INCIDENT)
        self.assertEqual(len(model_calls), 45)
        self.assertEqual(len(common.load_rows(common.result_path("fl-study-runs.jsonl"))), 45)
        self.assertEqual(len(common.load_rows(common.result_path("fl-comparators.jsonl"))), 2)
        with patch.object(analysis, "verify_freeze", return_value=self.frozen), patch("sys.stdout", new=io.StringIO()):
            report = analysis.analyse()
        self.assertTrue(report["complete"])
        self.assertEqual(report["totals"]["accepted"], 15)
        self.assertEqual(report["totals"]["rule_rejection"], 15)
        self.assertEqual(report["totals"]["declined"], 15)
        self.assertEqual(report["totals"]["correct"], 15)
        self.assertTrue((self.root / "analysis-out/fl/cells.csv").exists())
        self.assertTrue((self.root / "analysis-out/fl/exploratory-effects.md").exists())


class ExplicitSnapshotTests(unittest.TestCase):
    def test_named_manifest_wins_over_current_without_guest_queries(self):
        parent = ROOT / "var/p12-run-tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            checkout = Path(temporary)
            for name in ("bin/lab-coordinate", "etc/lab.env", "lib/lab_incident_env.sh", "lib/lab_env_overrides.sh"):
                target = checkout / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            # --snapshot reads host records only; an accidental guest query is fatal.
            fake_bin = checkout / "fake-bin"
            fake_bin.mkdir()
            ssh = fake_bin / "ssh"
            ssh.write_text('#!/usr/bin/env bash\nexit 97\n')
            ssh.chmod(0o755)
            incident = "SC-01_named"
            archive = checkout / "archive"
            for name, lsn in ((incident, "0/A"), ("SC-01_other", "0/B")):
                common.save(archive / name / "snapshots.json", [{"incident": name, "snapshot": "selected",
                            "recorded_lsn": lsn, "created_at": "2026-01-01T00:00:00Z",
                            "lsn_recorded_at": "2026-01-01T00:00:00Z"}])
            (archive / "current").symlink_to(archive / "SC-01_other")
            env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}
            env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
            proc = subprocess.run([str(checkout / "bin/lab-coordinate"), "--incident", incident,
                                   "--snapshot", "selected"], env=env, text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["incident"], incident)
            self.assertEqual(json.loads(proc.stdout)["lsn"], "0/A")


if __name__ == "__main__":
    unittest.main()
