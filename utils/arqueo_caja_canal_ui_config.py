"""
Presentación de canales en terreno/cuadratura: etiquetas y orden.
Persistencia en instance/arqueo_canales_ui.json (sin tablas nuevas).
La clave de conciliación sigue siendo canal_norm (canónico, ej. EFECTIVO).
"""
import json
import os
from typing import Any, Dict, List, Tuple

from utils.arqueo_caja_import import normalizar_canal

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INSTANCE = os.path.join(_BASE, "instance")
_CONFIG_PATH = os.path.join(_INSTANCE, "arqueo_canales_ui.json")


def _ensure_dir() -> None:
    os.makedirs(_INSTANCE, exist_ok=True)


def load_ui_config() -> Dict[str, Any]:
    _ensure_dir()
    if not os.path.exists(_CONFIG_PATH):
        return {"entries": []}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"entries": []}
        if "entries" not in data or not isinstance(data["entries"], list):
            data["entries"] = []
        return data
    except Exception:
        return {"entries": []}


def save_ui_config(data: Dict[str, Any]) -> None:
    _ensure_dir()
    out = {"entries": data.get("entries", [])}
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)


def _norm_entry_canonical(entry: Dict[str, Any]) -> str:
    return normalizar_canal(entry.get("canonical_norm", "") or entry.get("canonical", ""))


def etiqueta_canal(canonical_norm: str, muestra_sistema: str = "") -> str:
    """Nombre a mostrar; si hay mapeo usa label, si no muestra muestra_sistema o el norm."""
    cn = canonical_norm or ""
    for e in load_ui_config().get("entries", []):
        if _norm_entry_canonical(e) == cn:
            lab = (e.get("label") or "").strip()
            if lab:
                return lab
            break
    if (muestra_sistema or "").strip():
        return muestra_sistema.strip()
    return cn


def sort_tuple_canal(canonical_norm: str) -> Tuple[int, int, str]:
    """Orden de filas: sort ascendente del config; sin config al final alfabético."""
    cn = canonical_norm or ""
    for e in load_ui_config().get("entries", []):
        if _norm_entry_canonical(e) == cn:
            try:
                s = int(e.get("sort", 9999))
            except (TypeError, ValueError):
                s = 9999
            return (0, s, cn)
    return (1, 9999, cn)


def normalizar_entradas_config(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Limpia y normaliza canonical_norm; deduplica por norm."""
    seen = set()
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        raw = (e.get("canonical_norm") or e.get("canonical") or "").strip()
        cn = normalizar_canal(raw)
        if not cn or cn in seen:
            continue
        seen.add(cn)
        try:
            s = int(e.get("sort", 9999))
        except (TypeError, ValueError):
            s = 9999
        lab = (e.get("label") or "").strip()
        out.append({"canonical_norm": cn, "label": lab, "sort": s})
    out.sort(key=lambda x: (x["sort"], x["canonical_norm"]))
    return out
