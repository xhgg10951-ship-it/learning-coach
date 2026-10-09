"""Session records and bounded handoffs; no teaching or mastery inference."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

if __package__:
    from .learning import LearningError, _atomic, _id, _load, _save, _text, now, _unique_object, _invalid_constant
else:
    from learning import LearningError, _atomic, _id, _load, _save, _text, now, _unique_object, _invalid_constant

KINDS = {"content", "question", "explanation", "exercise", "weakness", "unresolved", "understanding", "evidence"}
BASES = {"user_report", "ai_assessment", "exercise_verified", "unverified"}
LABELS = {"content": "实际学习内容", "question": "用户问题", "explanation": "关键解释与结论",
          "exercise": "练习与批改", "weakness": "暴露的薄弱点", "unresolved": "未解决的问题",
          "understanding": "用户理解反馈", "evidence": "Sprint 验收证据"}
BASIS_LABELS = {"user_report": "用户自报", "ai_assessment": "AI 判断",
                "exercise_verified": "练习验证", "unverified": "尚未验证"}


def digest(value):
    try:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LearningError(f"Session 数据不是有效的有限 JSON: {exc}") from exc
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def text(value, label, limit=8000):
    _text(value, label)
    if len(value) > limit:
        raise LearningError(f"{label}: 最多 {limit} 字符，请分批或引用资料")
    return value


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise LearningError(f"字段错误；必需 {sorted(required)}；可选 {sorted(optional)}")


def ids(value, label, maximum=100):
    if not isinstance(value, list) or len(value) > maximum:
        raise LearningError(f"{label}: 必须为数组，最多 {maximum} 项")
    for item in value:
        _id(item, label)
    if len(value) != len(set(value)):
        raise LearningError(f"{label}: 不允许重复")
    return value


def session_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"SE-[a-f0-9]{32}", value):
        raise LearningError("Session ID 必须为 SE- 加 32 位小写十六进制 UUID")
    return value


def timestamp(value):
    try:
        result = dt.datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError()
        return result
    except (TypeError, ValueError) as exc:
        raise LearningError("Session 时间必须是包含时区的 ISO 时间") from exc


def read_payload(path):
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig")
        value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (UnicodeError, ValueError) as exc:
        raise LearningError(f"Session 输入 JSON 错误: {exc}") from exc
    if not isinstance(value, dict):
        raise LearningError("Session 输入必须是 JSON 对象")
    return value


def check_event(event, previous, sprint):
    fields(event, {"id", "kind", "text", "basis", "sources"},
           {"related_ids", "supersedes", "prompt", "answer", "result", "feedback",
            "understanding", "criterion", "outcome", "knowledge_ids", "review_candidates"})
    _id(event["id"], "event")
    if event["id"] in previous:
        raise LearningError(f"事实 ID 重复: {event['id']}；重试使用原 operation_id")
    if not isinstance(event["kind"], str) or event["kind"] not in KINDS:
        raise LearningError("未知学习事实 kind")
    if not isinstance(event["basis"], str) or event["basis"] not in BASES:
        raise LearningError("basis 必须区分 user_report / ai_assessment / exercise_verified / unverified")
    text(event["text"], "event.text")
    sources = event["sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 8:
        raise LearningError("事实需要 1 至 8 条 sources，保存可核对的引用与摘录")
    for source in sources:
        fields(source, {"ref", "quote"})
        text(source["ref"], "source.ref", 500)
        text(source["quote"], "source.quote", 4000)
    for key in ("related_ids", "supersedes", "knowledge_ids", "review_candidates"):
        ids(event.get(key, []), key)
    for identity in event.get("related_ids", []) + event.get("supersedes", []):
        if identity not in previous:
            raise LearningError(f"事实引用必须指向已保存或本批次前面的事实: {identity}")
    kind = event["kind"]
    extra = {"prompt", "answer", "result", "feedback"} if kind == "exercise" else {"understanding"} if kind == "understanding" else {"criterion", "outcome"} if kind == "evidence" else set()
    if (set(event) & {"prompt", "answer", "result", "feedback", "understanding", "criterion", "outcome"}) != extra:
        raise LearningError(f"{kind} 专属字段缺失或出现在错误的事实类型上")
    if kind == "exercise":
        text(event["prompt"], "exercise.prompt")
        if not isinstance(event["answer"], str) or len(event["answer"]) > 8000:
            raise LearningError("exercise.answer 必须为文本，未作答用空字符串")
        text(event["feedback"], "exercise.feedback")
        if event["result"] not in ("correct", "partial", "incorrect", "not_assessed"):
            raise LearningError("练习结果无效")
        if event["result"] != "not_assessed" and not event["answer"].strip():
            raise LearningError("没有作答不能记为已批改")
        if event["basis"] == "exercise_verified" and event["result"] == "not_assessed":
            raise LearningError("尚未批改不能记为练习验证")
    if kind == "understanding":
        if event["basis"] != "user_report" or event["understanding"] not in ("understood", "not_understood", "unsure"):
            raise LearningError("理解反馈必须是用户自报，不是 AI 已经讲解")
    if kind == "question" and event["basis"] != "user_report":
        raise LearningError("用户问题必须记为 user_report")
    if kind == "explanation" and event["basis"] == "exercise_verified":
        raise LearningError("AI 解释不能作为练习验证")
    if kind == "evidence":
        if sprint is None or event["criterion"] not in sprint["criteria"]:
            raise LearningError("验收证据 criterion 必须对应本 Session 的 Sprint 验收快照")
        if event["outcome"] not in ("met", "partial", "not_met", "unverified"):
            raise LearningError("验收证据 outcome 无效")
    if event["basis"] == "exercise_verified" and kind != "exercise":
        related = [previous[identity] for identity in event.get("related_ids", [])]
        exercises = [item for item in related if item["kind"] == "exercise" and
                     item["basis"] == "exercise_verified" and item["result"] != "not_assessed"]
        if not exercises:
            raise LearningError("练习验证结论必须关联已作答并批改的练习")
        if kind == "evidence" and event["outcome"] == "met" and not any(item["result"] == "correct" for item in exercises):
            raise LearningError("已验证达标的证据必须关联正确的练习结果")


def check_handoff(value, events):
    fields(value, {"summary", "next_step", "focus_ids"})
    text(value["summary"], "handoff.summary", 1200)
    text(value["next_step"], "handoff.next_step", 800)
    ids(value["focus_ids"], "focus_ids", 20)
    superseded = {identity for item in events.values() for identity in item.get("supersedes", [])}
    # Correcting an exercise also invalidates claims derived from that exercise.
    for identity, event in events.items():
        if event["basis"] == "exercise_verified" and any(key in superseded for key in event.get("related_ids", [])):
            superseded.add(identity)
    if any(identity not in events or identity in superseded for identity in value["focus_ids"]):
        raise LearningError("handoff.focus_ids 必须引用现存且未被替代的事实")


def render_note(record):
    lines = [f"# {record['topic']}", "", f"Session: `{record['id']}`",
             f"Goal / Track: `{record['goal_id']}` / `{record['track_id']}`",
             f"Sprint: `{record['sprint_id'] or '未关联'}`",
             f"开始：{record['created_at']}；结束：{record['completed_at']}", "",
             "本文件由 record.json 生成；机器状态以 JSON 为准。Session 完成不代表 Sprint 完成。", "",
             "## 本次摘要", "", record["handoff"]["summary"], ""]
    for kind, label in LABELS.items():
        lines += [f"## {label}", ""]
        matching = [event for event in record["events"] if event["kind"] == kind]
        if not matching:
            lines += ["未记录。", ""]
        for event in matching:
            lines += [f"### {event['id']} · {BASIS_LABELS[event['basis']]}", "", event["text"], ""]
            for key, title in (("prompt", "题目"), ("answer", "用户答案"), ("result", "结果"),
                               ("feedback", "批改"), ("understanding", "用户反馈"),
                               ("criterion", "验收标准"), ("outcome", "证据判断")):
                if key in event:
                    lines += [f"{title}：{event[key] or '未作答'}", ""]
            for key, title in (("related_ids", "关联事实"), ("supersedes", "修订并替代（原文仍保留）")):
                if event.get(key):
                    lines += [f"{title}：{', '.join(event[key])}", ""]
            lines += ["引用与摘录：", ""]
            for source in event["sources"]:
                lines += [f"- {source['ref']}", *[f"  > {line}" for line in source["quote"].splitlines()], ""]
    lines += ["## 下一次交接", "", record["handoff"]["next_step"], "",
              "重点事实：" + (", ".join(record["handoff"]["focus_ids"]) or "未指定"), "",
              "用户可以选择其他主题；完成 Sprint 需另行调用 transition。", ""]
    return "\n".join(lines)


class SessionStore:
    def __init__(self, hub):
        self.hub = hub

    def directory(self, goal, track, identity=None):
        parts = ["goals", _id(goal, "goal"), "tracks", _id(track, "track"), "sessions"]
        if identity is not None:
            parts.append(session_id(identity))
        return self.hub._path(*parts)

    def path(self, goal, track, identity, name):
        return self.hub._path(*self.directory(goal, track, identity).relative_to(self.hub.root).parts, name)

    def scope(self, goal=None, track=None):
        if (goal is None) != (track is None):
            raise LearningError("必须同时指定 --goal / --track，或都省略使用当前选择")
        if goal is None:
            selected = self.hub._active()
            goal, track = selected["goal_id"], selected["track_id"]
        if goal is None or track is None:
            raise LearningError("尚未选择 Goal/Track；请先 select")
        return goal, track, self.hub.get_track(goal, track)

    def load(self, goal, track, identity, state):
        record = _load(self.path(goal, track, identity, "record.json"))
        self.check_record(record, goal, track, identity, state)
        return record

    def check_record(self, record, goal, track, identity, state):
        fields(record, {"schema_version", "session_version", "kind", "id", "goal_id", "track_id",
                        "sprint_id", "sprint_snapshot", "topic", "status", "created_at", "updated_at",
                        "completed_at", "start_request_id", "previous_session_id", "events",
                        "checkpoints", "handoff", "extensions"})
        if type(record["session_version"]) is not int or record["session_version"] != 1 or record["kind"] != "session":
            raise LearningError("不支持的 Session 版本或类型；不自动迁移")
        if (record["id"], record["goal_id"], record["track_id"]) != (identity, goal, track):
            raise LearningError("Session 身份与所属 Goal/Track 不匹配")
        session_id(identity)
        _id(record["start_request_id"], "request")
        text(record["topic"], "topic", 500)
        if record["status"] not in ("active", "completed"):
            raise LearningError("Session 状态无效")
        if timestamp(record["updated_at"]) < timestamp(record["created_at"]):
            raise LearningError("Session 时间顺序错误")
        if record["previous_session_id"] is not None:
            session_id(record["previous_session_id"])
            if record["previous_session_id"] == identity:
                raise LearningError("Session 不能引用自己作为上次学习")
        sprint = record["sprint_snapshot"]
        if record["sprint_id"] is None:
            if sprint is not None:
                raise LearningError("未关联 Sprint 却存在验收快照")
        else:
            self.hub._unit(state, "sprint", record["sprint_id"])
            fields(sprint, {"id", "milestone_id", "objective", "criteria"})
            if sprint["id"] != record["sprint_id"] or sprint["milestone_id"] != state["sprints"][sprint["id"]]["milestone_id"]:
                raise LearningError("Sprint 快照关系不匹配")
            text(sprint["objective"], "sprint.objective")
            if not isinstance(sprint["criteria"], list) or not sprint["criteria"]:
                raise LearningError("Sprint 快照缺少验收标准")
            for criterion in sprint["criteria"]:
                text(criterion, "criterion")
        if not isinstance(record["events"], list) or not isinstance(record["checkpoints"], list):
            raise LearningError("events/checkpoints 必须为数组")
        events = {}
        for event in record["events"]:
            check_event(event, events, sprint)
            events[event["id"]] = event
        seen, assigned, available = set(), [], {}
        last_at = record["created_at"]
        for number, checkpoint in enumerate(record["checkpoints"]):
            fields(checkpoint, {"operation_id", "kind", "at", "event_ids", "handoff", "digest"})
            _id(checkpoint["operation_id"], "operation")
            if checkpoint["operation_id"] in seen or checkpoint["kind"] not in ("checkpoint", "finish"):
                raise LearningError("检查点操作重复或类型错误")
            seen.add(checkpoint["operation_id"])
            if checkpoint["kind"] == "finish" and number != len(record["checkpoints"]) - 1:
                raise LearningError("finish 必须为最后一个检查点")
            if timestamp(checkpoint["at"]) < timestamp(last_at):
                raise LearningError("检查点时间顺序错误")
            last_at = checkpoint["at"]
            ids(checkpoint["event_ids"], "event_ids")
            if any(key not in events for key in checkpoint["event_ids"]):
                raise LearningError("检查点引用不存在的事实")
            assigned.extend(checkpoint["event_ids"])
            available.update((key, events[key]) for key in checkpoint["event_ids"])
            check_handoff(checkpoint["handoff"], available)
            payload = {"operation_id": checkpoint["operation_id"],
                       "events": [events[key] for key in checkpoint["event_ids"]], "handoff": checkpoint["handoff"]}
            if digest(payload) != checkpoint["digest"]:
                raise LearningError("检查点摘要校验失败；原始事实或交接被修改")
        if assigned != list(events) or record["updated_at"] != last_at:
            raise LearningError("检查点与事实顺序或更新时间不一致")
        if record["handoff"] != (record["checkpoints"][-1]["handoff"] if seen else None):
            raise LearningError("当前交接与最后检查点不一致")
        finished = bool(seen and record["checkpoints"][-1]["kind"] == "finish")
        if finished != (record["status"] == "completed") or record["completed_at"] != (last_at if finished else None):
            raise LearningError("Session 完成状态与结束检查点不一致")
        fields(record["extensions"], {"knowledge_ids", "review_candidates"})
        for key, value in record["extensions"].items():
            ids(value, key)

    def signatures(self, goal, track):
        directory = self.directory(goal, track)
        result = []
        for child in sorted(directory.iterdir()):
            self.hub._path(*child.relative_to(self.hub.root).parts)
            if child.name == "index.json":
                self.hub._file(child)
                continue
            if child.name.startswith(".pending-"):
                raise LearningError(f"发现中断暂存文件: {child}；保留并人工检查")
            session_id(child.name)
            self.hub._dir(child)
            names = {p.name for p in child.iterdir()}
            if "record.json" not in names or names - {"record.json", "note.md"}:
                raise LearningError(f"Session 目录缺失记录或存在未识别文件: {child}")
            path = self.path(goal, track, child.name, "record.json")
            self.hub._file(path)
            if "note.md" in names:
                self.hub._file(self.path(goal, track, child.name, "note.md"))
            stat = path.stat()
            result.append({"id": child.name, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
        return result

    @staticmethod
    def entry(record):
        return {key: record[key] for key in ("id", "status", "topic", "created_at", "updated_at", "completed_at",
                                             "sprint_id", "start_request_id", "previous_session_id")}

    def catalog(self, goal, track, state, force=False):
        signatures = self.signatures(goal, track)
        path = self.directory(goal, track) / "index.json"
        if path.exists() and not force:
            try:
                cached = _load(path)
                if (cached.get("kind"), cached.get("goal_id"), cached.get("track_id")) == ("session_index", goal, track) and cached.get("signatures") == signatures and digest(cached.get("entries")) == cached.get("digest"):
                    entries = cached["entries"]
                    if isinstance(entries, list) and len(entries) == len(signatures) and {x["id"] for x in entries} == {x["id"] for x in signatures}:
                        for item in entries:
                            fields(item, {"id", "status", "topic", "created_at", "updated_at", "completed_at",
                                          "sprint_id", "start_request_id", "previous_session_id"})
                            session_id(item["id"])
                            _id(item["start_request_id"], "request")
                            text(item["topic"], "topic", 500)
                            timestamp(item["created_at"])
                            timestamp(item["updated_at"])
                            if item["status"] not in ("active", "completed"):
                                raise LearningError("索引状态错误")
                            if item["status"] == "completed":
                                timestamp(item["completed_at"])
                        if (len({item["start_request_id"] for item in entries}) != len(entries) or
                                sum(item["status"] == "active" for item in entries) > 1 or
                                entries != sorted(entries, key=lambda item: (item["created_at"], item["id"]), reverse=True)):
                            raise LearningError("索引顺序或唯一性错误")
                        return entries, "current"
            except (LearningError, KeyError, TypeError):
                pass  # Derived data only. Preserve the file; reads rebuild in memory.
        entries = [self.entry(self.load(goal, track, item["id"], state)) for item in signatures]
        entries.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        if len({item["start_request_id"] for item in entries}) != len(entries):
            raise LearningError("Session start_request_id 重复")
        if sum(item["status"] == "active" for item in entries) > 1:
            raise LearningError("同一 Track 存在多个 active Session")
        return entries, "rebuilt_in_memory" if signatures or path.exists() else "empty"

    def write_index(self, goal, track, state):
        entries, _ = self.catalog(goal, track, state, force=True)
        value = {"schema_version": 2, "kind": "session_index", "goal_id": goal, "track_id": track,
                 "signatures": self.signatures(goal, track), "entries": entries, "digest": digest(entries)}
        path = self.directory(goal, track) / "index.json"
        if path.exists():
            try:
                if _load(path) == value:
                    return
            except LearningError:
                pass
        _save(path, value)

    def materialize(self, record):
        path = self.path(record["goal_id"], record["track_id"], record["id"], "note.md")
        if record["status"] != "completed":
            if path.exists():
                raise LearningError(f"active Session 存在冲突笔记: {path}；保留文件")
            return
        expected = render_note(record)
        if path.exists():
            if path.read_bytes() != expected.encode("utf-8"):
                raise LearningError(f"笔记与权威记录冲突: {path}；保留文件，不覆盖人工修改")
        else:
            _atomic(path, expected)

    def result(self, record):
        goal, track, identity = record["goal_id"], record["track_id"], record["id"]
        return {**self.entry(record), "goal_id": goal, "track_id": track, "persisted": True,
                "event_count": len(record["events"]), "checkpoint_count": len(record["checkpoints"]),
                "record_path": str(self.path(goal, track, identity, "record.json")),
                "note_path": str(self.path(goal, track, identity, "note.md")) if record["status"] == "completed" else None,
                "note_exists": self.path(goal, track, identity, "note.md").is_file()}

    def start(self, goal, track, topic, request_id, sprint=None, previous=None):
        text(topic, "topic", 500)
        _id(request_id, "request")
        with self.hub._lock():
            goal, track, state = self.scope(goal, track)
            entries, _ = self.catalog(goal, track, state, force=True)
            retry = next((item for item in entries if item["start_request_id"] == request_id), None)
            if retry:
                record = self.load(goal, track, retry["id"], state)
                if (record["topic"], record["sprint_id"], record["previous_session_id"]) != (topic, sprint, previous):
                    raise LearningError("start request_id 已使用，但内容不同")
                self.materialize(record)
                self.write_index(goal, track, state)
                return self.result(record)
            self.hub._parents_active(goal, state)
            active = next((item for item in entries if item["status"] == "active"), None)
            if active:
                raise LearningError(f"已有未结束 Session {active['id']}；使用 session-resume 或先结束它")
            if previous is not None:
                prior = self.load(goal, track, previous, state)
                if prior["status"] != "completed":
                    raise LearningError("--from-session 必须指向已结束的 Session；中断学习用 session-resume")
            snapshot = None
            if sprint is not None:
                unit = self.hub._unit(state, "sprint", sprint)
                snapshot = {key: copy.deepcopy(unit[key]) for key in ("id", "milestone_id", "objective", "criteria")}
            identity, stamp = f"SE-{uuid.uuid4().hex}", now()
            record = {"schema_version": 2, "session_version": 1, "kind": "session", "id": identity,
                      "goal_id": goal, "track_id": track, "sprint_id": sprint, "sprint_snapshot": snapshot,
                      "topic": topic, "status": "active", "created_at": stamp, "updated_at": stamp,
                      "completed_at": None, "start_request_id": request_id, "previous_session_id": previous,
                      "events": [], "checkpoints": [], "handoff": None,
                      "extensions": {"knowledge_ids": [], "review_candidates": []}}
            self.check_record(record, goal, track, identity, state)
            self.hub._new_directory(self.directory(goal, track, identity), lambda directory: _save(directory / "record.json", record))
            self.write_index(goal, track, state)
            return self.result(record)

    def checkpoint(self, goal, track, identity, payload, finish=False):
        fields(payload, {"operation_id", "events", "handoff"})
        _id(payload["operation_id"], "operation")
        if not isinstance(payload["events"], list) or len(payload["events"]) > 100:
            raise LearningError("一次检查点最多 100 条事实")
        with self.hub._lock():
            goal, track, state = self.scope(goal, track)
            record = self.load(goal, track, identity, state)
            kind = "finish" if finish else "checkpoint"
            retry = next((item for item in record["checkpoints"] if item["operation_id"] == payload["operation_id"]), None)
            if retry:
                if retry["kind"] != kind or retry["digest"] != digest(payload):
                    raise LearningError("operation_id 已使用，但内容或操作不同")
                self.materialize(record)
                self.write_index(goal, track, state)
                return self.result(record)
            if record["status"] == "completed":
                if finish and not payload["events"] and payload["handoff"] == record["handoff"]:
                    self.materialize(record)
                    self.write_index(goal, track, state)
                    return self.result(record)
                raise LearningError("Session 已结束；不能追加或重新打开。重试使用原 operation_id 和内容")
            events = {event["id"]: event for event in record["events"]}
            for event in payload["events"]:
                check_event(event, events, record["sprint_snapshot"])
                events[event["id"]] = event
            check_handoff(payload["handoff"], events)
            # Check derived-file conflicts before committing any new facts.
            self.materialize(record)
            stamp = now()
            record["events"].extend(copy.deepcopy(payload["events"]))
            record["handoff"] = copy.deepcopy(payload["handoff"])
            record["updated_at"] = stamp
            record["checkpoints"].append({"operation_id": payload["operation_id"], "kind": kind,
                                           "at": stamp, "event_ids": [item["id"] for item in payload["events"]],
                                           "handoff": copy.deepcopy(payload["handoff"]), "digest": digest(payload)})
            if finish:
                record["status"], record["completed_at"] = "completed", stamp
            self.check_record(record, goal, track, identity, state)
            _save(self.path(goal, track, identity, "record.json"), record)
            # A failure here leaves a valid committed record; replay or repair
            # regenerates only derived artifacts, never re-applies learning facts.
            self.materialize(record)
            self.write_index(goal, track, state)
            return self.result(record)

    @staticmethod
    def limit(value, maximum=100):
        if type(value) is not int or not 1 <= value <= maximum:
            raise LearningError(f"limit 必须为 1 至 {maximum} 的整数")
        return value

    def compact(self, record):
        events = {event["id"]: event for event in record["events"]}
        handoff = record["handoff"]
        focus = []
        if handoff:
            for identity in handoff["focus_ids"]:
                event = events[identity]
                focus.append({"id": identity, "kind": event["kind"], "basis": event["basis"],
                              "text": event["text"][:500], "detail_truncated": len(event["text"]) > 500,
                              **{key: event[key] for key in ("criterion", "outcome", "understanding", "result") if key in event}})
        # Only explicit exercise-backed evidence qualifies; explanations and
        # self-reports remain visible with their original basis.
        verified = [item for item in focus if item["kind"] == "evidence" and item["basis"] == "exercise_verified" and item["outcome"] == "met"]
        return {**self.result(record), "handoff": handoff, "focus": focus,
                "verified_abilities": verified,
                "unstable_points": [item for item in focus if item["kind"] == "weakness"],
                "unresolved_questions": [item for item in focus if item["kind"] == "unresolved"],
                "understanding": [item for item in focus if item["kind"] == "understanding"],
                "omitted_event_count": len(events) - len(focus)}

    def context(self, goal=None, track=None, limit=1):
        self.limit(limit, 10)
        goal, track, state = self.scope(goal, track)
        entries, cache = self.catalog(goal, track, state)
        active = next((item for item in entries if item["status"] == "active"), None)
        recent = sorted((item for item in entries if item["status"] == "completed"),
                        key=lambda item: (item["completed_at"], item["id"]), reverse=True)[:limit]
        parent = self.hub.get_goal(goal)
        return {"goal": self.hub._summary(parent), "track": self.hub._summary(state),
                "current_milestone": next((item for item in state["milestones"].values() if item["status"] == "active"), None),
                "current_sprint": next((item for item in state["sprints"].values() if item["status"] == "active"), None),
                "learning_allowed": parent["status"] == state["status"] == "active",
                "mode": "resume" if active else "new_session" if recent else "start",
                "active_session": self.compact(self.load(goal, track, active["id"], state)) if active else None,
                "recent_sessions": [self.compact(self.load(goal, track, item["id"], state)) for item in recent],
                "index_status": cache, "history_scope": "selected_track_only", "recent_limit": limit}

    def resume(self, goal, track, identity):
        goal, track, state = self.scope(goal, track)
        record = self.load(goal, track, identity, state)
        if record["status"] != "active":
            raise LearningError("已结束 Session 不能恢复；请 session-start --from-session 新建")
        self.hub._parents_active(goal, state)
        return {"mode": "resume", "session": self.compact(record)}

    def listing(self, goal=None, track=None, limit=5):
        self.limit(limit)
        goal, track, state = self.scope(goal, track)
        entries, cache = self.catalog(goal, track, state)
        return {"goal_id": goal, "track_id": track, "total": len(entries), "index_status": cache,
                "sessions": [self.result(self.load(goal, track, item["id"], state)) for item in entries[:limit]]}

    def show(self, goal, track, identity, offset=0, limit=20):
        self.limit(limit)
        if type(offset) is not int or offset < 0:
            raise LearningError("offset 必须为非负整数")
        goal, track, state = self.scope(goal, track)
        record = self.load(goal, track, identity, state)
        end = offset + limit
        return {**self.compact(record), "sprint_snapshot": record["sprint_snapshot"],
                "events": record["events"][offset:end], "offset": offset,
                "next_offset": end if end < len(record["events"]) else None}

    def validate_track(self, goal, track, repair=False):
        state = self.hub.get_track(goal, track)
        entries, _ = self.catalog(goal, track, state, force=True)
        by_id = {entry["id"]: entry for entry in entries}
        for entry in entries:
            record = self.load(goal, track, entry["id"], state)
            previous = record["previous_session_id"]
            if previous is not None and (previous not in by_id or by_id[previous]["status"] != "completed" or timestamp(by_id[previous]["completed_at"]) > timestamp(record["created_at"])):
                raise LearningError("previous_session_id 缺失、未结束或时间关系错误")
            if repair:
                self.materialize(record)
            else:
                note = self.path(goal, track, entry["id"], "note.md")
                if record["status"] == "completed":
                    if not note.exists() or note.read_bytes() != render_note(record).encode("utf-8"):
                        raise LearningError(f"笔记缺失或冲突: {note}；运行 session-repair，仅补写缺失派生文件")
                elif note.exists():
                    raise LearningError(f"active Session 不应存在笔记: {note}")
        if entries or (self.directory(goal, track) / "index.json").exists():
            if repair:
                self.write_index(goal, track, state)
            else:
                cached, status = self.catalog(goal, track, state)
                if status != "current" or cached != entries:
                    raise LearningError("Session 索引缺失、过期或损坏；运行 session-repair")
        return len(entries)

    def repair(self, goal, track):
        with self.hub._lock():
            goal, track, _ = self.scope(goal, track)
            count = self.validate_track(goal, track, repair=True)
            return {"goal_id": goal, "track_id": track, "sessions": count, "repaired": True}


def add_commands(commands):
    for name in ("session-start", "session-checkpoint", "session-finish", "session-resume",
                 "session-context", "session-list", "session-show", "session-repair"):
        command = commands.add_parser(name)
        for key in ("goal", "track"):
            command.add_argument(f"--{key}", required=name not in {"session-context", "session-list"})
        if name in {"session-checkpoint", "session-finish", "session-resume", "session-show"}:
            command.add_argument("--session", required=True)
        if name == "session-start":
            command.add_argument("--topic", required=True)
            command.add_argument("--request-id", required=True)
            command.add_argument("--sprint")
            command.add_argument("--from-session")
        if name in {"session-checkpoint", "session-finish"}:
            command.add_argument("--data", required=True, help="UTF-8 JSON 文件；- 从 stdin 读取")
        if name in {"session-context", "session-list", "session-show"}:
            command.add_argument("--limit", type=int, default={"session-context": 1, "session-list": 5, "session-show": 20}[name])
        if name == "session-show":
            command.add_argument("--offset", type=int, default=0)


def run(store, args):
    name = args.command
    if name == "session-start":
        return store.start(args.goal, args.track, args.topic, args.request_id, args.sprint, args.from_session)
    if name in {"session-checkpoint", "session-finish"}:
        return store.checkpoint(args.goal, args.track, args.session, read_payload(args.data), finish=name == "session-finish")
    if name == "session-resume":
        return store.resume(args.goal, args.track, args.session)
    if name == "session-context":
        return store.context(args.goal, args.track, args.limit)
    if name == "session-list":
        return store.listing(args.goal, args.track, args.limit)
    if name == "session-show":
        return store.show(args.goal, args.track, args.session, args.offset, args.limit)
    if name == "session-repair":
        return store.repair(args.goal, args.track)
    raise LearningError(f"未知 Session 命令: {name}")
