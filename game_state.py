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
