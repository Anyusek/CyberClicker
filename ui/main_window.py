"""View/controller: schedules time, calls the model and displays results."""
import time
from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QBoxLayout, QCheckBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)
from game_state import GameState
from systems.persistence import LoadResult, PersistenceError, SaveStore
from systems.upgrades import UPGRADES, MAX_LEVEL, Upgrade
from ui.core_widget import CoreWidget
from ui.formatting import exact_en, format_en

STYLE = """
QMainWindow, QWidget#canvas { background: #080e1a; color: #e7f2f7; }
QWidget { font-family: 'Segoe UI'; font-size: 14px; color: #e7f2f7; }
QScrollArea { background: #080e1a; border: none; }
QFrame#panel { background: #0d1727; border: 1px solid #25374d; border-radius: 12px; }
QFrame#card { background: #111f32; border: 1px solid #2b4159; border-radius: 8px; }
QLabel { background: transparent; border: none; }
QLabel#eyebrow { color: #91a9bf; font-size: 12px; letter-spacing: 2px; }
QLabel#title { font-size: 26px; font-weight: 700; letter-spacing: 3px; }
QLabel#energy { color: #8ffff0; font-size: 42px; font-weight: 600; }
QLabel#heading { font-size: 18px; font-weight: 600; }
QLabel#muted { color: #a0b3c8; font-size: 13px; }
QLabel#accent { color: #c2aeff; font-size: 13px; }
QLabel#stat { font-size: 20px; font-weight: 600; }
QPushButton { background: #14283d; border: 1px solid #426480; border-radius: 8px;
              padding: 10px 16px; min-height: 24px; color: #dbeaf4; }
QPushButton:hover { background: #203f57; border-color: #65ddd5; }
QPushButton:pressed { background: #285567; }
QPushButton:focus { border: 2px solid #d5ccff; }
QPushButton#buy { background: #77eee1; color: #071c24; border: 1px solid #77eee1; font-weight: 600; }
QPushButton#buy:hover { background: #a3fff0; }
QPushButton#buy:pressed { background: #43cfc5; }
QPushButton:disabled, QPushButton#buy:disabled { background: #18283c; color: #92a6bc; border-color: #344962; }
QCheckBox { color: #a8bfd0; spacing: 8px; padding: 8px 0; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #658199; border-radius: 4px; background: #0c1728; }
QCheckBox::indicator:checked { background: #77eee1; border-color: #77eee1; }
QCheckBox::indicator:focus { border: 2px solid #d5ccff; }
QScrollBar:vertical { background: #0d1727; width: 10px; }
QScrollBar::handle:vertical { background: #344c64; min-height: 32px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMessageBox { background: #0d1727; }
"""

