"""Read-only evidence projections and validated teaching observations.

The Agent chooses pedagogy and grades actual work. Python never infers mastery
from duration, answer counts, explanations, or teaching mode.
"""
from __future__ import annotations

import copy

if __package__:
    from .learning import LearningError
    from .sessions import fields, text, event_validity, timestamp
else:
    from learning import LearningError
    from sessions import fields, text, event_validity, timestamp


MODES = {"adaptive", "quick", "guided", "deep", "practice"}
ERROR_TYPES = {"none", "wording", "conceptual", "reasoning", "implementation", "procedure", "mixed", "unassessed"}
DEFAULT_STATE = {"mode": "adaptive", "pace": "balanced", "depth": "standard",
                 "exercise_policy": "allowed", "difficulty": "尚无教学难度记录",
                 "reason": "依据画像、真实证据和用户本次选择确定起点；不默认从零开始。"}


def choice(value, options, label):
    if not isinstance(value, str) or value not in options:
        raise LearningError(f"{label} 必须为 {sorted(options)} 之一")


def check_adaptive_event(event, sprint):
    kind = event["kind"]
    if "teaching" in event and kind != "teaching":
        raise LearningError("teaching 字段仅用于 teaching 事实")
    if kind == "teaching":
        if event["basis"] not in {"user_report", "ai_assessment"}:
            raise LearningError("教学调整是用户选择或 AI 判断，不是掌握证据")
        state = event.get("teaching")
        fields(state, set(DEFAULT_STATE))
        choice(state["mode"], MODES, "teaching.mode")
        choice(state["pace"], {"fast", "balanced", "slow"}, "teaching.pace")
        choice(state["depth"], {"overview", "standard", "deep"}, "teaching.depth")
        choice(state["exercise_policy"], {"allowed", "declined"}, "teaching.exercise_policy")
        text(state["difficulty"], "teaching.difficulty", 800)
        text(state["reason"], "teaching.reason", 1200)
    if "assessment" not in event:
        return
    if kind != "exercise":
        raise LearningError("assessment 字段仅用于 exercise 事实")
    assessment = event["assessment"]
    fields(assessment, {"form", "error_type", "checks"})
    text(assessment["form"], "assessment.form", 120)
    choice(assessment["error_type"], ERROR_TYPES, "assessment.error_type")
    checks = assessment["checks"]
    if not isinstance(checks, list) or len(checks) > 100:
        raise LearningError("assessment.checks 必须为数组，最多 100 项")
    seen = set()
    for check in checks:
        fields(check, {"criterion", "outcome", "reason"})
        text(check["criterion"], "check.criterion")
        if sprint is None or check["criterion"] not in sprint["criteria"] or check["criterion"] in seen:
            raise LearningError("checks 必须唯一对应本 Session Sprint 验收快照；计划外任务用空 checks")
        seen.add(check["criterion"])
        choice(check["outcome"], {"met", "partial", "not_met", "unverified"}, "check.outcome")
        text(check["reason"], "check.reason", 1200)
    if event.get("result") == "not_assessed":
        if assessment["error_type"] != "unassessed" or any(c["outcome"] != "unverified" for c in checks):
            raise LearningError("未批改任务只能记录 unassessed / unverified")
    elif assessment["error_type"] == "unassessed":
        raise LearningError("已批改任务需要实际错误类型，无错误用 none")
    if event.get("result") == "correct" and any(c["outcome"] in {"partial", "not_met"} for c in checks):
        raise LearningError("整体 correct 与未达标的分项批改冲突；综合题请使用 partial")
    if event.get("result") == "incorrect" and any(c["outcome"] == "met" for c in checks):
        raise LearningError("综合题已有达标分项时使用 partial，保留局部成果")


def supports_criterion(exercise, criterion):
    """Partial integrated work can independently demonstrate one criterion."""
    if "assessment" in exercise:
        return any(c["criterion"] == criterion and c["outcome"] == "met"
                   for c in exercise["assessment"]["checks"])
    return exercise["result"] == "correct"  # Phase 2A contract.


def current_events(record):
    events = {event["id"]: event for event in record["events"]}
    validity = event_validity(events)
    return [event for key, event in events.items() if validity[key]["status"] == "current"]


def observation(record, event):
    checkpoint = next(c for c in record["checkpoints"] if event["id"] in c["event_ids"])
    return {"session_id": record["id"], "event_id": event["id"], "at": checkpoint["at"],
            "basis": event["basis"], "text": event["text"], "sources": copy.deepcopy(event["sources"])}


def performance_times(record):
    """A later correction regrades old work; it is not a new performance."""
    events = {event["id"]: event for event in record["events"]}
    times = {}
    for checkpoint in record["checkpoints"]:
        for identity in checkpoint["event_ids"]:
            event = events[identity]
            related = event.get("supersedes", [])
            if not related and (checkpoint["kind"] == "correction" or event["kind"] == "evidence"):
                related = event.get("related_ids", [])
            times[identity] = max((times[key] for key in related), key=timestamp) if related else checkpoint["at"]
    return times


