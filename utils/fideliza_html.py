"""Textos legales y diseño del correo de fidelización."""

from __future__ import annotations

import io
import re
import secrets
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from utils.fideliza_db import FidelizaError

CARPETA_IMAGENES = Path(__file__).resolve().parents[1] / "uploads" / "fideliza"
SITIO_PUBLICO = "https://datoshuente.com"
MAX_HTML = 150_000
MAX_ETIQUETA = 240
MAX_ASUNTO = 180

ETIQUETA_PUNTOS = "Acepto las bases del programa de puntos."
ETIQUETA_CONF = (
    "Acepto las bases de confidencialidad y el uso de mis datos "
    "para enviarme correos publicitarios."
)
ASUNTO_DEFECTO = "Tus puntos en Huentelauquen"
COLOR_FRANJA = "#c1121f"
_VERDE_FRANJA = "#1b4332"

BASES_PUNTOS = """
<h2>Bases del programa de puntos</h2>
<p>Estas bases regulan el programa de puntos de Huentelauquen. Al crear la cuenta las aceptas.</p>
<h3>Cómo se suman</h3>
<p>Los puntos se cargan en el local, cuando acercas el teléfono al cartel y la caja registra la compra. El saldo es el mismo en todas las sucursales.</p>
<h3>Canje</h3>
<p>Los premios y la cantidad de puntos de cada uno se informan en el local y en el correo. El canje se hace en caja y descuenta los puntos del saldo.</p>
<h3>Vigencia</h3>
<p>Los puntos no son dinero ni se canjean por efectivo. Huentelauquen puede actualizar premios, botones y estas bases. Los cambios quedan publicados en esta misma página.</p>
""".strip()

BASES_CONF = """
<h2>Confidencialidad y correos</h2>
<p>Huentelauquen usa tu nombre, RUT y correo para identificarte en el programa de puntos y avisarte cada movimiento de tu saldo.</p>
<h3>Correos publicitarios</h3>
<p>También aceptas que usemos esos datos para enviarte novedades, promociones y otras comunicaciones comerciales de Huentelauquen.</p>
<p>Si más adelante no quieres recibir publicidad, puedes pedirlo en el local.</p>
""".strip()

CORREO_DEFECTO = """
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f7f5;">
<tr><td align="center" style="padding:16px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#ffffff;">
<tr><td data-franja="1" bgcolor="#c1121f" style="background-color:#c1121f;color:#ffffff;padding:20px;font-family:Arial,sans-serif;">
<div style="font-size:12px;letter-spacing:1px;">HUENTELAUQUEN</div>
<div style="font-size:22px;font-weight:bold;">Tus puntos</div>
</td></tr>
<tr><td style="padding:20px;font-family:Arial,sans-serif;color:#1f2933;font-size:16px;line-height:1.45;">
<p>Hola {{nombre}},</p>
<p>Actualizamos tus puntos en Huentelauquen.</p>
<p><strong>Fecha:</strong> {{fecha}}<br>
<strong>Sucursal:</strong> {{sucursal}}<br>
<strong>Movimiento:</strong> {{movimiento}}<br>
<strong>Detalle:</strong> {{detalle}}<br>
<strong>Puntos:</strong> {{puntos}}<br>
<strong>Saldo:</strong> {{saldo}}</p>
{{premios}}
</td></tr>
<tr><td style="padding:12px 20px 20px;color:#64748b;font-size:12px;font-family:Arial,sans-serif;">Huentelauquen</td></tr>
</table>
</td></tr>
</table>
""".strip()

