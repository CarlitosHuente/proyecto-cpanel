"""Presentación de montos en pantalla: enteros en pesos chilenos (sin decimales)."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional


def dinero_presentacion(val: Any) -> str:
    """
    Convierte un monto a texto sin decimales (redondeo HALF_UP al entero más cercano).
    Separador de miles: punto (estilo es-CL frecuente en tablas).
    None / vacío → "—"
    """
    if val is None or val == "":
        return "—"
    try:
        d = val if isinstance(val, Decimal) else Decimal(str(val))
    except Exception:
        return "—"
    try:
        n = int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return "—"
    s = f"{abs(n):,}".replace(",", ".")
    return f"-{s}" if n < 0 else s
