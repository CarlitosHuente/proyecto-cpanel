"""
Agrupa canales (canal_norm) en tipos de pago para reportes (Efectivo, Redelcom, Delivery…).
Persistencia: instance/arqueo_tipos_pago.json
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from utils.arqueo_caja_import import normalizar_canal

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INSTANCE = os.path.join(_BASE, "instance")
_CONFIG_PATH = os.path.join(_INSTANCE, "arqueo_tipos_pago.json")


def _ensure_dir() -> None:
    os.makedirs(_INSTANCE, exist_ok=True)


def load_tipos_pago_config() -> Dict[str, Any]:
    _ensure_dir()
    if not os.path.exists(_CONFIG_PATH):
        return {"grupos": []}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"grupos": []}
        if "grupos" not in data or not isinstance(data["grupos"], list):
            data["grupos"] = []
        return data
    except Exception:
        return {"grupos": []}


def save_tipos_pago_config(data: Dict[str, Any]) -> None:
    _ensure_dir()
    out = {"grupos": normalizar_grupos_config(data.get("grupos", []))}
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)


def normalizar_grupos_config(grupos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_ids = set()
    seen_canales = set()
    out = []
    for g in grupos:
        if not isinstance(g, dict):
            continue
        gid = (g.get("id") or "").strip().lower().replace(" ", "_")[:40]
        if not gid or gid in seen_ids:
            continue
        label = (g.get("label") or gid).strip()[:80]
        try:
            sort = int(g.get("sort", 9999))
        except (TypeError, ValueError):
            sort = 9999
        canales_raw = g.get("canales") or []
        if isinstance(canales_raw, str):
            canales_raw = [c.strip() for c in canales_raw.split(",") if c.strip()]
        canales_norm = []
        for c in canales_raw:
            cn = normalizar_canal(c)
            if cn and cn not in seen_canales:
                seen_canales.add(cn)
                canales_norm.append(cn)
        seen_ids.add(gid)
        out.append({"id": gid, "label": label, "sort": sort, "canales": canales_norm})
    out.sort(key=lambda x: (x["sort"], x["label"].lower()))
    return out


def _mapa_canal_a_grupo() -> Dict[str, Tuple[str, str, int]]:
    """canal_norm -> (grupo_id, grupo_label, sort)"""
    m = {}
    for g in load_tipos_pago_config().get("grupos", []):
        gid = g.get("id") or ""
        label = g.get("label") or gid
        sort = g.get("sort", 9999)
        for cn in g.get("canales") or []:
            m[cn] = (gid, label, sort)
    return m


def resolver_tipo_pago(canal_norm: str, etiqueta_fallback: str = "") -> Tuple[str, str, int]:
    """
    Devuelve (tipo_id, tipo_label, sort).
    Si el canal no está en un grupo configurado, el tipo es el propio canal.
    """
    cn = canal_norm or ""
    m = _mapa_canal_a_grupo()
    if cn in m:
        gid, label, sort = m[cn]
        return gid, label, sort
    fb = (etiqueta_fallback or cn).strip() or cn
    return cn, fb, 9999


def listar_grupos_para_ui() -> List[Dict[str, Any]]:
    return load_tipos_pago_config().get("grupos", [])
