"""
Reporte mensual de ausencias = días del mes sin marcaje de entrada (Buk Asistencia).
Cruza nómina vigente (RRHH) con jornadas del mes.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Dict, List, Optional, Set

from utils.buk_asistencia_api import (
    configuracion_resumen as asistencia_config,
    dias_marcados_por_rut,
    listar_asistencia_rango,
)
from utils.buk_presencia import listar_todos_vigentes_enriquecidos


MESES_ES = (
    "",
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


def _mes_label(anio: int, mes: int) -> str:
    return f"{MESES_ES[mes]} {anio}"


def _mes_anio_desde_request(anio: Optional[int], mes: Optional[int]) -> tuple[int, int]:
    hoy = date.today()
    y = int(anio) if anio else hoy.year
    m = int(mes) if mes else hoy.month
    if m < 1:
        m = 1
    if m > 12:
        m = 12
    return y, m


def _dias_laborables_mes(anio: int, mes: int, hasta: date) -> List[date]:
    inicio = date(anio, mes, 1)
    fin = min(hasta, date(anio, mes, calendar.monthrange(anio, mes)[1]))
    if fin < inicio:
        return []
    dias: List[date] = []
    cursor = inicio
    while cursor <= fin:
        dias.append(cursor)
        cursor += timedelta(days=1)
    return dias


def _fmt_dia(d: date) -> str:
    return d.strftime("%d/%m")


def reporte_ausencias_mes(anio: Optional[int] = None, mes: Optional[int] = None) -> dict:
    """
    Por cada vigente: días del mes (hasta hoy si es el mes en curso) sin entrada en Asistencia.
    """
    y, m = _mes_anio_desde_request(anio, mes)
    hoy = date.today()
    ultimo_mes = date(y, m, calendar.monthrange(y, m)[1])
    eval_hasta = min(ultimo_mes, hoy) if (y, m) == (hoy.year, hoy.month) else ultimo_mes

    nomina = listar_todos_vigentes_enriquecidos()
    asist_cfg = asistencia_config()
    dias_periodo = _dias_laborables_mes(y, m, eval_hasta)
    periodo_set = set(dias_periodo)

    warnings: List[str] = []
    if not asist_cfg["token_configurado"]:
        warnings.append("Configure BUK_ASISTENCIA_TOKEN en .env para calcular ausencias.")
        return {
            "ok": False,
            "filas": [],
            "anio": y,
            "mes": m,
            "mes_label": _mes_label(y, m),
            "periodo_desde": dias_periodo[0].strftime("%d-%m-%Y") if dias_periodo else "",
            "periodo_hasta": dias_periodo[-1].strftime("%d-%m-%Y") if dias_periodo else "",
            "dias_evaluados": len(dias_periodo),
            "total_vigentes": nomina.get("total") or 0,
            "con_ausencias": 0,
            "error": warnings[0],
            "warnings": warnings,
            "asistencia_config": asist_cfg,
        }

    if not dias_periodo:
        return {
            "ok": False,
            "filas": [],
            "anio": y,
            "mes": m,
            "mes_label": _mes_label(y, m),
            "periodo_desde": "",
            "periodo_hasta": "",
            "dias_evaluados": 0,
            "total_vigentes": nomina.get("total") or 0,
            "con_ausencias": 0,
            "error": "El mes seleccionado aún no tiene días evaluables.",
            "warnings": warnings,
            "asistencia_config": asist_cfg,
        }

    asist = listar_asistencia_rango(dias_periodo[0], dias_periodo[-1])
    if not asist["ok"]:
        warnings.append(asist.get("error") or "Error al consultar marcajes del mes.")
        return {
            "ok": False,
            "filas": [],
            "anio": y,
            "mes": m,
            "mes_label": _mes_label(y, m),
            "periodo_desde": dias_periodo[0].strftime("%d-%m-%Y"),
            "periodo_hasta": dias_periodo[-1].strftime("%d-%m-%Y"),
            "dias_evaluados": len(dias_periodo),
            "total_vigentes": nomina.get("total") or 0,
            "con_ausencias": 0,
            "error": asist.get("error"),
            "warnings": warnings,
            "asistencia_config": asist_cfg,
        }

    marcados = dias_marcados_por_rut(asist.get("registros") or [])
    filas: List[dict] = []

    for emp in nomina.get("empleados") or []:
        rut_norm = emp.get("rut_norm") or ""
        dias_con_marca: Set[date] = marcados.get(rut_norm, set()) & periodo_set
        dias_sin_marca = sorted(d for d in dias_periodo if d not in dias_con_marca)
        n_eval = len(dias_periodo)
        n_marca = len(dias_con_marca)
        n_aus = len(dias_sin_marca)

        filas.append({
            **emp,
            "dias_evaluados": n_eval,
            "dias_marcados": n_marca,
            "dias_ausencia": n_aus,
            "fechas_ausencia": [d.isoformat() for d in dias_sin_marca],
            "fechas_ausencia_txt": ", ".join(_fmt_dia(d) for d in dias_sin_marca),
            "pct_asistencia": round(100 * n_marca / n_eval, 1) if n_eval else 0,
        })

    filas.sort(key=lambda x: (-x.get("dias_ausencia", 0), (x.get("full_name") or "").lower()))

    con_aus = sum(1 for f in filas if f.get("dias_ausencia", 0) > 0)
    if nomina.get("error"):
        warnings.append(str(nomina["error"]))

    return {
        "ok": nomina.get("ok", False),
        "filas": filas,
        "anio": y,
        "mes": m,
        "mes_label": _mes_label(y, m),
        "periodo_desde": dias_periodo[0].strftime("%d-%m-%Y"),
        "periodo_hasta": dias_periodo[-1].strftime("%d-%m-%Y"),
        "dias_evaluados": len(dias_periodo),
        "total_vigentes": len(filas),
        "con_ausencias": con_aus,
        "marcajes_api": len(asist.get("registros") or []),
        "error": nomina.get("error"),
        "warnings": warnings,
        "asistencia_config": asist_cfg,
    }
