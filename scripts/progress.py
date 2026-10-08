#!/usr/bin/env python3
"""Read-only progress summaries for v2 hubs and explicitly labelled legacy files.

Dates are display metadata only. No completion, mastery, delay or planning decision
is inferred from elapsed time, checkbox totals or estimated hours.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

DEFAULT_HUB = Path.home() / "learning-hub"
RE_STAGE = re.compile(r"^##\s+(.+?)\s*$")
RE_MODULE = re.compile(r"^###\s+\[(.)\]\s+(S\d+-M\d+)\s+(.+?)\s*$")
RE_HOURS = re.compile(r"预计耗时[:：]\s*([\d.]+)")
RE_MONTH = re.compile(r"^##\s+(\d{4})-(\d{2})\s*月")
RE_WEEK = re.compile(r"^###\s+(\d{4})-W(\d{1,2})")
RE_ITEM = re.compile(r"^\s*-\s+\[(.)\]\s+((?:W\d+-\d+)|(?:M\d+))[:：]\s*(.+?)\s*$")
RE_SECTION = re.compile(r"^##\s+")
LEGACY_WARNING = (
    "legacy：按旧版模板只读解析；保留原始日期和勾选标记。"
    "这些标记不等于能力掌握证明，不会自动迁移、顺延或推进状态。"
)


class ProgressError(ValueError):
    """A progress input cannot be summarized safely."""


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


def frontmatter(text: str) -> dict:
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    out: dict = {}
    if not match:
        return out
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip()] = value.split("#", 1)[0].strip()
    return out


def parse_syllabus(text: str) -> list[dict]:
    """Preserve legacy module markers; do not interpret them as mastery."""
    modules, stage, current = [], "", None
    for line in text.splitlines():
        match = RE_MODULE.match(line)
        if match:
            current = {"status": match.group(1), "id": match.group(2),
                       "name": match.group(3), "stage": stage, "hours": None}
            modules.append(current)
            continue
        if re.match(r"^###\s+", line):
            current = None  # Unknown headings must not lend metadata to a prior module.
            continue
        match = RE_STAGE.match(line)
        if match and not line.startswith("###"):
            stage, current = match.group(1), None
            continue
        if current is not None:
            match = RE_HOURS.search(line)
            if match:
                try:
                    value = float(match.group(1))
                    if math.isfinite(value):
                        current["hours"] = value
                except ValueError:
                    pass
    return modules


def parse_plan(text: str) -> dict:
    """Read historical calendar labels without comparing them to today's date."""
    months: list[dict] = []
    weeks: list[dict] = []
    current_month = current_week = None
    for line in text.splitlines():
        match = RE_MONTH.match(line)
        if match:
            current_month = {"month": f"{match.group(1)}-{match.group(2)}", "items": []}
            months.append(current_month)
            current_week = None
            continue
        match = RE_WEEK.match(line)
        if match:
            current_week = {"year": int(match.group(1)), "week": int(match.group(2)),
                            "label": line.lstrip("# ").strip(), "items": []}
            weeks.append(current_week)
            continue
        if RE_SECTION.match(line) or re.match(r"^###\s+", line):
            current_month = current_week = None
            continue
        match = RE_ITEM.match(line)
        if match:
            item = {"status": match.group(1), "id": match.group(2), "text": match.group(3)}
            if current_week is not None and item["id"].startswith("W"):
                current_week["items"].append(item)
            elif current_month is not None and item["id"].startswith("M"):
                current_month["items"].append(item)
    return {"months": months, "weeks": weeks}


