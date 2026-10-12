"""Live Codex teaching conversations. Not part of offline unittest discovery.

Uses the configured, authenticated Codex CLI. No canned assistant responses,
no expected answers in the teacher prompt, and no access to production hubs.
Structural checks cannot replace a review of the recorded teaching behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import learning, teaching


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture(work, scenario):
    hub = learning.Hub(work / "hub")
    hub.initialize()
    (hub.root / "profile.md").write_text("# 合成学生测试画像\n已有相关基础，偏好实际任务；所有内容为验收夹具，不是实际用户学习记录。\n", encoding="utf-8")
    hub.create_goal(scenario["title"], identity="demo", level=scenario["level"])
    hub.create_track("demo", scenario["title"], identity="core")
    hub.create_unit("demo", "core", "milestone", "应用能力", scenario["title"], scenario["criteria"])
    hub.create_unit("demo", "core", "sprint", scenario["title"], scenario["title"], scenario["criteria"], milestone="M001")
    hub.select("demo", "core")
    if scenario.get("history"):
        store = hub.sessions()
        sid = store.start("demo", "core", "ArrayList", "fixture-history", sprint="SP001")["id"]
        sources = [{"ref": "synthetic-fixture/user/1", "quote": "size 是元素数；容量是底层空间。扩容需要复制。get(size) 是空指针，批量复制只调一次所以常数时间。"}]
        task = {"id": "prior-task", "kind": "exercise", "text": "合成学生先前作答", "basis": "exercise_verified",
                "sources": sources, "prompt": "解释 size、容量、扩容、边界异常和批量复制成本", "answer": sources[0]["quote"],
                "result": "partial", "feedback": "基本操作与扩容机制正确；索引越界及批量复制复杂度判断错误。"}
        events = [task]
        for n, criterion in enumerate(scenario["criteria"]):
            if n >= 2:
                break
            # Legacy Phase 2A history uses a separate correct observation.
            correct = {**task, "id": f"prior-correct-{n}", "answer": "size 是元素数；容量是底层空间。几何扩容需要复制，单次 O(n)，追加均摊 O(1)。",
                       "result": "correct", "feedback": "合成历史答案正确，作为验收输入"}
            correct["sources"] = [{"ref": f"synthetic-fixture/user/{n + 2}", "quote": correct["answer"]}]
            events += [correct, {"id": f"prior-evidence-{n}", "kind": "evidence", "text": criterion,
                                "basis": "exercise_verified", "sources": correct["sources"], "criterion": criterion,
                                "outcome": "met", "related_ids": [correct["id"]]}]
        events.append({"id": "prior-gap", "kind": "weakness", "text": "曾混淆索引越界与空指针，误判批量复制复杂度",
                       "basis": "exercise_verified", "sources": sources, "related_ids": ["prior-task"]})
        store.checkpoint("demo", "core", sid, {"operation_id": "fixture-finish", "events": events,
                         "handoff": {"summary": "合成历史：已有集合基础，异常和复制成本不稳定", "next_step": "用实际案例聚焦异常与批量复制",
                                     "focus_ids": ["prior-gap"]}}, finish=True)
    return hub


def check_state(hub, expected):
    store = hub.sessions()
    ctx = teaching.context(store)
    entries, _ = store.catalog("demo", "core", hub.get_track("demo", "core"))
    latest = max(entries, key=lambda e: e["created_at"]) if entries else None
    result = {}
    for key, wanted in expected.items():
        if key in {"mode", "pace", "depth", "exercise_policy"}:
            actual = ctx["teaching_state"][key]
        elif key == "session":
            actual = latest["status"] if latest else None
        elif key == "sprint":
            actual = hub.get_track("demo", "core")["sprints"]["SP001"]["status"]
        elif key in {"verified", "unverified", "gaps"}:
            states = {c["criterion"]: c["status"] for c in ctx["criteria"]}
            accepted = {"verified"} if key == "verified" else {"unverified"} if key == "unverified" else {"unverified", "needs_consolidation"}
            actual = [criterion for criterion in wanted if states.get(criterion) in accepted]
        else:
            raise ValueError(f"Unknown check: {key}")
        result[key] = {"expected": wanted, "actual": actual, "pass": actual == wanted}
    result["valid"] = {"pass": hub.validate()["valid"]}
    return result, ctx


def prepare(scenario_id, scenario, out):
    base = out / scenario_id
    work = base / "workspace"
    work.mkdir(parents=True)
    shutil.copy2(ROOT / "SKILL.md", work / "SKILL.md")
    for directory in ("scripts", "references", "resources", "docs"):
        shutil.copytree(ROOT / directory, work / directory, ignore=shutil.ignore_patterns(
            "__pycache__", "evals", "agent-evaluation.md", "phase2b-delivery.md"))
    hub = fixture(work, scenario)
    write(base / "initial-context.json", teaching.context(hub.sessions()))
    return base, work, hub


def run(scenario_id, scenario, out, codex, timeout):
    base, work, hub = prepare(scenario_id, scenario, out)
    messages, results = [], []
    for number, turn in enumerate(scenario["turns"], 1):
        prefix = base / f"turn-{number:02d}"
        if turn.get("fresh"):
            messages = []
        prompt = ("请使用当前工作区 SKILL.md 的 learning-coach 为下面的用户教学。先读取适用的 Skill 和引用。"
                  f"数据目录是 {hub.root}，当前 Goal=demo / Track=core。工作区是独立合成学生验收环境，"
                  "此处会话与学习记录是测试数据，不是运行测试的真实用户的学习事实。"
                  "只允许读取当前工作区的 Skill、脚本及测试 hub，并写入测试 hub 或本工作区批次输入文件。"
                  "不修改 Skill/实现、不查询主仓库或其他用户记录，不调用其他 Agent。"
                  "需要运行 CLI 时使用当前工作区 scripts/learning.py。按正常教学对话回答本轮用户，不输出测试报告。\n"
                  + ("以下是此前实际对话消息：\n" + json.dumps(messages, ensure_ascii=False) + "\n" if messages else "这是一个新对话，只可从学习记录恢复。\n")
                  + "本轮用户：\n" + turn["user"])
        prefix.with_suffix(".prompt.txt").write_text(prompt, encoding="utf-8")
        command = [codex, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--approve-for-me",
                   "-C", str(work), "-o", str(prefix.with_suffix(".response.txt")), "-"]
        started = time.time()
        print(f"{scenario_id} turn {number}: running live Agent", flush=True)
        try:
            # Stream traces to disk so service failures/timeouts retain partial evidence.
            with prefix.with_suffix(".events.jsonl").open("w", encoding="utf-8") as trace, \
                    prefix.with_suffix(".stderr.txt").open("w", encoding="utf-8") as errors:
                run_result = subprocess.run(command, input=prompt, stdout=trace, stderr=errors,
                                            encoding="utf-8", errors="replace", timeout=timeout,
                                            cwd=work, env={**os.environ, "PYTHONUTF8": "1"})
        except subprocess.TimeoutExpired as exc:
            write(prefix.with_suffix(".failure.json"), {"status": "blocked", "reason": str(exc)})
            raise RuntimeError(f"{scenario_id} turn {number} timed out; not a pass") from exc
        response_file = prefix.with_suffix(".response.txt")
        if run_result.returncode or not response_file.exists():
            raise RuntimeError(f"Live Agent failed, see {prefix}; exit={run_result.returncode}")
        response = response_file.read_text(encoding="utf-8")
        checks, context = check_state(hub, turn.get("checks", {}))
        write(prefix.with_suffix(".context.json"), context)
        row = {"turn": number, "fresh": turn.get("fresh", False), "user": turn["user"], "assistant": response,
               "engine": "codex-cli", "completion_observed": True,
               "seconds": round(time.time() - started, 2), "checks": checks,
               "structural_pass": all(c["pass"] for c in checks.values())}
        results.append(row)
        write(base / "transcript.json", results)
        messages.extend([{"role": "user", "content": turn["user"]}, {"role": "assistant", "content": response}])
        print(f"{scenario_id} turn {number}: structural_pass={row['structural_pass']}", flush=True)
    return {"scenario": scenario_id, "turns": len(results), "structural_pass": all(r["structural_pass"] for r in results),
            "behavior_review": "required; inspect actual responses and tool traces"}


def collect_native(scenario_id, scenario, out, number, agent):
    """Audit an actual independent Agent's saved response against the same fixture.

    This command does not generate a response. The caller must retain its source
    Agent trace; the supplied identity is provenance metadata, not authentication.
    """
    base = out / scenario_id
    work = base / "workspace"
    turn = scenario["turns"][number - 1]
    raw = json.loads((work / f"agent-turn-{number:02d}.json").read_text(encoding="utf-8-sig"))
    if not isinstance(raw.get("assistant"), str) or not raw["assistant"].strip() or raw.get("user") != turn["user"]:
        raise ValueError("Actual response is missing or the user message differs from the scenario")
    target = base / "transcript.json"
    results = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    if number != len(results) + 1:
        raise ValueError("Collect each completed turn in order; do not overwrite prior observations")
    checks, ctx = check_state(learning.Hub(work / "hub"), turn.get("checks", {}))
    write(base / f"turn-{number:02d}.context.json", ctx)
    row = {"turn": number, "fresh": turn.get("fresh", False), "user": raw["user"], "assistant": raw["assistant"],
           "engine": "native-independent-agent", "source_agent": agent, "completion_observed": True, "checks": checks,
           "runtime_sha256": {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [work / "SKILL.md", *sorted((work / "scripts").glob("*.py")),
                                        *sorted((work / "references").glob("*.md"))]},
           "structural_pass": all(c["pass"] for c in checks.values())}
    results.append(row)
    write(target, results)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="New isolated output directory; never a production hub")
    parser.add_argument("--scenario", action="append", choices=("arraylist", "mysql", "english", "theory"))
    parser.add_argument("--codex", default=shutil.which("codex"))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--prepare-only", action="store_true", help="Only create isolated fixtures; do not call an Agent")
    parser.add_argument("--native-turn", type=int, help="Collect an actual native Agent response from an existing prepared fixture")
    parser.add_argument("--native-agent", help="Source identity of the independently executed Agent")
    parser.add_argument("--native-completed", action="store_true", help="Caller observed successful Agent completion, not merely a candidate file")
    args = parser.parse_args()
    scenarios = json.loads((ROOT / "tests/agent_scenarios.json").read_text(encoding="utf-8"))
    if args.native_turn is not None:
        if args.prepare_only or not args.native_agent or not args.native_completed or not args.scenario or len(args.scenario) != 1:
            parser.error("--native-turn needs one --scenario, --native-agent, and observed --native-completed")
        name = args.scenario[0]
        if not 1 <= args.native_turn <= len(scenarios[name]["turns"]):
            parser.error("native turn is outside the scenario")
        row = collect_native(name, scenarios[name], args.out.resolve(), args.native_turn, args.native_agent)
        print(json.dumps({"scenario": name, "turn": row["turn"], "checks": row["checks"]}, ensure_ascii=False, indent=2))
        return 0 if row["structural_pass"] else 1
    if not args.codex and not args.prepare_only:
        parser.error("An authenticated Codex CLI is required; no mock fallback")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source_files = [ROOT / "SKILL.md", ROOT / "tests/agent_scenarios.json", ROOT / "tests/run_agent_scenarios.py",
                    *sorted((ROOT / "scripts").glob("*.py")), *sorted((ROOT / "references").glob("*.md"))]
    write(out / "manifest.json", {"type": "live-agent-eval-with-synthetic-student", "python": sys.version,
                                 "codex": subprocess.check_output([args.codex, "--version"], text=True).strip() if args.codex else None,
                                 "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}})
    summaries = []
    try:
        for name in args.scenario or scenarios:
            if args.prepare_only:
                prepare(name, scenarios[name], out)
                summaries.append({"scenario": name, "status": "prepared_not_run"})
                write(out / "summary.json", summaries)
                continue
            summaries.append(run(name, scenarios[name], out, args.codex, args.timeout))
            write(out / "summary.json", summaries)
    except (RuntimeError, OSError, learning.LearningError) as exc:
        write(out / "failure.json", {"error": str(exc), "completed": summaries})
        print(str(exc), file=sys.stderr)
        return 2
    return 0 if args.prepare_only or all(s["structural_pass"] for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
