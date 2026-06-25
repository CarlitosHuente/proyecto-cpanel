"""Datos para vista imprimir factura DespachoWeb."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


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


def _calle_y_comuna(direccion: str, comuna: str) -> tuple[str, str]:
    """Evita repetir comuna si ya está en la dirección."""
    direccion = (direccion or "").strip()
    comuna = (comuna or "").strip()
    if not comuna:
        return direccion, ""
    d_low = direccion.lower()
    c_low = comuna.lower()
    if d_low == c_low:
        return direccion, ""
    if c_low in d_low:
        return direccion, ""
    return direccion, comuna


def _es_envio(nombre: str) -> bool:
    return (nombre or "").strip().lower() in ("envío", "envio")


def preparar_factura_impresion(orden: dict, detalle: list[dict]) -> dict[str, Any]:
    """Arma contexto Jinja similar al PDF Huentelauquen."""
    lineas_producto = []
    subtotal = 0
    envio_total = 0
    for ln in detalle or []:
        producto = (ln.get("producto") or "").strip()
        cantidad = float(ln.get("cantidad") or 1)
        total = int(ln.get("total") or 0)
        if _es_envio(producto):
            envio_total += total
            continue
        subtotal += total
        lineas_producto.append(
            {
                "producto": producto,
                "cantidad": cantidad,
                "total": total,
                "sku": ln.get("sku"),
            }
        )

    if subtotal == 0 and envio_total == 0:
        subtotal = sum(int(ln.get("total") or 0) for ln in detalle or [])

    total_general = subtotal + envio_total
    fecha_oc = orden.get("fecha_oc")
    calle, comuna = _calle_y_comuna(
        orden.get("direccion") or "",
        orden.get("comuna") or "",
    )

    return {
        "marca": "Huentelauquen",
        "titulo": "COMPROBANTE DE PEDIDO",
        "tipo_doc": "Pedido web",
        "empresa": {
            "nombre": "Huentelauquen",
            "sitio": "huentelauquen.cl",
            "giro": "Elaboración y comercialización de empanadas",
        },
        "cliente": orden.get("cliente") or "",
        "fecha_factura": _fmt_fecha_larga(fecha_oc),
        "fecha_pedido": _fmt_fecha_larga(fecha_oc),
        "n_orden": orden.get("n_orden") or "",
        "calle": calle,
        "comuna": comuna,
        "email": orden.get("email") or "",
        "celular": orden.get("celular") or "",
        "metodo_pago": "Webpay Plus",
        "lineas": lineas_producto,
        "subtotal": subtotal,
        "envio_total": envio_total,
        "mostrar_envio": envio_total > 0,
        "total": total_general,
        "estado": orden.get("estado") or "",
    }
