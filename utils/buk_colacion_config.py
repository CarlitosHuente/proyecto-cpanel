"""
Minutos de colación por recinto (obraId) — configuración manual Huente.
Persistencia: data/buk_colacion_recintos.json

Prioridad al calcular (en buk_calendario): Buk colacionTurno → grupos por día semana → default.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from utils.roles_config import DATA_DIR

COLACION_FILE = os.path.join(DATA_DIR, "buk_colacion_recintos.json")
DEFAULT_MINUTOS = 60
DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def leer_todas() -> Dict[str, dict]:
    _ensure_data_dir()
    if not os.path.isfile(COLACION_FILE):
        return {}
    try:
        with open(COLACION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _entry_recinto(obra_id: str) -> dict:
    entry = leer_todas().get(str(obra_id)) or {}
    return entry if isinstance(entry, dict) else {}


def _clamp_minutos(n: int) -> int:
    return max(0, min(int(n), 240))


def parse_colacion_buk(raw: Optional[str]) -> Optional[int]:
    """Parsea colacionTurno de Buk: entero o rango HH:MM-HH:MM."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.isdigit():
        return _clamp_minutos(int(s))
    m = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$", s)
    if m:
        try:
            ini = int(m.group(1)) * 60 + int(m.group(2))
            fin = int(m.group(3)) * 60 + int(m.group(4))
            diff = fin - ini
            if diff <= 0:
                diff += 24 * 60
            return _clamp_minutos(diff)
        except (TypeError, ValueError):
            return None
    m2 = re.search(r"(\d+)\s*min", s, re.I)
    if m2:
        return _clamp_minutos(int(m2.group(1)))
    return None


def default_minutos_recinto(obra_id: str) -> int:
    entry = _entry_recinto(obra_id)
    for key in ("default_minutos", "minutos"):
        if key in entry:
            try:
                return _clamp_minutos(int(entry[key]))
            except (TypeError, ValueError):
                pass
    return DEFAULT_MINUTOS


def minutos_colacion(obra_id: str) -> int:
    """Compatibilidad: devuelve default del recinto."""
    return default_minutos_recinto(obra_id)


def minutos_por_weekday(obra_id: str, weekday: int) -> Optional[int]:
    entry = _entry_recinto(obra_id)
    for g in entry.get("grupos") or []:
        if not isinstance(g, dict):
            continue
        dias = g.get("dias") or []
        if weekday in dias:
            try:
                return _clamp_minutos(int(g.get("minutos", DEFAULT_MINUTOS)))
            except (TypeError, ValueError):
                return DEFAULT_MINUTOS
    return None


def resolver_minutos_colacion(
    obra_id: str,
    dia: date,
    turno: Optional[dict] = None,
) -> dict:
    """{minutos, fuente: 'buk'|'config'|'default'}"""
    if turno:
        parsed = parse_colacion_buk(turno.get("colacion_turno"))
        if parsed is not None:
            return {"minutos": parsed, "fuente": "buk"}
    wd = minutos_por_weekday(obra_id, dia.weekday())
    if wd is not None:
        return {"minutos": wd, "fuente": "config"}
    return {"minutos": default_minutos_recinto(obra_id), "fuente": "default"}


def normalizar_grupos(grupos_raw) -> Tuple[List[dict], Optional[str]]:
    if grupos_raw is None:
        return [], None
    if not isinstance(grupos_raw, list):
        return [], "grupos debe ser una lista."

    asignados: Dict[int, int] = {}
    grupos_out: List[dict] = []
    for g in grupos_raw:
        if not isinstance(g, dict):
            continue
        try:
            minutos = _clamp_minutos(int(g.get("minutos", DEFAULT_MINUTOS)))
        except (TypeError, ValueError):
            return [], "Minutos inválidos en un grupo."
        dias_raw = g.get("dias") or []
        if not isinstance(dias_raw, list):
            return [], "dias debe ser una lista en cada grupo."
        dias: List[int] = []
        for d in dias_raw:
            try:
                wd = int(d)
            except (TypeError, ValueError):
                return [], "Día de semana inválido (0=Lun … 6=Dom)."
            if wd < 0 or wd > 6:
                return [], "Día de semana fuera de rango (0=Lun … 6=Dom)."
            asignados[wd] = minutos
            if wd not in dias:
                dias.append(wd)
        if not dias:
            continue
        dias.sort()
        grupos_out.append({"dias": dias, "minutos": minutos})

    merged: Dict[int, List[int]] = {}
    for g in grupos_out:
        key = g["minutos"]
        merged.setdefault(key, []).extend(g["dias"])
    grupos_final: List[dict] = []
    for minutos, dias_list in sorted(merged.items()):
        uniq = sorted(set(dias_list))
        if uniq:
            grupos_final.append({"dias": uniq, "minutos": minutos})
    return grupos_final, None


def resumen_grupos_texto(obra_id: str) -> str:
    entry = _entry_recinto(obra_id)
    default = default_minutos_recinto(obra_id)
    mapa: Dict[int, int] = {i: default for i in range(7)}
    for g in entry.get("grupos") or []:
        if not isinstance(g, dict):
            continue
        try:
            mins = _clamp_minutos(int(g.get("minutos", default)))
        except (TypeError, ValueError):
            continue
        for d in g.get("dias") or []:
            try:
                mapa[int(d)] = mins
            except (TypeError, ValueError):
                pass

    partes: List[str] = []
    i = 0
    while i < 7:
        m = mapa[i]
        j = i + 1
        while j < 7 and mapa[j] == m:
            j += 1
        rango = DIAS_SEMANA[i] if i == j - 1 else f"{DIAS_SEMANA[i]}–{DIAS_SEMANA[j - 1]}"
        if m == default and not (entry.get("grupos") or []):
            partes.append(f"Default {m} min")
            break
        if m == default:
            partes.append(f"{rango} → default {m} min")
        else:
            partes.append(f"{rango} {m} min")
        i = j
    return " · ".join(partes) if partes else f"Default {default} min"


def guardar_recinto(obra_id: str, minutos: int, nombre: str = "") -> Tuple[bool, str]:
    """Compatibilidad: guarda solo default_minutos."""
    return guardar_config_recinto(obra_id, nombre=nombre, default_minutos=minutos, grupos=None)


def guardar_config_recinto(
    obra_id: str,
    *,
    nombre: str = "",
    default_minutos: Optional[int] = None,
    grupos: Optional[List[dict]] = None,
) -> Tuple[bool, str]:
    _ensure_data_dir()
    key = str(obra_id)
    entry = _entry_recinto(key)
    if default_minutos is not None:
        try:
            entry["default_minutos"] = _clamp_minutos(int(default_minutos))
        except (TypeError, ValueError):
            return False, "default_minutos inválido."
        entry["minutos"] = entry["default_minutos"]
    if grupos is not None:
        normalizados, err = normalizar_grupos(grupos)
        if err:
            return False, err
        entry["grupos"] = normalizados
    if nombre:
        entry["nombre"] = nombre.strip()

    data = leer_todas()
    data[key] = entry
    try:
        with open(COLACION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        return False, f"No se pudo guardar: {exc}"
    return True, "OK"


def config_recinto(obra_id: str) -> dict:
    entry = _entry_recinto(obra_id)
    default = default_minutos_recinto(obra_id)
    grupos = entry.get("grupos") or []
    if not isinstance(grupos, list):
        grupos = []
    return {
        "obra_id": str(obra_id),
        "nombre": entry.get("nombre") or "",
        "default_minutos": default,
        "grupos": grupos,
        "resumen": resumen_grupos_texto(obra_id),
    }