_VARIABLES = ("nombre", "fecha", "movimiento", "detalle", "puntos", "saldo", "sucursal", "premios")
_SKIP = {"script", "style", "iframe", "object", "embed", "form", "input", "button", "textarea", "link", "meta", "svg"}
_VOID = {"br", "hr", "img"}
_TAGS = _VOID | {
    "p", "div", "span", "h1", "h2", "h3", "h4", "strong", "b", "em", "i", "u", "s", "strike",
    "ul", "ol", "li", "a", "blockquote", "table", "thead", "tbody", "tr", "th", "td",
    "sub", "sup", "font", "figure", "figcaption",
}
_PROPS = {
    "color", "background", "background-color", "font-size", "font-weight", "font-style",
    "font-family", "text-align", "text-decoration", "margin", "margin-top", "margin-bottom",
    "margin-left", "margin-right", "padding", "padding-top", "padding-bottom",
    "padding-left", "padding-right", "border", "border-top", "border-bottom", "border-radius",
    "width", "max-width", "height", "line-height", "letter-spacing", "page-break-before",
    "page-break-after", "display", "vertical-align", "border-collapse", "float", "clear",
}
_FUENTES = {"arial", "georgia", "verdana", "tahoma", "courier new", "sans-serif", "serif", "monospace"}
_MIME = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}


def _estilo(raw: str) -> str:
    partes = []
    for decl in (raw or "").split(";"):
        if ":" not in decl:
            continue
        prop, val = decl.split(":", 1)
        prop = prop.strip().lower()
        val = " ".join(val.strip().split())
        if prop not in _PROPS or not val:
            continue
        if not re.fullmatch(r"[#a-zA-Z0-9().,%\s\-]+", val):
            continue
        bajo = val.lower()
        if "url" in bajo or "expression" in bajo or "javascript" in bajo:
            continue
        partes.append(f"{prop}:{val}")
    return ";".join(partes)


def _url(val: str, imagen: bool = False) -> str:
    val = (val or "").strip().replace("\x00", "").replace(" ", "")
    if not val or len(val) > 500:
        return ""
    bajo = val.lower()
    if bajo.startswith(("javascript:", "data:", "vbscript:")):
        return ""
    if val.startswith("/fideliza/correo-img/") and ".." not in val:
        return val
    if not imagen and val.startswith("/") and not val.startswith("//") and ".." not in val:
        return val
    partes = urlsplit(val)
    if partes.scheme in ("https", "http") and partes.netloc:
        return val
    if not imagen and partes.scheme in ("mailto", "tel") and partes.path:
        return val
    return ""


