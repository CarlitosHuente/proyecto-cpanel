"""Semana operativa ISO (lun–dom) — criterio habitual en Chile."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterator, Tuple


def iso_anio_semana(f: date) -> Tuple[int, int]:
    iso = f.isocalendar()
    return iso[0], iso[1]


def lunes_de_semana_iso(anio: int, semana: int) -> date:
    """Primer día (lunes) de la semana ISO `semana` del año ISO `anio`."""
    enero4 = date(anio, 1, 4)
    lunes_semana1 = enero4 - timedelta(days=enero4.weekday())
    return lunes_semana1 + timedelta(weeks=semana - 1)


def rango_semana_iso(anio: int, semana: int) -> Tuple[date, date]:
    lun = lunes_de_semana_iso(anio, semana)
    return lun, lun + timedelta(days=6)


def dias_semana_iso(anio: int, semana: int) -> list[date]:
    ini, fin = rango_semana_iso(anio, semana)
    out = []
    d = ini
    while d <= fin:
        out.append(d)
        d += timedelta(days=1)
    return out


def iterar_dias(desde: date, hasta: date) -> Iterator[date]:
    d = desde
    while d <= hasta:
        yield d
        d += timedelta(days=1)


def semana_anterior(anio: int, semana: int) -> Tuple[int, int]:
    lun = lunes_de_semana_iso(anio, semana)
    prev = lun - timedelta(days=7)
    return iso_anio_semana(prev)


def semana_siguiente(anio: int, semana: int) -> Tuple[int, int]:
    lun = lunes_de_semana_iso(anio, semana)
    nxt = lun + timedelta(days=7)
    return iso_anio_semana(nxt)


NOMBRES_DIA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
