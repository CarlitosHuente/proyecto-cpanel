"""
Destinatarios y programación de notificaciones Huente (Config → Notificaciones).
Persistencia: data/notificaciones_config.json
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from utils.roles_config import DATA_DIR

NOTIF_FILE = os.path.join(DATA_DIR, "notificaciones_config.json")
TZ_CL = ZoneInfo("America/Santiago")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# weekday Python: Lun=0 … Dom=6
DIAS_SEMANA = (
    (0, "Lun"),
    (1, "Mar"),
    (2, "Mié"),
    (3, "Jue"),
    (4, "Vie"),
    (5, "Sáb"),
    (6, "Dom"),
)

SECCIONES = {
    "buk_alertas": {
        "label": "Alertas Buk",
        "descripcion": "Resumen de alertas de asistencia/turnos enviado desde Buk → Alertas.",
    },
}


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _default_auto() -> dict:
    return {
        "activo": False,
        "dias": [0, 1, 2, 3, 4],  # Lun–Vie
        "hora": "08:00",
        "ultimo_envio": None,
    }


def _default() -> dict:
    return {"buk_alertas": {"emails": [], "auto": _default_auto()}}


def _parse_hora(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "08:00"
    try:
        dt = datetime.strptime(s[:5], "%H:%M")
        return dt.strftime("%H:%M")
    except ValueError:
        return "08:00"


def _normalizar_auto(block: Optional[dict]) -> dict:
    base = _default_auto()
    if not isinstance(block, dict):
        return base
    dias_raw = block.get("dias")
    dias: List[int] = []
    if isinstance(dias_raw, list):
        for d in dias_raw:
            try:
                n = int(d)
            except (TypeError, ValueError):
                continue
            if 0 <= n <= 6 and n not in dias:
                dias.append(n)
    dias.sort()
    if not dias:
        dias = list(base["dias"])
    activo = block.get("activo")
    if isinstance(activo, str):
        activo = activo.strip().lower() in ("1", "true", "yes", "si", "sí", "on")
    return {
        "activo": bool(activo),
        "dias": dias,
        "hora": _parse_hora(str(block.get("hora") or base["hora"])),
        "ultimo_envio": (str(block.get("ultimo_envio")).strip()[:10] or None)
        if block.get("ultimo_envio")
        else None,
    }


def _normalizar_bloque(block) -> dict:
    if not isinstance(block, dict):
        return {"emails": [], "auto": _default_auto()}
    return {
        "emails": _limpiar_emails(block.get("emails") or []),
        "auto": _normalizar_auto(block.get("auto") if isinstance(block.get("auto"), dict) else None),
    }


def leer() -> dict:
    _ensure_data_dir()
    if not os.path.isfile(NOTIF_FILE):
        return _default()
    try:
        with open(NOTIF_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default()
        out = _default()
        for key in out:
            if key in data:
                out[key] = _normalizar_bloque(data[key])
        return out
    except (OSError, json.JSONDecodeError):
        return _default()


def _limpiar_emails(raw) -> List[str]:
    if isinstance(raw, str):
        partes = re.split(r"[\s,;]+", raw)
    elif isinstance(raw, list):
        partes = []
        for item in raw:
            if isinstance(item, str):
                partes.extend(re.split(r"[\s,;]+", item))
    else:
        return []
    out: List[str] = []
    seen = set()
    for p in partes:
        email = (p or "").strip()
        if not email or "@" not in email:
            continue
        if not _EMAIL_RE.match(email):
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(email)
    return out


def emails_seccion(seccion: str) -> List[str]:
    data = leer()
    block = data.get(seccion) or {}
    if isinstance(block, dict):
        return list(block.get("emails") or [])
    return []


def auto_seccion(seccion: str) -> dict:
    data = leer()
    block = data.get(seccion) or {}
    if isinstance(block, dict):
        return _normalizar_auto(block.get("auto") if isinstance(block.get("auto"), dict) else None)
    return _default_auto()


def guardar_seccion(
    seccion: str,
    emails_raw,
    *,
    auto_activo: bool = False,
    auto_dias=None,
    auto_hora: str = "08:00",
) -> Tuple[bool, str, dict]:
    if seccion not in SECCIONES:
        return False, f"Sección desconocida: {seccion}", {}
    emails = _limpiar_emails(emails_raw)
    prev = leer().get(seccion) or {}
    prev_auto = _normalizar_auto(prev.get("auto") if isinstance(prev, dict) else None)
    auto = {
        "activo": bool(auto_activo),
        "dias": [],
        "hora": _parse_hora(auto_hora),
        "ultimo_envio": prev_auto.get("ultimo_envio"),
    }
    if isinstance(auto_dias, (list, tuple)):
        for d in auto_dias:
            try:
                n = int(d)
            except (TypeError, ValueError):
                continue
            if 0 <= n <= 6 and n not in auto["dias"]:
                auto["dias"].append(n)
        auto["dias"].sort()
    if not auto["dias"]:
        auto["dias"] = [0, 1, 2, 3, 4]

    data = leer()
    data[seccion] = {"emails": emails, "auto": auto}
    _ensure_data_dir()
    try:
        with open(NOTIF_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True, "Guardado.", data[seccion]
    except OSError as exc:
        return False, f"No se pudo guardar: {exc}", {}


def marcar_ultimo_envio(seccion: str, fecha_iso: Optional[str] = None) -> None:
    data = leer()
    block = data.get(seccion)
    if not isinstance(block, dict):
        return
    auto = _normalizar_auto(block.get("auto") if isinstance(block.get("auto"), dict) else None)
    auto["ultimo_envio"] = fecha_iso or datetime.now(TZ_CL).date().isoformat()
    block["auto"] = auto
    data[seccion] = block
    try:
        with open(NOTIF_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def ahora_santiago() -> datetime:
    return datetime.now(TZ_CL)


def debe_enviar_auto(seccion: str, *, ahora: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    True si corresponde enviar ahora (activo, día, hora ya pasó hoy, aún no enviado hoy).
    Pensado para cron frecuente (p. ej. cada 15 min).
    """
    auto = auto_seccion(seccion)
    if not auto.get("activo"):
        return False, "automático desactivado"
    if not emails_seccion(seccion):
        return False, "sin destinatarios"

    now = ahora or ahora_santiago()
    if now.weekday() not in (auto.get("dias") or []):
        return False, "día no programado"

    hoy = now.date().isoformat()
    if auto.get("ultimo_envio") == hoy:
        return False, "ya enviado hoy"

    hora = _parse_hora(str(auto.get("hora") or "08:00"))
    try:
        hh, mm = map(int, hora.split(":"))
    except ValueError:
        hh, mm = 8, 0
    if (now.hour, now.minute) < (hh, mm):
        return False, "aún no es la hora"

    return True, "ok"


def emails_texto_para_form(seccion: str) -> str:
    return "\n".join(emails_seccion(seccion))


def etiqueta_dias(dias: List[int]) -> str:
    mapa = dict(DIAS_SEMANA)
    return ", ".join(mapa[d] for d in sorted(dias) if d in mapa) or "—"
