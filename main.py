"""Windows entry point; supports a custom save directory for portable/testing use."""
import argparse
import sys
from pathlib import Path
from PyQt6.QtCore import QLockFile, QStandardPaths, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox
from systems.persistence import SaveStore
from ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="CYBER CORE — энергетический кликер")
    parser.add_argument("--save-dir", type=Path, help="Папка сохранений (необязательно)")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("CyberCore")
    app.setOrganizationName("CyberCore")
    directory = args.save_dir or Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation)) / "saves"
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        QMessageBox.critical(None, "Папка сохранений недоступна", f"{directory}\n{exc}")
        return 1
    # Prevent two processes from silently replacing each other's progress.
    lock = QLockFile(str(directory / "session.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.warning(None, "Не удалось открыть сохранение",
            "Игра уже запущена с этой папкой сохранений либо папка недоступна.\n"
            "Закройте другой экземпляр или выберите другую папку через --save-dir.")
        return 1
    store = SaveStore(directory)
    result = store.load()
    window = MainWindow(result.state, store)
    window.show()
    QTimer.singleShot(0, lambda: window.resolve_load_warning(result))
    try:
        return app.exec()
    finally:
        lock.unlock()

if __name__ == "__main__":
    sys.exit(main())

.venv/
__pycache__/
*.pyc
build/
dist/
*.spec
saves/

# План развития

## Этап 1 — рабочий фундамент: реализован

- Чистый Python-модуль состояния и экономики.
- Начисление EN, клики, две технологии, ограничения и открытия.
- Основное окно, магазин, автоматическая добыча, общая статистика.
- JSON, проверка структуры, резервная копия, восстановление и диалоги ошибок.
- Блокировка общей папки сохранений от одновременного запуска.
- Тесты расчётов, транзакционных отказов и обработки повреждённых файлов.

## Этап 2 — визуальная основа: реализована в первом варианте

- Процедурное шестигранное ядро, мягкая энергетическая линза и три орбиты.
- Пульсация, вращение, волна клика и всплывающие значения без внешних ассетов.
- Неоновые акценты ограничены игровыми элементами; читабельный спокойный фон.
- Карточки технологий, согласованные отступы, клавиатурный фокус.
- Уменьшение анимации, вертикальная компоновка и прокрутка в узком окне.

## Этап 3 — следующий самостоятельный релиз: не реализован

Достижения, игровые уровни ядра, дополнительные ветви технологий и престиж
**не входят в версию 1.0**. Для них нет фиктивных кнопок или заглушек.
Сначала стоит проверить баланс и удобство текущей версии на Windows.

### Как безопасно расширять основу

1. Новую аддитивную технологию описать в `systems/upgrades.py`. UI построит карточку
   из каталога, а модель суммирует её бонус. Для неаддитивных механик добавить
   отдельный метод/систему вместо расчётов в обработчиках Qt.
2. Изменение каталога меняет ожидаемый формат уровней. Перед релизом повысить
   `SAVE_VERSION` и написать явную миграцию старых сохранений. Простое добавление
   ключа без миграции приведёт к отказу в загрузке старой версии, а не к тихому сбросу.
3. Достижения вынести в небольшую отдельную систему, которая получает снимок
   статистики после действий. Награды применять через модель, уникально по ID.
4. Определить правила уровней ядра отдельно от уровней технологий. Добавить
   тесты порогов, покупок на границе доступности и совместимости JSON.
5. Офлайн-добыча потребует отдельного дизайна: UTC timestamp, предел отсутствия,
   защита от отрицательного интервала и явный отчёт о полученной энергии.
6. Смена формул должна сопровождаться миграцией/пересчётом `click_power` и
   `auto_rate`, которые проверяются при загрузке. Не отключать проверку молча.

Модель изменяется только из главного потока Qt. Текущий объём не нуждается
в потоках, ECS, сервис-локаторах, DI-контейнерах или отдельных файлах на каждую
кнопку. Новые модули добавлять только при появлении самостоятельной обязанности.

"""The economy and serializable state. This module can run without PyQt6."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
import math
from systems.upgrades import UPGRADES, MAX_LEVEL

# Enough precision for all supported upgrade costs and balances.
getcontext().prec = 80
MAX_ENERGY = Decimal("1e60")
MAX_CLICKS = 10**15
SAVE_VERSION = 1

@dataclass
class Settings:
    reduced_motion: bool = False

@dataclass(frozen=True)
class ActionResult:
    success: bool
    message: str
    amount: Decimal = Decimal(0)

@dataclass
class GameState:
    energy: Decimal = Decimal(0)
    total_earned: Decimal = Decimal(0)
    clicks: int = 0
    levels: dict[str, int] = field(default_factory=lambda: {key: 0 for key in UPGRADES})
    settings: Settings = field(default_factory=Settings)

    @property
    def click_power(self) -> Decimal:
        return Decimal(1) + sum((u.click_bonus * self.levels[k]
                                for k, u in UPGRADES.items()), Decimal(0))

    @property
    def auto_rate(self) -> Decimal:
        return sum((u.auto_bonus * self.levels[k] for k, u in UPGRADES.items()), Decimal(0))

    def unlocked(self, key: str) -> bool:
        return self.total_earned >= UPGRADES[key].unlock_total

    def purchase_status(self, key: str) -> ActionResult:
        if key not in UPGRADES:
            return ActionResult(False, "Неизвестная технология")
        if self.levels[key] >= MAX_LEVEL:
            return ActionResult(False, "Достигнут максимальный уровень")
        if not self.unlocked(key):
            return ActionResult(False, "Технология ещё не открыта")
        cost = UPGRADES[key].cost(self.levels[key])
        if self.energy < cost:
            return ActionResult(False, "Недостаточно энергии", cost - self.energy)
        return ActionResult(True, "Можно приобрести", cost)

    def buy(self, key: str) -> ActionResult:
        status = self.purchase_status(key)
        if not status.success:
            return status
        cost = UPGRADES[key].cost(self.levels[key])
        self.energy -= cost
        self.levels[key] += 1
        return ActionResult(True, f"{UPGRADES[key].name}: уровень {self.levels[key]}", cost)

    def _earn(self, amount: Decimal) -> Decimal:
        # Both counters saturate together; never wrap or become infinity.
        actual = min(amount, MAX_ENERGY - self.energy, MAX_ENERGY - self.total_earned)
        self.energy += actual
        self.total_earned += actual
        return actual

    def click(self) -> ActionResult:
        if self.clicks >= MAX_CLICKS or self.total_earned >= MAX_ENERGY:
            return ActionResult(False, "Достигнут предел версии 1.0")
        self.clicks += 1
        amount = self._earn(self.click_power)
        return ActionResult(True, "Импульс получен", amount)

    def advance(self, seconds: float) -> Decimal:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise ValueError("Время должно быть числом")
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Время должно быть конечным и неотрицательным")
        return self._earn(self.auto_rate * Decimal(str(seconds)))

    def to_dict(self) -> dict:
        return {
            "version": SAVE_VERSION,
            "energy": str(self.energy), "total_earned": str(self.total_earned),
            "click_power": str(self.click_power), "auto_rate": str(self.auto_rate),
            "clicks": self.clicks, "levels": dict(self.levels),
            "settings": {"reduced_motion": self.settings.reduced_motion},
        }

    @classmethod
    def from_dict(cls, data: object) -> "GameState":
        if not isinstance(data, dict):
            raise ValueError("Сохранение должно быть объектом JSON")
        if type(data.get("version")) is not int or data["version"] != SAVE_VERSION:
            raise ValueError("Неподдерживаемая версия сохранения")
        def number(key: str) -> Decimal:
            value = data.get(key)
            # Decimal values are stored as strings to avoid float rounding.
            if not isinstance(value, str) or len(value) > 100:
                raise ValueError(f"Некорректное поле {key}")
            try:
                result = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError(f"Некорректное поле {key}") from exc
            if not result.is_finite() or not 0 <= result <= MAX_ENERGY:
                raise ValueError(f"Поле {key} вне допустимого диапазона")
            # Reject pathological tiny exponents before arithmetic/formatting.
            if not -30 <= result.as_tuple().exponent <= 60:
                raise ValueError(f"Слишком высокая точность поля {key}")
            return result
        energy, total = number("energy"), number("total_earned")
        if total < energy:
            raise ValueError("Баланс превышает общий заработок")
        clicks = data.get("clicks")
        if type(clicks) is not int or not 0 <= clicks <= MAX_CLICKS:
            raise ValueError("Некорректное число кликов")
        levels = data.get("levels")
        if not isinstance(levels, dict) or set(levels) != set(UPGRADES):
            raise ValueError("Некорректный каталог улучшений")
        if any(type(v) is not int or not 0 <= v <= MAX_LEVEL for v in levels.values()):
            raise ValueError("Некорректный уровень улучшения")
        settings = data.get("settings")
        if not isinstance(settings, dict) or type(settings.get("reduced_motion")) is not bool:
            raise ValueError("Некорректные настройки")
        state = cls(energy, total, clicks, dict(levels), Settings(settings["reduced_motion"]))
        if number("click_power") != state.click_power or number("auto_rate") != state.auto_rate:
            raise ValueError("Параметры добычи не соответствуют уровням улучшений")
        return state