def _attr(tag: str, attrs) -> str:
    limpio = []
    vistos = {}
    for nombre, valor in attrs:
        if not nombre:
            continue
        clave = nombre.lower()
        if clave.startswith("on"):
            continue
        vistos[clave] = valor or ""
    estilo = _estilo(vistos.get("style", ""))
    if estilo:
        limpio.append(("style", estilo))
    if tag == "a":
        href = _url(vistos.get("href", ""))
        if href:
            limpio.append(("href", href))
            if (vistos.get("target") or "").lower() == "_blank":
                limpio.append(("target", "_blank"))
                limpio.append(("rel", "noopener noreferrer"))
    elif tag == "img":
        src = _url(vistos.get("src", ""), imagen=True)
        if not src:
            return ""
        limpio.append(("src", src))
        alt = re.sub(r"\s+", " ", unescape(vistos.get("alt", ""))).strip()[:180]
        limpio.append(("alt", alt))
        for clave in ("width", "height"):
            if re.fullmatch(r"\d{1,4}", vistos.get(clave, "")):
                limpio.append((clave, vistos[clave]))
    elif tag in ("td", "th", "tr", "table", "p", "div", "h1", "h2", "h3", "h4"):
        align = (vistos.get("align") or "").lower()
        if align in ("left", "center", "right", "justify"):
            limpio.append(("align", align))
        if tag in ("td", "th"):
            valign = (vistos.get("valign") or "").lower()
            if valign in ("top", "middle", "bottom"):
                limpio.append(("valign", valign))
            bgcolor = vistos.get("bgcolor", "")
            if re.fullmatch(r"#[0-9a-fA-F]{3,8}", bgcolor):
                limpio.append(("bgcolor", bgcolor))
            if tag == "td" and vistos.get("data-franja") == "1":
                limpio.append(("data-franja", "1"))
            for clave in ("colspan", "rowspan"):
                if re.fullmatch(r"[1-6]", vistos.get(clave, "")):
                    limpio.append((clave, vistos[clave]))
        if tag == "table":
            if (vistos.get("role") or "").lower() == "presentation":
                limpio.append(("role", "presentation"))
            for clave in ("cellpadding", "cellspacing", "border"):
                if re.fullmatch(r"\d{1,2}", vistos.get(clave, "")):
                    limpio.append((clave, vistos[clave]))
            if re.fullmatch(r"\d{1,4}%?", vistos.get("width", "")):
                limpio.append(("width", vistos["width"]))
        elif re.fullmatch(r"\d{1,4}%?", vistos.get("width", "")):
            limpio.append(("width", vistos["width"]))
    elif tag == "font":
        size = vistos.get("size", "")
        if re.fullmatch(r"[1-7]", size):
            limpio.append(("size", size))
        color = vistos.get("color", "")
        if re.fullmatch(r"#[0-9a-fA-F]{3,8}", color):
            limpio.append(("color", color))
        face = (vistos.get("face") or "").strip().lower()
        if face in _FUENTES:
            limpio.append(("face", face))
    elif tag == "div" or tag == "span":
        pass
    if tag == "span" and vistos.get("data-var", "") in _VARIABLES:
        limpio.append(("data-var", vistos["data-var"]))
    if tag == "div" and vistos.get("data-salto") == "1":
        limpio.append(("data-salto", "1"))
    if tag == "img" and not any(item[0] == "src" for item in limpio):
        return ""
    return "".join(f' {clave}="{escape(valor, quote=True)}"' for clave, valor in limpio)


