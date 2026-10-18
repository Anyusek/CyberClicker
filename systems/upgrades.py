"""Data-driven technology catalogue; no Qt dependencies."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, localcontext

MAX_LEVEL = 200

@dataclass(frozen=True)
class Upgrade:
    key: str
    name: str
    description: str
    base_cost: Decimal
    growth: Decimal
    click_bonus: Decimal = Decimal(0)
    auto_bonus: Decimal = Decimal(0)
    unlock_total: Decimal = Decimal(0)

    def cost(self, level: int) -> Decimal:
        if type(level) is not int or not 0 <= level < MAX_LEVEL:
            raise ValueError("Недопустимый уровень покупки")
        with localcontext() as ctx:
            ctx.prec = 80
            return (self.base_cost * self.growth ** level).to_integral_value(
                rounding=ROUND_CEILING)

UPGRADES: dict[str, Upgrade] = {
    "pulse": Upgrade("pulse", "Импульсный усилитель", "+1 EN за каждый импульс",
                     Decimal(25), Decimal("1.45"), click_bonus=Decimal(1)),
    "reactor": Upgrade("reactor", "Автономный реактор", "+2 EN/с непрерывной добычи",
                       Decimal(80), Decimal("1.55"), auto_bonus=Decimal(2),
                       unlock_total=Decimal(50)),
}

