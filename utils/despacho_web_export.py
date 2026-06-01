"""Exportación Excel — DespachoWeb resumen / detalle por producto."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

import pandas as pd

from utils.formato_fecha import fecha_ddmmaaaa


def _precio_unit(total, cantidad) -> int:
    cant = float(cantidad or 0)
    if not cant:
        return 0
    return round(int(total or 0) / cant)


def generar_excel_resumen_productos(
    resumen: list[dict],
    lineas: list[dict],
    filtros: Optional[dict[str, str]] = None,
) -> io.BytesIO:
    filtros = filtros or {}

    filas_resumen = []
    for r in resumen:
        filas_resumen.append(
            {
                "Producto": r.get("producto") or "",
                "Cantidad total": float(r.get("cantidad_total") or 0),
                "Monto total CLP": int(r.get("monto_total") or 0),
                "Precio prom. CLP": int(r.get("precio_prom") or 0),
                "N° pedidos": int(r.get("num_pedidos") or 0),
            }
        )
    df_resumen = pd.DataFrame(filas_resumen)

    filas_det = []
    for ln in lineas:
        cant = float(ln.get("cantidad") or 0)
        total = int(ln.get("total") or 0)
        filas_det.append(
            {
                "ID línea": ln.get("detalle_id"),
                "Producto": ln.get("producto") or "",
                "Cantidad": cant,
                "Total línea CLP": total,
                "Precio unit. CLP": _precio_unit(total, cant),
                "Estado línea": ln.get("estado_linea") or "",
                "N° Orden": ln.get("n_orden") or "",
                "Fecha OC": fecha_ddmmaaaa(ln.get("fecha_oc")),
                "Cliente": ln.get("cliente") or "",
                "Celular": ln.get("celular") or "",
                "Email": ln.get("email") or "",
                "Estado orden": ln.get("estado_orden") or "",
                "Transporte": ln.get("transporte") or "",
                "Comuna": ln.get("comuna") or "",
                "Dirección": ln.get("direccion") or "",
                "Fecha estado orden": fecha_ddmmaaaa(ln.get("fecha_estado"), con_hora=True),
                "Observaciones orden": ln.get("obs") or "",
                "URL": ln.get("url") or "",
                "Creado por": ln.get("creado_por") or "",
                "Creado at": fecha_ddmmaaaa(ln.get("creado_at"), con_hora=True),
            }
        )
    df_detalle = pd.DataFrame(filas_det)

    filas_filtro = []
    for k, v in filtros.items():
        valor = v or "(todos)"
        if k in ("Desde", "Hasta") and v:
            valor = fecha_ddmmaaaa(v) or valor
        filas_filtro.append({"Parámetro": k, "Valor": valor})
    df_filtros = pd.DataFrame(filas_filtro)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_resumen.to_excel(writer, sheet_name="Resumen", index=False)
        df_detalle.to_excel(writer, sheet_name="Detalle_lineas", index=False)
        df_filtros.to_excel(writer, sheet_name="Filtros", index=False)
    buf.seek(0)
    return buf


def nombre_archivo_export() -> str:
    hoy = datetime.now().strftime("%d%m%Y_%H%M")
    return f"despacho_web_productos_{hoy}.xlsx"


def respuesta_excel(buf: io.BytesIO, filename: str):
    """Response binaria compatible con WSGI/cPanel (evita fallos de send_file+BytesIO)."""
    from flask import Response
    from werkzeug.utils import secure_filename

    safe = secure_filename(filename) or "despacho_web_export.xlsx"
    return Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )
