"""
Cliente Buk Asistencia (marcajes, recintos).
API: https://app.swaggerhub.com/apis-docs/BUKASISTENCIA/ApiAsistencia/1.0.0
Token distinto al de Buk RRHH (solicitar a SAC Buk).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import requests

from utils.env_config import buk_asistencia_settings

TZ_CHILE = ZoneInfo("America/Santiago")
DEFAULT_TIMEOUT = 45
MAX_PAGE_SIZE = 100
MAX_RANGO_DIAS = 35


def _fecha_marca_local(iso: Optional[str]) -> Optional[date]:
    """Fecha calendario Chile de un marcaje (entrada)."""
    if not iso:
        return None
    try:
        raw = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(TZ_CHILE).date()
    except (TypeError, ValueError):
        return None


class BukAsistenciaConfigError(Exception):
    pass


def _token() -> str:
    token = buk_asistencia_settings()["auth_token"]
    if not token:
        raise BukAsistenciaConfigError(
            "Falta BUK_ASISTENCIA_TOKEN en .env (token API Asistencia; solicitar a SAC Buk)."
        )
    return token


def configuracion_resumen() -> dict:
    cfg = buk_asistencia_settings()
    return {
        "base_url": cfg["base_url"],
        "token_configurado": cfg["token_configurado"],
    }


def _request(
    path: str,
    params: Optional[dict] = None,
    *,
    token_in_header: bool = True,
) -> Tuple[bool, Any, Optional[str]]:
    cfg = buk_asistencia_settings()
    url = f"{cfg['base_url'].rstrip('/')}/{path.lstrip('/')}"
    headers = {"Accept": "application/json"}
    if token_in_header:
        try:
            headers["token"] = _token()
        except BukAsistenciaConfigError as exc:
            return False, None, str(exc)

    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        return False, None, f"Error de red Buk Asistencia: {exc}"

    if resp.status_code == 403:
        return False, None, "Token Buk Asistencia inválido o sin permisos (HTTP 403)."
    if resp.status_code == 404:
        return False, None, f"Endpoint no encontrado (HTTP 404): {url}"
    if not resp.ok:
        detalle = resp.text[:300] if resp.text else resp.reason
        return False, None, f"Error Buk Asistencia HTTP {resp.status_code}: {detalle}"

    try:
        return True, resp.json(), None
    except ValueError:
        return False, None, "Respuesta Buk Asistencia no es JSON válido."


def _fecha_param(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _iso_a_hora_cl(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        raw = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(TZ_CHILE)
        return local.strftime("%H:%M")
    except (TypeError, ValueError):
        return str(iso)[:16]


def normalizar_rut(rut: Optional[str]) -> str:
    if not rut:
        return ""
    return re.sub(r"[^0-9kK]", "", str(rut)).upper()


def normalizar_fila_asistencia(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    entrada = raw.get("entrada")
    salida = raw.get("salida")
    if entrada and not salida:
        estado = "Trabajando"
    elif entrada and salida:
        estado = "Jornada cerrada"
    else:
        estado = "Sin entrada"
    nombre = " ".join(
        p for p in [
            raw.get("nombre"),
            raw.get("apellido_paterno"),
            raw.get("apellido_materno"),
        ] if p
    ).strip()
    return {
        "rut": raw.get("rut_trabajador") or "",
        "rut_norm": normalizar_rut(raw.get("rut_trabajador")),
        "nombre": nombre,
        "codigo_recinto": raw.get("codigo_recinto") or "",
        "nombre_recinto": raw.get("nombre_recinto") or "",
        "id_recinto": raw.get("id_recinto"),
        "entrada_iso": entrada or "",
        "salida_iso": salida or "",
        "entrada_hora": _iso_a_hora_cl(entrada),
        "salida_hora": _iso_a_hora_cl(salida),
        "estado_presencia": estado,
        "area": raw.get("area") or "",
        "especialidad": raw.get("especialidad") or "",
    }


def _paginar_todo(path: str, params_base: dict) -> Tuple[bool, List[dict], Optional[str]]:
    filas: List[dict] = []
    page = 1
    while True:
        params = dict(params_base)
        params["page"] = page
        params.setdefault("page_size", MAX_PAGE_SIZE)
        ok, payload, err = _request(path, params)
        if not ok:
            return False, filas, err
        chunk = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(chunk, list):
            chunk = []
        filas.extend(chunk)
        pag = payload.get("pagination") if isinstance(payload, dict) else {}
        total_pages = (pag or {}).get("totalPages") or (pag or {}).get("total_pages") or 1
        if page >= int(total_pages) or not chunk:
            break
        page += 1
    return True, filas, None


def probar_conexion() -> dict:
    """Ping a asistencia del día (1 página)."""
    cfg = configuracion_resumen()
    try:
        _token()
    except BukAsistenciaConfigError as exc:
        return {"ok": False, "error": str(exc), "config": cfg, "muestra": 0}

    ok, payload, err = _request(
        "v2/asistencia-empresa",
        {"desde": _fecha_param(date.today()), "hasta": _fecha_param(date.today()), "page": 1, "page_size": 5},
    )
    if not ok:
        return {"ok": False, "error": err, "config": cfg, "muestra": 0}

    chunk = payload.get("data") if isinstance(payload, dict) else []
    n = len(chunk) if isinstance(chunk, list) else 0
    pag = payload.get("pagination") if isinstance(payload, dict) else {}
    return {
        "ok": True,
        "error": None,
        "config": cfg,
        "muestra": n,
        "pagination": pag,
    }


def listar_asistencia_dia(fecha: Optional[date] = None) -> dict:
    """GET /v2/asistencia-empresa para un día (desde=hasta)."""
    cfg = configuracion_resumen()
    dia = fecha or date.today()
    fp = _fecha_param(dia)
    try:
        _token()
    except BukAsistenciaConfigError as exc:
        return {
            "ok": False,
            "registros": [],
            "error": str(exc),
            "config": cfg,
            "fecha": fp,
        }

    ok, raw_rows, err = _paginar_todo(
        "v2/asistencia-empresa",
        {"desde": fp, "hasta": fp},
    )
    if not ok:
        return {
            "ok": False,
            "registros": [],
            "error": err,
            "config": cfg,
            "fecha": fp,
        }

    registros = [normalizar_fila_asistencia(r) for r in raw_rows if isinstance(r, dict)]
    return {
        "ok": True,
        "registros": registros,
        "error": None,
        "config": cfg,
        "fecha": fp,
    }


def mapa_asistencia_por_rut(fecha: Optional[date] = None) -> dict:
    """Dict rut_norm → último registro de asistencia del día."""
    resultado = listar_asistencia_dia(fecha)
    out: Dict[str, dict] = {}
    if not resultado["ok"]:
        return out
    for row in resultado["registros"]:
        key = row.get("rut_norm") or ""
        if key:
            out[key] = row
    return out


def listar_asistencia_rango(fecha_inicio: date, fecha_fin: date) -> dict:
    """GET /v2/asistencia-empresa para un rango (particionado si supera 35 días)."""
    cfg = configuracion_resumen()
    if fecha_fin < fecha_inicio:
        return {
            "ok": False,
            "registros": [],
            "error": "Rango de fechas inválido.",
            "config": cfg,
            "desde": _fecha_param(fecha_inicio),
            "hasta": _fecha_param(fecha_fin),
        }

    try:
        _token()
    except BukAsistenciaConfigError as exc:
        return {
            "ok": False,
            "registros": [],
            "error": str(exc),
            "config": cfg,
            "desde": _fecha_param(fecha_inicio),
            "hasta": _fecha_param(fecha_fin),
        }

    raw_rows: List[dict] = []
    tramos = []
    cursor = fecha_inicio
    while cursor <= fecha_fin:
        tramo_fin = min(fecha_fin, cursor + timedelta(days=MAX_RANGO_DIAS - 1))
        tramos.append((cursor, tramo_fin))
        ok, chunk, err = _paginar_todo(
            "v2/asistencia-empresa",
            {"desde": _fecha_param(cursor), "hasta": _fecha_param(tramo_fin)},
        )
        if not ok:
            return {
                "ok": False,
                "registros": [],
                "error": err,
                "config": cfg,
                "desde": _fecha_param(fecha_inicio),
                "hasta": _fecha_param(fecha_fin),
            }
        raw_rows.extend(chunk)
        cursor = tramo_fin + timedelta(days=1)

    registros = [normalizar_fila_asistencia(r) for r in raw_rows if isinstance(r, dict)]
    return {
        "ok": True,
        "registros": registros,
        "error": None,
        "config": cfg,
        "desde": _fecha_param(fecha_inicio),
        "hasta": _fecha_param(fecha_fin),
        "tramos_api": len(tramos),
    }


def dias_marcados_por_rut(registros: List[dict]) -> Dict[str, Set[date]]:
    """RUT normalizado → fechas con al menos una entrada."""
    out: Dict[str, Set[date]] = {}
    for row in registros:
        rut = row.get("rut_norm") or ""
        if not rut or not row.get("entrada_iso"):
            continue
        dia = _fecha_marca_local(row.get("entrada_iso"))
        if not dia:
            continue
        out.setdefault(rut, set()).add(dia)
    return out


def _paginar_turnos(desde: date, hasta: date) -> Tuple[bool, List[dict], Optional[str]]:
    """GET /getAsignacionTurnos — token en query; respuesta puede ser lista directa."""
    token = _token()
    filas: List[dict] = []
    page = 1
    page_size = 500
    while True:
        params = {
            "token": token,
            "desde": _fecha_param(desde),
            "hasta": _fecha_param(hasta),
            "page": page,
            "page_size": page_size,
        }
        ok, payload, err = _request("getAsignacionTurnos", params, token_in_header=False)
        if not ok:
            return False, filas, err
        if isinstance(payload, list):
            chunk = payload
        elif isinstance(payload, dict):
            chunk = payload.get("data") or []
        else:
            chunk = []
        if not chunk:
            break
        filas.extend(chunk)
        if len(chunk) < page_size:
            break
        page += 1
    return True, filas, None


def normalizar_recinto(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    obra_id = raw.get("obraId") or raw.get("obra_id") or raw.get("id")
    return {
        "obra_id": str(obra_id) if obra_id is not None else "",
        "nombre": (raw.get("nombre") or raw.get("nombreRecinto") or "").strip(),
        "comuna": (raw.get("comuna") or "").strip(),
    }


def listar_recintos() -> dict:
    cfg = configuracion_resumen()
    try:
        _token()
    except BukAsistenciaConfigError as exc:
        return {"ok": False, "recintos": [], "error": str(exc), "config": cfg}

    ok, raw_rows, err = _paginar_todo("informacionRecinto", {})
    if not ok:
        return {"ok": False, "recintos": [], "error": err, "config": cfg}

    recintos = [normalizar_recinto(r) for r in raw_rows if isinstance(r, dict)]
    recintos = [r for r in recintos if r.get("obra_id")]
    recintos.sort(key=lambda x: (x.get("nombre") or "").lower())
    return {"ok": True, "recintos": recintos, "error": None, "config": cfg}


def normalizar_turno(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    dia_raw = (raw.get("diaTurno") or raw.get("dia_turno") or "").strip()
    dia: Optional[date] = None
    if dia_raw:
        try:
            dia = datetime.strptime(dia_raw, "%d-%m-%Y").date()
        except ValueError:
            pass
    id_rec = raw.get("idRecinto") or raw.get("id_recinto")
    return {
        "rut_norm": normalizar_rut(raw.get("dni") or raw.get("DNI")),
        "fecha": dia,
        "horario_turno": (raw.get("horarioTurno") or raw.get("horario_turno") or "").strip(),
        "colacion_turno": (raw.get("colacionTurno") or raw.get("colacion_turno") or "").strip(),
        "nombre_recinto": (raw.get("nombreRecinto") or raw.get("nombre_recinto") or "").strip(),
        "codigo_recinto": (raw.get("codigoRecinto") or raw.get("codigo_recinto") or "").strip(),
        "id_recinto": int(id_rec) if id_rec is not None else None,
        "licencia": bool(raw.get("licencia")),
        "permiso": bool(raw.get("permiso")),
        "vacaciones": bool(raw.get("vacaciones")),
        "nombre_turno": (raw.get("nombreTurno") or raw.get("nombre_turno") or "").strip(),
        "nombre_trabajador": (raw.get("nombreTrabajador") or raw.get("nombre_trabajador") or "").strip(),
    }


def listar_turnos_rango(fecha_inicio: date, fecha_fin: date) -> dict:
    cfg = configuracion_resumen()
    if fecha_fin < fecha_inicio:
        return {"ok": False, "turnos": [], "error": "Rango inválido.", "config": cfg}
    try:
        _token()
    except BukAsistenciaConfigError as exc:
        return {"ok": False, "turnos": [], "error": str(exc), "config": cfg}

    all_turnos: List[dict] = []
    cursor = fecha_inicio
    while cursor <= fecha_fin:
        tramo_fin = min(fecha_fin, cursor + timedelta(days=MAX_RANGO_DIAS - 1))
        ok, chunk, err = _paginar_turnos(cursor, tramo_fin)
        if not ok:
            return {"ok": False, "turnos": [], "error": err, "config": cfg}
        all_turnos.extend(chunk)
        cursor = tramo_fin + timedelta(days=1)

    turnos = [normalizar_turno(t) for t in all_turnos if isinstance(t, dict)]
    return {
        "ok": True,
        "turnos": turnos,
        "error": None,
        "config": cfg,
        "desde": _fecha_param(fecha_inicio),
        "hasta": _fecha_param(fecha_fin),
    }


def normalizar_registro_marcaje(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    dni = raw.get("DNI") or raw.get("dni") or ""
    try:
        ano = int(raw.get("ano"))
        mes = int(raw.get("mes"))
        dia = int(raw.get("dia"))
        hora = int(raw.get("hora", 0))
        minutos = int(raw.get("minutos", 0))
        segundos = int(raw.get("segundos", 0))
    except (TypeError, ValueError):
        return {}
    marca_dt = datetime(ano, mes, dia, hora, minutos, segundos, tzinfo=TZ_CHILE)
    return {
        "rut_norm": normalizar_rut(dni),
        "fecha": date(ano, mes, dia),
        "sentido": (raw.get("sentido") or "").strip().lower(),
        "marca_dt": marca_dt,
        "obra_id": raw.get("obra_id") or raw.get("obraId"),
    }


def listar_registros_recinto(
    obra_id: str,
    fecha_inicio: date,
    fecha_fin: date,
    *,
    dni: Optional[str] = None,
) -> dict:
    cfg = configuracion_resumen()
    if fecha_fin < fecha_inicio:
        return {"ok": False, "registros": [], "error": "Rango inválido.", "config": cfg}
    try:
        _token()
    except BukAsistenciaConfigError as exc:
        return {"ok": False, "registros": [], "error": str(exc), "config": cfg}

    raw_rows: List[dict] = []
    cursor = fecha_inicio
    dni_param = normalizar_rut(dni) if dni else None
    while cursor <= fecha_fin:
        tramo_fin = min(fecha_fin, cursor + timedelta(days=MAX_RANGO_DIAS - 1))
        params = {
            "obra_id": obra_id,
            "from": _fecha_param(cursor),
            "to": _fecha_param(tramo_fin),
        }
        if dni_param:
            params["dni_colaborador"] = dni_param
        ok, chunk, err = _paginar_todo("obtenerRegistroAsistencia", params)
        if not ok:
            return {"ok": False, "registros": [], "error": err, "config": cfg}
        raw_rows.extend(chunk)
        cursor = tramo_fin + timedelta(days=1)

    registros = [normalizar_registro_marcaje(r) for r in raw_rows if isinstance(r, dict)]
    registros = [r for r in registros if r]
    return {
        "ok": True,
        "registros": registros,
        "error": None,
        "config": cfg,
        "desde": _fecha_param(fecha_inicio),
        "hasta": _fecha_param(fecha_fin),
    }
