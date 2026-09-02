from __future__ import annotations

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
    MAX_PAGINAS_MASIVO,
    MAX_PDFS,
    archivar_original_masivo,
    cargar_batch,
    contar_pendientes,
    crear_batch,
    crear_batch_masivo,
    item_pendiente,
    limpiar_batch,
    marcar_item,
    mover_respaldo,
    pdf_path,
)
from utils.despacho_web_celular import formatear_celular_chile
from utils.despacho_web_export import (
    generar_excel_resumen_productos,
    nombre_archivo_export,
    respuesta_excel,
)
from utils.despacho_web_imprimir import preparar_factura_impresion
from utils.despacho_web_maps import (
    MAX_PARADAS_POR_ENLACE,
    normalizar_direccion_maps,
    partir_ruta_google,
    url_buscar_direccion,
)
from utils.env_config import ors_settings
from utils.despacho_web_pdf_parser import parse_factura_pdf_bytes
from utils.despacho_web_pdf_split import dividir_pdf_por_paginas
from utils.despacho_web_service import (
    ESTADOS_ORDEN,
    TRANSPORTES,
    OrdenDuplicadaError,
    actualizar_orden,
    asegurar_productos,
    contar_ordenes,
    contar_ordenes_filtradas,
    eliminar_orden,
    guardar_orden,
    listar_detalle_export_lineas,
    listar_detalle_orden,
    listar_lineas_por_producto,
    listar_ordenes,
    listar_ordenes_index_inbox,
    listar_ordenes_para_ruta,
    listar_ordenes_recientes,
    listar_productos_activos,
    contar_ordenes_index_inbox,
    obtener_orden,
    orden_existe,
    resumir_ventas_por_producto,
    sanear_texto_web,
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
            ordenes = listar_ordenes_index_inbox(cur, comuna=comuna_filtro or None)
            total_inbox = contar_ordenes_index_inbox(cur, comuna=comuna_filtro or None)
    finally:
        conn.close()
    return render_template(
        "despacho_web/index.html",
        ordenes=ordenes,
        comuna_filtro=comuna_filtro,
        total_inbox=total_inbox,
        max_pdfs=MAX_PDFS,
        max_paginas_masivo=MAX_PAGINAS_MASIVO,
    )


@despacho_web_bp.route("/productos")
@login_requerido
@permiso_modulo("despacho_web")
def productos():
    from utils.despacho_web_tables import TBL_PRODUCTOS

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT producto_id, nombre, sku, descripcion
                FROM {TBL_PRODUCTOS}
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
    from utils.despacho_web_service import _generar_sku_unico
    from utils.despacho_web_tables import TBL_PRODUCTOS

    nombre = (request.form.get("nombre") or "").strip()
    sku = (request.form.get("sku") or "").strip() or None
    if not nombre:
        flash("Nombre de producto obligatorio.", "danger")
        return redirect(url_for("despacho_web.productos"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT producto_id, sku FROM {TBL_PRODUCTOS} WHERE nombre = %s LIMIT 1",
                (nombre,),
            )
            existente = cur.fetchone()
            if existente:
                if sku and sku != existente.get("sku"):
                    cur.execute(
                        f"UPDATE {TBL_PRODUCTOS} SET sku = %s WHERE producto_id = %s",
                        (sku, existente["producto_id"]),
                    )
            else:
                sku_final = _generar_sku_unico(cur, nombre, sku)
                cur.execute(
                    f"""
                    INSERT INTO {TBL_PRODUCTOS} (sku, nombre, descripcion, unidad_medida)
                    VALUES (%s, %s, %s, 'unidad')
                    """,
                    (sku_final, nombre, "Alta manual DespachoWeb"),
                )
        conn.commit()
        flash(f'Producto "{nombre}" guardado.', "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al guardar producto: {e}", "danger")
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


@despacho_web_bp.route("/procesar-masivo", methods=["POST"])
@login_requerido
@permiso_modulo("despacho_web")
def procesar_masivo():
    f = request.files.get("pdf_masivo")
    if not f or not f.filename:
        flash("Seleccione un PDF multipágina.", "warning")
        return redirect(url_for("despacho_web.index"))

    if not f.filename.lower().endswith(".pdf"):
        flash("El archivo debe ser PDF.", "warning")
        return redirect(url_for("despacho_web.index"))

    data = f.read()
    if not data:
        flash("Archivo vacío.", "warning")
        return redirect(url_for("despacho_web.index"))

    errores = []
    try:
        paginas = dividir_pdf_por_paginas(data)
    except Exception as e:
        flash(f"No se pudo leer el PDF: {e}", "danger")
        return redirect(url_for("despacho_web.index"))

    if len(paginas) > MAX_PAGINAS_MASIVO:
        flash(f"Máximo {MAX_PAGINAS_MASIVO} páginas por PDF masivo.", "warning")
        return redirect(url_for("despacho_web.index"))

    nombre_orig = secure_filename(f.filename) or "facturas_masivas.pdf"
    archivos = []
    for i, page_bytes in enumerate(paginas):
        etiqueta = f"{nombre_orig} — pág. {i + 1}"
        try:
            parsed = parse_factura_pdf_bytes(page_bytes)
            parsed["pagina_origen"] = i + 1
            archivos.append((etiqueta, page_bytes, parsed))
        except Exception as e:
            errores.append(f"Pág. {i + 1}: {e}")

    if not archivos:
        flash(
            "No se pudo procesar ninguna página: " + "; ".join(errores),
            "danger",
        )
        return redirect(url_for("despacho_web.index"))

    nombres_nuevos: list[str] = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for _etiq, _data, parsed in archivos:
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
    batch_id = crear_batch_masivo(usuario, nombre_orig, data, archivos)
    session["despacho_web_batch"] = batch_id

    if errores:
        flash("Algunas páginas fallaron: " + "; ".join(errores), "warning")

    return redirect(url_for("despacho_web.resumen_lote", batch_id=batch_id))


@despacho_web_bp.route("/resumen-lote/<batch_id>")
@login_requerido
@permiso_modulo("despacho_web")
def resumen_lote(batch_id):
    manifest = cargar_batch(batch_id)
    if not manifest or manifest.get("modo") != "bulk":
        flash("Lote masivo no encontrado o expirado.", "warning")
        return redirect(url_for("despacho_web.index"))

    filas = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for it in manifest.get("items", []):
                parsed = it.get("parsed") or {}
                n_orden = str(parsed.get("n_orden") or "").strip()
                duplicado = bool(n_orden and orden_existe(cur, n_orden))
                adv = parsed.get("advertencias") or []
                filas.append(
                    {
                        "idx": it.get("idx"),
                        "pagina": it.get("pagina") or (it.get("idx", 0) + 1),
                        "n_orden": n_orden,
                        "cliente": parsed.get("cliente") or "",
                        "comuna": parsed.get("comuna") or "",
                        "estado": parsed.get("estado") or "Pendiente",
                        "num_lineas": len(parsed.get("lineas") or []),
                        "advertencias": adv,
                        "duplicado": duplicado,
                        "status": it.get("status"),
                    }
                )
    finally:
        conn.close()

    pendientes = contar_pendientes(manifest)
    return render_template(
        "despacho_web/resumen_lote.html",
        batch_id=batch_id,
        manifest=manifest,
        filas=filas,
        pendientes=pendientes,
        total=len(filas),
    )


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
        archivar_original_masivo(batch_id, manifest)
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
        estados=ESTADOS_ORDEN,
        modo_lote=manifest.get("modo") or "unit",
        pagina_origen=item.get("pagina") or parsed.get("pagina_origen"),
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
            archivar_original_masivo(batch_id, manifest)
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
        archivar_original_masivo(batch_id, manifest)
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
    orden_por = request.args.get("sort", "").strip() or None
    orden_dir = request.args.get("dir", "").strip() or None
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
                orden_por=orden_por,
                orden_dir=orden_dir,
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
        sort_col=orden_por or "creado_at",
        sort_dir=(orden_dir or "desc").lower(),
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


@despacho_web_bp.route("/ordenes/<n_orden>/imprimir")
@login_requerido
@permiso_modulo("despacho_web")
def orden_imprimir(n_orden):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            orden = obtener_orden(cur, n_orden)
            if not orden:
                flash(f"Orden N° {n_orden} no encontrada.", "warning")
                return redirect(url_for("despacho_web.ordenes"))
            detalle = listar_detalle_orden(cur, n_orden)
    finally:
        conn.close()

    factura = preparar_factura_impresion(orden, detalle)
    return render_template("despacho_web/imprimir_factura.html", factura=factura)


def _paradas_desde_payload(data: dict) -> list[dict]:
    """Normaliza lista de paradas desde JSON del cliente."""
    out = []
    for i, p in enumerate(data.get("paradas") or []):
        if isinstance(p, str):
            out.append({"id": i + 1, "direccion": p, "n_orden": "", "cliente": ""})
            continue
        n_orden = str(p.get("n_orden") or "").strip()
        direccion = (p.get("direccion") or "").strip()
        comuna = (p.get("comuna") or "").strip()
        if not direccion and n_orden:
            continue
        out.append(
            {
                "id": int(p.get("id") or i + 1),
                "n_orden": n_orden,
                "cliente": (p.get("cliente") or "").strip(),
                "comuna": comuna,
                "direccion": normalizar_direccion_maps(direccion, comuna),
            }
        )
    return out


def _enlaces_google(origen: str, paradas: list[dict], volver_origen: bool) -> list[dict]:
    dirs = [p["direccion"] for p in paradas if p.get("direccion")]
    return partir_ruta_google(origen, dirs, volver_origen=volver_origen)


@despacho_web_bp.route("/ruta")
@login_requerido
@permiso_modulo("despacho_web")
def ruta():
    comuna = request.args.get("comuna", "").strip() or None
    transporte = request.args.get("transporte", "").strip() or None
    buscar = request.args.get("q", "").strip() or None
    ors = ors_settings()

    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                ordenes = listar_ordenes_para_ruta(
                    cur,
                    comuna=comuna,
                    transporte=transporte,
                    buscar=buscar,
                )
        finally:
            conn.close()

        html = render_template(
            "despacho_web/ruta.html",
            ordenes=ordenes,
            comuna_filtro=sanear_texto_web(comuna or ""),
            transporte_filtro=sanear_texto_web(transporte or ""),
            buscar=sanear_texto_web(buscar or ""),
            transportes=TRANSPORTES,
            origen_default=sanear_texto_web(ors["origen_default"]),
            ors_configurado=ors["configurado"],
            max_paradas_enlace=MAX_PARADAS_POR_ENLACE,
        )
        # base.html u otros contextos pueden traer surrogates; limpiar HTML completo.
        return sanear_texto_web(html)
    except Exception as e:
        current_app.logger.exception("despacho_web ruta: %s", e)
        flash(
            "No se pudo abrir Armar ruta. Verifique que el deploy incluyó "
            "templates/despacho_web/ruta.html y reinicie la app en cPanel.",
            "danger",
        )
        return redirect(url_for("despacho_web.index"))


@despacho_web_bp.route("/ruta/optimizar", methods=["POST"])
@login_requerido
@permiso_modulo("despacho_web")
def ruta_optimizar():
    from utils.despacho_web_ors import OrsError, optimizar_paradas

    data = request.get_json(silent=True) or {}
    origen = (data.get("origen") or ors_settings()["origen_default"]).strip()
    volver_origen = bool(data.get("volver_origen"))
    paradas = _paradas_desde_payload(data)
    if not paradas:
        return jsonify({"success": False, "error": "Seleccione al menos una parada."}), 400

    try:
        for i, p in enumerate(paradas):
            p["id"] = i + 1
        result = optimizar_paradas(origen, paradas, volver_origen=volver_origen)
        enlaces = _enlaces_google(origen, result["paradas"], volver_origen)
        return jsonify(
            {
                "success": True,
                "paradas": result["paradas"],
                "advertencias": result.get("advertencias") or [],
                "no_geocodificadas": result.get("no_geocodificadas") or [],
                "enlaces": enlaces,
            }
        )
    except OrsError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        current_app.logger.exception("ORS optimize: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@despacho_web_bp.route("/ruta/enlaces", methods=["POST"])
@login_requerido
@permiso_modulo("despacho_web")
def ruta_enlaces():
    """Genera enlaces Google Maps con el orden actual (sin optimizar)."""
    data = request.get_json(silent=True) or {}
    origen = (data.get("origen") or ors_settings()["origen_default"]).strip()
    volver_origen = bool(data.get("volver_origen"))
    paradas = _paradas_desde_payload(data)
    if not paradas:
        return jsonify({"success": False, "error": "Seleccione al menos una parada."}), 400
    enlaces = _enlaces_google(origen, paradas, volver_origen)
    return jsonify({"success": True, "enlaces": enlaces})


@despacho_web_bp.route("/ruta/maps/<n_orden>")
@login_requerido
@permiso_modulo("despacho_web")
def ruta_maps_una(n_orden):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            orden = obtener_orden(cur, n_orden)
    finally:
        conn.close()
    if not orden:
        flash(f"Orden N° {n_orden} no encontrada.", "warning")
        return redirect(url_for("despacho_web.ruta"))
    url = url_buscar_direccion(
        normalizar_direccion_maps(orden.get("direccion") or "", orden.get("comuna") or "")
    )
    return redirect(url)


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


@despacho_web_bp.route("/resumen-productos")
@login_requerido
@permiso_modulo("despacho_web")
def resumen_productos():
    desde = request.args.get("desde", "").strip() or None
    hasta = request.args.get("hasta", "").strip() or None
    comuna = request.args.get("comuna", "").strip() or None
    estado = request.args.get("estado", "").strip() or None
    producto_sel = request.args.get("producto", "").strip() or None
    orden_por = request.args.get("sort", "").strip() or None
    orden_dir = request.args.get("dir", "").strip() or None

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            resumen = resumir_ventas_por_producto(
                cur,
                desde=desde,
                hasta=hasta,
                comuna=comuna,
                estado=estado,
                orden_por=orden_por,
                orden_dir=orden_dir,
            )
            detalle = []
            if producto_sel:
                detalle = listar_lineas_por_producto(
                    cur,
                    producto_sel,
                    desde=desde,
                    hasta=hasta,
                    comuna=comuna,
                    estado=estado,
                    orden_por=orden_por,
                    orden_dir=orden_dir,
                )
            num_ordenes = contar_ordenes_filtradas(
                cur, desde=desde, hasta=hasta, comuna=comuna, estado=estado
            )
    finally:
        conn.close()

    totales = {
        "cantidad": sum(float(r.get("cantidad_total") or 0) for r in resumen),
        "monto": sum(int(r.get("monto_total") or 0) for r in resumen),
        "productos": len(resumen),
        "ordenes": num_ordenes,
    }

    return render_template(
        "despacho_web/resumen_productos.html",
        resumen=resumen,
        detalle=detalle,
        producto_sel=producto_sel,
        estados=ESTADOS_ORDEN,
        desde=desde or "",
        hasta=hasta or "",
        comuna_filtro=comuna or "",
        estado_filtro=estado or "",
        totales=totales,
        sort_col=orden_por or "cantidad_total",
        sort_dir=(orden_dir or "desc").lower(),
    )


@despacho_web_bp.route("/resumen-productos/exportar")
@login_requerido
@permiso_modulo("despacho_web")
def resumen_productos_exportar():
    desde = request.args.get("desde", "").strip() or None
    hasta = request.args.get("hasta", "").strip() or None
    comuna = request.args.get("comuna", "").strip() or None
    estado = request.args.get("estado", "").strip() or None
    producto = request.args.get("producto", "").strip() or None

    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                resumen = resumir_ventas_por_producto(
                    cur, desde=desde, hasta=hasta, comuna=comuna, estado=estado
                )
                lineas = listar_detalle_export_lineas(
                    cur,
                    desde=desde,
                    hasta=hasta,
                    comuna=comuna,
                    estado=estado,
                    producto=producto,
                )
        finally:
            conn.close()

        filtros = {
            "Desde": desde or "",
            "Hasta": hasta or "",
            "Comuna": comuna or "",
            "Estado orden": estado or "",
            "Producto": producto or "",
        }
        buf = generar_excel_resumen_productos(resumen, lineas, filtros=filtros)
        return respuesta_excel(buf, nombre_archivo_export())
    except Exception as e:
        current_app.logger.exception("Error export Excel DespachoWeb: %s", e)
        flash(f"No se pudo generar el Excel: {e}", "danger")
        return redirect(
            url_for(
                "despacho_web.resumen_productos",
                desde=desde or "",
                hasta=hasta or "",
                comuna=comuna or "",
                estado=estado or "",
                producto=producto or "",
            )
        )

