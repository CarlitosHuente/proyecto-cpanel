"""
Estado de resultados de gestión: estructura P&L compartida (dashboard, informe, comparativo).
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

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


def armar_reporte_gestion(macros_data: dict, columnas_cc: List[str]) -> List[dict]:
    reporte = []
    cache: Dict[str, Dict[str, float]] = {}
    for l in ESTRUCTURA_GESTION:
        f = {
            "id": l["id"],
            "titulo": l["titulo"],
            "tipo": l["tipo"],
            "color": l.get("color", "secondary"),
            "grupos": [],
            "totales_cc": {c: 0.0 for c in columnas_cc},
        }
        if l["tipo"] == "macro":
            enc = False
            for src in l["fuente"]:
                if src not in macros_data:
                    continue
                d = macros_data[src]
                f["grupos"].extend(d["grupos"])
                for cc in columnas_cc:
                    f["totales_cc"][cc] += d["totales_cc"].get(cc, 0)
                enc = True
            cache[l["id"]] = dict(f["totales_cc"])
            if enc or l["id"] == "otros":
                reporte.append(f)
        elif l["tipo"] == "calculo":
            for op in l["operacion"]:
                tot = cache.get(op, {})
                for cc in columnas_cc:
                    f["totales_cc"][cc] += tot.get(cc, 0)
            cache[l["id"]] = dict(f["totales_cc"])
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


def ventas_por_cc(reporte: List[dict], columnas_cc: List[str]) -> Dict[str, float]:
    ing = next((s for s in reporte if s["id"] == "ingresos_op"), None)
    if not ing:
        return {cc: 0.0 for cc in columnas_cc}
    out = {}
    for cc in columnas_cc:
        out[cc] = float(ing["totales_cc"].get(cc, 0))
    out["__TOTAL__"] = float(sum(ing["totales_cc"].values()))
    return out


def resumen_pct_dashboard(reporte: List[dict], alcance_cc: str) -> List[dict]:
    """Filas para el bloque resumen % del dashboard."""
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


def kpis_desde_reporte(reporte: List[dict], alcance_cc: str) -> Dict[str, Any]:
    """KPIs dashboard alineados a ESTRUCTURA_GESTION."""
    t = {s["id"]: total_alcance(s["totales_cc"], alcance_cc) for s in reporte}
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
