"""Presentación de fechas: DDMMAAAA (ej. 28052026)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Union


def fecha_ddmmaaaa(val: Any, con_hora: bool = False) -> str:
    """
    Fecha en formato DDMMAAAA. Con hora: DDMMAAAA HH:MM.
    None / vacío → cadena vacía (Excel) o usar filtro Jinja que devuelve «—».
    """
    if val is None or val == "":
        return ""
    if isinstance(val, datetime):
        if con_hora:
            return val.strftime("%d%m%Y %H:%M")
        return val.strftime("%d%m%Y")
    if isinstance(val, date):
        return val.strftime("%d%m%Y")
    s = str(val).strip()
    if not s:
        return ""
    # ISO YYYY-MM-DD o YYYY-MM-DD HH:MM:SS
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        try:
            if con_hora and len(s) >= 16:
                dt = datetime.fromisoformat(s[:19].replace(" ", "T"))
                return dt.strftime("%d%m%Y %H:%M")
            d = date.fromisoformat(s[:10])
            return d.strftime("%d%m%Y")
        except ValueError:
            pass
    return s[:10]
