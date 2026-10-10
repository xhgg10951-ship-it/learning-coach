"""Real files, subprocess handoffs and injected crashes. All hubs are temporary."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import learning, sessions


def fact(identity="content-1", kind="content", basis="unverified", **extra):
    return {"id": identity, "kind": kind, "text": "实际学习内容", "basis": basis,
            "sources": [{"ref": "test/user/1", "quote": "用户实际说的话"}], **extra}


def batch(operation="checkpoint-1", events=None, focus=None):
    events = [fact()] if events is None else events
    return {"operation_id": operation, "events": events,
            "handoff": {"summary": "本次实际学习摘要", "next_step": "下次由用户选择主题",
                        "focus_ids": [item["id"] for item in events] if focus is None else focus}}


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="learning-session-")
        self.addCleanup(self.temp.cleanup)
        self.hub = learning.Hub(Path(self.temp.name) / "hub")
        self.hub.initialize()
        self.hub.create_goal("Java", identity="java")
        self.hub.create_track("java", "Java 基础", identity="core")
        self.hub.create_unit("java", "core", "milestone", "集合", "使用集合", ["解释集合使用"])
        self.hub.create_unit("java", "core", "sprint", "ArrayList", "区分 size 与容量",
                             ["在具体例子中判断 size", "解释扩容复制"], milestone="M001")
        self.hub.select("java", "core")
        self.store = self.hub.sessions()

    def start(self, **kwargs):
        return self.store.start("java", "core", kwargs.pop("topic", "ArrayList"),
                                kwargs.pop("request_id", "start-1"), **kwargs)

    def checkpoint(self, identity, payload=None, finish=False):
        return self.store.checkpoint("java", "core", identity, payload or batch(), finish=finish)

    def read(self, identity):
        return json.loads(self.store.path("java", "core", identity, "record.json").read_text(encoding="utf-8"))

    def snapshot(self):
        return {p.relative_to(self.hub.root).as_posix(): p.read_bytes()
                for p in self.hub.root.rglob("*") if p.is_file()}

    def cli(self, *args, payload=None, fail=False):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/learning.py"),
                                 "--hub", str(self.hub.root), *args],
                                input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                                capture_output=True, encoding="utf-8", timeout=30,
                                env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(result.returncode, 2 if fail else 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout if fail else result.stderr, "")
        return json.loads(result.stderr if fail else result.stdout)

    def test_start_persists_stable_id_and_is_retryable(self):
        result = self.start(sprint="SP001")
        self.assertRegex(result["id"], r"^SE-[a-f0-9]{32}$")
        record = self.read(result["id"])
        self.assertEqual(record["status"], "active")
        self.assertEqual(record["sprint_snapshot"]["criteria"], ["在具体例子中判断 size", "解释扩容复制"])
        before = self.snapshot()
        self.assertEqual(self.start(sprint="SP001"), result)
        self.assertEqual(before, self.snapshot())
        with self.assertRaises(learning.LearningError):
            self.start(topic="different")
        with self.assertRaisesRegex(learning.LearningError, "session-resume"):
            self.start(request_id="another")

    def test_incremental_batches_and_retries_preserve_prior_facts(self):
        identity = self.start()["id"]
        first = batch()
        second = batch("checkpoint-2", [fact("question-1", "question", "user_report")], ["content-1", "question-1"])
        self.checkpoint(identity, first)
        self.checkpoint(identity, second)
        before = self.snapshot()
        self.checkpoint(identity, first)
        self.assertEqual(self.snapshot(), before)
        record = self.read(identity)
        self.assertEqual(record["events"], first["events"] + second["events"])
        self.assertEqual(len(record["checkpoints"]), 2)
        changed = copy.deepcopy(first)
        changed["events"][0]["text"] = "改写历史"
        with self.assertRaises(learning.LearningError):
            self.checkpoint(identity, changed)
        self.assertEqual(before, self.snapshot())

    def test_finish_one_question_without_exercises_off_sprint(self):
        identity = self.start(topic="临时网络问题")["id"]
        payload = batch("finish-1", [fact("question-1", "question", "user_report")])
        before_plan = (self.hub._tdir("java", "core") / "state.json").read_bytes()
        result = self.checkpoint(identity, payload, finish=True)
        self.assertEqual(result["status"], "completed")
        note = Path(result["note_path"]).read_text(encoding="utf-8")
        self.assertIn("临时网络问题", note)
        self.assertIn("用户问题", note)
        self.assertIn("用户实际说的话", note)
        self.assertIn("## 练习与批改\n\n未记录。", note)
        self.assertEqual((self.hub._tdir("java", "core") / "state.json").read_bytes(), before_plan)
        self.assertTrue(self.hub.validate()["valid"])

    def test_finish_empty_session_is_allowed(self):
        identity = self.start()["id"]
        result = self.checkpoint(identity, batch("finish", []), finish=True)
        self.assertEqual(result["event_count"], 0)
        self.assertTrue(Path(result["note_path"]).exists())

    def test_finish_idempotency_and_no_reopening(self):
        identity = self.start()["id"]
        payload = batch("finish-1")
        expected = self.checkpoint(identity, payload, finish=True)
        before = self.snapshot()
        self.assertEqual(self.checkpoint(identity, payload, finish=True), expected)
        retry = batch("finish-again", [], ["content-1"])
        self.assertEqual(self.checkpoint(identity, retry, finish=True), expected)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.start()["id"], identity)
        with self.assertRaises(learning.LearningError):
            self.store.resume("java", "core", identity)
        with self.assertRaises(learning.LearningError):
            self.checkpoint(identity, batch("new", [fact("new")]))
        new = self.start(request_id="start-2", previous=identity, topic="用户改学其他内容")
        self.assertNotEqual(new["id"], identity)
        self.assertEqual(self.read(new["id"])["events"], [])
        self.assertEqual(self.read(identity)["status"], "completed")

    def test_resume_after_interruption_in_fresh_process(self):
        identity = self.start()["id"]
        self.checkpoint(identity)
        before = self.snapshot()
        recovered = self.cli("session-resume", "--goal", "java", "--track", "core", "--session", identity)
        self.assertEqual(recovered["session"]["handoff"]["summary"], "本次实际学习摘要")
        self.assertEqual(recovered["session"]["id"], identity)
        self.assertEqual(self.cli("session-context")["mode"], "resume")
        self.assertEqual(before, self.snapshot())

    def test_goal_track_isolation_and_unrelated_corruption_not_loaded(self):
        first = self.start()["id"]
        self.checkpoint(first)
        self.hub.create_track("java", "Other", identity="other")
        self.hub.create_goal("English", identity="english")
        self.hub.create_track("english", "Core", identity="core")
        other = self.store.start("java", "other", "SQL", "start-1")["id"]
        foreign = self.store.start("english", "core", "English", "start-1")["id"]
        self.assertEqual(len({first, other, foreign}), 3)
        self.hub.select("english", "core")
        self.assertEqual(self.store.context()["active_session"]["id"], foreign)
        self.hub.select("java", "core")
        (self.hub._gdir("english") / "state.json").write_text("{broken", encoding="utf-8")
        self.store.path("java", "other", other, "record.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(self.cli("session-context")["active_session"]["id"], first)
        with self.assertRaises(learning.LearningError):
            self.store.resume("java", "core", foreign)

    def test_end_to_end_arraylist_actual_files_and_new_process_continuation(self):
        started = self.cli("session-start", "--goal", "java", "--track", "core", "--sprint", "SP001",
                           "--topic", "Java ArrayList", "--request-id", "arraylist-start")
        identity = started["id"]
        scope = ["--goal", "java", "--track", "core", "--session", identity]
        first = json.loads((ROOT / "resources/examples/session-checkpoint.json").read_text(encoding="utf-8"))
        final = json.loads((ROOT / "resources/examples/session-finish.json").read_text(encoding="utf-8"))
        self.cli("session-checkpoint", *scope, "--data", "-", payload=first)
        result = self.cli("session-finish", *scope, "--data", "-", payload=final)
        record = self.read(identity)
        self.assertEqual(record["events"], first["events"] + final["events"])
        self.assertEqual(record["status"], "completed")
        note = Path(result["note_path"]).read_text(encoding="utf-8")
        for fragment in ("为什么预分配容量后 size 还是 0", "size 与容量仍容易混淆", "扩容复制成本尚不清楚", "用户答案：10", "用户答案：4", "练习验证", "尚未验证", "模拟会话/user/6"):
            self.assertIn(fragment, note)
        before = self.snapshot()
        context = self.cli("session-context")
        self.assertEqual(context["mode"], "new_session")
        self.assertIsNone(context["active_session"])
        last = context["recent_sessions"][0]
        self.assertEqual(last["id"], identity)
        self.assertEqual(len(last["unstable_points"]), 2)
        self.assertEqual(last["verified_abilities"][0]["id"], "evidence-1")
        self.assertEqual(last["unresolved_questions"][0]["id"], "unresolved-1")
        self.assertIn("扩容复制", last["handoff"]["next_step"])
        self.assertEqual(last["note_path"], result["note_path"])
        self.assertEqual(before, self.snapshot())
        next_session = self.cli("session-start", "--goal", "java", "--track", "core", "--topic", "扩容复制",
                                "--request-id", "next-start", "--from-session", identity)
        self.assertEqual(self.read(next_session["id"])["previous_session_id"], identity)
        self.assertEqual(self.cli("session-context")["active_session"]["id"], next_session["id"])
        self.assertEqual(self.hub.get_track("java", "core")["sprints"]["SP001"]["status"], "active")
        self.assertEqual(self.cli("validate")["sessions"], 2)

    def test_context_bounded_and_history_paged_without_reading_old_records(self):
        identities = []
        for number in range(4):
            identity = self.start(request_id=f"start-{number}")["id"]
            self.checkpoint(identity, batch("finish", [fact(f"e-{i}") for i in range(30)], ["e-29"]), finish=True)
            identities.append(identity)
        before = self.snapshot()
        loaded = []
        original = self.store.load
        def observed(goal, track, identity, state):
            loaded.append(identity)
            return original(goal, track, identity, state)
        with mock.patch.object(self.store, "load", side_effect=observed):
            context = self.store.context()
        self.assertEqual(loaded, [identities[-1]])
        self.assertEqual(len(context["recent_sessions"]), 1)
        self.assertNotIn("events", context["recent_sessions"][0])
        self.assertEqual(context["recent_sessions"][0]["omitted_event_count"], 29)
        self.assertEqual([item["id"] for item in self.store.listing(limit=2)["sessions"]], identities[-1:-3:-1])
        page = self.store.show("java", "core", identities[0], offset=20, limit=10)
        self.assertEqual(len(page["events"]), 10)
        self.assertIsNone(page["next_offset"])
        self.assertEqual(before, self.snapshot())

    def test_read_and_start_compatibility_does_not_rewrite_phase1(self):
        before = self.snapshot()
        self.assertEqual(self.store.context()["recent_sessions"], [])
        self.assertEqual(before, self.snapshot())
        identity = self.start()["id"]
        self.checkpoint(identity, finish=True)
        for path, content in before.items():
            self.assertEqual((self.hub.root / path).read_bytes(), content)
        legacy = self.hub.root / "goals/legacy"
        legacy.mkdir()
        (legacy / "goal.md").write_text("旧目标原文", encoding="utf-8")
        snapshot = self.snapshot()
        with self.assertRaises(learning.LearningError):
            self.store.start("legacy", "core", "topic", "start")
        self.assertEqual(snapshot, self.snapshot())

    def test_sprint_snapshot_survives_later_criteria_changes(self):
        identity = self.start(sprint="SP001")["id"]
        self.hub.update("java", "sprint", "用户调整要求", track="core", identity="SP001", criteria=["新标准"])
        evidence = fact("evidence-1", "evidence", "user_report", criterion="在具体例子中判断 size", outcome="met")
        self.checkpoint(identity, batch(events=[evidence]), finish=True)
        self.assertTrue(self.hub.validate()["valid"])
        self.assertEqual(self.store.context()["recent_sessions"][0]["verified_abilities"], [])

    def test_parent_pause_blocks_new_learning_but_preserves_finish(self):
        identity = self.start()["id"]
        self.hub.transition("java", "track", "paused", "暂停", track="core")
        self.assertFalse(self.store.context()["learning_allowed"])
        with self.assertRaises(learning.LearningError):
            self.store.resume("java", "core", identity)
        self.checkpoint(identity, finish=True)
        with self.assertRaises(learning.LearningError):
            self.start(request_id="next")

    def test_corrections_append_without_overwriting_original_facts(self):
        identity = self.start()["id"]
        first = batch()
        self.checkpoint(identity, first)
        correction = fact("corrected", supersedes=["content-1"], text="用户更正了事实")
        self.checkpoint(identity, batch("correct", [correction]))
        self.assertEqual(self.read(identity)["events"][0], first["events"][0])
        self.assertEqual(self.store.context()["active_session"]["focus"][0]["id"], "corrected")
        with self.assertRaises(learning.LearningError):
            self.checkpoint(identity, batch("stale-handoff", [], ["content-1"]))

    def test_invalid_batches_and_unsupported_claims_leave_files_unchanged(self):
        identity = self.start(sprint="SP001")["id"]
        invalid = [fact(basis="mastered"), fact(sources=[]), fact(related_ids=["missing"]),
                   fact("x", "understanding", "ai_assessment", understanding="understood"),
                   fact("x", "explanation", "exercise_verified"),
                   fact("x", "evidence", "exercise_verified", criterion="在具体例子中判断 size", outcome="met"),
                   fact("x", "evidence", "user_report", criterion="不属于快照", outcome="met"),
                   fact("x", "exercise", "exercise_verified", prompt="题目", answer="", result="correct", feedback="正确")]
        before = self.snapshot()
        for event in invalid:
            with self.subTest(event=event):
                with self.assertRaises(learning.LearningError):
                    self.checkpoint(identity, batch(events=[fact("valid"), event]))
                self.assertEqual(before, self.snapshot())

    def test_structured_cli_errors_and_json_file_input(self):
        self.cli("session-context", "--goal", "java", fail=True)
        self.cli("session-context", "--limit", "0", fail=True)
        self.cli("session-start", "--goal", "java", "--track", "core", "--topic", "X", fail=True)
        identity = self.start()["id"]
        for payload in ({}, {"operation_id": "x", "events": None, "handoff": None}):
            self.cli("session-checkpoint", "--goal", "java", "--track", "core", "--session", identity,
                     "--data", "-", payload=payload, fail=True)
        data = Path(self.temp.name) / "payload.json"
        data.write_text(json.dumps(batch()), encoding="utf-8-sig")
        self.cli("session-checkpoint", "--goal", "java", "--track", "core", "--session", identity, "--data", str(data))

    def test_record_replace_failure_keeps_existing_bytes(self):
        identity = self.start()["id"]
        self.checkpoint(identity)
        before = self.snapshot()
        original = sessions._save
        def fail(path, value):
            if path.name == "record.json":
                raise OSError("disk full")
            return original(path, value)
        with mock.patch.object(sessions, "_save", side_effect=fail):
            with self.assertRaises(OSError):
                self.checkpoint(identity, batch("finish", []), finish=True)
        self.assertEqual(before, self.snapshot())
        self.assertTrue(self.hub.validate()["valid"])

    def test_actual_atomic_replace_failure_preserves_record(self):
        identity = self.start()["id"]
        before = self.snapshot()
        with mock.patch.object(learning.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                self.checkpoint(identity)
        self.assertEqual(before, self.snapshot())

    def test_crash_after_record_commit_recovered_without_duplicate_events(self):
        identity = self.start()["id"]
        payload = batch("finish")
        real_replace = learning.os.replace
        def interrupt_after(source, target):
            real_replace(source, target)
            if Path(target).name == "record.json":
                raise OSError("process interrupted after commit")
        with mock.patch.object(learning.os, "replace", side_effect=interrupt_after):
            with self.assertRaises(OSError):
                self.checkpoint(identity, payload, finish=True)
        self.assertEqual(self.read(identity)["status"], "completed")
        context = self.cli("session-context")
        self.assertEqual(context["mode"], "new_session")
        self.assertEqual(context["index_status"], "rebuilt_in_memory")
        with self.assertRaises(learning.LearningError):
            self.hub.validate()
        self.checkpoint(identity, payload, finish=True)
        self.assertEqual(len(self.read(identity)["events"]), 1)
        self.assertTrue(self.hub.validate()["valid"])

    def test_note_failure_repaired_from_canonical_record(self):
        identity = self.start()["id"]
        payload = batch("finish")
        with mock.patch.object(sessions, "_atomic", side_effect=OSError("note write failed")):
            with self.assertRaises(OSError):
                self.checkpoint(identity, payload, finish=True)
        record_bytes = self.store.path("java", "core", identity, "record.json").read_bytes()
        self.cli("session-repair", "--goal", "java", "--track", "core")
        self.assertEqual(self.store.path("java", "core", identity, "record.json").read_bytes(), record_bytes)
        self.assertTrue(self.hub.validate()["valid"])

    def test_start_index_failure_retry_returns_original_id(self):
        original = sessions._save
        def fail_index(path, value):
            if path.name == "index.json":
                raise OSError("index failed")
            return original(path, value)
        with mock.patch.object(sessions, "_save", side_effect=fail_index):
            with self.assertRaises(OSError):
                self.start()
        context = self.store.context()
        identity = context["active_session"]["id"]
        self.assertEqual(self.start()["id"], identity)
        self.assertEqual(self.hub.validate()["sessions"], 1)

    def test_missing_index_read_rebuild_and_explicit_repair(self):
        identity = self.start()["id"]
        self.checkpoint(identity, finish=True)
        index = self.store.directory("java", "core") / "index.json"
        index.unlink()
        before = self.snapshot()
        self.assertEqual(self.cli("session-context")["recent_sessions"][0]["id"], identity)
        self.assertEqual(before, self.snapshot())
        self.store.repair("java", "core")
        self.assertTrue(self.hub.validate()["valid"])

    def test_corruption_is_detected_without_overwrite(self):
        identity = self.start()["id"]
        self.checkpoint(identity)
        path = self.store.path("java", "core", identity, "record.json")
        value = self.read(identity)
        value["events"][0]["text"] = "篡改旧事实"
        path.write_text(json.dumps(value), encoding="utf-8")
        before = self.snapshot()
        for operation in (self.store.context, self.hub.validate, lambda: self.store.repair("java", "core")):
            with self.assertRaises(learning.LearningError):
                operation()
        self.assertEqual(before, self.snapshot())

    def test_conflicting_note_is_preserved(self):
        identity = self.start()["id"]
        result = self.checkpoint(identity, finish=True)
        Path(result["note_path"]).write_text("用户额外记录", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaisesRegex(learning.LearningError, "冲突"):
            self.store.repair("java", "core")
        with self.assertRaises(learning.LearningError):
            self.checkpoint(identity, finish=True)
        self.assertEqual(before, self.snapshot())

    def test_cross_process_lock_rejects_mutation(self):
        identity = self.start()["id"]
        before = self.snapshot()
        with self.hub._lock():
            error = self.cli("session-checkpoint", "--goal", "java", "--track", "core", "--session", identity,
                             "--data", "-", payload=batch(), fail=True)
            self.assertIn("写锁", error["error"])
        self.assertEqual(before, self.snapshot())

    def test_unsafe_session_id_and_symlink_protection(self):
        identity = self.start()["id"]
        before = self.snapshot()
        for bad in ("../escape", "SE-../escape", "con", "", "SE-" + "0" * 33):
            with self.assertRaises(learning.LearningError):
                self.store.resume("java", "core", bad)
        self.assertEqual(before, self.snapshot())
        record_path = self.store.path("java", "core", identity, "record.json")
        original = Path.is_symlink
        with mock.patch.object(Path, "is_symlink", lambda path: path == record_path or original(path)):
            with self.assertRaisesRegex(learning.LearningError, "链接"):
                self.store.context()

    def test_corrupt_derived_index_is_readable_and_repairable(self):
        identity = self.start()["id"]
        self.checkpoint(identity)
        path = self.store.directory("java", "core") / "index.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        bad_entry = copy.deepcopy(original)
        bad_entry["entries"] = [{"id": identity}]
        bad_entry["digest"] = sessions.digest(bad_entry["entries"])
        for damaged in ("{broken", json.dumps(bad_entry)):
            path.write_text(damaged, encoding="utf-8")
            before = self.snapshot()
            context = self.cli("session-context")
            self.assertEqual(context["active_session"]["id"], identity)
            self.assertEqual(context["index_status"], "rebuilt_in_memory")
            self.assertEqual(before, self.snapshot())
            self.store.repair("java", "core")
            self.assertTrue(self.hub.validate()["valid"])

    def test_missing_note_is_visible_and_finish_retry_repairs_it(self):
        identity = self.start()["id"]
        result = self.checkpoint(identity, finish=True)
        Path(result["note_path"]).unlink()
        self.assertFalse(self.store.context()["recent_sessions"][0]["note_exists"])
        recovered = self.checkpoint(identity, finish=True)
        self.assertTrue(recovered["note_exists"])
        self.assertEqual(recovered["event_count"], 1)

    def test_unknown_session_version_and_scope_are_rejected(self):
        identity = self.start()["id"]
        path = self.store.path("java", "core", identity, "record.json")
        original = self.read(identity)
        for key, value in (("session_version", 99), ("schema_version", 3), ("goal_id", "foreign"),
                           ("status", "paused"), ("events", None), ("created_at", "yesterday")):
            changed = {**original, key: value}
            path.write_text(json.dumps(changed), encoding="utf-8")
            before = self.snapshot()
            self.cli("session-context", fail=True)
            self.assertEqual(before, self.snapshot())

    def test_correcting_exercise_invalidates_old_verified_claim(self):
        identity = self.start(sprint="SP001")["id"]
        exercise = fact("exercise-1", "exercise", "exercise_verified", prompt="题目", answer="2", result="correct", feedback="正确")
        evidence = fact("evidence-1", "evidence", "exercise_verified", criterion="在具体例子中判断 size",
                        outcome="met", related_ids=["exercise-1"])
        self.checkpoint(identity, batch(events=[exercise, evidence]))
        corrected = {**exercise, "id": "exercise-2", "result": "incorrect", "feedback": "重新核对为错误", "supersedes": ["exercise-1"]}
        before = self.snapshot()
        with self.assertRaises(learning.LearningError):
            self.checkpoint(identity, batch("corrected", [corrected], ["evidence-1"]))
        self.assertEqual(before, self.snapshot())
        self.checkpoint(identity, batch("corrected", [corrected]))
        self.assertEqual(self.store.context()["active_session"]["verified_abilities"], [])

    def test_start_from_active_and_foreign_session_rejected(self):
        identity = self.start()["id"]
        self.hub.create_track("java", "Other", identity="other")
        before = self.snapshot()
        with self.assertRaises(learning.LearningError):
            self.store.start("java", "other", "Other", "request", previous=identity)
        with self.assertRaises(learning.LearningError):
            self.start(request_id="new", previous=identity)
        self.assertEqual(before, self.snapshot())

    def test_later_batch_validation_failure_is_atomic(self):
        identity = self.start()["id"]
        payload = batch(events=[fact("valid"), fact("invalid", basis="unknown")])
        before = self.snapshot()
        self.cli("session-finish", "--goal", "java", "--track", "core", "--session", identity,
                 "--data", "-", payload=payload, fail=True)
        self.assertEqual(before, self.snapshot())

    def test_nonfinite_retry_payload_returns_structured_error(self):
        identity = self.start()["id"]
        self.checkpoint(identity)
        bad = batch()
        bad["events"][0]["text"] = float("inf")
        before = self.snapshot()
        with self.assertRaises(learning.LearningError):
            self.checkpoint(identity, bad)
        self.assertEqual(before, self.snapshot())

    def test_stdin_is_utf8_even_when_host_uses_other_encoding(self):
        identity = self.start()["id"]
        payload = batch()
        result = subprocess.run([sys.executable, str(ROOT / "scripts/learning.py"), "--hub", str(self.hub.root),
                                 "session-checkpoint", "--goal", "java", "--track", "core", "--session", identity,
                                 "--data", "-"], input=json.dumps(payload, ensure_ascii=False),
                                encoding="utf-8", capture_output=True, timeout=30,
                                env={**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read(identity)["events"][0]["sources"], payload["events"][0]["sources"])

    def completed_evidence(self):
        identity = self.start(sprint="SP001")["id"]
        exercise = fact("ex-1", "exercise", "exercise_verified", prompt="两个元素的 size？", answer="10",
                        result="correct", feedback="原批改有误")
        evidence = fact("claim-1", "evidence", "exercise_verified", criterion="在具体例子中判断 size",
                        outcome="met", related_ids=["ex-1"])
        payload = batch("original-finish", [exercise, evidence])
        self.checkpoint(identity, payload, finish=True)
        correction = batch("correct-after-finish", [
            {**exercise, "id": "ex-2", "result": "incorrect", "feedback": "答案应为 2，原批改错误", "supersedes": ["ex-1"]}
        ])
        correction["reason"] = "结束后核对题目，发现把容量当作 size 的答案被误判为正确"
        correction["handoff"]["summary"] = "原达标结论撤回，size 与容量仍需区分"
        return identity, payload, correction

    def test_review2_completed_session_can_correct_without_reopening(self):
        identity, original_payload, correction = self.completed_evidence()
        original = self.read(identity)
        plan = (self.hub._tdir("java", "core") / "state.json").read_bytes()
        with self.assertRaises(learning.LearningError):
            self.checkpoint(identity, batch("ordinary-append", correction["events"]))
        # A linked new Session cannot supersede foreign facts, and a plain
        # explanation there cannot retract the original record's claim.
        active = self.start(request_id="later", previous=identity)["id"]
        with self.assertRaises(learning.LearningError):
            self.checkpoint(active, batch("foreign-correction", correction["events"]))
        self.checkpoint(active, batch("explanation", [fact("later-explanation", "explanation", "ai_assessment")]))
        self.assertEqual(self.store.show("java", "core", identity)["event_validity"]["claim-1"]["status"], "current")
        active_bytes = self.store.path("java", "core", active, "record.json").read_bytes()
        result = self.cli("session-correct", "--goal", "java", "--track", "core", "--session", identity,
                          "--data", "-", payload=correction)
        saved = self.read(identity)
        self.assertEqual(saved["session_version"], 2)
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["completed_at"], original["completed_at"])
        self.assertEqual(saved["events"][:2], original["events"])
        self.assertEqual(saved["checkpoints"][:1], original["checkpoints"])
        self.assertEqual(saved["checkpoints"][-1]["reason"], correction["reason"])
        shown = self.cli("session-show", "--goal", "java", "--track", "core", "--session", identity)
        self.assertEqual(shown["verified_abilities"], [])
        self.assertEqual(shown["event_validity"]["claim-1"]["status"], "invalidated")
        note = Path(result["note_path"]).read_text(encoding="utf-8")
        self.assertIn("依据已失效", note)
        self.assertIn(correction["reason"], note)
        self.assertEqual(self.store.path("java", "core", active, "record.json").read_bytes(), active_bytes)
        self.assertEqual((self.hub._tdir("java", "core") / "state.json").read_bytes(), plan)
        self.assertTrue(self.cli("validate")["valid"])

    def test_review2_list_can_reach_session_101_in_new_process(self):
        identities = []
        for number in range(101):
            identity = self.start(request_id=f"history-{number}")["id"]
            self.checkpoint(identity, batch("finish", []), finish=True)
            identities.append(identity)
        before = self.snapshot()
        first = self.cli("session-list", "--limit", "100")
        self.assertEqual(first["total"], 101)
        self.assertEqual(len(first["sessions"]), 100)
        last = self.cli("session-list", "--limit", "100", "--offset", "100")
        self.assertEqual(first["next_offset"], 100)
        self.assertEqual(last["offset"], 100)
        self.assertIsNone(last["next_offset"])
        self.assertEqual([item["id"] for item in last["sessions"]], [identities[0]])
        self.assertEqual({item["id"] for item in first["sessions"] + last["sessions"]}, set(identities))
        self.assertEqual(before, self.snapshot())

    def test_review2_reversed_checkpoint_returns_path_in_json_error(self):
        identity, _, _ = self.completed_evidence()
        record = self.read(identity)
        record["checkpoints"][0]["event_ids"].reverse()
        path = self.store.path("java", "core", identity, "record.json")
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        before = self.snapshot()
        error = self.cli("session-context", fail=True)
        self.assertIn(str(path), error["error"])
        self.assertEqual(before, self.snapshot())

    def test_review2_correction_retries_and_second_correction_preserve_history(self):
        identity, finish_payload, correction = self.completed_evidence()
        original = self.read(identity)
        self.store.correct("java", "core", identity, correction)
        before = self.snapshot()
        self.store.correct("java", "core", identity, correction)
        self.checkpoint(identity, finish_payload, finish=True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.read(identity)["handoff"], correction["handoff"])
        second = copy.deepcopy(correction)
        second["operation_id"] = "correction-two"
        second["reason"] = "进一步核对批改说明"
        second["events"][0].update(id="ex-3", supersedes=["ex-2"], feedback="补充说明：容量不决定 size")
        second["handoff"]["focus_ids"] = ["ex-3"]
        self.store.correct("java", "core", identity, second)
        saved = self.read(identity)
        self.assertEqual(len(saved["checkpoints"]), 3)
        self.assertEqual(saved["completed_at"], original["completed_at"])
        self.assertEqual(saved["checkpoints"][:1], original["checkpoints"])
        before = self.snapshot()
        self.store.correct("java", "core", identity, correction)
        self.assertEqual(before, self.snapshot())
        changed = copy.deepcopy(correction)
        changed["reason"] = "相同请求键但理由不同"
        with self.assertRaises(learning.LearningError):
            self.store.correct("java", "core", identity, changed)
        self.assertEqual(before, self.snapshot())
        self.assertTrue(self.hub.validate()["valid"])

    def test_review2_correction_rejects_unrelated_or_invalid_payload_atomically(self):
        identity, _, correction = self.completed_evidence()
        cases = []
        for key, value in (("reason", ""), ("events", []), ("events", [fact("unrelated")]),
                           ("handoff", {**correction["handoff"], "focus_ids": ["claim-1"]})):
            cases.append({**copy.deepcopy(correction), key: value})
        cases.append({**copy.deepcopy(correction), "events": correction["events"] + [fact("unrelated")]})
        cases.append({**copy.deepcopy(correction), "operation_id": "original-finish"})
        cases.append({key: value for key, value in correction.items() if key != "reason"})
        before = self.snapshot()
        for payload in cases:
            with self.subTest(payload=payload):
                self.cli("session-correct", "--goal", "java", "--track", "core", "--session", identity,
                         "--data", "-", payload=payload, fail=True)
                self.assertEqual(before, self.snapshot())
        self.hub.create_track("java", "Other", identity="other")
        before = self.snapshot()
        self.cli("session-correct", "--goal", "java", "--track", "other", "--session", identity,
                 "--data", "-", payload=correction, fail=True)
        self.assertEqual(before, self.snapshot())
        active = self.start(request_id="still-active")["id"]
        before = self.snapshot()
        self.cli("session-correct", "--goal", "java", "--track", "core", "--session", active,
                 "--data", "-", payload=correction, fail=True)
        self.assertEqual(before, self.snapshot())

    def test_review2_corrected_predecessor_used_by_new_process(self):
        identity, _, correction = self.completed_evidence()
        active = self.start(request_id="continue", previous=identity)["id"]
        self.store.correct("java", "core", identity, correction)
        context = self.cli("session-context")
        self.assertEqual(context["continuation"]["handoff"], correction["handoff"])
        self.assertEqual(context["recent_sessions"][0]["verified_abilities"], [])
        resumed = self.cli("session-resume", "--goal", "java", "--track", "core", "--session", active)
        self.assertEqual(resumed["reference_session"]["verified_abilities"], [])
        self.assertEqual(resumed["continuation"], context["continuation"])
        self.assertEqual(self.read(active)["session_version"], 1)
        self.assertTrue(self.cli("validate")["valid"])

    def test_review2_correction_keeps_completed_time_and_recency_after_pause(self):
        identity, _, correction = self.completed_evidence()
        original = self.read(identity)
        recent = self.start(request_id="newer")["id"]
        self.checkpoint(recent, batch("finish", []), finish=True)
        self.hub.transition("java", "goal", "paused", "暂时暂停")
        self.store.correct("java", "core", identity, correction)
        self.assertEqual(self.read(identity)["completed_at"], original["completed_at"])
        self.assertGreaterEqual(self.read(identity)["updated_at"], original["updated_at"])
        self.assertEqual(self.store.context()["recent_sessions"][0]["id"], recent)
        self.assertTrue(self.hub.validate()["valid"])

    def test_review2_correction_preserves_manually_edited_note(self):
        identity, _, correction = self.completed_evidence()
        note = self.store.path("java", "core", identity, "note.md")
        note.write_text(note.read_text(encoding="utf-8") + "\n用户补充\n", encoding="utf-8")
        before = self.snapshot()
        self.cli("session-correct", "--goal", "java", "--track", "core", "--session", identity,
                 "--data", "-", payload=correction, fail=True)
        self.assertEqual(before, self.snapshot())

    def test_review2_correction_commit_failure_preserves_all_bytes(self):
        identity, _, correction = self.completed_evidence()
        before = self.snapshot()
        with mock.patch.object(learning.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                self.store.correct("java", "core", identity, correction)
        self.assertEqual(before, self.snapshot())

    def test_review2_correction_note_failure_is_retryable_from_history(self):
        identity, _, correction = self.completed_evidence()
        note = self.store.path("java", "core", identity, "note.md")
        old_note = note.read_bytes()
        with mock.patch.object(sessions, "_atomic", side_effect=OSError("note failed")):
            with self.assertRaises(OSError):
                self.store.correct("java", "core", identity, correction)
        canonical = self.store.path("java", "core", identity, "record.json").read_bytes()
        self.assertEqual(note.read_bytes(), old_note)
        self.assertEqual(self.cli("session-context")["recent_sessions"][0]["verified_abilities"], [])
        self.cli("validate", fail=True)
        self.cli("session-correct", "--goal", "java", "--track", "core", "--session", identity,
                 "--data", "-", payload=correction)
        self.assertEqual(self.store.path("java", "core", identity, "record.json").read_bytes(), canonical)
        self.assertIn("依据已失效", note.read_text(encoding="utf-8"))
        self.assertTrue(self.hub.validate()["valid"])

    def test_review2_repair_accepts_historical_generated_note_but_not_edits(self):
        identity, _, correction = self.completed_evidence()
        note = self.store.path("java", "core", identity, "note.md")
        old_note = note.read_bytes()
        self.store.correct("java", "core", identity, correction)
        current = note.read_bytes()
        record_bytes = self.store.path("java", "core", identity, "record.json").read_bytes()
        note.write_bytes(old_note + b"\nuser addition\n")
        before = self.snapshot()
        self.cli("session-repair", "--goal", "java", "--track", "core", fail=True)
        self.assertEqual(before, self.snapshot())
        note.write_bytes(old_note)
        self.cli("session-repair", "--goal", "java", "--track", "core")
        self.assertEqual(note.read_bytes(), current)
        self.assertEqual(self.store.path("java", "core", identity, "record.json").read_bytes(), record_bytes)

    def test_review2_pagination_boundaries_and_selected_page_reads(self):
        prior, recent, active = self.continuation_fixture()
        with mock.patch.object(self.store, "load", wraps=self.store.load) as loads:
            page = self.store.listing(limit=1, offset=2)
        self.assertEqual([call.args[2] for call in loads.call_args_list], [prior])
        self.assertIsNone(page["next_offset"])
        self.assertEqual(self.cli("session-list", "--offset", "3")["sessions"], [])
        self.assertEqual(self.cli("session-list", "--offset", "999")["sessions"], [])
        for args in (("--offset", "-1"), ("--offset", "oops"), ("--limit", "101"), ("--limit", "0")):
            self.cli("session-list", *args, fail=True)
        before = self.snapshot()
        for value in (True, 1.5, -1, "2"):
            with self.assertRaises(learning.LearningError):
                self.store.listing(offset=value)
        self.assertEqual(before, self.snapshot())

    def test_review2_correction_index_failure_and_missing_note_repair(self):
        identity, _, correction = self.completed_evidence()
        real_save = sessions._save
        def fail_index(path, value):
            if path.name == "index.json":
                raise OSError("index failed")
            return real_save(path, value)
        with mock.patch.object(sessions, "_save", side_effect=fail_index):
            with self.assertRaises(OSError):
                self.store.correct("java", "core", identity, correction)
        path = self.store.path("java", "core", identity, "record.json")
        canonical = path.read_bytes()
        self.assertEqual(self.cli("session-context")["recent_sessions"][0]["verified_abilities"], [])
        self.store.path("java", "core", identity, "note.md").unlink()
        self.cli("session-repair", "--goal", "java", "--track", "core")
        self.assertEqual(path.read_bytes(), canonical)
        self.assertTrue(self.cli("validate")["valid"])

    def test_review2_correction_survives_child_exit_after_commit(self):
        identity, _, correction = self.completed_evidence()
        child = """
