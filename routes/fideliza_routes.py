"""Fidelización: página pública del sticker y módulo de caja / administración."""

from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from utils.auth import login_requerido, permiso_modulo, tiene_permiso
from utils.fideliza_db import (
    CODIGO_MINUTOS,
    FidelizaError,
    HoraBloqueada,
    acreditar,
    actualizar_cliente,
    ahora,
    anular_movimiento,
    abrir_espera,
    asegurar_esquema,
    bloqueo_hora,
    buscar_clientes,
    canjear,
    crear_cliente,
    crear_opcion,
    crear_premio,
    crear_sucursal,
    crear_tag_sucursal,
    datos_aviso,
    espera_publica,
    exportar_clientes,
    exportar_movimientos,
    faltan_premios,
    generar_codigo,
    guardar_minutos,
    leer_textos,
    normalizar_correo,
    guardar_opcion,
    guardar_premio,
    listar_cola,
    listar_locales,
    listar_opciones,
    listar_premios,
    listar_tags,
    minutos_entre_puntos,
    movimientos,
    movimientos_sucursal,
    nombre_usuario,
    obtener_cliente,
    obtener_cliente_cookie,
    obtener_tag_id,
    tag_de_sucursal,
    obtener_tag,
    opciones_activas,
    premios_activos,
    quitar_espera,
    registrar_resultado_correo,
    rut_mostrar,
    toggle_tag,
    validar_codigo,
)
from utils.fideliza_html import (
    armar_correo,
    editor_textos,
    guardar_correo,
    guardar_imagen,
    guardar_legales,
    legales_publicos,
    mime_imagen,
    ruta_imagen,
    variables_de_prueba,
)
from utils.fideliza_mail import enviar_aviso
from utils.mail_smtp import enviar_correo

fideliza_bp = Blueprint("fideliza", __name__)

COOKIE = "fideliza_cli"
COOKIE_MAX = 60 * 60 * 24 * 365


@fideliza_bp.before_request
def _esquema():
    asegurar_esquema()


def _usuario() -> str:
    return session.get("usuario") or ""


def _tag_de_caja():
    if "tag" in request.args and not (request.args.get("tag") or "").strip():
        session.pop("fideliza_tag_id", None)
        return None
    pedido = request.values.get("tag")
    if pedido:
        try:
            tag = obtener_tag_id(int(pedido))
        except ValueError:
            tag = None
        if tag and tag.get("activo"):
            session["fideliza_tag_id"] = tag["id"]
            return tag
    if session.get("rol") != "superusuario" and session.get("sucursal_id"):
        return tag_de_sucursal(session.get("sucursal_id"))
    guardado = session.get("fideliza_tag_id")
    if guardado:
        tag = obtener_tag_id(int(guardado))
        if tag and tag.get("activo"):
            return tag
    return None


def _ir_caja(tag=None):
    if tag is None:
        tag = _tag_de_caja()
    if tag:
        return redirect(url_for("fideliza.caja", tag=tag["id"] if isinstance(tag, dict) else tag))
    return redirect(url_for("fideliza.caja"))


def _aviso(resultado: dict) -> bool:
    mov_id = resultado["mov"]["id"]
    try:
        envio = enviar_aviso(resultado)
        ok = bool(envio.get("ok"))
        registrar_resultado_correo(mov_id, ok, envio.get("error") or "")
        if not ok:
            flash(f"Puntos guardados. El correo no salió: {envio.get('error')}", "warning")
        return ok
    except Exception as exc:
        registrar_resultado_correo(mov_id, False, str(exc))
        flash("Puntos guardados. El correo no se pudo enviar.", "warning")
        return False


