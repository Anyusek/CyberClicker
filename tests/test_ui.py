"""Real Qt widgets and input events; no display server required."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QBoxLayout, QMessageBox
from game_state import GameState
from systems.persistence import SaveStore
from ui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SaveStore(Path(self.temp.name))
        self.window = MainWindow(GameState(), self.store)
        self.window.show()
        APP.processEvents()
        self.window.game_timer.stop()
        self.window.save_timer.stop()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self.temp.cleanup()

    def test_mouse_keyboard_shop_save_restore(self):
        core = self.window.core
        center, _ = core.geometry_values()
        QTest.mouseClick(core, Qt.MouseButton.LeftButton, pos=center.toPoint())
        self.assertEqual(self.window.state.clicks, 1)
        QTest.keyClick(core, Qt.Key.Key_Space)
        QTest.keyClick(core, Qt.Key.Key_Return)
        self.assertEqual(self.window.state.clicks, 3)
        self.window.state.energy = self.window.state.total_earned = Decimal(200)
        self.window.refresh()
        QTest.mouseClick(self.window.cards['pulse'].button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.state.levels['pulse'], 1)
        self.assertEqual(self.window.state.energy, 175)
        QTest.mouseClick(self.window.cards['reactor'].button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.state.auto_rate, 2)
        self.assertEqual(self.window.state.energy, 95)
        self.window.motion_box.setChecked(True)
        self.assertTrue(self.window.core.reduced_motion)
        QTest.mouseClick(self.window.save_button, Qt.MouseButton.LeftButton)
        loaded = self.store.load().state
        self.assertEqual(loaded.levels, self.window.state.levels)
        self.assertTrue(loaded.settings.reduced_motion)
        self.assertGreaterEqual(loaded.energy, 95)

    def test_click_outside_core_does_not_mine(self):
        QTest.mouseClick(self.window.core, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
        self.assertEqual(self.window.state.clicks, 0)

    def test_disabled_purchase_and_unlock(self):
        self.assertFalse(self.window.cards['pulse'].button.isEnabled())
        self.assertFalse(self.window.cards['reactor'].button.isEnabled())
        self.window.state.energy = self.window.state.total_earned = Decimal(80)
        self.window.refresh()
        self.assertTrue(self.window.cards['reactor'].button.isEnabled())

    def test_responsive_stacks(self):
        self.window.resize(760, 680)
        APP.processEvents()
        self.assertEqual(self.window.main_layout.direction(), QBoxLayout.Direction.TopToBottom)
        self.window.resize(1200, 880)
        APP.processEvents()
        self.assertEqual(self.window.main_layout.direction(), QBoxLayout.Direction.LeftToRight)

    def test_decline_recovery_leaves_original(self):
        self.store.path.write_text('corrupt')
        result = self.store.load()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            self.window.resolve_load_warning(result)
        self.assertFalse(self.store.allow_write)
        self.assertFalse(self.window.save_button.isEnabled())
        self.assertFalse(self.window.save_game())
        self.assertEqual(self.store.path.read_text(), 'corrupt')
        # Allow teardown to save/archive without another modal question.
        self.store.allow_write = True

    def test_purchase_settles_old_rate(self):
        self.window.state.energy = self.window.state.total_earned = Decimal(200)
        with patch('ui.main_window.time.monotonic', return_value=20):
            self.window.last_tick = 10
            self.window.on_buy('reactor')
            self.assertEqual(self.window.state.energy, 120)
        with patch('ui.main_window.time.monotonic', return_value=21):
            self.window.tick()
            self.assertEqual(self.window.state.energy, 122)
        # Restore a real timestamp before teardown.
        import time
        self.window.last_tick = time.monotonic()
