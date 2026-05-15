"""Presentación de montos en pantalla: enteros en pesos chilenos (sin decimales)."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any


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


def metrico_presentacion(val: Any, decimales: int = 2) -> str:
    """
    Cantidades no monetarias (kg, litros, etc.): hasta `decimales` (default 2), sin rellenar ceros finales en exceso.
    None / vacío → "—"
    """
    if val is None or val == "":
        return "—"
    try:
        d = val if isinstance(val, Decimal) else Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return "—"
    try:
        q = Decimal("1").scaleb(-decimales)  # 10^-decimales
        d = d.quantize(q, rounding=ROUND_HALF_UP)
        s = format(d, "f").rstrip("0").rstrip(".") if "." in format(d, "f") else format(d, "f")
        if s in ("-0", "-0."):
            s = "0"
        neg = s.startswith("-")
        body = s.lstrip("-")
        parts = body.split(".")
        intp = parts[0]
        try:
            intp_fmt = f"{int(intp):,}".replace(",", ".")
        except ValueError:
            intp_fmt = intp
        if len(parts) > 1 and parts[1]:
            return f"-{intp_fmt},{parts[1]}" if neg else f"{intp_fmt},{parts[1]}"
        return f"-{intp_fmt}" if neg else intp_fmt
    except Exception:
        return "—"