class _Limpiar(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        tag = (tag or "").lower()
        if self.skip:
            if tag in _SKIP:
                self.skip += 1
            return
        if tag in _SKIP:
            self.skip += 1
            return
        if tag not in _TAGS:
            return
        attrs_html = _attr(tag, attrs)
        if tag == "img" and "src=" not in attrs_html:
            return
        self.out.append(f"<{tag}{attrs_html}>")

    def handle_endtag(self, tag):
        tag = (tag or "").lower()
        if tag in _SKIP:
            if self.skip:
                self.skip -= 1
            return
        if self.skip or tag not in _TAGS or tag in _VOID:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip or not data:
            return
        self.out.append(escape(data))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def sanitizar(html: str) -> str:
    parser = _Limpiar()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        return ""
    return "".join(parser.out).strip()[:MAX_HTML]


def _texto_plano(valor: str, limite: int) -> str:
    valor = re.sub(r"\s+", " ", unescape(valor or "")).strip()
    return valor[:limite]


def guardar_legales(etiqueta_puntos: str, bases_puntos: str) -> None:
    from utils.fideliza_db import _guardar_columnas

    _guardar_columnas(
        {
            "etiqueta_puntos": _texto_plano(etiqueta_puntos, MAX_ETIQUETA) or None,
            "bases_puntos": sanitizar(bases_puntos) or None,
        }
    )


def color_franja(raw: str | None) -> str:
    valor = (raw or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", valor):
        return valor.lower()
    return COLOR_FRANJA


def _pintar_td(tag: str, color: str) -> str:
    if re.search(r"background-color\s*:", tag, re.I):
        tag = re.sub(
            r"background-color\s*:\s*[^;\"']+",
            f"background-color:{color}",
            tag,
            count=1,
            flags=re.I,
        )
    elif re.search(r"style\s*=", tag, re.I):
        tag = re.sub(r'style="', f'style="background-color:{color};', tag, count=1, flags=re.I)
    else:
        tag = tag[:-1] + f' style="background-color:{color};color:#ffffff;">'
    if re.search(r"bgcolor\s*=", tag, re.I):
        tag = re.sub(r'bgcolor="[^"]*"', f'bgcolor="{color}"', tag, count=1, flags=re.I)
    else:
        tag = tag[:-1] + f' bgcolor="{color}">'
    return tag


def aplicar_franja(html: str, color: str | None) -> str:
    """Pinta la barra superior del correo. La primera franja verde antigua también cuenta."""
    color = color_franja(color)
    origen = html or ""
    if 'data-franja="1"' not in origen.lower():
        def marcar(match):
            tag = match.group(0)
            if marcar.listo:
                return tag
            if re.search(rf"background(?:-color)?\s*:\s*{_VERDE_FRANJA}", tag, re.I) or re.search(
                rf'bgcolor="{_VERDE_FRANJA}"', tag, re.I
            ):
                marcar.listo = True
                if "data-franja" not in tag.lower():
                    tag = tag[:-1] + ' data-franja="1">'
            return tag

        marcar.listo = False
        origen = re.sub(r"<td\b[^>]*>", marcar, origen, flags=re.I)

    def pintar(match):
        tag = match.group(0)
        if 'data-franja="1"' not in tag.lower():
            return tag
        return _pintar_td(tag, color)

    return re.sub(r"<td\b[^>]*>", pintar, origen, flags=re.I)


def guardar_color_correo(color: str) -> None:
    from utils.fideliza_db import _guardar_columnas

    if not re.fullmatch(r"#[0-9a-fA-F]{6}", (color or "").strip()):
        raise FidelizaError("Elige un color para la franja del correo.")
    _guardar_columnas({"correo_color": color.strip().lower()})


def guardar_correo(asunto: str, html: str) -> None:
    from utils.fideliza_db import _guardar_columnas

    limpio = sanitizar(html)
    _guardar_columnas(
        {
            "correo_asunto": _texto_plano(asunto, MAX_ASUNTO) or None,
            "correo_html": limpio or None,
        }
    )


def editor_textos(row: dict) -> dict:
    color = color_franja(row.get("correo_color"))
    return {
        "etiqueta_puntos": row.get("etiqueta_puntos") or ETIQUETA_PUNTOS,
        "bases_puntos": row.get("bases_puntos") or BASES_PUNTOS,
        "etiqueta_conf": row.get("etiqueta_confidencialidad") or ETIQUETA_CONF,
        "bases_conf": row.get("bases_confidencialidad") or BASES_CONF,
        "asunto": row.get("correo_asunto") or ASUNTO_DEFECTO,
        "correo": aplicar_franja(row.get("correo_html") or CORREO_DEFECTO, color),
        "correo_activo": bool((row.get("correo_html") or "").strip()),
        "correo_color": color,
    }


def legales_publicos(row: dict) -> dict:
    editor = editor_textos(row or {})
    return {
        "etiqueta_puntos": editor["etiqueta_puntos"],
        "bases_puntos": sanitizar(editor["bases_puntos"]) or sanitizar(BASES_PUNTOS),
        "etiqueta_conf": editor["etiqueta_conf"],
        "bases_conf": sanitizar(editor["bases_conf"]) or sanitizar(BASES_CONF),
    }


def _cuando(valor) -> str:
    if not valor:
        return ""
    return valor.strftime("%d/%m/%Y %H:%M")


def _tipo(tipo: str) -> str:
    return {"acumulacion": "Suma de puntos", "canje": "Canje", "anulacion": "Anulación"}.get(tipo or "", tipo or "")


def _premios(premios: list) -> tuple[str, str]:
    if not premios:
        return "", ""
    items_html = []
    lineas = []
    for premio in premios:
        nombre = str(premio.get("nombre") or "")
        costo = int(premio.get("puntos") or 0)
        if premio.get("listo"):
            estado = "Ya puedes canjearlo"
        else:
            estado = f"Te faltan {int(premio.get('faltan') or 0)} puntos"
        items_html.append(
            f"<li><strong>{escape(nombre)}</strong> ({costo} puntos): {escape(estado)}</li>"
        )
        lineas.append(f"{nombre} ({costo} puntos): {estado}")
    html = "<p><strong>Premios</strong></p><ul>" + "".join(items_html) + "</ul>"
    return html, "\n".join(lineas)


def variables_desde_aviso(aviso: dict) -> dict:
    mov = aviso["mov"]
    puntos = int(mov["puntos"])
    premios_html, premios_texto = _premios(aviso.get("premios") or [])
    return {
        "nombre": escape(str(mov.get("nombre") or "")),
        "fecha": escape(_cuando(mov.get("creado_at"))),
        "movimiento": escape(_tipo(mov.get("tipo"))),
        "detalle": escape(str(mov.get("detalle") or "")),
        "puntos": escape(f"+{puntos}" if puntos > 0 else str(puntos)),
        "saldo": escape(str(mov.get("saldo_despues") if mov.get("saldo_despues") is not None else "")),
        "sucursal": escape((mov.get("sucursal") or "").strip() or "Huentelauquen"),
        "premios_html": premios_html,
        "premios_texto": premios_texto,
        "nombre_texto": str(mov.get("nombre") or ""),
        "fecha_texto": _cuando(mov.get("creado_at")),
        "movimiento_texto": _tipo(mov.get("tipo")),
        "detalle_texto": str(mov.get("detalle") or ""),
        "puntos_texto": f"+{puntos}" if puntos > 0 else str(puntos),
        "saldo_texto": str(mov.get("saldo_despues") if mov.get("saldo_despues") is not None else ""),
        "sucursal_texto": (mov.get("sucursal") or "").strip() or "Huentelauquen",
    }


def variables_de_prueba(premios: list) -> dict:
    aviso = {
        "mov": {
            "nombre": "Ana Pérez",
            "creado_at": None,
            "tipo": "acumulacion",
            "detalle": "Compra 12",
            "puntos": 2,
            "saldo_despues": 5,
            "sucursal": "Costanera",
        },
        "premios": premios,
    }
    datos = variables_desde_aviso(aviso)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    fecha = datetime.now(ZoneInfo("America/Santiago")).strftime("%d/%m/%Y %H:%M")
    datos["fecha"] = escape(fecha)
    datos["fecha_texto"] = fecha
    return datos


def _aplicar(plantilla: str, valores: dict, html_mode: bool) -> str:
    def reemplazo(match):
        clave = match.group(1).lower()
        if clave == "premios":
            return valores["premios_html"] if html_mode else valores["premios_texto"]
        sufijo = "" if html_mode else "_texto"
        return valores.get(f"{clave}{sufijo}", "")

    return re.sub(
        r"\{\{\s*(" + "|".join(_VARIABLES) + r")\s*\}\}",
        reemplazo,
        plantilla or "",
        flags=re.I,
    )


def html_a_texto(html: str) -> str:
    texto = re.sub(r"(?i)<br\s*/?>", "\n", html or "")
    texto = re.sub(r"(?i)</p>|</h[1-4]>|</tr>|</div>", "\n", texto)
    texto = re.sub(r"(?i)</li>", "\n", texto)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = unescape(texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def ruta_imagen(nombre: str) -> Path | None:
    if not re.fullmatch(r"[a-f0-9]{24}\.(jpg|png|gif|webp)", nombre or ""):
        return None
    path = CARPETA_IMAGENES / nombre
    if not path.is_file():
        return None
    return path


def mime_imagen(nombre: str) -> str:
    return _MIME.get(nombre.rsplit(".", 1)[-1], "application/octet-stream")


def _ext_de_bytes(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return ""


def guardar_imagen(archivo) -> str:
    if not archivo or not getattr(archivo, "filename", ""):
        raise FidelizaError("Elige una imagen.")
    data = archivo.read()
    if not data:
        raise FidelizaError("La imagen está vacía.")
    if len(data) > 3_000_000:
        raise FidelizaError("La imagen supera 3 MB.")
    ext = _ext_de_bytes(data)
    if not ext:
        raise FidelizaError("Usa JPG, PNG, GIF o WEBP.")
    data, ext = _reducir(data, ext)
    CARPETA_IMAGENES.mkdir(parents=True, exist_ok=True)
    nombre = secrets.token_hex(12) + "." + ext
    (CARPETA_IMAGENES / nombre).write_bytes(data)
    return nombre


def _reducir(data: bytes, ext: str) -> tuple[bytes, str]:
    if ext in ("gif", "webp"):
        if len(data) > 2_500_000:
            raise FidelizaError("Esa imagen es muy pesada.")
        return data, ext
    try:
        from PIL import Image
    except ImportError:
        if len(data) > 2_000_000:
            raise FidelizaError("La imagen supera 2 MB.")
        return data, ext
    try:
        imagen = Image.open(io.BytesIO(data))
        imagen.load()
        if max(imagen.size) > 8000:
            raise FidelizaError("La imagen es demasiado grande.")
        if imagen.width > 1400:
            alto = max(1, round(imagen.height * 1400 / imagen.width))
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            imagen = imagen.resize((1400, alto), resample)
        salida = io.BytesIO()
        if ext == "png":
            imagen.save(salida, format="PNG", optimize=True)
            return salida.getvalue(), "png"
        if imagen.mode != "RGB":
            imagen = imagen.convert("RGB")
        imagen.save(salida, format="JPEG", quality=85, optimize=True)
        return salida.getvalue(), "jpg"
    except FidelizaError:
        raise
    except Exception as exc:
        raise FidelizaError("No se pudo leer la imagen.") from exc


def _cid(html: str) -> tuple[str, list]:
    inline = []
    vistos = {}

    def reemplazo(match):
        src = match.group(1)
        nombre = src.rsplit("/", 1)[-1]
        if nombre not in vistos:
            path = ruta_imagen(nombre)
            if not path:
                return match.group(0)
            cid = f"fid{len(vistos) + 1}"
            vistos[nombre] = cid
            inline.append((cid, path.read_bytes(), mime_imagen(nombre)))
        return f'src="cid:{vistos[nombre]}"'

    return re.sub(r'src="(/fideliza/correo-img/[^"]+)"', reemplazo, html), inline


def _absolutas(html: str, base: str) -> str:
    def reemplazo(match):
        attr, url = match.group(1), match.group(2)
        if url.startswith("//"):
            return match.group(0)
        return f'{attr}="{base}{url}"'

    return re.sub(r'(href|src)="(/[^"]*)"', reemplazo, html)


def url_publica() -> str:
    try:
        from flask import has_request_context, request

        if has_request_context():
            host = request.host or ""
            if host.startswith("127.") or "localhost" in host:
                return SITIO_PUBLICO
            return request.url_root.rstrip("/")
    except Exception:
        pass
    return SITIO_PUBLICO


def armar_correo(asunto: str, html: str, valores: dict, base: str | None = None, color: str | None = None) -> dict:
    cuerpo_base = aplicar_franja(sanitizar(html) or sanitizar(CORREO_DEFECTO), color)
    cuerpo = _aplicar(cuerpo_base, valores, True)
    cuerpo, inline = _cid(cuerpo)
    cuerpo = _absolutas(cuerpo, (base or url_publica()).rstrip("/"))
    tema = _aplicar(_texto_plano(asunto, MAX_ASUNTO) or ASUNTO_DEFECTO, valores, False)
    tema = re.sub(r"\s+", " ", tema).strip()[:MAX_ASUNTO] or ASUNTO_DEFECTO
    return {
        "asunto": tema,
        "texto": html_a_texto(_aplicar(cuerpo_base, valores, False)),
        "html": cuerpo,
        "inline": inline,
    }
