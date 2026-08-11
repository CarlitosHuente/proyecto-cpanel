"""
Alertas Buk marcadas como revisadas (persistencia JSON).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, Set

from utils.roles_config import DATA_DIR

REVISADAS_FILE = os.path.join(DATA_DIR, "buk_alertas_revisadas.json")


def _ensure() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def leer_todas() -> Dict[str, dict]:
    _ensure()
    if not os.path.isfile(REVISADAS_FILE):
        return {}
    try:
        with open(REVISADAS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def ids_revisadas() -> Set[str]:
    return set(leer_todas().keys())


def esta_revisada(alerta_id: str) -> bool:
    return str(alerta_id) in leer_todas()


def marcar(alerta_id: str, usuario: str = "", revisada: bool = True) -> bool:
    _ensure()
    data = leer_todas()
    key = str(alerta_id)
    if revisada:
        data[key] = {
            "revisada_por": (usuario or "").strip(),
            "revisada_en": datetime.now().isoformat(timespec="seconds"),
        }
    elif key in data:
        del data[key]
    try:
        with open(REVISADAS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True
