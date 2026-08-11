"""Prueba local: subir imagen/archivo a Drive vía Apps Script (subcarpeta respaldoimagenes).

No toca Contabilidad ni el flujo del mayor.xlsx.
"""
from __future__ import annotations

import base64
import json
import mimetypes

import requests
from flask import Blueprint, flash, render_template, request
from werkzeug.utils import secure_filename

from utils.auth import login_requerido, permiso_modulo

drive_prueba_bp = Blueprint("drive_prueba", __name__, url_prefix="/drive-prueba")

# Misma Web App que Contab usa para el mayor (doPost dual tras actualizar el script).
URL_WEBHOOK_SCRIPT = (
    "https://script.google.com/macros/s/"
    "AKfycbxUK2SQ_fDaX1wEcTDLfnefcZPCZDp3A5rrqd2gZ6KBHV7qbBuysYTXltBBLXraNGj7/exec"
)

MAX_BYTES = 8 * 1024 * 1024  # límite práctico para Web App Apps Script


@drive_prueba_bp.route("/", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("utilidades")
def index():
    resultado = None
    if request.method == "POST":
        archivo = request.files.get("archivo")
        if not archivo or not archivo.filename:
            flash("Selecciona un archivo.", "danger")
        else:
            data = archivo.read()
            if not data:
                flash("El archivo está vacío.", "danger")
            elif len(data) > MAX_BYTES:
                flash(f"Archivo demasiado grande (máx. {MAX_BYTES // (1024 * 1024)} MB).", "danger")
            else:
                nombre = secure_filename(archivo.filename) or "archivo.bin"
                mime = (
                    archivo.mimetype
                    or mimetypes.guess_type(nombre)[0]
                    or "application/octet-stream"
                )
                b64 = base64.b64encode(data).decode("ascii")
                payload = {
                    "accion": "imagen",
                    "nombre": nombre,
                    "mime": mime,
                    "base64": b64,
                }
                body = json.dumps(payload, separators=(",", ":"))
                try:
                    # text/plain evita que el body se confunda con form y caiga al camino del mayor
                    resp = requests.post(
                        URL_WEBHOOK_SCRIPT,
                        data=body.encode("utf-8"),
                        headers={"Content-Type": "text/plain; charset=utf-8"},
                        timeout=90,
                    )
                    texto = (resp.text or "").strip()
                    detalle = {
                        "http": resp.status_code,
                        "bytes_archivo": len(data),
                        "len_base64": len(b64),
                        "nombre": nombre,
                        "mime": mime,
                        "body_enviado_0": body[:80],
                    }
                    if texto.upper().startswith("OK"):
                        url = texto[3:].lstrip(":").strip() if len(texto) > 2 else ""
                        resultado = {
                            "ok": True,
                            "respuesta": texto,
                            "url": url or None,
                            "detalle": detalle,
                        }
                        flash("Archivo subido a Drive (respaldoimagenes).", "success")
                    else:
                        resultado = {
                            "ok": False,
                            "respuesta": texto or f"HTTP {resp.status_code}",
                            "detalle": detalle,
                        }
                        flash(f"Drive/script respondió error: {resultado['respuesta']}", "danger")
                except Exception as exc:
                    resultado = {"ok": False, "respuesta": str(exc), "detalle": None}
                    flash(f"Error al llamar al Apps Script: {exc}", "danger")

    return render_template("drive_prueba/index.html", resultado=resultado)
