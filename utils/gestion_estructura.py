"""
Estado de resultados de gestión: estructura P&L compartida (dashboard, informe, comparativo).
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

MES_LABELS_CORTOS = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]

ESTRUCTURA_GESTION: List[dict] = [
    {
        "id": "ingresos_op",
        "titulo": "INGRESOS DE EXPLOTACIÓN",
        "tipo": "macro",
        "fuente": ["Ingresos Operacionales", "Ingresos Venta"],
    },
    {
        "id": "costo_directo",
        "titulo": "COSTO DIRECTO (COSTO DE VENTA)",
        "tipo": "macro",
        "fuente": ["Costo Venta"],
    },
    {
        "id": "margen_op",
        "titulo": "MARGEN OPERACIONAL (BRUTO)",
        "tipo": "calculo",
        "color": "primary",
        "operacion": ["ingresos_op", "costo_directo"],
    },
    {
        "id": "costos_fijos",
        "titulo": "GASTOS FIJOS LOCALES",
        "tipo": "macro",
        "fuente": ["Costos de Explotación"],
    },
    {
        "id": "margen",
        "titulo": "MARGEN DE EXPLOTACIÓN",
        "tipo": "calculo",
        "color": "warning",
        "operacion": ["margen_op", "costos_fijos"],
    },
    {
        "id": "gastos_adm",
        "titulo": "GASTOS DE ADMINISTRACIÓN Y VENTAS",
        "tipo": "macro",
        "fuente": ["Gastos de Administración y Ventas"],
    },
    {
        "id": "res_op",
        "titulo": "RESULTADO OPERACIONAL",
        "tipo": "calculo",
        "color": "info",
        "operacion": ["margen", "gastos_adm"],
    },
    {
        "id": "no_op",
        "titulo": "INGRESOS Y EGRESOS NO OPERACIONALES",
        "tipo": "macro",
        "fuente": ["Ingresos No Operacionales"],
    },
    {
        "id": "res_final",
        "titulo": "RESULTADO ANTES DE IMPTO",
        "tipo": "calculo",
        "color": "success",
        "operacion": ["res_op", "no_op"],
    },
    {
        "id": "otros",
        "titulo": "SIN CLASIFICAR / OTROS",
        "tipo": "macro",
        "fuente": ["Sin Clasificar", "Otros"],
    },
]

# Filas del resumen % en dashboard (ids de ESTRUCTURA_GESTION)
RESUMEN_PCT_IDS = [
    "ingresos_op",
    "costo_directo",
    "margen_op",
    "costos_fijos",
    "margen",
    "gastos_adm",
    "res_op",
    "res_final",
]


def switches_desde_request(form_enviado: bool, args) -> tuple[bool, bool]:
    if form_enviado:
        return args.get("distribuir_sg") == "on", args.get("ajuste_fabrica") == "on"
    return True, True


def armar_macros_data_cc(df_final, data_clasif: dict, columnas_cc: List[str]) -> dict:
    """Matriz cuenta → montos por centro de costo (un periodo o varios en df_final)."""
    matriz = {}
    for _, row in df_final.iterrows():
        cta = row["CUENTA"]
        cc = row["CENTRO COSTO"]
        if cta not in matriz:
            matriz[cta] = {"nombre": row["NOMBRE"], "montos": {}}
        matriz[cta]["montos"][cc] = matriz[cta]["montos"].get(cc, 0) + row["SALDO_REAL"]

    macros_data = {}
    for grp in data_clasif.get("grupos", []):
        m = grp.get("macro_categoria", "Otros")
        if m not in macros_data:
            macros_data[m] = {"grupos": [], "totales_cc": {c: 0.0 for c in columnas_cc}}
        fg = {
            "nombre": grp["nombre"],
            "tipo": grp["tipo"],
            "totales_cc": {c: 0.0 for c in columnas_cc},
            "detalle_cuentas": [],
        }
        for cta_id in grp["cuentas"]:
            cid = str(cta_id)
            if cid not in matriz:
                continue
            data_cta = matriz[cid]
            for cc, val in data_cta["montos"].items():
                if cc not in fg["totales_cc"]:
                    fg["totales_cc"][cc] = 0.0
                fg["totales_cc"][cc] += val
                if cc not in macros_data[m]["totales_cc"]:
                    macros_data[m]["totales_cc"][cc] = 0.0
                macros_data[m]["totales_cc"][cc] += val
            fg["detalle_cuentas"].append(
                {"codigo": cid, "nombre": data_cta["nombre"], "montos_cc": data_cta["montos"]}
            )
        macros_data[m]["grupos"].append(fg)

    sin_clasif = {"nombre": "Pendientes", "totales_cc": {c: 0.0 for c in columnas_cc}, "detalle_cuentas": []}
    procesadas = {str(c) for g in data_clasif.get("grupos", []) for c in g["cuentas"]}
    hay_pend = False
    for cta, data in matriz.items():
        if cta in procesadas:
            continue
        if sum(abs(v) for v in data["montos"].values()) <= 1:
            continue
        hay_pend = True
        for cc, val in data["montos"].items():
            if cc not in sin_clasif["totales_cc"]:
                sin_clasif["totales_cc"][cc] = 0.0
            sin_clasif["totales_cc"][cc] += val
        sin_clasif["detalle_cuentas"].append(
            {"codigo": cta, "nombre": data["nombre"], "montos_cc": data["montos"]}
        )
    if hay_pend:
        if "Sin Clasificar" not in macros_data:
            macros_data["Sin Clasificar"] = {"grupos": [], "totales_cc": {c: 0.0 for c in columnas_cc}}
        macros_data["Sin Clasificar"]["grupos"].append(sin_clasif)
        for cc in columnas_cc:
            macros_data["Sin Clasificar"]["totales_cc"][cc] = (
                macros_data["Sin Clasificar"]["totales_cc"].get(cc, 0)
                + sin_clasif["totales_cc"].get(cc, 0)
            )
    return macros_data


def _grupos_macro_para_linea(
    macros_data: dict,
    macro_nombre: str,
    linea_id: str,
    macros_meta: Dict[str, dict],
    config_activa: bool,
) -> List[dict]:
    d = macros_data.get(macro_nombre)
    if not d:
        return []
    grupos = d.get("grupos") or []
    if not config_activa:
        return grupos
    meta = macros_meta.get(macro_nombre, {})
    if not meta.get("partir_por_tipo"):
        return grupos
    if linea_id == "ingresos_op":
        return [g for g in grupos if g.get("tipo") == "INGRESO"]
    if linea_id == "costo_directo":
        return [g for g in grupos if g.get("tipo") == "GASTO"]
    return grupos


def _macros_gasto_desde_brutos(macros_meta: Dict[str, dict]) -> List[str]:
    out = []
    for nombre, meta in macros_meta.items():
        if not meta.get("activo", True):
            continue
        if meta.get("seccion_pl") == "ingresos_brutos" and meta.get("partir_por_tipo"):
            out.append(nombre)
    return out


def _incorporar_grupos_en_fila(
    f: dict,
    grupos: List[dict],
    columnas: List[str],
    total_key: str,
    vistos: Optional[set] = None,
) -> None:
    if vistos is None:
        vistos = set()
    for g in grupos:
        clave = g.get("nombre") or ""
        if clave in vistos:
            continue
        vistos.add(clave)
        f["grupos"].append(g)
        totales = g.get(total_key) or g.get("totales_cc") or g.get("totales_col") or {}
        for col in columnas:
            f[total_key][col] += float(totales.get(col, 0))


def armar_reporte_gestion(
    macros_data: dict,
    columnas: List[str],
    *,
    estructura: Optional[List[dict]] = None,
    macros_meta: Optional[Dict[str, dict]] = None,
    config_activa: bool = False,
    total_key: str = "totales_cc",
) -> List[dict]:
    estructura = estructura or ESTRUCTURA_GESTION
    macros_meta = macros_meta or {}
    reporte = []
    cache: Dict[str, Dict[str, float]] = {}
    macros_gasto_brutos = _macros_gasto_desde_brutos(macros_meta) if config_activa else []

    for l in estructura:
        f = {
            "id": l["id"],
            "titulo": l["titulo"],
            "tipo": l["tipo"],
            "color": l.get("color", "secondary"),
            "grupos": [],
            total_key: {c: 0.0 for c in columnas},
        }
        if l["tipo"] == "macro":
            enc = False
            vistos: set = set()
            for src in l["fuente"]:
                if src not in macros_data:
                    continue
                grupos = _grupos_macro_para_linea(
                    macros_data, src, l["id"], macros_meta, config_activa
                )
                if grupos:
                    enc = True
                _incorporar_grupos_en_fila(f, grupos, columnas, total_key, vistos)
            if l["id"] == "costo_directo" and config_activa:
                for src in macros_gasto_brutos:
                    if src in l["fuente"]:
                        continue
                    grupos = _grupos_macro_para_linea(
                        macros_data, src, "costo_directo", macros_meta, config_activa
                    )
                    if grupos:
                        enc = True
                    _incorporar_grupos_en_fila(f, grupos, columnas, total_key, vistos)
            cache[l["id"]] = dict(f[total_key])
            if enc or l["id"] == "otros":
                reporte.append(f)
        elif l["tipo"] == "calculo":
            for op in l["operacion"]:
                tot = cache.get(op, {})
                for col in columnas:
                    f[total_key][col] += tot.get(col, 0)
            cache[l["id"]] = dict(f[total_key])
            reporte.append(f)
    return reporte


def total_alcance(totales_cc: dict, alcance_cc: str) -> float:
    """Suma columnas según Total Empresa o un centro de costo."""
    if alcance_cc and alcance_cc != "Total Empresa":
        return float(totales_cc.get(alcance_cc, 0))
    return float(sum(totales_cc.values()))


def totales_empresa_por_seccion(reporte: List[dict]) -> Dict[str, float]:
    return {s["id"]: float(sum(s["totales_cc"].values())) for s in reporte}


def pct_sobre_ventas(monto: float, ventas: float) -> Optional[float]:
    if ventas is None or ventas == 0:
        return None
    return float(
        (Decimal(str(monto)) / Decimal(str(ventas)) * Decimal("100")).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
    )


def ventas_brutas_por_cc(df, columnas_cc: List[str]) -> Dict[str, float]:
    """Ventas brutas = suma cuentas 4xx (misma base que el gráfico de tendencia)."""
    out: Dict[str, float] = {cc: 0.0 for cc in columnas_cc}
    if df is None or getattr(df, "empty", True):
        out["__TOTAL__"] = 0.0
        return out
    ing = df[df["CUENTA"].astype(str).str.startswith("4")]
    for cc in columnas_cc:
        out[cc] = float(ing[ing["CENTRO COSTO"] == cc]["SALDO_REAL"].sum())
    out["__TOTAL__"] = float(ing["SALDO_REAL"].sum())
    return out


def ventas_brutas_alcance(ventas_cc: Dict[str, float], alcance_cc: str) -> float:
    if alcance_cc and alcance_cc != "Total Empresa":
        return float(ventas_cc.get(alcance_cc, 0))
    return float(ventas_cc.get("__TOTAL__", 0))


def ventas_por_cc(reporte: List[dict], columnas_cc: List[str], ventas_cc: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Base % s/ ventas: brutas (4xx) si se pasa ventas_cc; si no, ingresos_op (legacy)."""
    if ventas_cc is not None:
        return dict(ventas_cc)
    ing = next((s for s in reporte if s["id"] == "ingresos_op"), None)
    if not ing:
        return {cc: 0.0 for cc in columnas_cc}
    out = {}
    for cc in columnas_cc:
        out[cc] = float(ing["totales_cc"].get(cc, 0))
    out["__TOTAL__"] = float(sum(ing["totales_cc"].values()))
    return out


