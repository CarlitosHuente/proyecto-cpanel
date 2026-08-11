"""
Resolución de Flask SECRET_KEY sin hardcodear en el repo.

Orden:
1. Variable de entorno SECRET_KEY (.env / cPanel)
2. Archivo persistente instance/flask_secret_key (gitignored)
3. Generar y guardar en ese archivo (primera vez en el servidor)
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = ROOT_DIR / "instance"
SECRET_FILE = INSTANCE_DIR / "flask_secret_key"


def obtener_secret_key() -> str:
    env_key = (os.environ.get("SECRET_KEY") or "").strip()
    if env_key:
        return env_key

    try:
        if SECRET_FILE.is_file():
            stored = SECRET_FILE.read_text(encoding="utf-8").strip()
            if stored:
                return stored
    except OSError:
        pass

    generated = secrets.token_urlsafe(48)
    try:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_text(generated + "\n", encoding="utf-8")
        try:
            os.chmod(SECRET_FILE, 0o600)
        except OSError:
            pass
    except OSError:
        # Sin permiso de escritura: clave efímera (reinicio invalida sesiones).
        return generated

    return generated
