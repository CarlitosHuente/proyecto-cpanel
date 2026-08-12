from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from utils.auth import login_requerido, permiso_modulo
from utils.buk_api import listar_trabajadores_vigentes, probar_conexion
from utils.buk_asistencia_api import probar_conexion as probar_conexion_asistencia
from utils.buk_alertas import contador_alertas_mes, reporte_alertas_mes
from utils.buk_alertas_correo import enviar_alertas_buk
from utils.buk_alertas_revisadas import marcar as marcar_alerta_revisada
from utils.buk_ausencias import reporte_ausencias_mes
from utils.buk_calendario import opciones_calendario, reporte_calendario_mes
from utils.buk_colacion_config import (
    config_recinto,
    guardar_config_recinto,
    guardar_recinto,
    leer_todas,
)
from utils.buk_presencia import listar_presencia_dia
from utils.buk_documentos import buscar_empleado_vigente_por_rut, subir_pdf_con_firma_empleado, carpeta_encuestas
from utils.buk_encuesta_pdf import CAMPOS_ENCUESTA, generar_pdf_encuesta
from utils.notificaciones_config import emails_seccion
from utils.mail_smtp import smtp_configurado

buk_bp = Blueprint("buk", __name__, url_prefix="/buk")


@buk_bp.route("/")
@login_requerido
@permiso_modulo("buk")
def index():
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 25, type=int)
    resultado = listar_trabajadores_vigentes(page=page, page_size=page_size)
    return render_template(
        "buk/index.html",
        resultado=resultado,
        page=page,
        page_size=page_size,
    )


@buk_bp.route("/api/estado")
@login_requerido
@permiso_modulo("buk")
def api_estado():
    return jsonify(probar_conexion())


@buk_bp.route("/api/trabajadores-vigentes")
@login_requerido
@permiso_modulo("buk")
def api_trabajadores_vigentes():
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 25, type=int)
    exclude_pending = request.args.get("exclude_pending", "true").lower() != "false"
    resultado = listar_trabajadores_vigentes(
        page=page,
        page_size=page_size,
        exclude_pending=exclude_pending,
    )
    status = 200 if resultado["ok"] else 502
    return jsonify(resultado), status


