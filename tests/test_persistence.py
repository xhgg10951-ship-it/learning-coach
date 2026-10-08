"""Real persistence boundaries plus injected replace/rename failures; never live data."""
from __future__ import annotations
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
from scripts import learning


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='learning-persistence-')
        self.addCleanup(self.temp.cleanup)
        self.hub = learning.Hub(Path(self.temp.name) / 'hub')
        self.hub.initialize()
        self.hub.create_goal('Java', identity='java')
        self.hub.create_track('java', 'Core', identity='core')
        self.path = self.hub.root / 'goals/java/tracks/core/state.json'

    def snapshot(self):
        return {str(p.relative_to(self.hub.root)): p.read_bytes()
                for p in self.hub.root.rglob('*') if p.is_file()}

    def milestone(self, **extra):
        return self.hub.create_unit('java', 'core', 'milestone', 'Build', 'Build and explain', ['Demonstrate'], **extra)

    def test_failed_atomic_replace_preserves_state_and_cleans_temporary_file(self):
        before = self.snapshot()
        with mock.patch.object(learning.os, 'replace', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):
                self.hub.update('java', 'track', 'Rename requested', track='core', title='Changed')
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.hub.validate()['valid'])

    def test_failed_unit_state_commit_rolls_back_only_new_document(self):
        before = self.snapshot()
        real_replace = learning.os.replace
        def fail_state(source, target):
            if Path(target) == self.path:
                raise OSError('simulated state commit failure')
            return real_replace(source, target)
        with mock.patch.object(learning.os, 'replace', side_effect=fail_state):
            with self.assertRaises(OSError):
                self.milestone()
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.hub.validate()['valid'])

    def test_error_after_successful_replace_keeps_committed_document(self):
        real_replace = learning.os.replace
        def commit_then_interrupt(source, target):
            real_replace(source, target)
            if Path(target) == self.path:
                raise OSError('simulated interruption after successful commit')
        with mock.patch.object(learning.os, 'replace', side_effect=commit_then_interrupt):
            with self.assertRaises(OSError):
                self.milestone()
        self.assertTrue(self.hub.validate()['valid'])
        self.assertEqual(self.hub.get_track('java', 'core')['milestones']['M001']['status'], 'active')
        self.assertTrue((self.path.parent / 'milestones/M001.md').is_file())

    def test_failed_directory_commit_cleans_its_staging_directory(self):
        before = self.snapshot()
        with mock.patch.object(learning.os, 'rename', side_effect=OSError('simulated rename failure')):
            with self.assertRaises(OSError):
                self.hub.create_goal('English', identity='english')
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(list(self.hub.root.rglob('.pending-*')))

    def test_another_process_respects_write_lock_and_can_retry_after_release(self):
        args = [sys.executable, str(ROOT / 'scripts/learning.py'), '--hub', str(self.hub.root),
                'track-create', '--goal', 'java', '--id', 'spring', '--title', 'Spring']
        before = self.snapshot()
        with self.hub._lock():
            result = subprocess.run(args, text=True, encoding='utf-8', capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertIn('写锁', json.loads(result.stderr)['error'])
            with self.assertRaises(learning.LearningError):
                self.hub.validate()
        self.assertEqual(self.snapshot(), before)
        result = subprocess.run(args, text=True, encoding='utf-8', capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.hub.list_tracks('java')), 2)

    def test_orphan_document_is_reported_without_overwriting(self):
        orphan = self.path.parent / 'milestones/M001.md'
        orphan.write_text('User recovery material', encoding='utf-8')
        before = self.snapshot()
        for operation in (self.hub.validate, self.milestone):
            with self.assertRaisesRegex(learning.LearningError, '未索引'):
                operation()
        self.assertEqual(self.snapshot(), before)

    def test_interrupted_staging_directory_is_reported_and_preserved(self):
        pending = self.hub.root / 'goals/.pending-example'
        pending.mkdir()
        (pending / 'notes.md').write_text('Original content', encoding='utf-8')
        before = self.snapshot()
        with self.assertRaisesRegex(learning.LearningError, '中断暂存'):
            self.hub.validate()
        self.assertEqual(self.snapshot(), before)

    def test_missing_active_cannot_be_silently_reinitialized(self):
        (self.hub.root / 'state/active.json').unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(learning.LearningError, 'active.json'):
            self.hub.initialize()
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_json_keys_and_nonfinite_numbers_are_clear_errors(self):
        good = self.path.read_text(encoding='utf-8')
        bad_inputs = [good.replace('"status": "active"', '"status": "active", "status": "paused"', 1),
                      good.replace('"extensions": {}', '"extensions": {"bad": NaN}', 1),
                      good.replace('"extensions": {}', '"extensions": {"bad": Infinity}', 1),
                      good.replace('"extensions": {}', '"extensions": {"bad": ' + '9' * 5000 + '}', 1)]
        for bad in bad_inputs:
            with self.subTest(bad=bad[:100]):
                self.path.write_text(bad, encoding='utf-8')
                with self.assertRaises(learning.LearningError):
                    self.hub.get_track('java', 'core')
                self.assertEqual(self.path.read_text(encoding='utf-8'), bad)

    def test_huge_hours_are_rejected_without_overflow_traceback(self):
        self.milestone()
        state = json.loads(self.path.read_text(encoding='utf-8'))
        state['milestones']['M001']['estimated_hours'] = 10 ** 400
        self.path.write_text(json.dumps(state), encoding='utf-8')
        with self.assertRaisesRegex(learning.LearningError, 'estimated_hours'):
            self.hub.get_track('java', 'core')

    def test_read_rejects_completed_goal_with_active_track(self):
        path = self.hub.root / 'goals/java/state.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        state['status'] = 'completed'
        path.write_text(json.dumps(state), encoding='utf-8')
        with self.assertRaisesRegex(learning.LearningError, '未完成 Track'):
            self.hub.get_track('java', 'core')

    def test_dependencies_reject_cycles_missing_ids_and_self_reference(self):
        self.hub.create_track('java', 'Spring', identity='spring', dependencies=['core'])
        before = self.snapshot()
        for dependencies in (['spring'], ['missing'], ['core']):
            with self.subTest(dependencies=dependencies):
                with self.assertRaises(learning.LearningError):
                    self.hub.update('java', 'track', 'Requested dependency', track='core', dependencies=dependencies)
                self.assertEqual(self.snapshot(), before)
        # Prerequisite is advisory: neither track has to finish first.
        created = self.hub.create_unit('java', 'spring', 'milestone', 'API', 'Build API', ['Run API'])
        self.assertEqual(created['status'], 'active')

    def test_auto_ids_are_unique_and_explicit_empty_ids_are_invalid(self):
        first = self.hub.create_goal('One')
        second = self.hub.create_goal('Two')
        self.assertNotEqual(first['id'], second['id'])
        before = self.snapshot()
        for operation in (lambda: self.hub.create_goal('Invalid', identity=''),
                          lambda: self.hub.create_track('java', 'Invalid', identity=''),
                          lambda: self.milestone(identity='')):
            with self.assertRaises(learning.LearningError):
                operation()
            self.assertEqual(self.snapshot(), before)

    def test_update_preserves_original_criteria_and_reason_in_history(self):
        self.milestone()
        self.hub.update('java', 'milestone', 'User narrows scope', track='core', identity='M001',
                        criteria=['Demonstrate request handling'], objective='Explain request flow')
        state = learning.Hub(self.hub.root).get_track('java', 'core')
        self.assertEqual(state['milestones']['M001']['criteria'], ['Demonstrate request handling'])
        event = state['history'][-1]
        self.assertEqual(event['before']['criteria'], ['Demonstrate'])
        self.assertEqual(event['after']['criteria'], ['Demonstrate request handling'])
        self.assertEqual(event['note'], 'User narrows scope')
        before = self.snapshot()
        self.hub.update('java', 'milestone', 'Identical retry', track='core', identity='M001',
                        criteria=['Demonstrate request handling'], objective='Explain request flow')
        self.assertEqual(self.snapshot(), before)

    def test_current_does_not_read_unrelated_damaged_goal_or_track(self):
        self.milestone()
        self.hub.select('java', 'core')
        self.hub.create_track('java', 'Unused', identity='unused')
        self.hub.create_goal('Unrelated', identity='unrelated')
        (self.hub.root / 'goals/java/tracks/unused/state.json').write_text('{bad', encoding='utf-8')
        (self.hub.root / 'goals/unrelated/state.json').write_text('{bad', encoding='utf-8')
        self.assertEqual(self.hub.current()['track']['current_milestone']['id'], 'M001')
        with self.assertRaises(learning.LearningError):
            self.hub.validate()


if __name__ == '__main__':
    unittest.main()
