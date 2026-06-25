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


def _detectar_estado_pdf(texto: str) -> str:
    """Si el PDF menciona retiro en Costanera, estado inicial Retiro Costanera."""
    if re.search(r"retiro\s+costanera", texto or "", re.IGNORECASE):
        return "Retiro Costanera"
    return "Pendiente"


def _limpiar_nombre_cliente(texto: str) -> str:
    t = (texto or "").strip()
    if "Enviar a:" in t or "enviar a:" in t.lower():
        t = re.split(r"\s*Enviar a:", t, flags=re.I)[0].strip()
    if "Fecha de factura:" in t:
        t = t.split("Fecha de factura:")[0].strip()
    return t


def _parse_cabecera(head: list[str]) -> dict[str, Any]:
    n_orden = ""
    fecha_oc = None
    for ln in head:
        if re.search(r"N[uú]mero de pedido:", ln, re.I):
            n_orden = re.split(r"N[uú]mero de pedido:", ln, flags=re.I)[1].strip()
        if "Fecha de factura:" in ln and not fecha_oc:
            fecha_oc = _parse_fecha_es(ln.split("Fecha de factura:", 1)[1])
        if "Fecha de pedido:" in ln and not fecha_oc:
            fecha_oc = _parse_fecha_es(ln.split(":", 1)[1])

    tiene_enviar_a = any("enviar a:" in ln.lower() for ln in head)
    cliente = ""
    calle = ""
    comuna = ""

    if head:
        cliente = _limpiar_nombre_cliente(head[0])

    if len(head) > 1:
        ln1 = head[1]
        if re.search(r"N[uú]mero de pedido:", ln1, re.I):
            calle = re.split(r"N[uú]mero de pedido:", ln1, flags=re.I)[0].strip()
            if tiene_enviar_a:
                m_nom = re.match(
                    r"^(.+?)\s+[\d.\-]+\s*$",
                    calle,
                )
                if m_nom and not re.match(r"^[\d.\-\s]+$", m_nom.group(1)):
                    nombre_envio = m_nom.group(1).strip()
                    if len(nombre_envio) > 4:
                        cliente = nombre_envio
                calle = re.sub(r"\s+" + re.escape(cliente) + r"\s*$", "", calle).strip()
        else:
            calle = ln1

    if tiene_enviar_a and len(head) > 1:
        ln1 = head[1]
        m = re.match(
            r"^(.+?)\s+[\d.]+\-?\s*N[uú]mero de pedido:",
            ln1,
            re.I,
        )
        if m:
            posible = m.group(1).strip()
            if posible and not re.match(r"^[\d.\-\s]+$", posible):
                cliente = posible
            calle = re.split(r"N[uú]mero de pedido:", ln1, flags=re.I)[0].strip()
            calle = re.sub(r"\s+" + re.escape(cliente) + r"\s*$", "", calle).strip()

    meta_prefixes = ("fecha de", "método de", "metodo de")
    for ln in head[2:]:
        low = ln.lower()
        if any(low.startswith(p) for p in meta_prefixes):
            continue
        if "@" in ln:
            continue
        digits = re.sub(r"\D", "", ln)
        if len(digits) >= 8 and len(digits) <= 12:
            continue
        if not comuna:
            comuna = ln.strip()
            break

    return {
        "cliente": cliente,
        "n_orden": n_orden,
        "fecha_oc": fecha_oc,
        "calle": calle,
        "comuna": comuna,
    }


def _parse_factura_texto(texto: str) -> dict[str, Any]:
    advertencias: list[str] = []
    texto = texto.replace("\r\n", "\n")
    lineas = [ln.strip() for ln in texto.split("\n") if ln.strip()]

    if "FACTURA" not in texto.upper() and "HUENTELAUQUEN" not in texto.upper():
        advertencias.append("El PDF no parece una factura Huentelauquen.")

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

    cab = _parse_cabecera(head)
    cliente = cab["cliente"]
    n_orden = cab["n_orden"]
    fecha_oc = cab["fecha_oc"]
    calle = cab["calle"]
    comuna = cab["comuna"]

    email = _extraer_email(head)
    celular_raw = _extraer_celular(head)
    lineas_prod = _parse_lineas_producto(prod_bloque)

    direccion = calle
    if comuna and comuna.lower() not in (direccion or "").lower():
        direccion = f"{calle}, {comuna}".strip(", ")

    if not n_orden:
        advertencias.append("No se detectó N° de pedido.")
    if not cliente:
        advertencias.append("No se detectó nombre de cliente.")
    if not fecha_oc:
        advertencias.append("No se detectó fecha; revise manualmente.")
    if not lineas_prod:
        advertencias.append("No se detectaron líneas de producto.")

    estado = _detectar_estado_pdf(texto)
    if estado == "Retiro Costanera":
        advertencias.append("Detectado «Retiro Costanera» en PDF — estado inicial asignado.")

    return {
        "n_orden": n_orden,
        "fecha_oc": fecha_oc or date.today().isoformat(),
        "cliente": cliente,
        "estado": estado,
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


def parse_factura_pdf_multipage(data: bytes) -> list[dict[str, Any]]:
    """Parsea cada página de un PDF como orden independiente."""
    from utils.despacho_web_pdf_split import dividir_pdf_por_paginas

    paginas = dividir_pdf_por_paginas(data)
    resultados = []
    for i, page_bytes in enumerate(paginas):
        parsed = parse_factura_pdf_bytes(page_bytes)
        parsed["pagina_origen"] = i + 1
        resultados.append(parsed)
    return resultados


def parse_factura_pdf_bytes(data: bytes) -> dict[str, Any]:
    """
    Parsea factura web Huentelauquen.
    Devuelve dict con campos de orden + lineas + advertencias.
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError("Instale pdfplumber: pip install pdfplumber") from e

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not pdf.pages:
            raise ValueError("PDF sin páginas")
        texto = pdf.pages[0].extract_text() or ""

    return _parse_factura_texto(texto)
