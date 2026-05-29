import os
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from utils.auth import login_requerido, permiso_modulo
from utils.db import get_db_connection
from utils.despacho_web_batch import (
    MAX_PDFS,
    cargar_batch,
    contar_pendientes,
    crear_batch,
    item_pendiente,
    limpiar_batch,
    marcar_item,
    mover_respaldo,
    pdf_path,
)
from utils.despacho_web_celular import formatear_celular_chile
from utils.despacho_web_pdf_parser import parse_factura_pdf_bytes
from utils.despacho_web_service import (
    ESTADOS_ORDEN,
    TRANSPORTES,
    OrdenDuplicadaError,
    actualizar_orden,
    asegurar_productos,
    contar_ordenes,
    eliminar_orden,
    guardar_orden,
    listar_detalle_orden,
    listar_ordenes,
    listar_ordenes_recientes,
    listar_productos_activos,
    obtener_orden,
    orden_existe,
)

despacho_web_bp = Blueprint("despacho_web", __name__, url_prefix="/despacho-web")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_ROOT = os.path.join(BASE_DIR, "uploads", "despacho_web")


def _init_upload_dirs(app):
    os.makedirs(os.path.join(UPLOAD_ROOT, "temp"), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_ROOT, "respaldos"), exist_ok=True)
    app.config.setdefault("UPLOAD_FOLDER_DESPACHO_WEB", UPLOAD_ROOT)


@despacho_web_bp.record_once
def _on_register(state):
    _init_upload_dirs(state.app)


@despacho_web_bp.route("/")
@login_requerido
@permiso_modulo("despacho_web")
def index():
    comuna_filtro = request.args.get("comuna", "").strip()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            ordenes = listar_ordenes_recientes(cur, comuna=comuna_filtro or None)
    finally:
        conn.close()
    return render_template(
        "despacho_web/index.html",
        ordenes=ordenes,
        comuna_filtro=comuna_filtro,
        max_pdfs=MAX_PDFS,
    )


@despacho_web_bp.route("/productos")
@login_requerido
@permiso_modulo("despacho_web")
def productos():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT nombre, precio, sku_referencia, activo, creado_at
                FROM dw_productos
                ORDER BY nombre ASC
                """
            )
            productos_list = cur.fetchall() or []
    finally:
        conn.close()
    return render_template("despacho_web/productos.html", productos=productos_list)


@despacho_web_bp.route("/productos/guardar", methods=["POST"])
@login_requerido
@permiso_modulo("despacho_web")
def productos_guardar():
    nombre = (request.form.get("nombre") or "").strip()
    precio = (request.form.get("precio") or "").strip()
    sku = (request.form.get("sku_referencia") or "").strip() or None
    if not nombre:
        flash("Nombre de producto obligatorio.", "danger")
        return redirect(url_for("despacho_web.productos"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dw_productos (nombre, precio, sku_referencia, activo)
                VALUES (%s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    precio = VALUES(precio),
                    sku_referencia = VALUES(sku_referencia),
                    activo = 1
                """,
                (nombre, precio or None, sku),
            )
        conn.commit()
        flash(f'Producto "{nombre}" guardado.', "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al guardar producto: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("despacho_web.productos"))


@despacho_web_bp.route("/productos/toggle", methods=["POST"])
@login_requerido
@permiso_modulo("despacho_web")
def productos_toggle():
    nombre = (request.form.get("nombre") or "").strip()
    activo = 1 if request.form.get("activo") == "1" else 0
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dw_productos SET activo = %s WHERE nombre = %s",
                (activo, nombre),
            )
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("despacho_web.productos"))


