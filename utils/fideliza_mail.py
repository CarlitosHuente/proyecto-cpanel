"""Correo al cliente cuando cambian sus puntos."""

from __future__ import annotations

from utils.fideliza_db import leer_textos
from utils.fideliza_html import armar_correo, color_franja, variables_desde_aviso
from utils.mail_reporte_html import envolver_reporte_html, seccion_tabla
from utils.mail_smtp import enviar_correo


def _cuando(valor) -> str:
    if not valor:
        return ""
    return valor.strftime("%d/%m/%Y %H:%M")


def _tipo(tipo: str) -> str:
    return {
        "acumulacion": "Suma de puntos",
        "canje": "Canje",
        "anulacion": "Anulación",
    }.get(tipo, tipo)


def enviar_aviso(aviso: dict) -> dict:
    textos = leer_textos()
    color = color_franja(textos.get("correo_color"))
    if (textos.get("correo_html") or "").strip():
        armado = armar_correo(
            textos.get("correo_asunto") or "",
            textos["correo_html"],
            variables_desde_aviso(aviso),
            color=color,
        )
        return enviar_correo(
            aviso["mov"]["correo"],
            armado["asunto"],
            armado["texto"],
            html=armado["html"],
            inline=armado["inline"],
        )
    mov = aviso["mov"]
    premios = aviso.get("premios") or []
    puntos = int(mov["puntos"])
    signo = f"+{puntos}" if puntos > 0 else str(puntos)
    filas_premio = []
    for premio in premios:
        if premio["listo"]:
            estado = "Ya puedes canjearlo"
        else:
            estado = f"Te faltan {premio['faltan']} puntos"
        filas_premio.append((premio["nombre"], str(premio["puntos"]), estado))

    texto = [
        f"Hola {mov['nombre']},",
        "",
        "Actualizamos tus puntos en Huentelauquen.",
        f"Fecha: {_cuando(mov['creado_at'])}",
        f"Movimiento: {_tipo(mov['tipo'])}",
        f"Detalle: {mov['detalle']}",
        f"Puntos: {signo}",
        f"Saldo: {mov['saldo_despues']}",
    ]
    for nombre, costo, estado in filas_premio:
        texto.append(f"{nombre} ({costo} puntos): {estado}")

    secciones = []
    if filas_premio:
        secciones.append(
            seccion_tabla("Premios", ["Premio", "Costo", "Estado"], filas_premio)
        )
    html = envolver_reporte_html(
        "Tus puntos",
        subtitulo=_tipo(mov["tipo"]),
        meta=[
            ("Nombre", mov["nombre"]),
            ("Fecha", _cuando(mov["creado_at"])),
            ("Detalle", mov["detalle"]),
            ("Puntos", signo),
            ("Saldo", str(mov["saldo_despues"])),
        ],
        secciones_html=secciones,
        pie="Huentelauquen",
        color_franja=color,
    )
    return enviar_correo(
        mov["correo"],
        "Tus puntos en Huentelauquen",
        "\n".join(texto),
        html=html,
    )
