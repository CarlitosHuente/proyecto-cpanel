"""
Plantilla HTML reutilizable para reportes por correo (Alertas Buk y futuros módulos).

Estilo email-safe: tablas + estilos inline (Gmail/Outlook).
"""

from __future__ import annotations

import html
from typing import Iterable, List, Optional, Sequence, Tuple

# Paleta Huente (correo claro, no flat)
_COLOR_HEADER = "#1b4332"
_COLOR_HEADER_ACCENT = "#2d6a4f"
_COLOR_BORDER = "#d8e2dc"
_COLOR_BG = "#f6f8f7"
_COLOR_CARD = "#ffffff"
_COLOR_TEXT = "#1f2933"
_COLOR_MUTED = "#5c6b73"
_COLOR_WARN_BG = "#fff8e6"
_COLOR_WARN_BORDER = "#e6c35c"
_COLOR_TH = "#e8f0ec"
_COLOR_ROW_ALT = "#f3f7f5"


def esc(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _meta_table(rows: Sequence[Tuple[str, str]]) -> str:
    cells = []
    for label, value in rows:
        cells.append(
            "<tr>"
            f'<td style="padding:8px 12px;border-bottom:1px solid {_COLOR_BORDER};'
            f'color:{_COLOR_MUTED};font-size:13px;width:38%;">{esc(label)}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {_COLOR_BORDER};'
            f'color:{_COLOR_TEXT};font-size:13px;font-weight:600;">{esc(value)}</td>'
            "</tr>"
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;background:{_COLOR_CARD};'
        f'border:1px solid {_COLOR_BORDER};border-radius:6px;">'
        + "".join(cells)
        + "</table>"
    )


def _data_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    empty_msg: str = "Sin registros",
    nowrap_cols: Optional[Sequence[int]] = None,
) -> str:
    nowrap = set(nowrap_cols or [])
    thead = "".join(
        f'<th style="padding:9px 10px;text-align:left;font-size:12px;color:{_COLOR_HEADER};'
        f'background:{_COLOR_TH};border-bottom:2px solid {_COLOR_HEADER_ACCENT};'
        f'white-space:nowrap;">{esc(h)}</th>'
        for h in headers
    )
    if not rows:
        body = (
            f'<tr><td colspan="{len(headers)}" style="padding:14px 10px;text-align:center;'
            f'color:{_COLOR_MUTED};font-size:13px;">{esc(empty_msg)}</td></tr>'
        )
    else:
        parts = []
        for i, row in enumerate(rows):
            bg = _COLOR_CARD if i % 2 == 0 else _COLOR_ROW_ALT
            tds = []
            for col_i, cell in enumerate(row):
                ws = "white-space:nowrap;" if col_i in nowrap else "white-space:normal;"
                tds.append(
                    f'<td style="padding:8px 10px;border-bottom:1px solid {_COLOR_BORDER};'
                    f'font-size:13px;color:{_COLOR_TEXT};vertical-align:top;{ws}">{esc(cell)}</td>'
                )
            parts.append(f'<tr style="background:{bg};">{"".join(tds)}</tr>')
        body = "".join(parts)

    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;border:1px solid {_COLOR_BORDER};'
        f'border-radius:6px;overflow:hidden;background:{_COLOR_CARD};">'
        f"<thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>"
    )


def seccion_tabla(
    titulo: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    badge_count: Optional[int] = None,
    accent: str = _COLOR_HEADER_ACCENT,
    nowrap_cols: Optional[Sequence[int]] = None,
) -> str:
    count = badge_count if badge_count is not None else len(rows)
    badge = (
        f'<span style="display:inline-block;margin-left:8px;padding:2px 8px;'
        f"border-radius:999px;background:{accent};color:#fff;font-size:12px;"
        f'font-weight:700;">{count}</span>'
    )
    return (
        f'<div style="margin:22px 0 8px 0;">'
        f'<h3 style="margin:0 0 10px 0;font-size:15px;color:{_COLOR_HEADER};'
        f'font-family:Arial,Helvetica,sans-serif;">{esc(titulo)}{badge}</h3>'
        f"{_data_table(headers, rows, nowrap_cols=nowrap_cols)}"
        f"</div>"
    )


def envolver_reporte_html(
    titulo: str,
    *,
    subtitulo: str = "",
    meta: Optional[Sequence[Tuple[str, str]]] = None,
    aviso: str = "",
    secciones_html: Iterable[str] = (),
    pie: str = "Huente CPanel",
) -> str:
    """Envoltura común para reportes HTML por correo."""
    meta_block = _meta_table(meta) if meta else ""
    aviso_block = ""
    if aviso:
        aviso_block = (
            f'<div style="margin:14px 0;padding:10px 12px;background:{_COLOR_WARN_BG};'
            f"border:1px solid {_COLOR_WARN_BORDER};border-radius:6px;"
            f'color:{_COLOR_TEXT};font-size:13px;">{esc(aviso)}</div>'
        )
    secciones = "\n".join(secciones_html)

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{_COLOR_BG};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_COLOR_BG};">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
        style="max-width:720px;border-collapse:collapse;background:{_COLOR_CARD};
        border:1px solid {_COLOR_BORDER};border-radius:10px;overflow:hidden;
        font-family:Arial,Helvetica,sans-serif;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
        <tr>
          <td style="background:{_COLOR_HEADER};padding:18px 22px;">
            <div style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;
              color:#b7e4c7;font-weight:700;">Huentelauquen</div>
            <div style="font-size:20px;color:#ffffff;font-weight:700;margin-top:4px;">{esc(titulo)}</div>
            {f'<div style="font-size:13px;color:#d8f3dc;margin-top:6px;">{esc(subtitulo)}</div>' if subtitulo else ''}
          </td>
        </tr>
        <tr>
          <td style="padding:18px 22px 8px 22px;">
            {meta_block}
            {aviso_block}
            {secciones}
          </td>
        </tr>
        <tr>
          <td style="padding:14px 22px 20px 22px;border-top:1px solid {_COLOR_BORDER};
            color:{_COLOR_MUTED};font-size:12px;">
            {esc(pie)}
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
