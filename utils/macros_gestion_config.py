"""
Configuración de macros de gestión → líneas del P&L.

Seguridad en producción: si no existe `macros_gestion.json` o `activo` es false,
el informe sigue usando ESTRUCTURA_GESTION legacy (mismo comportamiento de siempre).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

MACROS_GESTION_FILENAME = "macros_gestion.json"

SECCIONES_PL: List[dict] = [
    {"id": "ingresos_brutos", "label": "Ingresos / ventas brutas", "linea_pl": "ingresos_op"},
    {"id": "costo_directo", "label": "Costo directo y comisiones", "linea_pl": "costo_directo"},
    {"id": "costos_fijos", "label": "Gastos fijos locales", "linea_pl": "costos_fijos"},
    {"id": "gastos_adm", "label": "Gastos de administración y ventas", "linea_pl": "gastos_adm"},
    {"id": "no_op", "label": "Ingresos / egresos no operacionales", "linea_pl": "no_op"},
    {"id": "otros", "label": "Sin clasificar / otros", "linea_pl": "otros"},
]

SECCION_PL_A_LINEA = {s["id"]: s["linea_pl"] for s in SECCIONES_PL}

DEFAULT_MACROS: List[dict] = [
    {
        "nombre": "Ingresos Venta",
        "seccion_pl": "ingresos_brutos",
        "orden": 10,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Ingresos Operacionales",
        "seccion_pl": "ingresos_brutos",
        "orden": 20,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Costo Venta",
        "seccion_pl": "costo_directo",
        "orden": 30,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Costos de Explotación",
        "seccion_pl": "costos_fijos",
        "orden": 40,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Gastos de Administración y Ventas",
        "seccion_pl": "gastos_adm",
        "orden": 50,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Ingresos No Operacionales",
        "seccion_pl": "no_op",
        "orden": 60,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Otros",
        "seccion_pl": "otros",
        "orden": 70,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Sin Clasificar",
        "seccion_pl": "otros",
        "orden": 80,
        "partir_por_tipo": False,
        "activo": True,
    },
]

PRESET_SEPARAR_VENTAS_COSTOS: List[dict] = [
    {
        "nombre": "Ingresos Venta",
        "seccion_pl": "ingresos_brutos",
        "orden": 10,
        "partir_por_tipo": True,
        "activo": True,
    },
    {
        "nombre": "Ingresos Operacionales",
        "seccion_pl": "ingresos_brutos",
        "orden": 20,
        "partir_por_tipo": True,
        "activo": True,
    },
    {
        "nombre": "Costo Venta",
        "seccion_pl": "costo_directo",
        "orden": 30,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Costos de Explotación",
        "seccion_pl": "costos_fijos",
        "orden": 40,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Gastos de Administración y Ventas",
        "seccion_pl": "gastos_adm",
        "orden": 50,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Ingresos No Operacionales",
        "seccion_pl": "no_op",
        "orden": 60,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Otros",
        "seccion_pl": "otros",
        "orden": 70,
        "partir_por_tipo": False,
        "activo": True,
    },
    {
        "nombre": "Sin Clasificar",
        "seccion_pl": "otros",
        "orden": 80,
        "partir_por_tipo": False,
        "activo": True,
    },
]


def config_default() -> dict:
    return {"activo": False, "macros": deepcopy(DEFAULT_MACROS)}


def preparar_macros_config(data: Optional[dict], grupos_clasif: Optional[List[dict]] = None) -> dict:
    """Normaliza config y agrega macros huérfanas usadas en grupos pero no listadas."""
    base = config_default()
    if data:
        base["activo"] = bool(data.get("activo", False))
        if data.get("macros"):
            base["macros"] = []
            vistos = set()
            for m in data["macros"]:
                nombre = (m.get("nombre") or "").strip()
                if not nombre or nombre in vistos:
                    continue
                vistos.add(nombre)
                base["macros"].append(_normalizar_macro(m))
    nombres_cfg = {m["nombre"] for m in base["macros"]}
    max_orden = max((m.get("orden", 0) for m in base["macros"]), default=0)
    for g in grupos_clasif or []:
        nombre = (g.get("macro_categoria") or "").strip()
        if not nombre or nombre in nombres_cfg:
            continue
        max_orden += 10
        base["macros"].append(
            {
                "nombre": nombre,
                "seccion_pl": _inferir_seccion_por_nombre(nombre),
                "orden": max_orden,
                "partir_por_tipo": False,
                "activo": True,
            }
        )
        nombres_cfg.add(nombre)
    base["macros"].sort(key=lambda x: (x.get("orden", 999), x["nombre"]))
    return base


def _normalizar_macro(m: dict) -> dict:
    sec = m.get("seccion_pl") or _inferir_seccion_por_nombre(m.get("nombre", ""))
    if sec not in SECCION_PL_A_LINEA:
        sec = "otros"
    return {
        "nombre": (m.get("nombre") or "").strip(),
        "seccion_pl": sec,
        "orden": int(m.get("orden", 999)),
        "partir_por_tipo": bool(m.get("partir_por_tipo", False)),
        "activo": bool(m.get("activo", True)),
    }


def _inferir_seccion_por_nombre(nombre: str) -> str:
    n = (nombre or "").lower()
    if "costo venta" in n or "comision" in n:
        return "costo_directo"
    if "ingreso" in n and "no oper" in n:
        return "no_op"
    if "ingreso" in n or "venta" in n:
        return "ingresos_brutos"
    if "explot" in n or "fijo" in n:
        return "costos_fijos"
    if "admin" in n or "ventas" in n:
        return "gastos_adm"
    if "sin clasificar" in n or n == "otros":
        return "otros"
    return "otros"


def nombres_macros_para_ui(cfg: dict) -> List[str]:
    return [m["nombre"] for m in cfg.get("macros", []) if m.get("activo", True)]


def meta_por_nombre(cfg: dict) -> Dict[str, dict]:
    return {m["nombre"]: m for m in cfg.get("macros", []) if m.get("nombre")}


def estructura_gestion_desde_config(cfg: dict) -> List[dict]:
    """Arma la estructura P&L según seccion_pl de cada macro activa."""
    fuentes_por_linea: Dict[str, List[str]] = {}
    for m in cfg.get("macros", []):
        if not m.get("activo", True):
            continue
        linea = SECCION_PL_A_LINEA.get(m.get("seccion_pl"))
        if not linea:
            continue
        fuentes_por_linea.setdefault(linea, []).append(m["nombre"])

    def _f(linea: str, legacy: List[str]) -> List[str]:
        return fuentes_por_linea.get(linea) or legacy

    return [
        {
            "id": "ingresos_op",
            "titulo": "INGRESOS DE EXPLOTACIÓN",
            "tipo": "macro",
            "fuente": _f("ingresos_op", ["Ingresos Operacionales", "Ingresos Venta"]),
        },
        {
            "id": "costo_directo",
            "titulo": "COSTO DIRECTO (COSTO DE VENTA)",
            "tipo": "macro",
            "fuente": _f("costo_directo", ["Costo Venta"]),
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
            "fuente": _f("costos_fijos", ["Costos de Explotación"]),
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
            "fuente": _f("gastos_adm", ["Gastos de Administración y Ventas"]),
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
            "fuente": _f("no_op", ["Ingresos No Operacionales"]),
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
            "fuente": _f("otros", ["Sin Clasificar", "Otros"]),
        },
    ]


def resolver_estructura_reporte(
    cfg: Optional[dict],
) -> Tuple[List[dict], Dict[str, dict], bool]:
    """
    Retorna (estructura, meta_por_nombre, config_activa).
    Si config no activa → estructura legacy sin meta (comportamiento anterior).
    """
    from utils.gestion_estructura import ESTRUCTURA_GESTION

    if not cfg or not cfg.get("activo"):
        return ESTRUCTURA_GESTION, {}, False
    return estructura_gestion_desde_config(cfg), meta_por_nombre(cfg), True
