"""Bandeja PDF desde correo (Arqueo / resúmenes). Independiente de DespachoWeb."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.db import get_db_connection
from utils.env_config import imap_settings
from utils.mail_imap_inbox import fetch_pdf_attachments

BASE_DIR = Path(__file__).resolve().parent.parent
CORREO_PDF_ROOT = BASE_DIR / "uploads" / "correo_pdf"
TBL = "mail_pdf_inbox"


def ensure_dirs() -> None:
    CORREO_PDF_ROOT.mkdir(parents=True, exist_ok=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stored_name(row_id: int) -> str:
    return f"{row_id}.pdf"


def path_for_row(row_id: int) -> Path:
    return CORREO_PDF_ROOT / _stored_name(row_id)


def imap_configurado() -> bool:
    return bool(imap_settings().get("configurado"))


def listar_pdfs(
    *,
    incluir_ignored: bool = False,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    ensure_dirs()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if incluir_ignored:
                cur.execute(
                    f"""
                    SELECT id, message_id, from_addr, subject, received_at, filename,
                           sha256, status, error, created_at
                    FROM {TBL}
                    ORDER BY COALESCE(received_at, created_at) DESC, id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                cur.execute(
                    f"""
                    SELECT id, message_id, from_addr, subject, received_at, filename,
                           sha256, status, error, created_at
                    FROM {TBL}
                    WHERE status <> 'ignored'
                    ORDER BY COALESCE(received_at, created_at) DESC, id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            return list(cur.fetchall() or [])
    finally:
        conn.close()


def obtener_pdf(row_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, message_id, from_addr, subject, received_at, filename,
                       sha256, status, error, stored_path, created_at
                FROM {TBL}
                WHERE id = %s
                """,
                (row_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def ignorar_pdf(row_id: int) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {TBL} SET status = 'ignored', error = NULL WHERE id = %s",
                (row_id,),
            )
            conn.commit()
            return cur.rowcount > 0
    finally:
        conn.close()


def sync_from_imap(*, only_unseen: bool = False, limit: int = 80) -> Dict[str, Any]:
    """
    Baja PDFs nuevos desde IMAP y los registra en mail_pdf_inbox.
    Retorna contadores: nuevos, duplicados, sin_pdf omitidos vía cliente, error.
    """
    ensure_dirs()
    cfg = imap_settings()
    if not cfg.get("configurado"):
        return {
            "ok": False,
            "error": "IMAP no configurado (faltan IMAP_HOST / IMAP_USER / IMAP_PASSWORD).",
            "nuevos": 0,
            "duplicados": 0,
        }

    try:
        attachments = fetch_pdf_attachments(
            host=cfg["host"],
            port=int(cfg["port"]),
            user=cfg["user"],
            password=cfg["password"],
            folder=cfg["folder"],
            ssl=bool(cfg["ssl"]),
            only_unseen=only_unseen,
            mark_seen=True,
            limit=limit,
        )
    except Exception as ex:
        return {
            "ok": False,
            "error": f"Error IMAP: {ex}",
            "nuevos": 0,
            "duplicados": 0,
        }

    nuevos = 0
    duplicados = 0
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for att in attachments:
                digest = _sha256(att.data)
                cur.execute(
                    f"""
                    SELECT id FROM {TBL}
                    WHERE message_id = %s AND sha256 = %s
                    LIMIT 1
                    """,
                    (att.message_id, digest),
                )
                if cur.fetchone():
                    duplicados += 1
                    continue

                cur.execute(
                    f"""
                    INSERT INTO {TBL}
                        (message_id, from_addr, subject, received_at, filename,
                         sha256, stored_path, status, imap_uid)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                    """,
                    (
                        att.message_id,
                        att.from_addr,
                        att.subject,
                        att.received_at,
                        att.filename,
                        digest,
                        "",  # se actualiza tras conocer id
                        att.imap_uid,
                    ),
                )
                row_id = cur.lastrowid
                dest = path_for_row(row_id)
                dest.write_bytes(att.data)
                rel = f"correo_pdf/{row_id}.pdf"
                cur.execute(
                    f"UPDATE {TBL} SET stored_path = %s WHERE id = %s",
                    (rel, row_id),
                )
                nuevos += 1
        conn.commit()
    except Exception as ex:
        conn.rollback()
        return {
            "ok": False,
            "error": f"Error al guardar: {ex}",
            "nuevos": nuevos,
            "duplicados": duplicados,
        }
    finally:
        conn.close()

    return {
        "ok": True,
        "error": None,
        "nuevos": nuevos,
        "duplicados": duplicados,
        "revisados": len(attachments),
    }
