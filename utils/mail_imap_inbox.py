"""Cliente IMAP (stdlib) para bajar adjuntos PDF de una casilla."""

from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Any, Iterator, List, Optional


@dataclass
class PdfAttachment:
    message_id: str
    from_addr: str
    subject: str
    received_at: Optional[datetime]
    filename: str
    data: bytes
    imap_uid: str


def _decode_header_value(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return (raw or "").strip()


def _safe_filename(name: str) -> str:
    name = _decode_header_value(name) or "adjunto.pdf"
    name = name.replace("\\", "_").replace("/", "_")
    name = re.sub(r"[^\w.\- ()áéíóúÁÉÍÓÚñÑ]+", "_", name, flags=re.UNICODE)
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name[:180] or "adjunto.pdf"


def _message_id(msg: Message) -> str:
    mid = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
    if mid:
        return mid[:255]
    # Fallback estable si el servidor no envía Message-ID
    date = msg.get("Date") or ""
    subj = msg.get("Subject") or ""
    frm = msg.get("From") or ""
    return f"fallback:{hash((date, subj, frm)) & 0xFFFFFFFFFFFFFFFF:x}"


def _received_at(msg: Message) -> Optional[datetime]:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def _iter_pdf_parts(msg: Message) -> Iterator[tuple[str, bytes]]:
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disposition = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()
        ctype = (part.get_content_type() or "").lower()
        is_pdf = False
        if filename and filename.lower().endswith(".pdf"):
            is_pdf = True
        elif ctype == "application/pdf":
            is_pdf = True
        elif "attachment" in disposition and filename and ".pdf" in filename.lower():
            is_pdf = True
        if not is_pdf:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        yield _safe_filename(filename or "adjunto.pdf"), payload


def fetch_pdf_attachments(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    folder: str = "INBOX",
    ssl: bool = True,
    only_unseen: bool = False,
    mark_seen: bool = True,
    limit: int = 100,
) -> List[PdfAttachment]:
    """
    Lee la carpeta IMAP y devuelve adjuntos PDF.
    Por defecto revisa todos los mensajes recientes (hasta `limit` UIDs),
    no solo UNSEEN, para no perder correos ya abiertos en webmail.
    """
    if not host or not user:
        raise ValueError("Faltan IMAP_HOST o IMAP_USER.")

    if ssl:
        client: Any = imaplib.IMAP4_SSL(host, port)
    else:
        client = imaplib.IMAP4(host, port)

    results: List[PdfAttachment] = []
    try:
        client.login(user, password)
        typ, _ = client.select(folder, readonly=False)
        if typ != "OK":
            raise RuntimeError(f"No se pudo abrir carpeta IMAP: {folder}")

        criteria = "UNSEEN" if only_unseen else "ALL"
        typ, data = client.uid("search", None, criteria)
        if typ != "OK" or not data or not data[0]:
            return results

        uids = data[0].split()
        # Los más recientes primero
        uids = list(reversed(uids))[: max(1, limit)]

        for uid in uids:
            typ, fetched = client.uid("fetch", uid, "(RFC822)")
            if typ != "OK" or not fetched or not fetched[0]:
                continue
            raw = fetched[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw)
            mid = _message_id(msg)
            frm = _decode_header_value(msg.get("From"))
            subj = _decode_header_value(msg.get("Subject"))
            recv = _received_at(msg)
            pdfs = list(_iter_pdf_parts(msg))
            if not pdfs:
                continue
            for fname, blob in pdfs:
                results.append(
                    PdfAttachment(
                        message_id=mid,
                        from_addr=frm[:255],
                        subject=subj[:500],
                        received_at=recv,
                        filename=fname,
                        data=bytes(blob),
                        imap_uid=uid.decode() if isinstance(uid, bytes) else str(uid),
                    )
                )
            if mark_seen:
                client.uid("store", uid, "+FLAGS", "(\\Seen)")
    finally:
        try:
            client.logout()
        except Exception:
            pass

    return results
