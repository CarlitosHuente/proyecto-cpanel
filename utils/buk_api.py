"""
Cliente de lectura para la API REST de Buk (Chile).
Solo consulta; no persiste datos ni escribe en Buk.
Configuración: utils/env_config.py → .env
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

import requests

from utils.env_config import buk_settings

DEFAULT_TIMEOUT = 30
MAX_PAGE_SIZE = 100
MIN_PAGE_SIZE = 25


class BukConfigError(Exception):
    """Faltan variables de entorno para conectar con Buk."""


def configuracion_resumen() -> dict:
    """Metadatos seguros (sin token) para mostrar en UI."""
    cfg = buk_settings()
    return {
        "tenant": cfg["tenant"],
        "base_url": cfg["base_url"],
        "token_configurado": cfg["token_configurado"],
    }


def _auth_token() -> str:
    token = buk_settings()["auth_token"]
    if not token:
        raise BukConfigError(
            "Falta BUK_AUTH_TOKEN en .env (Configuración → Accesos API en Buk)."
        )
    return token


def _headers() -> dict:
    return {
        "Accept": "application/json",
        "auth_token": _auth_token(),
    }


def _request(path: str, params: Optional[dict] = None) -> Tuple[bool, Any, Optional[str]]:
    url = f"{buk_settings()['base_url'].rstrip('/')}/{path.lstrip('/')}"
    try:
        resp = requests.get(
            url,
            headers=_headers(),
            params=params or {},
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        return False, None, f"Error de red al contactar Buk: {exc}"

    if resp.status_code == 401:
        return False, None, "Token Buk inválido o sin permisos (HTTP 401)."
    if resp.status_code == 403:
        return False, None, "Acceso denegado por Buk (HTTP 403). Revise permisos del token."
    if resp.status_code == 404:
        return False, None, f"Endpoint no encontrado (HTTP 404): {url}"
    if not resp.ok:
        detalle = resp.text[:300] if resp.text else resp.reason
        return False, None, f"Error Buk HTTP {resp.status_code}: {detalle}"

    try:
        return True, resp.json(), None
    except ValueError:
        return False, None, "Respuesta de Buk no es JSON válido."


def _clamp_page_size(page_size: int) -> int:
    try:
        n = int(page_size)
    except (TypeError, ValueError):
        n = MIN_PAGE_SIZE
    return max(MIN_PAGE_SIZE, min(n, MAX_PAGE_SIZE))


def normalizar_empleado(raw: dict) -> dict:
    """Reduce el payload a campos operativos no sensibles."""
    if not isinstance(raw, dict):
        return {}

    job = raw.get("current_job") if isinstance(raw.get("current_job"), dict) else {}
    full_name = (raw.get("full_name") or "").strip()
    if not full_name:
        partes = [
            raw.get("first_name"),
            raw.get("surname"),
            raw.get("second_surname"),
        ]
        full_name = " ".join(p for p in partes if p).strip()

    rut = raw.get("rut") or raw.get("document_number") or ""
    role = job.get("role")
    if isinstance(role, dict):
        cargo = (role.get("name") or role.get("code") or "").strip()
    else:
        cargo = (role or "").strip() if role else ""

    ctrlit = (job.get("custom_attributes") or {}).get("ctrlit_recinto") or ""
    ctrlit = str(ctrlit).strip() if ctrlit and str(ctrlit) not in ("None", "sin_recinto") else ""

    return {
        "id": raw.get("id"),
        "person_id": raw.get("person_id"),
        "full_name": full_name,
        "rut": rut,
        "code_sheet": raw.get("code_sheet") or "",
        "email": raw.get("email") or "",
        "status": raw.get("status") or "",
        "active_since": raw.get("active_since") or "",
        "cargo": cargo,
        "area_id": job.get("area_id"),
        "recinto_codigo": ctrlit,
        "cost_center": job.get("cost_center") or "",
        "contract_type": job.get("contract_type") or "",
        "job_start_date": job.get("start_date") or "",
        "weekly_hours": job.get("weekly_hours"),
    }


def listar_trabajadores_vigentes(
    page: int = 1,
    page_size: int = 25,
    exclude_pending: bool = True,
) -> dict:
    cfg = configuracion_resumen()
    try:
        _auth_token()
    except BukConfigError as exc:
        return {
            "ok": False,
            "empleados": [],
            "pagination": {},
            "error": str(exc),
            "config": cfg,
        }

    try:
        page_n = max(1, int(page))
    except (TypeError, ValueError):
        page_n = 1

    size = _clamp_page_size(page_size)
    params = {
        "page": page_n,
        "page_size": size,
        "exclude_pending": "true" if exclude_pending else "false",
    }

    ok, payload, err = _request("employees/active", params=params)
    if not ok:
        return {
            "ok": False,
            "empleados": [],
            "pagination": {},
            "error": err,
            "config": cfg,
        }

    data = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(data, list):
        data = []

    pagination = payload.get("pagination") if isinstance(payload, dict) else {}
    if not isinstance(pagination, dict):
        pagination = {}

    empleados = [normalizar_empleado(row) for row in data if isinstance(row, dict)]

    return {
        "ok": True,
        "empleados": empleados,
        "pagination": pagination,
        "error": None,
        "config": cfg,
    }


def probar_conexion() -> dict:
    resultado = listar_trabajadores_vigentes(page=1, page_size=MIN_PAGE_SIZE)
    pag = resultado.get("pagination") or {}
    total_en_pagina = len(resultado.get("empleados") or [])

    return {
        "ok": resultado["ok"],
        "error": resultado.get("error"),
        "config": resultado.get("config") or configuracion_resumen(),
        "muestra_recibida": total_en_pagina,
        "pagination": pag,
        "total_en_respuesta": pag.get("count"),
        "total_pages": pag.get("total_pages"),
    }
