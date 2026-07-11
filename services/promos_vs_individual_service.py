"""
Análisis Promoción vs Individual (solo Comercial).

Las líneas RUBRO=PROMOCIÓN se excluyen del NETO del dashboard para no doble-contar
dinero; aquí se leen a propósito para:
  1) contar packs de cada combo;
  2) derivar unidades de producto vía receta del nombre del combo;
  3) estimar unidades individuales = total producto (líneas no-promo) − unidades promo;
  4) KPIs de mix/ticket/precio efectivo;
  5) precios_base para simulador what-if en el cliente.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from utils.db import get_db_connection

SQL_COMERCIAL = """
    SELECT fecha, des_articu, rubro, n_comp, sub_rengl, cantidad,
           precio, precio_lis, sucursal
    FROM ventas_comercial
    WHERE UPPER(TRIM(estado)) IN ('COBRADO', 'COBRADA', 'DESPACH./COBRADA')
      AND fecha IS NOT NULL
"""

# Claves normalizadas (sin tilde, upper, espacios colapsados) → unidades por categoría.
RECETAS_PROMO: Dict[str, Dict[str, int]] = {
    "3X2 EMPANADAS PROMOCION": {"Empanadas": 3},
    "2 EMPANDAS Y 1 NECTAR": {"Empanadas": 2, "Nectar": 1},
    "1 EMPANADA Y 1 NECTAR": {"Empanadas": 1, "Nectar": 1},
    "1 EMPANADAS Y 1 BEBIDA": {"Empanadas": 1, "Bebidas": 1},
    "2 EMPANADAS Y 1 BEBIDA": {"Empanadas": 2, "Bebidas": 1},
    "1 EMPANADA + 1 NECTAR + 1 HELADO": {"Empanadas": 1, "Nectar": 1, "Helados": 1},
}

CATEGORIAS = ("Empanadas", "Nectar", "Bebidas", "Helados")


def _fold(texto) -> str:
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper().strip()
    return re.sub(r"\s+", " ", s)


def _filtro_fechas_sql(desde, hasta, semana, año) -> Tuple[str, list]:
    if desde and hasta:
        return " AND fecha >= %s AND fecha <= %s", [desde, hasta]
    if semana and año:
        return " AND YEAR(fecha) = %s AND WEEK(fecha, 3) = %s", [int(año), int(semana)]
    return "", []


def _cargar_lineas(
    sucursal: Optional[str],
    desde=None,
    hasta=None,
    semana=None,
    año=None,
) -> pd.DataFrame:
    extra_sql, params = _filtro_fechas_sql(desde, hasta, semana, año)
    sql = SQL_COMERCIAL + extra_sql
    if sucursal and sucursal != "TODAS":
        sql += " AND sucursal = %s"
        params = params + [sucursal]

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
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"])
    if df.empty:
        return df

    cant = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
    precio_lis = pd.to_numeric(df.get("PRECIO_LIS"), errors="coerce").fillna(0)
    precio = pd.to_numeric(df.get("PRECIO"), errors="coerce").fillna(0)
    sub = pd.to_numeric(df.get("SUB_RENGL"), errors="coerce").fillna(0)
    precio_efec = precio_lis.where(precio_lis != 0, precio)
    df["CANTIDAD"] = cant
    df["SUB_RENGL"] = sub
    df["PRECIO_UNIT_BRUTO"] = precio_efec
    # NETO presentación (lista×cant/1.19) — útil para precio efectivo de líneas producto.
    df["NETO"] = (cant * precio_efec) / 1.19
    df["FAMILIA_FOLD"] = df["FAMILIA"].map(_fold)
    df["DESC_FOLD"] = df["DESCRIPCION"].map(_fold)
    df["ES_PROMO"] = df["FAMILIA_FOLD"].str.contains("PROMOCION", na=False)
    return df


def _mask_categoria(df: pd.DataFrame, categoria: str) -> pd.Series:
    fam = df["FAMILIA_FOLD"]
    desc = df["DESC_FOLD"]
    if categoria == "Empanadas":
        return fam.str.contains("EMPANADA", na=False)
    if categoria == "Nectar":
        return desc.str.contains("NECTAR", na=False)
    if categoria == "Bebidas":
        return fam.str.contains("BEBIDA", na=False)
    if categoria == "Helados":
        return fam.str.contains("HELADO", na=False)
    return pd.Series(False, index=df.index)


def _receta_para_desc(desc_fold: str) -> Optional[Dict[str, int]]:
    if desc_fold in RECETAS_PROMO:
        return RECETAS_PROMO[desc_fold]
    for key, receta in RECETAS_PROMO.items():
        if key == desc_fold:
            return receta
    return None


def _neto_boleta_sin_doble_conteo(g: pd.DataFrame) -> float:
    """
    Plata cobrada de la boleta evitando el doble conteo típico 3x2
    (SUB_RENGL en promo y en componentes).

    Con promo: promo_sub + max(prod_sub_positivo − promo_sub, 0)
    Sin promo: suma SUB_RENGL productos.
    Resultado en NETO (/1.19).
    """
    promo_sub = float(g.loc[g["ES_PROMO"], "SUB_RENGL"].sum())
    prod_pos = float(g.loc[~g["ES_PROMO"] & (g["SUB_RENGL"] > 0), "SUB_RENGL"].sum())
    if promo_sub > 0:
        bruto = promo_sub + max(prod_pos - promo_sub, 0.0)
    else:
        bruto = prod_pos
    return bruto / 1.19


def _payload_vacio(sucursal: str) -> Dict[str, Any]:
    return {
        "kpis": {
            "packs_promo": 0,
            "neto_promo": 0,
            "combos_distintos": 0,
            "pct_empanadas_promo": 0.0,
            "pct_boletas_con_promo": 0.0,
            "ticket_con_promo": 0,
            "ticket_sin_promo": 0,
            "precio_efectivo_emp_promo": 0,
            "precio_efectivo_emp_indiv": 0,
            "packs_por_dia": 0.0,
            "dias_con_venta": 0,
            "packs_con_nectar": 0.0,
            "packs_con_bebida": 0.0,
            "total_boletas": 0,
            "boletas_con_promo": 0,
        },
        "por_categoria": [],
        "ranking_combos": [],
        "sin_receta": [],
        "precios_base": {"combos": [], "categorias": []},
        "meta": {
            "filas": 0,
            "filas_promo": 0,
            "sucursal": sucursal or "—",
            "empresa": "comercial",
        },
    }


def calcular_promos_vs_individual(
    sucursal: str,
    desde=None,
    hasta=None,
    semana=None,
    año=None,
) -> Dict[str, Any]:
    df = _cargar_lineas(
        sucursal=sucursal,
        desde=desde,
        hasta=hasta,
        semana=semana,
        año=año,
    )

    if df.empty:
        return _payload_vacio(sucursal)

    promos = df.loc[df["ES_PROMO"]].copy()
    productos = df.loc[~df["ES_PROMO"]].copy()

    packs_total = float(promos["CANTIDAD"].sum()) if not promos.empty else 0.0
    # Neto cobrado en combos: usa SUB_RENGL del promo (plata real del combo).
    if not promos.empty:
        neto_promo = int(round(float(promos["SUB_RENGL"].sum()) / 1.19))
    else:
        neto_promo = 0

    total_cat: Dict[str, float] = {}
    for cat in CATEGORIAS:
        if productos.empty:
            total_cat[cat] = 0.0
        else:
            total_cat[cat] = float(
                productos.loc[_mask_categoria(productos, cat), "CANTIDAD"].sum()
            )

    promo_cat: Dict[str, float] = {c: 0.0 for c in CATEGORIAS}
    # Neto de combo atribuido a cada categoría (reparto proporcional por unidades de receta).
    neto_atrib_cat: Dict[str, float] = {c: 0.0 for c in CATEGORIAS}
    ranking: List[dict] = []
    sin_receta: List[dict] = []
    packs_con_nectar = 0.0
    packs_con_bebida = 0.0
    precios_combos: List[dict] = []

    if not promos.empty:
        agrup = (
            promos.groupby("DESCRIPCION", dropna=False)
            .agg(
                packs=("CANTIDAD", "sum"),
                sub=("SUB_RENGL", "sum"),
                precio_sum=("PRECIO_UNIT_BRUTO", "sum"),
                n_lineas=("CANTIDAD", "count"),
            )
            .reset_index()
            .sort_values("packs", ascending=False)
        )
        for _, row in agrup.iterrows():
            desc = str(row["DESCRIPCION"])
            packs = float(row["packs"])
            neto = int(round(float(row["sub"]) / 1.19))
            # Precio bruto unitario promedio del pack (con IVA), enteros.
            precio_bruto_prom = (
                int(round(float(row["sub"]) / packs)) if packs > 0 else 0
            )
            pct_mix = round(100.0 * packs / packs_total, 1) if packs_total > 0 else 0.0
            receta = _receta_para_desc(_fold(desc))
            derivadas: Dict[str, float] = {c: 0.0 for c in CATEGORIAS}
            if receta:
                total_u_receta = float(sum(receta.values())) or 1.0
                for cat, u in receta.items():
                    qty = packs * float(u)
                    derivadas[cat] = qty
                    promo_cat[cat] += qty
                    neto_atrib_cat[cat] += neto * (float(u) / total_u_receta)
                if derivadas.get("Nectar", 0) > 0:
                    packs_con_nectar += packs
                if derivadas.get("Bebidas", 0) > 0:
                    packs_con_bebida += packs
                ranking.append(
                    {
                        "descripcion": desc,
                        "packs": packs,
                        "neto": neto,
                        "pct_mix": pct_mix,
                        "precio_bruto_prom": precio_bruto_prom,
                        "unidades": {
                            c: float(derivadas[c]) for c in CATEGORIAS if derivadas[c]
                        },
                        "con_receta": True,
                    }
                )
            else:
                sin_receta.append(
                    {"descripcion": desc, "packs": packs, "neto": neto}
                )
                ranking.append(
                    {
                        "descripcion": desc,
                        "packs": packs,
                        "neto": neto,
                        "pct_mix": pct_mix,
                        "precio_bruto_prom": precio_bruto_prom,
                        "unidades": {},
                        "con_receta": False,
                    }
                )
            precios_combos.append(
                {
                    "descripcion": desc,
                    "packs": packs,
                    "neto_actual": neto,
                    "precio_bruto_actual": precio_bruto_prom,
                    "con_receta": bool(receta),
                }
            )

    # --- Ticket y % boletas ---
    boletas_promo_ids = (
        set(promos["N_BOLETA"].dropna().unique()) if not promos.empty else set()
    )
    if "N_BOLETA" in df.columns and df["N_BOLETA"].notna().any():
        ticket_vals = []
        ticket_flags = []  # True = boleta con promo
        for boleta_id, g in df.dropna(subset=["N_BOLETA"]).groupby(
            "N_BOLETA", dropna=False
        ):
            ticket_vals.append(_neto_boleta_sin_doble_conteo(g))
            ticket_flags.append(boleta_id in boletas_promo_ids)
        total_boletas = len(ticket_vals)
        boletas_con_promo = int(sum(ticket_flags))
        pct_boletas = (
            round(100.0 * boletas_con_promo / total_boletas, 1) if total_boletas else 0.0
        )
        t_con = [v for v, f in zip(ticket_vals, ticket_flags) if f]
        t_sin = [v for v, f in zip(ticket_vals, ticket_flags) if not f]
        ticket_con = int(round(sum(t_con) / len(t_con))) if t_con else 0
        ticket_sin = int(round(sum(t_sin) / len(t_sin))) if t_sin else 0
    else:
        total_boletas = boletas_con_promo = 0
        pct_boletas = 0.0
        ticket_con = ticket_sin = 0

    # Días con venta
    dias = int(df["FECHA"].dt.normalize().nunique())
    packs_por_dia = round(packs_total / dias, 2) if dias else 0.0

    # Precio efectivo empanada (neto atribuido / unidades)
    emp_promo_u = float(promo_cat.get("Empanadas", 0.0))
    precio_emp_promo = (
        int(round(neto_atrib_cat["Empanadas"] / emp_promo_u)) if emp_promo_u > 0 else 0
    )

    # Individual: líneas emp en boletas SIN promo (plata y unidades claras).
    if not productos.empty and boletas_promo_ids:
        emp_mask = _mask_categoria(productos, "Empanadas")
        emp_suelto = productos.loc[
            emp_mask & ~productos["N_BOLETA"].isin(boletas_promo_ids)
        ]
    elif not productos.empty:
        emp_suelto = productos.loc[_mask_categoria(productos, "Empanadas")]
    else:
        emp_suelto = productos.iloc[0:0]

    emp_indiv_u = float(emp_suelto["CANTIDAD"].sum()) if len(emp_suelto) else 0.0
    # Neto individual: SUB_RENGL de esas líneas / 1.19 (cobro real suelto).
    emp_indiv_neto = (
        float(emp_suelto["SUB_RENGL"].sum()) / 1.19 if len(emp_suelto) else 0.0
    )
    precio_emp_indiv = (
        int(round(emp_indiv_neto / emp_indiv_u)) if emp_indiv_u > 0 else 0
    )

    por_categoria: List[dict] = []
    precios_categorias: List[dict] = []
    for cat in CATEGORIAS:
        total = float(total_cat[cat])
        en_promo_raw = float(promo_cat[cat])
        en_promo = min(en_promo_raw, total) if total > 0 else en_promo_raw
        individual = max(total - en_promo, 0.0)
        pct_promo = round(100.0 * en_promo / total, 1) if total > 0 else 0.0

        # Precio efectivo promo categoría
        pe_promo = (
            int(round(neto_atrib_cat[cat] / en_promo_raw)) if en_promo_raw > 0 else 0
        )
        # Precio individual observado: líneas categoría en boletas SIN promo.
        if not productos.empty:
            mask_c = _mask_categoria(productos, cat)
            if boletas_promo_ids:
                suelto = productos.loc[
                    mask_c & ~productos["N_BOLETA"].isin(boletas_promo_ids)
                ]
            else:
                suelto = productos.loc[mask_c]
            u_s = float(suelto["CANTIDAD"].sum())
            n_s = float(suelto["SUB_RENGL"].sum()) / 1.19
            pe_indiv = int(round(n_s / u_s)) if u_s > 0 else 0
            precio_bruto_indiv = int(round((n_s * 1.19) / u_s)) if u_s > 0 else 0
        else:
            pe_indiv = 0
            precio_bruto_indiv = 0

        # Simulador: volumen = unidades KPI individual; neto actual = vol × precio observado.
        neto_indiv_sim = (
            int(round(individual * precio_bruto_indiv / 1.19))
            if individual > 0 and precio_bruto_indiv > 0
            else 0
        )

        por_categoria.append(
            {
                "categoria": cat,
                "total": total,
                "promo": en_promo,
                "individual": individual,
                "pct_promo": pct_promo,
                "precio_efectivo_promo": pe_promo,
                "precio_efectivo_indiv": pe_indiv,
                "unidades_dia": round(total / dias, 2) if dias else 0.0,
            }
        )
        precios_categorias.append(
            {
                "categoria": cat,
                "unidades_individual": float(individual),
                "unidades_promo": float(en_promo),
                "neto_individual_actual": neto_indiv_sim,
                "precio_bruto_actual": precio_bruto_indiv,
                "precio_efectivo_promo": pe_promo,
                "precio_efectivo_indiv": pe_indiv,
            }
        )

    emp = next((c for c in por_categoria if c["categoria"] == "Empanadas"), None)
    pct_emp = float(emp["pct_promo"]) if emp else 0.0

    return {
        "kpis": {
            "packs_promo": float(packs_total),
            "neto_promo": int(neto_promo),
            "combos_distintos": int(len(ranking)),
            "pct_empanadas_promo": float(pct_emp),
            "pct_boletas_con_promo": float(pct_boletas),
            "ticket_con_promo": int(ticket_con),
            "ticket_sin_promo": int(ticket_sin),
            "precio_efectivo_emp_promo": int(precio_emp_promo),
            "precio_efectivo_emp_indiv": int(precio_emp_indiv),
            "packs_por_dia": float(packs_por_dia),
            "dias_con_venta": int(dias),
            "packs_con_nectar": float(packs_con_nectar),
            "packs_con_bebida": float(packs_con_bebida),
            "total_boletas": int(total_boletas),
            "boletas_con_promo": int(boletas_con_promo),
        },
        "por_categoria": por_categoria,
        "ranking_combos": ranking,
        "sin_receta": sin_receta,
        "precios_base": {
            "combos": precios_combos,
            "categorias": precios_categorias,
        },
        "meta": {
            "filas": int(len(df)),
            "filas_promo": int(len(promos)),
            "sucursal": sucursal or "—",
            "empresa": "comercial",
        },
    }
