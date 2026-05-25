"""
Agregación de ventas por hora (hora_pedid) para Comercial y Agrícola.
Reutiliza NETO comercial del dashboard; agrícola usa SUB_RENGL / 1.19.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from utils.db import get_db_connection
from utils.sheet_cache import procesar_neto_comercial_mismo_que_dashboard

_DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_DIAS_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

SQL_COMERCIAL = """
    SELECT fecha, hora_pedid, des_articu, rubro, n_comp, sub_rengl,
           cantidad, precio, precio_lis, sucursal
    FROM ventas_comercial
    WHERE UPPER(TRIM(estado)) IN ('COBRADO', 'COBRADA', 'DESPACH./COBRADA')
      AND fecha IS NOT NULL
"""

SQL_AGRICOLA = """
    SELECT fecha, hora_pedid, des_articu, rubro, n_comp, sub_rengl,
           cantidad, des_client
    FROM ventas_agricola
    WHERE UPPER(TRIM(estado)) IN ('COBRADO', 'COBRADA', 'DESPACH./COBRADA')
      AND fecha IS NOT NULL
"""


def _clasificar_sucursal_agricola(cliente) -> str:
    if pd.isna(cliente):
        return "FACTURA"
    c = str(cliente).upper()
    if "OCASIONAL" in c:
        return "BOLETAS"
    if "TRABAJADOR" in c:
        return "TRABAJADOR"
    return "FACTURA"


def parse_hora_pedid(val) -> Optional[int]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if hasattr(val, "hour"):
        h = int(val.hour)
        return h if 0 <= h <= 23 else None
    s = str(val).strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2})", s)
    if not m:
        return None
    h = int(m.group(1))
    return h if 0 <= h <= 23 else None


def _filtro_fechas_sql(desde, hasta, semana, año) -> Tuple[str, list]:
    if desde and hasta:
        return " AND fecha >= %s AND fecha <= %s", [desde, hasta]
    if semana and año:
        return " AND YEAR(fecha) = %s AND WEEK(fecha, 3) = %s", [int(año), int(semana)]
    return "", []


def _cargar_lineas(
    empresa: str,
    sucursal: Optional[str],
    desde=None,
    hasta=None,
    semana=None,
    año=None,
) -> pd.DataFrame:
    empresa = (empresa or "comercial").lower()
    extra_sql, params = _filtro_fechas_sql(desde, hasta, semana, año)

    if empresa == "comercial":
        sql = SQL_COMERCIAL + extra_sql
        if sucursal and sucursal != "TODAS":
            sql += " AND sucursal = %s"
            params = params + [sucursal]
    else:
        sql = SQL_AGRICOLA + extra_sql

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or None)
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df.columns = df.columns.str.strip().str.upper()
    df.rename(
        columns={"DES_ARTICU": "DESCRIPCION", "RUBRO": "FAMILIA", "N_COMP": "N_BOLETA"},
        inplace=True,
    )

    if empresa == "comercial":
        df = procesar_neto_comercial_mismo_que_dashboard(df, diagnostico=False)
    else:
        df["NETO"] = pd.to_numeric(df["SUB_RENGL"], errors="coerce").fillna(0) / 1.19
        df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
        if "DES_CLIENT" in df.columns:
            df["SUCURSAL"] = df["DES_CLIENT"].apply(_clasificar_sucursal_agricola)
        else:
            df["SUCURSAL"] = "FACTURA"
        if sucursal and sucursal != "TODAS":
            df = df[df["SUCURSAL"] == sucursal]

    if df.empty:
        return df

    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"])
    df["HORA"] = df["HORA_PEDID"].apply(parse_hora_pedid)
    df["NETO"] = pd.to_numeric(df["NETO"], errors="coerce").fillna(0)
    df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
    return df


def _ticket_promedio(neto: float, boletas: int) -> int:
    if boletas <= 0:
        return 0
    return int(round(neto / boletas))


def _filas_hora_vacias() -> List[dict]:
    return [
        {
            "hora": h,
            "label": f"{h:02d}:00",
            "neto": 0,
            "boletas": 0,
            "cantidad": 0,
            "ticket": 0,
            "pct_neto": 0.0,
        }
        for h in range(24)
    ]


def _serie_por_hora(df_sub: pd.DataFrame, neto_ref: int) -> List[dict]:
    if df_sub.empty or neto_ref <= 0:
        return _filas_hora_vacias()

    neto_por_h = df_sub.groupby("HORA", dropna=True)["NETO"].sum()
    cant_por_h = df_sub.groupby("HORA")["CANTIDAD"].sum()
    boletas_por_h = (
        df_sub.groupby("HORA")["N_BOLETA"].nunique()
        if "N_BOLETA" in df_sub.columns
        else pd.Series(dtype=int)
    )

    filas = []
    for h in range(24):
        neto_h = int(neto_por_h.get(h, 0))
        bol_h = int(boletas_por_h.get(h, 0)) if h in boletas_por_h.index else 0
        cant_h = int(cant_por_h.get(h, 0)) if h in cant_por_h.index else 0
        pct = round(100.0 * neto_h / neto_ref, 1) if neto_ref else 0.0
        filas.append(
            {
                "hora": h,
                "label": f"{h:02d}:00",
                "neto": neto_h,
                "boletas": bol_h,
                "cantidad": cant_h,
                "ticket": _ticket_promedio(neto_h, bol_h),
                "pct_neto": pct,
            }
        )
    return filas


def _kpis_sub(df_sub: pd.DataFrame) -> dict:
    if df_sub.empty:
        return {
            "neto_total": 0,
            "hora_pico": None,
            "hora_pico_label": "—",
            "neto_hora_pico": 0,
            "ticket_promedio": 0,
            "total_boletas": 0,
            "total_cantidad": 0,
        }
    neto = int(df_sub["NETO"].sum())
    boletas = int(df_sub["N_BOLETA"].nunique()) if "N_BOLETA" in df_sub.columns else 0
    cant = int(df_sub["CANTIDAD"].sum())
    sub_ok = df_sub[df_sub["HORA"].notna()]
    hora_pico = None
    neto_hp = 0
    if not sub_ok.empty:
        por_h = sub_ok.groupby("HORA")["NETO"].sum()
        if not por_h.empty:
            hora_pico = int(por_h.idxmax())
            neto_hp = int(por_h.max())
    return {
        "neto_total": neto,
        "hora_pico": hora_pico,
        "hora_pico_label": f"{hora_pico:02d}:00" if hora_pico is not None else "—",
        "neto_hora_pico": neto_hp,
        "ticket_promedio": _ticket_promedio(neto, boletas),
        "total_boletas": boletas,
        "total_cantidad": cant,
    }


def _serie_por_dia_semana(df_ok: pd.DataFrame, neto_total: int) -> List[dict]:
    if "DIA_ISO" not in df_ok.columns:
        df_ok = df_ok.copy()
        df_ok["DIA_ISO"] = df_ok["FECHA"].dt.isocalendar().day.astype(int)

    por_dia = []
    for dia_iso in range(1, 8):
        sub = df_ok[df_ok["DIA_ISO"] == dia_iso]
        neto_dia = int(sub["NETO"].sum()) if not sub.empty else 0
        kpis_d = _kpis_sub(sub)
        por_dia.append(
            {
                "dia_iso": dia_iso,
                "label": _DIAS_ES[dia_iso - 1],
                "label_corto": _DIAS_CORTO[dia_iso - 1],
                "neto_total": neto_dia,
                "hora_pico_label": kpis_d["hora_pico_label"],
                "neto_hora_pico": kpis_d["neto_hora_pico"],
                "total_boletas": kpis_d["total_boletas"],
                "por_hora": _serie_por_hora(sub, neto_dia if neto_dia else neto_total),
            }
        )
    return por_dia


def _empty_response(empresa, sucursal, desde, hasta, semana, año) -> Dict[str, Any]:
    return {
        "kpis": _kpis_sub(pd.DataFrame()),
        "por_hora": _filas_hora_vacias(),
        "por_dia": [
            {
                "dia_iso": i,
                "label": _DIAS_ES[i - 1],
                "label_corto": _DIAS_CORTO[i - 1],
                "neto_total": 0,
                "hora_pico_label": "—",
                "neto_hora_pico": 0,
                "total_boletas": 0,
                "por_hora": _filas_hora_vacias(),
            }
            for i in range(1, 8)
        ],
        "heatmap": {
            "dias": _DIAS_ES,
            "horas": list(range(24)),
            "valores": [[0] * 24 for _ in range(7)],
        },
        "sin_hora": {"neto": 0, "boletas": 0, "cantidad": 0},
        "meta": {
            "empresa": empresa,
            "sucursal": sucursal or "TODAS",
            "desde": desde,
            "hasta": hasta,
            "semana": semana,
            "año": año,
            "filas": 0,
        },
    }


def calcular_ventas_horario(
    empresa: str = "comercial",
    sucursal: Optional[str] = None,
    desde=None,
    hasta=None,
    semana=None,
    año=None,
) -> Dict[str, Any]:
    df = _cargar_lineas(empresa, sucursal, desde, hasta, semana, año)

    if df.empty:
        return _empty_response(empresa, sucursal, desde, hasta, semana, año)

    df_ok = df[df["HORA"].notna()].copy()
    df_sin = df[df["HORA"].isna()]

    neto_total = int(df["NETO"].sum())
    boletas_total = int(df["N_BOLETA"].nunique()) if "N_BOLETA" in df.columns else 0
    cantidad_total = int(df["CANTIDAD"].sum())

    por_hora = _serie_por_hora(df_ok, neto_total)
    hora_pico = None
    neto_hora_pico = 0
    neto_por_h = df_ok.groupby("HORA", dropna=True)["NETO"].sum()
    if not neto_por_h.empty:
        hora_pico = int(neto_por_h.idxmax())
        neto_hora_pico = int(neto_por_h.max())

    df_ok["DIA_ISO"] = df_ok["FECHA"].dt.isocalendar().day.astype(int)
    por_dia = _serie_por_dia_semana(df_ok, neto_total)

    heat_vals = [[0] * 24 for _ in range(7)]
    hm = df_ok.groupby(["DIA_ISO", "HORA"])["NETO"].sum()
    for (dia, hora), val in hm.items():
        di = int(dia) - 1
        hi = int(hora)
        if 0 <= di < 7 and 0 <= hi < 24:
            heat_vals[di][hi] = int(val)

    sin_hora_neto = int(df_sin["NETO"].sum()) if not df_sin.empty else 0
    sin_hora_bol = int(df_sin["N_BOLETA"].nunique()) if not df_sin.empty and "N_BOLETA" in df_sin.columns else 0
    sin_hora_cant = int(df_sin["CANTIDAD"].sum()) if not df_sin.empty else 0

    return {
        "kpis": {
            "neto_total": neto_total,
            "hora_pico": hora_pico,
            "hora_pico_label": f"{hora_pico:02d}:00" if hora_pico is not None else "—",
            "neto_hora_pico": neto_hora_pico,
            "ticket_promedio": _ticket_promedio(neto_total, boletas_total),
            "total_boletas": boletas_total,
            "total_cantidad": cantidad_total,
        },
        "por_hora": por_hora,
        "por_dia": por_dia,
        "heatmap": {
            "dias": _DIAS_ES,
            "horas": list(range(24)),
            "valores": heat_vals,
        },
        "sin_hora": {
            "neto": sin_hora_neto,
            "boletas": sin_hora_bol,
            "cantidad": sin_hora_cant,
        },
        "meta": {
            "empresa": empresa,
            "sucursal": sucursal or "TODAS",
            "desde": desde,
            "hasta": hasta,
            "semana": semana,
            "año": año,
            "filas": len(df),
        },
    }


def listar_sucursales_horario(empresa: str) -> List[str]:
    empresa = (empresa or "comercial").lower()
    if empresa == "agricola":
        return ["TODAS", "BOLETAS", "TRABAJADOR", "FACTURA"]

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT sucursal
                FROM ventas_comercial
                WHERE sucursal IS NOT NULL AND TRIM(sucursal) <> ''
                ORDER BY sucursal
                """
            )
            rows = cur.fetchall()
        return [str(r["sucursal"]) for r in rows if r.get("sucursal")]
    finally:
        conn.close()