def coverage(records, sprint):
    """Project all criteria, not just handoff.focus_ids; retain evidence provenance.

    Most recent independently assessed evidence determines current status. New
    unverified work or self-report cannot erase earlier observed performance.
    Changed objectives/criteria do not retroactively relabel old evidence.
    """
    rows = []
    for criterion in sprint["criteria"] if sprint else []:
        evidence = []
        for record in records:
            snapshot = record["sprint_snapshot"]
            if (snapshot is None or snapshot["id"] != sprint["id"] or
                    snapshot["objective"] != sprint["objective"] or criterion not in snapshot["criteria"]):
                continue
            observed = performance_times(record)
            for event in current_events(record):
                checks = event.get("assessment", {}).get("checks", []) if event["kind"] == "exercise" else []
                if event["kind"] == "evidence":
                    checks = [{"criterion": event["criterion"], "outcome": event["outcome"], "reason": event["text"]}]
                for check in checks:
                    if check["criterion"] == criterion:
                        evidence.append({**observation(record, event), "outcome": check["outcome"],
                                         "observed_at": observed[event["id"]],
                                         "reason": check["reason"], "related_ids": event.get("related_ids", [])})
        evidence.sort(key=lambda e: (timestamp(e["observed_at"]), timestamp(e["at"])))
        independent = [e for e in evidence if e["basis"] == "exercise_verified" and e["outcome"] != "unverified"]
        reported = [e for e in evidence if e["basis"] == "user_report" and e["outcome"] != "unverified"]
        decisive = independent[-1] if independent else reported[-1] if reported else None
        status = ("verified" if decisive["outcome"] == "met" else "needs_consolidation") if independent else "user_reported" if reported else "unverified"
        rows.append({"criterion": criterion, "status": status, "decisive_evidence": decisive, "evidence": evidence})
    return rows


def context(store, goal=None, track=None, session=None, sprint=None, topic=None, limit=10):
    store.limit(limit)
    goal, track, state = store.scope(goal, track)
    parent = store.hub.get_goal(goal)
    entries, cache = store.catalog(goal, track, state)
    active = next((item for item in entries if item["status"] == "active"), None)
    anchor = store.load(goal, track, session or active["id"], state) if session or active else None
    unit = store.hub._unit(state, "sprint", sprint) if sprint else (
        state["sprints"][anchor["sprint_id"]] if anchor and anchor["sprint_id"] else
        next((item for item in state["sprints"].values() if item["status"] == "active"), None))
    topic = text(topic, "topic", 500) if topic is not None else anchor["topic"] if anchor else None
    # Limit is a read budget, never a teaching or exercise quota.
    relevant = [entry for entry in entries if (unit and entry["sprint_id"] == unit["id"]) or
                (topic and topic.casefold() in entry["topic"].casefold()) or (unit is None and topic is None)]
    relevant.sort(key=lambda e: (timestamp(e["created_at"]), e["id"]), reverse=True)
    priority = [anchor["id"]] if anchor else []
    if anchor and anchor["previous_session_id"]:
        priority.append(anchor["previous_session_id"])
    candidates = list(dict.fromkeys(priority + [item["id"] for item in relevant]))
    # An explicit predecessor and anchor are never evicted by a read limit.
    selected = candidates[:max(limit, len(priority))]
    records = [anchor if anchor and identity == anchor["id"] else store.load(goal, track, identity, state)
               for identity in selected]
    if anchor and anchor["previous_session_id"]:
        prior = next(r for r in records if r["id"] == anchor["previous_session_id"])
        if prior["status"] != "completed" or timestamp(prior["completed_at"]) > timestamp(anchor["created_at"]):
            raise LearningError("显式前序 Session 必须已结束且早于当前 Session")
    # Settings follow explicit continuity, not some more recent unrelated lesson.
    setting_records = records[:len(priority)] if anchor else records
    setting = next(((record, event) for record in setting_records
                    for event in reversed(current_events(record)) if event["kind"] == "teaching"), None)
    teaching = {**copy.deepcopy(setting[1]["teaching"] if setting else DEFAULT_STATE),
                "source": observation(*setting) if setting else None}
    rows = coverage(sorted(records, key=lambda r: timestamp(r["created_at"])), unit)
    exercises, weaknesses = [], []
    for record in records:
        for event in current_events(record):
            if event["kind"] == "exercise":
                exercises.append({**observation(record, event), **{k: copy.deepcopy(event[k]) for k in
                                  ("prompt", "answer", "result", "feedback", "assessment") if k in event}})
            elif event["kind"] in {"weakness", "unresolved"}:
                weaknesses.append({**observation(record, event), "kind": event["kind"],
                                   "scope": "historical_observation; consult latest criterion evidence"})
    omitted = len(candidates) - len(selected)
    verified = [row["criterion"] for row in rows if row["status"] == "verified"]
    gaps = [row["criterion"] for row in rows if row["status"] != "verified"]
    return {"goal": store.hub._summary(parent), "track": store.hub._summary(state),
            "profiles": {"common": store.hub._path("profile.md").read_text(encoding="utf-8"),
                         "goal": parent["profile"],
                         "goal_notes": store.hub._path("goals", goal, "goal.md").read_text(encoding="utf-8"),
                         "track_notes": store.hub._path("goals", goal, "tracks", track, "track.md").read_text(encoding="utf-8")},
            "current_milestone": state["milestones"].get(unit["milestone_id"]) if unit else None,
            "current_sprint": unit, "topic": topic,
            "learning_allowed": parent["status"] == state["status"] == "active",
            "active_session_id": active["id"] if active else None,
            "teaching_state": teaching, "criteria": rows,
            "verified_abilities": verified, "remaining_gaps": gaps,
            "exercises": exercises, "weaknesses_and_unresolved": weaknesses,
            "sessions": [store.compact(record) for record in records],
            "history": {"scope": "selected_track_only", "selected_ids": selected,
                        "omitted_sessions": omitted, "complete": omitted == 0, "index_status": cache},
            "recommendation": {
                "practice": "stop" if teaching["exercise_policy"] == "declined" else "user_choice",
                "avoid_basic_repetition": verified,
                "target_gaps": gaps,
                "may_suggest_sprint_completion": bool(rows) and not gaps and omitted == 0,
                "reason": "仅根据有效独立证据；缺少证据不等于能力不足。时长、题数、讲解次数不参与判断。",
                "lifecycle_action": "none"}}
