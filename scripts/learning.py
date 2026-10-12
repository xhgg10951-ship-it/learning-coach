#!/usr/bin/env python3
"""Local learning structure, validated persistence and a standard-library JSON CLI."""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid
from contextlib import contextmanager

SCHEMA_VERSION = 2
TERMINAL = {"completed", "skipped", "ended"}
STATUSES = {
    "goal": {"active", "paused", "completed"},
    "track": {"pending", "active", "paused", "completed"},
    "milestone": {"pending", "active", "paused", "completed", "skipped", "ended"},
    "sprint": {"pending", "active", "paused", "completed", "skipped", "ended"},
}
TRANSITIONS = {
    "pending": {"active", "paused", "skipped", "ended"},
    "active": {"paused", "completed", "skipped", "ended"},
    "paused": {"active", "skipped", "ended"},
    "completed": set(), "skipped": set(), "ended": set(),
}

class LearningError(ValueError):
    """Expected, actionable data or lifecycle error."""


def default_hub() -> Path:
    return Path(os.environ.get("LEARNING_COACH_HUB") or Path.home() / "learning-hub")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise LearningError(f"{label}: 必须为非空文本")
    return value.strip()


def _id(value, kind):
    if not isinstance(value, str):
        raise LearningError(f"{kind} ID 必须是字符串")
    pattern = r"M[0-9]{3,}" if kind == "milestone" else r"SP[0-9]{3,}" if kind == "sprint" else r"[a-z0-9][a-z0-9-]{0,63}"
    if not re.fullmatch(pattern, value) or value in {"con", "prn", "aux", "nul"} or re.fullmatch(r"(?:com|lpt)[0-9]", value):
        raise LearningError(f"非法 {kind} ID: {value!r}；目标/领域使用小写字母、数字、连字符；单元使用 M001 / SP001")
    if kind in {"milestone", "sprint"} and int(re.search(r"[0-9]+$", value).group()) == 0:
        raise LearningError(f"{kind} ID 序号必须大于零")
    return value


def _criteria(value):
    if not isinstance(value, list) or not value:
        raise LearningError("criteria: 至少一个可检验的完成标准")
    out = [_text(v, "criterion") for v in value]
    if len(set(out)) != len(out):
        raise LearningError("criteria: 完成标准重复")
    return out


