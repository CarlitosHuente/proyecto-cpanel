"""Tick de notificaciones automáticas (cron cPanel)."""

from __future__ import annotations

from typing import Any, Dict, List

from utils.buk_alertas_correo import enviar_alertas_buk
from utils.notificaciones_config import (
    SECCIONES,
    ahora_santiago,
    debe_enviar_auto,
    marcar_ultimo_envio,
)


def procesar_notificaciones_auto(*, forzar: bool = False) -> dict:
    """
    Evalúa secciones con envío automático y dispara las que correspondan.
    forzar=True ignora día/hora/último_envio (solo para pruebas internas).
    """
    now = ahora_santiago()
    resultados: List[Dict[str, Any]] = []

    for seccion in SECCIONES:
        if seccion != "buk_alertas":
            continue
        if forzar:
            ok_due, motivo = True, "forzado"
        else:
            ok_due, motivo = debe_enviar_auto(seccion, ahora=now)
        if not ok_due:
            resultados.append({"seccion": seccion, "enviado": False, "motivo": motivo})
            continue

        envio = enviar_alertas_buk(now.year, now.month)
        if envio.get("ok"):
            marcar_ultimo_envio(seccion, now.date().isoformat())
            resultados.append(
                {
                    "seccion": seccion,
                    "enviado": True,
                    "motivo": motivo,
                    "destinos": envio.get("destinos"),
                    "total_pendientes": envio.get("total_pendientes"),
                }
            )
        else:
            resultados.append(
                {
                    "seccion": seccion,
                    "enviado": False,
                    "motivo": envio.get("error") or "error de envío",
                    "destinos": envio.get("destinos"),
                }
            )

    return {
        "ok": True,
        "ahora": now.isoformat(),
        "resultados": resultados,
    }
