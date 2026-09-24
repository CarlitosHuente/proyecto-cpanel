"""Módulo Reportería: comparativos de ventas en PDF y envío manual."""
from __future__ import annotations

import os

from flask import Blueprint, abort, jsonify, render_template, request, send_file, session

from utils.auth import login_requerido, permiso_modulo
from utils.mail_reporte_html import envolver_reporte_html
from utils.mail_smtp import _normalizar_destinos, enviar_correo
from utils.reporteria_db import (
    actualizar_correos,
    eliminar,
    guardar,
    guardar_pdf,
    listar,
    marcar_error,
    marcar_listo,
    obtener,
    ruta_absoluta,
)
from utils.reporteria_pdf import (
    CORTE_LABEL,
    EMPRESA_LABEL,
    VISTA_LABEL,
    generar_pdf_ventas,
)
from utils.reporteria_ventas import calcular_comparativo, opciones

reporteria_bp = Blueprint("reporteria", __name__, url_prefix="/reporteria")

EMPRESAS = {"comercial", "agricola"}
CORTES = {"semanal", "mensual"}
VISTAS = {"consolidado", "sucursales", "ambos"}


def _usuario() -> str:
    return session.get("usuario") or ""


def _payload() -> dict:
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    empresa = (data.get("empresa") or "").strip()
    corte = (data.get("corte") or "").strip()
    vista = "ambos"
    sucursales = []
    familias = []
    familias_ficha = []
    correos_raw = data.get("correos")
    if isinstance(correos_raw, str):
        correos = _normalizar_destinos(correos_raw)
    else:
        correos = _normalizar_destinos(correos_raw or [])
    if not nombre:
        nombre = "Reporte Ventas"
    if empresa not in EMPRESAS:
        raise ValueError("Empresa no válida.")
    if corte not in CORTES:
        raise ValueError("Corte no válido.")
    periodo_num = data.get("periodo_num")
    periodo_anio = data.get("periodo_anio")
    if periodo_num in ("", None) and periodo_anio in ("", None):
        periodo_num = None
        periodo_anio = None
    else:
        try:
            periodo_num = int(periodo_num)
            periodo_anio = int(periodo_anio)
        except (TypeError, ValueError):
            raise ValueError("Indica el número y el año del periodo, o déjalos vacíos.")
        if periodo_anio < 2015 or periodo_anio > 2100:
            raise ValueError("Año fuera de rango.")
        if corte == "semanal" and not 1 <= periodo_num <= 53:
            raise ValueError("La semana debe estar entre 1 y 53.")
        if corte == "mensual" and not 1 <= periodo_num <= 12:
            raise ValueError("El mes debe estar entre 1 y 12.")
        if corte == "semanal":
            try:
                from datetime import date
                date.fromisocalendar(periodo_anio, periodo_num, 1)
            except ValueError:
                raise ValueError("Esa semana no existe en ese año.")
    rid = data.get("id")
    try:
        rid = int(rid) if rid else None
    except (TypeError, ValueError):
        rid = None
    return {
        "id": rid,
        "nombre": nombre[:160],
        "empresa": empresa,
        "corte": corte,
        "vista": vista,
        "sucursales": sucursales,
        "familias": familias,
        "familias_ficha": familias_ficha,
        "correos": correos,
        "periodo_num": periodo_num,
        "periodo_anio": periodo_anio,
    }


@reporteria_bp.route("/")
@login_requerido
@permiso_modulo("reporteria")
def index():
    return render_template(
        "reporteria/lista.html",
        reportes=listar(),
        empresa_label=EMPRESA_LABEL,
        corte_label=CORTE_LABEL,
        vista_label=VISTA_LABEL,
        meses=["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    )


@reporteria_bp.route("/nuevo")
@login_requerido
@permiso_modulo("reporteria")
def nuevo():
    return render_template("reporteria/editar.html", reporte=None)


@reporteria_bp.route("/<int:reporte_id>/editar")
@login_requerido
@permiso_modulo("reporteria")
def editar(reporte_id: int):
    reporte = obtener(reporte_id)
    if not reporte:
        abort(404)
    return render_template("reporteria/editar.html", reporte=reporte)


@reporteria_bp.route("/api/opciones")
@login_requerido
@permiso_modulo("reporteria")
def api_opciones():
    empresa = (request.args.get("empresa") or "comercial").strip()
    if empresa not in EMPRESAS:
        return jsonify({"ok": False, "error": "Empresa no válida."}), 400
    try:
        data = opciones(empresa)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, **data})


