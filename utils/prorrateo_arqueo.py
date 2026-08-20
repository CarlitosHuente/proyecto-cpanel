"""Prorrateo de cuentas de comisión según mix de Arqueo (reporte tipo de pago)."""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# Cuenta del mayor (plegada) → etiquetas/ids del reporte de tipos de pago.
# Mercado Pago = Redelcom (mismo mix de tarjeta/QR del arqueo).
_MAPA_CUENTA_TIPO = {
    "COMISION UBER EATS": ["UBER", "UBER EATS", "UBEREATS"],
    "COMISION MERCADO PAGO": ["REDELCOM", "MERCADO PAGO", "MERCADOPAGO"],
    "COMISION RAPPI": ["RAPPI"],
    "COMISION PEDIDOS YA": ["PEDIDOS YA", "PEDIDOSYA"],
    "COMISION MESA CHILENA": ["MESA CHILENA", "MESACHILENA"],
}

TIPO_ARQUEO = "ARQUEO_TIPO_PAGO"


def _fold(texto: Any) -> str:
    if texto is None:
        return ""
    s = unicodedata.normalize("NFD", str(texto).strip().upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def aliases_tipo_pago(nombre_cuenta: str) -> List[str]:
    """Aliases plegados para buscar el tipo en el reporte de Arqueo."""
    f = _fold(nombre_cuenta)
    if not f:
        return []
    for key, als in _MAPA_CUENTA_TIPO.items():
        if f == key or key in f or f in key:
            return [_fold(a) for a in als]
    if f.startswith("COMISION "):
        rest = f[9:].strip()
        if rest:
            return [rest]
    return []


def usa_mix_arqueo(nombre_cuenta: str, tipo: Optional[str] = None) -> bool:
    if (tipo or "") == TIPO_ARQUEO:
        return True
    f = _fold(nombre_cuenta)
    return any(f == key or key in f or f in key for key in _MAPA_CUENTA_TIPO)


def _alias_sucursal(nombre: str) -> List[str]:
    s = _fold(nombre).replace(".", " ")
    alias = [s]
    if "FOOD" in s or "ESC" in s or "MILITAR" in s:
        alias.extend(["ESC MILITAR", "ESCUELA MILITAR", "FOOD TRUCK", "FOODTRUCK"])
    if "WEB" in s:
        alias.extend(["WEB", "PAGINA WEB", "PAGINAWEB"])
    if "COSTANERA" in s:
        alias.extend(["COSTANERA", "COSTANERA CENTER"])
    if "EGANA" in s:
        alias.extend(["PLAZA EGANA"])
    if s == "MUT" or " MUT" in f" {s} ":
        alias.append("MUT")
    return list({a.replace("  ", " ").strip() for a in alias if a})


def _coinciden(nombre_a: str, nombre_b: str) -> bool:
    a_list = _alias_sucursal(nombre_a)
    b_list = _alias_sucursal(nombre_b)
    for a in a_list:
        for b in b_list:
            if a == b or a in b or b in a:
                return True
    return False


def _elegir_centro(nombre_suc: str, centros: List[str]) -> Optional[str]:
    for cc in centros:
        cc_s = str(cc or "").strip()
        if not cc_s or _fold(cc_s) in ("SERVICIOS GENERALES", "NAN", "NONE"):
            continue
        if _coinciden(nombre_suc, cc_s):
            return cc_s
    return None


def _encontrar_tipo(por_tipo: List[dict], nombre_cuenta: str) -> Optional[dict]:
    aliases = aliases_tipo_pago(nombre_cuenta)
    if not aliases:
        return None
    for t in por_tipo or []:
        lab = _fold(t.get("label"))
        tid = _fold(t.get("tipo_id"))
        for a in aliases:
            if not a:
                continue
            if a == lab or a == tid or a in lab or lab in a or a in tid or tid in a:
                return t
    return None


def _reporte_mes(periodo: str, fuente: str) -> Optional[dict]:
    from utils.arqueo_reporte_tipos import reporte_tipos_pago_mes

    partes = str(periodo or "").split("-")
    if len(partes) < 2:
        return None
    try:
        anio, mes = int(partes[0]), int(partes[1])
    except (TypeError, ValueError):
        return None
    try:
        return reporte_tipos_pago_mes(anio, mes, fuente=fuente)
    except Exception as e:
        print(f"WARN prorrateo arqueo ({fuente} {periodo}): {e}")
        return None


def distribucion_arqueo(
    nombre_cuenta: str,
    periodo: str,
    centros: List[str],
    reporte: Optional[dict] = None,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Proporciones 0–1 por centro de costo del mayor, según el mix de Arqueo
    (% de este tipo). Mercado Pago busca Redelcom.
    """
    meta: Dict[str, Any] = {"ok": False, "tipo_label": "", "fuente": "", "motivo": ""}
    tipo = None
    usado = reporte
    if usado:
        tipo = _encontrar_tipo(usado.get("por_tipo") or [], nombre_cuenta)
        meta["fuente"] = usado.get("fuente") or ""
    if tipo is None:
        for fuente in ("terreno", "sistema"):
            usado = _reporte_mes(periodo, fuente)
            if not usado:
                continue
            tipo = _encontrar_tipo(usado.get("por_tipo") or [], nombre_cuenta)
            if tipo:
                meta["fuente"] = fuente
                break
    if tipo is None:
        meta["motivo"] = "No hay mix de Arqueo para esta comisión en el mes"
        return {}, meta

    meta["tipo_label"] = tipo.get("label") or ""
    monto_tipo = float(tipo.get("monto") or 0)
    if monto_tipo <= 0:
        meta["motivo"] = f"Monto 0 en {meta['tipo_label']}"
        return {}, meta

    dist: Dict[str, float] = {}
    for suc in tipo.get("sucursales") or []:
        cc = _elegir_centro(suc.get("nombre") or "", centros)
        if not cc:
            cc = str(suc.get("nombre") or "").strip()
        if not cc:
            continue
        prop = float(suc.get("monto") or 0) / monto_tipo
        if prop <= 0:
            continue
        dist[cc] = dist.get(cc, 0.0) + prop

    total = sum(dist.values())
    if total <= 0:
        meta["motivo"] = "Sin sucursales con monto en ese tipo"
        return {}, meta
    if abs(total - 1.0) > 0.001:
        dist = {k: v / total for k, v in dist.items()}
    meta["ok"] = True
    return dist, meta
