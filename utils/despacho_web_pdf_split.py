"""Divide un PDF multipágina en PDFs de una hoja (DespachoWeb masivo)."""
from __future__ import annotations

import io
from typing import List

from pypdf import PdfReader, PdfWriter


def dividir_pdf_por_paginas(data: bytes) -> List[bytes]:
    """Retorna una lista de PDFs (bytes), uno por página."""
    reader = PdfReader(io.BytesIO(data))
    if not reader.pages:
        raise ValueError("PDF sin páginas")
    paginas: List[bytes] = []
    for page in reader.pages:
        writer = PdfWriter()
        writer.add_page(page)
        buf = io.BytesIO()
        writer.write(buf)
        paginas.append(buf.getvalue())
    return paginas
