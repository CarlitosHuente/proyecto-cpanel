"""Comparativo de ventas en neto: 6 periodos vs el mismo corte del año anterior."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence

import pandas as pd
import pytz

from utils.db import get_db_connection
from utils.sheet_cache import procesar_neto_comercial_mismo_que_dashboard

ESTADOS_SQL = "('COBRADO', 'COBRADA', 'DESPACH./COBRADA')"
MESES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
FAMILIAS_BASE = ["Otros", "Quesos", "Empanadas", "Papayas", "Bebidas", "Pizzas", "Helados"]


def hoy_chile() -> date:
    return datetime.now(pytz.timezone("America/Santiago")).date()


def _mes_atras(anio: int, mes: int, n: int) -> tuple:
    mes -= n
    while mes <= 0:
        mes += 12
        anio -= 1
    return anio, mes


def _fin_mes(anio: int, mes: int) -> date:
    if mes == 12:
        return date(anio + 1, 1, 1) - timedelta(days=1)
    return date(anio, mes + 1, 1) - timedelta(days=1)


def ancla_datos(empresa: str) -> date:
    """Última venta cobrada, sin pasar de hoy. Así el corte sigue los datos cargados."""
    hoy = hoy_chile()
    tabla = "ventas_comercial" if empresa == "comercial" else "ventas_agricola"
    df = _query(
        f"""
        SELECT MAX(fecha) AS fecha
        FROM {tabla}
        WHERE UPPER(TRIM(estado)) IN {ESTADOS_SQL}
          AND fecha IS NOT NULL
        """,
        (),
    )
    if df.empty or df.iloc[0]["FECHA"] is None:
        return hoy
    bruto = df.iloc[0]["FECHA"]
    if isinstance(bruto, datetime):
        bruto = bruto.date()
    elif not isinstance(bruto, date):
        bruto = pd.to_datetime(bruto, errors="coerce")
        if pd.isna(bruto):
            return hoy
        bruto = bruto.date()
    return bruto if bruto <= hoy else hoy


def armar_periodos(corte: str, ancla: Optional[date] = None, hoy_real: Optional[date] = None) -> List[dict]:
    ancla = ancla or hoy_chile()
    hoy_real = hoy_real or hoy_chile()
    periodos: List[dict] = []
    if corte == "semanal":
        lunes = ancla - timedelta(days=ancla.weekday())
        for i in range(5, -1, -1):
            d = lunes - timedelta(weeks=i)
            iso = d.isocalendar()
            anio, semana = int(iso.year), int(iso.week)
            ini = date.fromisocalendar(anio, semana, 1)
            fin = date.fromisocalendar(anio, semana, 7)
            s_ini = s_fin = None
            try:
                s_ini = date.fromisocalendar(anio - 1, semana, 1)
                s_fin = date.fromisocalendar(anio - 1, semana, 7)
            except ValueError:
                pass
            periodos.append(
                {
                    "etiqueta": f"S{semana}",
                    "etiqueta_sombra": f"S{semana} {anio - 1}" if s_ini else f"S{semana} s/año ant.",
                    "inicio": ini,
                    "fin": fin,
                    "sombra_inicio": s_ini,
                    "sombra_fin": s_fin,
                    "incompleto": ini <= hoy_real < fin,
                }
            )
        return periodos

    for i in range(5, -1, -1):
        anio, mes = _mes_atras(ancla.year, ancla.month, i)
        ini = date(anio, mes, 1)
        fin = _fin_mes(anio, mes)
        s_anio = anio - 1
        s_ini = date(s_anio, mes, 1)
        s_fin = _fin_mes(s_anio, mes)
        periodos.append(
            {
                "etiqueta": f"{MESES[mes]} {anio}",
                "etiqueta_sombra": f"{MESES[mes]} {s_anio}",
                "inicio": ini,
                "fin": fin,
                "sombra_inicio": s_ini,
                "sombra_fin": s_fin,
                "incompleto": ini <= hoy_real < fin,
            }
        )
    return periodos


def _rangos_sql(periodos: Sequence[dict]) -> tuple:
    ini_a = min(p["inicio"] for p in periodos)
    fin_a = max(p["fin"] for p in periodos)
    sombras = [p for p in periodos if p["sombra_inicio"] and p["sombra_fin"]]
    if not sombras:
        return ini_a, fin_a, None, None
    return ini_a, fin_a, min(p["sombra_inicio"] for p in sombras), max(p["sombra_fin"] for p in sombras)


def _query(sql: str, params: tuple) -> pd.DataFrame:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.columns = df.columns.str.strip().str.upper()
    return df


def _cargar_lineas(empresa: str, periodos: Sequence[dict]) -> pd.DataFrame:
    ini_a, fin_a, ini_s, fin_s = _rangos_sql(periodos)
    if ini_s is None:
        filtro_fecha = "fecha >= %s AND fecha <= %s"
        params = (ini_a, fin_a)
    else:
        filtro_fecha = "((fecha >= %s AND fecha <= %s) OR (fecha >= %s AND fecha <= %s))"
        params = (ini_a, fin_a, ini_s, fin_s)

    if empresa == "comercial":
        df = _query(
            f"""
            SELECT fecha, des_articu, rubro, sub_rengl, cantidad, precio, precio_lis, sucursal, n_comp
            FROM ventas_comercial
            WHERE UPPER(TRIM(estado)) IN {ESTADOS_SQL}
              AND fecha IS NOT NULL
              AND {filtro_fecha}
            """,
            params,
        )
        if df.empty:
            return df
        df.rename(
            columns={"DES_ARTICU": "DESCRIPCION", "RUBRO": "FAMILIA"},
            inplace=True,
        )
        df = procesar_neto_comercial_mismo_que_dashboard(df, diagnostico=False)
    else:
        df = _query(
            f"""
            SELECT fecha, des_articu, rubro, sub_rengl, cantidad, des_client, n_comp
            FROM ventas_agricola
            WHERE UPPER(TRIM(estado)) IN {ESTADOS_SQL}
              AND fecha IS NOT NULL
              AND {filtro_fecha}
            """,
            params,
        )
        if df.empty:
            return df
        df.rename(
            columns={"DES_ARTICU": "DESCRIPCION", "RUBRO": "FAMILIA"},
            inplace=True,
        )
        df["NETO"] = pd.to_numeric(df["SUB_RENGL"], errors="coerce").fillna(0) / 1.19
        df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
        cliente = df["DES_CLIENT"].astype(str).str.upper()
        df["SUCURSAL"] = "FACTURA"
        df.loc[cliente.str.contains("OCASIONAL", na=False), "SUCURSAL"] = "BOLETAS"
        df.loc[cliente.str.contains("TRABAJADOR", na=False), "SUCURSAL"] = "TRABAJADOR"
        df["FAMILIA"] = df["FAMILIA"].fillna("SIN FAMILIA").astype(str).str.strip()

    if df.empty:
        return df
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"])
    df["SUCURSAL"] = df["SUCURSAL"].fillna("").astype(str).str.strip()
    df["DESCRIPCION"] = df["DESCRIPCION"].fillna("").astype(str).str.strip()
    df["FAMILIA"] = df["FAMILIA"].fillna("SIN FAMILIA").astype(str).str.strip()
    df["NETO"] = pd.to_numeric(df["NETO"], errors="coerce").fillna(0.0)
    df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0.0)
    if "N_COMP" not in df.columns:
        df["N_COMP"] = ""
    df["N_COMP"] = df["N_COMP"].fillna("").astype(str).str.strip()
    return df


def _mask_rango(serie_fecha: pd.Series, ini: Optional[date], fin: Optional[date]) -> pd.Series:
    if ini is None or fin is None:
        return pd.Series(False, index=serie_fecha.index)
    return (serie_fecha >= pd.Timestamp(ini)) & (serie_fecha <= pd.Timestamp(fin))


def _var_pct(actual: float, sombra: float) -> Optional[float]:
    if sombra == 0:
        return None
    return round((actual - sombra) / abs(sombra) * 100, 1)


def _serie(df: pd.DataFrame, periodos: Sequence[dict]) -> List[dict]:
    filas = []
    for p in periodos:
        neto = float(df.loc[_mask_rango(df["FECHA"], p["inicio"], p["fin"]), "NETO"].sum()) if not df.empty else 0.0
        sombra = (
            float(df.loc[_mask_rango(df["FECHA"], p["sombra_inicio"], p["sombra_fin"]), "NETO"].sum())
            if not df.empty
            else 0.0
        )
        filas.append(
            {
                "etiqueta": p["etiqueta"],
                "etiqueta_sombra": p["etiqueta_sombra"],
                "neto": round(neto),
                "neto_sombra": round(sombra),
                "var_pesos": round(neto - sombra),
                "var_pct": _var_pct(neto, sombra),
                "incompleto": bool(p["incompleto"]),
            }
        )
    return filas


def _totales(serie: Sequence[dict]) -> dict:
    neto = sum(x["neto"] for x in serie)
    sombra = sum(x["neto_sombra"] for x in serie)
    return {
        "neto": int(round(neto)),
        "neto_sombra": int(round(sombra)),
        "var_pesos": int(round(neto - sombra)),
        "var_pct": _var_pct(neto, sombra),
    }


def _top_productos(df: pd.DataFrame, periodos: Sequence[dict], limite: int = 8) -> List[dict]:
    if df.empty:
        return []
    mask_a = pd.Series(False, index=df.index)
    mask_s = pd.Series(False, index=df.index)
    for p in periodos:
        mask_a = mask_a | _mask_rango(df["FECHA"], p["inicio"], p["fin"])
        mask_s = mask_s | _mask_rango(df["FECHA"], p["sombra_inicio"], p["sombra_fin"])
    actual = df.loc[mask_a].groupby("DESCRIPCION", dropna=False)["NETO"].sum()
    sombra = df.loc[mask_s].groupby("DESCRIPCION", dropna=False)["NETO"].sum()
    if actual.empty:
        return []
    top = actual.sort_values(ascending=False).head(limite)
    out = []
    for nombre, neto in top.items():
        ant = float(sombra.get(nombre, 0.0))
        neto_f = float(neto)
        out.append(
            {
                "producto": str(nombre),
                "neto": round(neto_f),
                "neto_sombra": round(ant),
                "var_pesos": round(neto_f - ant),
                "var_pct": _var_pct(neto_f, ant),
            }
        )
    return out


def _bloques(df: pd.DataFrame, vista: str, sucursales: Sequence[str], periodos: Sequence[dict]) -> List[dict]:
    presentes = sorted({s for s in df["SUCURSAL"].tolist() if s}) if not df.empty else []
    elegidas = [s for s in sucursales if s] or presentes
    if vista == "sucursales":
        grupos = [(n, [n]) for n in elegidas]
    elif vista == "ambos":
        grupos = [("Consolidado", list(elegidas))] + [(n, [n]) for n in elegidas]
    else:
        grupos = [("Consolidado", list(elegidas) if sucursales else None)]

    bloques = []
    for titulo, filtro in grupos:
        if filtro is None:
            sub = df
        elif df.empty:
            sub = df
        else:
            sub = df[df["SUCURSAL"].isin(filtro)]
        serie = _serie(sub, periodos)
        bloques.append({"titulo": titulo, "serie": serie, "totales": _totales(serie)})
    return bloques


def opciones(empresa: str) -> dict:
    """Sucursales y familias para el formulario, acotadas a 14 meses."""
    desde = hoy_chile() - timedelta(days=430)
    if empresa == "agricola":
        df = _query(
            f"""
            SELECT DISTINCT
                CASE
                    WHEN UPPER(des_client) LIKE '%%OCASIONAL%%' THEN 'BOLETAS'
                    WHEN UPPER(des_client) LIKE '%%TRABAJADOR%%' THEN 'TRABAJADOR'
                    ELSE 'FACTURA'
                END AS sucursal,
                rubro
            FROM ventas_agricola
            WHERE fecha >= %s AND fecha IS NOT NULL
            """,
            (desde,),
        )
        if df.empty:
            return {"sucursales": ["BOLETAS", "FACTURA", "TRABAJADOR"], "familias": []}
        suc = sorted({str(s).strip() for s in df["SUCURSAL"].tolist() if str(s).strip()})
        fam = sorted({str(s).strip() for s in df["RUBRO"].dropna().tolist() if str(s).strip()})
        return {"sucursales": suc, "familias": fam}

    suc_df = _query(
        """
        SELECT DISTINCT sucursal
        FROM ventas_comercial
        WHERE fecha >= %s AND sucursal IS NOT NULL AND TRIM(sucursal) <> ''
        """,
        (desde,),
    )
    rub_df = _query(
        """
        SELECT DISTINCT rubro
        FROM ventas_comercial
        WHERE fecha >= %s AND rubro IS NOT NULL AND TRIM(rubro) <> ''
        """,
        (desde,),
    )
    sucursales = []
    if not suc_df.empty:
        sucursales = sorted({str(s).strip() for s in suc_df["SUCURSAL"].tolist() if str(s).strip()})
    familias = list(FAMILIAS_BASE)
    if not rub_df.empty:
        mini = pd.DataFrame(
            {
                "DESCRIPCION": [""] * len(rub_df),
                "FAMILIA": rub_df["RUBRO"].astype(str).tolist(),
                "CANTIDAD": 0,
                "PRECIO": 0,
                "PRECIO_LIS": 0,
                "SUB_RENGL": 0,
                "SUCURSAL": "",
            }
        )
        proc = procesar_neto_comercial_mismo_que_dashboard(mini, diagnostico=False)
        if not proc.empty and "FAMILIA" in proc.columns:
            extra = sorted({str(s).strip() for s in proc["FAMILIA"].tolist() if str(s).strip()})
            familias = sorted(set(familias) | set(extra))
    return {"sucursales": sucursales, "familias": familias}


def _recorte(df: pd.DataFrame, periodo: dict, sombra: bool = False) -> pd.DataFrame:
    if df.empty:
        return df
    if sombra:
        return df.loc[_mask_rango(df["FECHA"], periodo["sombra_inicio"], periodo["sombra_fin"])]
    return df.loc[_mask_rango(df["FECHA"], periodo["inicio"], periodo["fin"])]


def _ticket(df: pd.DataFrame) -> Optional[int]:
    if df.empty:
        return None
    boletas = df["N_COMP"]
    boletas = boletas[boletas.ne("") & ~boletas.str.lower().isin(["none", "nan"])]
    n = int(boletas.nunique())
    if n <= 0:
        return None
    return int(round(float(df["NETO"].sum()) / n))


def _partes(df: pd.DataFrame, columna: str) -> List[dict]:
    if df.empty or columna not in df.columns:
        return []
    grupo = df.groupby(columna, dropna=False)["NETO"].sum().sort_values(ascending=False)
    total = float(grupo.sum())
    if total == 0:
        return []
    out = []
    for nombre, neto in grupo.items():
        valor = float(neto)
        if valor == 0:
            continue
        out.append(
            {
                "nombre": str(nombre),
                "neto": int(round(valor)),
                "pct": round(valor / total * 100, 1),
            }
        )
    return out


def _precio(neto: float, cantidad: float) -> Optional[int]:
    if not cantidad:
        return None
    return int(round(neto / cantidad))


def _fichas_familia(df_periodo: pd.DataFrame, familias: Sequence[str]) -> List[dict]:
    if df_periodo.empty:
        nombres = list(familias)
    elif not familias:
        top = df_periodo.groupby("FAMILIA")["NETO"].sum().sort_values(ascending=False).head(4)
        nombres = [str(n) for n in top.index]
    else:
        nombres = [str(f) for f in familias if str(f).strip()]
    out = []
    for fam in nombres:
        sub = df_periodo[df_periodo["FAMILIA"] == fam] if not df_periodo.empty else df_periodo
        neto = float(sub["NETO"].sum()) if not sub.empty else 0.0
        cant = float(sub["CANTIDAD"].sum()) if not sub.empty else 0.0
        out.append(
            {
                "familia": fam,
                "neto": int(round(neto)),
                "cantidad": cant,
                "precio": _precio(neto, cant),
            }
        )
    return out


def _comparativo_sucursales(df: pd.DataFrame, periodo: dict, sucursales: Sequence[str]) -> List[dict]:
    presentes = sorted({s for s in df["SUCURSAL"].tolist() if s}) if not df.empty else []
    nombres = [s for s in sucursales if s] or presentes
    filas = []
    for nombre in nombres:
        sub = df[df["SUCURSAL"] == nombre] if not df.empty else df
        actual = _recorte(sub, periodo, False)
        sombra = _recorte(sub, periodo, True)
        neto = float(actual["NETO"].sum()) if not actual.empty else 0.0
        ant = float(sombra["NETO"].sum()) if not sombra.empty else 0.0
        filas.append(
            {
                "sucursal": nombre,
                "neto": int(round(neto)),
                "neto_sombra": int(round(ant)),
                "var_pesos": int(round(neto - ant)),
                "var_pct": _var_pct(neto, ant),
            }
        )
    filas.sort(key=lambda r: r["neto"], reverse=True)
    return filas


def _celda_prod(neto: float, cantidad: float) -> dict:
    return {"neto": int(round(neto)), "cantidad": cantidad, "precio": _precio(neto, cantidad)}


def _matriz_productos(df: pd.DataFrame, periodo: dict, sucursales: Sequence[str], limite: int = 40) -> dict:
    presentes = sorted({s for s in df["SUCURSAL"].tolist() if s}) if not df.empty else []
    columnas = [s for s in sucursales if s] or presentes
    sem = _recorte(df, periodo, False)
    sombra = _recorte(df, periodo, True)
    etiqueta = periodo.get("etiqueta") or ""
    anio = periodo["inicio"].year
    anio_ant = anio - 1
    grupos = columnas + ["Total"]
    vacio = {"etiqueta": etiqueta, "anio": anio, "anio_anterior": anio_ant, "grupos": grupos, "familias": [], "filas": []}
    if sem.empty:
        return vacio
    ranking = sem.groupby("DESCRIPCION")["NETO"].sum().sort_values(ascending=False)
    filas = []
    for producto in ranking.index:
        sub = sem[sem["DESCRIPCION"] == producto]
        ant = sombra[sombra["DESCRIPCION"] == producto] if not sombra.empty else sombra
        pares = []
        for suc in columnas:
            trozo = sub[sub["SUCURSAL"] == suc]
            previo = ant[ant["SUCURSAL"] == suc] if not ant.empty else ant
            neto = float(trozo["NETO"].sum()) if not trozo.empty else 0.0
            cant = float(trozo["CANTIDAD"].sum()) if not trozo.empty else 0.0
            neto_ant = float(previo["NETO"].sum()) if not previo.empty else 0.0
            cant_ant = float(previo["CANTIDAD"].sum()) if not previo.empty else 0.0
            pares.append({"actual": _celda_prod(neto, cant), "anterior": _celda_prod(neto_ant, cant_ant)})
        neto = float(sub["NETO"].sum())
        cant = float(sub["CANTIDAD"].sum())
        neto_ant = float(ant["NETO"].sum()) if not ant.empty else 0.0
        cant_ant = float(ant["CANTIDAD"].sum()) if not ant.empty else 0.0
        pares.append({"actual": _celda_prod(neto, cant), "anterior": _celda_prod(neto_ant, cant_ant)})
        filas.append({"producto": str(producto), "familia": str(sub["FAMILIA"].iloc[0] if len(sub) else ""), "pares": pares})
    por_familia: dict = {}
    for fila in filas:
        por_familia.setdefault(fila["familia"] or "Sin familia", []).append(fila)
    orden = sorted(por_familia, key=lambda fam: sum(p["pares"][-1]["actual"]["neto"] for p in por_familia[fam]), reverse=True)
    familias = [{"familia": fam, "filas": por_familia[fam]} for fam in orden]
    return {
        "etiqueta": etiqueta,
        "anio": anio,
        "anio_anterior": anio_ant,
        "grupos": grupos,
        "familias": familias,
        "filas": filas,
    }


def calcular_comparativo(
    empresa: str,
    corte: str,
    vista: str,
    sucursales: Sequence[str],
    familias: Sequence[str],
    nombre: str = "",
    familias_ficha: Optional[Sequence[str]] = None,
    periodo_num: Optional[int] = None,
    periodo_anio: Optional[int] = None,
) -> dict:
    if periodo_num and periodo_anio:
        if corte == "semanal":
            ancla = date.fromisocalendar(int(periodo_anio), int(periodo_num), 4)
        else:
            ancla = _fin_mes(int(periodo_anio), int(periodo_num))
    else:
        ancla = ancla_datos(empresa)
    periodos = armar_periodos(corte, ancla, hoy_chile())
    df = _cargar_lineas(empresa, periodos)
    if familias and not df.empty:
        pedidas = {str(f).strip() for f in familias if str(f).strip()}
        df = df[df["FAMILIA"].isin(pedidas)].copy()
    base = df
    if sucursales and not df.empty:
        base = df[df["SUCURSAL"].isin(list(sucursales))].copy()
    incompleto = next((p["etiqueta"] for p in periodos if p["incompleto"]), "")
    ultimo = periodos[-1]
    semana = _recorte(base, ultimo, False)
    etiqueta_periodo = "Última semana" if corte == "semanal" else "Último mes"
    return {
        "nombre": nombre,
        "empresa": empresa,
        "corte": corte,
        "vista": vista,
        "sucursales": list(sucursales),
        "familias": list(familias),
        "familias_ficha": list(familias_ficha or []),
        "ancla": ancla.isoformat(),
        "periodo_incompleto": incompleto,
        "etiqueta_macro": f"{etiqueta_periodo} {ultimo['etiqueta']}",
        "semana": {
            "etiqueta": ultimo["etiqueta"],
            "neto": int(round(float(semana["NETO"].sum()))) if not semana.empty else 0,
            "ticket": _ticket(semana),
            "por_sucursal": _partes(semana, "SUCURSAL"),
            "por_familia": _partes(semana, "FAMILIA"),
            "fichas": _fichas_familia(semana, familias_ficha or []),
        },
        "comparativo_semana": _comparativo_sucursales(base, ultimo, sucursales),
        "periodos": [
            {
                "etiqueta": p["etiqueta"],
                "etiqueta_sombra": p["etiqueta_sombra"],
                "inicio": p["inicio"].isoformat(),
                "fin": p["fin"].isoformat(),
                "incompleto": p["incompleto"],
            }
            for p in periodos
        ],
        "bloques": _bloques(base, "ambos", sucursales, periodos),
        "matriz": _matriz_productos(base, ultimo, sucursales),
    }
