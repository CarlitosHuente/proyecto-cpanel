"""Periodo YYYY-MM a partir del mayor contable (Costeo, Prorrateos)."""
from datetime import datetime

import pandas as pd

from utils.sheet_cache import obtener_datos


def periodos_con_movimiento_mayor(df_mayor=None):
    """YYYY-MM con movimiento, de más antiguo a más reciente."""
    if df_mayor is None:
        df_mayor = obtener_datos("mayor")
    if df_mayor is None or getattr(df_mayor, "empty", True) or "FECHA" not in df_mayor.columns:
        return []
    fechas = pd.to_datetime(df_mayor["FECHA"], errors="coerce").dropna()
    if fechas.empty:
        return []
    return sorted(fechas.dt.strftime("%Y-%m").unique().tolist())


def periodo_predeterminado_mayor(pedido=None, df_mayor=None):
    """Si el usuario eligió mes, se respeta. Si no, el más reciente del mayor."""
    pedido = (pedido or "").strip()
    if pedido:
        return pedido
    periodos = periodos_con_movimiento_mayor(df_mayor)
    if periodos:
        return periodos[-1]
    return datetime.now().strftime("%Y-%m")
