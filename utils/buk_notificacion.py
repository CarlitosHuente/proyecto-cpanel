"""
Aviso al colaborador tras subir documento firmable a Buk.

1. Intenta endpoints públicos de notificación (campana Buk vía API).
2. Si no hay API, opcionalmente envía correo SMTP (Huente) como respaldo.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

from utils.env_config import buk_settings, load_env
from utils.mail_smtp import enviar_correo, smtp_configurado

DEFAULT_TIMEOUT = 30

# Rutas probadas en tenant huentelauquen (jun 2026); todas devolvieron 404 salvo futuras de SAC.
_NOTIFY_POST_PATHS = (
    "employees/{employee_id}/docs/{file_id}/notify",
    "employees/{employee_id}/docs/{file_id}/notify_signers",
    "employees/{employee_id}/employee_files/{file_id}/notify",
    "employee_files/{file_id}/notify",
    "employee_files/{file_id}/notify_signers",
    "documents/{file_id}/notify",
)


def _env_bool(name: str, default: bool = True) -> bool:
    load_env()
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "si", "sí", "on")


def iniciar_flujo_automatico_habilitado() -> bool:
    return _env_bool("BUK_INICIAR_FLUJO_AUTOMATICO", True)


def notificar_tras_subida_habilitado() -> bool:
    return _env_bool("BUK_NOTIFICAR_TRAS_SUBIDA", True)


def url_portal_buk() -> str:
    load_env()
    tenant = buk_settings()["tenant"]
    explicit = (os.environ.get("BUK_PORTAL_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    return f"https://{tenant}.buk.cl"


def _smtp_configurado() -> bool:
    return smtp_configurado()


def notificar_firmantes_documento(
    employee_id: int,
    file_id: int,
    *,
    empleado: Optional[dict] = None,
) -> dict:
    """
    Dispara aviso de firma pendiente tras subir el PDF.
    Devuelve estado explícito para UI / logs.
    """
    cfg = buk_settings()
    token = cfg.get("auth_token")
    if not token:
        return {"ok": False, "canal": None, "error": "Falta BUK_AUTH_TOKEN.", "detalle": None}

    base = cfg["base_url"].rstrip("/")
    headers = {
        "auth_token": token,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = {"employee_id": int(employee_id), "employee_file_id": int(file_id), "file_id": int(file_id)}

    intentos: List[Dict[str, Any]] = []
    for tpl in _NOTIFY_POST_PATHS:
        path = tpl.format(employee_id=int(employee_id), file_id=int(file_id))
        url = f"{base}/{path}"
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            intentos.append({"path": path, "status": None, "error": str(exc)})
            continue
        intentos.append({"path": path, "status": resp.status_code})
        if resp.status_code in (200, 201, 202, 204):
            return {
                "ok": True,
                "canal": "buk_api",
                "error": None,
                "detalle": {"endpoint": path, "http_status": resp.status_code},
                "intentos": intentos,
            }

    if empleado and _smtp_configurado():
        correo = enviar_aviso_firma_correo(
            empleado,
            filename=(empleado.get("_ultimo_filename") or "documento"),
            carpeta=(empleado.get("_ultima_carpeta") or "Capacitacion"),
            file_id=int(file_id),
        )
        if correo.get("ok"):
            return {
                "ok": True,
                "canal": "correo_huente",
                "error": None,
                "detalle": correo,
                "intentos": intentos,
            }
        return {
            "ok": False,
            "canal": "correo_huente",
            "error": correo.get("error") or "No se pudo enviar correo.",
            "detalle": correo,
            "intentos": intentos,
        }

    return {
        "ok": False,
        "canal": None,
        "error": (
            "Buk no expone API de notificación (campana) en este tenant. "
            "Use Notificar en Documentos del colaborador en Buk, o configure SMTP_*/IMAP_* en .env."
        ),
        "detalle": {
            "portal_buk": url_portal_buk(),
            "flujo_automatico_subida": iniciar_flujo_automatico_habilitado(),
        },
        "intentos": intentos,
    }


def enviar_aviso_firma_correo(
    empleado: dict,
    *,
    filename: str,
    carpeta: str,
    file_id: int,
) -> dict:
    """Correo de respaldo cuando la API Buk no notifica."""
    load_env()
    destino = (empleado.get("email") or empleado.get("personal_email") or "").strip()
    if not destino:
        return {"ok": False, "error": "El colaborador no tiene email en Buk.", "destino": None}

    nombre = (empleado.get("full_name") or "Colaborador").strip()
    portal = url_portal_buk()
    asunto = (os.environ.get("BUK_AVISO_FIRMA_ASUNTO") or "Documento pendiente de firma — Huente / Buk").strip()
    cuerpo = (
        f"Hola {nombre},\n\n"
        f"Se cargó en Buk un documento que requiere tu firma electrónica:\n"
        f"  • Archivo: {filename}\n"
        f"  • Carpeta: {carpeta}\n"
        f"  • ID documento: {file_id}\n\n"
        f"Ingresa a {portal} con tu usuario Buk y revisa "
        f"«Mis firmas pendientes» o la carpeta {carpeta} en tu ficha.\n\n"
        f"— Huente CPanel (aviso automático)\n"
    )

    envio = enviar_correo(destino, asunto, cuerpo)
    return {
        "ok": bool(envio.get("ok")),
        "error": envio.get("error"),
        "destino": destino,
        "asunto": asunto,
        "from_addr": envio.get("from_addr"),
        "fuente": envio.get("fuente"),
    }
