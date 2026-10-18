"""Presentation-only number formatting. Purchases always use exact costs."""
from decimal import Decimal, ROUND_DOWN, localcontext

SUFFIXES = ("", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc")

def format_en(value: Decimal) -> str:
    with localcontext() as ctx:
        ctx.prec = 80
        if value >= Decimal("1e36"):
            return f"{value:.2E}"
        group = max(0, min(len(SUFFIXES) - 1, value.adjusted() // 3)) if value else 0
        scaled = value / (Decimal(1000) ** group)
        shown = scaled.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        text = f"{shown:,.2f}".replace(",", " ").rstrip("0").rstrip(".")
        return text + (f" {SUFFIXES[group]}" if group else "")

def exact_en(value: Decimal) -> str:
    return format(value, "f")
