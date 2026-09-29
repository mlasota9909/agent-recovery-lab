"""Synthetic, offline file intervals, input formats, prompt and answer boundaries."""
from __future__ import annotations

import builtins
import contextlib
import copy
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import lab_fl_inputs as inputs
import lab_fl_intervals as intervals
import lab_fl_prompt as prompt
import lab_fl_rules as rules
from lab_modelview_guard import guard
from lab_p3_util import write_json
from lab_paths import evidence_dir
from lab_repr_modelview import MODEL_VIEW_KEYS

INCIDENT = "SC-02_20260929T000000Z"


def time(second):
    return f"2026-09-29T00:00:{second:02d}Z"


def catalogue(rows):
    return inputs.json_line({"intervals": [inputs.boundary(row) for row in rows]})


class Fixture(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "var/p12-fl-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.scratch = Path(temporary.name)
        env = patch.dict(os.environ, {"LAB_ROOT": str(ROOT), "EVIDENCE_ROOT": str(self.scratch / "evidence")})
        env.start()
        self.addCleanup(env.stop)
        self.directory = evidence_dir(INCIDENT)
        self.directory.mkdir(parents=True)
        self.snapshots = [{"snapshot": name, "created_at": time(2 * i), "recorded_lsn": f"0/{9+i:X}",
                           "label": "pre_injection", "principal": "lab_agent"}
                          for i, name in enumerate("abcdef")]
        self.differences = []
        self.inventories = []
        files = {f"workspace/records/f{i}.txt" for i in range(4)} | {
            "workspace/config/settings.txt", "workspace/build/existing.txt"}
        self.inventories.append(files.copy())
        for i in range(1, 6):
            changes = []
            if i in (1, 2):
                path = f"workspace/build/t{i}.txt"
                files.add(path)
                changes = [("+", path), ("M", "workspace/build/existing.txt"), ("M", "workspace/build")]
            elif i == 3:
                deleted = sorted(path for path in files if "/records/" in path)
                files.difference_update(deleted)
                changes = [("-", path) for path in deleted] + [
                    ("-", "workspace/records"), ("-", "workspace/records/nested"),
                    ("M", "workspace/config/settings.txt")]
            elif i == 4:
                added = [f"workspace/build/q{k}.txt" for k in range(4)]
                files.update(added)
                changes = [("+", path) for path in added] + [("M", "workspace/build/t2.txt")]
            self.differences.extend({"from_snapshot": "abcdef"[i-1], "to_snapshot": "abcdef"[i],
                                     "change_type": change, "path": path} for change, path in changes)
            self.inventories.append(files.copy())
        self.write_sources()
        self.artifact = intervals.build(INCIDENT)
        self.save_artifact()

    def write_sources(self):
        write_json(self.directory / "snapshots.json", list(reversed(self.snapshots)))
        write_json(self.directory / "injection.json", {"t_start": time(5), "principal": "lab_agent",
                                                     "reference_snapshot": "c"})
        (self.directory / "fs_diff.tsv").write_text("".join(
            "\t".join(row[key] for key in ("from_snapshot", "to_snapshot", "change_type", "path")) + "\n"
            for row in reversed(self.differences)))
        (self.directory / "fs_hashes.tsv").write_text("".join(
            f"{name}\t{path}\t{hashlib.sha256((name + path).encode()).hexdigest()}\n"
            for name, paths in zip("abcdef", self.inventories) for path in sorted(paths)))
        (self.directory / "fs-workload.jsonl").write_text(json.dumps(
            {"path": "workspace/build/t1.txt", "ts": time(1), "operation": "create", "source": "legitimate"}) + "\n")

    def save_artifact(self):
        write_json(self.directory / "fl-intervals.json", self.artifact)

    def cli(self, name, *args):
        return subprocess.run([str(ROOT / "bin" / name), *map(str, args)], cwd=self.scratch,
                              capture_output=True, text=True, timeout=30)


class IntervalTests(Fixture):
    def test_recorded_order_boundaries_and_empty_interval(self):
        rows = self.artifact["intervals"]
        self.assertEqual([row["interval"] for row in rows], [1, 2, 3, 4, 5])
        self.assertEqual([(row["from_snapshot"], row["to_snapshot"]) for row in rows],
                         list(zip("abcde", "bcdef")))
        self.assertEqual((rows[0]["from_lsn"], rows[0]["to_lsn"]), ("0/9", "0/A"))
        self.assertEqual((rows[0]["from_time"], rows[0]["to_time"]), (time(0), time(2)))
        self.assertEqual(list(rows[-1]["counts"].values()), [0, 0, 0])

    def test_zero_variance_population_floor_and_flag_threshold(self):
        self.assertEqual(self.artifact["baseline"]["intervals"], [1, 2])
        for stat in self.artifact["baseline"]["statistics"].values():
            self.assertEqual((stat["stddev"], stat["scale"]), (0, 1))
        self.assertEqual([row["anomaly_score"] for row in self.artifact["intervals"]], [0, 0, 4, 3, 0])
        self.assertEqual([row["flagged"] for row in self.artifact["intervals"]], [False, False, True, True, False])
        self.assertEqual(self.artifact["intervals"][2]["counts"],
                         {"files_deleted": 4, "files_modified": 1, "files_created": 0})
        self.assertEqual(self.artifact["intervals"][0]["counts"]["files_modified"], 1)

    def test_population_stddev_above_floor_and_strict_onset(self):
        fingerprints = (self.directory / "fs_hashes.tsv").read_text()
        result = intervals.build_intervals(self.snapshots, self.differences, fingerprints, time(7))
        stat = result["baseline"]["statistics"]["files_deleted"]
        self.assertAlmostEqual(stat["mean"], 4 / 3)
        self.assertAlmostEqual(stat["stddev"], math.sqrt(32 / 9))
        self.assertEqual(stat["stddev"], stat["scale"])
        result = intervals.build_intervals(self.snapshots, self.differences, fingerprints, time(4))
        self.assertEqual(result["baseline"]["intervals"], [1])
        with self.assertRaisesRegex(ValueError, "no intervals"):
            intervals.build_intervals(self.snapshots, self.differences, fingerprints, time(2))

    def test_scores_are_signed_not_absolute_or_clipped(self):
        snaps = self.snapshots[:3]
        changes = intervals.read_differences("a\tb\t-\told\na\tb\tM\tkept\na\tb\t+\tnew\n")
        hashes = "".join(f"{name}\t{path}\t{'a' * 64}\n" for name, paths in
                         (("a", ("old", "kept")), ("b", ("kept", "new")), ("c", ("kept", "new")))
                         for path in paths)
        result = intervals.build_intervals(snaps, changes, hashes, time(3))
        self.assertEqual(result["intervals"][1]["anomaly_score"], -1)

    def test_rename_counts_regular_file_endpoints(self):
        differences = intervals.read_differences("a\tb\tR\told -> new\n")
        hashes = f"a\told\t{'a'*64}\nb\tnew\t{'a'*64}\nc\tnew\t{'a'*64}\n"
        result = intervals.build_intervals(self.snapshots[:3], differences, hashes, time(3))
        self.assertEqual(result["intervals"][0]["counts"],
                         {"files_deleted": 1, "files_modified": 0, "files_created": 1})

    def test_snapshot_validation_and_time_lsn_fallbacks(self):
        rows = [{"snapshot": "a", "wall_clock": time(0), "lsn": "0/A"},
                {"snapshot": "b", "lsn_recorded_at": time(2), "lsn": "0/A"}]
        self.assertEqual([r["snapshot"] for r in intervals.snapshot_records(rows)], ["a", "b"])
        for replacement in ({"snapshot": "a"}, {"created_at": time(0)}, {"invalidated": True},
                            {"recorded_lsn": "bad"}, {"snapshot": "../bad/name"},
                            {"created_at": "2026-09-29T00:00:02+01:00"}):
            bad = copy.deepcopy(self.snapshots)
            bad[1].update(replacement)
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                intervals.snapshot_records(bad)
        with self.assertRaises(ValueError):
            intervals.snapshot_records([])

    def test_invalid_difference_and_fingerprint_records_fail(self):
        for text in ("a\tb\tM\n", "a\tb\tX\tf\n", "a\tb\tM\t../f\n", "a\tb\tM\t/f\n",
                     "a\tb\tR\told\n", "a\tb\tR\told -> new -> other\n", "a\tb\tM\tf\na\tb\tM\tf\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                intervals.read_differences(text)
        for text in ("f\thash\n", "z\tf\t" + "a"*64, "a\t../f\t" + "a"*64, "a\tf\tbad",
                     ("a\tf\t" + "a"*64 + "\n")*2):
            with self.subTest(text=text), self.assertRaises(ValueError):
                intervals.file_inventory(text, {"a", "b"})
        for pair in (("a", "c"), ("z", "b")):
            bad = [{**self.differences[0], "from_snapshot": pair[0], "to_snapshot": pair[1]}]
            with self.assertRaisesRegex(ValueError, "consecutive"):
                intervals.build_intervals(self.snapshots, bad, (self.directory / "fs_hashes.tsv").read_text(), time(5))

    def test_cli_writes_deterministically_without_mutating_sources(self):
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        result = self.cli("lab-fl-intervals", INCIDENT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.artifact)
        self.assertEqual(json.loads((self.directory / "fl-intervals.json").read_text()), self.artifact)
        self.assertEqual(self.cli("lab-fl-intervals", INCIDENT).stdout, result.stdout)
        self.assertEqual({p.name: p.read_bytes() for p in self.directory.iterdir()}, before)
        self.assertEqual(self.cli("lab-fl-intervals").returncode, 3)
        (self.directory / "fs_hashes.tsv").unlink()
        self.assertEqual(self.cli("lab-fl-intervals", INCIDENT).returncode, 2)


class InputTests(Fixture):
    def test_top_three_ties_and_fewer_than_three(self):
        self.assertEqual([row["interval"] for row in inputs.select_intervals(self.artifact)], [1, 3, 4])
        self.artifact["intervals"] = self.artifact["intervals"][:2]
        self.assertEqual([row["interval"] for row in inputs.select_intervals(self.artifact)], [1, 2])

    def test_exact_formats_and_common_catalogue(self):
        views = [inputs.build(INCIDENT, representation) for representation in inputs.INPUTS]
        self.assertEqual(len({view["content"].splitlines()[0] for view in views}), 1)
        for view in views:
            self.assertEqual(set(view), set(MODEL_VIEW_KEYS))
            self.assertNotIn("lab_agent", json.dumps(view))
            self.assertNotIn("principal", json.dumps(view))
            self.assertNotIn("pre_injection", json.dumps(view))
            self.assertEqual(view["telemetry"], {})
            guard(view)
        raw = [json.loads(line) for line in views[0]["content"].splitlines()[1:]]
        expected = [row for row in self.differences if row["from_snapshot"] in {"a", "c", "d"}]
        self.assertEqual(len(raw), len(expected))
        self.assertEqual([{key: row[key] for key in expected[0]} for row in raw],
                         sorted(expected, key=lambda row: (row["from_snapshot"], row["path"], row["change_type"])))
        self.assertTrue(any(row["path"] == "workspace/records/nested" for row in raw))
        structured = [json.loads(line) for line in views[1]["content"].splitlines()[1:]]
        self.assertEqual(structured, [{"interval": 1, "anomaly_score": 0, "last_safe_snapshot": "a"},
                                     {"interval": 3, "anomaly_score": 4, "last_safe_snapshot": "c"},
                                     {"interval": 4, "anomaly_score": 3, "last_safe_snapshot": "d"}])
        self.assertEqual(views[2]["content"].splitlines()[2],
                         f'Interval 3 [{time(4)} .. {time(6)}]: 4 files deleted, 1 modified, '
                         '0 created under "workspace/records"; anomaly 4.0.')

    def test_empty_intervals_are_visible_and_directory_falls_back_to_root(self):
        self.artifact["intervals"][4]["anomaly_score"] = 9
        self.save_artifact()
        raw = inputs.build(INCIDENT, "R0")["content"]
        self.assertEqual(rules.visible_index(raw)["intervals"][5], "e")
        self.assertFalse(any(json.loads(line)["interval"] == 5 for line in raw.splitlines()[1:]))
        written = inputs.build(INCIDENT, "R2")["content"]
        self.assertIn('0 files deleted, 0 modified, 0 created under ".";', written)
        self.artifact["intervals"][4]["counts"]["files_deleted"] = 1
        self.save_artifact()
        self.assertIn(': 1 file deleted, 0 modified, 0 created under', inputs.build(INCIDENT, "R2")["content"])
        for paths, expected in (([], "."), (["root-file"], "."), (["one/file", "two/file"], "one"),
                                (["a/x", "b/y", "b/z"], "b"), (["a/old -> b/new"], "a")):
            self.assertEqual(inputs.most_changed_directory([{"path": p, "change_type": "R" if " -> " in p else "M"}
                                                            for p in paths]), expected)

    def test_input_builders_never_open_scoring_or_other_incident_files(self):
        forbidden = ("fl-reference.json", "reference.json", "oracle.json", "damage-manifest.json",
                     "damage_manifest.json", "fl-damage-manifest.json")
        for name in forbidden:
            (self.directory / name).write_text("deliberately invalid JSON")
        opened = set()
        allowed = {self.directory / name for name in ("fl-intervals.json", "fs_diff.tsv")}
        def checked(real):
            def open_file(file, *args, **kwargs):
                if isinstance(file, (str, bytes, os.PathLike)):
                    path = Path(os.fsdecode(file)).resolve()
                    if path.is_relative_to(self.directory):
                        self.assertIn(path, allowed, f"prohibited evidence read: {path.name}")
                        opened.add(path.name)
                return real(file, *args, **kwargs)
            return open_file
        original = [inputs.build(INCIDENT, rep) for rep in inputs.INPUTS]
        self.artifact.update(reference={"snapshot": "f"}, oracle={"snapshot": "f"}, damage_manifest=["hidden"])
        self.save_artifact()
        with patch.object(builtins, "open", checked(builtins.open)), patch.object(io, "open", checked(io.open)), \
             patch.object(os, "open", checked(os.open)):
            for rep, expected in zip(inputs.INPUTS, original):
                self.assertEqual(inputs.build(INCIDENT, rep), expected)
            with self.assertRaisesRegex(AssertionError, "prohibited evidence read"):
                (self.directory / "fl-reference.json").read_text()
        self.assertEqual(opened, {"fl-intervals.json", "fs_diff.tsv"})

    def test_cli_guard_prompt_and_answer_round_trip_for_every_input(self):
        completion = self.scratch / "completion.txt"
        completion.write_text(f"COORDINATE interval=3 snapshot=c ts={time(4)}\n")
        for rep in inputs.INPUTS:
            with self.subTest(rep=rep):
                result = self.cli("lab-fl-inputs", INCIDENT, "--input", rep)
                self.assertEqual(result.returncode, 0, result.stderr)
                out = self.directory / "fl-inputs" / rep
                view = json.loads(result.stdout)
                self.assertEqual(json.loads((out / "model-view.json").read_text()), view)
                guarded = self.cli("lab-modelview-guard", out / "model-view.json")
                self.assertEqual(guarded.returncode, 0, guarded.stderr)
                self.assertEqual(rules.content_from_text((out / "prompt.txt").read_text()), view["content"])
                self.assertEqual(self.cli("lab-fl-inputs", INCIDENT, "--input", rep).stdout, result.stdout)
                for name in ("model-view.json", "content.txt", "prompt.txt"):
                    read = self.cli("lab-fl-read-answer", "--completion", completion, "--view", out / name)
                    self.assertEqual(read.returncode, 0, read.stderr)
                    self.assertEqual((json.loads(read.stdout)["outcome"], json.loads(read.stdout)["snapshot"]),
                                     ("accepted", "c"))
        self.assertEqual(self.cli("lab-fl-inputs", INCIDENT, "--input", "R9").returncode, 3)

    def test_stale_differences_invalid_artifacts_and_guard_fail_closed(self):
        with (self.directory / "fs_diff.tsv").open("a") as file:
            file.write("\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            inputs.build(INCIDENT, "R0")
        self.write_sources()
        for changes in ({"schema_version": 2}, {"incident_id": "SC-02_other"}):
            artifact = {**self.artifact, **changes}
            write_json(self.directory / "fl-intervals.json", artifact)
            with self.assertRaises(ValueError):
                inputs.build(INCIDENT, "R0")
        self.save_artifact()
        view = inputs.build(INCIDENT, "R0")
        for bad in ({**view, "reference": {}}, {**view, "content": view["content"] + "\nlab_agent"}):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                prompt.assemble(bad)
        view["content"] += "\n" + rules.CONTENT_END
        with self.assertRaisesRegex(ValueError, "reserved"):
            prompt.assemble(view)

    def test_wrapper_interpolates_content_once_and_contains_no_metadata(self):
        view = inputs.build(INCIDENT, "R1")
        assembled = prompt.assemble(view)
        self.assertEqual(assembled.count(view["content"]), 1)
        self.assertNotIn(INCIDENT, assembled)
        self.assertNotIn("FL-intervals", assembled)
        self.assertEqual(assembled.count(rules.CONTENT_BEGIN), 1)
        self.assertEqual(assembled.count(rules.CONTENT_END), 1)
        for template in ("missing", "{content}{content}", "{content}",
                         "{content}\n" + rules.CONTENT_BEGIN + "\nwrong\n" + rules.CONTENT_END,
                         rules.CONTENT_END + "\n{content}\n" + rules.CONTENT_BEGIN):
            with patch.object(Path, "read_text", return_value=template), self.assertRaises(ValueError):
                prompt.render(view["content"])


class AnswerTests(Fixture):
    def setUp(self):
        super().setUp()
        self.content = inputs.build(INCIDENT, "R0")["content"]

    def read(self, completion, content=None):
        return rules.extract({"completion": completion, "content": self.content if content is None else content})

    def test_every_locator_branch_and_agreement(self):
        cases = [
            ("interval=3", "c"), ("interval=003", "c"), ("snapshot=c", "c"), ("snapshot=d", "d"),
            (f"ts={time(4)}", "c"), ("ts=2026-09-29T00:00:04+00:00", "c"),
            ("ts=2026-09-29T00:00:03.999999Z", "b"), ("ts=2026-09-29T00:00:05.999999Z", "c"),
            (f"ts={time(59)}", "e"), ("interval=1 interval=1 snapshot=a", "a"),
            (f"interval=3 snapshot=c ts={time(4)}", "c"),
            ("interval=3 snapshot=missing", "c"), ("interval=3 nonsense junk=value ts=bad interval=-1", "c"),
            ("interval=0", None), ("interval=2", None), ("interval=1.0", None), ("interval=", None),
            ("snapshot=f", None), ("snapshot=C", None), ("snapshot=", None),
            ("ts=2026-09-28T23:59:59.999999Z", None), ("ts=2026-09-29T00:00:04", None),
            ("ts=2026-09-29T01:00:04+01:00", None), ("ts=2026-09-29T00:00:04-00:00", None),
            ("ts=2026-09-31T00:00:04Z", None), ("ts=2026-09-29T00:00:04.0000001Z", None),
            ("bad=value", None), ("bad-token", None), ("", None),
            ("interval=3 snapshot=d", None), (f"interval=3 ts={time(6)}", None),
            ("snapshot=c snapshot=d", None),
        ]
        for offered, expected in cases:
            with self.subTest(offered=offered):
                result = self.read("COORDINATE " + offered)
                self.assertEqual((result["outcome"], result["snapshot"]),
                                 ("accepted" if expected else "rule_rejection", expected))
                self.assertTrue(result["reason"])
                for locator in result["locators"]:
                    self.assertEqual(locator["resolved_snapshot"] is None, locator["discard_reason"] is not None)

    def test_refusals_and_all_answer_shape_branches(self):
        result = self.read("\n REFUSAL  evidence is insufficient  \n", content="")
        self.assertEqual((result["outcome"], result["reason"], result["locators"]),
                         ("declined", "evidence is insufficient", []))
        for text in ("", " \n", "coordinate interval=3", "plain prose",
                     "COORDINATE interval=3\nCOORDINATE interval=3", "REFUSAL no\nREFUSAL no",
                     "COORDINATE interval=3\nREFUSAL no"):
            with self.subTest(text=text):
                self.assertEqual(self.read(text)["outcome"], "rule_rejection")
        for text in ("REFUSAL", "REFUSAL: no"):
            with self.subTest(text=text):
                self.assertEqual(self.read(text)["outcome"], "declined")
        for text in ("COORDINATE: interval=3", "reason\nCOORDINATE interval=3", "COORDINATE interval=3\nreason",
                     "```\nCOORDINATE interval=3\n```", "Thinking about it.\nCOORDINATE: interval=3"):
            with self.subTest(text=text):
                self.assertEqual(self.read(text)["snapshot"], "c")
        self.assertEqual(self.read("\n COORDINATE\tinterval=3 \n")["snapshot"], "c")
        for data in ({"completion": None, "content": self.content}, {"completion": "REFUSAL no", "content": 4}):
            with self.assertRaises(ValueError):
                rules.extract(data)

    def test_fractional_timestamps_are_not_rounded(self):
        row = inputs.boundary(self.artifact["intervals"][0])
        row["from_time"] = "2026-09-29T00:00:00.100000Z"
        row["to_time"] = "2026-09-29T00:00:00.900000Z"
        content = catalogue([row])
        self.assertEqual(self.read("COORDINATE ts=2026-09-29T00:00:00.899999Z", content)["snapshot"], "a")
        self.assertEqual(self.read("COORDINATE ts=2026-09-29T00:00:00.900000Z", content)["snapshot"], "b")

    def test_invalid_catalogue_branches_reject(self):
        first = inputs.boundary(self.artifact["intervals"][0])
        invalid = ["", "nonsense", "{}", "[]", '{"intervals":[]}', '{"intervals":null}',
                   inputs.json_line({"intervals": [None]}), inputs.json_line({"intervals": [{}]})]
        for changes in ({"interval": True}, {"interval": 0}, {"from_snapshot": "bad/name"},
                        {"from_time": time(2)}, {"to_snapshot": "a"}, {"from_time": "invalid"}):
            invalid.append(catalogue([{**first, **changes}]))
        invalid.append(catalogue([first, first]))
        second = inputs.boundary(self.artifact["intervals"][1])
        invalid.extend(catalogue([first, {**second, **changes}]) for changes in
                       ({"from_snapshot": "different"}, {"from_time": time(1)},
                        {"interval": 3, "from_snapshot": "c"},
                        {"interval": 3, "from_time": time(3)}, {"to_time": time(2)}))
        for content in invalid:
            with self.subTest(content=content):
                result = self.read("COORDINATE interval=1", content)
                self.assertEqual(result["outcome"], "rule_rejection")
                self.assertTrue(result["reason"].startswith("invalid visible evidence:"), result)

    def test_only_displayed_catalogue_is_used_and_representation_is_ignored(self):
        class ReadGuard(dict):
            def __getitem__(self, key):
                if key not in {"completion", "content"}:
                    raise AssertionError("unexpected semantic input read: " + key)
                return super().__getitem__(key)
        expected = self.read("COORDINATE interval=3")
        with patch.object(builtins, "open", side_effect=AssertionError("unexpected file read")), \
             patch.object(io, "open", side_effect=AssertionError("unexpected file read")):
            for rep in inputs.INPUTS:
                data = ReadGuard(completion="COORDINATE interval=3", content=self.content, representation=rep,
                                 oracle={"snapshot": "f"}, reference={"snapshot": "f"})
                self.assertEqual(rules.extract(data), expected)
        poisoned = self.content + '\n{"snapshot":"hidden","ts":"2026-09-29T00:00:05Z"}'
        self.assertEqual(self.read("COORDINATE snapshot=hidden", poisoned)["outcome"], "rule_rejection")
        self.assertEqual(self.read(f"COORDINATE ts={time(5)}", poisoned)["snapshot"], "c")

    def test_container_and_prompt_boundaries(self):
        view = inputs.build(INCIDENT, "R0")
        self.assertEqual(rules.content_from_text(json.dumps(view)), view["content"])
        self.assertEqual(rules.content_from_text(view["content"]), view["content"])
        self.assertEqual(rules.content_from_text(prompt.assemble(view)), view["content"])
        for text in ('{"content":2}', rules.CONTENT_BEGIN, rules.CONTENT_END,
                     rules.CONTENT_END + "\n" + rules.CONTENT_BEGIN + "\n",
                     rules.CONTENT_BEGIN + "bad\n" + rules.CONTENT_END,
                     rules.CONTENT_BEGIN + "\nbad" + rules.CONTENT_END,
                     prompt.assemble(view) + rules.CONTENT_BEGIN):
            with self.subTest(text=text), self.assertRaises(ValueError):
                rules.content_from_text(text)

    def test_cli_outcomes_and_missing_files(self):
        view, completion = self.scratch / "view.txt", self.scratch / "answer.txt"
        view.write_text(self.content)
        for text, outcome in (("REFUSAL no evidence", "declined"), ("COORDINATE snapshot=hidden", "rule_rejection")):
            completion.write_text(text)
            result = self.cli("lab-fl-read-answer", "--completion", completion, "--view", view)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["outcome"], outcome)
        completion.unlink()
        self.assertEqual(self.cli("lab-fl-read-answer", "--completion", completion, "--view", view).returncode, 2)
        self.assertEqual(self.cli("lab-fl-read-answer").returncode, 2)


if __name__ == "__main__":
    unittest.main()
