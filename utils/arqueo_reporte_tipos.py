"""
Reporte mensual de ingresos por tipo de pago y desglose por sucursal.
Fuentes: terreno (captura cajero, Caja 1+2) o sistema (import líneas DEBE−HABER).
"""
from calendar import monthrange
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Literal, Optional

from utils.arqueo_caja_canal_ui_config import etiqueta_canal
from utils.arqueo_caja_import import normalizar_canal
from utils.arqueo_tipo_pago_config import resolver_tipo_pago
from utils.db import get_db_connection

FuenteReporte = Literal["terreno", "sistema"]


def _rango_mes(anio: int, mes: int) -> tuple[date, date]:
    ultimo = monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo)


def _pct(parte: Decimal, total: Decimal) -> float:
    if total is None or total == 0:
        return 0.0
    return float(
        (parte / total * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    )


def _filas_terreno_mes(desde: date, hasta: date, sucursal_id: Optional[int] = None) -> List[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            q = """SELECT t.id, t.sucursal_id, s.nombre_sucursal, t.fecha, t.caja,
                          t.canal_norm, t.canal_raw, t.monto, t.propina
                   FROM arqueo_caja_terreno t
                   JOIN Sucursales s ON s.sucursal_id = t.sucursal_id
                   WHERE t.fecha >= %s AND t.fecha <= %s"""
            params: list = [desde, hasta]
            if sucursal_id:
                q += " AND t.sucursal_id = %s"
                params.append(sucursal_id)
            q += " ORDER BY t.fecha DESC, s.nombre_sucursal, t.caja, t.canal_norm"
            cur.execute(q, params)
            return cur.fetchall() or []
    finally:
        conn.close()


def _filas_sistema_mes(desde: date, hasta: date, sucursal_id: Optional[int] = None) -> List[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            q = """SELECT l.sucursal_id, s.nombre_sucursal, l.fec_compr AS fecha,
                          l.desc_cta, l.debe, l.haber
                   FROM arqueo_caja_lineas l
                   JOIN Sucursales s ON s.sucursal_id = l.sucursal_id
                   WHERE l.fec_compr >= %s AND l.fec_compr <= %s"""
            params: list = [desde, hasta]
            if sucursal_id:
                q += " AND l.sucursal_id = %s"
                params.append(sucursal_id)
            cur.execute(q, params)
            rows = cur.fetchall() or []
    finally:
        conn.close()
    out = []
    for r in rows:
        cn = normalizar_canal(r.get("desc_cta"))
        if not cn:
            continue
        neto = Decimal(str(r["debe"])) - Decimal(str(r["haber"]))
        out.append(
            {
                "sucursal_id": r["sucursal_id"],
                "nombre_sucursal": r["nombre_sucursal"],
                "fecha": r["fecha"],
                "canal_norm": cn,
                "canal_raw": (r.get("desc_cta") or "").strip(),
                "monto": neto,
            }
        )
    return out


DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def contar_boletas_mes(
    anio: int, mes: int, sucursal_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Boletas emitidas = N_COMP distintos en import sistema (arqueo_caja_lineas) del mes.
    """
    desde, hasta = _rango_mes(anio, mes)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            base = """FROM arqueo_caja_lineas l
                      JOIN Sucursales s ON s.sucursal_id = l.sucursal_id
                      WHERE l.fec_compr >= %s AND l.fec_compr <= %s
                        AND TRIM(l.n_comp) <> ''"""
            params: list = [desde, hasta]
            suc_filter = ""
            if sucursal_id:
                suc_filter = " AND l.sucursal_id = %s"
            if sucursal_id:
                cur.execute(
                    f"""SELECT COUNT(DISTINCT l.n_comp) AS n {base}{suc_filter}""",
                    params + [sucursal_id],
                )
                total = int((cur.fetchone() or {}).get("n") or 0)
                cur.execute(
                    f"""SELECT l.sucursal_id, s.nombre_sucursal,
                               COUNT(DISTINCT l.n_comp) AS boletas
                        {base}{suc_filter}
                        GROUP BY l.sucursal_id, s.nombre_sucursal""",
                    params + [sucursal_id],
                )
            else:
                cur.execute(
                    f"""SELECT COUNT(DISTINCT l.n_comp) AS n {base}""",
                    params,
                )
                total = int((cur.fetchone() or {}).get("n") or 0)
                cur.execute(
                    f"""SELECT l.sucursal_id, s.nombre_sucursal,
                               COUNT(DISTINCT l.n_comp) AS boletas
                        {base}
                        GROUP BY l.sucursal_id, s.nombre_sucursal
                        ORDER BY s.nombre_sucursal""",
                    params,
                )
            por_suc = []
            for r in cur.fetchall() or []:
                b = int(r.get("boletas") or 0)
                por_suc.append(
                    {
                        "sucursal_id": r["sucursal_id"],
                        "nombre": r["nombre_sucursal"],
                        "boletas": b,
                        "pct_del_total": _pct(Decimal(b), Decimal(total)) if total else 0.0,
                    }
                )
            cur.execute(
                f"""SELECT l.fec_compr AS fecha, COUNT(DISTINCT l.n_comp) AS boletas
                    {base}{suc_filter}
                    GROUP BY l.fec_compr
                    ORDER BY l.fec_compr""",
                params + ([sucursal_id] if sucursal_id else []),
            )
            por_dia = []
            for r in cur.fetchall() or []:
                b = int(r.get("boletas") or 0)
                fe = r["fecha"]
                if hasattr(fe, "isoformat"):
                    fiso = fe.isoformat()
                    dia_nom = DIAS_ES[fe.weekday()]
                else:
                    fiso = str(fe)[:10]
                    dia_nom = ""
                por_dia.append(
                    {
                        "fecha": fiso,
                        "dia": dia_nom,
                        "boletas": b,
                        "pct_del_total": _pct(Decimal(b), Decimal(total)) if total else 0.0,
                    }
                )
    finally:
        conn.close()
    return {
        "total_boletas": total,
        "por_sucursal": por_suc,
        "por_dia": por_dia,
        "sucursal_id": sucursal_id,
    }


def _agregar_filas(
    filas: List[dict], incluir_detalle_filas: bool = False
) -> Dict[str, Any]:
    """
    Agrega montos por (tipo_pago, sucursal).
    filas deben tener: sucursal_id, nombre_sucursal, canal_norm, monto (+ opcional id, fecha, caja…)
    """
    tipo_suc: Dict[str, Dict[int, Decimal]] = {}
    tipo_meta: Dict[str, Dict[str, Any]] = {}
    suc_nombres: Dict[int, str] = {}
    total = Decimal("0")

    for r in filas:
        monto = Decimal(str(r.get("monto") or 0))
        if monto == 0:
            continue
        sid = int(r["sucursal_id"])
        cn = r.get("canal_norm") or ""
        etiqueta = etiqueta_canal(cn, r.get("canal_raw") or cn)
        tid, tlabel, tsort = resolver_tipo_pago(cn, etiqueta)
        total += monto
        suc_nombres[sid] = r.get("nombre_sucursal") or str(sid)
        if tid not in tipo_suc:
            tipo_suc[tid] = {}
            tipo_meta[tid] = {"id": tid, "label": tlabel, "sort": tsort}
        tipo_suc[tid][sid] = tipo_suc[tid].get(sid, Decimal("0")) + monto

    por_tipo = []
    for tid, por_suc in sorted(
        tipo_suc.items(), key=lambda x: (tipo_meta[x[0]]["sort"], tipo_meta[x[0]]["label"].lower())
    ):
        monto_tipo = sum(por_suc.values())
        sucursales = []
        for sid, monto_s in sorted(
            por_suc.items(), key=lambda x: suc_nombres.get(x[0], "").lower()
        ):
            sucursales.append(
                {
                    "sucursal_id": sid,
                    "nombre": suc_nombres.get(sid, str(sid)),
                    "monto": monto_s,
                    "pct_del_tipo": _pct(monto_s, monto_tipo),
                    "pct_del_total": _pct(monto_s, total),
                }
            )
        por_tipo.append(
            {
                "tipo_id": tid,
                "label": tipo_meta[tid]["label"],
                "monto": monto_tipo,
                "pct_del_total": _pct(monto_tipo, total),
                "sucursales": sucursales,
            }
        )

    detalle = []
    if incluir_detalle_filas:
        for r in filas:
            monto = Decimal(str(r.get("monto") or 0))
            if monto == 0:
                continue
            cn = r.get("canal_norm") or ""
            etiqueta = etiqueta_canal(cn, r.get("canal_raw") or cn)
            tid, tlabel, _ = resolver_tipo_pago(cn, etiqueta)
            fe = r.get("fecha")
            detalle.append(
                {
                    "id": r.get("id"),
                    "fecha": fe.isoformat() if hasattr(fe, "isoformat") else str(fe)[:10],
                    "sucursal_id": r["sucursal_id"],
                    "nombre_sucursal": r.get("nombre_sucursal"),
                    "caja": r.get("caja"),
                    "canal_norm": cn,
                    "canal_label": etiqueta,
                    "tipo_label": tlabel,
                    "monto": monto,
                }
            )

    return {
        "total_mes": total,
        "por_tipo": por_tipo,
        "detalle_filas": detalle,
        "cant_filas": len(filas),
    }


def reporte_tipos_pago_mes(
    anio: int,
    mes: int,
    fuente: FuenteReporte = "terreno",
    incluir_detalle: bool = False,
    sucursal_id: Optional[int] = None,
) -> Dict[str, Any]:
    desde, hasta = _rango_mes(anio, mes)
    if fuente == "sistema":
        filas = _filas_sistema_mes(desde, hasta, sucursal_id)
    else:
        raw = _filas_terreno_mes(desde, hasta, sucursal_id)
        filas = [
            {
                "id": r["id"],
                "sucursal_id": r["sucursal_id"],
                "nombre_sucursal": r["nombre_sucursal"],
                "fecha": r["fecha"],
                "caja": r.get("caja"),
                "canal_norm": r["canal_norm"],
                "canal_raw": r.get("canal_raw"),
                "monto": r["monto"],
            }
            for r in raw
        ]
    agg = _agregar_filas(filas, incluir_detalle_filas=incluir_detalle and fuente == "terreno")
    agg["boletas"] = contar_boletas_mes(anio, mes, sucursal_id)
    agg["desde"] = desde.isoformat()
    agg["hasta"] = hasta.isoformat()
    agg["anio"] = anio
    agg["mes"] = mes
    agg["fuente"] = fuente
    agg["sucursal_id"] = sucursal_id
    return agg
