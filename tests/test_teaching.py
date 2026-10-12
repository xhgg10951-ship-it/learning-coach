"""Adaptive state and evidence integration, with real temporary Session files."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import learning, sessions, teaching


CRITERIA = ["准确区分 size 与容量", "区分索引越界与空指针", "解释批量复制复杂度", "实现并运行综合案例"]


def event(identity, kind="exercise", basis="exercise_verified", **extra):
    return {"id": identity, "kind": kind, "text": "测试夹具，非真实学习记录",
            "basis": basis, "sources": [{"ref": "fixture/user/1", "quote": "实际测试输入"}], **extra}


def exercise(identity="task-1", outcomes=("met", "not_met", "not_met", "unverified"), **changes):
    return event(identity, prompt="阅读列表代码，判断 size、异常与复制成本", answer="size=2，其余判断待修正",
                 result="partial", feedback="size 正确，异常类型与复制复杂度存在概念错误",
                 assessment={"form": "代码阅读和复杂度分析", "error_type": "conceptual",
                             "checks": [{"criterion": c, "outcome": o, "reason": "依据本次测试答案"}
                                        for c, o in zip(CRITERIA, outcomes)]}, **changes)


def adjustment(identity="mode-1", **changes):
    return event(identity, "teaching", "user_report", teaching={**teaching.DEFAULT_STATE,
                 "difficulty": "Java 集合基础以上，局部补异常和批量复制", **changes})


def batch(identity="save-1", events=(), focus=()):
    return {"operation_id": identity, "events": list(events),
            "handoff": {"summary": "仅测试数据", "next_step": "由用户选择是否继续", "focus_ids": list(focus)}}


class TeachingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="learning-teaching-")
        self.addCleanup(self.temp.cleanup)
        self.hub = learning.Hub(Path(self.temp.name) / "hub")
        self.hub.initialize()
        self.hub.create_goal("Java", identity="java", level="已有集合基础")
        self.hub.create_track("java", "Java 基础", identity="core")
        self.hub.create_unit("java", "core", "milestone", "集合", "使用集合", CRITERIA)
        self.hub.create_unit("java", "core", "sprint", "ArrayList", "分析和应用 ArrayList", CRITERIA, milestone="M001")
        self.hub.select("java", "core")
        self.store = self.hub.sessions()
        self.sid = self.store.start("java", "core", "ArrayList", "start-1", sprint="SP001")["id"]

    def save(self, payload, finish=False):
        return self.store.checkpoint("java", "core", self.sid, payload, finish=finish)

    def context(self, **kwargs):
        return teaching.context(self.store, **kwargs)

    def read(self):
        return json.loads(self.store.path("java", "core", self.sid, "record.json").read_text(encoding="utf-8"))

    def snapshot(self):
        return {p.relative_to(self.hub.root).as_posix(): p.read_bytes() for p in self.hub.root.rglob("*") if p.is_file()}

    def test_start_reads_profile_requirements_and_no_evidence_is_unverified(self):
        (self.hub.root / "profile.md").write_text("喜欢真实小任务", encoding="utf-8")
        (self.hub._tdir("java", "core") / "track.md").write_text("能使用常见集合", encoding="utf-8")
        before = self.snapshot()
        ctx = self.context()
        self.assertEqual(ctx["profiles"]["goal"]["level"], "已有集合基础")
        self.assertEqual(ctx["profiles"]["track_notes"], "能使用常见集合")
        self.assertEqual(ctx["profiles"]["common"], "喜欢真实小任务")
        self.assertEqual(ctx["current_milestone"]["id"], "M001")
        self.assertEqual([c["status"] for c in ctx["criteria"]], ["unverified"] * 4)
        self.assertEqual(before, self.snapshot())

    def test_integrated_partial_preserves_passed_skills_outside_focus(self):
        self.save(batch(events=[exercise()]))
        ctx = self.context()
        self.assertEqual([c["status"] for c in ctx["criteria"]], ["verified", "needs_consolidation", "needs_consolidation", "unverified"])
        self.assertEqual(ctx["recommendation"]["avoid_basic_repetition"], CRITERIA[:1])
        self.assertEqual(ctx["exercises"][0]["answer"], "size=2，其余判断待修正")

    def test_partial_integrated_task_supports_only_matching_passed_criterion(self):
        self.save(batch(events=[exercise(), event("claim", "evidence", related_ids=["task-1"], criterion=CRITERIA[0], outcome="met")]))
        before = self.snapshot()
        with self.assertRaises(learning.LearningError):
            self.save(batch("invalid", [event("claim-2", "evidence", related_ids=["task-1"], criterion=CRITERIA[3], outcome="met")]))
        self.assertEqual(before, self.snapshot())

    def test_modes_and_decline_persist_without_planning_mutations(self):
        path = self.hub._tdir("java", "core") / "state.json"
        original = path.read_bytes()
        for i, mode in enumerate(sorted(teaching.MODES)):
            self.save(batch(f"save-{i}", [adjustment(f"mode-{i}", mode=mode, exercise_policy="declined")]))
            self.assertEqual(self.context()["teaching_state"]["mode"], mode)
            self.assertEqual(self.context()["recommendation"]["practice"], "stop")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.read()["session_version"], 3)

    def test_new_process_restores_difficulty_and_gaps_after_finish(self):
        self.save(batch(events=[exercise(), adjustment(mode="quick", pace="fast")]), finish=True)
        old = self.sid
        self.sid = self.store.start("java", "core", "ArrayList", "new-start", sprint="SP001", previous=old)["id"]
        # An early content checkpoint must not erase inherited settings.
        self.save(batch("empty-checkpoint"))
        result = subprocess.run([sys.executable, str(ROOT / "scripts/learning.py"), "--hub", str(self.hub.root),
                                 "teaching-context"], capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        ctx = json.loads(result.stdout)
        self.assertEqual(ctx["teaching_state"]["mode"], "quick")
        self.assertEqual(ctx["teaching_state"]["source"]["session_id"], old)
        self.assertEqual(ctx["remaining_gaps"], CRITERIA[1:])
        self.assertEqual(self.read()["events"], [])

    def test_explicit_predecessor_beats_newer_unrelated_mode(self):
        self.save(batch(events=[adjustment(mode="quick")]), finish=True)
        prior = self.sid
        self.sid = self.store.start("java", "core", "其他课题", "other", sprint="SP001")["id"]
        self.save(batch(events=[adjustment(mode="deep")]), finish=True)
        self.sid = self.store.start("java", "core", "ArrayList", "third", sprint="SP001", previous=prior)["id"]
        ctx = self.context(limit=1)
        self.assertEqual(ctx["teaching_state"]["mode"], "quick")
        self.assertEqual(ctx["history"]["selected_ids"], [self.sid, prior])
        self.assertFalse(ctx["history"]["complete"])

    def test_end_immediately_without_exercises_or_sprint_acceptance(self):
        saved = self.save(batch(events=[adjustment(exercise_policy="declined")]), finish=True)
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(self.hub.get_track("java", "core")["sprints"]["SP001"]["status"], "active")
        self.assertIn("declined", Path(saved["note_path"]).read_text(encoding="utf-8"))
        self.assertTrue(self.hub.validate()["valid"])

    def test_only_wording_does_not_invalidate_demonstrated_ability(self):
        task = exercise(outcomes=("met", "met", "met", "unverified"))
        task["result"] = "correct"
        task["assessment"]["error_type"] = "wording"
        self.save(batch(events=[task]))
        self.assertEqual(self.context()["verified_abilities"], CRITERIA[:3])

    def test_explanation_self_report_and_duration_never_prove_mastery(self):
        self.hub.update("java", "sprint", "调整参考粒度", track="core", identity="SP001", estimated_hours=1000)
        self.save(batch(events=[event("explain", "explanation", "ai_assessment"),
                               event("self", "evidence", "user_report", criterion=CRITERIA[0], outcome="met")]))
        ctx = self.context()
        self.assertEqual(ctx["criteria"][0]["status"], "user_reported")
        self.assertFalse(ctx["verified_abilities"])
        self.assertFalse(ctx["recommendation"]["may_suggest_sprint_completion"])

    def test_all_verified_only_suggests_completion(self):
        task = exercise(outcomes=("met",) * 4)
        task.update(result="correct")
        task["assessment"]["error_type"] = "none"
        self.save(batch(events=[task]))
        ctx = self.context()
        self.assertTrue(ctx["recommendation"]["may_suggest_sprint_completion"])
        self.assertEqual(ctx["recommendation"]["lifecycle_action"], "none")
        self.assertEqual(self.read()["status"], "active")

    def test_current_corrected_evidence_controls_difficulty_and_coverage(self):
        derived = adjustment()
        derived.update(basis="ai_assessment", related_ids=["task-1"])
        self.save(batch(events=[exercise(), derived]), finish=True)
        replacement = exercise("fixed", outcomes=("unverified",) * 4, supersedes=["task-1"])
        replacement.update(result="not_assessed", answer="", basis="unverified")
        replacement["assessment"]["error_type"] = "unassessed"
        payload = {**batch("correct", [replacement]), "reason": "原输入是 AI 演示而非用户回答"}
        self.store.correct("java", "core", self.sid, payload)
        ctx = self.context()
        self.assertEqual(ctx["verified_abilities"], [])
        self.assertIsNone(ctx["teaching_state"]["source"])
        self.assertEqual(self.read()["session_version"], 3)
        self.assertTrue(self.hub.validate()["valid"])

    def test_v3_correction_note_failure_replays_historical_render(self):
        self.save(batch(events=[exercise()]), finish=True)
        old_note = self.store.path("java", "core", self.sid, "note.md").read_bytes()
        payload = {**batch("correction", [exercise("fixed", supersedes=["task-1"])]), "reason": "补充批改理由"}
        with mock.patch.object(sessions, "_atomic", side_effect=OSError("note failed")):
            with self.assertRaises(OSError):
                self.store.correct("java", "core", self.sid, payload)
        self.assertEqual(old_note, self.store.path("java", "core", self.sid, "note.md").read_bytes())
        self.store.correct("java", "core", self.sid, payload)
        self.assertTrue(self.hub.validate()["valid"])
        self.assertIn("fixed", self.store.path("java", "core", self.sid, "note.md").read_text(encoding="utf-8"))

    def test_bad_teaching_and_assessment_are_atomic_rejections(self):
        cases = []
        for key, value in (("mode", "automatic-complete"), ("pace", 4), ("depth", None), ("exercise_policy", "forced")):
            cases.append(adjustment(**{key: value}))
        bad = exercise()
        bad["assessment"]["checks"][0]["criterion"] = "其他 Sprint 标准"
        cases.append(bad)
        for change in ({"result": "not_assessed"}, {"result": "correct"}, {"answer": ""}):
            bad = exercise()
            bad.update(change)
            cases.append(bad)
        before = self.snapshot()
        for item in cases:
            with self.subTest(item=item), self.assertRaises(learning.LearningError):
                self.save(batch(events=[item]))
            self.assertEqual(self.snapshot(), before)

    def test_no_writes_on_read_and_v1_remains_compatible(self):
        self.save(batch(events=[event("old", "content", "unverified")]), finish=True)
        before = self.snapshot()
        self.context()
        self.store.repair("java", "core")
        self.assertEqual(self.read()["session_version"], 1)
        self.assertEqual(before, self.snapshot())

    def test_no_cross_goal_or_track_reads(self):
        self.hub.create_goal("English", identity="english")
        self.hub.create_track("english", "Conversation", identity="core")
        (self.hub._gdir("english") / "state.json").write_text("broken", encoding="utf-8")
        self.assertEqual(self.context()["goal"]["id"], "java")

    def test_objective_changes_do_not_reinterpret_old_evidence(self):
        self.save(batch(events=[exercise()]))
        self.hub.update("java", "sprint", "改变能力目标", track="core", identity="SP001", objective="新目标")
        self.assertEqual(self.context()["verified_abilities"], [])

    def test_latest_independent_result_wins_but_unverified_does_not_erase(self):
        self.save(batch(events=[exercise()]), finish=True)
        self.sid = self.store.start("java", "core", "ArrayList", "second", sprint="SP001")["id"]
        task = exercise("new", outcomes=("unverified", "met", "met", "unverified"))
        task.update(result="correct")
        task["assessment"]["error_type"] = "none"
        self.save(batch(events=[task]))
        self.assertEqual(self.context()["verified_abilities"], CRITERIA[:3])

    def test_domain_forms_are_open_and_off_sprint_work_can_finish(self):
        self.save(batch(), finish=True)
        for number, form in enumerate(("SQL 与执行计划", "英语情境表达", "理论案例分析")):
            self.sid = self.store.start("java", "core", "计划外", f"off-{number}")["id"]
            task = exercise()
            task["assessment"].update(form=form, checks=[])
            self.save(batch(events=[task]), finish=True)
        self.assertTrue(self.hub.validate()["valid"])

    def test_completed_sprint_without_active_session_still_has_recent_teaching(self):
        self.save(batch(events=[adjustment(mode="deep")]), finish=True)
        self.hub.transition("java", "sprint", "ended", "测试用户结束单元", track="core", identity="SP001")
        ctx = self.context()
        self.assertIsNone(ctx["current_sprint"])
        self.assertEqual(ctx["teaching_state"]["mode"], "deep")
        self.assertFalse(ctx["recommendation"]["may_suggest_sprint_completion"])

    def test_successful_retest_removes_criterion_gap_without_deleting_history(self):
        first = exercise()
        self.save(batch(events=[first]))
        second = exercise("retest", outcomes=("unverified", "met", "met", "unverified"))
        second.update(result="correct")
        second["assessment"]["error_type"] = "none"
        self.save(batch("retest-batch", [second]))
        ctx = self.context()
        self.assertEqual(ctx["remaining_gaps"], CRITERIA[3:])
        self.assertEqual(ctx["criteria"][1]["decisive_evidence"]["event_id"], "retest")
        self.assertEqual(self.read()["events"][0], first)

    def test_invalid_handoff_never_loses_new_mode_on_retry(self):
        payload = batch(events=[adjustment(mode="quick")])
        self.save(payload)
        original = self.snapshot()
        self.assertEqual(self.save(payload)["event_count"], 1)
        self.assertEqual(self.snapshot(), original)
        payload["events"][0]["teaching"]["mode"] = "deep"
        with self.assertRaises(learning.LearningError):
            self.save(payload)
        self.assertEqual(self.snapshot(), original)

    def test_late_correction_of_old_work_does_not_override_newer_performance(self):
        self.save(batch(events=[exercise()]), finish=True)
        prior = self.sid
        self.sid = self.store.start("java", "core", "ArrayList", "next", sprint="SP001")["id"]
        self.save(batch(events=[exercise("recent", outcomes=("not_met", "not_met", "not_met", "unverified"))]))
        fixed = exercise("fixed", supersedes=["task-1"])
        self.store.correct("java", "core", prior, {**batch("late-fix", [fixed]), "reason": "更正旧批改的措辞"})
        row = self.context()["criteria"][0]
        self.assertEqual(row["status"], "needs_consolidation")
        self.assertEqual(row["decisive_evidence"]["event_id"], "recent")

    def test_predecessor_times_compare_instants_across_timezones(self):
        with mock.patch.object(sessions, "now", return_value="2030-01-01T10:00:00+08:00"):
            self.save(batch(events=[adjustment(mode="guided")]), finish=True)
        prior = self.sid
        with mock.patch.object(sessions, "now", return_value="2030-01-01T03:00:00+00:00"):
            self.sid = self.store.start("java", "core", "ArrayList", "timezone-next", sprint="SP001", previous=prior)["id"]
        self.assertEqual(self.context()["teaching_state"]["mode"], "guided")


if __name__ == "__main__":
    unittest.main()
