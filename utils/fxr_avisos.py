"""Avisos por correo al dueño de una rendición FxR."""
from __future__ import annotations

from typing import Optional

from utils.mail_smtp import enviar_correo, smtp_configurado


def avisar_dueno_fxr(
    destinatario: str,
    asunto: str,
    cuerpo: str,
) -> dict:
    """Envía correo al dueño; no falla la operación si SMTP no está configurado."""
    dest = (destinatario or "").strip()
    if not dest or "@" not in dest:
        return {"ok": False, "error": "Sin destinatario", "omitido": True}
    if not smtp_configurado():
        return {"ok": False, "error": "SMTP no configurado", "omitido": True}
    res = enviar_correo(dest, asunto, cuerpo)
    res["omitido"] = False
    return res


def texto_correccion_linea(
    *,
    rid: int,
    correlativo: Optional[int],
    revisor: str,
    antes: dict,
    despues: dict,
    motivo: str,
) -> tuple[str, str]:
    ref = f"N° {correlativo}" if correlativo else f"#{rid}"
    asunto = f"FxR {ref}: corrección de un comprobante"
    cambios = []
    keys = [
        ("tipo_doc", "Tipo doc"),
        ("n_doc", "N° doc"),
        ("fecha_comprobante", "Fecha"),
        ("concepto", "Concepto"),
        ("monto", "Monto"),
        ("tipo_gasto_nombre", "Tipo gasto"),
        ("centro_costo_nombre", "Centro costo"),
        ("observaciones", "Observaciones"),
    ]
    for k, label in keys:
        a = antes.get(k)
        b = despues.get(k)
        if str(a or "") != str(b or ""):
            cambios.append(f"  · {label}: «{a or '—'}» → «{b or '—'}»")
    if not cambios:
        cambios.append("  · (sin cambios de campos detectados)")
    cuerpo = (
        f"El revisor ({revisor}) corrigió datos en tu rendición {ref}.\n\n"
        f"Motivo: {motivo or 'Corrección en revisión'}\n\n"
        f"Cambios:\n" + "\n".join(cambios) + "\n\n"
        f"Entra a Fondos por Rendir para revisar el estado actual.\n"
    )
    return asunto, cuerpo


def texto_quitar_linea(
    *,
    rid: int,
    correlativo: Optional[int],
    revisor: str,
    linea: dict,
    motivo: str,
) -> tuple[str, str]:
    ref = f"N° {correlativo}" if correlativo else f"#{rid}"
    asunto = f"FxR {ref}: comprobante devuelto a tu inbox"
    cuerpo = (
        f"El revisor ({revisor}) quitó un comprobante de tu rendición {ref}.\n"
        f"El archivo quedó de nuevo en tu inbox para que lo corrijas o lo vuelvas a incluir.\n\n"
        f"Motivo: {motivo}\n\n"
        f"Comprobante:\n"
        f"  · Concepto: {linea.get('concepto') or '—'}\n"
        f"  · Tipo/N°: {linea.get('tipo_doc') or '—'} {linea.get('n_doc') or ''}\n"
        f"  · Monto: {linea.get('monto') or 0}\n"
        f"  · Fecha: {linea.get('fecha_comprobante') or '—'}\n\n"
        f"Entra a Fondos por Rendir → Inbox.\n"
    )
    return asunto, cuerpo


def texto_rechazo(
    *,
    rid: int,
    correlativo: Optional[int],
    revisor: str,
    motivo: str,
) -> tuple[str, str]:
    ref = f"N° {correlativo}" if correlativo else f"#{rid}"
    asunto = f"FxR {ref}: rendición rechazada"
    cuerpo = (
        f"Tu rendición {ref} fue rechazada por {revisor}.\n\n"
        f"Motivo: {motivo}\n\n"
        f"Puedes corregirla (estado rechazada) y volver a marcarla Preparada.\n"
    )
    return asunto, cuerpo


def texto_retirada(
    *,
    rid: int,
    correlativo: Optional[int],
    usuario: str,
) -> tuple[str, str]:
    ref = f"N° {correlativo}" if correlativo else f"#{rid}"
    asunto = f"FxR {ref}: retirada de revisión"
    cuerpo = (
        f"La rendición {ref} fue retirada de la cola de revisión por {usuario}\n"
        f"y volvió a borrador para corrección.\n"
    )
    return asunto, cuerpo
