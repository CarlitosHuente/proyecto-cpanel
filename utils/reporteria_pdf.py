"""PDF de ventas: semana actual, comparativo y matriz producto × sucursal."""
from __future__ import annotations

import os
from datetime import datetime

import pytz
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from utils.formato_dinero import dinero_presentacion, metrico_presentacion

PAGE_W, PAGE_H = landscape(letter)
MARGIN = 1.15 * cm
# Rojo del dashboard gerencial para el año actual; gris punteado para el anterior.
COLOR_ROJO = colors.Color(216 / 255, 0, 0)
COLOR_TINTA = colors.Color(0.10, 0.10, 0.12)
COLOR_ACTUAL = COLOR_ROJO
COLOR_SOMBRA = colors.Color(0.55, 0.58, 0.62)
COLOR_AREA = colors.Color(216 / 255, 0.12, 0.12, alpha=0.16)
COLOR_TEXTO = COLOR_TINTA
COLOR_MUTED = colors.Color(0.38, 0.40, 0.44)
COLOR_LINEA = colors.Color(0.90, 0.91, 0.92)
COLOR_PAPEL = colors.Color(0.98, 0.98, 0.99)
COLOR_SUBE = colors.Color(0.12, 0.55, 0.36)
COLOR_BAJA = COLOR_ROJO
COLOR_CIAN = colors.Color(0.0, 0.70, 0.85)
PALETA = [
    COLOR_ROJO,
    colors.Color(0.96, 0.78, 0.10),
    COLOR_CIAN,
    colors.Color(0.18, 0.62, 0.32),
    colors.Color(0.25, 0.32, 0.42),
    colors.Color(0.55, 0.40, 0.28),
    colors.Color(0.45, 0.48, 0.55),
    colors.Color(0.72, 0.45, 0.18),
]

EMPRESA_LABEL = {"comercial": "Comercial", "agricola": "Agrícola"}
CORTE_LABEL = {"semanal": "Semanal (6 semanas)", "mensual": "Mensual (6 meses)"}
VISTA_LABEL = {
    "consolidado": "Consolidado",
    "sucursales": "Por sucursal",
    "ambos": "Consolidado y por sucursal",
}


def _fmt_pct(valor) -> str:
    if valor is None:
        return "s/base"
    signo = "+" if valor > 0 else ""
    return f"{signo}{valor:.1f}".replace(".", ",") + "%"


def _sentido(pesos: float) -> str:
    if pesos > 0:
        return "Sube"
    if pesos < 0:
        return "Baja"
    return "Igual"


def _color_var(pesos: float):
    if pesos > 0:
        return COLOR_SUBE
    if pesos < 0:
        return COLOR_BAJA
    return COLOR_MUTED


def _clip(texto: str, ancho: float, size: float = 8, font: str = "Helvetica") -> str:
    t = "" if texto is None else str(texto)
    if stringWidth(t, font, size) <= ancho:
        return t
    while t and stringWidth(t + "…", font, size) > ancho:
        t = t[:-1]
    return (t + "…") if t else ""


def _fecha_hora() -> str:
    return datetime.now(pytz.timezone("America/Santiago")).strftime("%d/%m/%Y %H:%M")


