"""Standalone entry-point integration check; uses temporary save files only."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import main
from systems.persistence import SaveStore
from ui.main_window import MainWindow

class SmokeApplication(QApplication):
    def __init__(self, args: list[str]):
        super().__init__(args)
        QTimer.singleShot(250, self.play)

    def play(self) -> None:
        window = next(w for w in self.topLevelWidgets() if isinstance(w, MainWindow))
        for _ in range(25):
            window.on_core(window.core.geometry_values()[0])
        window.on_buy('pulse')
        for _ in range(40):
            window.on_core(window.core.geometry_values()[0])
        window.on_buy('reactor')
        QTimer.singleShot(800, lambda: self.finish(window))

    def finish(self, window: MainWindow) -> None:
        assert window.state.clicks == 65
        assert window.state.auto_rate == 2
        assert window.state.energy > 1
        window.close()
        self.quit()

def run() -> None:
    main.QApplication = SmokeApplication
    with tempfile.TemporaryDirectory() as directory:
        sys.argv = ['main.py', '--save-dir', directory]
        assert main.main() == 0
        state = SaveStore(Path(directory)).load().state
        assert state.clicks == 65 and state.auto_rate == 2
        assert not (Path(directory) / 'session.lock').exists()
    print('PASS: real entry point, Qt event loop, 65 impulses, 2 upgrades, '
          'live auto-production, close/save, disk reload, lock release.')

if __name__ == '__main__':
    run()