def parse_sessions(directory: Path, warnings: list[str] | None = None) -> list[dict]:
    """Preserve legacy session files even when their metadata is incomplete."""
    warnings = warnings if warnings is not None else []
    sessions = []
    if not directory.exists():
        return sessions
    if not directory.is_dir():
        raise ProgressError(f"legacy sessions 路径不是文件夹：{directory}")
    for path in sorted(directory.glob("*.md")):
        metadata = frontmatter(read(path))
        date = metadata.get("date") or path.name[:10]
        try:
            dt.date.fromisoformat(date)
        except ValueError:
            warnings.append(f"legacy session {path.name}：日期无法识别，保留原始值。")
        minutes = None
        raw_minutes = metadata.get("minutes")
        if raw_minutes:
            try:
                number = float(raw_minutes)
                if number < 0 or not math.isfinite(number):
                    raise ValueError
                minutes = int(number)
            except ValueError:
                warnings.append(f"legacy session {path.name}：minutes 无效，未计入时长。")
        sessions.append({"date": date, "topic": metadata.get("topic", path.stem),
                         "minutes": minutes, "file": path.name})
    return sessions


def analyze_goal(directory: Path, today: dt.date | None = None) -> dict:
    """Compatibility reader for legacy goals. ``today`` never changes results."""
    if (directory / "state.json").exists() or (directory / "tracks").exists():
        raise ProgressError(f"{directory}：新版 Goal 必须通过 Hub 读取，不能按旧模板解析。")
    warnings = [LEGACY_WARNING]
    metadata = frontmatter(read(directory / "goal.md"))
    syllabus = read(directory / "syllabus.md")
    plan_text = read(directory / "plan.md")
    modules = parse_syllabus(syllabus)
    plan = parse_plan(plan_text)
    if not (directory / "goal.md").is_file():
        warnings.append("legacy：缺少 goal.md，目标标题使用目录名。")
    if not (directory / "syllabus.md").is_file():
        warnings.append("legacy：缺少 syllabus.md，模块数量未知。")
    elif syllabus.strip() and not modules:
        warnings.append("legacy：syllabus.md 不符合可识别的旧版模块格式，模块数量未知。")
    if plan_text.strip() and not (plan["months"] or plan["weeks"]):
        warnings.append("legacy：plan.md 不符合可识别的旧版计划格式，保留原文件供人工核对。")
    module_lines = [line for line in syllabus.splitlines() if re.match(r"^###\s+\[", line)]
    if len(module_lines) != len(modules):
        warnings.append("legacy：部分模块标题无法解析，以下统计仅包含可识别模块，请核对原文件。")
    plan_items = sum(len(section["items"]) for sections in plan.values() for section in sections)
    checklist_lines = [line for line in plan_text.splitlines() if re.match(r"^\s*-\s+\[.\]", line)]
    if len(checklist_lines) != plan_items:
        warnings.append("legacy：部分计划条目无法解析，以下列表仅包含可识别条目，请核对原文件。")
    for module in modules:
        if module["status"] not in {" ", "x", "~", ">", "-"}:
            warnings.append(f"legacy：模块 {module['id']} 的标记 {module['status']!r} 无法解释。")
    sessions = parse_sessions(directory / "sessions", warnings)
    active = [module for module in modules if module["status"] != "-"]
    known_modules = bool(modules)
    return {
        "id": directory.name, "slug": directory.name,
        "title": metadata.get("title", directory.name),
        "status": metadata.get("status", "unknown"),
        "format": "legacy", "legacy": True, "warnings": warnings,
        "metadata": metadata, "modules": modules,
        "module_total": len(active) if known_modules else None,
        "module_marked_done": sum(module["status"] == "x" for module in active) if known_modules else None,
        "module_marked_doing": sum(module["status"] == "~" for module in active) if known_modules else None,
        "estimated_hours": (sum(module["hours"] for module in active)
                            if known_modules and all(module["hours"] is not None for module in active)
                            else None),
        "plan": plan, "sessions": sessions,
    }


def effective_status(saved: str, parent: str) -> str:
    """Display a parent's pause without changing saved child or terminal status."""
    return "paused" if parent == "paused" and saved in {"pending", "active", "paused"} else saved


