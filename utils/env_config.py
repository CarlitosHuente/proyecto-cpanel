"""
Configuración por entorno — única fuente para DB, Buk y otras integraciones.
Lee `.env` en la raíz del proyecto (no versionado). Plantilla: `.env.example`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"

# Fallback local solo si falta `.env` o variables DB incompletas.
# Sin password por defecto (usar DB_PASSWORD en .env).
_LOCAL_DB_DEFAULTS = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "huente_app",
}

_LOCAL_BUK_DEFAULTS = {
    "tenant": "huentelauquen",
    "country": "chile",
}


def load_env() -> None:
    """Carga .env (idempotente; app.py también llama dotenv al arrancar)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ENV_FILE)


def db_connection_params() -> Dict[str, Optional[str]]:
    """
    Parámetros MySQL: prioridad variables de entorno (.env / cPanel).
    Si no hay DB_HOST en entorno, usa defaults locales de desarrollo.
    """
    load_env()
    host = os.environ.get("DB_HOST")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")
    database = os.environ.get("DB_NAME")

    if host and user and database:
        return {
            "host": host,
            "user": user,
            "password": password or "",
            "database": database,
            "source": "env",
        }

    return {
        "host": _LOCAL_DB_DEFAULTS["host"],
        "user": _LOCAL_DB_DEFAULTS["user"],
        "password": _LOCAL_DB_DEFAULTS["password"],
        "database": _LOCAL_DB_DEFAULTS["database"],
        "source": "local_default",
    }


def buk_settings() -> Dict[str, str]:
    """Tenant, token y URL base Buk (sin exponer el token en respuestas API)."""
    load_env()
    tenant = (os.environ.get("BUK_TENANT") or _LOCAL_BUK_DEFAULTS["tenant"]).strip().lower()
    country = (os.environ.get("BUK_COUNTRY") or _LOCAL_BUK_DEFAULTS["country"]).strip().lower()
    token = (os.environ.get("BUK_AUTH_TOKEN") or "").strip()
    explicit_base = (os.environ.get("BUK_API_BASE") or "").strip().rstrip("/")
    if explicit_base:
        base_url = explicit_base
    else:
        base_url = f"https://{tenant}.buk.cl/api/v1/{country}"
    return {
        "tenant": tenant,
        "country": country,
        "auth_token": token,
        "base_url": base_url,
        "token_configurado": bool(token),
    }


def buk_asistencia_settings() -> Dict[str, str]:
    """API Buk Asistencia (marcajes). Token distinto al RRHH."""
    load_env()
    token = (os.environ.get("BUK_ASISTENCIA_TOKEN") or "").strip()
    base = (os.environ.get("BUK_ASISTENCIA_API_BASE") or "https://app.ctrlit.cl/ctrl/api").strip().rstrip("/")
    return {
        "auth_token": token,
        "base_url": base,
        "token_configurado": bool(token),
    }


def _env_bool(name: str, default: bool = True) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on", "si", "sí")


def imap_settings() -> Dict[str, Optional[str]]:
    """Credenciales IMAP para bandeja PDF (Arqueo). No exponer password en respuestas."""
    load_env()
    host = (os.environ.get("IMAP_HOST") or "").strip()
    port_raw = (os.environ.get("IMAP_PORT") or "993").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 993
    user = (os.environ.get("IMAP_USER") or "").strip()
    password = os.environ.get("IMAP_PASSWORD") or ""
    folder = (os.environ.get("IMAP_FOLDER") or "INBOX").strip() or "INBOX"
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "folder": folder,
        "ssl": _env_bool("IMAP_SSL", True),
        "configurado": bool(host and user and password),
    }


def mail_sync_token() -> str:
    """Token secreto para endpoint de sync por cron."""
    load_env()
    return (os.environ.get("MAIL_SYNC_TOKEN") or "").strip()
