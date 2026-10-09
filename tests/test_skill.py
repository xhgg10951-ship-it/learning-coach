"""Exercise the skill's discoverable references and published CLI examples."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SHELL_BLOCK = re.compile(r"```shell\s*\n(.*?)```", re.S)


class SkillWorkflowTests(unittest.TestCase):
    def test_local_references_are_reachable_and_resolve(self):
        queue = [ROOT / "SKILL.md"]
        visited = set()
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            for target in LINK.findall(current.read_text(encoding="utf-8")):
                target = target.split("#", 1)[0]
                if not target or "://" in target:
                    continue
                resolved = (current.parent / target).resolve()
                self.assertTrue(resolved.is_relative_to(ROOT), f"Reference escapes skill: {target}")
                self.assertTrue(resolved.exists(), f"Broken reference in {current}: {target}")
                if resolved.suffix == ".md":
                    queue.append(resolved)
        for reference in ("onboarding", "syllabus", "planning", "progress", "session"):
            self.assertIn(ROOT / "references" / f"{reference}.md", visited)

    def test_documented_workflows_execute_in_an_isolated_hub(self):
        with tempfile.TemporaryDirectory(prefix="learning-coach-skill-") as directory:
            work = Path(directory).resolve()
            commands = set()
            session_results = []
            session_id = None
            finish_results = []
            for reference in ("onboarding", "syllabus", "planning", "session", "progress"):
                document = ROOT / "references" / f"{reference}.md"
                for block in SHELL_BLOCK.findall(document.read_text(encoding="utf-8")):
                    for line in block.splitlines():
                        if not line.strip():
                            continue
                        args = shlex.split(line)
                        if "<SESSION_ID>" in args:
                            self.assertIsNotNone(session_id, "示例必须先创建 Session")
                            args = [session_id if arg == "<SESSION_ID>" else arg for arg in args]
                        self.assertEqual(args[0], "python")
                        script = ROOT / args[1]
                        self.assertIn(script, (ROOT / "scripts/learning.py", ROOT / "scripts/progress.py"))
                        args[:2] = [sys.executable, str(script)]
                        for option in ("--hub", "--html"):
                            if option in args:
                                index = args.index(option) + 1
                                relative = Path(args[index])
                                self.assertFalse(relative.is_absolute())
                                relocated = (work / relative).resolve()
                                self.assertTrue(relocated.is_relative_to(work))
                                args[index] = str(relocated)
                        result = subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True)
                        self.assertEqual(result.returncode, 0, f"{reference}: {line}\n{result.stderr}")
                        if script.name == "learning.py":
                            command = args[args.index("--hub") + 2]
                            commands.add(command)
                            payload = json.loads(result.stdout)
                            if command == "session-spec":
                                session_results.append(payload)
                            if command == "session-start" and session_id is None:
                                session_id = payload["id"]
                            if command == "session-finish":
                                finish_results.append(payload)
            self.assertTrue({"init", "goal-create", "track-create", "select", "current", "show",
                             "milestone-create", "sprint-create", "transition", "update", "validate",
                             "session-spec"}.issubset(commands))
            self.assertTrue({"session-start", "session-checkpoint", "session-finish", "session-resume",
                             "session-context", "session-list", "session-show", "session-repair"}.issubset(commands))
            self.assertEqual(finish_results[0], finish_results[1])
            saved = json.loads(Path(finish_results[0]["record_path"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(len(saved["events"]), 10)
            self.assertEqual(len(saved["checkpoints"]), 2)
            note = Path(finish_results[0]["note_path"]).read_text(encoding="utf-8")
            self.assertIn("扩容复制成本尚不清楚", note)
            self.assertIn("用户答案：10", note)
            planning = work / "planning-demo"
            state = json.loads((planning / "goals/java-backend/tracks/spring-boot/state.json").read_text(encoding="utf-8"))
            self.assertEqual(set(state["sprints"]), {"SP001", "SP002"})
            self.assertEqual(state["milestones"]["M001"]["status"], "completed")
            self.assertTrue(all(sprint["status"] == "completed" for sprint in state["sprints"].values()))
            pointer = json.loads((planning / "state/active.json").read_text(encoding="utf-8"))
            self.assertEqual((pointer["goal_id"], pointer["track_id"]), ("java-backend", "spring-boot"))
            adjusted = json.loads((work / "adjustment-demo/goals/python/tracks/basics/state.json").read_text(encoding="utf-8"))
            self.assertEqual(adjusted["sprints"]["SP001"]["status"], "ended")
            self.assertEqual(adjusted["sprints"]["SP002"]["status"], "skipped")
            self.assertTrue(all(result["persisted"] is False for result in session_results))
            self.assertEqual({result["sprint_id"] for result in session_results}, {None, "SP001"})
            self.assertEqual(list(planning.glob("goals/*/tracks/*/sessions/*")), [])
            self.assertTrue((work / "artifacts/learning-progress.html").is_file())


if __name__ == "__main__":
    unittest.main()
