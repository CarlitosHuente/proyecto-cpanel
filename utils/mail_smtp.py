"""
Envío SMTP compartido (Alertas Buk, avisos firma, futuros reportes).

Usa smtp_settings(): SMTP_* o fallback a la casilla IMAP de Arqueo.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import List, Optional, Sequence, Union

from utils.env_config import smtp_settings

DEFAULT_TIMEOUT = 30


def smtp_configurado() -> bool:
    return bool(smtp_settings().get("configurado"))


def _normalizar_destinos(to: Union[str, Sequence[str], None]) -> List[str]:
    if to is None:
        return []
    if isinstance(to, str):
        raw = to.replace(";", ",")
        partes = [p.strip() for p in raw.split(",")]
    else:
        partes = []
        for item in to:
            if not item:
                continue
            partes.extend(_normalizar_destinos(str(item)))
    out: List[str] = []
    seen = set()
    for p in partes:
        if not p or "@" not in p:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _from_header(cfg: dict) -> str:
    addr = (cfg.get("from_addr") or "").strip()
    name = (cfg.get("from_name") or "").strip()
    if name and addr:
        return formataddr((name, addr))
    return addr


def enviar_correo(
    to: Union[str, Sequence[str]],
    subject: str,
    body_text: str,
    *,
    html: Optional[str] = None,
    bcc: Optional[Union[str, Sequence[str]]] = None,
) -> dict:
    """
    Envía un correo de texto (y HTML opcional).
    Devuelve {"ok": bool, "error": str|None, "destinos": list, "from_addr": str|None, "fuente": str}.
    """
    cfg = smtp_settings()
    destinos = _normalizar_destinos(to)
    destinos_bcc = _normalizar_destinos(bcc)
    from_addr = (cfg.get("from_addr") or "").strip()
    from_header = _from_header(cfg)

    if not destinos and not destinos_bcc:
        return {
            "ok": False,
            "error": "No hay destinatarios válidos.",
            "destinos": [],
            "from_addr": from_addr,
            "fuente": cfg.get("fuente"),
        }
    if not cfg.get("configurado"):
        return {
            "ok": False,
            "error": (
                "Correo de salida no configurado. "
                "Configure IMAP_* (casilla Arqueo) o SMTP_* en .env / cPanel."
            ),
            "destinos": destinos or destinos_bcc,
            "from_addr": from_addr,
            "fuente": cfg.get("fuente"),
        }

    host = cfg["host"]
    port = int(cfg["port"] or 587)
    user = (cfg.get("user") or "").strip()
    password = cfg.get("password") or ""
    use_tls = bool(cfg.get("use_tls"))
    use_ssl = bool(cfg.get("use_ssl"))

    msg = EmailMessage()
    msg["Subject"] = (subject or "").strip() or "(sin asunto)"
    msg["From"] = from_header
    if destinos:
        msg["To"] = ", ".join(destinos)
    if destinos_bcc:
        msg["Bcc"] = ", ".join(destinos_bcc)
    msg.set_content(body_text or "")
    if html:
        msg.add_alternative(html, subtype="html")

    recipients = list(dict.fromkeys(destinos + destinos_bcc))

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=DEFAULT_TIMEOUT) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg, from_addr=from_addr, to_addrs=recipients)
        else:
            with smtplib.SMTP(host, port, timeout=DEFAULT_TIMEOUT) as smtp:
                if use_tls:
                    smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg, from_addr=from_addr, to_addrs=recipients)
    except smtplib.SMTPException as exc:
        return {
            "ok": False,
            "error": f"Error SMTP: {exc}",
            "destinos": recipients,
            "from_addr": from_addr,
            "fuente": cfg.get("fuente"),
        }
    except OSError as exc:
        return {
            "ok": False,
            "error": f"Error de red SMTP: {exc}",
            "destinos": recipients,
            "from_addr": from_addr,
            "fuente": cfg.get("fuente"),
        }

    return {
        "ok": True,
        "error": None,
        "destinos": recipients,
        "from_addr": from_addr,
        "from_name": cfg.get("from_name"),
        "fuente": cfg.get("fuente"),
    }
