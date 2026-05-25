"""
Persistencia unificada: permisos por rol + página de inicio por rol.
Archivo principal: data/roles_config.json (carpeta escribible en hosting).
Migra desde roles_config.json o permisos.json en la raíz si existían.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

from utils.permisos_catalogo import DEFAULT_PAGINA_INICIO

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ROLES_CONFIG_FILE = os.path.join(DATA_DIR, "roles_config.json")
ROLES_CONFIG_LEGACY_ROOT = os.path.join(BASE_DIR, "roles_config.json")
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
_config_mtime: Optional[float] = None


def _default_config() -> dict:
    return {
        "permisos": {k: list(v) for k, v in DEFAULT_PERMISOS.items()},
        "pagina_inicio": dict(DEFAULT_PAGINA_INICIO),
    }


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _leer_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error leyendo {path}: {e}")
        return None


def _migrar_fuentes_legacy() -> Optional[dict]:
    """Toma permisos de archivos viejos en la raíz del proyecto."""
    if os.path.exists(ROLES_CONFIG_LEGACY_ROOT):
        data = _leer_json(ROLES_CONFIG_LEGACY_ROOT)
        if data and "permisos" in data:
            return data

    if os.path.exists(PERMISOS_LEGACY_FILE):
        permisos = _leer_json(PERMISOS_LEGACY_FILE)
        if permisos:
            cfg = _default_config()
            cfg["permisos"] = permisos
            return cfg
    return None


def _mtime_archivo() -> Optional[float]:
    if os.path.exists(ROLES_CONFIG_FILE):
        try:
            return os.path.getmtime(ROLES_CONFIG_FILE)
        except OSError:
            return None
    return None


def cargar_config(forzar: bool = False) -> dict:
    """Carga config; invalida caché si el archivo cambió en disco."""
    global _config_cache, _config_mtime

    mtime = _mtime_archivo()
    if (
        not forzar
        and _config_cache is not None
        and mtime is not None
        and _config_mtime == mtime
    ):
        return _config_cache

    if mtime is not None:
        data = _leer_json(ROLES_CONFIG_FILE)
        if data:
            if "permisos" not in data:
                data["permisos"] = _default_config()["permisos"]
            if "pagina_inicio" not in data:
                data["pagina_inicio"] = dict(DEFAULT_PAGINA_INICIO)
            _config_cache = data
            _config_mtime = mtime
            return data

    if _config_cache is not None and not forzar:
        return _config_cache

    migrado = _migrar_fuentes_legacy()
    if migrado:
        ok, _ = guardar_config(migrado)
        if ok:
            return migrado

    cfg = _default_config()
    _config_cache = cfg
    _config_mtime = None
    return cfg


def guardar_config(config: dict) -> Tuple[bool, str]:
    """Persiste en data/roles_config.json. Devuelve (ok, mensaje)."""
    global _config_cache, _config_mtime

    _ensure_data_dir()
    _config_cache = config

    try:
        tmp = ROLES_CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        os.replace(tmp, ROLES_CONFIG_FILE)
        _config_mtime = _mtime_archivo()
        return True, ROLES_CONFIG_FILE
    except Exception as e:
        msg = f"No se pudo guardar roles_config.json en {ROLES_CONFIG_FILE}: {e}"
        print(msg)
        return False, msg


def obtener_permisos() -> Dict[str, List[str]]:
    return cargar_config().get("permisos", {})


def guardar_permisos(nuevos: Dict[str, List[str]]) -> Tuple[bool, str]:
    cfg = dict(cargar_config())
    cfg["permisos"] = nuevos
    return guardar_config(cfg)


def obtener_paginas_inicio() -> Dict[str, str]:
    return cargar_config().get("pagina_inicio", {})


def guardar_paginas_inicio(nuevas: Dict[str, str]) -> Tuple[bool, str]:
    cfg = dict(cargar_config())
    cfg["pagina_inicio"] = nuevas
    return guardar_config(cfg)


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


def sincronizar_si_cambio() -> bool:
    """Recarga desde disco si el archivo fue modificado (otro worker o deploy)."""
    global _config_mtime
    mtime = _mtime_archivo()
    if mtime is not None and mtime != _config_mtime:
        cargar_config(forzar=True)
        return True
    return False
