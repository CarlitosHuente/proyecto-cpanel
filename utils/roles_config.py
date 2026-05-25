"""
Persistencia unificada: permisos por rol + página de inicio por rol.
Archivo: roles_config.json en la raíz del proyecto.
Migra automáticamente desde permisos.json si existe.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from utils.permisos_catalogo import DEFAULT_PAGINA_INICIO

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLES_CONFIG_FILE = os.path.join(BASE_DIR, "roles_config.json")
PERMISOS_LEGACY_FILE = os.path.join(BASE_DIR, "permisos.json")

DEFAULT_PERMISOS: Dict[str, List[str]] = {
    "superusuario": ["*"],
    "admin": [
        "dashboard", "ventas", "clientes", "seremi", "contab", "reporte",
        "sucursales", "productos", "categorias", "agricola", "utilidades",
        "arqueo_caja", "fabrica", "flujo", "config",
    ],
    "ventas": ["dashboard", "ventas", "clientes", "utilidades"],
    "seremi2": ["seremi"],
    "seremi": ["sucursales", "seremi", "productos", "categorias"],
    "contab": ["contab", "utilidades"],
    "sucursales": ["sucursales", "seremi"],
    "gerencia": ["reporte", "ventas", "dashboard", "utilidades"],
    "logistica": ["sucursales", "productos", "categorias", "utilidades", "fabrica"],
    "invitado": [],
}

_config_cache: Optional[dict] = None


def _default_config() -> dict:
    return {
        "permisos": {k: list(v) for k, v in DEFAULT_PERMISOS.items()},
        "pagina_inicio": dict(DEFAULT_PAGINA_INICIO),
    }


def _migrar_desde_permisos_legacy() -> Optional[dict]:
    if not os.path.exists(PERMISOS_LEGACY_FILE):
        return None
    try:
        with open(PERMISOS_LEGACY_FILE, "r", encoding="utf-8") as f:
            permisos = json.load(f)
        cfg = _default_config()
        cfg["permisos"] = permisos
        return cfg
    except Exception as e:
        print(f"Error migrando permisos.json: {e}")
        return None


def cargar_config(forzar: bool = False) -> dict:
    global _config_cache
    if _config_cache is not None and not forzar:
        return _config_cache

    if os.path.exists(ROLES_CONFIG_FILE):
        try:
            with open(ROLES_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "permisos" not in data:
                data["permisos"] = _default_config()["permisos"]
            if "pagina_inicio" not in data:
                data["pagina_inicio"] = dict(DEFAULT_PAGINA_INICIO)
            _config_cache = data
            return data
        except Exception as e:
            print(f"Error cargando roles_config.json: {e}")

    migrado = _migrar_desde_permisos_legacy()
    if migrado:
        guardar_config(migrado)
        _config_cache = migrado
        return migrado

    cfg = _default_config()
    _config_cache = cfg
    return cfg


def guardar_config(config: dict) -> None:
    global _config_cache
    _config_cache = config
    try:
        with open(ROLES_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando roles_config.json: {e}")


def obtener_permisos() -> Dict[str, List[str]]:
    return cargar_config().get("permisos", {})


def guardar_permisos(nuevos: Dict[str, List[str]]) -> None:
    cfg = cargar_config()
    cfg["permisos"] = nuevos
    guardar_config(cfg)


def obtener_paginas_inicio() -> Dict[str, str]:
    return cargar_config().get("pagina_inicio", {})


def guardar_paginas_inicio(nuevas: Dict[str, str]) -> None:
    cfg = cargar_config()
    cfg["pagina_inicio"] = nuevas
    guardar_config(cfg)


def pagina_inicio_para_rol(rol: str) -> str:
    paginas = obtener_paginas_inicio()
    if rol in paginas and paginas[rol]:
        return paginas[rol]
    return DEFAULT_PAGINA_INICIO.get(rol) or DEFAULT_PAGINA_INICIO["default"]


def listar_roles(extra_desde_bd: Optional[List[str]] = None) -> List[str]:
    roles = list(obtener_permisos().keys())
    if extra_desde_bd:
        for r in extra_desde_bd:
            if r and r not in roles:
                roles.append(r)
    return sorted(roles, key=lambda x: (x != "superusuario", x != "admin", x.lower()))
