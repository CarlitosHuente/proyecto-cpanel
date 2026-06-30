"""
Cruza nómina vigente (Buk RRHH) con marcajes del día (Buk Asistencia).
Solo lectura; no persiste en MySQL.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from utils.buk_api import (
    _request as rrhh_request,
    listar_trabajadores_vigentes,
    normalizar_empleado,
)
from utils.buk_asistencia_api import (
    configuracion_resumen as asistencia_config,
    listar_asistencia_dia,
    normalizar_rut,
)


def _role_nombre(role) -> str:
    if isinstance(role, dict):
        return (role.get("name") or role.get("code") or "").strip()
    return (role or "").strip() if role else ""


def _enriquecer_desde_raw(raw: dict, areas: Dict[int, str], recintos: Dict[str, str]) -> dict:
    base = normalizar_empleado(raw)
    job = raw.get("current_job") if isinstance(raw.get("current_job"), dict) else {}
    area_id = job.get("area_id")
    ctrlit = (job.get("custom_attributes") or {}).get("ctrlit_recinto") or ""
    ctrlit = str(ctrlit).strip() if ctrlit else ""
    base["cargo"] = _role_nombre(job.get("role"))
    base["area_id"] = area_id
    base["area_nombre"] = areas.get(area_id, "") if area_id else ""
    base["recinto_codigo"] = ctrlit if ctrlit not in ("", "sin_recinto", "None") else ""
    base["recinto_nombre"] = recintos.get(base["recinto_codigo"], base["recinto_codigo"])
    base["rut_norm"] = normalizar_rut(base.get("rut"))
    return base


def _mapa_areas() -> Dict[int, str]:
    ok, payload, _ = rrhh_request("areas", {"page": 1, "page_size": 100})
    if not ok or not isinstance(payload, dict):
        return {}
    data = payload.get("data") or []
    return {row["id"]: row.get("name") or "" for row in data if isinstance(row, dict) and row.get("id")}


def _mapa_recintos_rrhh() -> Dict[str, str]:
    ok, payload, _ = rrhh_request("recintos", {"page": 1, "page_size": 100})
    if not ok or not isinstance(payload, dict):
        return {}
    data = payload.get("data") or []
    return {row["code"]: row.get("name") or row["code"] for row in data if isinstance(row, dict) and row.get("code")}


def listar_todos_vigentes_enriquecidos() -> dict:
    """Todos los empleados activos (pagina RRHH) con área y recinto asignado."""
    areas = _mapa_areas()
    recintos = _mapa_recintos_rrhh()
    empleados: List[dict] = []
    page = 1
    error = None
    ok_global = True

    while True:
        chunk = listar_trabajadores_vigentes(page=page, page_size=100)
        if not chunk["ok"]:
            ok_global = False
            error = chunk.get("error")
            break
        ok, payload, err = rrhh_request(
            "employees/active",
            {"page": page, "page_size": 100, "exclude_pending": "true"},
        )
        if not ok:
            ok_global = False
            error = err
            break
        data = payload.get("data") if isinstance(payload, dict) else []
        for raw in data:
            if isinstance(raw, dict):
                empleados.append(_enriquecer_desde_raw(raw, areas, recintos))
        pag = payload.get("pagination") if isinstance(payload, dict) else {}
        total_pages = pag.get("total_pages") or 1
        if page >= int(total_pages):
            break
        page += 1

    return {
        "ok": ok_global and bool(empleados),
        "empleados": empleados,
        "error": error,
        "total": len(empleados),
    }


def listar_presencia_dia(fecha: Optional[date] = None) -> dict:
    """
    Listado unificado: todos los vigentes + marcaje del día si hay token Asistencia.
    """
    dia = fecha or date.today()
    nomina = listar_todos_vigentes_enriquecidos()
    asist_cfg = asistencia_config()
    asistencia = listar_asistencia_dia(dia)
    asist_por_rut: Dict[str, dict] = {}
    if asistencia["ok"]:
        for row in asistencia["registros"]:
            key = row.get("rut_norm") or ""
            if key:
                asist_por_rut[key] = row

    filas: List[dict] = []
    for emp in nomina.get("empleados") or []:
        rut_norm = emp.get("rut_norm") or ""
        marca = asist_por_rut.get(rut_norm)
        if marca:
            estado = marca.get("estado_presencia") or "—"
            recinto_marca = marca.get("nombre_recinto") or marca.get("codigo_recinto") or "—"
            hora_entrada = marca.get("entrada_hora") or "—"
            hora_salida = marca.get("salida_hora") or "—"
        elif asist_cfg["token_configurado"] and asistencia["ok"]:
            estado = "Sin marca hoy"
            recinto_marca = "—"
            hora_entrada = "—"
            hora_salida = "—"
        else:
            estado = "—"
            recinto_marca = "—"
            hora_entrada = "—"
            hora_salida = "—"

        filas.append({
            **emp,
            "estado_contrato": emp.get("status") or "",
            "estado_presencia": estado,
            "recinto_marca": recinto_marca,
            "hora_entrada": hora_entrada,
            "hora_salida": hora_salida,
        })

    filas.sort(key=lambda x: (x.get("full_name") or "").lower())

    con_marca = sum(
        1 for f in filas
        if f.get("estado_presencia") in ("Trabajando", "Jornada cerrada")
    )
    trabajando = sum(1 for f in filas if f.get("estado_presencia") == "Trabajando")

    warnings = []
    if not asist_cfg["token_configurado"]:
        warnings.append(
            "Configure BUK_ASISTENCIA_TOKEN en .env para ver marcajes (token distinto al de RRHH; ver SAC Buk)."
        )
    elif not asistencia["ok"]:
        warnings.append(asistencia.get("error") or "No se pudo consultar asistencia del día.")

    return {
        "ok": nomina.get("ok", False),
        "filas": filas,
        "total": len(filas),
        "trabajando": trabajando,
        "con_marca": con_marca,
        "fecha": dia.strftime("%d-%m-%Y"),
        "error": nomina.get("error"),
        "warnings": warnings,
        "asistencia_ok": asistencia.get("ok", False),
        "asistencia_config": asist_cfg,
    }
