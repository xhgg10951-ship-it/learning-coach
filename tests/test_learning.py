"""Phase 1 CLI acceptance tests. Tests only use isolated temporary learning hubs."""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "learning.py"


class LearningCLIAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="learning-coach-test-")
        self.addCleanup(self.temp.cleanup)
        self.hub = Path(self.temp.name) / "hub"
        self.call("init")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), "--hub", str(self.hub), *map(str, args)],
            text=True, encoding="utf-8", capture_output=True,
            env=dict(os.environ, PYTHONUTF8="1"), cwd=ROOT, timeout=20)

    def call(self, *args):
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, f"{args}\n{result.stderr}\n{result.stdout}")
        self.assertEqual(result.stderr, "", f"Unexpected stderr for {args}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"Success must return one JSON value: {args}: {result.stdout!r}: {exc}")

    def rejected(self, *args):
        before = self.snapshot()
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 2, f"{args}\n{result.stdout}\n{result.stderr}")
        self.assertEqual(result.stdout, "")
        try:
            error = json.loads(result.stderr)
        except json.JSONDecodeError as exc:
            self.fail(f"Failure must return a JSON error: {args}: {result.stderr!r}: {exc}")
        self.assertTrue(error.get("error"), error)
        self.assertEqual(self.snapshot(), before, f"Rejected operation changed files: {args}")
        return error

    def snapshot(self):
        return {p.relative_to(self.hub).as_posix(): p.read_bytes()
                for p in self.hub.rglob("*") if p.is_file()}

    def goal(self, goal="java-backend", title="Java 后端开发"):
        return self.call("goal-create", "--id", goal, "--title", title,
                         "--description", "独立实现可运行的项目", "--level", "初学",
                         "--motivation", "完成自己的作品", "--ability", "能解释并演示实现")

    def track(self, track="java-core", goal="java-backend", depends=()):
        args = ["track-create", "--goal", goal, "--id", track, "--title", track]
        for dependency in depends:
            args += ["--depends-on", dependency]
        return self.call(*args)

    def fixture(self):
        self.goal()
        self.track()
        return self.milestone(), self.sprint()

    def milestone(self, track="java-core", goal="java-backend", **options):
        args = ["milestone-create", "--goal", goal, "--track", track,
                "--title", options.pop("title", "运行基础 API"),
                "--objective", "能够实现并说明请求处理流程",
                "--criterion", "独立运行 API 并解释一次请求的完整流程"]
        for key, value in options.items():
            args += ["--" + key.replace("_", "-"), str(value)]
        return self.call(*args)

    def sprint(self, milestone="M001", track="java-core", goal="java-backend", **options):
        args = ["sprint-create", "--goal", goal, "--track", track, "--milestone", milestone,
                "--title", options.pop("title", "项目启动"), "--objective", "理解项目结构并能独立启动",
                "--criterion", "能从空目录创建并启动项目"]
        for key, value in options.items():
            args += ["--" + key.replace("_", "-"), str(value)]
        return self.call(*args)

    def change(self, kind, status, id=None, goal="java-backend", track="java-core",
               note="用户确认：已独立演示并解释验收标准", reject=False):
        args = ["transition", "--goal", goal, "--kind", kind, "--status", status, "--note", note]
        if kind != "goal":
            args += ["--track", track]
        if id is not None:
            args += ["--id", id]
        return (self.rejected if reject else self.call)(*args)

    def state(self, goal="java-backend", track="java-core"):
        return self.call("show", "--goal", goal, "--track", track)

    def state_path(self, goal="java-backend", track="java-core"):
        return self.hub / "goals" / goal / "tracks" / track / "state.json"

    def rewrite_state(self, state):
        self.state_path().write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def test_01_multiple_goals_keep_profiles_and_state_independent(self):
        java = self.goal()
        english = self.goal("english", "英语口语")
        self.assertEqual(java["id"], "java-backend")
        self.assertEqual(english["id"], "english")
        english_before = (self.hub / "goals/english/state.json").read_bytes()
        self.change("goal", "paused", note="先学习英语")
        self.assertEqual((self.hub / "goals/english/state.json").read_bytes(), english_before)
        self.assertEqual(self.call("show", "--goal", "english")["status"], "active")
        profile = (self.hub / "goals/java-backend/goal.md").read_text(encoding="utf-8")
        for detail in ["独立实现可运行的项目", "初学", "完成自己的作品", "能解释并演示实现"]:
            self.assertIn(detail, profile + json.dumps(java, ensure_ascii=False))

    def test_02_multiple_tracks_have_independent_files_and_state(self):
        self.goal()
        for track in ("java-core", "spring-boot", "mysql"):
            self.track(track)
            for folder in ("milestones", "sprints", "sessions"):
                self.assertTrue((self.state_path(track=track).parent / folder).is_dir())
        others = {track: self.state_path(track=track).read_bytes() for track in ("spring-boot", "mysql")}
        self.milestone()
        self.sprint()
        for track, content in others.items():
            self.assertEqual(self.state_path(track=track).read_bytes(), content)
            self.assertEqual(self.state(track=track)["milestones"], {})
            self.assertEqual(self.state(track=track)["sprints"], {})

    def test_03_progressive_planning_creates_only_requested_units(self):
        self.goal()
        self.track()
        state = self.state()
        self.assertEqual(state["milestones"], {})
        self.assertEqual(state["sprints"], {})
        self.assertEqual(self.milestone()["id"], "M001")
        self.assertEqual(self.state()["sprints"], {})
        self.assertEqual(self.sprint()["id"], "SP001")
        state = self.state()
        self.assertEqual(set(state["milestones"]), {"M001"})
        self.assertEqual(set(state["sprints"]), {"SP001"})
        self.assertTrue(state["sprints"]["SP001"]["criteria"])
        self.assertEqual(state["sprints"]["SP001"]["milestone_id"], "M001")

    def test_04_multiple_sprints_can_complete_on_same_day(self):
        self.fixture()
        self.change("sprint", "completed", "SP001")
        self.assertEqual(self.sprint(title="处理第一个请求")["id"], "SP002")
        self.change("sprint", "completed", "SP002")
        state = self.state()
        self.assertEqual([s["status"] for s in state["sprints"].values()], ["completed", "completed"])
        self.assertEqual(state["milestones"]["M001"]["status"], "active")

    def test_05_one_month_of_inactivity_does_not_change_progress(self):
        self.fixture()
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=35)).isoformat()

        def age_metadata(value):
            if isinstance(value, dict):
                return {key: age_metadata(item) for key, item in value.items()}
            if isinstance(value, list):
                return [age_metadata(item) for item in value]
            if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}T", value):
                return old
            return value

        self.rewrite_state(age_metadata(self.state()))
        self.call("select", "--goal", "java-backend", "--track", "java-core")
        before = self.snapshot()
        self.call("current")
        self.call("validate")
        aged = self.state()
        self.assertEqual(aged["sprints"]["SP001"]["status"], "active")
        self.assertEqual(set(aged["sprints"]), {"SP001"})
        self.assertEqual(self.snapshot(), before)

    def test_06_switching_goals_and_tracks_preserves_unfinished_sprint(self):
        self.fixture()
        self.track("mysql")
        self.goal("english", "英语口语")
        self.track("speaking", "english")
        original = self.state_path().read_bytes()
        for goal, track in [("java-backend", "mysql"), ("english", "speaking"), ("java-backend", "java-core")]:
            self.call("select", "--goal", goal, "--track", track)
            current = self.call("current")
            self.assertEqual(current["active"]["goal_id"], goal)
            self.assertEqual(current["active"]["track_id"], track)
            self.assertEqual(current["goal"]["id"], goal)
            self.assertEqual(current["track"]["id"], track)
        self.assertEqual(self.state_path().read_bytes(), original)

    def test_07_duplicate_ids_and_concurrent_units_are_rejected(self):
        self.fixture()
        self.rejected("goal-create", "--id", "java-backend", "--title", "重复")
        self.rejected("track-create", "--goal", "java-backend", "--id", "java-core", "--title", "重复")
        for command, unit_id in [("milestone-create", "M001"), ("sprint-create", "SP001")]:
            args = [command, "--goal", "java-backend", "--track", "java-core", "--id", unit_id,
                    "--title", "重复", "--objective", "可检验目标", "--criterion", "能演示目标"]
            if command == "sprint-create":
                args += ["--milestone", "M001"]
            self.rejected(*args)
            args[args.index("--id") + 1] = "M002" if command == "milestone-create" else "SP002"
            self.rejected(*args)

    def test_07_resuming_another_unit_cannot_bypass_single_active_rule(self):
        self.fixture()
        self.sprint(adjustment="用户改为先练习请求处理")
        self.change("sprint", "active", "SP001", reject=True)
        self.milestone(adjustment="用户要求切换阶段目标")
        self.change("milestone", "active", "M001", reject=True)
        state = self.state()
        self.assertEqual(state["milestones"]["M001"]["status"], "paused")
        self.assertEqual(state["sprints"]["SP002"]["status"], "paused")

    def test_08_fresh_process_reads_identical_position_and_history(self):
        self.fixture()
        self.change("sprint", "completed", "SP001", note="独立启动并解释目录结构")
        self.sprint()
        self.call("select", "--goal", "java-backend", "--track", "java-core")
        state, current = self.state(), self.call("current")
        before = self.snapshot()
        # Each CLI call launches a fresh interpreter, including these reads.
        self.assertEqual(self.state(), state)
        self.assertEqual(self.call("current"), current)
        self.assertIn("独立启动并解释目录结构", json.dumps(state, ensure_ascii=False))
        self.assertEqual(self.snapshot(), before)

    def test_09_legacy_goal_is_not_overwritten_or_treated_as_empty_v2(self):
        legacy = self.hub / "goals/old-java"
        legacy.mkdir(parents=True)
        (legacy / "goal.md").write_text("---\ntitle: 旧目标\nstatus: active\n---\n", encoding="utf-8")
        (legacy / "plan.md").write_text("## 2026-09 月\n### 2026-W36\n- [ ] W36-1: 用户原始记录\n", encoding="utf-8")
        self.rejected("goal-create", "--id", "old-java", "--title", "覆盖旧目标")
        self.rejected("show", "--goal", "old-java")
        self.rejected("track-create", "--goal", "old-java", "--id", "basics", "--title", "基础")


    def test_init_is_repeatable_without_rewriting_existing_data(self):
        self.fixture()
        before = self.snapshot()
        self.call("init")
        self.assertEqual(self.snapshot(), before)

    def test_repeated_transition_is_idempotent_without_duplicate_history(self):
        self.fixture()
        self.change("sprint", "completed", "SP001")
        before = self.snapshot()
        self.change("sprint", "completed", "SP001")
        self.assertEqual(self.snapshot(), before)

    def test_ids_are_stable_when_titles_change(self):
        self.fixture()
        self.call("update", "--goal", "java-backend", "--track", "java-core", "--kind", "sprint",
                  "--id", "SP001", "--title", "调整后的学习单元", "--objective", "能独立启动并解释配置",
                  "--criterion", "完成启动演示", "--criterion", "说明配置来源", "--note", "根据用户已有经验缩小范围")
        state = self.state()
        self.assertEqual(set(state["sprints"]), {"SP001"})
        self.assertEqual(state["sprints"]["SP001"]["title"], "调整后的学习单元")
        self.assertEqual(state["sprints"]["SP001"]["criteria"], ["完成启动演示", "说明配置来源"])
        self.assertIn("根据用户已有经验缩小范围", json.dumps(state, ensure_ascii=False))

    def test_skip_and_end_are_preserved_as_distinct_outcomes(self):
        self.fixture()
        self.change("sprint", "skipped", "SP001", note="用户已有经验，主动跳过，未做验收")
        self.sprint()
        self.change("sprint", "ended", "SP002", note="用户决定提前结束，未完成")
        self.sprint()
        state = self.state()
        self.assertEqual(state["sprints"]["SP001"]["status"], "skipped")
        self.assertEqual(state["sprints"]["SP002"]["status"], "ended")
        self.assertEqual(state["sprints"]["SP003"]["status"], "active")
        self.change("sprint", "completed", "SP001", reject=True)
        self.change("sprint", "completed", "SP002", reject=True)

    def test_milestone_cannot_complete_with_unfinished_sprints(self):
        self.fixture()
        self.change("milestone", "completed", "M001", reject=True)
        self.change("sprint", "paused", "SP001", note="先处理别的任务")
        self.change("milestone", "completed", "M001", reject=True)
        self.change("sprint", "active", "SP001", note="恢复任务")
        self.change("sprint", "completed", "SP001")
        self.change("milestone", "completed", "M001")
        self.assertEqual(self.milestone()["id"], "M002")
        self.assertEqual(self.sprint(milestone="M002")["id"], "SP002")

    def test_completion_requires_active_unit_and_nonempty_note(self):
        self.fixture()
        self.change("sprint", "completed", "SP001", note="", reject=True)
        self.change("sprint", "completed", "SP001", note="   ", reject=True)
        self.change("sprint", "paused", "SP001", note="用户暂停")
        self.change("sprint", "completed", "SP001", reject=True)

    def test_pausing_milestone_pauses_its_active_sprint(self):
        self.fixture()
        self.change("milestone", "paused", "M001", note="用户暂停阶段")
        state = self.state()
        self.assertEqual(state["milestones"]["M001"]["status"], "paused")
        self.assertEqual(state["sprints"]["SP001"]["status"], "paused")
        self.change("sprint", "active", "SP001", reject=True)

    def test_ending_milestone_ends_unfinished_sprints(self):
        self.fixture()
        self.change("milestone", "ended", "M001", note="目标变化，提前结束")
        state = self.state()
        self.assertEqual(state["milestones"]["M001"]["status"], "ended")
        self.assertEqual(state["sprints"]["SP001"]["status"], "ended")
        self.assertEqual(self.milestone()["id"], "M002")

    def test_paused_parents_block_progress_but_allow_context_selection(self):
        self.fixture()
        for kind in ("track", "goal"):
            with self.subTest(parent=kind):
                self.change(kind, "paused", note="用户暂停这个范围")
                self.call("select", "--goal", "java-backend", "--track", "java-core")
                self.call("current")
                self.change("sprint", "completed", "SP001", reject=True)
                self.rejected("sprint-create", "--goal", "java-backend", "--track", "java-core",
                              "--milestone", "M001", "--title", "新单元", "--objective", "新目标",
                              "--criterion", "演示目标", "--adjustment", "用户调整内容")
                self.change(kind, "active", note="用户恢复这个范围")
        self.assertEqual(self.state()["sprints"]["SP001"]["status"], "active")

    def test_goal_and_track_cannot_complete_with_unfinished_children(self):
        self.fixture()
        self.change("track", "completed", reject=True)
        self.change("goal", "completed", reject=True)
        self.change("sprint", "completed", "SP001")
        self.change("milestone", "completed", "M001")
        self.change("track", "completed")
        self.change("goal", "completed")
        self.assertEqual(self.call("show", "--goal", "java-backend")["status"], "completed")

    def test_dependencies_do_not_force_track_order(self):
        self.goal()
        self.track()
        self.track("spring-boot", depends=("java-core",))
        self.change("track", "paused", note="基础内容稍后再学")
        self.call("select", "--goal", "java-backend", "--track", "spring-boot")
        self.milestone(track="spring-boot")
        self.assertEqual(self.state(track="spring-boot")["milestones"]["M001"]["status"], "active")

    def test_scoped_ids_can_be_reused_in_other_goals_and_tracks(self):
        self.fixture()
        self.goal("english", "英语口语")
        self.track("java-core", "english")
        self.assertEqual(self.milestone(goal="english")["id"], "M001")
        self.assertEqual(self.sprint(goal="english")["id"], "SP001")
        self.assertEqual(self.state()["sprints"]["SP001"]["status"], "active")

    def test_session_spec_allows_off_plan_topic_without_persisting_records(self):
        self.fixture()
        before = self.snapshot()
        result = self.call("session-spec", "--goal", "java-backend", "--track", "java-core",
                           "--topic", "临时想了解的网络问题", "--minutes", "45")
        self.assertIn("临时想了解的网络问题", json.dumps(result, ensure_ascii=False))
        associated = self.call("session-spec", "--goal", "java-backend", "--track", "java-core",
                               "--sprint", "SP001", "--topic", "启动项目")
        self.assertIn("SP001", json.dumps(associated))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list((self.state_path().parent / "sessions").iterdir()), [])

    def test_all_read_commands_are_read_only(self):
        self.fixture()
        self.call("select", "--goal", "java-backend", "--track", "java-core")
        before = self.snapshot()
        for args in [("current",), ("list",), ("list", "--goal", "java-backend"),
                     ("show", "--goal", "java-backend"),
                     ("show", "--goal", "java-backend", "--track", "java-core"), ("validate",)]:
            with self.subTest(command=args):
                self.call(*args)
                self.assertEqual(self.snapshot(), before)

    def test_goal_only_selection_does_not_leak_previous_track(self):
        self.fixture()
        self.goal("english", "英语口语")
        self.call("select", "--goal", "java-backend", "--track", "java-core")
        self.call("select", "--goal", "english")
        current = self.call("current")
        self.assertEqual(current["active"]["goal_id"], "english")
        self.assertIsNone(current["active"]["track_id"])
        self.assertIsNone(current["track"])

    def test_unsafe_goal_ids_cannot_escape_hub(self):
        for unsafe in ("../escape", "..", ".", "a/b", "a\\b", "C:\\escape", "", "CON"):
            with self.subTest(id=unsafe):
                self.rejected("goal-create", "--id", unsafe, "--title", "非法 ID")
        self.assertFalse((Path(self.temp.name) / "escape").exists())

    def test_empty_objectives_criteria_and_invalid_hours_are_rejected(self):
        self.goal()
        self.track()
        common = ["milestone-create", "--goal", "java-backend", "--track", "java-core", "--title", "阶段"]
        self.rejected(*common, "--objective", "", "--criterion", "演示")
        self.rejected(*common, "--objective", "可检验目标", "--criterion", "   ")
        for hours in ("0", "-1", "nan", "inf"):
            with self.subTest(hours=hours):
                self.rejected(*common, "--objective", "可检验目标", "--criterion", "演示", "--hours", hours)

    def test_argparse_errors_also_use_json_error_contract(self):
        self.rejected("does-not-exist")
        self.rejected("goal-create", "--id", "java-backend")
        self.rejected("transition", "--goal", "java-backend", "--kind", "goal",
                      "--status", "unknown", "--note", "非法状态")

    def test_corrupt_json_reports_error_and_preserves_corrupt_bytes(self):
        self.fixture()
        self.state_path().write_text('{"schema_version":', encoding="utf-8")
        self.rejected("show", "--goal", "java-backend", "--track", "java-core")
        self.rejected("validate")
        self.change("sprint", "completed", "SP001", reject=True)

    def test_valid_json_with_wrong_shape_or_version_is_rejected(self):
        self.fixture()
        original = self.state_path().read_bytes()
        for invalid in ([], {"schema_version": 999}, {"schema_version": 2}):
            with self.subTest(value=invalid):
                self.rewrite_state(invalid)
                self.rejected("show", "--goal", "java-backend", "--track", "java-core")
                self.rejected("validate")
                self.state_path().write_bytes(original)

    def test_invalid_persisted_status_and_duplicate_active_units_are_rejected(self):
        self.fixture()
        state = self.state()
        state["sprints"]["SP001"]["status"] = "overdue"
        self.rewrite_state(state)
        self.rejected("validate")
        state["sprints"]["SP001"]["status"] = "active"
        state["sprints"]["SP002"] = {**state["sprints"]["SP001"], "id": "SP002"}
        self.rewrite_state(state)
        self.rejected("validate")

    def test_missing_authoritative_state_is_reported_not_reinitialized(self):
        self.fixture()
        self.state_path().unlink()
        self.rejected("show", "--goal", "java-backend", "--track", "java-core")
        self.rejected("validate")
        self.rejected("track-create", "--goal", "java-backend", "--id", "java-core", "--title", "覆盖")

    def test_corrupt_active_pointer_is_not_silently_reset(self):
        self.fixture()
        (self.hub / "state/active.json").write_text("not JSON", encoding="utf-8")
        self.rejected("current")
        self.rejected("init")



    def test_boundary_pending_units_need_explicit_activation(self):
        self.goal()
        self.call("track-create", "--goal", "java-backend", "--id", "java-core",
                  "--title", "Java", "--status", "pending")
        self.rejected("milestone-create", "--goal", "java-backend", "--track", "java-core",
                      "--title", "阶段", "--objective", "能运行项目", "--criterion", "独立运行项目")
        self.change("track", "active", note="用户选择开始")
        self.milestone(status="pending")
        self.change("milestone", "completed", "M001", reject=True)
        self.rejected("sprint-create", "--goal", "java-backend", "--track", "java-core",
                      "--milestone", "M001", "--title", "单元", "--objective", "能运行项目",
                      "--criterion", "独立运行项目")
        self.change("milestone", "active", "M001", note="用户选择开始")
        self.sprint(status="pending")
        self.change("sprint", "completed", "SP001", reject=True)
        self.change("sprint", "active", "SP001", note="用户选择开始")
        self.change("sprint", "completed", "SP001")

    def test_boundary_current_does_not_load_unrelated_goals_or_tracks(self):
        self.fixture()
        self.track("mysql")
        self.goal("english", "英语口语")
        self.track("speaking", "english")
        self.call("select", "--goal", "java-backend", "--track", "java-core")
        expected = self.call("current")
        self.state_path(track="mysql").write_text("corrupt unrelated track", encoding="utf-8")
        self.state_path(goal="english", track="speaking").write_text("corrupt unrelated goal", encoding="utf-8")
        self.assertEqual(self.call("current"), expected)
        self.rejected("validate")

    def test_boundary_skipping_milestone_preserves_completed_history(self):
        self.fixture()
        self.change("sprint", "completed", "SP001")
        self.sprint()
        before_completed = self.state()["sprints"]["SP001"]
        self.change("milestone", "skipped", "M001", note="用户主动改变目标，跳过剩余内容")
        state = self.state()
        self.assertEqual(state["sprints"]["SP001"], before_completed)
        self.assertEqual(state["sprints"]["SP002"]["status"], "skipped")
        self.assertEqual(state["milestones"]["M001"]["status"], "skipped")
        self.rejected("update", "--goal", "java-backend", "--track", "java-core",
                      "--kind", "sprint", "--id", "SP001", "--criterion", "改写完成标准",
                      "--note", "不能改写历史验收")
        self.assertEqual(self.state()["sprints"]["SP001"], before_completed)

    def test_boundary_custom_ids_advance_sequence_without_reusing_history(self):
        self.goal()
        self.track()
        self.assertEqual(self.milestone(id="M007")["id"], "M007")
        self.assertEqual(self.sprint(milestone="M007", id="SP012")["id"], "SP012")
        self.change("sprint", "ended", "SP012", note="用户提前结束")
        self.change("milestone", "ended", "M007", note="用户提前结束")
        self.assertEqual(self.milestone()["id"], "M008")
        self.assertEqual(self.sprint(milestone="M008")["id"], "SP013")

    def test_boundary_markdown_checkboxes_do_not_override_machine_state(self):
        self.fixture()
        document = self.state_path().parent / "sprints" / "SP001.md"
        with document.open("a", encoding="utf-8") as stream:
            stream.write("\n- [x] 用户手工补充说明，不是验收状态\n")
        self.assertEqual(self.state()["sprints"]["SP001"]["status"], "active")
        self.call("validate")


if __name__ == "__main__":
    unittest.main()
