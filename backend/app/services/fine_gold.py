"""Deterministic fine-gold arithmetic (PRD §3).

    Fine gold (g) = net metal weight (g) × fineness (parts per thousand) ÷ 1000

All weights are Decimal grams quantised to 0.001 g (milligram) with ROUND_HALF_UP.
Floats are never used for accounting.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

GRAM = Decimal("0.001")
ZERO = Decimal("0.000")
MAX_FINENESS_PPT = Decimal("999.9")


class WeightError(ValueError):
    pass


def to_grams(value: Decimal | int | float | str) -> Decimal:
    """Parse a weight, rejecting more than 3 decimal places instead of silently rounding."""
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise WeightError(f"Invalid weight: {value!r}") from exc
    if not d.is_finite():
        raise WeightError("Weight must be a finite number")
    if d != d.quantize(GRAM):
        raise WeightError("Weights are recorded to 0.001 g; use at most 3 decimal places")
    return d.quantize(GRAM)


def validate_fineness(ppt: Decimal | int | float | str) -> Decimal:
    try:
        d = ppt if isinstance(ppt, Decimal) else Decimal(str(ppt))
    except (InvalidOperation, ValueError) as exc:
        raise WeightError(f"Invalid fineness: {ppt!r}") from exc
    if not (Decimal(0) < d <= MAX_FINENESS_PPT):
        raise WeightError("Fineness must be greater than 0 and at most 999.9 parts per thousand")
    if d != d.quantize(Decimal("0.1")):
        raise WeightError("Fineness is recorded to 0.1 parts per thousand")
    return d.quantize(Decimal("0.1"))


def fine_gold(net_weight_g: Decimal, fineness_ppt: Decimal) -> Decimal:
    """Fine gold equivalent of a net metal weight at a fineness in parts per thousand."""
    return (Decimal(net_weight_g) * Decimal(fineness_ppt) / Decimal(1000)).quantize(GRAM, rounding=ROUND_HALF_UP)


def split_weights(gross_g: Decimal, net_g: Decimal) -> Decimal:
    """Validate gross/net and return the non-metal (stone) weight = gross − net."""
    if gross_g <= 0:
        raise WeightError("Gross weight must be greater than zero")
    if net_g <= 0:
        raise WeightError("Net metal weight must be greater than zero")
    if net_g > gross_g:
        raise WeightError("Net metal weight cannot exceed gross weight")
    return (gross_g - net_g).quantize(GRAM)
