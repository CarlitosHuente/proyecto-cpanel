"""Subida del PDF final FxR a Drive vía Apps Script (mismo webhook del mayor)."""
from __future__ import annotations

import base64
import json

import requests

URL_WEBHOOK_SCRIPT = (
    "https://script.google.com/macros/s/"
    "AKfycbxUK2SQ_fDaX1wEcTDLfnefcZPCZDp3A5rrqd2gZ6KBHV7qbBuysYTXltBBLXraNGj7/exec"
)


def subir_pdf_rendicion(pdf_bytes: bytes, nombre: str) -> tuple[bool, str, str | None]:
    """
    Sube PDF a respaldoimagenes (accion imagen).
    Retorna (ok, mensaje_o_error, url_opcional).
    """
    payload = {
        "accion": "imagen",
        "nombre": nombre,
        "mime": "application/pdf",
        "base64": base64.b64encode(pdf_bytes).decode("ascii"),
    }
    body = json.dumps(payload, separators=(",", ":"))
    try:
        resp = requests.post(
            URL_WEBHOOK_SCRIPT,
            data=body.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=180,
        )
        texto = (resp.text or "").strip()
        if texto.upper().startswith("OK"):
            url = texto[3:].lstrip(":").strip() or None
            return True, texto, url
        return False, texto or f"HTTP {resp.status_code}", None
    except Exception as exc:
        return False, str(exc), None
