"""PDF final FxR en tamaño Carta: resumen (con agrupación) + imágenes en hojas + PDFs fusionados."""
from __future__ import annotations

import io
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm, inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from utils.formato_dinero import dinero_presentacion

# Carta (Letter)
PAGE_W, PAGE_H = letter
MARGIN = 0.6 * inch

# Datos emisor (formato rendición)
EMPRESA_NOMBRE = "Hacienda Huentelauquen Comercial SpA"
EMPRESA_RUT = "77.332.804-8"
LOGO_REL = os.path.join("static", "img", "logo.png")

# Colores del formato Excel de referencia
COLOR_AMARILLO = colors.Color(1.0, 0.95, 0.2)  # encabezado tabla
COLOR_CELESTE = colors.Color(0.72, 0.88, 0.98)  # cajas Nombre/Área/Fecha
COLOR_BORDE = colors.black


def armar_filas_resumen(lineas: List[dict]) -> List[dict]:
    """
    Agrupa líneas cuyo tipo_gasto.permite_agrupar=1 en una fila sumada.
    El resto va línea a línea.
    """
    grupos: Dict[Any, List[dict]] = defaultdict(list)
    sueltas: List[dict] = []
    for l in lineas:
        if l.get("permite_agrupar") and l.get("tipo_gasto_id"):
            key = (l["tipo_gasto_id"], l.get("centro_costo_id"))
            grupos[key].append(l)
        else:
            sueltas.append(l)

    filas: List[dict] = []
    for l in sueltas:
        filas.append(
            {
                "fecha": l.get("fecha_comprobante"),
                "tipo_doc": l.get("tipo_doc"),
                "n_doc": l.get("n_doc"),
                "concepto": l.get("concepto"),
                "tipo_gasto": l.get("tipo_gasto_nombre"),
                "centro": l.get("centro_costo_codigo") or l.get("centro_costo_nombre"),
                "monto": int(l.get("monto") or 0),
                "duplicado": bool(l.get("duplicado_n_doc")),
                "dup_ok": bool(l.get("duplicado_autorizado")),
                "agrupada": False,
                "n_items": 1,
            }
        )

    for (_tg, _cc), items in grupos.items():
        montos = sum(int(x.get("monto") or 0) for x in items)
        fechas = [x.get("fecha_comprobante") for x in items if x.get("fecha_comprobante")]
        f0 = min(fechas) if fechas else None
        f1 = max(fechas) if fechas else None
        if f0 and f1 and f0 != f1:
            if hasattr(f0, "strftime"):
                fs = f"{f0.strftime('%d-%m-%y')}…{f1.strftime('%d-%m-%y')}"
            else:
                fs = f"{f0}…{f1}"
        elif f0 and hasattr(f0, "strftime"):
            fs = f0.strftime("%d-%m-%y")
        else:
            fs = str(f0 or "")
        nombre_tg = items[0].get("tipo_gasto_nombre") or "Agrupado"
        centro = items[0].get("centro_costo_codigo") or items[0].get("centro_costo_nombre")
        filas.append(
            {
                "fecha": fs,
                "tipo_doc": "—",
                "n_doc": "—",
                "concepto": f"{nombre_tg} ({len(items)} comprobantes)",
                "tipo_gasto": nombre_tg,
                "centro": centro,
                "monto": montos,
                "duplicado": False,
                "dup_ok": False,
                "agrupada": True,
                "n_items": len(items),
            }
        )
    return filas