@despacho_web_bp.route("/procesar", methods=["POST"])
@login_requerido
@permiso_modulo("despacho_web")
def procesar():
    files = request.files.getlist("pdfs")
    if not files:
        flash("Seleccione al menos un PDF.", "warning")
        return redirect(url_for("despacho_web.index"))

    valid_files = [f for f in files if f and f.filename]
    if not valid_files:
        flash("Archivos vacíos.", "warning")
        return redirect(url_for("despacho_web.index"))
    if len(valid_files) > MAX_PDFS:
        flash(f"Máximo {MAX_PDFS} PDF por carga.", "warning")
        return redirect(url_for("despacho_web.index"))

    archivos = []
    errores = []
    for f in valid_files:
        if not f.filename.lower().endswith(".pdf"):
            errores.append(f"{f.filename}: no es PDF")
            continue
        data = f.read()
        if not data:
            errores.append(f"{f.filename}: archivo vacío")
            continue
        try:
            parsed = parse_factura_pdf_bytes(data)
            archivos.append((secure_filename(f.filename) or "factura.pdf", data, parsed))
        except Exception as e:
            errores.append(f"{f.filename}: {e}")

    if errores and not archivos:
        flash("No se pudo procesar ningún PDF: " + "; ".join(errores), "danger")
        return redirect(url_for("despacho_web.index"))

    nombres_nuevos: list[str] = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for _nombre, _data, parsed in archivos:
                creados = asegurar_productos(cur, parsed.get("lineas") or [])
                parsed["productos_auto_creados"] = creados
                nombres_nuevos.extend(creados)
        conn.commit()
    finally:
        conn.close()

    if nombres_nuevos:
        unicos = list(dict.fromkeys(nombres_nuevos))
        flash(
            "Productos nuevos agregados al catálogo: " + ", ".join(unicos),
            "info",
        )

    usuario = session.get("usuario", "desconocido")
    batch_id = crear_batch(usuario, archivos)
    session["despacho_web_batch"] = batch_id

    if errores:
        flash("Algunos archivos fallaron: " + "; ".join(errores), "warning")

    return redirect(url_for("despacho_web.validar", batch_id=batch_id))


@despacho_web_bp.route("/validar/<batch_id>")
@login_requerido
@permiso_modulo("despacho_web")
def validar(batch_id):
    manifest = cargar_batch(batch_id)
    if not manifest:
        flash("Lote de validación no encontrado o expirado.", "warning")
        return redirect(url_for("despacho_web.index"))

    item = item_pendiente(manifest)
    if not item:
        limpiar_batch(batch_id)
        session.pop("despacho_web_batch", None)
        flash("Todas las órdenes del lote fueron procesadas.", "success")
        return redirect(url_for("despacho_web.index"))

    parsed = item["parsed"]
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            asegurar_productos(cur, parsed.get("lineas") or [])
            conn.commit()
            productos = listar_productos_activos(cur)
    finally:
        conn.close()

    celular_fmt = formatear_celular_chile(parsed.get("celular_raw") or "")
    total_items = len(manifest["items"])
    pendientes = contar_pendientes(manifest)
    procesados = total_items - pendientes
    idx_actual = item["idx"] + 1

    return render_template(
        "despacho_web/validar.html",
        batch_id=batch_id,
        item=item,
        parsed=parsed,
        celular_fmt=celular_fmt or "",
        productos=productos,
        total_items=total_items,
        pendientes=pendientes,
        procesados=procesados,
        idx_actual=idx_actual,
    )


@despacho_web_bp.route("/pdf/<batch_id>/<int:idx>")
@login_requerido
@permiso_modulo("despacho_web")
def servir_pdf(batch_id, idx):
    path = pdf_path(batch_id, idx)
    if not path or not os.path.isfile(path):
        return "PDF no encontrado", 404
    return send_file(path, mimetype="application/pdf")


@despacho_web_bp.route("/guardar", methods=["POST"])
@login_requerido
@permiso_modulo("despacho_web")
def guardar():
    data = request.get_json(silent=True) or {}
    batch_id = data.get("batch_id")
    idx = data.get("idx")
    if batch_id is None or idx is None:
        return jsonify({"success": False, "error": "Faltan batch_id o idx"}), 400

    manifest = cargar_batch(batch_id)
    if not manifest:
        return jsonify({"success": False, "error": "Lote no encontrado"}), 404

    item = next((it for it in manifest["items"] if it["idx"] == idx), None)
    if not item or item.get("status") != "pending":
        return jsonify({"success": False, "error": "Ítem no pendiente"}), 400

    orden_data = data.get("orden") or {}
    lineas = data.get("lineas") or []
    n_orden = str(orden_data.get("n_orden", "")).strip()

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if orden_existe(cur, n_orden):
                return jsonify(
                    {
                        "success": False,
                        "error": f"La Orden N° {n_orden} ya existe en el sistema",
                    }
                ), 409

        respaldo = mover_respaldo(batch_id, idx, n_orden)
        usuario = session.get("usuario", "desconocido")
        guardar_orden(conn, orden_data, lineas, usuario, respaldo or None)
        marcar_item(manifest, idx, "saved")

        restantes = contar_pendientes(manifest)
        if restantes == 0:
            limpiar_batch(batch_id)
            session.pop("despacho_web_batch", None)
            return jsonify(
                {
                    "success": True,
                    "mensaje": f"Orden N° {n_orden} guardada. Lote completado.",
                    "completado": True,
                    "redirect": url_for("despacho_web.index"),
                }
            )

        return jsonify(
            {
                "success": True,
                "mensaje": f"Orden N° {n_orden} guardada.",
                "completado": False,
                "redirect": url_for("despacho_web.validar", batch_id=batch_id),
                "restantes": restantes,
            }
        )
    except OrdenDuplicadaError as e:
        return jsonify({"success": False, "error": str(e)}), 409
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@despacho_web_bp.route("/omitir", methods=["POST"])
@login_requerido
@permiso_modulo("despacho_web")
def omitir():
    data = request.get_json(silent=True) or {}
    batch_id = data.get("batch_id")
    idx = data.get("idx")
    manifest = cargar_batch(batch_id)
    if not manifest:
        return jsonify({"success": False, "error": "Lote no encontrado"}), 404

    marcar_item(manifest, idx, "skipped")
    restantes = contar_pendientes(manifest)
    if restantes == 0:
        limpiar_batch(batch_id)
        session.pop("despacho_web_batch", None)
        return jsonify(
            {
                "success": True,
                "completado": True,
                "redirect": url_for("despacho_web.index"),
            }
        )
    return jsonify(
        {
            "success": True,
            "completado": False,
            "redirect": url_for("despacho_web.validar", batch_id=batch_id),
        }
    )