def status_label(entity: dict) -> str:
    saved, effective = entity["status"], entity["effective_status"]
    if saved != effective:
        return f"保存状态 {saved}；当前有效状态 {effective}（上级已暂停）"
    return saved


def _read_v2_goal(hub_path: Path, goal_id: str, track_id: str | None) -> dict:
    if __package__:
        from .learning import Hub
    else:
        from learning import Hub
    hub = Hub(hub_path)
    state = hub.get_goal(goal_id)
    track_ids = [track_id] if track_id else [item["id"] for item in hub.list_tracks(goal_id)]
    tracks = []
    for selected_id in track_ids:
        track = hub.get_track(goal_id, selected_id)
        track_status = effective_status(track["status"], state["status"])
        milestones = {
            identity: {**item, "effective_status": effective_status(item["status"], track_status)}
            for identity, item in track["milestones"].items()
        }
        sprints = [
            {**item, "effective_status": effective_status(
                item["status"], milestones[item["milestone_id"]]["effective_status"])}
            for item in track["sprints"].values()
        ]
        tracks.append({
            "id": track["id"], "title": track["title"], "status": track["status"],
            "effective_status": track_status,
            "milestones": list(milestones.values()), "sprints": sprints,
        })
    return {
        "id": state["id"], "slug": state["id"], "title": state["title"],
        "status": state["status"], "format": "v2", "schema_version": 2,
        "legacy": False, "warnings": [], "tracks": tracks,
    }


def load_goals(hub_path: Path, goal_id: str | None = None, track_id: str | None = None) -> list[dict]:
    if track_id and not goal_id:
        raise ProgressError("--track 必须与 --goal 一起使用。")
    root = hub_path / "goals"
    if root.exists() and not root.is_dir():
        raise ProgressError(f"目标目录不是文件夹：{root}")
    if not root.exists() and (hub_path / "state" / "active.json").exists():
        raise ProgressError(f"新版数据目录缺少 goals/：{hub_path}；未按空数据汇总。")
    directories = sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []
    if goal_id:
        directories = [path for path in directories if path.name == goal_id]
        if not directories:
            raise ProgressError(f"未找到 Goal：{goal_id}")
    goals = []
    for directory in directories:
        if (directory / "state.json").exists():
            goals.append(_read_v2_goal(hub_path, directory.name, track_id))
        elif (directory / "tracks").exists():
            raise ProgressError(f"新版 Goal {directory.name} 缺少 state.json；未按旧格式解析。")
        elif any((directory / name).exists() for name in ("goal.md", "syllabus.md", "plan.md", "sessions")):
            if track_id:
                raise ProgressError(f"legacy Goal {directory.name} 没有 Track 结构。")
            goals.append(analyze_goal(directory))
        else:
            raise ProgressError(f"无法识别 Goal 目录 {directory}，没有状态文件或旧版文档。")
    return sorted(goals, key=lambda goal: goal["status"] != "active")


