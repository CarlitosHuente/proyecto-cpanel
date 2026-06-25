"""Datos para vista imprimir factura DespachoWeb."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def _fmt_fecha_larga(val) -> str:
    if val is None:
        return ""
    meses = (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    )
    if isinstance(val, datetime):
        d = val.date()
    elif isinstance(val, date):
        d = val
    else:
        s = str(val)[:10]
        try:
            d = date.fromisoformat(s)
        except ValueError:
            return s
    return f"{meses[d.month - 1]} {d.day}, {d.year}"


def preparar_factura_impresion(orden: dict, detalle: list[dict]) -> dict[str, Any]:
    """Arma contexto Jinja similar al PDF Huentelauquen."""
    lineas = []
    subtotal = 0
    envio_total = 0
    for ln in detalle or []:
        producto = (ln.get("producto") or "").strip()
        cantidad = float(ln.get("cantidad") or 1)
        total = int(ln.get("total") or 0)
        row = {
            "producto": producto,
            "cantidad": cantidad,
            "total": total,
            "sku": ln.get("sku"),
        }
        if producto.lower() == "envío" or producto.lower() == "envio":
            envio_total += total
        else:
            subtotal += total
        lineas.append(row)

    if subtotal == 0 and envio_total == 0:
        subtotal = sum(int(ln.get("total") or 0) for ln in detalle or [])

    total_general = subtotal + envio_total
    fecha_oc = orden.get("fecha_oc")
    return {
        "marca": "Huentelauquen",
        "titulo": "FACTURA",
        "cliente": orden.get("cliente") or "",
        "fecha_factura": _fmt_fecha_larga(fecha_oc),
        "fecha_pedido": _fmt_fecha_larga(fecha_oc),
        "n_orden": orden.get("n_orden") or "",
        "direccion": orden.get("direccion") or "",
        "comuna": orden.get("comuna") or "",
        "email": orden.get("email") or "",
        "celular": orden.get("celular") or "",
        "metodo_pago": "Webpay Plus",
        "lineas": lineas,
        "subtotal": subtotal,
        "envio_total": envio_total,
        "total": total_general,
        "estado": orden.get("estado") or "",
    }
