"""Cola temporal de PDFs pendientes de validación (DespachoWeb)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_ROOT = os.path.join(BASE_DIR, "uploads", "despacho_web", "temp")
RESPALDO_ROOT = os.path.join(BASE_DIR, "uploads", "despacho_web", "respaldos")

MAX_PDFS = 5


def _batch_dir(batch_id: str) -> str:
    return os.path.join(TEMP_ROOT, batch_id)


def _manifest_path(batch_id: str) -> str:
    return os.path.join(_batch_dir(batch_id), "manifest.json")


def crear_batch(usuario: str, archivos: list[tuple[str, bytes, dict]]) -> str:
    """
    archivos: lista de (nombre_original, pdf_bytes, parsed_dict)
    """
    if not archivos:
        raise ValueError("Sin archivos")
    if len(archivos) > MAX_PDFS:
        raise ValueError(f"Máximo {MAX_PDFS} PDF por carga")

    batch_id = uuid.uuid4().hex
    bdir = _batch_dir(batch_id)
    os.makedirs(bdir, exist_ok=True)

    items = []
    for idx, (nombre, pdf_bytes, parsed) in enumerate(archivos):
        stored = f"{idx}.pdf"
        with open(os.path.join(bdir, stored), "wb") as f:
            f.write(pdf_bytes)
        items.append(
            {
                "idx": idx,
                "filename": nombre,
                "pdf_stored": stored,
                "parsed": parsed,
                "status": "pending",
            }
        )

    manifest = {
        "batch_id": batch_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "usuario": usuario,
        "items": items,
    }
    with open(_manifest_path(batch_id), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return batch_id


def cargar_batch(batch_id: str) -> dict[str, Any] | None:
    path = _manifest_path(batch_id)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_batch(manifest: dict) -> None:
    batch_id = manifest["batch_id"]
    with open(_manifest_path(batch_id), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def pdf_path(batch_id: str, idx: int) -> str | None:
    manifest = cargar_batch(batch_id)
    if not manifest:
        return None
    for it in manifest.get("items", []):
        if it["idx"] == idx and it.get("status") == "pending":
            return os.path.join(_batch_dir(batch_id), it["pdf_stored"])
    for it in manifest.get("items", []):
        if it["idx"] == idx:
            return os.path.join(_batch_dir(batch_id), it["pdf_stored"])
    return None


def item_pendiente(manifest: dict) -> dict | None:
    for it in manifest.get("items", []):
        if it.get("status") == "pending":
            return it
    return None


def contar_pendientes(manifest: dict) -> int:
    return sum(1 for it in manifest.get("items", []) if it.get("status") == "pending")


def marcar_item(manifest: dict, idx: int, status: str) -> None:
    for it in manifest.get("items", []):
        if it["idx"] == idx:
            it["status"] = status
            break
    guardar_batch(manifest)


def limpiar_batch(batch_id: str) -> None:
    bdir = _batch_dir(batch_id)
    if os.path.isdir(bdir):
        for fn in os.listdir(bdir):
            try:
                os.remove(os.path.join(bdir, fn))
            except OSError:
                pass
        try:
            os.rmdir(bdir)
        except OSError:
            pass


def mover_respaldo(batch_id: str, idx: int, n_orden: str) -> str:
    """Copia PDF temporal a respaldos/{n_orden}.pdf; retorna ruta relativa."""
    os.makedirs(RESPALDO_ROOT, exist_ok=True)
    src = pdf_path(batch_id, idx)
    if not src or not os.path.isfile(src):
        return ""
    dest_name = f"{n_orden}.pdf"
    dest = os.path.join(RESPALDO_ROOT, dest_name)
    with open(src, "rb") as fsrc:
        data = fsrc.read()
    with open(dest, "wb") as fdst:
        fdst.write(data)
    return os.path.join("despacho_web", "respaldos", dest_name).replace("\\", "/")
