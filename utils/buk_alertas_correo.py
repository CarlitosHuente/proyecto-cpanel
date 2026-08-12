"""Armar y enviar resumen de alertas Buk por correo."""

from __future__ import annotations

from typing import List, Optional, Tuple

from utils.buk_alertas import reporte_alertas_mes
from utils.mail_reporte_html import envolver_reporte_html, seccion_tabla
from utils.mail_smtp import enviar_correo, smtp_configurado
from utils.notificaciones_config import emails_seccion

_TITULOS: Tuple[Tuple[str, str, str], ...] = (
    ("sin_turno_mes", "Sin turno en el mes", "#9b2226"),
    ("sin_marca", "Turno sin marcaje", "#9b2226"),
    ("atraso_entrada", "Entrada tarde (>1 h)", "#bc6c25"),
    ("salida_anticipada", "Salida anticipada (>1 h)", "#2a6f97"),
    ("marcaje_descanso", "Marcaje en día descanso", "#495057"),
    ("jornada_abierta", "Jornada abierta (sin salida)", "#bc6c25"),
)

_HEADERS = ("Fecha", "Colaborador", "RUT", "Sucursal", "Detalle")


def _items_pendientes(grupos: dict, key: str) -> List[dict]:
    return [a for a in (grupos.get(key) or []) if not a.get("revisada")]


def _filas(items: List[dict]) -> List[List[str]]:
    rows = []
    for a in items:
        rows.append(
            [
                a.get("fecha_txt") or "—",
                a.get("nombre") or "—",
                a.get("rut") or "—",
                a.get("obra_nombre") or "—",
                a.get("detalle") or "",
            ]
        )
    return rows


def formatear_cuerpo(resultado: dict) -> str:
    """Fallback texto plano (clientes sin HTML)."""
    mes_label = resultado.get("mes_label") or "Mes"
    lineas = [
        f"Alertas Buk — {mes_label}",
        f"Periodo evaluado: {resultado.get('periodo_desde')} → {resultado.get('periodo_hasta')}",
        f"Corte (ayer): {resultado.get('fecha_corte')}",
        f"Pendientes: {resultado.get('total_pendientes')}",
        f"Vigentes: {resultado.get('total_vigentes')} · Con turno en mes: {resultado.get('vigentes_con_turno_mes')}",
        "",
        "Solo se incluyen alertas no revisadas.",
        "",
    ]
    grupos = resultado.get("grupos") or {}
    for key, titulo, _accent in _TITULOS:
        items = _items_pendientes(grupos, key)
        lineas.append(f"{titulo} ({len(items)})")
        if not items:
            lineas.append("  (ninguna)")
        else:
            for a in items:
                lineas.append(
                    f"  • {a.get('fecha_txt') or '—'} | {a.get('nombre') or '—'} "
                    f"({a.get('rut') or ''}) | {a.get('obra_nombre') or '—'} | {a.get('detalle') or ''}"
                )
        lineas.append("")
    lineas.append("— Huentelauquen · Alertas Buk")
    return "\n".join(lineas)


def formatear_html(resultado: dict) -> str:
    mes_label = resultado.get("mes_label") or "Mes"
    grupos = resultado.get("grupos") or {}
    secciones = []
    for key, titulo, accent in _TITULOS:
        items = _items_pendientes(grupos, key)
        secciones.append(
            seccion_tabla(
                titulo,
                _HEADERS,
                _filas(items),
                badge_count=len(items),
                accent=accent,
                nowrap_cols=(0, 2),  # Fecha y RUT en una sola línea
            )
        )

    meta = [
        ("Periodo evaluado", f"{resultado.get('periodo_desde')} → {resultado.get('periodo_hasta')}"),
        ("Corte (ayer)", str(resultado.get("fecha_corte") or "—")),
        ("Pendientes", str(resultado.get("total_pendientes") or 0)),
        (
            "Nómina",
            f"{resultado.get('total_vigentes') or 0} vigentes · "
            f"{resultado.get('vigentes_con_turno_mes') or 0} con turno en el mes",
        ),
    ]
    if resultado.get("obra_id"):
        meta.append(("Filtro sucursal", str(resultado.get("obra_id"))))

    return envolver_reporte_html(
        f"Alertas Buk — {mes_label}",
        subtitulo="Resumen de asistencia y turnos",
        meta=meta,
        aviso="Solo se incluyen alertas no revisadas.",
        secciones_html=secciones,
        pie="Huentelauquen · CPanel · Alertas Buk",
    )


def enviar_alertas_buk(
    anio: int,
    mes: int,
    obra_id: Optional[str] = None,
) -> dict:
    """
    Genera reporte (sin revisadas) y lo envía a destinarios de Config → Notificaciones.
    """
    destinarios = emails_seccion("buk_alertas")
    if not destinarios:
        return {
            "ok": False,
            "error": "No hay correos configurados. Vaya a Configuración → Notificaciones.",
            "destinos": [],
        }
    if not smtp_configurado():
        return {
            "ok": False,
            "error": "Correo de salida no configurado (IMAP_* o SMTP_*).",
            "destinos": destinarios,
        }

    resultado = reporte_alertas_mes(anio, mes, obra_id, incluir_revisadas=False)
    if not resultado.get("ok"):
        return {
            "ok": False,
            "error": resultado.get("error") or "No se pudo generar el reporte de alertas.",
            "destinos": destinarios,
        }

    mes_label = resultado.get("mes_label") or f"{anio}-{mes:02d}"
    asunto = f"Alertas Buk — {mes_label}"
    if obra_id:
        asunto += " (sucursal filtrada)"
    cuerpo = formatear_cuerpo(resultado)
    html = formatear_html(resultado)
    envio = enviar_correo(destinarios, asunto, cuerpo, html=html)
    envio["total_pendientes"] = resultado.get("total_pendientes")
    envio["mes_label"] = mes_label
    return envio