@reporteria_bp.route("/guardar", methods=["POST"])
@login_requerido
@permiso_modulo("reporteria")
def api_guardar():
    try:
        datos = _payload()
        rid = guardar(datos, _usuario())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "id": rid})


@reporteria_bp.route("/<int:reporte_id>/generar", methods=["POST"])
@login_requerido
@permiso_modulo("reporteria")
def api_generar(reporte_id: int):
    reporte = obtener(reporte_id)
    if not reporte:
        return jsonify({"ok": False, "error": "Reporte no encontrado."}), 404
    try:
        datos = calcular_comparativo(
            reporte["empresa"],
            reporte["corte"],
            reporte["vista"],
            reporte["sucursales"],
            reporte["familias"],
            nombre=reporte["nombre"],
            familias_ficha=reporte.get("familias_ficha") or [],
            periodo_num=reporte.get("periodo_num"),
            periodo_anio=reporte.get("periodo_anio"),
        )
        ruta_rel = f"uploads/reporteria/reporte_{reporte_id}.pdf"
        abs_path = ruta_absoluta(ruta_rel)
        if not abs_path:
            raise RuntimeError("Ruta de PDF no válida.")
        generar_pdf_ventas(datos, abs_path)
        with open(abs_path, "rb") as fh:
            guardar_pdf(reporte_id, fh.read())
        marcar_listo(reporte_id, ruta_rel)
    except Exception as exc:
        marcar_error(reporte_id, str(exc))
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "id": reporte_id})


@reporteria_bp.route("/<int:reporte_id>/pdf")
@login_requerido
@permiso_modulo("reporteria")
def descargar(reporte_id: int):
    reporte = obtener(reporte_id)
    if not reporte or reporte.get("estado") != "listo":
        abort(404)
    path = ruta_absoluta(reporte.get("ruta_pdf"))
    if not path or not os.path.isfile(path):
        abort(404)
    nombre = (reporte.get("nombre") or f"reporte_{reporte_id}").replace("/", "-")
    return send_file(path, as_attachment=True, download_name=f"{nombre}.pdf", mimetype="application/pdf")


@reporteria_bp.route("/<int:reporte_id>/enviar", methods=["POST"])
@login_requerido
@permiso_modulo("reporteria")
def enviar(reporte_id: int):
    reporte = obtener(reporte_id)
    if not reporte or reporte.get("estado") != "listo":
        return jsonify({"ok": False, "error": "El PDF todavía no está listo."}), 400
    body = request.get_json(silent=True) or {}
    if "correos" in body and body.get("correos") not in (None, ""):
        correos = _normalizar_destinos(body.get("correos"))
        if correos:
            actualizar_correos(reporte_id, correos)
            reporte["correos"] = correos
    destinos = reporte.get("correos") or []
    if not destinos:
        return jsonify({"ok": False, "error": "Agrega al menos un correo."}), 400
    path = ruta_absoluta(reporte.get("ruta_pdf"))
    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "error": "No se encontró el PDF."}), 404
    with open(path, "rb") as fh:
        pdf = fh.read()
    empresa = EMPRESA_LABEL.get(reporte["empresa"], reporte["empresa"])
    corte = CORTE_LABEL.get(reporte["corte"], reporte["corte"])
    html = envolver_reporte_html(
        reporte["nombre"],
        subtitulo="Comparativo de ventas (neto)",
        meta=[("Empresa", empresa), ("Corte", corte)],
        aviso="El informe va adjunto en PDF.",
        pie="Huente — Reportería",
    )
    texto = f"{reporte['nombre']}\nEmpresa: {empresa}\nCorte: {corte}\nEl informe va adjunto en PDF."
    nombre_adj = (reporte.get("nombre") or "reporte").replace("/", "-") + ".pdf"
    resultado = enviar_correo(
        destinos,
        f"Reporte: {reporte['nombre']}",
        texto,
        html=html,
        adjuntos=[(nombre_adj, pdf, "application/pdf")],
    )
    if not resultado.get("ok"):
        return jsonify({"ok": False, "error": resultado.get("error") or "No se pudo enviar."}), 500
    return jsonify({"ok": True, "destinos": resultado.get("destinos") or destinos})


@reporteria_bp.route("/<int:reporte_id>/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("reporteria")
def api_eliminar(reporte_id: int):
    if not eliminar(reporte_id):
        return jsonify({"ok": False, "error": "Reporte no encontrado."}), 404
    return jsonify({"ok": True})
