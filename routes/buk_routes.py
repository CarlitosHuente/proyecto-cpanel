from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from utils.auth import login_requerido, permiso_modulo
from utils.buk_api import listar_trabajadores_vigentes, probar_conexion
from utils.buk_asistencia_api import probar_conexion as probar_conexion_asistencia
from utils.buk_ausencias import reporte_ausencias_mes
from utils.buk_presencia import listar_presencia_dia
from utils.buk_documentos import buscar_empleado_vigente_por_rut, subir_pdf_con_firma_empleado, carpeta_encuestas
from utils.buk_encuesta_pdf import CAMPOS_ENCUESTA, generar_pdf_encuesta

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
    raw = (request.args.get("mes") or "").strip()
    if raw and len(raw) >= 7 and "-" in raw:
        try:
            dt = datetime.strptime(raw[:7], "%Y-%m")
            return dt.year, dt.month
        except ValueError:
            pass
    anio = request.args.get("anio", type=int)
    mes = request.args.get("mes_num", type=int)
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
