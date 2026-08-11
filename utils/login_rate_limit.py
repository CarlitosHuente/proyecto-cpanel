"""Rate-limit simple en memoria para el login (mitiga fuerza bruta externa)."""

from __future__ import annotations

import threading
import time
from typing import Dict, Tuple

# Ventana y umbrales (por proceso; en Passenger multi-worker es por worker).
_WINDOW_SEC = 300  # 5 minutos
_MAX_FAILS_IP = 20
_MAX_FAILS_EMAIL = 10

_lock = threading.Lock()
_fails: Dict[str, list] = {}


def _prune(times: list, now: float) -> list:
    cutoff = now - _WINDOW_SEC
    return [t for t in times if t >= cutoff]


def _key_ip(ip: str) -> str:
    return f"ip:{ip or 'unknown'}"


def _key_email(email: str) -> str:
    return f"email:{(email or '').strip().lower() or 'empty'}"


def login_bloqueado(ip: str, email: str) -> Tuple[bool, str]:
    """True si IP o email superó el umbral de fallos recientes."""
    now = time.time()
    with _lock:
        for key, limit, label in (
            (_key_ip(ip), _MAX_FAILS_IP, "IP"),
            (_key_email(email), _MAX_FAILS_EMAIL, "correo"),
        ):
            times = _prune(_fails.get(key, []), now)
            _fails[key] = times
            if len(times) >= limit:
                return True, (
                    f"Demasiados intentos fallidos ({label}). "
                    f"Espera unos minutos e inténtalo de nuevo."
                )
    return False, ""


def registrar_login_fallido(ip: str, email: str) -> None:
    now = time.time()
    with _lock:
        for key in (_key_ip(ip), _key_email(email)):
            times = _prune(_fails.get(key, []), now)
            times.append(now)
            _fails[key] = times


def registrar_login_ok(ip: str, email: str) -> None:
    """Limpia contadores del email (y alivia IP) tras un login correcto."""
    with _lock:
        _fails.pop(_key_email(email), None)
        # No borramos toda la IP: otros atacantes podrían compartir NAT.