def label(text: str, role: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget

def panel(name: str = "panel") -> QFrame:
    frame = QFrame()
    frame.setObjectName(name)
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return frame

class UpgradeCard(QFrame):
    def __init__(self, upgrade: Upgrade, buy_callback):
        super().__init__()
        self.upgrade = upgrade
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self.level = label("", "accent")
        layout.addWidget(self.level)
        layout.addWidget(label(upgrade.name, "heading", True))
        layout.addWidget(label(upgrade.description, "muted", True))
        self.condition = label("", "muted", True)
        layout.addWidget(self.condition)
        self.button = QPushButton()
        self.button.setObjectName("buy")
        self.button.setAccessibleName(f"Купить: {upgrade.name}")
        self.button.clicked.connect(lambda: buy_callback(upgrade.key))
        layout.addWidget(self.button)

    def refresh(self, state: GameState) -> None:
        u = self.upgrade
        level = state.levels[u.key]
        self.level.setText(f"{'01 / MANUAL' if u.key == 'pulse' else '02 / AUTOMATION'}    ·    LV {level:02d}")
        status = state.purchase_status(u.key)
        self.button.setEnabled(status.success)
        if level >= MAX_LEVEL:
            self.button.setText("Максимальный уровень")
            self.condition.setText("Технология полностью развита")
            self.button.setToolTip("Достигнут предел версии 1.0")
            return
        cost = u.cost(level)
        self.button.setToolTip(f"Точная стоимость: {exact_en(cost)} EN")
        if not state.unlocked(u.key):
            self.button.setText("Технология закрыта")
            self.condition.setText(f"Открытие: {format_en(state.total_earned)} / {format_en(u.unlock_total)} EN всего")
        else:
            self.button.setText(f"Улучшить  ·  {format_en(cost)} EN")
            if status.success:
                self.condition.setText("Энергии достаточно для улучшения")
            else:
                self.condition.setText(f"Не хватает {format_en(status.amount)} EN")

class MainWindow(QMainWindow):
    def __init__(self, state: GameState, store: SaveStore):
        super().__init__()
        self.state, self.store = state, store
        self.setWindowTitle("CYBER CORE • энергетическая система")
        self.setMinimumSize(720, 640)
        self.resize(1200, 880)
        self.setStyleSheet(STYLE)
        self.last_tick = time.monotonic()
        self.status_until = 0.0
        self.last_save = "Пока не сохранено"
        self.last_save_error = ""
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.setCentralWidget(self.scroll)
        canvas = QWidget()
        canvas.setObjectName("canvas")
        self.scroll.setWidget(canvas)
        root = QVBoxLayout(canvas)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(20)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.setSpacing(4)
        brand.addWidget(label("CYBER CORE", "title"))
        brand.addWidget(label("ЭНЕРГЕТИЧЕСКАЯ СИСТЕМА / v1.0", "eyebrow"))
        header.addLayout(brand)
        header.addStretch()
        self.save_button = QPushButton("Сохранить")
        self.save_button.clicked.connect(lambda: self.save_game(manual=True))
        header.addWidget(self.save_button)
        root.addLayout(header)
        self.main_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.main_layout.setSpacing(20)
        root.addLayout(self.main_layout)
        left = panel()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(24, 20, 24, 20)
        left_layout.setSpacing(6)
        left_layout.addWidget(label("ДОСТУПНАЯ ЭНЕРГИЯ", "eyebrow"))
        self.balance = label("0 EN", "energy")
        left_layout.addWidget(self.balance)
        self.output = label("", "muted", True)
        left_layout.addWidget(self.output)
        self.core = CoreWidget()
        self.core.activated.connect(self.on_core)
        self.core.set_reduced_motion(state.settings.reduced_motion)
        left_layout.addWidget(self.core, 1)
        self.feedback = label("Система готова. Создайте первый импульс.", "accent", True)
        self.feedback.setMinimumHeight(38)
        left_layout.addWidget(self.feedback)
        self.main_layout.addWidget(left, 3)
        right = panel()
        right.setMinimumWidth(340)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(16)
        right_layout.addWidget(label("ТЕХНОЛОГИИ", "eyebrow"))
        right_layout.addWidget(label("Развитие ядра", "heading"))
        self.cards = {}
        for key, upgrade in UPGRADES.items():
            card = UpgradeCard(upgrade, self.on_buy)
            self.cards[key] = card
            right_layout.addWidget(card)
        right_layout.addWidget(label("Стоимость растёт с каждым уровнем.\nАвтодобыча работает, пока игра открыта.", "muted", True))
        right_layout.addStretch()
        self.main_layout.addWidget(right, 2)
        stats = panel()
        stats_layout = QHBoxLayout(stats)
        stats_layout.setContentsMargins(24, 16, 24, 16)
        stats_layout.setSpacing(24)
        self.stat_labels = {}
        for key, title in (("earned", "ВСЕГО ДОБЫТО"), ("clicks", "ИМПУЛЬСОВ"), ("levels", "УРОВНЕЙ ТЕХНОЛОГИЙ")):
            column = QVBoxLayout()
            column.setSpacing(6)
            column.addWidget(label(title, "eyebrow"))
            self.stat_labels[key] = label("0", "stat")
            column.addWidget(self.stat_labels[key])
            stats_layout.addLayout(column, 1)
        root.addWidget(stats)
        footer = QHBoxLayout()
        self.motion_box = QCheckBox("Уменьшить анимацию")
        self.motion_box.setChecked(state.settings.reduced_motion)
        self.motion_box.toggled.connect(self.on_motion)
        footer.addWidget(self.motion_box)
        footer.addStretch()
        self.save_status = label("", "muted")
        self.save_status.setToolTip(str(store.path))
        footer.addWidget(self.save_status)
        root.addLayout(footer)
        root.addStretch()
        self.game_timer = QTimer(self)
        self.game_timer.setInterval(100)
        self.game_timer.timeout.connect(self.tick)
        self.game_timer.start()
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(15000)
        self.save_timer.timeout.connect(self.save_game)
        self.save_timer.start()
        self.refresh()
        self._responsive()

    def _advance(self) -> None:
        now = time.monotonic()
        self.state.advance(max(0.0, now-self.last_tick))
        self.last_tick = now

    def tick(self) -> None:
        self._advance()
        self.refresh()

    def message(self, text: str) -> None:
        self.feedback.setText(text)
        self.status_until = time.monotonic() + 4

    def on_core(self, point: QPointF) -> None:
        self._advance()
        result = self.state.click()
        if result.success:
            self.core.burst(point, f"+{format_en(result.amount)} EN")
            # Keep purchase/save feedback visible instead of replacing on every click.
        else:
            self.message(result.message)
        self.refresh()

    def on_buy(self, key: str) -> None:
        self._advance()  # Settle elapsed production at the OLD rate before buying.
        result = self.state.buy(key)
        self.message(result.message)
        self.refresh()

    def on_motion(self, checked: bool) -> None:
        self.state.settings.reduced_motion = checked
        self.core.set_reduced_motion(checked)
        self.message("Уменьшение анимации включено" if checked else "Анимация включена")

    def refresh(self) -> None:
        self.balance.setText(f"{format_en(self.state.energy)} EN")
        self.balance.setToolTip(f"Точный баланс: {exact_en(self.state.energy)} EN")
        self.output.setText(f"+{format_en(self.state.click_power)} EN / импульс    ·    {format_en(self.state.auto_rate)} EN / с")
        for card in self.cards.values():
            card.refresh(self.state)
        self.stat_labels["earned"].setText(f"{format_en(self.state.total_earned)} EN")
        self.stat_labels["clicks"].setText(f"{self.state.clicks:,}".replace(",", " "))
        self.stat_labels["levels"].setText(str(sum(self.state.levels.values())))
        if time.monotonic() > self.status_until:
            self.feedback.setText("Реактор вырабатывает энергию" if self.state.auto_rate else "Создайте импульс, чтобы получить энергию")
        self.save_status.setText(self.last_save if self.store.allow_write else "Запись отключена • прогресс только в памяти")
        self.save_button.setEnabled(self.store.allow_write)

    def save_game(self, manual: bool = False) -> bool:
        if not self.store.allow_write:
            return False
        self._advance()
        try:
            self.store.save(self.state)
        except PersistenceError as exc:
            error = str(exc)
            self.last_save = "Ошибка сохранения"
            self.message(error)
            # Autosave alerts once per distinct error, never silently losing progress.
            if manual or error != self.last_save_error:
                QMessageBox.warning(self, "Ошибка сохранения", error)
            self.last_save_error = error
            self.refresh()
            return False
        self.last_save_error = ""
        self.last_save = time.strftime("Сохранено %H:%M:%S")
        if manual:
            self.message("Прогресс безопасно сохранён")
        self.refresh()
        return True

    def resolve_load_warning(self, result: LoadResult) -> None:
        if not result.warning:
            return
        if result.needs_consent:
            text = (result.warning + "\n\nРазрешить сохранение этой сессии? Перед перезаписью "
                    "повреждённые файлы будут скопированы в .invalid-…json. "
                    "При выборе «Нет» существующие файлы останутся нетронутыми.")
            answer = QMessageBox.question(self, "Восстановление прогресса", text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            self.store.allow_write = answer == QMessageBox.StandardButton.Yes
        else:
            QMessageBox.warning(self, "Восстановление прогресса", result.warning)
        self.refresh()

    def _responsive(self) -> None:
        if hasattr(self, "main_layout"):
            direction = (QBoxLayout.Direction.LeftToRight if self.width() >= 1000
                         else QBoxLayout.Direction.TopToBottom)
            self.main_layout.setDirection(direction)

    def resizeEvent(self, event):
        self._responsive()
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent):
        if not self.store.allow_write:
            answer = QMessageBox.question(self, "Прогресс не сохраняется",
                "Запись отключена после ошибки загрузки. Выйти без сохранения этой сессии?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        elif not self.save_game():
            answer = QMessageBox.question(self, "Прогресс не сохранён",
                "Сохранение не удалось. Выйти без сохранения последних изменений?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.game_timer.stop()
        self.save_timer.stop()
        event.accept()
