#!/usr/bin/env python3
"""Sincroniza PDFs desde la casilla IMAP hacia mail_pdf_inbox.

Uso (desde la raíz del proyecto, con .env cargado):
  python3 scripts/sync_mail_pdf_inbox.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from utils.correo_pdf_service import imap_configurado, sync_from_imap  # noqa: E402


def main() -> int:
    if not imap_configurado():
        print("ERROR: IMAP no configurado. Revisá IMAP_HOST, IMAP_USER, IMAP_PASSWORD en .env")
        return 1
    result = sync_from_imap()
    if not result.get("ok"):
        print(f"ERROR: {result.get('error')}")
        return 1
    print(
        f"OK — nuevos={result.get('nuevos')} "
        f"duplicados={result.get('duplicados')} "
        f"adjuntos_revisados={result.get('revisados')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
