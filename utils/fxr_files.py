"""Procesado de archivos FxR: escáner liviano, PDF páginas, rutas de staging."""
from __future__ import annotations

import io
import os
import uuid
from typing import List, Optional, Tuple

from flask import current_app
from PIL import Image, ImageOps, ImageEnhance
from pypdf import PdfReader, PdfWriter
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

ALLOWED_IMG = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
ALLOWED_PDF = {".pdf"}


def upload_root() -> str:
    root = os.path.join(current_app.root_path, "uploads", "fxr")
    os.makedirs(root, exist_ok=True)
    return root


def abs_path(rel: str) -> str:
    return os.path.join(current_app.root_path, rel)


def guardar_upload(file: FileStorage, usuario_slug: str, escaner: bool = True) -> Tuple[str, str, int]:
    """Guarda archivo procesado. Retorna (ruta_relativa, mime, num_paginas)."""
    if not file or not file.filename:
        raise ValueError("Sin archivo")
    nombre = secure_filename(file.filename) or "archivo"
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in ALLOWED_IMG | ALLOWED_PDF:
        raise ValueError("Formato no permitido (imagen o PDF)")

    carpeta_rel = os.path.join("uploads", "fxr", "staging", secure_filename(usuario_slug) or "user")
    carpeta_abs = os.path.join(current_app.root_path, carpeta_rel)
    os.makedirs(carpeta_abs, exist_ok=True)
    token = uuid.uuid4().hex[:12]

    data = file.read()
    if not data:
        raise ValueError("Archivo vacío")
    if len(data) > 12 * 1024 * 1024:
        raise ValueError("Archivo supera 12 MB")

    if ext in ALLOWED_PDF:
        rel, pages = _guardar_pdf(data, carpeta_abs, carpeta_rel, token)
        return rel, "application/pdf", pages

    rel = _guardar_imagen_escaner(data, carpeta_abs, carpeta_rel, token, escaner=escaner)
    return rel, "image/jpeg", 1


def _guardar_imagen_escaner(data: bytes, carpeta_abs: str, carpeta_rel: str, token: str, escaner: bool) -> str:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    # Reducir tamaño
    max_side = 1600
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    if escaner:
        gray = ImageOps.grayscale(img)
        gray = ImageOps.autocontrast(gray, cutoff=2)
        gray = ImageEnhance.Contrast(gray).enhance(1.25)
        gray = ImageEnhance.Sharpness(gray).enhance(1.1)
        out = gray.convert("RGB")
    else:
        out = img.convert("RGB")
    fname = f"{token}.jpg"
    abs_f = os.path.join(carpeta_abs, fname)
    out.save(abs_f, format="JPEG", quality=65, optimize=True)
    return os.path.join(carpeta_rel, fname).replace("\\", "/")


def _guardar_pdf(data: bytes, carpeta_abs: str, carpeta_rel: str, token: str) -> Tuple[str, int]:
    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    fname = f"{token}.pdf"
    abs_f = os.path.join(carpeta_abs, fname)
    with open(abs_f, "wb") as f:
        writer.write(f)
    return os.path.join(carpeta_rel, fname).replace("\\", "/"), len(reader.pages)


def pdf_eliminar_paginas(rel_path: str, indices_eliminar: List[int]) -> Tuple[str, int]:
    """indices_eliminar: 0-based. Reescribe el PDF en la misma carpeta."""
    abs_f = abs_path(rel_path)
    reader = PdfReader(abs_f)
    keep = [i for i in range(len(reader.pages)) if i not in set(indices_eliminar)]
    if not keep:
        raise ValueError("Debe quedar al menos una página")
    writer = PdfWriter()
    for i in keep:
        writer.add_page(reader.pages[i])
    token = uuid.uuid4().hex[:12]
    carpeta = os.path.dirname(abs_f)
    fname = f"{token}.pdf"
    nuevo_abs = os.path.join(carpeta, fname)
    with open(nuevo_abs, "wb") as f:
        writer.write(f)
    # borrar anterior
    try:
        if os.path.abspath(abs_f) != os.path.abspath(nuevo_abs):
            os.remove(abs_f)
    except OSError:
        pass
    rel_dir = os.path.dirname(rel_path)
    return os.path.join(rel_dir, fname).replace("\\", "/"), len(keep)


def borrar_archivo_local(rel_path: Optional[str]) -> None:
    if not rel_path:
        return
    try:
        p = abs_path(rel_path)
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass
