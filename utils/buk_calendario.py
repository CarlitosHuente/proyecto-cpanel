"""
Calendario mensual Buk: turnos + marcajes crudos por trabajador y recinto.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time
from typing import Dict, List, Optional, Tuple

from utils.buk_asistencia_api import (
    TZ_CHILE,
    configuracion_resumen,
    listar_recintos,
    listar_registros_recinto,
    listar_turnos_rango,
    normalizar_rut,
)
from utils.buk_colacion_config import (
    DIAS_SEMANA,
    default_minutos_recinto,
    config_recinto,
    leer_todas,
    resolver_minutos_colacion,
    resumen_grupos_texto,
)
from utils.buk_presencia import listar_todos_vigentes_enriquecidos

MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _rango_mes(anio: int, mes: int) -> Tuple[date, date]:
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo)


def _parse_horario_turno(horario: str) -> Tuple[Optional[time], Optional[time]]:
    if not horario:
        return None, None
    m = re.match(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", horario.strip())
    if not m:
        return None, None
    try:
        ini = time(int(m.group(1)), int(m.group(2)))
        fin = time(int(m.group(3)), int(m.group(4)))
        return ini, fin
    except ValueError:
        return None, None


def _dt_dia_hora(d: date, t: time) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, tzinfo=TZ_CHILE)


def _format_duracion(minutos: int) -> str:
    if minutos <= 0:
        return "0 min"
    h, m = divmod(minutos, 60)
    if h and m:
        return f"{h} h {m} min"
    if h:
        return f"{h} h"
    return f"{m} min"


def _format_delta_positivo(minutos: int) -> str:
    if minutos <= 0:
        return ""
    h, m = divmod(minutos, 60)
    if h and m:
        return f"+{h} h {m} min"
    if h:
        return f"+{h} h"
    return f"+{m} min"


def _format_entrada_tarde(minutos: int) -> str:
    d = _format_delta_positivo(minutos)
    return f"Entrada {d} tarde" if d else ""


def _format_entrada_anticipada(minutos: int) -> str:
    return f"Entrada −{minutos} min anticipada" if minutos > 0 else ""


def _format_salida_tarde(minutos: int) -> str:
    d = _format_delta_positivo(minutos)
    return f"Salida {d} tarde" if d else ""


def _format_salida_anticipada(minutos: int) -> str:
    return f"Salida −{minutos} min anticipada" if minutos > 0 else ""


def _agregar_marcajes_por_dia(registros: List[dict], rut_norm: str) -> Dict[date, dict]:
    """Primera entrada y última salida por día (ignora marcas intermedias de colación)."""
    por_dia: Dict[date, dict] = {}
    for row in registros:
        if (row.get("rut_norm") or "") != rut_norm:
            continue
        dia = row.get("fecha")
        if not isinstance(dia, date):
            continue
        marca_dt = row.get("marca_dt")
        if not isinstance(marca_dt, datetime):
            continue
        sentido = row.get("sentido") or ""
        bucket = por_dia.setdefault(dia, {"entrada": None, "salida": None})
        if sentido == "entrada":
            if bucket["entrada"] is None or marca_dt < bucket["entrada"]:
                bucket["entrada"] = marca_dt
        elif sentido == "salida":
            if bucket["salida"] is None or marca_dt > bucket["salida"]:
                bucket["salida"] = marca_dt
    return por_dia


def _turno_programado(turno: dict) -> bool:
    return not (turno.get("licencia") or turno.get("permiso") or turno.get("vacaciones"))


def _filtrar_turnos(turnos: List[dict], rut_norm: str, obra_id: str) -> Dict[date, dict]:
    try:
        obra_int = int(obra_id)
    except (TypeError, ValueError):
        obra_int = None
    out: Dict[date, dict] = {}
    for t in turnos:
        if (t.get("rut_norm") or "") != rut_norm:
            continue
        if obra_int is not None and t.get("id_recinto") != obra_int:
            continue
        dia = t.get("fecha")
        if isinstance(dia, date):
            out[dia] = t
    return out


def _construir_celda(
    dia: date,
    *,
    fuera_mes: bool,
    turno: Optional[dict],
    marca: Optional[dict],
    colacion_min: int,
    colacion_fuente: str,
    tiene_turnos_mes: bool = False,
) -> dict:
    celda = {
        "fecha": dia.isoformat(),
        "dia_num": dia.day,
        "fuera_mes": fuera_mes,
        "entrada": "",
        "salida": "",
        "horas_neto_txt": "",
        "sin_marca": False,
        "alerta_turno": False,
        "descanso": False,
        "sin_turno": False,
        "entrada_tarde_txt": "",
        "entrada_anticipada_txt": "",
        "salida_tarde_txt": "",
        "salida_anticipada_txt": "",
        "turno_horario": "",
        "licencia": False,
        "permiso": False,
        "vacaciones": False,
        "minutos_neto": 0,
        "minutos_atraso": 0,
        "minutos_entrada_anticipada": 0,
        "minutos_salida_despues": 0,
        "minutos_salida_anticipada": 0,
        "colacion_minutos": colacion_min,
        "colacion_fuente": colacion_fuente,
    }
    if fuera_mes:
        return celda

    if turno:
        celda["turno_horario"] = turno.get("horario_turno") or ""
        celda["licencia"] = bool(turno.get("licencia"))
        celda["permiso"] = bool(turno.get("permiso"))
        celda["vacaciones"] = bool(turno.get("vacaciones"))
    elif tiene_turnos_mes:
        celda["descanso"] = True
    else:
        celda["sin_turno"] = True

    entrada_dt = marca.get("entrada") if marca else None
    salida_dt = marca.get("salida") if marca else None

    if entrada_dt:
        celda["entrada"] = entrada_dt.strftime("%H:%M")
    if salida_dt:
        celda["salida"] = salida_dt.strftime("%H:%M")

    programado = turno and _turno_programado(turno)
    if programado and not entrada_dt:
        celda["sin_marca"] = True
        celda["alerta_turno"] = True

    if entrada_dt and salida_dt and salida_dt > entrada_dt:
        bruto = int((salida_dt - entrada_dt).total_seconds() // 60)
        neto = max(0, bruto - colacion_min)
        celda["minutos_neto"] = neto
        celda["horas_neto_txt"] = _format_duracion(neto)

    if turno and entrada_dt:
        ini_t, fin_t = _parse_horario_turno(turno.get("horario_turno") or "")
        if ini_t:
            ini_dt = _dt_dia_hora(dia, ini_t)
            if entrada_dt > ini_dt:
                mins = int((entrada_dt - ini_dt).total_seconds() // 60)
                celda["minutos_atraso"] = mins
                celda["entrada_tarde_txt"] = _format_entrada_tarde(mins)
            elif entrada_dt < ini_dt:
                mins = int((ini_dt - entrada_dt).total_seconds() // 60)
                celda["minutos_entrada_anticipada"] = mins
                celda["entrada_anticipada_txt"] = _format_entrada_anticipada(mins)
        if fin_t and salida_dt:
            fin_dt = _dt_dia_hora(dia, fin_t)
            if salida_dt > fin_dt:
                mins = int((salida_dt - fin_dt).total_seconds() // 60)
                celda["minutos_salida_despues"] = mins
                celda["salida_tarde_txt"] = _format_salida_tarde(mins)
            elif salida_dt < fin_dt:
                mins = int((fin_dt - salida_dt).total_seconds() // 60)
                celda["minutos_salida_anticipada"] = mins
                celda["salida_anticipada_txt"] = _format_salida_anticipada(mins)

    return celda


def _resumen_mes(celdas_mes: List[dict]) -> dict:
    dias_trabajados = 0
    dias_ausencia = 0
    dias_programados = 0
    min_atraso = 0
    min_entrada_anticipada = 0
    min_salida_despues = 0
    min_salida_anticipada = 0
    min_neto_total = 0
    licencia = permiso = vacaciones = 0

    for c in celdas_mes:
        if c.get("licencia"):
            licencia += 1
        if c.get("permiso"):
            permiso += 1
        if c.get("vacaciones"):
            vacaciones += 1
        if c.get("turno_horario") and not (c.get("licencia") or c.get("permiso") or c.get("vacaciones")):
            dias_programados += 1
            if c.get("sin_marca"):
                dias_ausencia += 1
        if c.get("entrada"):
            dias_trabajados += 1
        min_atraso += c.get("minutos_atraso") or 0
        min_entrada_anticipada += c.get("minutos_entrada_anticipada") or 0
        min_salida_despues += c.get("minutos_salida_despues") or 0
        min_salida_anticipada += c.get("minutos_salida_anticipada") or 0
        min_neto_total += c.get("minutos_neto") or 0

    promedio = int(min_neto_total / dias_trabajados) if dias_trabajados else 0
    return {
        "dias_trabajados": dias_trabajados,
        "dias_ausencia": dias_ausencia,
        "dias_programados": dias_programados,
        "tiempo_atrasado_txt": _format_duracion(min_atraso),
        "entrada_anticipada_txt": _format_duracion(min_entrada_anticipada),
        "salida_despues_txt": _format_duracion(min_salida_despues),
        "salida_anticipada_txt": _format_duracion(min_salida_anticipada),
        "horas_netas_total_txt": _format_duracion(min_neto_total),
        "promedio_dia_txt": _format_duracion(promedio),
        "licencia": licencia,
        "permiso": permiso,
        "vacaciones": vacaciones,
    }


def reporte_calendario_mes(
    anio: int,
    mes: int,
    obra_id: str,
    rut: str,
) -> dict:
    cfg = configuracion_resumen()
    rut_norm = normalizar_rut(rut)
    inicio, fin = _rango_mes(anio, mes)
    mes_label = f"{MESES_ES[mes - 1].capitalize()} {anio}"

    warnings: List[str] = []
    if not cfg.get("token_configurado"):
        warnings.append(
            "Configure BUK_ASISTENCIA_TOKEN en .env para consultar turnos y marcajes."
        )

    empleado = None
    nomina = listar_todos_vigentes_enriquecidos()
    for emp in nomina.get("empleados") or []:
        if (emp.get("rut_norm") or "") == rut_norm:
            empleado = emp
            break

    colacion_resumen = resumen_grupos_texto(obra_id) if obra_id else ""

    vacio = {
        "ok": False,
        "anio": anio,
        "mes": mes,
        "mes_label": mes_label,
        "obra_id": obra_id,
        "rut": rut,
        "rut_norm": rut_norm,
        "empleado": empleado,
        "semanas": [],
        "resumen": _resumen_mes([]),
        "colacion_resumen": colacion_resumen,
        "warnings": warnings,
        "error": None,
        "config": cfg,
    }

    if not obra_id:
        vacio["error"] = "Seleccione una sucursal (recinto)."
        return vacio
    if not rut_norm:
        vacio["error"] = "Seleccione un colaborador."
        return vacio

    turnos_res = listar_turnos_rango(inicio, fin)
    if not turnos_res["ok"]:
        vacio["error"] = turnos_res.get("error")
        return vacio

    registros_res = listar_registros_recinto(obra_id, inicio, fin, dni=rut_norm)
    if not registros_res["ok"]:
        vacio["error"] = registros_res.get("error")
        return vacio

    turnos_map = _filtrar_turnos(turnos_res["turnos"], rut_norm, obra_id)
    marcas_map = _agregar_marcajes_por_dia(registros_res["registros"], rut_norm)
    tiene_turnos_mes = len(turnos_map) > 0

    celdas_mes: List[dict] = []
    semanas: List[List[dict]] = []
    cal = calendar.Calendar(firstweekday=0)
    for semana in cal.monthdatescalendar(anio, mes):
        fila: List[dict] = []
        for dia in semana:
            fuera = dia.month != mes
            turno = turnos_map.get(dia)
            marca = marcas_map.get(dia)
            col = resolver_minutos_colacion(obra_id, dia, turno)
            celda = _construir_celda(
                dia,
                fuera_mes=fuera,
                turno=turno,
                marca=marca,
                colacion_min=col["minutos"],
                colacion_fuente=col["fuente"],
                tiene_turnos_mes=tiene_turnos_mes,
            )
            fila.append(celda)
            if not fuera:
                celdas_mes.append(celda)
        semanas.append(fila)

    return {
        "ok": True,
        "anio": anio,
        "mes": mes,
        "mes_label": mes_label,
        "periodo_desde": inicio.strftime("%d-%m-%Y"),
        "periodo_hasta": fin.strftime("%d-%m-%Y"),
        "obra_id": obra_id,
        "rut": rut,
        "rut_norm": rut_norm,
        "empleado": empleado,
        "semanas": semanas,
        "resumen": _resumen_mes(celdas_mes),
        "colacion_resumen": colacion_resumen,
        "colacion_default": default_minutos_recinto(obra_id),
        "turnos_count": len(turnos_map),
        "marcajes_count": len(marcas_map),
        "warnings": warnings,
        "error": None,
        "config": cfg,
    }


def opciones_calendario() -> dict:
    """Recintos, colaboradores vigentes y colaciones guardadas para filtros UI."""
    recintos_res = listar_recintos()
    nomina = listar_todos_vigentes_enriquecidos()
    empleados = sorted(
        nomina.get("empleados") or [],
        key=lambda e: (e.get("full_name") or "").lower(),
    )
    colaciones = leer_todas()
    configs_recinto = {}
    for r in recintos_res.get("recintos") or []:
        oid = r.get("obra_id")
        if oid:
            configs_recinto[str(oid)] = config_recinto(str(oid))
    return {
        "recintos_ok": recintos_res.get("ok", False),
        "recintos": recintos_res.get("recintos") or [],
        "recintos_error": recintos_res.get("error"),
        "empleados": empleados,
        "empleados_ok": nomina.get("ok", False),
        "colaciones": colaciones,
        "configs_recinto": configs_recinto,
        "dias_semana": list(DIAS_SEMANA),
    }