import os, sys
from pathlib import Path
from scripts import learning, sessions
save = sessions._save
def exit_after_commit(path, value):
    save(path, value)
    if path.name == 'record.json':
        os._exit(73)
sessions._save = exit_after_commit
raise SystemExit(learning.main(sys.argv[1:]))
"""
        result = subprocess.run([sys.executable, "-B", "-c", child, "--hub", str(self.hub.root),
                                 "session-correct", "--goal", "java", "--track", "core", "--session", identity,
                                 "--data", "-"], cwd=ROOT, input=json.dumps(correction, ensure_ascii=False),
                                capture_output=True, encoding="utf-8", timeout=30, env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertEqual(result.stdout, "")
        path = self.store.path("java", "core", identity, "record.json")
        canonical = path.read_bytes()
        self.assertEqual(self.cli("session-context")["recent_sessions"][0]["verified_abilities"], [])
        before = self.snapshot()
        self.cli("session-correct", "--goal", "java", "--track", "core", "--session", identity,
                 "--data", "-", payload=correction, fail=True)
        self.assertEqual(before, self.snapshot())
        # This test has waited for its own child to exit. Production recovery
        # still requires an operator to establish that no writer remains.
        (self.hub.root / ".write.lock").unlink()
        self.cli("session-repair", "--goal", "java", "--track", "core")
        self.cli("session-correct", "--goal", "java", "--track", "core", "--session", identity,
                 "--data", "-", payload=correction)
        self.assertEqual(path.read_bytes(), canonical)
        self.assertEqual(len(self.read(identity)["checkpoints"]), 2)
        self.assertTrue(self.cli("validate")["valid"])

    def test_review2_corrupt_checkpoint_dependencies_are_structured_and_readonly(self):
        identity, _, correction = self.completed_evidence()
        self.store.correct("java", "core", identity, correction)
        original = self.read(identity)
        path = self.store.path("java", "core", identity, "record.json")
        variants = []
        for event_ids in (["claim-1"], ["ex-1", "ex-1"], ["missing"], None):
            value = copy.deepcopy(original)
            value["checkpoints"][0]["event_ids"] = event_ids
            variants.append(value)
        value = copy.deepcopy(original)
        del value["checkpoints"][-1]["reason"]
        variants.append(value)
        value = copy.deepcopy(original)
        value["session_version"] = 1
        variants.append(value)
        value = copy.deepcopy(original)
        value["checkpoints"][1]["kind"] = "checkpoint"
        variants.append(value)
        value = copy.deepcopy(original)
        value["completed_at"] = value["updated_at"]
        variants.append(value)
        for damaged in variants:
            with self.subTest(damaged=damaged):
                path.write_text(json.dumps(damaged, ensure_ascii=False), encoding="utf-8")
                before = self.snapshot()
                for args in (("session-context",), ("validate",), ("session-repair", "--goal", "java", "--track", "core")):
                    self.assertIn(str(path), self.cli(*args, fail=True)["error"])
                    self.assertEqual(before, self.snapshot())

    def corrected_session(self):
        identity = self.start(sprint="SP001")["id"]
        exercise = fact("exercise-1", "exercise", "exercise_verified", prompt="题目", answer="2", result="correct", feedback="正确")
        evidence = fact("evidence-1", "evidence", "exercise_verified", criterion="在具体例子中判断 size",
                        outcome="met", related_ids=["exercise-1"])
        self.checkpoint(identity, batch(events=[exercise, evidence]))
        corrected = {**exercise, "id": "exercise-2", "result": "incorrect", "feedback": "重新核对为错误", "supersedes": ["exercise-1"]}
        self.checkpoint(identity, batch("corrected", [corrected]))
        result = self.checkpoint(identity, batch("finish", [], ["exercise-2"]), finish=True)
        return identity, result

    def test_review_corrected_evidence_is_marked_in_finished_note(self):
        identity, result = self.corrected_session()
        original = self.read(identity)
        note = Path(result["note_path"]).read_text(encoding="utf-8")
        exercise_section = note.split("### exercise-1", 1)[1].split("###", 1)[0]
        evidence_section = note.split("### evidence-1", 1)[1].split("## 下一次交接", 1)[0]
        self.assertIn("已更正", exercise_section)
        self.assertIn("exercise-2", exercise_section)
        self.assertIn("依据已失效", evidence_section)
        self.assertIn("exercise-1", evidence_section)
        self.assertIn("exercise-2", evidence_section)
        self.assertIn("历史证据判断：met", evidence_section)
        context = self.cli("session-context")
        self.assertEqual(context["recent_sessions"][0]["verified_abilities"], [])
        self.assertEqual(self.read(identity), original)
        self.assertTrue(self.cli("validate")["valid"])

    def continuation_fixture(self):
        prior = self.start(request_id="a", topic="用户选择的旧主题 A")["id"]
        prior_payload = batch("finish-a")
        prior_payload["handoff"]["summary"] = "A 的真实学习记录"
        prior_payload["handoff"]["next_step"] = "继续 A 的未解决问题"
        self.checkpoint(prior, prior_payload, finish=True)
        recent = self.start(request_id="b", topic="较新的另一个主题 B")["id"]
        recent_payload = batch("finish-b")
        recent_payload["handoff"]["summary"] = "B 的真实学习记录"
        self.checkpoint(recent, recent_payload, finish=True)
        active = self.start(request_id="c", topic="继续 A", previous=prior)["id"]
        return prior, recent, active

    def test_review_empty_session_resumes_explicit_predecessor_in_fresh_process(self):
        prior, recent, active = self.continuation_fixture()
        before = self.snapshot()
        context = self.cli("session-context")
        self.assertEqual(context["recent_sessions"][0]["id"], prior)
        self.assertEqual(context["continuation"]["source_session_id"], prior)
        self.assertEqual(context["continuation"]["handoff"]["summary"], "A 的真实学习记录")
        self.assertEqual(context["active_session"]["id"], active)
        self.assertIsNone(context["active_session"]["handoff"])
        resumed = self.cli("session-resume", "--goal", "java", "--track", "core", "--session", active)
        self.assertEqual(resumed["continuation"], context["continuation"])
        self.assertEqual(resumed["reference_session"]["id"], prior)
        self.assertEqual(resumed["session"]["event_count"], 0)
        self.assertEqual(before, self.snapshot())

    def test_review_checkpoint_does_not_load_unchanged_session_history(self):
        for number in range(2):
            identity = self.start(request_id=f"old-{number}")["id"]
            self.checkpoint(identity, batch("finish"), finish=True)
        active = self.start(request_id="current")["id"]
        with mock.patch.object(self.store, "load", wraps=self.store.load) as loads:
            self.checkpoint(active)
        loaded_ids = [call.args[2] for call in loads.call_args_list]
        self.assertEqual(loaded_ids, [active, active])
        self.assertTrue(self.hub.validate()["valid"])

    def legacy_corrected_note(self, record):
        template = (ROOT / "tests/fixtures/session-note-before-validity.md").read_text(encoding="utf-8")
        return (template.replace("__SESSION_ID__", record["id"])
                .replace("__CREATED_AT__", record["created_at"]).replace("__COMPLETED_AT__", record["completed_at"]))

    def test_review_old_generated_note_requires_explicit_safe_upgrade(self):
        identity, result = self.corrected_session()
        record = self.read(identity)
        legacy = self.legacy_corrected_note(record)
        self.assertEqual(legacy, sessions.render_note(record, annotate_validity=False))
        path = Path(result["note_path"])
        path.write_text(legacy, encoding="utf-8", newline="\n")
        before = self.snapshot()
        self.cli("validate", fail=True)
        self.cli("session-context")
        with self.assertRaisesRegex(learning.LearningError, "旧版笔记"):
            self.checkpoint(identity, batch("finish", [], ["exercise-2"]), finish=True)
        self.assertEqual(before, self.snapshot())
        self.cli("session-repair", "--goal", "java", "--track", "core")
        self.assertIn("依据已失效", path.read_text(encoding="utf-8"))
        after = self.snapshot()
        changed = [key for key in before if before[key] != after[key]]
        self.assertEqual(changed, [path.relative_to(self.hub.root).as_posix()])
        self.assertTrue(self.cli("validate")["valid"])
        self.store.repair("java", "core")
        self.assertEqual(after, self.snapshot())

    def test_review_old_note_with_user_edit_is_never_overwritten(self):
        identity, result = self.corrected_session()
        note = self.legacy_corrected_note(self.read(identity)) + "\n用户补充：还需要核对批改。\n"
        Path(result["note_path"]).write_text(note, encoding="utf-8", newline="\n")
        before = self.snapshot()
        self.cli("session-repair", "--goal", "java", "--track", "core", fail=True)
        self.assertEqual(before, self.snapshot())

    def test_review_failed_note_upgrade_preserves_old_bytes(self):
        identity, result = self.corrected_session()
        path = Path(result["note_path"])
        path.write_text(self.legacy_corrected_note(self.read(identity)), encoding="utf-8", newline="\n")
        before = self.snapshot()
        with mock.patch.object(learning.os, "replace", side_effect=OSError("upgrade interrupted")):
            with self.assertRaises(OSError):
                self.store.repair("java", "core")
        self.assertEqual(before, self.snapshot())

    def test_review_invalidation_cascades_and_new_evidence_stays_current(self):
        identity = self.start(sprint="SP001")["id"]
        original = fact("e-1", "exercise", "exercise_verified", prompt="题目", answer="2", result="correct", feedback="正确")
        first = fact("claim-1", "evidence", "exercise_verified", criterion="在具体例子中判断 size",
                     outcome="met", related_ids=["e-1"])
        dependent = {**first, "id": "claim-2", "related_ids": ["e-1", "claim-1"]}
        self.checkpoint(identity, batch(events=[original, first, dependent]))
        corrected = {**original, "id": "e-2", "result": "incorrect", "feedback": "先前批改有误", "supersedes": ["e-1"]}
        self.checkpoint(identity, batch("correction", [corrected]))
        new_exercise = {**original, "id": "e-3", "prompt": "另外一个例子", "answer": "独立作答"}
        new_evidence = {**first, "id": "claim-3", "related_ids": ["e-3"]}
        result = self.checkpoint(identity, batch("finish", [new_exercise, new_evidence]), finish=True)
        shown = self.cli("session-show", "--goal", "java", "--track", "core", "--session", identity)
        validity = shown["event_validity"]
        self.assertEqual(validity["e-1"]["status"], "superseded")
        self.assertEqual(validity["claim-2"]["status"], "invalidated")
        self.assertEqual(validity["claim-2"]["correction_ids"], ["e-2"])
        self.assertEqual(validity["claim-3"]["status"], "current")
        self.assertEqual([event["id"] for event in shown["verified_abilities"]], ["claim-3"])
        note = Path(result["note_path"]).read_text(encoding="utf-8")
        self.assertIn("历史证据判断：met", note.split("### claim-2", 1)[1].split("### claim-3", 1)[0])
        self.assertNotIn("依据已失效", note.split("### claim-3", 1)[1])
        self.assertEqual(self.read(identity)["events"][:3], [original, first, dependent])
        self.assertTrue(self.hub.validate()["valid"])

    def test_review_recovery_reads_only_one_explicit_predecessor(self):
        prior, recent, active = self.continuation_fixture()
        with mock.patch.object(self.store, "load", wraps=self.store.load) as loads:
            context = self.store.context()
        self.assertEqual([call.args[2] for call in loads.call_args_list], [active, prior])
        self.assertEqual(context["recent_order"], "explicit_predecessor_first")
        with mock.patch.object(self.store, "load", wraps=self.store.load) as loads:
            self.store.resume("java", "core", active)
        self.assertEqual([call.args[2] for call in loads.call_args_list], [active, prior])
        expanded = self.store.context(limit=2)
        self.assertEqual([item["id"] for item in expanded["recent_sessions"]], [prior, recent])
        self.assertEqual([item["id"] for item in self.store.listing()["sessions"]], [active, recent, prior])

    def test_review_current_checkpoint_takes_priority_over_predecessor(self):
        prior, recent, active = self.continuation_fixture()
        payload = batch()
        payload["handoff"]["summary"] = "C 已经开始自己的学习"
        self.checkpoint(active, payload)
        with mock.patch.object(self.store, "load", wraps=self.store.load) as loads:
            resumed = self.store.resume("java", "core", active)
        self.assertEqual([call.args[2] for call in loads.call_args_list], [active])
        self.assertIsNone(resumed["reference_session"])
        self.assertEqual(resumed["continuation"]["source"], "current_session")
        self.assertEqual(resumed["continuation"]["handoff"], payload["handoff"])
        context = self.cli("session-context")
        self.assertEqual(context["continuation"], resumed["continuation"])
        self.assertEqual(context["recent_sessions"][0]["id"], recent)

    def test_review_missing_or_corrupt_predecessor_never_falls_back(self):
        prior, recent, active = self.continuation_fixture()
        path = self.store.path("java", "core", prior, "record.json")
        path.unlink()
        before = self.snapshot()
        self.cli("session-resume", "--goal", "java", "--track", "core", "--session", active, fail=True)
        self.cli("session-context", fail=True)
        self.assertEqual(before, self.snapshot())
        path.write_text("{broken", encoding="utf-8")
        before = self.snapshot()
        self.cli("session-resume", "--goal", "java", "--track", "core", "--session", active, fail=True)
        self.cli("session-context", fail=True)
        self.assertEqual(before, self.snapshot())

    def test_review_no_predecessor_does_not_invent_a_handoff(self):
        active = self.start()["id"]
        resumed = self.store.resume("java", "core", active)
        self.assertEqual(resumed["continuation"], {"source": "none", "source_session_id": None, "handoff": None})
        self.assertIsNone(resumed["reference_session"])

    def test_review_changed_history_is_revalidated_during_index_refresh(self):
        prior, recent, active = self.continuation_fixture()
        path = self.store.path("java", "core", prior, "record.json")
        damaged = self.read(prior)
        damaged["events"][0]["text"] = "未经授权改写事实"
        path.write_text(json.dumps(damaged, ensure_ascii=False), encoding="utf-8")
        damaged_bytes = path.read_bytes()
        with self.assertRaises(learning.LearningError):
            self.checkpoint(active)
        # The canonical checkpoint commits before index refresh. It stays valid
        # and is never rolled back to hide an unrelated damaged historical file.
        self.assertEqual(len(self.read(active)["events"]), 1)
        self.assertEqual(path.read_bytes(), damaged_bytes)
        with self.assertRaises(learning.LearningError):
            self.hub.validate()

    def test_review_invalid_cache_falls_back_to_full_canonical_reads(self):
        prior, recent, active = self.continuation_fixture()
        index = self.store.directory("java", "core") / "index.json"
        index.write_text("{broken", encoding="utf-8")
        with mock.patch.object(self.store, "load", wraps=self.store.load) as loads:
            self.checkpoint(active)
        self.assertEqual(set(call.args[2] for call in loads.call_args_list), {prior, recent, active})
        self.assertTrue(self.hub.validate()["valid"])

    def test_review_full_validation_and_repair_ignore_cache_signatures(self):
        prior, recent, active = self.continuation_fixture()
        path = self.store.path("java", "core", prior, "record.json")
        before_stat = path.stat()
        data = path.read_bytes().replace("实际学习内容".encode("utf-8"), "伪造学习内容".encode("utf-8"), 1)
        self.assertEqual(len(data), before_stat.st_size)
        path.write_bytes(data)
        os.utime(path, ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns))
        before = self.snapshot()
        with self.assertRaises(learning.LearningError):
            self.hub.validate()
        with self.assertRaises(learning.LearningError):
            self.store.repair("java", "core")
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