@despacho_web_bp.route("/verificar-duplicado")
@login_requerido
@permiso_modulo("despacho_web")
def verificar_duplicado():
    n_orden = (request.args.get("n_orden") or "").strip()
    if not n_orden:
        return jsonify({"existe": False})
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            existe = orden_existe(cur, n_orden)
    finally:
        conn.close()
    return jsonify({"existe": existe, "n_orden": n_orden})


@despacho_web_bp.route("/ordenes")
@login_requerido
@permiso_modulo("despacho_web")
def ordenes():
    comuna = request.args.get("comuna", "").strip()
    estado = request.args.get("estado", "").strip()
    buscar = request.args.get("q", "").strip()
    pagina = max(1, int(request.args.get("pagina", 1) or 1))
    por_pagina = 50
    offset = (pagina - 1) * por_pagina

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            total = contar_ordenes(
                cur,
                comuna=comuna or None,
                estado=estado or None,
                buscar=buscar or None,
            )
            filas = listar_ordenes(
                cur,
                comuna=comuna or None,
                estado=estado or None,
                buscar=buscar or None,
                limite=por_pagina,
                offset=offset,
            )
    finally:
        conn.close()

    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    return render_template(
        "despacho_web/ordenes.html",
        ordenes=filas,
        estados=ESTADOS_ORDEN,
        comuna_filtro=comuna,
        estado_filtro=estado,
        buscar=buscar,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
    )


@despacho_web_bp.route("/ordenes/<n_orden>", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("despacho_web")
def orden_editar(n_orden):
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        orden_data = data.get("orden") or request.form.to_dict()
        lineas = data.get("lineas") or []
        conn = get_db_connection()
        try:
            actualizar_orden(conn, n_orden, orden_data, lineas)
            if request.is_json or data:
                return jsonify({"success": True, "mensaje": "Orden actualizada."})
            flash(f"Orden N° {n_orden} actualizada.", "success")
            return redirect(url_for("despacho_web.orden_editar", n_orden=n_orden))
        except ValueError as e:
            if request.is_json or data:
                return jsonify({"success": False, "error": str(e)}), 400
            flash(str(e), "danger")
        except Exception as e:
            if request.is_json or data:
                return jsonify({"success": False, "error": str(e)}), 500
            flash(str(e), "danger")
        finally:
            conn.close()
        return redirect(url_for("despacho_web.orden_editar", n_orden=n_orden))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            orden = obtener_orden(cur, n_orden)
            if not orden:
                flash(f"Orden N° {n_orden} no encontrada.", "warning")
                return redirect(url_for("despacho_web.ordenes"))
            detalle = listar_detalle_orden(cur, n_orden)
            productos = listar_productos_activos(cur)
    finally:
        conn.close()

    return render_template(
        "despacho_web/orden_editar.html",
        orden=orden,
        detalle=detalle,
        productos=productos,
        estados=ESTADOS_ORDEN,
        transportes=TRANSPORTES,
    )


@despacho_web_bp.route("/ordenes/<n_orden>/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("despacho_web")
def orden_eliminar(n_orden):
    conn = get_db_connection()
    try:
        eliminar_orden(conn, n_orden)
        flash(f"Orden N° {n_orden} eliminada.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        flash(str(e), "danger")
    finally:
        conn.close()
    return redirect(url_for("despacho_web.ordenes"))