def _hours(value):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and value > 0 and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise LearningError("estimated_hours: 必须为有限正数；仅用于估计，不决定完成状态")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LearningError(f"JSON 存在重复键/ID: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise LearningError(f"JSON 不允许非有限数值: {value}")


def _load(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except FileNotFoundError as exc:
        raise LearningError(f"缺失文件: {path}；保留原文件，检查路径或从备份恢复") from exc
    except (UnicodeError, ValueError) as exc:
        raise LearningError(f"JSON 格式错误: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LearningError(f"JSON 必须是对象: {path}")
    if type(value.get("schema_version")) is not int or value["schema_version"] != SCHEMA_VERSION:
        raise LearningError(f"不支持的 schema_version: {path}；不自动迁移或覆盖")
    return value


def _atomic(path, value):
    """Same-volume replace keeps the previous authoritative file on write failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _save(path, value):
    _atomic(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _record(state, kind, entity_id, event, note, before=None, after=None):
    stamp = now()
    state["updated_at"] = stamp
    state["history"].append({"at": stamp, "kind": kind, "id": entity_id,
                             "event": event, "note": note,
                             "before": copy.deepcopy(before), "after": copy.deepcopy(after)})


def _entity(kind, entity_id, title, status):
    stamp = now()
    return {"schema_version": SCHEMA_VERSION, "kind": kind, "id": entity_id,
            "title": _text(title, "title"), "status": status,
            "created_at": stamp, "updated_at": stamp, "extensions": {}}


class Hub:
    def __init__(self, path=None):
        self.root = Path(path if path is not None else default_hub()).expanduser().resolve()

    def _path(self, *parts):
        path = self.root
        for part in parts:
            path = path / part
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise LearningError(f"数据目录不允许链接或联接点: {path}")
        if not path.resolve().is_relative_to(self.root):
            raise LearningError(f"路径越出数据目录: {path}")
        return path

    def _gdir(self, goal):
        return self._path("goals", _id(goal, "goal"))

    def _tdir(self, goal, track):
        return self._path("goals", _id(goal, "goal"), "tracks", _id(track, "track"))

    @contextmanager
    def _lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(".write.lock")
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise LearningError(f"写锁已存在: {path}；其他操作可能正在写入。若进程已退出，确认没有写入者后手动移走锁，再运行 validate；不会自动抢锁") from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"pid": os.getpid(), "created_at": now()}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            yield
        finally:
            path.unlink()

    def _initialized(self):
        self._file(self._path("profile.md"))
        self._dir(self._path("goals"))
        self._active()

    def initialize(self):
        with self._lock():
            active_path = self._path("state", "active.json")
            if active_path.exists():
                self._initialized()
                return {"hub": str(self.root), "schema_version": SCHEMA_VERSION}
            if self._path("state").exists() and any(self._path("state").iterdir()):
                raise LearningError("state/ 非空但缺少 active.json；拒绝猜测当前状态，请先检查和恢复")
            existing_goals = self._path("goals")
            if existing_goals.is_dir() and any((p / "state.json").exists() or (p / "tracks").exists() for p in existing_goals.iterdir() if p.is_dir()):
                raise LearningError("已存在新版 Goal 但缺少 active.json；请从备份恢复，不自动重置学习位置")
            self._path("goals").mkdir(exist_ok=True)
            profile = self._path("profile.md")
            if not profile.exists():
                _atomic(profile, "# 用户画像\n\n- 称呼：\n- 身份：\n- 已有技能：\n- 资料语言偏好：尽量中文\n- 偏好资料形式：\n- 预算：\n\n## 更新记录\n")
            _save(active_path, {"schema_version": SCHEMA_VERSION, "goal_id": None,
                                "track_id": None, "updated_at": now()})
            return {"hub": str(self.root), "schema_version": SCHEMA_VERSION}

    def _file(self, path):
        self._path(*path.relative_to(self.root).parts)
        if not path.is_file():
            raise LearningError(f"缺失文件: {path}；不会自动补写或忽略")

    def _dir(self, path):
        self._path(*path.relative_to(self.root).parts)
        if not path.is_dir():
            raise LearningError(f"缺失目录: {path}")

    def _base(self, value, kind, entity_id):
        if not isinstance(value, dict) or value.get("kind") != kind or value.get("id") != entity_id:
            raise LearningError(f"{kind} 的 ID/类型与目录或索引不一致: {entity_id}")
        if type(value.get("schema_version")) is not int or value["schema_version"] != SCHEMA_VERSION:
            raise LearningError(f"{kind} {entity_id}: 不支持的 schema_version")
        _id(entity_id, kind)
        _text(value.get("title"), "title")
        if not isinstance(value.get("status"), str) or value["status"] not in STATUSES[kind]:
            raise LearningError(f"{kind} {entity_id}: 非法状态 {value.get('status')!r}")
        for key in ("created_at", "updated_at"):
            try:
                stamp = dt.datetime.fromisoformat(_text(value.get(key), key))
                if stamp.tzinfo is None:
                    raise ValueError("missing timezone")
            except (ValueError, TypeError) as exc:
                raise LearningError(f"{kind} {entity_id}: {key} 时间元数据无效，必须包含时区") from exc
        if not isinstance(value.get("extensions"), dict):
            raise LearningError(f"{kind} {entity_id}: extensions 必须为对象")

    def _history(self, state):
        if not isinstance(state.get("history"), list):
            raise LearningError("history 必须为数组，禁止丢弃历史决策")
        for entry in state["history"]:
            if not isinstance(entry, dict) or not all(k in entry for k in ("at", "kind", "id", "event", "note", "before", "after")):
                raise LearningError("history 记录格式错误")
            _text(entry["note"], "history.note")
            _text(entry["event"], "history.event")
            if not isinstance(entry["kind"], str) or entry["kind"] not in STATUSES:
                raise LearningError("history.kind 无效")
            _id(entry["id"], entry["kind"])
            try:
                if dt.datetime.fromisoformat(entry["at"]).tzinfo is None:
                    raise ValueError()
            except (ValueError, TypeError) as exc:
                raise LearningError("history.at 无效") from exc

    def get_goal(self, goal):
        directory = self._gdir(goal)
        path = self._path("goals", goal, "state.json")
        if not path.exists() and directory.exists() and any((directory / name).exists() for name in ("goal.md", "plan.md", "syllabus.md")):
            raise LearningError(f"旧版 legacy 或缺失权威 state.json: {directory}；仅用 progress.py 只读检查，禁止覆盖；按 docs/architecture.md 人工迁移到新目录")
        state = _load(path)
        self._base(state, "goal", goal)
        self._history(state)
        if not isinstance(state.get("profile"), dict) or any(not isinstance(state["profile"].get(k), str) for k in ("description", "level", "motivation", "ability")):
            raise LearningError(f"Goal {goal}: profile 字段格式错误")
        self._file(directory / "goal.md")
        self._dir(directory / "tracks")
        return state

    def _validate_track(self, state, goal, track, files=True):
        self._base(state, "track", track)
        self._history(state)
        if state.get("goal_id") != goal:
            raise LearningError(f"Track {track}: goal_id 不匹配，拒绝跨目标读写")
        dependencies = state.get("dependencies")
        if not isinstance(dependencies, list) or any(not isinstance(x, str) for x in dependencies) or len(dependencies) != len(set(dependencies)):
            raise LearningError("dependencies 必须是无重复 Track ID 的数组")
        for dependency in dependencies:
            _id(dependency, "track")
            if dependency == track:
                raise LearningError("Track 不能依赖自己")
            self._file(self._tdir(goal, dependency) / "state.json")
        self._dependencies(goal, track, dependencies)
        for plural in ("milestones", "sprints"):
            if not isinstance(state.get(plural), dict):
                raise LearningError(f"{plural} 必须是以 ID 为键的对象")
            for identity, unit in state[plural].items():
                kind = "milestone" if plural == "milestones" else "sprint"
                self._base(unit, kind, identity)
                _text(unit.get("objective"), "objective")
                _criteria(unit.get("criteria"))
                _hours(unit.get("estimated_hours"))
                if kind == "sprint":
                    parent = unit.get("milestone_id")
                    if not isinstance(parent, str) or parent not in state["milestones"]:
                        raise LearningError(f"Sprint {identity}: 缺失所属 Milestone {parent!r}")
                    parent_status = state["milestones"][parent]["status"]
                    if unit["status"] == "active" and parent_status != "active":
                        raise LearningError(f"Sprint {identity}: active 必须属于 active Milestone")
                    if parent_status in TERMINAL and unit["status"] not in TERMINAL:
                        raise LearningError(f"Sprint {identity}: 已结束 Milestone 下存在未结束 Sprint")
        if sum(m["status"] == "active" for m in state["milestones"].values()) > 1:
            raise LearningError("同一 Track 最多一个进行中的 Milestone")
        for identity in state["milestones"]:
            if sum(s["status"] == "active" and s["milestone_id"] == identity for s in state["sprints"].values()) > 1:
                raise LearningError(f"Milestone {identity} 最多一个进行中的 Sprint")
        if state["status"] == "completed" and any(m["status"] not in TERMINAL for m in state["milestones"].values()):
            raise LearningError("已完成 Track 仍包含未结束 Milestone")
        if files:
            directory = self._tdir(goal, track)
            self._file(directory / "track.md")
            for plural in ("milestones", "sprints", "sessions"):
                self._dir(directory / plural)
                if plural == "sessions":
                    continue
                for identity in state[plural]:
                    self._file(directory / plural / f"{identity}.md")
                actual = {p.name for p in (directory / plural).iterdir()}
                expected = {f"{identity}.md" for identity in state[plural]}
                if actual != expected:
                    raise LearningError(f"{directory / plural}: 存在未索引/中断遗留文件 {sorted(actual - expected)}；保留文件，人工核对备份与 state.json")
        return state

    def _dependencies(self, goal, track, dependencies):
        # Visit only the declared prerequisite chain; no detailed plans are loaded.
        visiting, visited = set(), set()
        def visit(identity, links=None):
            if identity in visiting:
                raise LearningError(f"Track 前置依赖存在循环: {identity}")
            if identity in visited:
                return
            visiting.add(identity)
            if links is None:
                path = self._tdir(goal, identity) / "state.json"
                self._file(path)
                related = _load(path)
                self._base(related, "track", identity)
                if related.get("goal_id") != goal:
                    raise LearningError("依赖 Track 的 goal_id 不匹配")
                links = related.get("dependencies")
            if not isinstance(links, list) or any(not isinstance(x, str) for x in links) or len(set(links)) != len(links):
                raise LearningError(f"Track {identity}: dependencies 格式错误")
            for dependency in links:
                _id(dependency, "track")
                visit(dependency)
            visiting.remove(identity)
            visited.add(identity)
        visit(track, dependencies)

    def get_track(self, goal, track):
        parent = self.get_goal(goal)
        directory = self._tdir(goal, track)
        self._file(directory / "state.json")
        state = self._validate_track(_load(directory / "state.json"), goal, track)
        if parent["status"] == "completed" and state["status"] != "completed":
            raise LearningError(f"Goal {goal}: completed 下存在未完成 Track {track}")
        return state

    def _active(self):
        path = self._path("state", "active.json")
        state = _load(path)
        if not all(k in state for k in ("goal_id", "track_id", "updated_at")):
            raise LearningError("active.json 缺少当前学习位置字段")
        goal, track = state["goal_id"], state["track_id"]
        if goal is None and track is not None:
            raise LearningError("active.json 的 Track 缺少 Goal")
        if goal is not None:
            _id(goal, "goal")
        if track is not None:
            _id(track, "track")
        try:
            if dt.datetime.fromisoformat(state["updated_at"]).tzinfo is None:
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise LearningError("active.json updated_at 无效") from exc
        return state

    @staticmethod
    def _summary(state):
        return {k: state[k] for k in ("id", "title", "status")}

    def list_goals(self):
        directory = self._path("goals")
        self._dir(directory)
        return [self._summary(self.get_goal(p.name)) for p in sorted(directory.iterdir()) if p.is_dir()]

    def list_tracks(self, goal):
        self.get_goal(goal)
        directory = self._gdir(goal) / "tracks"
        return [self._summary(self.get_track(goal, p.name)) for p in sorted(directory.iterdir()) if p.is_dir()]

    def current(self):
        pointer = self._active()
        goal = self.get_goal(pointer["goal_id"]) if pointer["goal_id"] else None
        track = None
        if pointer["track_id"]:
            state = self.get_track(pointer["goal_id"], pointer["track_id"])
            milestone = next((m for m in state["milestones"].values() if m["status"] == "active"), None)
            sprint = next((s for s in state["sprints"].values() if s["status"] == "active"), None)
            track = {**self._summary(state), "goal_id": state["goal_id"],
                     "effective_status": state["status"] if goal["status"] == "active" else goal["status"],
                     "dependencies": state["dependencies"], "current_milestone": milestone, "current_sprint": sprint,
                     "paused_milestones": [m["id"] for m in state["milestones"].values() if m["status"] == "paused"],
                     "paused_sprints": [s["id"] for s in state["sprints"].values() if s["status"] == "paused"]}
        return {"active": pointer, "goal": goal, "track": track}

    def select(self, goal, track=None):
        with self._lock():
            old = self._active()
            self.get_goal(goal)
            if track is not None:
                self.get_track(goal, track)
            if (old["goal_id"], old["track_id"]) != (goal, track):
                _save(self._path("state", "active.json"), {"schema_version": SCHEMA_VERSION,
                      "goal_id": goal, "track_id": track, "updated_at": now()})
        return self.current()

    def _new_directory(self, target, populate):
        if target.exists():
            raise LearningError(f"重复 ID 或已有目录（包括旧版数据），拒绝覆盖: {target}")
        temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=target.parent))
        try:
            populate(temporary)
            os.rename(temporary, target)
        finally:
            if temporary.exists():
                if temporary.resolve().parent != target.parent.resolve() or not temporary.name.startswith(".pending-"):
                    raise LearningError("暂存目录路径校验失败")
                shutil.rmtree(temporary)

    def create_goal(self, title, identity=None, description="", level="", motivation="", ability=""):
        identity = _id(f"g-{uuid.uuid4().hex}" if identity is None else identity, "goal")
        state = _entity("goal", identity, title, "active")
        profile = {"description": description, "level": level, "motivation": motivation, "ability": ability}
        if any(not isinstance(v, str) for v in profile.values()):
            raise LearningError("Goal profile 必须为文本字段")
        state.update(profile=profile, history=[])
        _record(state, "goal", identity, "create", "创建学习目标", after=profile)
        with self._lock():
            self._initialized()
            def populate(directory):
                (directory / "tracks").mkdir()
                _atomic(directory / "goal.md", f"# {state['title']}\n\nID: `{identity}`\n\n画像字段和状态以 state.json 为准。此处保留偏好、补充背景和用户提供的原始说明。\n\n## 补充画像\n\n## 用户反馈\n")
                _save(directory / "state.json", state)
            self._new_directory(self._gdir(identity), populate)
        return state

    def create_track(self, goal, title, identity=None, dependencies=None, status="active"):
        identity = _id(f"t-{uuid.uuid4().hex}" if identity is None else identity, "track")
        if status not in {"active", "pending"}:
            raise LearningError("新 Track 只能为 pending 或 active")
        state = _entity("track", identity, title, status)
        state.update(goal_id=goal, dependencies=[] if dependencies is None else dependencies, milestones={}, sprints={}, history=[])
        with self._lock():
            parent = self.get_goal(goal)
            self._require_active(parent, "Goal")
            self._validate_track(state, goal, identity, files=False)
            _record(state, "track", identity, "create", "创建粗粒度学习领域")
            def populate(directory):
                for name in ("milestones", "sprints", "sessions"):
                    (directory / name).mkdir()
                _atomic(directory / "track.md", f"# {state['title']}\n\nID: `{identity}`\n\n状态、依赖和能力验收以 state.json 为准。\n\n## 粗略能力方向\n\n## 资料\n\n## 用户反馈\n")
                _save(directory / "state.json", state)
            self._new_directory(self._tdir(goal, identity), populate)
        return state

    @staticmethod
    def _require_active(entity, label):
        if entity["status"] != "active":
            raise LearningError(f"{label} 当前为 {entity['status']}，请先显式激活/恢复后再推进下级；切换位置不会改变状态")

    def _parents_active(self, goal, track):
        self._require_active(self.get_goal(goal), "Goal")
        self._require_active(track, "Track")

    def _unit(self, state, kind, identity):
        _id(identity, kind)
        plural = "milestones" if kind == "milestone" else "sprints"
        if identity not in state[plural]:
            raise LearningError(f"不存在 {kind} ID: {identity}")
        return state[plural][identity]

    def _set_status(self, state, entity, status, note):
        before = entity["status"]
        entity["status"] = status
        entity["updated_at"] = now()
        _record(state, entity["kind"], entity["id"], "transition", note,
                before={"status": before}, after={"status": status})

    def _cascade(self, state, milestone, status, note):
        for sprint in state["sprints"].values():
            if sprint["milestone_id"] != milestone["id"]:
                continue
            if (status == "paused" and sprint["status"] == "active") or (status in {"skipped", "ended"} and sprint["status"] not in TERMINAL):
                self._set_status(state, sprint, status, f"Milestone {milestone['id']} {status}: {note}")

    def create_unit(self, goal, track, kind, title, objective, criteria, identity=None,
                    milestone=None, hours=None, adjustment=None, status="active"):
        if kind not in {"milestone", "sprint"}:
            raise LearningError("单元必须为 milestone 或 sprint")
        if status not in {"pending", "active"}:
            raise LearningError("新单元只能为 pending 或 active")
        if adjustment is not None:
            adjustment = _text(adjustment, "adjustment")
        with self._lock():
            state = self.get_track(goal, track)
            self._parents_active(goal, state)
            plural, prefix = ("milestones", "M") if kind == "milestone" else ("sprints", "SP")
            if kind == "sprint":
                parent = self._unit(state, "milestone", milestone)
                self._require_active(parent, "Milestone")
                siblings = [s for s in state[plural].values() if s["milestone_id"] == milestone]
            else:
                siblings = list(state[plural].values())
            identity = _id(f"{prefix}{max((int(x[len(prefix):]) for x in state[plural]), default=0) + 1:03d}" if identity is None else identity, kind)
            if identity in state[plural]:
                raise LearningError(f"重复 {kind} ID: {identity}")
            unfinished = [s for s in siblings if s["status"] not in TERMINAL]
            if unfinished and adjustment is None:
                raise LearningError("当前单元尚未完成/跳过/结束；用户明确要求调整时才可传 --adjustment 理由创建后续单元")
            if unfinished:
                for previous in unfinished:
                    if previous["status"] == "active":
                        self._set_status(state, previous, "paused", adjustment)
                        if kind == "milestone":
                            self._cascade(state, previous, "paused", adjustment)
            unit = _entity(kind, identity, title, status)
            unit.update(objective=_text(objective, "objective"), criteria=_criteria(criteria),
                        estimated_hours=_hours(hours if hours is not None else (30 if kind == "milestone" else 5)))
            if kind == "sprint":
                unit["milestone_id"] = milestone
            state[plural][identity] = unit
            _record(state, kind, identity, "create", adjustment or "经用户确认创建当前学习单元", after=unit)
            self._validate_track(state, goal, track, files=False)
            document = self._tdir(goal, track) / plural / f"{identity}.md"
            if document.exists():
                raise LearningError(f"存在未索引的同名文档，保留并拒绝覆盖: {document}")
            _atomic(document, f"# {identity} {unit['title']}\n\n目标、验收标准、预计工作量和状态以 ../state.json 为准。\n\n## 资料与范围\n\n## 用户说明与调整\n")
            try:
                _save(self._tdir(goal, track) / "state.json", state)
            except BaseException:
                # A signal/error can arrive after replace committed successfully.
                # Remove our new document only when the old state is still readable
                # and proves that it never took ownership of this document.
                try:
                    persisted = _load(self._tdir(goal, track) / "state.json")
                except (LearningError, OSError):
                    pass
                else:
                    if isinstance(persisted.get(plural), dict) and identity not in persisted[plural]:
                        document.unlink()
                raise
        return unit

    def transition(self, goal, kind, status, note, track=None, identity=None):
        note = _text(note, "note")
        if kind not in STATUSES or status not in STATUSES[kind]:
            raise LearningError(f"非法 {kind} 状态: {status}")
        with self._lock():
            parent = self.get_goal(goal)
            state = parent if kind == "goal" else self.get_track(goal, track)
            entity = state if kind in {"goal", "track"} else self._unit(state, kind, identity)
            old = entity["status"]
            if old == status:
                return entity
            if status not in TRANSITIONS[old]:
                raise LearningError(f"非法状态转换 {old} → {status}；终态不可重开，请创建有历史说明的新单元")
            if kind != "goal" and status in {"active", "completed"}:
                self._require_active(parent, "Goal")
            if kind in {"milestone", "sprint"} and status in {"active", "completed"}:
                self._require_active(state, "Track")
            if kind == "sprint" and status in {"active", "completed"}:
                self._require_active(self._unit(state, "milestone", entity["milestone_id"]), "Milestone")
            if status == "completed":
                if kind == "goal" and any(t["status"] != "completed" for t in self.list_tracks(goal)):
                    raise LearningError("Goal 下仍有未完成 Track，请明确处理各领域后再完成目标")
                if kind == "track" and any(m["status"] not in TERMINAL for m in state["milestones"].values()):
                    raise LearningError("Track 下仍有未结束 Milestone")
                if kind == "milestone" and any(s["status"] not in TERMINAL and s["milestone_id"] == identity for s in state["sprints"].values()):
                    raise LearningError("Milestone 下仍有未结束 Sprint；必须先处理，完成数不能代表能力验收")
            self._set_status(state, entity, status, note)
            if kind == "milestone":
                self._cascade(state, entity, status, note)
            if kind == "goal":
                self._base(state, "goal", goal)
                path = self._gdir(goal) / "state.json"
            else:
                self._validate_track(state, goal, track)
                path = self._tdir(goal, track) / "state.json"
            _save(path, state)
            return entity

    def update(self, goal, kind, note, track=None, identity=None, **changes):
        note = _text(note, "note")
        if kind not in STATUSES:
            raise LearningError(f"非法类型: {kind}")
        allowed = {"title"}
        allowed |= {"description", "level", "motivation", "ability"} if kind == "goal" else {"dependencies"} if kind == "track" else {"objective", "criteria", "estimated_hours"}
        if not changes or set(changes) - allowed:
            raise LearningError(f"{kind}: 没有有效修改或字段不适用: {sorted(set(changes) - allowed)}")
        with self._lock():
            state = self.get_goal(goal) if kind == "goal" else self.get_track(goal, track)
            entity = state if kind in {"goal", "track"} else self._unit(state, kind, identity)
            if entity["status"] in TERMINAL:
                raise LearningError("已结束记录不能改写；请在新单元中记录修订理由，保留原验收与决策")
            before, after = {}, {}
            for key, value in changes.items():
                target = entity["profile"] if kind == "goal" and key in {"description", "level", "motivation", "ability"} else entity
                if key in {"title", "objective"}:
                    value = _text(value, key)
                elif key == "criteria":
                    value = _criteria(value)
                elif key == "estimated_hours":
                    value = _hours(value)
                elif key != "dependencies" and not isinstance(value, str):
                    raise LearningError(f"{key} 必须为文本")
                if target.get(key) != value:
                    before[key], after[key] = copy.deepcopy(target.get(key)), value
                    target[key] = value
            if not after:
                return entity
            entity["updated_at"] = now()
            _record(state, kind, entity["id"], "update", note, before=before, after=after)
            if kind == "goal":
                self._base(state, kind, goal)
                path = self._gdir(goal) / "state.json"
            else:
                self._validate_track(state, goal, track)
                path = self._tdir(goal, track) / "state.json"
            _save(path, state)
            return entity

    def session_spec(self, goal, track, topic, sprint=None, minutes=60):
        state = self.get_track(goal, track)
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0:
            raise LearningError("Session 建议时长必须是正整数分钟")
        if sprint is not None:
            self._unit(state, "sprint", sprint)
        return {"schema_version": SCHEMA_VERSION, "id": f"SE-{uuid.uuid4().hex}",
                "goal_id": goal, "track_id": track, "sprint_id": sprint,
                "topic": _text(topic, "topic"), "planned_minutes": minutes,
                "extensions": {}, "persisted": False}

    def sessions(self):
        if __package__:
            from .sessions import SessionStore
        else:
            from sessions import SessionStore
        return SessionStore(self)

    def validate(self):
        if self._path(".write.lock").exists():
            raise LearningError("存在写锁；请等待写入完成，或确认无写入程序后人工处理残留锁")
        self._initialized()
        pending = [str(p.relative_to(self.root)) for p in self.root.rglob(".pending-*")]
        if pending:
            raise LearningError(f"发现中断暂存文件 {pending}；保留并人工检查，不自动删除")
        goals = self.list_goals()
        count = 0
        session_count = 0
        for goal in goals:
            tracks = self.list_tracks(goal["id"])
            if goal["status"] == "completed" and any(t["status"] != "completed" for t in tracks):
                raise LearningError(f"Goal {goal['id']}: completed 下存在未完成 Track")
            count += len(tracks)
            for track in tracks:
                session_count += self.sessions().validate_track(goal["id"], track["id"])
        self.current()
        return {"valid": True, "schema_version": SCHEMA_VERSION, "goals": len(goals), "tracks": count,
                "sessions": session_count}


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise LearningError(f"参数错误: {message}")


def parser():
    ap = JsonArgumentParser(description=__doc__)
    ap.add_argument("--hub", default=None, help="数据目录；也可设置 LEARNING_COACH_HUB")
    commands = ap.add_subparsers(dest="command", required=True)
    for name in ("init", "current", "validate"):
        commands.add_parser(name)
    goal = commands.add_parser("goal-create")
    goal.add_argument("--id")
    goal.add_argument("--title", required=True)
    for key in ("description", "level", "motivation", "ability"):
        goal.add_argument(f"--{key}", default="")
    track = commands.add_parser("track-create")
    track.add_argument("--goal", required=True)
    track.add_argument("--id")
    track.add_argument("--title", required=True)
    track.add_argument("--depends-on", action="append", default=[])
    track.add_argument("--status", choices=["pending", "active"], default="active")
    listing = commands.add_parser("list")
    listing.add_argument("--goal")
    for name in ("show", "select"):
        command = commands.add_parser(name)
        command.add_argument("--goal", required=True)
        command.add_argument("--track")
    for kind in ("milestone", "sprint"):
        command = commands.add_parser(f"{kind}-create")
        command.add_argument("--goal", required=True)
        command.add_argument("--track", required=True)
        command.add_argument("--id")
        command.add_argument("--title", required=True)
        command.add_argument("--objective", required=True)
        command.add_argument("--criterion", action="append", required=True)
        command.add_argument("--hours", type=float)
        command.add_argument("--adjustment")
        command.add_argument("--status", choices=["pending", "active"], default="active")
        if kind == "sprint":
            command.add_argument("--milestone", required=True)
    for name in ("transition", "update"):
        command = commands.add_parser(name)
        command.add_argument("--goal", required=True)
        command.add_argument("--track")
        command.add_argument("--kind", choices=list(STATUSES), required=True)
        command.add_argument("--id")
        command.add_argument("--note", required=True)
        if name == "transition":
            command.add_argument("--status", required=True)
        else:
            command.add_argument("--title")
            command.add_argument("--objective")
            command.add_argument("--criterion", action="append")
            command.add_argument("--hours", type=float)
            command.add_argument("--depends-on", action="append")
            command.add_argument("--clear-dependencies", action="store_true")
            for key in ("description", "level", "motivation", "ability"):
                command.add_argument(f"--{key}")
    session = commands.add_parser("session-spec")
    session.add_argument("--goal", required=True)
    session.add_argument("--track", required=True)
    session.add_argument("--sprint")
    session.add_argument("--topic", required=True)
    session.add_argument("--minutes", type=int, default=60)
    if __package__:
        from .sessions import add_commands
    else:
        from sessions import add_commands
    add_commands(commands)
    return ap


def run(args):
    hub = Hub(args.hub)
    command = args.command
    if command == "teaching-context" or (command.startswith("session-") and command != "session-spec"):
        if __package__:
            from .sessions import run as run_session
        else:
            from sessions import run as run_session
        return run_session(hub.sessions(), args)
    if command == "init":
        return hub.initialize()
    if command in {"current", "validate"}:
        return getattr(hub, command)()
    if command == "goal-create":
        return hub.create_goal(args.title, args.id, args.description, args.level, args.motivation, args.ability)
    if command == "track-create":
        return hub.create_track(args.goal, args.title, args.id, args.depends_on, args.status)
    if command == "list":
        return hub.list_tracks(args.goal) if args.goal else hub.list_goals()
    if command == "show":
        return hub.get_track(args.goal, args.track) if args.track else hub.get_goal(args.goal)
    if command == "select":
        return hub.select(args.goal, args.track)
    if command.endswith("-create"):
        return hub.create_unit(args.goal, args.track, command.split("-")[0], args.title,
                               args.objective, args.criterion, args.id, getattr(args, "milestone", None),
                               args.hours, args.adjustment, args.status)
    if command in {"transition", "update"}:
        if args.kind != "goal" and args.track is None:
            raise LearningError("Track/Milestone/Sprint 操作必须明确 --track")
        if args.kind == "goal" and (args.track is not None or args.id is not None):
            raise LearningError("Goal 操作只使用 --goal，不接受 --track / --id")
        if args.kind == "track" and args.id is not None:
            raise LearningError("Track 操作使用 --track，不接受 --id")
        if args.kind in {"milestone", "sprint"} and args.id is None:
            raise LearningError("Milestone/Sprint 操作必须明确 --id")
        if command == "transition":
            return hub.transition(args.goal, args.kind, args.status, args.note, args.track, args.id)
        changes = {key: getattr(args, key) for key in ("title", "objective", "description", "level", "motivation", "ability") if getattr(args, key) is not None}
        for key, dest in (("criterion", "criteria"), ("hours", "estimated_hours"), ("depends_on", "dependencies")):
            if getattr(args, key) is not None:
                changes[dest] = getattr(args, key)
        if args.clear_dependencies:
            if args.depends_on:
                raise LearningError("不能同时设置 --depends-on 和 --clear-dependencies")
            changes["dependencies"] = []
        return hub.update(args.goal, args.kind, args.note, args.track, args.id, **changes)
    if command == "session-spec":
        return hub.session_spec(args.goal, args.track, args.topic, args.sprint, args.minutes)
    raise LearningError(f"未知命令: {command}")


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        result = run(parser().parse_args(argv))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (LearningError, OSError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    # Use the same module identity as sessions.py, including LearningError.
    if __package__:
        from .learning import main as entry_main
    else:
        from learning import main as entry_main
    raise SystemExit(entry_main())