def resumen_pct_dashboard(
    reporte: List[dict], alcance_cc: str, ventas_cc: Optional[Dict[str, float]] = None
) -> List[dict]:
    """Filas para el bloque resumen % del dashboard (% s/ ventas brutas)."""
    if ventas_cc is not None:
        ventas = ventas_brutas_alcance(ventas_cc, alcance_cc)
    else:
        ventas = total_alcance(
            next(s["totales_cc"] for s in reporte if s["id"] == "ingresos_op"), alcance_cc
        )
    filas = []
    for sid in RESUMEN_PCT_IDS:
        sec = next((s for s in reporte if s["id"] == sid), None)
        if not sec:
            continue
        monto = total_alcance(sec["totales_cc"], alcance_cc)
        filas.append(
            {
                "id": sid,
                "titulo": sec["titulo"],
                "tipo": sec["tipo"],
                "color": sec.get("color"),
                "monto": monto,
                "pct": pct_sobre_ventas(monto, ventas),
                "es_ventas": sid == "ingresos_op",
            }
        )
    return filas


def kpis_desde_reporte(
    reporte: List[dict], alcance_cc: str, ventas_cc: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """KPIs dashboard: ventas brutas (4xx) + márgenes s/ esa base."""
    t = {s["id"]: total_alcance(s["totales_cc"], alcance_cc) for s in reporte}
    if ventas_cc is not None:
        ventas = ventas_brutas_alcance(ventas_cc, alcance_cc)
    else:
        ventas = t.get("ingresos_op", 0)
    res_final = t.get("res_final", 0)
    margen_bruto = t.get("margen_op", 0)
    res_op = t.get("res_op", 0)
    gastos_estructura = ventas - res_final if ventas or res_final else 0
    return {
        "venta": ventas,
        "margen_bruto": margen_bruto,
        "margen_bruto_pct": pct_sobre_ventas(margen_bruto, ventas) or 0.0,
        "resultado_op": res_op,
        "resultado_op_pct": pct_sobre_ventas(res_op, ventas) or 0.0,
        "resultado": res_final,
        "costo_total": abs(gastos_estructura),
    }


def ranking_cc_resultado_op(
    reporte: List[dict], columnas_cc: List[str], ventas_cc: Dict[str, float]
) -> Dict[str, Any]:
    """Comparativo por centro de costo: resultado operacional del mes."""
    sec = next((s for s in reporte if s["id"] == "res_op"), None)
    vacio: Dict[str, Any] = {
        "filas": [],
        "total": 0.0,
        "ventas_empresa": 0.0,
        "res_op_pct_empresa": None,
        "mejor": None,
        "peor": None,
    }
    if not sec:
        return vacio
    total = float(sum(sec["totales_cc"].values()))
    filas = []
    for cc in columnas_cc:
        monto = float(sec["totales_cc"].get(cc, 0))
        v = float(ventas_cc.get(cc, 0))
        filas.append(
            {
                "cc": cc,
                "resultado_op": monto,
                "ventas": v,
                "resultado_op_pct": pct_sobre_ventas(monto, v),
                "participacion_pct": pct_sobre_ventas(monto, total) if total else None,
            }
        )
    filas.sort(key=lambda x: x["resultado_op"], reverse=True)
    activas = [f for f in filas if abs(f["resultado_op"]) > 1 or abs(f["ventas"]) > 1]
    ventas_empresa = float(ventas_cc.get("__TOTAL__", 0))
    return {
        "filas": filas,
        "total": total,
        "ventas_empresa": ventas_empresa,
        "res_op_pct_empresa": pct_sobre_ventas(total, ventas_empresa),
        "mejor": activas[0] if activas else None,
        "peor": activas[-1] if activas else None,
    }


def _periodo_mas_meses(periodo: str, meses: int) -> str:
    y, m = map(int, periodo.split("-"))
    m += meses
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _kpis_vacios() -> Dict[str, Any]:
    return {
        "venta": 0.0,
        "margen_bruto": 0.0,
        "margen_bruto_pct": 0.0,
        "resultado_op": 0.0,
        "resultado_op_pct": 0.0,
        "resultado": 0.0,
        "costo_total": 0.0,
    }


def _var_pct_monto(act: float, ant: float, *, abs_den: bool = False) -> float:
    if abs_den:
        return ((act - ant) / abs(ant) * 100) if abs(ant) > 0 else 0.0
    return ((act - ant) / ant * 100) if ant > 0 else 0.0


def serie_kpis_mensual(
    df_final,
    data_clasif: dict,
    columnas_cc: List[str],
    alcance_cc: str,
    periodo_seleccionado: str,
    *,
    armar_reporte: Optional[Callable[[Any, List[str]], List[dict]]] = None,
) -> Dict[str, Any]:
    """Serie ene–dic (YoY) + mes siguiente para drill-down de cards del dashboard.

    ``armar_reporte(macros_data, columnas)`` debe devolver el P&L de gestión
    (p. ej. el wrapper de contab que aplica macros_gestion.json).
    """
    if armar_reporte is None:
        armar_reporte = lambda macros, cols: armar_reporte_gestion(macros, cols)

    anio_act = int(periodo_seleccionado[:4])
    anio_ant = anio_act - 1
    periodo_proximo = _periodo_mas_meses(periodo_seleccionado, 1)

    cache: Dict[str, Tuple[bool, Dict[str, Any]]] = {}

    def kpis_periodo(periodo: str) -> Tuple[bool, Dict[str, Any]]:
        if periodo in cache:
            return cache[periodo]
        if df_final is None or getattr(df_final, "empty", True):
            vacio = (False, _kpis_vacios())
            cache[periodo] = vacio
            return vacio
        df_p = df_final[df_final["PERIODO_STR"] == periodo]
        if df_p.empty:
            vacio = (False, _kpis_vacios())
            cache[periodo] = vacio
            return vacio
        macros = armar_macros_data_cc(df_p, data_clasif, columnas_cc)
        reporte = armar_reporte(macros, columnas_cc)
        ventas_cc = ventas_brutas_por_cc(df_p, columnas_cc)
        kpis = kpis_desde_reporte(reporte, alcance_cc, ventas_cc)
        out = (True, kpis)
        cache[periodo] = out
        return out

    periodos_filas: List[Tuple[int, str, str, str]] = []
    for mes in range(1, 13):
        per_act = f"{anio_act:04d}-{mes:02d}"
        per_ant = f"{anio_ant:04d}-{mes:02d}"
        periodos_filas.append((mes, MES_LABELS_CORTOS[mes - 1], per_act, per_ant))

    anio_prox = int(periodo_proximo[:4])
    if anio_prox > anio_act:
        mes_prox = int(periodo_proximo[5:7])
        periodos_filas.append(
            (
                mes_prox,
                f"{MES_LABELS_CORTOS[mes_prox - 1]} {anio_prox}",
                periodo_proximo,
                _periodo_mas_meses(periodo_proximo, -12),
            )
        )

    filas: List[dict] = []
    for mes, label, per_act, per_ant in periodos_filas:
        tiene_act, k_act = kpis_periodo(per_act)
        _, k_ant = kpis_periodo(per_ant)
        es_seleccionado = per_act == periodo_seleccionado
        es_proximo = per_act == periodo_proximo

        # Mes siguiente sin mayor: layout de referencia (año ant. sí, actual —).
        if es_proximo and not tiene_act:
            mostrar_act = False
        else:
            mostrar_act = tiene_act

        venta_act = float(k_act["venta"]) if mostrar_act else None
        venta_ant = float(k_ant["venta"])
        mb_act = float(k_act["margen_bruto_pct"]) if mostrar_act else None
        mb_ant = float(k_ant["margen_bruto_pct"])
        ro_act = float(k_act["resultado_op_pct"]) if mostrar_act else None
        ro_ant = float(k_ant["resultado_op_pct"])
        res_act = float(k_act["resultado"]) if mostrar_act else None
        res_ant = float(k_ant["resultado"])

        filas.append(
            {
                "mes": mes,
                "label": label,
                "periodo_act": per_act,
                "periodo_ant": per_ant,
                "es_seleccionado": es_seleccionado,
                "es_proximo": es_proximo,
                "tiene_dato_act": mostrar_act,
                "venta_act": venta_act,
                "venta_ant": venta_ant,
                "var_venta": (
                    _var_pct_monto(venta_act, venta_ant) if venta_act is not None else None
                ),
                "margen_bruto_pct_act": mb_act,
                "margen_bruto_pct_ant": mb_ant,
                "var_margen_bruto_pp": (mb_act - mb_ant) if mb_act is not None else None,
                "resultado_op_pct_act": ro_act,
                "resultado_op_pct_ant": ro_ant,
                "var_resultado_op_pp": (ro_act - ro_ant) if ro_act is not None else None,
                "resultado_act": res_act,
                "resultado_ant": res_ant,
                "var_resultado": (
                    _var_pct_monto(res_act, res_ant, abs_den=True)
                    if res_act is not None
                    else None
                ),
            }
        )

    return {
        "anio_actual": anio_act,
        "anio_anterior": anio_ant,
        "periodo_seleccionado": periodo_seleccionado,
        "periodo_proximo": periodo_proximo,
        "labels": [f["label"] for f in filas],
        "filas": filas,
    }