def generar_pdf_rendicion(
    rendicion: dict,
    lineas: List[dict],
    dups_info: List[dict],
    root_path: str,
    layout: Optional[dict] = None,
) -> bytes:
    """
    layout: {
      "pages": [
        {"items": [{"linea_id": 1, "x":0.05, "y":0.05, "w":0.4, "h":0.3}, ...]}
      ]
    }
    Coordenadas en fracción de página (0-1), origen arriba-izquierda en el editor;
    en PDF se convierten a origen abajo-izquierda.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    filas = armar_filas_resumen(lineas)
    _dibujar_portada(c, rendicion, filas, dups_info, root_path=root_path)
    c.showPage()

    # Imágenes: layout interactivo o auto-pack
    imgs = [l for l in lineas if _es_imagen(l)]
    if layout and layout.get("pages"):
        _dibujar_layout(c, imgs, layout, root_path)
    elif imgs:
        _auto_pack_imagenes(c, imgs, root_path)

    c.save()
    resumen = buf.getvalue()
    return fusionar_solo_pdfs_comprobante(resumen, lineas, root_path)


def _es_imagen(linea: dict) -> bool:
    mime = (linea.get("mime") or "").lower()
    rel = (linea.get("archivo_local") or "").lower()
    if "pdf" in mime or rel.endswith(".pdf"):
        return False
    return bool(linea.get("archivo_local"))


def _logo_path(root_hint: Optional[str] = None) -> Optional[str]:
    candidatos = []
    if root_hint:
        candidatos.append(os.path.join(root_hint, LOGO_REL))
    aqui = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    candidatos.append(os.path.join(aqui, LOGO_REL))
    candidatos.append(os.path.abspath(LOGO_REL))
    for p in candidatos:
        if os.path.isfile(p):
            return p
    return None


def _fmt_fecha(val) -> str:
    if hasattr(val, "strftime"):
        return val.strftime("%d-%m-%y")
    s = str(val or "").strip()
    return s[:16] if s else "—"


def _clip_text(text: str, font: str, size: float, max_w: float) -> str:
    t = str(text or "")
    if not t:
        return ""
    if stringWidth(t, font, size) <= max_w:
        return t
    ell = "…"
    while t and stringWidth(t + ell, font, size) > max_w:
        t = t[:-1]
    return (t + ell) if t else ell


def _celda(
    c,
    x: float,
    y: float,
    w: float,
    h: float,
    texto: str,
    *,
    font: str = "Helvetica",
    size: float = 8,
    align: str = "left",
    fill=None,
    bold: bool = False,
) -> None:
    """Dibuja celda con borde; el texto queda recortado al ancho (no se monta con la siguiente)."""
    if fill is not None:
        c.setFillColor(fill)
        c.rect(x, y, w, h, fill=1, stroke=0)
    c.setStrokeColor(COLOR_BORDE)
    c.setLineWidth(0.6)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setFillColor(colors.black)
    fnt = "Helvetica-Bold" if bold else font
    c.setFont(fnt, size)
    pad = 2.5
    max_w = max(4, w - 2 * pad)
    txt = _clip_text(texto, fnt, size, max_w)
    ty = y + (h - size) / 2 - 0.5
    if align == "right":
        c.drawRightString(x + w - pad, ty, txt)
    elif align == "center":
        c.drawCentredString(x + w / 2, ty, txt)
    else:
        c.drawString(x + pad, ty, txt)


def _dibujar_portada(c, rendicion, filas, dups_info, root_path: str = ""):
    width, height = PAGE_W, PAGE_H
    left = 1.4 * cm
    right = width - 1.4 * cm
    usable = right - left

    # --- Encabezado: logo der. + empresa centro + caja datos izq. ---
    logo = _logo_path(root_path)
    logo_w, logo_h = 3.6 * cm, 1.7 * cm
    if logo:
        try:
            c.drawImage(
                ImageReader(logo),
                right - logo_w,
                height - 2.3 * cm,
                width=logo_w,
                height=logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, height - 1.1 * cm, EMPRESA_NOMBRE)
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, height - 1.55 * cm, f"RUT : {EMPRESA_RUT}")

    # Caja celeste Nombre / Área / Fecha (estilo formato)
    box_x, box_y = left, height - 3.55 * cm
    box_w, box_h = 7.2 * cm, 1.85 * cm
    c.setFillColor(COLOR_CELESTE)
    c.setStrokeColor(COLOR_BORDE)
    c.setLineWidth(0.8)
    c.rect(box_x, box_y, box_w, box_h, fill=1, stroke=1)

    nombre = rendicion.get("nombre_snapshot") or "—"
    area = rendicion.get("area") or "—"
    fecha_s = _fmt_fecha(rendicion.get("fecha_rendicion"))
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    line_h = 0.48 * cm
    ty = box_y + box_h - 0.45 * cm
    for label, val in (("NOMBRE", nombre), ("AREA", area), ("FECHA", fecha_s)):
        c.setFont("Helvetica-Bold", 8)
        c.drawString(box_x + 0.2 * cm, ty, f"{label} :")
        c.setFont("Helvetica", 9)
        c.drawString(box_x + 2.0 * cm, ty, _clip_text(str(val), "Helvetica", 9, box_w - 2.3 * cm))
        ty -= line_h

    # Título + N°
    corr = rendicion.get("correlativo") or "—"
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 4.2 * cm, "RENDICION DE GASTOS")
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(right, height - 4.2 * cm, f"N°  {corr}")

    # Tipo solicitud (como el formato)
    y = height - 4.85 * cm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, "SOLICITO DEVOLUCION POR")
    y -= 0.45 * cm
    c.setFont("Helvetica", 9)
    tipo = (rendicion.get("tipo") or "RENDICION_DE_FONDO").replace("_", " ")
    c.drawString(left, y, tipo)
    # casilla marcada
    cx = left + stringWidth(tipo, "Helvetica", 9) + 0.35 * cm
    c.setFillColor(COLOR_CELESTE)
    c.rect(cx, y - 0.08 * cm, 0.45 * cm, 0.45 * cm, fill=1, stroke=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(cx + 0.22 * cm, y, "X")

    # --- Tabla con anchos fijos (sin solapamiento) ---
    # FECHA | TIPO | N° DOC | CONCEPTO | T.GASTO | C.COSTO | $ TOTAL
    col_ws = [
        1.7 * cm,  # FECHA
        1.6 * cm,  # TIPO
        2.2 * cm,  # N° DOC
        5.0 * cm,  # CONCEPTO
        2.3 * cm,  # T.GASTO
        2.0 * cm,  # C.COSTO
        2.2 * cm,  # $ TOTAL
    ]
    # Ajustar última columna al borde derecho
    suma = sum(col_ws)
    if abs(suma - usable) > 0.5:
        col_ws[-1] = max(1.8 * cm, usable - sum(col_ws[:-1]))
    headers = ["FECHA", "TIPO", "N° DOC", "CONCEPTO", "T.GASTO", "C.COSTO", "$ TOTAL"]
    aligns = ["center", "center", "left", "left", "left", "left", "right"]
    row_h = 0.52 * cm

    def _xs():
        xs, acc = [], left
        for w in col_ws:
            xs.append(acc)
            acc += w
        return xs

    def _draw_header(yy: float) -> float:
        xs = _xs()
        for i, h in enumerate(headers):
            _celda(
                c, xs[i], yy, col_ws[i], row_h, h,
                size=7.5, align="center", fill=COLOR_AMARILLO, bold=True,
            )
        return yy - row_h

    y = _draw_header(y - 0.75 * cm)

    for l in filas:
        if y < 3.2 * cm:
            c.showPage()
            y = height - 2 * cm
            y = _draw_header(y)

        f = l.get("fecha")
        fs = f if isinstance(f, str) and ("…" in f or len(f) <= 16) else _fmt_fecha(f)
        vals = [
            fs,
            str(l.get("tipo_doc") or "—"),
            str(l.get("n_doc") or "—"),
            str(l.get("concepto") or ""),
            str(l.get("tipo_gasto") or ""),
            str(l.get("centro") or ""),
            dinero_presentacion(l.get("monto") or 0),
        ]
        xs = _xs()
        fill_row = colors.Color(1, 0.92, 0.92) if l.get("duplicado") else None
        for i, val in enumerate(vals):
            _celda(
                c, xs[i], y, col_ws[i], row_h, val,
                size=7.5, align=aligns[i], fill=fill_row,
            )
        if l.get("duplicado"):
            # marca pequeña en concepto
            marca = "DUP OK" if l.get("dup_ok") else "DUP"
            c.setFillColor(colors.Color(0.75, 0, 0))
            c.setFont("Helvetica-Bold", 6)
            c.drawRightString(xs[3] + col_ws[3] - 2, y + 2, marca)
            c.setFillColor(colors.black)
        y -= row_h

    # Fila TOTAL
    y -= 0.15 * cm
    if y < 2.8 * cm:
        c.showPage()
        y = height - 2 * cm
    tot_w = sum(col_ws[:-1])
    _celda(c, left, y, tot_w, row_h + 0.08 * cm, "TOTAL", size=9, align="right", bold=True, fill=COLOR_AMARILLO)
    _celda(
        c, left + tot_w, y, col_ws[-1], row_h + 0.08 * cm,
        dinero_presentacion(rendicion.get("total") or 0),
        size=9, align="right", bold=True, fill=COLOR_AMARILLO,
    )
    y -= 0.9 * cm

    # Comentario / firma (centrado, bajo el total)
    comentario = (rendicion.get("comentario_firma") or "").strip()
    if y < 4.5 * cm:
        c.showPage()
        y = height - 2 * cm
    c.setStrokeColor(COLOR_BORDE)
    c.setLineWidth(0.7)
    box_h = 2.4 * cm if comentario else 1.6 * cm
    c.setFillColor(colors.Color(0.98, 0.98, 0.98))
    c.rect(left, y - box_h, usable, box_h, fill=1, stroke=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(width / 2, y - 0.45 * cm, "COMENTARIO / FIRMA")
    c.setFont("Helvetica", 9)
    if comentario:
        ty = y - 0.9 * cm
        for chunk in _wrap(comentario, 85):
            if ty < y - box_h + 0.25 * cm:
                break
            c.drawCentredString(width / 2, ty, chunk)
            ty -= 0.38 * cm
    else:
        c.setFillColor(colors.Color(0.45, 0.45, 0.45))
        c.setFont("Helvetica-Oblique", 8)
        c.drawCentredString(
            width / 2,
            y - 1.0 * cm,
            "Ej.: Depositar en cuenta …… / Firma ……………………",
        )
        c.setFillColor(colors.black)
    y -= box_h + 0.6 * cm

    if dups_info:
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.Color(0.7, 0, 0))
        c.drawString(left, y, "Documentos duplicados (autorizados / referencia)")
        c.setFillColor(colors.black)
        y -= 0.45 * cm
        c.setFont("Helvetica", 8)
        for d in dups_info:
            if y < 2.5 * cm:
                c.showPage()
                y = height - 2 * cm
                c.setFont("Helvetica", 8)
            cuando = d.get("otro_cuando")
            cuando_s = cuando.strftime("%d-%m-%Y %H:%M") if hasattr(cuando, "strftime") else str(cuando or "—")
            corr_o = d.get("otro_correlativo") or f"ID {d.get('otro_rendicion_id')}"
            texto = (
                f"N° {d.get('n_doc')} ({d.get('tipo_doc')}): también en rendición {corr_o} | "
                f"quién: {d.get('otro_usuario')} | cuándo: {cuando_s} | "
                f"cuánto: {dinero_presentacion(d.get('otro_monto') or 0)} | "
                f"estado: {d.get('otro_estado')}"
            )
            if d.get("autorizado"):
                texto += f" | autorizado por: {d.get('autorizado_por') or '—'}"
            for chunk in _wrap(texto, 95):
                c.drawString(left, y, chunk)
                y -= 0.35 * cm


def _wrap(text: str, width: int) -> List[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _auto_pack_imagenes(c, imgs: List[dict], root_path: str, por_hoja: int = 4) -> None:
    """Coloca hasta N imágenes por hoja Carta en grilla (sin páginas 'Anexo' vacías)."""
    usable_w = PAGE_W - 2 * MARGIN
    usable_h = PAGE_H - 2 * MARGIN - 0.4 * inch
    cols = 2 if por_hoja >= 2 else 1
    rows = max(1, (por_hoja + cols - 1) // cols)
    cell_w = usable_w / cols
    cell_h = usable_h / rows

    for i, linea in enumerate(imgs):
        if i % por_hoja == 0 and i > 0:
            c.showPage()
        if i % por_hoja == 0:
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.grey)
            c.drawString(MARGIN, PAGE_H - 0.45 * inch, "Comprobantes (imágenes)")
            c.setFillColor(colors.black)

        slot = i % por_hoja
        col = slot % cols
        row = slot // cols
        x = MARGIN + col * cell_w + 0.1 * inch
        # origen abajo-izquierda
        y = PAGE_H - MARGIN - 0.4 * inch - (row + 1) * cell_h + 0.1 * inch
        _draw_img_fit(
            c,
            os.path.join(root_path, linea["archivo_local"]),
            x,
            y,
            cell_w - 0.2 * inch,
            cell_h - 0.25 * inch,
            etiqueta=f"#{linea.get('id')} {linea.get('concepto') or ''}"[:40],
        )


def _dibujar_layout(c, imgs: List[dict], layout: dict, root_path: str) -> None:
    by_id = {int(l["id"]): l for l in imgs}
    pages = layout.get("pages") or []
    for pi, page in enumerate(pages):
        if pi > 0:
            c.showPage()
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.grey)
        c.drawString(MARGIN, PAGE_H - 0.45 * inch, f"Comprobantes — hoja {pi + 1}")
        c.setFillColor(colors.black)
        for item in page.get("items") or []:
            lid = int(item.get("linea_id") or 0)
            linea = by_id.get(lid)
            if not linea:
                continue
            # editor: x,y desde arriba-izquierda en 0..1
            x_frac = float(item.get("x", 0.05))
            y_frac = float(item.get("y", 0.05))
            w_frac = float(item.get("w", 0.4))
            h_frac = float(item.get("h", 0.3))
            x = MARGIN + x_frac * (PAGE_W - 2 * MARGIN)
            w = max(0.5 * inch, w_frac * (PAGE_W - 2 * MARGIN))
            h = max(0.5 * inch, h_frac * (PAGE_H - 2 * MARGIN - 0.4 * inch))
            top = PAGE_H - MARGIN - 0.4 * inch - y_frac * (PAGE_H - 2 * MARGIN - 0.4 * inch)
            y = top - h
            _draw_img_fit(
                c,
                os.path.join(root_path, linea["archivo_local"]),
                x,
                y,
                w,
                h,
                etiqueta=None,
            )


def _draw_img_fit(c, abs_f: str, x, y, max_w, max_h, etiqueta: Optional[str] = None) -> None:
    if not os.path.isfile(abs_f):
        return
    try:
        with Image.open(abs_f) as im:
            iw, ih = im.size
        if iw <= 0 or ih <= 0:
            return
        scale = min(max_w / iw, max_h / ih)
        dw, dh = iw * scale, ih * scale
        ox = x + (max_w - dw) / 2
        oy = y + (max_h - dh) / 2
        c.drawImage(ImageReader(abs_f), ox, oy, width=dw, height=dh, preserveAspectRatio=True, mask="auto")
        if etiqueta:
            c.setFont("Helvetica", 6)
            c.drawString(x, y - 8, etiqueta[:50])
    except Exception:
        pass


def fusionar_solo_pdfs_comprobante(pdf_base: bytes, lineas: List[dict], root_path: str) -> bytes:
    """Agrega páginas reales de PDFs de comprobante (sin hojas 'Anexo' vacías)."""
    writer = PdfWriter()
    reader = PdfReader(io.BytesIO(pdf_base))
    for p in reader.pages:
        writer.add_page(p)
    for linea in lineas:
        rel = linea.get("archivo_local") or ""
        mime = (linea.get("mime") or "").lower()
        abs_f = os.path.join(root_path, rel) if rel else ""
        if not abs_f or not os.path.isfile(abs_f):
            continue
        if "pdf" not in mime and not abs_f.lower().endswith(".pdf"):
            continue
        try:
            r = PdfReader(abs_f)
            for p in r.pages:
                writer.add_page(p)
        except Exception:
            continue
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def layout_default_para_imagenes(imgs: List[dict], por_hoja: int = 4) -> dict:
    """Layout inicial en grilla 2x2 para el editor interactivo."""
    pages = []
    cols, rows = 2, 2
    for i, linea in enumerate(imgs):
        if i % por_hoja == 0:
            pages.append({"items": []})
        slot = i % por_hoja
        col = slot % cols
        row = slot // cols
        pages[-1]["items"].append(
            {
                "linea_id": linea["id"],
                "x": 0.02 + col * 0.49,
                "y": 0.02 + row * 0.48,
                "w": 0.46,
                "h": 0.44,
            }
        )
    return {"pages": pages or [{"items": []}]}