class _Pdf:
    def __init__(self, path: str, datos: dict):
        self.c = canvas.Canvas(path, pagesize=landscape(letter))
        self.datos = datos
        self.y = PAGE_H - MARGIN
        self.page = 1

    def _footer(self):
        c = self.c
        c.setFillColor(COLOR_MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN, 0.55 * cm, "Huente — Reportería · montos en neto")
        c.drawRightString(PAGE_W - MARGIN, 0.55 * cm, str(self.page))

    def nueva(self):
        self._footer()
        self.c.showPage()
        self.c.setPageSize(landscape(letter))
        self.page += 1
        self.y = PAGE_H - MARGIN

    def espacio(self, alto: float):
        if self.y - alto < 1.4 * cm:
            self.nueva()

    def titulo(self, texto: str, size: float = 13):
        self.espacio(0.8 * cm)
        self.c.setFillColor(COLOR_TINTA)
        self.c.setFont("Helvetica-Bold", size)
        self.c.drawString(MARGIN, self.y, texto)
        self.y -= 0.22 * cm
        self.c.setFillColor(COLOR_ROJO)
        self.c.rect(MARGIN, self.y, 1.6 * cm, 1.5, fill=1, stroke=0)
        self.y -= 0.45 * cm

    def portada(self):
        d = self.datos
        c = self.c
        c.setFillColor(COLOR_TINTA)
        c.rect(0, PAGE_H - 1.7 * cm, PAGE_W, 1.7 * cm, fill=1, stroke=0)
        c.setFillColor(COLOR_ROJO)
        c.rect(0, PAGE_H - 1.82 * cm, PAGE_W, 0.12 * cm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(MARGIN, PAGE_H - 0.75 * cm, _clip(d.get("nombre") or "Reporte de ventas", 18 * cm, 14, "Helvetica-Bold"))
        c.setFont("Helvetica", 8)
        meta = " · ".join(
            [
                EMPRESA_LABEL.get(d.get("empresa"), ""),
                CORTE_LABEL.get(d.get("corte"), ""),
                _fecha_hora(),
            ]
        )
        c.drawString(MARGIN, PAGE_H - 1.25 * cm, meta)
        self.y = PAGE_H - 2.85 * cm
        if d.get("periodo_incompleto"):
            c.setFillColor(COLOR_MUTED)
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(MARGIN, self.y, f"El periodo {d['periodo_incompleto']} está en curso.")
            self.y -= 0.45 * cm

    def macro(self):
        semana = self.datos.get("semana") or {}
        self.titulo(f"1. {self.datos.get('etiqueta_macro') or 'Periodo actual'}")
        self._cards_macro(semana)
        self.y -= 0.2 * cm
        self._dos_tortas(semana.get("por_sucursal") or [], semana.get("por_familia") or [])
        self.y -= 0.35 * cm
        self._fichas(semana.get("fichas") or [])

    def _cards_macro(self, semana: dict):
        self.espacio(1.7 * cm)
        c = self.c
        alto = 1.45 * cm
        ancho = 6.2 * cm
        y = self.y - alto
        pares = [
            ("Neto consolidado", dinero_presentacion(semana.get("neto"))),
            ("Ticket promedio", dinero_presentacion(semana.get("ticket"))),
        ]
        for i, (label, valor) in enumerate(pares):
            x = MARGIN + i * (ancho + 0.4 * cm)
            c.setFillColor(colors.Color(0.94, 0.96, 0.94))
            c.roundRect(x, y, ancho, alto, 4, fill=1, stroke=0)
            c.setFillColor(COLOR_MUTED)
            c.setFont("Helvetica", 8)
            c.drawString(x + 8, y + alto - 0.4 * cm, label)
            c.setFillColor(COLOR_ACTUAL)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(x + 8, y + 0.28 * cm, valor)
        self.y = y - 0.25 * cm

    def _dos_tortas(self, sucursales: list, familias: list):
        alto = 6.3 * cm
        self.espacio(alto)
        mitad = (PAGE_W - 2 * MARGIN) / 2
        self._torta(MARGIN, self.y - alto, mitad - 0.2 * cm, alto, "Por sucursal", sucursales)
        self._torta(MARGIN + mitad, self.y - alto, mitad - 0.2 * cm, alto, "Por familia", familias)
        self.y -= alto + 0.15 * cm

    def _torta(self, x, y, ancho, alto, titulo, partes):
        c = self.c
        c.setFillColor(COLOR_ACTUAL)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, y + alto - 0.35 * cm, titulo)
        if not partes:
            c.setFillColor(COLOR_MUTED)
            c.setFont("Helvetica", 8)
            c.drawString(x, y + alto / 2, "Sin ventas en el periodo.")
            return
        radio = 2.15 * cm
        cx = x + radio + 0.15 * cm
        cy = y + alto / 2 - 0.15 * cm
        total_ang = 0
        for i, parte in enumerate(partes):
            frac = max((parte.get("pct") or 0) / 100, 0)
            extent = frac * 360
            if extent <= 0:
                continue
            c.setFillColor(PALETA[i % len(PALETA)])
            c.wedge(cx - radio, cy - radio, cx + radio, cy + radio, total_ang, extent, stroke=0, fill=1)
            total_ang += extent
        c.setFillColor(colors.white)
        c.circle(cx, cy, radio * 0.42, fill=1, stroke=0)
        lx = x + radio * 2 + 0.55 * cm
        ly = y + alto - 0.85 * cm
        for i, parte in enumerate(partes[:8]):
            c.setFillColor(PALETA[i % len(PALETA)])
            c.rect(lx, ly - 1, 0.28 * cm, 0.28 * cm, fill=1, stroke=0)
            c.setFillColor(COLOR_TEXTO)
            c.setFont("Helvetica", 7.5)
            texto = f"{parte.get('nombre')}  {dinero_presentacion(parte.get('neto'))}  ({_fmt_pct(parte.get('pct')).replace('+', '')})"
            c.drawString(lx + 0.4 * cm, ly, _clip(texto, ancho - (lx - x) - 0.5 * cm, 7.5))
            ly -= 0.42 * cm
        if len(partes) > 8:
            c.setFillColor(COLOR_MUTED)
            c.setFont("Helvetica", 7)
            c.drawString(lx, ly, f"+ {len(partes) - 8} más")

    def _fichas(self, fichas: list):
        if not fichas:
            return
        self.titulo("Familias del periodo", 11)
        alto = 1.7 * cm
        ancho = 4.35 * cm
        gap = 0.25 * cm
        por_fila = max(int((PAGE_W - 2 * MARGIN) // (ancho + gap)), 1)
        c = self.c
        for i, ficha in enumerate(fichas):
            if i % por_fila == 0:
                self.espacio(alto + 0.2 * cm)
                base = self.y - alto
            else:
                base = self.y - alto
            x = MARGIN + (i % por_fila) * (ancho + gap)
            c.setStrokeColor(COLOR_LINEA)
            c.setFillColor(colors.white)
            c.roundRect(x, base, ancho, alto, 3, fill=0, stroke=1)
            c.setFillColor(COLOR_ACTUAL)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + 6, base + alto - 0.38 * cm, _clip(ficha.get("familia"), ancho - 12, 8, "Helvetica-Bold"))
            c.setFillColor(COLOR_TEXTO)
            c.setFont("Helvetica", 7.5)
            precio = dinero_presentacion(ficha.get("precio")) if ficha.get("precio") is not None else "—"
            c.drawString(x + 6, base + 0.72 * cm, f"$ {dinero_presentacion(ficha.get('neto'))}")
            c.drawString(x + 6, base + 0.38 * cm, f"Und {metrico_presentacion(ficha.get('cantidad'))}")
            c.drawString(x + 6, base + 0.08 * cm, f"$/Und {precio}")
            if (i % por_fila) == por_fila - 1 or i == len(fichas) - 1:
                self.y = base - 0.55 * cm

    def comparativo_semana(self):
        filas = self.datos.get("comparativo_semana") or []
        self.espacio(1.2 * cm)
        self.titulo("2. Comparativo de sucursales del periodo")
        headers = ["Sucursal", "Neto", "Año anterior", "Diferencia", "Var %", ""]
        cols = [5.5 * cm, 3.2 * cm, 3.2 * cm, 3.2 * cm, 2.4 * cm, 2 * cm]
        cuerpo = []
        for fila in filas:
            cuerpo.append(
                [
                    fila.get("sucursal") or "",
                    dinero_presentacion(fila.get("neto")),
                    dinero_presentacion(fila.get("neto_sombra")),
                    dinero_presentacion(fila.get("var_pesos")),
                    _fmt_pct(fila.get("var_pct")),
                    _sentido(fila.get("var_pesos") or 0),
                ]
            )
        if not cuerpo:
            cuerpo.append(["Sin sucursales en el periodo", "", "", "", "", ""])
        self._tabla(headers, cuerpo, cols)

    def tendencias(self):
        self.nueva()
        self.titulo("3. Últimos periodos · año actual y año anterior")
        bloques = self.datos.get("bloques") or []
        primero = bloques[:1]
        resto = bloques[1:]
        for bloque in primero:
            self._bloque_linea(bloque)
        if not resto:
            return
        self.nueva()
        for i in range(0, len(resto), 2):
            if i:
                self.nueva()
            self._par_sucursales(resto[i:i + 2])

    def _bloque_linea(self, bloque: dict):
        self.espacio(7.2 * cm)
        c = self.c
        c.setFillColor(COLOR_TINTA)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGIN, self.y, bloque.get("titulo") or "Consolidado")
        tot = bloque.get("totales") or {}
        c.setFont("Helvetica", 8)
        c.setFillColor(_color_var(tot.get("var_pesos") or 0))
        c.drawRightString(
            PAGE_W - MARGIN,
            self.y,
            f"{_sentido(tot.get('var_pesos') or 0)}  {dinero_presentacion(tot.get('var_pesos'))}  ({_fmt_pct(tot.get('var_pct'))})",
        )
        self.y -= 0.7 * cm
        self._leyenda_anios(MARGIN)
        self.y -= 0.45 * cm
        self._linea(bloque.get("serie") or [], MARGIN, PAGE_W - 2 * MARGIN, 4.6 * cm)
        self.y -= 0.55 * cm
        self._tabla_serie(bloque.get("serie") or [], tot)
        self.y -= 0.6 * cm

    def _par_sucursales(self, bloques: list):
        """Dos sucursales por hoja: gráfico arriba y tabla abajo, en columnas."""
        gap = 0.7 * cm
        ancho = (PAGE_W - 2 * MARGIN - gap) / 2
        top = PAGE_H - MARGIN - 0.2 * cm
        alto_graf = 6.4 * cm
        for i, bloque in enumerate(bloques):
            x = MARGIN + i * (ancho + gap)
            c = self.c
            c.setFillColor(COLOR_TINTA)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(x, top, bloque.get("titulo") or "")
            tot = bloque.get("totales") or {}
            c.setFont("Helvetica", 7)
            c.setFillColor(_color_var(tot.get("var_pesos") or 0))
            c.drawRightString(
                x + ancho,
                top,
                f"{_sentido(tot.get('var_pesos') or 0)}  {dinero_presentacion(tot.get('var_pesos'))}",
            )
            self._leyenda_anios(x, top - 0.55 * cm, mover_y=False)
            base_graf = top - 0.95 * cm
            self._linea(
                bloque.get("serie") or [],
                x,
                ancho,
                alto_graf,
                techo=base_graf,
            )
            self._tabla_en(
                x,
                base_graf - alto_graf - 0.85 * cm,
                ancho,
                bloque.get("serie") or [],
                tot,
            )
        self.y = MARGIN

    def _linea(self, serie: list, x0: float, ancho: float, alto: float, techo: float = None):
        if techo is None:
            self.espacio(alto + 0.85 * cm)
            techo = self.y
        base = techo - alto
        c = self.c
        c.setFillColor(COLOR_PAPEL)
        c.roundRect(x0, base, ancho, alto, 3, fill=1, stroke=0)
        c.setStrokeColor(COLOR_LINEA)
        c.setLineWidth(0.4)
        c.line(x0 + 0.25 * cm, base + 0.7 * cm, x0 + ancho - 0.2 * cm, base + 0.7 * cm)
        maximo = 1.0
        for fila in serie:
            maximo = max(maximo, abs(fila.get("neto") or 0), abs(fila.get("neto_sombra") or 0))
        n = max(len(serie), 1)
        piso = base + 0.85 * cm
        techo_linea = base + alto - 0.35 * cm

        def xy(i, valor):
            x = x0 + (i + 0.5) * (ancho / n)
            y = piso + (abs(valor) / maximo) * (techo_linea - piso)
            return x, y

        def puntos_de(clave):
            return [xy(i, fila.get(clave) or 0) for i, fila in enumerate(serie)]

        actuales = puntos_de("neto")
        if len(actuales) >= 2:
            c.setFillColor(COLOR_AREA)
            camino = c.beginPath()
            camino.moveTo(actuales[0][0], piso)
            for x, y in actuales:
                camino.lineTo(x, y)
            camino.lineTo(actuales[-1][0], piso)
            camino.close()
            c.drawPath(camino, fill=1, stroke=0)

        def trazo(puntos, color, grosor, dash=None):
            c.setStrokeColor(color)
            c.setFillColor(color)
            c.setLineWidth(grosor)
            if dash:
                c.setDash(dash)
            for a, b in zip(puntos, puntos[1:]):
                c.line(a[0], a[1], b[0], b[1])
            c.setDash()
            for x, y in puntos:
                c.circle(x, y, 2.2, fill=1, stroke=0)

        trazo(puntos_de("neto_sombra"), COLOR_SOMBRA, 1.2, (1, 2))
        trazo(actuales, COLOR_ACTUAL, 1.8)
        c.setFillColor(COLOR_MUTED)
        c.setFont("Helvetica", 7)
        for i, fila in enumerate(serie):
            x, _y = xy(i, 0)
            c.drawCentredString(x, base + 0.22 * cm, fila.get("etiqueta") or "")
        if techo == self.y:
            self.y = base - 0.15 * cm

    def _leyenda_anios(self, x: float, y: float = None, mover_y: bool = True):
        c = self.c
        if y is None:
            y = self.y
        anio = str((self.datos.get("matriz") or {}).get("anio") or "")
        anio_ant = str((self.datos.get("matriz") or {}).get("anio_anterior") or "")
        c.setStrokeColor(COLOR_SOMBRA)
        c.setDash(1, 2)
        c.setLineWidth(1.2)
        c.line(x, y + 0.08 * cm, x + 0.45 * cm, y + 0.08 * cm)
        c.setDash()
        c.setFillColor(COLOR_MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(x + 0.55 * cm, y, f"Ventas {anio_ant}".strip())
        c.setStrokeColor(COLOR_ROJO)
        c.setFillColor(COLOR_ROJO)
        c.setLineWidth(1.8)
        c.line(x + 3.1 * cm, y + 0.08 * cm, x + 3.55 * cm, y + 0.08 * cm)
        c.circle(x + 3.32 * cm, y + 0.08 * cm, 2.2, fill=1, stroke=0)
        c.setFillColor(COLOR_MUTED)
        c.drawString(x + 3.7 * cm, y, f"Ventas {anio}".strip())
        if mover_y:
            self.y -= 0.2 * cm

    def _tabla_en(self, x0: float, y_top: float, ancho: float, serie: list, totales: dict):
        headers = ["Periodo", "Neto", "Año ant.", "Dif.", "%"]
        filas = []
        for fila in serie:
            filas.append(
                [
                    (fila.get("etiqueta") or "") + (" *" if fila.get("incompleto") else ""),
                    dinero_presentacion(fila.get("neto")),
                    dinero_presentacion(fila.get("neto_sombra")),
                    dinero_presentacion(fila.get("var_pesos")),
                    _fmt_pct(fila.get("var_pct")),
                ]
            )
        filas.append(
            [
                "Total",
                dinero_presentacion(totales.get("neto")),
                dinero_presentacion(totales.get("neto_sombra")),
                dinero_presentacion(totales.get("var_pesos")),
                _fmt_pct(totales.get("var_pct")),
            ]
        )
        pesos = [0.16, 0.24, 0.24, 0.22, 0.14]
        cols = [ancho * p for p in pesos]
        alto = 0.38 * cm
        c = self.c
        y = y_top
        for idx, fila in enumerate([headers] + filas):
            es_header = idx == 0
            negrita = es_header or idx == len(filas)
            if es_header or negrita:
                c.setFillColor(colors.Color(0.94, 0.95, 0.96) if es_header else colors.Color(0.97, 0.97, 0.98))
                c.rect(x0, y - alto + 2, ancho, alto, fill=1, stroke=0)
            c.setStrokeColor(COLOR_LINEA)
            c.setLineWidth(0.3)
            c.line(x0, y - alto + 2, x0 + ancho, y - alto + 2)
            x = x0
            for i, celda in enumerate(fila):
                c.setFillColor(COLOR_TEXTO)
                c.setFont("Helvetica-Bold" if negrita else "Helvetica", 6.5)
                c.drawString(x + 2, y - 0.24 * cm, _clip(str(celda), cols[i] - 4, 6.5, "Helvetica-Bold" if negrita else "Helvetica"))
                x += cols[i]
            y -= alto

    def _tabla_serie(self, serie: list, totales: dict):
        cols = [3.2 * cm, 3.3 * cm, 3.3 * cm, 3.3 * cm, 2.5 * cm, 2.2 * cm]
        headers = ["Periodo", "Neto", "Año ant.", "Diferencia", "Var %", ""]
        filas = []
        for fila in serie:
            marca = " *" if fila.get("incompleto") else ""
            filas.append(
                [
                    (fila.get("etiqueta") or "") + marca,
                    dinero_presentacion(fila.get("neto")),
                    dinero_presentacion(fila.get("neto_sombra")),
                    dinero_presentacion(fila.get("var_pesos")),
                    _fmt_pct(fila.get("var_pct")),
                    _sentido(fila.get("var_pesos") or 0),
                ]
            )
        filas.append(
            [
                "Total",
                dinero_presentacion(totales.get("neto")),
                dinero_presentacion(totales.get("neto_sombra")),
                dinero_presentacion(totales.get("var_pesos")),
                _fmt_pct(totales.get("var_pct")),
                _sentido(totales.get("var_pesos") or 0),
            ]
        )
        self._tabla(headers, filas, cols, ultima_negrita=True)

    def matriz(self):
        matriz = self.datos.get("matriz") or {}
        grupos = matriz.get("grupos") or []
        filas = matriz.get("filas") or []
        etiqueta = matriz.get("etiqueta") or ""
        anio = str(matriz.get("anio") or "")
        anio_ant = str(matriz.get("anio_anterior") or "")
        self.nueva()
        self.titulo(f"4. Detalle por producto · {etiqueta}".strip())
        self.c.setFillColor(COLOR_MUTED)
        self.c.setFont("Helvetica", 8)
        self.c.drawString(MARGIN, self.y, "Agrupado por familia.")
        self.y -= 0.35 * cm
        if not filas:
            self.c.setFillColor(COLOR_TEXTO)
            self.c.drawString(MARGIN, self.y, "Sin productos en el periodo.")
            return
        nombre_w = 3.6 * cm
        metric_w = 1.15 * cm
        n_vals = max(len(grupos) * 2, 1)
        resto = PAGE_W - 2 * MARGIN - nombre_w - metric_w
        col_w = resto / n_vals
        alto = 0.36 * cm
        c = self.c

        def encabezado():
            self.espacio(alto * 3)
            y = self.y
            c.setFillColor(colors.Color(0.93, 0.94, 0.96))
            c.rect(MARGIN, y - alto * 2 + 2, PAGE_W - 2 * MARGIN, alto * 2, fill=1, stroke=0)
            c.setFillColor(COLOR_TINTA)
            c.setFont("Helvetica-Bold", 6.5)
            c.drawString(MARGIN + 2, y - 0.42 * cm, "Producto")
            x = MARGIN + nombre_w + metric_w
            for grupo in grupos:
                c.setFont("Helvetica-Bold", 6.5)
                c.drawCentredString(x + col_w, y - 0.22 * cm, _clip(grupo, col_w * 2 - 4, 6.5, "Helvetica-Bold"))
                c.setFillColor(COLOR_ROJO)
                c.setFont("Helvetica-Bold", 7)
                c.drawCentredString(x + col_w / 2, y - alto - 0.18 * cm, _clip(anio, col_w - 2, 7, "Helvetica-Bold"))
                c.setFillColor(COLOR_MUTED)
                c.setFont("Helvetica", 7)
                c.drawCentredString(x + col_w + col_w / 2, y - alto - 0.18 * cm, _clip(anio_ant, col_w - 2, 7))
                c.setFillColor(COLOR_TINTA)
                x += col_w * 2
            self.y = y - alto * 2

        encabezado()
        familias = matriz.get("familias") or [{"familia": "", "filas": filas}]
        for bloque in familias:
            if not bloque.get("filas"):
                continue
            if self.y - alto * 4 < 1.3 * cm:
                self.nueva()
                encabezado()
            y = self.y
            c.setFillColor(COLOR_TINTA)
            c.rect(MARGIN, y - alto + 2, PAGE_W - 2 * MARGIN, alto, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(MARGIN + 4, y - 0.24 * cm, bloque.get("familia") or "Sin familia")
            self.y = y - alto
            for fila in bloque["filas"]:
                if self.y - alto * 3 < 1.3 * cm:
                    self.nueva()
                    encabezado()
                    y = self.y
                    c.setFillColor(COLOR_TINTA)
                    c.rect(MARGIN, y - alto + 2, PAGE_W - 2 * MARGIN, alto, fill=1, stroke=0)
                    c.setFillColor(colors.white)
                    c.setFont("Helvetica-Bold", 8)
                    c.drawString(MARGIN + 4, y - 0.24 * cm, bloque.get("familia") or "Sin familia")
                    self.y = y - alto
                metricas = [("($)", "neto", True), ("(Und)", "cantidad", False), ("$/Und", "precio", True)]
                for mi, (label, clave, es_peso) in enumerate(metricas):
                    y = self.y
                    if mi == 0:
                        c.setFillColor(colors.Color(0.96, 0.97, 0.98))
                        c.rect(MARGIN, y - alto + 2, PAGE_W - 2 * MARGIN, alto, fill=1, stroke=0)
                        c.setFillColor(COLOR_TINTA)
                        c.setFont("Helvetica-Bold", 6.5)
                        c.drawString(MARGIN + 2, y - 0.22 * cm, _clip(fila.get("producto"), nombre_w - 4, 6.5, "Helvetica-Bold"))
                    c.setFillColor(COLOR_MUTED)
                    c.setFont("Helvetica", 6)
                    c.drawString(MARGIN + nombre_w + 2, y - 0.22 * cm, label)
                    x = MARGIN + nombre_w + metric_w
                    for par in fila.get("pares") or []:
                        for lado, color in (("actual", COLOR_TINTA), ("anterior", COLOR_MUTED)):
                            bruto = (par.get(lado) or {}).get(clave)
                            if clave == "precio" and bruto is None:
                                texto = "—"
                            elif es_peso:
                                texto = dinero_presentacion(bruto)
                            else:
                                texto = metrico_presentacion(bruto)
                            c.setFillColor(color)
                            c.setFont("Helvetica", 6)
                            c.drawCentredString(x + col_w / 2, y - 0.22 * cm, _clip(texto, col_w - 2, 6))
                            x += col_w
                    self.y -= alto
                self.y -= 0.04 * cm

    def _tabla(self, headers, filas, cols, ultima_negrita=False):
        alto = 0.42 * cm
        c = self.c
        for idx, fila in enumerate([headers] + filas):
            if self.y - alto < 1.3 * cm:
                self.nueva()
            y = self.y
            es_header = idx == 0
            negrita = es_header or (ultima_negrita and idx == len(filas))
            if es_header or negrita:
                c.setFillColor(colors.Color(0.96, 0.93, 0.93) if es_header else colors.Color(0.98, 0.96, 0.96))
                c.rect(MARGIN, y - alto + 2, sum(cols), alto, fill=1, stroke=0)
            c.setStrokeColor(COLOR_LINEA)
            c.line(MARGIN, y - alto + 2, MARGIN + sum(cols), y - alto + 2)
            x = MARGIN
            for i, celda in enumerate(fila):
                if not es_header and i == len(fila) - 1 and celda in ("Sube", "Baja", "Igual"):
                    c.setFillColor(_color_var(1 if celda == "Sube" else (-1 if celda == "Baja" else 0)))
                else:
                    c.setFillColor(COLOR_TEXTO)
                c.setFont("Helvetica-Bold" if negrita else "Helvetica", 7.5)
                c.drawString(x + 2, y - 0.26 * cm, _clip(str(celda), cols[i] - 4, 7.5, "Helvetica-Bold" if negrita else "Helvetica"))
                x += cols[i]
            self.y -= alto
        self.y -= 0.3 * cm

    def cerrar(self):
        self._footer()
        self.c.save()


def generar_pdf_ventas(datos: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pdf = _Pdf(path, datos)
    pdf.portada()
    pdf.macro()
    pdf.comparativo_semana()
    pdf.tendencias()
    pdf.matriz()
    pdf.cerrar()
