"""Normalización de teléfonos chilenos para DespachoWeb (+569XXXXXXXX)."""
from __future__ import annotations

import re

_CELULAR_OK = re.compile(r"^\+569\d{8}$")


def formatear_celular_chile(valor: str | None) -> str | None:
    """
    Acepta: 99393805, 999393805, 56999393805, +56999393805, +56 9 9939 3805, etc.
    Devuelve '+569XXXXXXXX' o None.
    """
    if not valor:
        return None
    s = str(valor).strip()
    if _CELULAR_OK.match(s):
        return s

    digits = re.sub(r"\D", "", s)
    if not digits:
        return None

    if digits.startswith("56"):
        digits = digits[2:]

    if len(digits) == 9 and digits.startswith("9"):
        return f"+56{digits}"
    if len(digits) == 8:
        return f"+569{digits}"
    if len(digits) > 9:
        tail = digits[-9:]
        if tail.startswith("9"):
            return f"+56{tail}"
        tail8 = digits[-8:]
        if len(tail8) == 8:
            return f"+569{tail8}"
    return None


def celular_valido(valor: str | None) -> bool:
    fmt = formatear_celular_chile(valor)
    return bool(fmt and _CELULAR_OK.match(fmt))