def summary_text(goals: list[dict], today: dt.date) -> str:
    lines = [f"学习进度 · 展示日期 {today.isoformat()}（日期不驱动状态）"]
    if not goals:
        lines.append("未找到学习目标。")
    for goal in goals:
        lines.append(f"\n{goal['title']} [{goal['id']}] status={goal['status']} format={goal['format']}")
        for warning in goal["warnings"]:
            lines.append(f"提示：{warning}")
        if goal["legacy"]:
            if goal["module_total"] is None:
                lines.append("旧版模块数量：未知；请核对原始文件。")
            else:
                hours = f"{goal['estimated_hours']:g}h" if goal["estimated_hours"] is not None else "未知"
                lines.append(f"旧版模块标记：勾选完成 {goal['module_marked_done']}/{goal['module_total']}，"
                             f"进行中 {goal['module_marked_doing']}；预计总时长 {hours}。")
                lines.extend(f"  [{module['status']}] {module['id']}: {module['name']}"
                             for module in goal["modules"])
            lines.append(f"旧版学习记录文件：{len(goal['sessions'])} 份。")
            for session in goal["sessions"][-3:]:
                minutes = f"{session['minutes']} 分钟" if session["minutes"] is not None else "时长未知"
                lines.append(f"  {session['date']} · {session['topic']} · {minutes}")
            for month in goal["plan"]["months"]:
                lines.append(f"历史月份标签 {month['month']}：")
                lines.extend(f"  [{item['status']}] {item['id']}: {item['text']}" for item in month["items"])
            for week in goal["plan"]["weeks"]:
                lines.append(f"历史周标签 {week['label']}：")
                lines.extend(f"  [{item['status']}] {item['id']}: {item['text']}" for item in week["items"])
            continue
        lines.append("状态是已保存的用户决策与验收记录，不从数量或时长推断能力掌握。")
        if not goal["tracks"]:
            lines.append("尚无 Track。")
        for track in goal["tracks"]:
            lines.append(f"  Track {track['id']} · {track['title']} [{status_label(track)}]")
            for field, label in (("milestones", "Milestone"), ("sprints", "Sprint")):
                if not track[field]:
                    lines.append(f"    尚无 {label}。")
                for item in track[field]:
                    parent = f" → {item['milestone_id']}" if field == "sprints" else ""
                    lines.append(f"    {label} {item['id']}{parent} · {item['title']} [{status_label(item)}]")
                    lines.append(f"      能力目标：{item['objective']}")
                    lines.extend(f"      验收标准：{criterion}" for criterion in item["criteria"])
    return "\n".join(lines)


def validate_html_path(output: Path, hub_path: Path) -> Path:
    output = output.expanduser().resolve()
    hub = hub_path.expanduser().resolve()
    if output == hub or hub in output.parents:
        raise ProgressError("HTML 输出必须位于学习数据目录之外，避免覆盖 hub 中的原始数据。")
    if output.suffix.lower() != ".html":
        raise ProgressError("HTML 输出文件须使用 .html 扩展名。")
    return output


def write_html(output: Path, summary: str) -> None:
    document = ("<!doctype html>\n<html lang=\"zh-CN\"><meta charset=\"utf-8\">"
                "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                "<title>学习进度</title><style>body{font-family:system-ui,sans-serif;"
                "max-width:68rem;margin:2rem auto;padding:0 1rem;line-height:1.7}"
                "pre{font-family:inherit;white-space:pre-wrap;overflow-wrap:anywhere}"
                "</style><body><pre>" + html.escape(summary) + "</pre></body></html>\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent,
                                         prefix=f".{output.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", help="数据目录；默认 LEARNING_COACH_HUB 或 ~/learning-hub")
    parser.add_argument("--goal")
    parser.add_argument("--track", help="仅展示所选 Goal 下的一个 Track")
    parser.add_argument("--today", help="展示日期 YYYY-MM-DD；不参与规划或状态计算")
    parser.add_argument("--html", help="数据目录之外的 .html 摘要文件")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        today = dt.date.fromisoformat(arguments.today) if arguments.today else dt.date.today()
        hub_path = Path(arguments.hub or os.environ.get("LEARNING_COACH_HUB") or DEFAULT_HUB).expanduser()
        output = validate_html_path(Path(arguments.html), hub_path) if arguments.html else None
        goals = load_goals(hub_path, arguments.goal, arguments.track)
        summary = summary_text(goals, today)
        if output:
            write_html(output, summary)
        if arguments.json:
            print(json.dumps({"today": today.isoformat(), "goals": goals}, ensure_ascii=False, indent=2,
                             allow_nan=False))
        else:
            print(summary)
        if output:
            print(f"HTML 摘要已生成：{output}", file=sys.stderr)
        return 0
    except (OSError, ValueError, ImportError, KeyError, TypeError) as error:
        print(f"进度读取失败：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
