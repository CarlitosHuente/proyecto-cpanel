"""
Subida de documentos PDF a la ficha del colaborador en Buk (Gestión Documental).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional, Tuple

import requests

from utils.buk_api import _request, normalizar_empleado
from utils.buk_notificacion import (
    iniciar_flujo_automatico_habilitado,
    notificar_firmantes_documento,
    notificar_tras_subida_habilitado,
)
from utils.env_config import buk_settings, load_env

DEFAULT_TIMEOUT = 60
CARPETA_DEFAULT = "Capacitacion"


def normalizar_rut_busqueda(rut: str) -> str:
    return re.sub(r"[^0-9kK]", "", (rut or "").strip()).upper()


def carpeta_encuestas() -> str:
    load_env()
    return (os.environ.get("BUK_ENCUESTA_CARPETA") or CARPETA_DEFAULT).strip() or CARPETA_DEFAULT


def buscar_empleado_vigente_por_rut(rut: str) -> dict:
    """Busca colaborador activo por RUT (sin validación estricta de dígito verificador)."""
    rut_limpio = normalizar_rut_busqueda(rut)
    if len(rut_limpio) < 7:
        return {"ok": False, "empleado": None, "error": "RUT demasiado corto."}

    ok, payload, err = _request(
        "employees/active",
        {
            "document_number": rut_limpio,
            "page": 1,
            "page_size": 25,
            "exclude_pending": "true",
        },
    )
    if not ok:
        return {"ok": False, "empleado": None, "error": err or "Error al consultar Buk."}

    data = payload.get("data") if isinstance(payload, dict) else []
    if not data:
        ok2, payload2, err2 = _request(
            "employees/active",
            {"page": 1, "page_size": 100, "exclude_pending": "true"},
        )
        if ok2 and isinstance(payload2, dict):
            for row in payload2.get("data") or []:
                if not isinstance(row, dict):
                    continue
                nr = normalizar_rut_busqueda(row.get("rut") or row.get("document_number"))
                if nr == rut_limpio:
                    emp = normalizar_empleado(row)
                    emp["id"] = row.get("id")
                    emp["full_name"] = row.get("full_name") or emp.get("full_name")
                    emp["rut"] = row.get("rut") or emp.get("rut")
                    return {"ok": True, "empleado": emp, "error": None}
        return {"ok": False, "empleado": None, "error": "No se encontró colaborador vigente con ese RUT."}

    raw = data[0]
    emp = normalizar_empleado(raw)
    emp["id"] = raw.get("id")
    emp["full_name"] = raw.get("full_name") or emp.get("full_name")
    emp["rut"] = raw.get("rut") or emp.get("rut")
    return {"ok": True, "empleado": emp, "error": None}


def subir_pdf_con_firma_empleado(
    employee_id: int,
    pdf_bytes: bytes,
    filename: str,
    *,
    carpeta: Optional[str] = None,
    visible: bool = True,
    notificar: Optional[bool] = None,
    empleado: Optional[dict] = None,
) -> dict:
    """
    POST /employees/{id}/docs — multipart file + firma colaborador.
    Intenta carpeta Capacitacion; Buk crea la carpeta si no existe.
    Tras subir, intenta notificar al firmante (API Buk y/o correo SMTP).
    """
    cfg = buk_settings()
    token = cfg.get("auth_token")
    if not token:
        return {"ok": False, "error": "Falta BUK_AUTH_TOKEN en .env."}

    carpeta_usar = (carpeta or carpeta_encuestas()).strip()
    url = f"{cfg['base_url'].rstrip('/')}/employees/{int(employee_id)}/docs"
    headers = {"auth_token": token}

    data = {
        "visible": "true" if visible else "false",
        "signable_by_employee": "true",
        "signatures": json.dumps(
            [{"signature_type": "employee_signature", "position": 1}],
            ensure_ascii=False,
        ),
    }
    if iniciar_flujo_automatico_habilitado():
        # Equivalente UI «Iniciar flujo automático» al emitir documentos en Buk.
        data["start_automatic_flow"] = "true"
    if carpeta_usar:
        data["folder"] = carpeta_usar

    files = {"file": (filename, pdf_bytes, "application/pdf")}

    try:
        resp = requests.post(
            url,
            headers=headers,
            data=data,
            files=files,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Error de red al subir documento: {exc}"}

    if resp.status_code not in (200, 201):
        detalle = resp.text[:400] if resp.text else resp.reason
        return {"ok": False, "error": f"Error Buk HTTP {resp.status_code}: {detalle}"}

    try:
        body = resp.json()
    except ValueError:
        body = {}

    archivo = body.get("employee_file") if isinstance(body, dict) else {}
    firmas = (archivo or {}).get("signatures") or []
    file_id = (archivo or {}).get("id")
    requiere_firma = any(
        (s or {}).get("signature_type") == "employee_signature" for s in firmas if isinstance(s, dict)
    )

    resultado = {
        "ok": True,
        "error": None,
        "employee_id": body.get("employee_id") if isinstance(body, dict) else employee_id,
        "file_id": file_id,
        "filename": filename,
        "carpeta": carpeta_usar or "DOCUMENTOS (raíz)",
        "employee_folder_id": (archivo or {}).get("employee_folder_id"),
        "requiere_firma_empleado": requiere_firma,
        "flujo_automatico_solicitado": iniciar_flujo_automatico_habilitado(),
        "notificacion": None,
        "raw": body,
    }

    debe_notificar = notificar if notificar is not None else notificar_tras_subida_habilitado()
    if debe_notificar and requiere_firma and file_id:
        emp_ctx = dict(empleado or {})
        emp_ctx["_ultimo_filename"] = filename
        emp_ctx["_ultima_carpeta"] = resultado["carpeta"]
        resultado["notificacion"] = notificar_firmantes_documento(
            int(employee_id),
            int(file_id),
            empleado=emp_ctx,
        )

    return resultado
