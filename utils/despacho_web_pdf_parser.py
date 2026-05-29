"""Extracción de datos desde factura PDF tienda web Huentelauquen."""
from __future__ import annotations

import io
import re
from datetime import date
from typing import Any, Optional

MESES_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _parse_monto_clp(texto: str) -> int:
    digits = re.sub(r"[^\d]", "", texto or "")
    return int(digits) if digits else 0


def _parse_fecha_es(texto: str) -> Optional[str]:
    """'mayo 11, 2026' → '2026-05-11'."""
    m = re.search(
        r"(\w+)\s+(\d{1,2}),?\s+(\d{4})",
        texto,
        re.IGNORECASE,
    )
    if not m:
        return None
    mes_nombre = m.group(1).lower()
    mes = MESES_ES.get(mes_nombre)
    if not mes:
        return None
    try:
        d = date(int(m.group(3)), mes, int(m.group(2)))
        return d.isoformat()
    except ValueError:
        return None


def _extraer_email(lineas: list[str]) -> Optional[str]:
    for ln in lineas:
        m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", ln)
        if m:
            return m.group(0).strip()
    return None


def _extraer_celular(lineas: list[str]) -> Optional[str]:
    texto = "\n".join(lineas)
    compacto = re.sub(r"[\s.\-()]", "", texto)
    for patron in (
        r"\+569\d{8}",
        r"569\d{8}",
        r"(?<!\d)9\d{8}(?!\d)",
        r"(?<!\d)\d{8}(?!\d)",
    ):
        m = re.search(patron, compacto)
        if m:
            return m.group(0)
    for ln in lineas:
        if "Producto Cantidad" in ln:
            break
        if "@" in ln:
            continue
        compact_ln = re.sub(r"[\s.\-()]", "", ln)
        m = re.search(r"\+569\d{8}", compact_ln)
        if m:
            return m.group(0)
        m = re.search(r"(?<!\d)9\d{8}(?!\d)", compact_ln)
        if m:
            return m.group(0)
        m = re.search(r"(?<!\d)\d{8}(?!\d)", compact_ln)
        if m:
            return m.group(0)
    return None


def _parse_lineas_producto(bloque: list[str]) -> list[dict[str, Any]]:
    lineas: list[dict[str, Any]] = []
    i = 0
    while i < len(bloque):
        ln = bloque[i].strip()
        i += 1
        if not ln or ln.startswith("SKU:") or ln.startswith("Peso:"):
            continue
        ln_low = ln.lower()
        if ln_low.startswith("subtotal"):
            continue
        if ln_low.startswith("envío") or ln_low.startswith("envio"):
            m = re.search(r"\$\s*[\d.]+", ln)
            total = _parse_monto_clp(m.group(0) if m else ln)
            lineas.append(
                {
                    "producto": "Envío",
                    "cantidad": 1,
                    "total": total,
                    "sku": None,
                }
            )
            continue
        if ln_low.startswith("total"):
            break
        m = re.match(
            r"^(.+?)\s+(\d+(?:[.,]\d+)?)\s+\$\s*([\d.]+)\s*$",
            ln,
        )
        if m:
            nombre = m.group(1).strip()
            cantidad = float(m.group(2).replace(",", "."))
            total = _parse_monto_clp(m.group(3))
            sku = None
            if i < len(bloque) and bloque[i].strip().upper().startswith("SKU:"):
                sku = bloque[i].split(":", 1)[1].strip()
                i += 1
            lineas.append(
                {
                    "producto": nombre,
                    "cantidad": cantidad,
                    "total": total,
                    "sku": sku,
                }
            )
    return lineas


def parse_factura_pdf_bytes(data: bytes) -> dict[str, Any]:
    """
    Parsea factura web Huentelauquen.
    Devuelve dict con campos de orden + lineas + advertencias.
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError("Instale pdfplumber: pip install pdfplumber") from e

    advertencias: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not pdf.pages:
            raise ValueError("PDF sin páginas")
        texto = pdf.pages[0].extract_text() or ""

    texto = texto.replace("\r\n", "\n")
    lineas = [ln.strip() for ln in texto.split("\n") if ln.strip()]

    if "FACTURA" not in texto.upper() and "HUENTELAUQUEN" not in texto.upper():
        advertencias.append("El PDF no parece una factura Huentelauquen.")

    # Cabecera: tras FACTURA hasta bloque productos
    try:
        idx_factura = next(
            i for i, ln in enumerate(lineas) if ln.upper() == "FACTURA"
        )
    except StopIteration:
        idx_factura = 0

    cabecera = lineas[idx_factura + 1 :]
    idx_prod = next(
        (i for i, ln in enumerate(cabecera) if ln.startswith("Producto Cantidad")),
        len(cabecera),
    )
    head = cabecera[:idx_prod]
    prod_bloque = cabecera[idx_prod + 1 :]

    cliente = ""
    fecha_oc = None
    n_orden = ""
    calle = ""
    comuna = ""

    if head:
        ln0 = head[0]
        if "Fecha de factura:" in ln0:
            partes = ln0.split("Fecha de factura:", 1)
            cliente = partes[0].strip()
            fecha_oc = _parse_fecha_es(partes[1])
        else:
            cliente = ln0

    if len(head) > 1:
        ln1 = head[1]
        if "Número de pedido:" in ln1 or "Numero de pedido:" in ln1:
            partes = re.split(r"N[uú]mero de pedido:", ln1, flags=re.I)
            calle = partes[0].strip()
            n_orden = partes[1].strip() if len(partes) > 1 else ""
        else:
            calle = ln1

    if len(head) > 2:
        ln2 = head[2]
        if not ln2.lower().startswith("fecha de pedido"):
            comuna = ln2.strip()

    for ln in head:
        if "Fecha de pedido:" in ln and not fecha_oc:
            fecha_oc = _parse_fecha_es(ln.split(":", 1)[1])
        if ("Número de pedido:" in ln or "Numero de pedido:" in ln) and not n_orden:
            n_orden = re.split(r"N[uú]mero de pedido:", ln, flags=re.I)[1].strip()

    email = _extraer_email(head)
    celular_raw = _extraer_celular(head)

    lineas_prod = _parse_lineas_producto(prod_bloque)

    direccion = calle
    if comuna:
        if comuna.lower() not in (direccion or "").lower():
            direccion = f"{calle}, {comuna}".strip(", ")

    if not n_orden:
        advertencias.append("No se detectó N° de pedido.")
    if not cliente:
        advertencias.append("No se detectó nombre de cliente.")
    if not fecha_oc:
        advertencias.append("No se detectó fecha; revise manualmente.")
    if not lineas_prod:
        advertencias.append("No se detectaron líneas de producto.")

    return {
        "n_orden": n_orden,
        "fecha_oc": fecha_oc or date.today().isoformat(),
        "cliente": cliente,
        "estado": "Pendiente",
        "transporte": "",
        "direccion": direccion,
        "comuna": comuna,
        "calle": calle,
        "celular_raw": celular_raw or "",
        "email": email or "",
        "url": "",
        "obs": "",
        "lineas": lineas_prod,
        "advertencias": advertencias,
    }