def _set_cookie(resp, token: str):
    resp.set_cookie(
        COOKIE,
        token,
        max_age=COOKIE_MAX,
        httponly=True,
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")),
        samesite="Lax",
        path="/",
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _publica(token: str, **ctx):
    tag = obtener_tag(token)
    if not tag:
        abort(404)
    resp = make_response(
        render_template(
            "fideliza/publico.html",
            tag=tag,
            momento=ahora(),
            legales=legales_publicos(leer_textos()),
            **ctx,
        )
    )
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


def _estado_conocido(token: str, cliente: dict):
    hasta = bloqueo_hora(cliente)
    if hasta:
        resp = _publica(
            token,
            vista="en_hora",
            cliente=cliente,
            hasta=hasta,
            premios=faltan_premios(cliente["saldo"]),
        )
        return _set_cookie(resp, cliente["cookie_token"])
    try:
        espera = abrir_espera(cliente["id"], obtener_tag(token)["id"])
    except HoraBloqueada as exc:
        resp = _publica(
            token,
            vista="en_hora",
            cliente=cliente,
            hasta=exc.hasta,
            premios=faltan_premios(cliente["saldo"]),
        )
        return _set_cookie(resp, cliente["cookie_token"])
    resp = _publica(token, vista="cargando", cliente=cliente, espera=espera)
    return _set_cookie(resp, cliente["cookie_token"])


@fideliza_bp.route("/f/<token>", methods=["GET"])
def publico(token):
    tag = obtener_tag(token)
    if not tag:
        abort(404)
    cliente = obtener_cliente_cookie(request.cookies.get(COOKIE, ""))
    if not cliente:
        return _publica(token, vista="elegir")
    return _estado_conocido(token, cliente)


@fideliza_bp.route("/f/<token>/cuenta", methods=["POST"])
def publico_cuenta(token):
    if not obtener_tag(token):
        abort(404)
    try:
        cliente = crear_cliente(
            request.form.get("nombre", ""),
            request.form.get("rut", ""),
            request.form.get("correo", ""),
            request.form.get("acepta_puntos") == "1",
            request.form.get("acepta_publicidad") == "1",
        )
    except FidelizaError as exc:
        return _publica(token, vista="crear", error=str(exc), form=request.form)
    resp = _publica(token, vista="bienvenida", cliente=cliente)
    return _set_cookie(resp, cliente["cookie_token"])


@fideliza_bp.route("/f/<token>/recuperar", methods=["POST"])
def publico_recuperar(token):
    if not obtener_tag(token):
        abort(404)
    try:
        cliente = validar_codigo(request.form.get("rut", ""), request.form.get("codigo", ""))
    except FidelizaError as exc:
        return _publica(token, vista="recuperar", error=str(exc), form=request.form)
    return _estado_conocido(token, cliente)


@fideliza_bp.route("/f/espera/<espera_token>", methods=["GET"])
def publico_estado(espera_token):
    row = espera_publica(espera_token)
    if not row:
        return jsonify({"estado": "desconocido"}), 404
    if row["estado"] == "acreditada":
        aviso = None
        from utils.db import get_db_connection

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, detalle, puntos, saldo_despues
                    FROM fideliza_movimiento
                    WHERE espera_id = %s AND tipo = 'acumulacion'
                    ORDER BY id DESC LIMIT 1
                    """,
                    (row["id"],),
                )
                aviso = cur.fetchone()
        finally:
            conn.close()
        return jsonify(
            {
                "estado": "acreditada",
                "detalle": aviso["detalle"] if aviso else "",
                "puntos": int(aviso["puntos"]) if aviso else 0,
                "saldo": int(aviso["saldo_despues"]) if aviso else int(row["saldo"]),
                "premios": faltan_premios(aviso["saldo_despues"] if aviso else row["saldo"]),
            }
        )
    return jsonify({"estado": row["estado"]})


@fideliza_bp.route("/fideliza/")
@login_requerido
def inicio():
    rol = session.get("rol")
    if not tiene_permiso(rol, "fideliza") and tiene_permiso(rol, "fideliza.vender"):
        return redirect(url_for("fideliza.caja"))
    if not tiene_permiso(rol, "fideliza"):
        return render_template("403.html"), 403
    return render_template(
        "fideliza/inicio.html",
        puede_vender=tiene_permiso(rol, "fideliza.vender"),
        locales=listar_locales(),
    )


@fideliza_bp.route("/fideliza/caja")
@login_requerido
@permiso_modulo("fideliza.vender")
def caja():
    tag = _tag_de_caja()
    return render_template(
        "fideliza/caja.html",
        tag=tag,
        locales=listar_locales(),
        opciones=opciones_activas(),
        premios=premios_activos(),
        movimientos=movimientos_sucursal(tag["id"]) if tag else [],
        quien=nombre_usuario(_usuario()),
    )


@fideliza_bp.route("/fideliza/caja/cola")
@login_requerido
@permiso_modulo("fideliza.vender")
def caja_cola():
    filas = []
    tag = _tag_de_caja()
    for row in listar_cola(tag["id"] if tag else None):
        filas.append(
            {
                "id": row["id"],
                "cliente_id": row["cliente_id"],
                "nombre": row["nombre"],
                "correo": row["correo"],
                "saldo": int(row["saldo"]),
                "desde": row["creado_at"].strftime("%H:%M"),
            }
        )
    return jsonify({"espera": filas})


@fideliza_bp.route("/fideliza/caja/acreditar", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza.vender")
def caja_acreditar():
    try:
        tag_id = int(request.form["tag_id"]) if request.form.get("tag_id") else None
        resultado = acreditar(
            int(request.form["espera_id"]),
            int(request.form["opcion_id"]),
            _usuario(),
            tag_id,
        )
    except (FidelizaError, KeyError, ValueError) as exc:
        flash(str(exc) if str(exc) else "No se pudo sumar los puntos.", "danger")
        return _ir_caja()
    _aviso(resultado)
    flash(
        f"Listo. {resultado['mov']['detalle']} sumó {resultado['mov']['puntos']} puntos. Saldo {resultado['mov']['saldo_despues']}.",
        "success",
    )
    return _ir_caja()


@fideliza_bp.route("/fideliza/caja/canjear", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza.vender")
def caja_canjear():
    try:
        tag_id = int(request.form["tag_id"]) if request.form.get("tag_id") else None
        resultado = canjear(
            int(request.form["cliente_id"]),
            int(request.form["premio_id"]),
            _usuario(),
            tag_id,
        )
    except (FidelizaError, KeyError, ValueError) as exc:
        flash(str(exc) if str(exc) else "No se pudo canjear.", "danger")
        return _ir_caja()
    _aviso(resultado)
    flash(f"Canje registrado. Saldo {resultado['mov']['saldo_despues']}.", "success")
    return _ir_caja()


@fideliza_bp.route("/fideliza/caja/quitar", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza.vender")
def caja_quitar():
    try:
        quitar_espera(int(request.form["espera_id"]))
    except (FidelizaError, KeyError, ValueError) as exc:
        flash(str(exc) or "No se pudo quitar de la lista.", "danger")
    return _ir_caja()


def _xlsx(filas: list, nombre: str):
    df = pd.DataFrame(filas)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Datos")
    buf.seek(0)
    marca = datetime.now().strftime("%Y%m%d_%H%M")
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"{nombre}_{marca}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@fideliza_bp.route("/fideliza/exportar/clientes")
@login_requerido
@permiso_modulo("fideliza")
def exportar_clientes_xlsx():
    filas = []
    for row in exportar_clientes():
        filas.append(
            {
                "Nombre": row["nombre"],
                "RUT": rut_mostrar(row["rut"]),
                "Correo": row["correo"],
                "Puntos": int(row["saldo"]),
                "Acepta bases de puntos": "Sí" if row.get("acepta_puntos") else "No",
                "Acepta confidencialidad y publicidad": "Sí" if row.get("acepta_publicidad") else "No",
                "Aceptado el": row["acepta_at"].strftime("%d/%m/%Y %H:%M") if row.get("acepta_at") else "",
                "Creado el": row["creado_at"].strftime("%d/%m/%Y %H:%M") if row.get("creado_at") else "",
            }
        )
    return _xlsx(filas, "fideliza_clientes")


@fideliza_bp.route("/fideliza/exportar/movimientos")
@login_requerido
@permiso_modulo("fideliza")
def exportar_movimientos_xlsx():
    tag_id = request.args.get("tag")
    try:
        tag_id = int(tag_id) if tag_id else None
    except ValueError:
        tag_id = None
    filas = []
    for row in exportar_movimientos(tag_id):
        filas.append(
            {
                "Fecha": row["creado_at"].strftime("%d/%m/%Y %H:%M") if row.get("creado_at") else "",
                "Sucursal": row.get("sucursal") or "",
                "Cliente": row["cliente"],
                "RUT": rut_mostrar(row["rut"]),
                "Correo": row["correo"],
                "Tipo": row["tipo"],
                "Detalle": row["detalle"],
                "Puntos": int(row["puntos"]),
                "Saldo": int(row["saldo_despues"]),
                "Usuario": row.get("usuario") or "",
                "Correo enviado": "Sí" if row.get("correo_ok") else "No",
            }
        )
    return _xlsx(filas, "fideliza_movimientos")


@fideliza_bp.route("/fideliza/clientes")
@login_requerido
@permiso_modulo("fideliza")
def clientes():
    q = request.args.get("q", "")
    return render_template(
        "fideliza/clientes.html",
        clientes=buscar_clientes(q),
        q=q,
        rut_mostrar=rut_mostrar,
    )


@fideliza_bp.route("/fideliza/clientes/<int:cliente_id>")
@login_requerido
@permiso_modulo("fideliza")
def ficha(cliente_id):
    cliente = obtener_cliente(cliente_id)
    if not cliente:
        abort(404)
    tipo = request.args.get("tipo", "")
    return render_template(
        "fideliza/ficha.html",
        cliente=cliente,
        movimientos=movimientos(cliente_id, tipo),
        tipo=tipo,
        premios=premios_activos(),
        codigo_minutos=CODIGO_MINUTOS,
        rut_mostrar=rut_mostrar,
    )


@fideliza_bp.route("/fideliza/clientes/<int:cliente_id>/datos", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza")
def ficha_datos(cliente_id):
    try:
        actualizar_cliente(cliente_id, request.form.get("nombre", ""), request.form.get("correo", ""))
    except FidelizaError as exc:
        flash(str(exc), "danger")
    else:
        flash("Datos actualizados.", "success")
    return redirect(url_for("fideliza.ficha", cliente_id=cliente_id))


@fideliza_bp.route("/fideliza/clientes/<int:cliente_id>/codigo", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza")
def ficha_codigo(cliente_id):
    try:
        codigo = generar_codigo(cliente_id, _usuario())
    except FidelizaError as exc:
        flash(str(exc), "danger")
    else:
        visible = f"{codigo[:3]} {codigo[3:]}"
        flash(
            f"Código de recuperación: {visible}. Vence en {CODIGO_MINUTOS} minutos y sirve una sola vez.",
            "warning",
        )
    return redirect(url_for("fideliza.ficha", cliente_id=cliente_id))


@fideliza_bp.route("/fideliza/clientes/<int:cliente_id>/anular", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza")
def ficha_anular(cliente_id):
    mov_id = int(request.form.get("mov_id") or 0)
    previo = datos_aviso(mov_id)
    if not previo or previo["mov"]["cliente_id"] != cliente_id:
        abort(404)
    try:
        resultado = anular_movimiento(mov_id, _usuario())
    except (FidelizaError, ValueError) as exc:
        flash(str(exc) or "No se pudo anular.", "danger")
        return redirect(url_for("fideliza.ficha", cliente_id=cliente_id))
    _aviso(resultado)
    flash("Movimiento anulado.", "success")
    return redirect(url_for("fideliza.ficha", cliente_id=cliente_id))


@fideliza_bp.route("/fideliza/clientes/<int:cliente_id>/canjear", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza")
def ficha_canjear(cliente_id):
    try:
        resultado = canjear(cliente_id, int(request.form["premio_id"]), _usuario())
    except (FidelizaError, KeyError, ValueError) as exc:
        flash(str(exc) or "No se pudo canjear.", "danger")
        return redirect(url_for("fideliza.ficha", cliente_id=cliente_id))
    _aviso(resultado)
    flash("Canje registrado.", "success")
    return redirect(url_for("fideliza.ficha", cliente_id=cliente_id))


@fideliza_bp.route("/fideliza/clientes/<int:cliente_id>/reenviar", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza")
def ficha_reenviar(cliente_id):
    aviso = datos_aviso(int(request.form.get("mov_id") or 0))
    if not aviso or aviso["mov"]["cliente_id"] != cliente_id:
        abort(404)
    if _aviso(aviso):
        flash("Correo reenviado.", "success")
    return redirect(url_for("fideliza.ficha", cliente_id=cliente_id))


@fideliza_bp.route("/fideliza/config", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fideliza")
def config():
    if request.method == "POST":
        accion = request.form.get("accion")
        try:
            if accion == "minutos":
                guardar_minutos(int(request.form.get("minutos") or 0))
            elif accion == "opcion":
                guardar_opcion(
                    int(request.form["opcion_id"]),
                    request.form.get("etiqueta", ""),
                    int(request.form.get("puntos") or 0),
                    int(request.form.get("orden") or 0),
                    request.form.get("activo") == "1",
                )
            elif accion == "opcion_nueva":
                crear_opcion(request.form.get("etiqueta", ""), int(request.form.get("puntos") or 0))
            elif accion == "premio":
                guardar_premio(
                    int(request.form["premio_id"]),
                    request.form.get("nombre", ""),
                    int(request.form.get("puntos") or 0),
                    int(request.form.get("orden") or 0),
                    request.form.get("activo") == "1",
                )
            elif accion == "premio_nuevo":
                crear_premio(request.form.get("nombre", ""), int(request.form.get("puntos") or 0))
            elif accion == "sucursal":
                crear_sucursal(request.form.get("nombre", ""))
            elif accion == "tag":
                tag = crear_tag_sucursal(int(request.form.get("sucursal_id") or 0))
                flash(f"Listo {tag['nombre']}. Graba la dirección en el cartel de esa sucursal.", "success")
            elif accion == "tag_activo":
                toggle_tag(int(request.form["tag_id"]), request.form.get("activo") == "1")
            elif accion == "legales":
                guardar_legales(
                    request.form.get("etiqueta_puntos", ""),
                    request.form.get("bases_puntos", ""),
                    request.form.get("etiqueta_conf", ""),
                    request.form.get("bases_conf", ""),
                )
            elif accion == "correo":
                guardar_correo(request.form.get("asunto", ""), request.form.get("correo_html", ""))
            elif accion == "correo_automatico":
                guardar_correo("", "")
            else:
                raise FidelizaError("Acción no reconocida.")
        except (FidelizaError, KeyError, ValueError) as exc:
            flash(str(exc) or "No se pudo guardar.", "danger")
        else:
            if accion == "correo_automatico":
                flash("El correo volvió al diseño automático.", "success")
            elif accion != "tag":
                flash("Guardado.", "success")
        return redirect(url_for("fideliza.config"))
    return render_template(
        "fideliza/config.html",
        minutos=minutos_entre_puntos(),
        opciones=listar_opciones(),
        premios=listar_premios(),
        locales=listar_locales(),
        editor=editor_textos(leer_textos()),
    )


@fideliza_bp.route("/fideliza/config/imagen", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza")
def config_imagen():
    try:
        nombre = guardar_imagen(request.files.get("imagen"))
    except FidelizaError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "url": url_for("fideliza.correo_img", nombre=nombre)})


@fideliza_bp.route("/fideliza/correo-img/<nombre>")
def correo_img(nombre):
    path = ruta_imagen(nombre)
    if not path:
        abort(404)
    return send_file(path, mimetype=mime_imagen(nombre), max_age=60 * 60 * 24 * 30, conditional=True)


@fideliza_bp.route("/fideliza/config/correo-prueba", methods=["POST"])
@login_requerido
@permiso_modulo("fideliza")
def correo_prueba():
    destino = normalizar_correo(request.form.get("destino", ""))
    if not destino:
        return jsonify({"ok": False, "error": "Escribe un correo válido para la prueba."}), 400
    armado = armar_correo(
        request.form.get("asunto", ""),
        request.form.get("html", ""),
        variables_de_prueba(faltan_premios(5)),
    )
    envio = enviar_correo(
        destino,
        armado["asunto"],
        armado["texto"],
        html=armado["html"],
        inline=armado["inline"],
    )
    if not envio.get("ok"):
        return jsonify({"ok": False, "error": envio.get("error") or "No se pudo enviar."}), 400
    return jsonify({"ok": True})
