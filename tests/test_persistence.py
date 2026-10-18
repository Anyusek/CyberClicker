import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from decimal import Decimal
from game_state import GameState
from systems.persistence import PersistenceError, SaveStore

class SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SaveStore(Path(self.temp.name))

    def state(self, amount):
        return GameState(Decimal(amount), Decimal(amount))

    def test_missing_is_normal_new_game(self):
        result = self.store.load()
        self.assertEqual(result.state.energy, 0)
        self.assertFalse(result.warning)
        self.assertTrue(self.store.allow_write)

    def test_save_reload_and_backup(self):
        self.store.save(self.state(100))
        self.store.save(self.state(200))
        self.assertEqual(self.store.load().state.energy, 200)
        self.assertEqual(SaveStore._read(self.store.backup).energy, 100)
        self.assertFalse(list(self.store.directory.glob('*.tmp')))

    def test_corrupt_primary_requires_consent_and_preserves_bytes(self):
        self.store.save(self.state(100))
        self.store.save(self.state(200))
        broken = b'{bad json'
        self.store.path.write_bytes(broken)
        result = self.store.load()
        self.assertEqual(result.state.energy, 100)
        self.assertTrue(result.needs_consent)
        with self.assertRaises(PersistenceError):
            self.store.save(result.state)
        self.assertEqual(self.store.path.read_bytes(), broken)
        self.store.allow_write = True
        self.store.save(result.state)
        archives = list(self.store.directory.glob('save.invalid-*.json'))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), broken)
        self.assertEqual(self.store.load().state.energy, 100)

    def test_two_corrupt_files_not_silently_reset(self):
        self.store.path.write_text('bad')
        self.store.backup.write_text('also bad')
        result = self.store.load()
        self.assertTrue(result.needs_consent)
        self.assertFalse(self.store.allow_write)
        self.assertEqual(self.store.path.read_text(), 'bad')
        self.assertEqual(self.store.backup.read_text(), 'also bad')

    def test_missing_primary_recovers_backup(self):
        self.store.backup.write_text(json.dumps(self.state(55).to_dict()))
        result = self.store.load()
        self.assertEqual(result.state.energy, 55)
        self.assertTrue(result.warning)
        self.assertFalse(result.needs_consent)

    def test_invalid_backup_archived_before_replacement(self):
        self.store.save(self.state(100))
        self.store.backup.write_bytes(b'broken backup')
        self.store.save(self.state(200))
        archives = list(self.store.directory.glob('save.backup.invalid-*.json'))
        self.assertEqual(archives[0].read_bytes(), b'broken backup')
        self.assertEqual(SaveStore._read(self.store.backup).energy, 100)

    def test_failed_replace_leaves_previous_progress(self):
        self.store.save(self.state(100))
        original = self.store.path.read_bytes()
        from systems import persistence
        real_replace = persistence.os.replace
        def failing_replace(source, target):
            if Path(target) == self.store.path:
                raise OSError('simulated disk failure')
            return real_replace(source, target)
        with patch('systems.persistence.os.replace', side_effect=failing_replace):
            with self.assertRaises(PersistenceError):
                self.store.save(self.state(200))
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertEqual(self.store.load().state.energy, 100)
        self.assertFalse(list(self.store.directory.glob('*.tmp')))

    def test_large_file_rejected(self):
        self.store.path.write_bytes(b' ' * (1024 * 1024 + 1))
        self.assertTrue(self.store.load().needs_consent)

    def test_invalid_state_does_not_touch_disk(self):
        self.store.save(self.state(50))
        original = self.store.path.read_bytes()
        with self.assertRaises(PersistenceError):
            self.store.save(GameState(Decimal(99), Decimal(1)))
        self.assertEqual(self.store.path.read_bytes(), original)
