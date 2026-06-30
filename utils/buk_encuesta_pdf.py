"""Generación PDF simple para encuestas POC (Capacitación)."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

TZ_CHILE = ZoneInfo("America/Santiago")

CAMPOS_ENCUESTA = [
    ("campo_1", "1. Observación general"),
    ("campo_2", "2. Tema de capacitación"),
    ("campo_3", "3. Aprendizaje principal"),
    ("campo_4", "4. Calificación (1-5)"),
    ("campo_5", "5. Comentarios adicionales"),
]


def generar_pdf_encuesta(
    *,
    titulo: str,
    empleado: dict,
    respuestas: Dict[str, str],
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter
    y = height - 2 * cm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, y, titulo)
    y -= 0.8 * cm

    c.setFont("Helvetica", 10)
    ahora = datetime.now(TZ_CHILE).strftime("%d/%m/%Y %H:%M")
    c.drawString(2 * cm, y, f"Fecha: {ahora}")
    y -= 0.6 * cm
    c.drawString(2 * cm, y, f"Colaborador: {empleado.get('full_name') or '—'}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"RUT: {empleado.get('rut') or '—'}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"Ficha: {empleado.get('code_sheet') or '—'}")
    y -= 1 * cm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(2 * cm, y, "Respuestas")
    y -= 0.7 * cm

    c.setFont("Helvetica", 10)
    max_w = width - 4 * cm
    for key, label in CAMPOS_ENCUESTA:
        texto = (respuestas.get(key) or "").strip() or "—"
        y = _bloque_texto(c, 2 * cm, y, max_w, label, texto, height)
        y -= 0.4 * cm
        if y < 3 * cm:
            c.showPage()
            y = height - 2 * cm
            c.setFont("Helvetica", 10)

    y -= 0.5 * cm
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(
        2 * cm,
        max(y, 2 * cm),
        "Documento generado por Huente CPanel — requiere firma del colaborador en Buk.",
    )
    c.save()
    return buf.getvalue()


def _bloque_texto(c, x, y, max_w, label, texto, page_h):
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, label)
    y -= 0.45 * cm
    c.setFont("Helvetica", 10)
    for linea in _wrap(texto, 90):
        if y < 2.5 * cm:
            c.showPage()
            y = page_h - 2 * cm
            c.setFont("Helvetica", 10)
        c.drawString(x + 0.3 * cm, y, linea[:120])
        y -= 0.42 * cm
    return y


def _wrap(texto: str, ancho: int) -> List[str]:
    palabras = texto.split()
    if not palabras:
        return ["—"]
    lineas: List[str] = []
    actual = ""
    for p in palabras:
        candidato = f"{actual} {p}".strip()
        if len(candidato) <= ancho:
            actual = candidato
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas or ["—"]
