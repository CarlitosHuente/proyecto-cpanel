"""Redirects seguros: solo rutas internas (evita open redirect)."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from flask import has_request_context, request


def url_interna_segura(target: Optional[str], fallback: str = "/") -> str:
    """
    Acepta path relativo (/...) o URL absoluta del mismo Host.
    Rechaza //evil.com, esquemas externos y hosts distintos.
    """
    if not target:
        return fallback
    t = target.strip()
    if not t:
        return fallback

    parsed = urlparse(t)

    if parsed.scheme or parsed.netloc:
        if not has_request_context():
            return fallback
        host = (request.host or "").lower()
        if (parsed.netloc or "").lower() != host:
            return fallback
        path = parsed.path or "/"
        if not path.startswith("/") or path.startswith("//"):
            return fallback
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path

    if not t.startswith("/") or t.startswith("//"):
        return fallback
    return t
