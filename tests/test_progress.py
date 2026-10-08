"""Regression coverage for read-only legacy and v2 progress reporting."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import progress


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.hub = self.root / "hub"
        self.goal = self.hub / "goals" / "legacy-java"
        self.goal.mkdir(parents=True)
        (self.goal / "goal.md").write_text(
            "---\ntitle: Java 后端\nstatus: active\ndeadline: 2020-01-01\n---\n# 原始画像\n",
            encoding="utf-8")
        (self.goal / "syllabus.md").write_text(
            "# 大纲\n## 阶段一\n### [x] S1-M1 基础\n- 预计耗时：4h\n"
            "### [~] S1-M2 集合\n- 预计耗时：6h\n### [-] S1-M3 已移除\n",
            encoding="utf-8")
        (self.goal / "plan.md").write_text(
            "## 2020-01 月\n- [ ] M1: 学会集合\n"
            "### 2020-W01\n- [~] W1-1: 对比集合\n"
            "### 2020-W99\n- [ ] W99-1: 保留异常的旧标签供人工核对\n",
            encoding="utf-8")
        (self.goal / "sessions").mkdir()
        (self.goal / "sessions" / "2020-01-02.md").write_text(
            "---\ndate: 2020-01-02\ntopic: 集合\nminutes: 30\n---\n原始学习记录\n",
            encoding="utf-8")

    def snapshot(self):
        return {str(path.relative_to(self.hub)): path.read_bytes()
                for path in self.hub.rglob("*") if path.is_file()}

    def cli(self, *arguments, env=None):
        child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        if env:
            child_env.update(env)
        return subprocess.run([sys.executable, str(SCRIPTS / "progress.py"), *arguments],
                              capture_output=True, text=True, encoding="utf-8", env=child_env)

    def create_v2(self):
        commands = [
            ["init"],
            ["goal-create", "--id", "modern-java", "--title", "新版 Java"],
            ["track-create", "--goal", "modern-java", "--id", "java-core", "--title", "Java 基础"],
            ["milestone-create", "--goal", "modern-java", "--track", "java-core",
             "--title", "基础应用", "--objective", "实现基本程序", "--criterion", "能运行程序"],
            ["sprint-create", "--goal", "modern-java", "--track", "java-core", "--milestone", "M001",
             "--title", "第一个程序", "--objective", "启动应用", "--criterion", "解释启动输出"],
        ]
        for arguments in commands:
            result = self.core_cli(*arguments)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.hub / "goals" / "modern-java" / "tracks" / "java-core"

    def core_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "learning.py"), "--hub", str(self.hub), *arguments],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def test_v2_and_legacy_can_share_a_read_only_report(self):
        self.create_v2()
        before = self.snapshot()
        result = self.cli("--hub", str(self.hub), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        goals = {goal["id"]: goal for goal in json.loads(result.stdout)["goals"]}
        self.assertEqual(goals["legacy-java"]["format"], "legacy")
        modern = goals["modern-java"]
        self.assertEqual(modern["schema_version"], 2)
        self.assertFalse(modern["legacy"])
        self.assertNotIn("module_total", modern)
        self.assertEqual(modern["tracks"][0]["milestones"][0]["id"], "M001")
        self.assertEqual(modern["tracks"][0]["sprints"][0]["criteria"], ["解释启动输出"])
        self.assertEqual(self.snapshot(), before)

    def test_v2_dates_do_not_reinterpret_saved_states(self):
        self.create_v2()
        before = self.snapshot()
        results = []
        for date in ("2026-10-08", "2040-12-31"):
            result = self.cli("--hub", str(self.hub), "--goal", "modern-java", "--today", date, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            results.append(json.loads(result.stdout)["goals"])
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1][0]["tracks"][0]["sprints"][0]["status"], "active")
        self.assertEqual(self.snapshot(), before)

    def test_parent_pause_is_visible_without_changing_saved_child_status(self):
        self.create_v2()
        for kind in ("track", "goal"):
            with self.subTest(kind=kind):
                scope = ["--track", "java-core"] if kind == "track" else []
                changed = self.core_cli("transition", "--goal", "modern-java", "--kind", kind,
                                        "--status", "paused", "--note", "暂时休息", *scope)
                self.assertEqual(changed.returncode, 0, changed.stdout + changed.stderr)
                before = self.snapshot()
                report = progress.load_goals(self.hub, "modern-java")
                track = report[0]["tracks"][0]
                self.assertEqual(track["effective_status"], "paused")
                for unit in (track["milestones"][0], track["sprints"][0]):
                    self.assertEqual(unit["status"], "active")
                    self.assertEqual(unit["effective_status"], "paused")
                self.assertIn("上级已暂停", progress.summary_text(report, dt.date(2026, 10, 8)))
                self.assertEqual(self.snapshot(), before)
                resumed = self.core_cli("transition", "--goal", "modern-java", "--kind", kind,
                                        "--status", "active", "--note", "继续学习", *scope)
                self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
        self.assertEqual(progress.effective_status("completed", "paused"), "completed")
        self.assertEqual(progress.effective_status("skipped", "paused"), "skipped")

    def test_track_selection_does_not_load_an_unrelated_broken_track(self):
        self.create_v2()
        result = self.core_cli("track-create", "--goal", "modern-java", "--id", "mysql", "--title", "MySQL")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        unrelated = self.hub / "goals" / "modern-java" / "tracks" / "mysql" / "state.json"
        unrelated.write_text("{broken", encoding="utf-8")
        before = self.snapshot()
        selected = self.cli("--hub", str(self.hub), "--goal", "modern-java", "--track", "java-core", "--json")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(json.loads(selected.stdout)["goals"][0]["tracks"][0]["id"], "java-core")
        complete = self.cli("--hub", str(self.hub), "--goal", "modern-java", "--json")
        self.assertEqual(complete.returncode, 2)
        self.assertIn("JSON", complete.stderr)
        self.assertEqual(complete.stdout, "")
        self.assertEqual(self.snapshot(), before)

    def test_corrupt_new_format_does_not_fall_back_to_legacy(self):
        self.create_v2()
        goal_state = self.hub / "goals" / "modern-java" / "state.json"
        goal_state.write_text("{broken", encoding="utf-8")
        before = self.snapshot()
        result = self.cli("--hub", str(self.hub), "--json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("JSON", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_missing_v2_document_is_a_report_error(self):
        track = self.create_v2()
        (track / "track.md").unlink()
        before = self.snapshot()
        result = self.cli("--hub", str(self.hub), "--goal", "modern-java", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("track.md", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_legacy_files_remain_readable_and_unchanged(self):
        before = self.snapshot()
        result = progress.load_goals(self.hub)[0]
        self.assertTrue(result["legacy"])
        self.assertEqual(result["format"], "legacy")
        self.assertTrue(result["warnings"])
        self.assertEqual(result["module_total"], 2)
        self.assertEqual(result["module_marked_done"], 1)
        self.assertEqual(result["sessions"][0]["minutes"], 30)
        self.assertEqual(result["plan"]["weeks"][1]["week"], 99)
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("overdue", result)
        self.assertNotIn("current_week", result)
        self.assertNotIn("hours_done", result)

    def test_calendar_changes_only_display_date(self):
        before = self.snapshot()
        early = self.cli("--hub", str(self.hub), "--today", "2020-01-01", "--json")
        late = self.cli("--hub", str(self.hub), "--today", "2040-12-31", "--json")
        self.assertEqual(early.returncode, 0, early.stderr)
        self.assertEqual(late.returncode, 0, late.stderr)
        self.assertEqual(json.loads(early.stdout)["goals"], json.loads(late.stdout)["goals"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(progress.analyze_goal(self.goal, dt.date(2020, 1, 1)),
                         progress.analyze_goal(self.goal, dt.date(2040, 12, 31)))

    def test_json_remains_pure_with_html_and_html_escapes_text(self):
        (self.goal / "goal.md").write_text(
            "---\ntitle: <script>alert(1)</script>\nstatus: active\n---\n", encoding="utf-8")
        before = self.snapshot()
        output = self.root / "artifacts" / "progress.html"
        result = self.cli("--hub", str(self.hub), "--json", "--html", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["goals"]), 1)
        self.assertIn("HTML", result.stderr)
        document = output.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", document)
        self.assertNotIn("<script>", document)
        self.assertNotIn("https://", document)
        self.assertEqual(before, self.snapshot())

    def test_html_cannot_write_into_hub(self):
        for output in (self.goal / "goal.md", self.goal / "new-report.html", self.hub / "report.html"):
            with self.subTest(output=output):
                before = self.snapshot()
                result = self.cli("--hub", str(self.hub), "--json", "--html", str(output))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(before, self.snapshot())

    def test_hub_configuration_and_explicit_override(self):
        result = self.cli("--json", env={"LEARNING_COACH_HUB": str(self.hub)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["goals"][0]["id"], "legacy-java")
        result = self.cli("--hub", str(self.root / "empty"), "--json",
                          env={"LEARNING_COACH_HUB": str(self.hub)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["goals"], [])

    def test_unrecognized_legacy_modules_are_unknown_not_zero(self):
        (self.goal / "syllabus.md").write_text("# 新结构，没有旧版标记\n", encoding="utf-8")
        goal = progress.load_goals(self.hub)[0]
        self.assertIsNone(goal["module_total"])
        self.assertIsNone(goal["module_marked_done"])
        self.assertGreater(len(goal["warnings"]), 1)
        self.assertIn("未知", progress.summary_text([goal], dt.date(2026, 1, 1)))

    def test_partial_legacy_parsing_has_explicit_warnings(self):
        with (self.goal / "syllabus.md").open("a", encoding="utf-8") as stream:
            stream.write("### [x] custom-module 无法按旧规则解析\n")
        with (self.goal / "plan.md").open("a", encoding="utf-8") as stream:
            stream.write("- [x] custom-item: 保留\n")
        result = progress.load_goals(self.hub)[0]
        self.assertTrue(any("部分模块" in warning for warning in result["warnings"]))
        self.assertTrue(any("部分计划" in warning for warning in result["warnings"]))

    def test_unrecognized_sections_do_not_leak_metadata_into_previous_items(self):
        modules = progress.parse_syllabus(
            "### [x] S1-M1 基础\n预计耗时：4h\n"
            "### [x] custom 别的模块\n预计耗时：99h\n")
        self.assertEqual(modules[0]["hours"], 4)
        plan = progress.parse_plan(
            "### 2020-W01\n- [x] W1-1: 第一项\n"
            "### 自定义章节\n- [ ] W1-2: 不应被归入上一周\n")
        self.assertEqual(len(plan["weeks"][0]["items"]), 1)

    def test_initialized_hub_with_missing_goals_is_not_an_empty_report(self):
        missing_hub = self.root / "broken-hub"
        (missing_hub / "state").mkdir(parents=True)
        (missing_hub / "state" / "active.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(progress.ProgressError, "goals/"):
            progress.load_goals(missing_hub)

    def test_missing_hours_are_unknown_instead_of_zero(self):
        (self.goal / "syllabus.md").write_text(
            "## 阶段一\n### [x] S1-M1 基础\n", encoding="utf-8")
        result = progress.load_goals(self.hub)[0]
        self.assertIsNone(result["estimated_hours"])
        self.assertIn("预计总时长 未知", progress.summary_text([result], dt.date(2026, 1, 1)))

    def test_malformed_sessions_are_preserved_with_warnings(self):
        path = self.goal / "sessions" / "undated.md"
        path.write_text("---\ndate: unknown\nminutes: nan\n---\n", encoding="utf-8")
        result = progress.load_goals(self.hub)[0]
        self.assertEqual(len(result["sessions"]), 2)
        bad = next(item for item in result["sessions"] if item["file"] == "undated.md")
        self.assertIsNone(bad["minutes"])
        self.assertEqual(bad["date"], "unknown")
        self.assertTrue(any("minutes" in item for item in result["warnings"]))

    def test_new_layout_without_goal_state_is_an_explicit_error(self):
        (self.goal / "tracks").mkdir()
        before = self.snapshot()
        result = self.cli("--hub", str(self.hub), "--json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("state.json", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(progress.ProgressError):
            progress.analyze_goal(self.goal)

    def test_invalid_selection_and_date_fail_clearly(self):
        for arguments in (("--track", "java-core"), ("--goal", "missing"),
                          ("--goal", "legacy-java", "--track", "java-core"),
                          ("--today", "not-a-date")):
            with self.subTest(arguments=arguments):
                result = self.cli("--hub", str(self.hub), "--json", *arguments)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)

    def test_unknown_directory_is_not_silently_reported_as_empty_goal(self):
        (self.hub / "goals" / "unrecognized").mkdir()
        with self.assertRaises(progress.ProgressError):
            progress.load_goals(self.hub)


if __name__ == "__main__":
    unittest.main()
