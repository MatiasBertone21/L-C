from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from bson import Decimal128, ObjectId

from app.core.exceptions import DomainValidationError

DEC2 = Decimal("0.01")
DEC6 = Decimal("0.000001")


def to_decimal(val: Any, default: Decimal | None = Decimal("0")) -> Decimal | None:
    if val is None:
        return default
    if isinstance(val, Decimal128):
        return val.to_decimal()
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def to_dec128(val: Decimal | float | int | None, quant: Decimal = DEC6) -> Decimal128 | None:
    if val is None:
        return None
    dec = val if isinstance(val, Decimal) else Decimal(str(val))
    return Decimal128(dec.quantize(quant, rounding=ROUND_HALF_UP))


def to_money_float(val: Any, decimals: int = 2) -> float | None:
    dec = to_decimal(val, default=None)
    if dec is None:
        return None
    q = Decimal("1").scaleb(-decimals)
    return float(dec.quantize(q, rounding=ROUND_HALF_UP))


def parse_object_id(raw_id: str, label: str = "ID") -> ObjectId:
    if not ObjectId.is_valid(raw_id):
        raise DomainValidationError(f"{label} inválido: '{raw_id}'.")
    return ObjectId(raw_id)