def _fecha_desde_request():
    raw = (request.args.get("fecha") or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _mes_anio_desde_request():
    raw = (request.values.get("mes") or "").strip()
    if raw and len(raw) >= 7 and "-" in raw:
        try:
            dt = datetime.strptime(raw[:7], "%Y-%m")
            return dt.year, dt.month
        except ValueError:
            pass
    anio = request.values.get("anio", type=int)
    mes = request.values.get("mes_num", type=int)
    if anio and mes:
        return anio, mes
    hoy = datetime.today()
    return hoy.year, hoy.month


def _render_presencia():
    resultado = listar_presencia_dia(_fecha_desde_request())
    return render_template("buk/presencia.html", resultado=resultado)


@buk_bp.route("/presencia")
@login_requerido
@permiso_modulo("buk")
def presencia():
    return _render_presencia()


@buk_bp.route("/asistencia")
@login_requerido
@permiso_modulo("buk")
def asistencia():
    """Alias del reporte de marcajes del día."""
    return _render_presencia()


@buk_bp.route("/ausencias")
@login_requerido
@permiso_modulo("buk")
def ausencias():
    anio, mes = _mes_anio_desde_request()
    resultado = reporte_ausencias_mes(anio, mes)
    mes_input = f"{resultado['anio']}-{resultado['mes']:02d}"
    return render_template(
        "buk/ausencias.html",
        resultado=resultado,
        mes_input=mes_input,
        solo_ausencias=request.args.get("solo_ausencias", "1") == "1",
    )


@buk_bp.route("/api/ausencias-mes")
@login_requerido
@permiso_modulo("buk")
def api_ausencias_mes():
    anio, mes = _mes_anio_desde_request()
    resultado = reporte_ausencias_mes(anio, mes)
    status = 200 if resultado.get("ok") else 502
    return jsonify(resultado), status


@buk_bp.route("/api/presencia-hoy")
@login_requerido
@permiso_modulo("buk")
def api_presencia_hoy():
    resultado = listar_presencia_dia(_fecha_desde_request())
    status = 200 if resultado.get("ok") else 502
    return jsonify(resultado), status


@buk_bp.route("/api/asistencia-hoy")
@login_requerido
@permiso_modulo("buk")
def api_asistencia_hoy():
    return api_presencia_hoy()


@buk_bp.route("/api/estado-asistencia")
@login_requerido
@permiso_modulo("buk")
def api_estado_asistencia():
    return jsonify(probar_conexion_asistencia())


@buk_bp.route("/encuestas", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("buk")
def encuestas():
    form = {}
    resultado = None

    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k, _ in CAMPOS_ENCUESTA}
        form["rut"] = (request.form.get("rut") or "").strip()
        rut = form["rut"]

        busqueda = buscar_empleado_vigente_por_rut(rut)
        if not busqueda["ok"]:
            resultado = {"ok": False, "error": busqueda["error"]}
        else:
            empleado = busqueda["empleado"]
            pdf = generar_pdf_encuesta(
                titulo="Encuesta de Capacitación — Huente (POC)",
                empleado=empleado,
                respuestas=form,
            )
            rut_corto = (empleado.get("rut") or "colaborador").replace(".", "").replace("-", "")[:12]
            nombre_archivo = f"Encuesta_Capacitacion_{rut_corto}.pdf"
            upload = subir_pdf_con_firma_empleado(
                employee_id=int(empleado["id"]),
                pdf_bytes=pdf,
                filename=nombre_archivo,
                carpeta=carpeta_encuestas(),
                empleado=empleado,
            )
            if upload["ok"]:
                resultado = {"ok": True, "empleado": empleado, "upload": upload}
            else:
                resultado = {"ok": False, "error": upload.get("error")}

    return render_template(
        "buk/encuestas.html",
        campos=CAMPOS_ENCUESTA,
        form=form if request.method == "POST" else None,
        resultado=resultado,
    )


@buk_bp.route("/api/buscar-rut")
@login_requerido
@permiso_modulo("buk")
def api_buscar_rut():
    rut = (request.args.get("rut") or "").strip()
    return jsonify(buscar_empleado_vigente_por_rut(rut))


@buk_bp.route("/calendario")
@login_requerido
@permiso_modulo("buk")
def calendario():
    anio, mes = _mes_anio_desde_request()
    obra_id = (request.args.get("obra_id") or "").strip()
    rut = (request.args.get("rut") or "").strip()
    mes_input = f"{anio}-{mes:02d}"
    opciones = opciones_calendario()
    resultado = None
    alertas_contador = 0
    if obra_id and rut:
        resultado = reporte_calendario_mes(anio, mes, obra_id, rut)
    cnt = contador_alertas_mes(anio, mes, obra_id or None)
    if cnt.get("ok"):
        alertas_contador = cnt.get("total") or 0
    return render_template(
        "buk/calendario.html",
        mes_input=mes_input,
        obra_id=obra_id,
        rut=rut,
        opciones=opciones,
        resultado=resultado,
        alertas_contador=alertas_contador,
    )


@buk_bp.route("/api/calendario-mes")
@login_requerido
@permiso_modulo("buk")
def api_calendario_mes():
    anio, mes = _mes_anio_desde_request()
    obra_id = (request.args.get("obra_id") or "").strip()
    rut = (request.args.get("rut") or "").strip()
    if not obra_id or not rut:
        return jsonify({"ok": False, "error": "Parámetros obra_id y rut requeridos."}), 400
    resultado = reporte_calendario_mes(anio, mes, obra_id, rut)
    status = 200 if resultado.get("ok") else 502
    return jsonify(resultado), status


@buk_bp.route("/api/colacion-recinto", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("buk")
def api_colacion_recinto():
    if request.method == "GET":
        obra_id = (request.args.get("obra_id") or "").strip()
        if obra_id:
            return jsonify({"ok": True, "config": config_recinto(obra_id)})
        return jsonify({"ok": True, "colaciones": leer_todas()})

    data = request.get_json(silent=True) or {}
    obra_id = (data.get("obra_id") or request.form.get("obra_id") or "").strip()
    nombre = (data.get("nombre") or request.form.get("nombre") or "").strip()
    if not obra_id:
        return jsonify({"ok": False, "error": "obra_id requerido."}), 400

    grupos = data.get("grupos")
    default_raw = data.get("default_minutos")
    if default_raw is None and data.get("minutos") is not None:
        default_raw = data.get("minutos")
    if default_raw is None and request.form.get("minutos") is not None:
        default_raw = request.form.get("minutos")

    if grupos is not None or default_raw is not None:
        default_minutos = None
        if default_raw is not None:
            try:
                default_minutos = int(default_raw)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "default_minutos inválido."}), 400
        ok, msg = guardar_config_recinto(
            obra_id,
            nombre=nombre,
            default_minutos=default_minutos,
            grupos=grupos if grupos is not None else None,
        )
    else:
        try:
            minutos = int(data.get("minutos") or request.form.get("minutos"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Minutos inválidos."}), 400
        ok, msg = guardar_recinto(obra_id, minutos, nombre)

    if not ok:
        return jsonify({"ok": False, "error": msg}), 400
    cfg = config_recinto(obra_id)
    return jsonify({"ok": True, **cfg})


@buk_bp.route("/alertas")
@login_requerido
@permiso_modulo("buk")
def alertas():
    anio, mes = _mes_anio_desde_request()
    obra_id = (request.args.get("obra_id") or "").strip() or None
    mes_input = f"{anio}-{mes:02d}"
    incluir = request.args.get("incluir_revisadas", "0") == "1"
    opciones = opciones_calendario()
    resultado = reporte_alertas_mes(anio, mes, obra_id, incluir_revisadas=incluir)
    destinarios = emails_seccion("buk_alertas")
    return render_template(
        "buk/alertas.html",
        mes_input=mes_input,
        obra_id=obra_id or "",
        incluir_revisadas=incluir,
        opciones=opciones,
        resultado=resultado,
        notif_emails=destinarios,
        smtp_ok=smtp_configurado(),
    )


@buk_bp.route("/alertas/enviar", methods=["POST"])
@login_requerido
@permiso_modulo("buk")
def alertas_enviar():
    anio, mes = _mes_anio_desde_request()
    obra_id = (request.form.get("obra_id") or request.args.get("obra_id") or "").strip() or None
    incluir = request.args.get("incluir_revisadas", "0") == "1"
    if request.form.get("incluir_revisadas") == "1":
        incluir = True
    mes_input = f"{anio}-{mes:02d}"
    redirect_kwargs = {"mes": mes_input}
    if obra_id:
        redirect_kwargs["obra_id"] = obra_id
    if incluir:
        redirect_kwargs["incluir_revisadas"] = "1"

    destinarios = emails_seccion("buk_alertas")
    if not destinarios:
        flash(
            "No hay correos configurados para Alertas Buk. "
            "Configure destinatarios en Configuración → Notificaciones.",
            "warning",
        )
        return redirect(url_for("buk.alertas", **redirect_kwargs))

    resultado = enviar_alertas_buk(anio, mes, obra_id)
    if resultado.get("ok"):
        dest = ", ".join(resultado.get("destinos") or destinarios)
        pendientes = resultado.get("total_pendientes")
        flash(
            f"Alertas Buk enviadas a: {dest}"
            + (f" ({pendientes} pendiente(s))." if pendientes is not None else "."),
            "success",
        )
    else:
        flash(resultado.get("error") or "No se pudo enviar el correo.", "danger")
    return redirect(url_for("buk.alertas", **redirect_kwargs))


@buk_bp.route("/api/alertas-mes")
@login_requerido
@permiso_modulo("buk")
def api_alertas_mes():
    anio, mes = _mes_anio_desde_request()
    obra_id = (request.args.get("obra_id") or "").strip() or None
    incluir = request.args.get("incluir_revisadas", "0") == "1"
    resultado = reporte_alertas_mes(anio, mes, obra_id, incluir_revisadas=incluir)
    status = 200 if resultado.get("ok") else 502
    return jsonify(resultado), status


@buk_bp.route("/api/alertas-contador")
@login_requerido
@permiso_modulo("buk")
def api_alertas_contador():
    anio, mes = _mes_anio_desde_request()
    obra_id = (request.args.get("obra_id") or "").strip() or None
    return jsonify(contador_alertas_mes(anio, mes, obra_id))


@buk_bp.route("/api/alertas-revisar", methods=["POST"])
@login_requerido
@permiso_modulo("buk")
def api_alertas_revisar():
    data = request.get_json(silent=True) or {}
    alerta_id = (data.get("alerta_id") or "").strip()
    if not alerta_id:
        return jsonify({"ok": False, "error": "alerta_id requerido."}), 400
    revisada = data.get("revisada", True)
    if isinstance(revisada, str):
        revisada = revisada.lower() in ("1", "true", "yes")
    usuario = session.get("usuario") or session.get("nombre") or ""
    ok = marcar_alerta_revisada(alerta_id, usuario, revisada=bool(revisada))
    if not ok:
        return jsonify({"ok": False, "error": "No se pudo guardar."}), 500
    return jsonify({"ok": True, "alerta_id": alerta_id, "revisada": bool(revisada)})
