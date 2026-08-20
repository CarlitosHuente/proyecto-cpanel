"""Módulo Fondos por Rendir (FxR) / Rendición de Gastos."""
from __future__ import annotations

import os
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from utils.auth import login_requerido, permiso_modulo
from utils import fxr_db as db
from utils.fxr_files import (
    abs_path,
    borrar_archivo_local,
    guardar_jpeg_pulido,
    guardar_upload,
    pdf_eliminar_paginas,
)
from utils.fxr_pdf import generar_pdf_rendicion, layout_default_para_imagenes
from utils.fxr_drive import subir_pdf_rendicion
import json

fxr_bp = Blueprint("fxr", __name__, url_prefix="/fxr")

_esquema_ok = False


def _ensure():
    global _esquema_ok
    if not _esquema_ok:
        db.asegurar_esquema_fxr()
        _esquema_ok = True


@fxr_bp.before_request
def _before():
    _ensure()


def _email() -> str:
    return session.get("usuario") or ""


def _es_super() -> bool:
    return session.get("rol") == "superusuario"


def _perfil() -> dict:
    return db.perfil_usuario(_email())


def _nombre_usuario() -> str:
    """Nombre legible desde usuarios_huente.nombre; si no hay, el email."""
    return _perfil()["nombre"]


def super_requerido(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _es_super():
            abort(403)
        return f(*args, **kwargs)

    return wrapped


def _puede_ver_rendicion(r: dict) -> bool:
    if not r:
        return False
    if _es_super():
        return True
    return r.get("usuario_email") == _email()


# ---------- Home / inbox ----------

@fxr_bp.route("/")
@login_requerido
@permiso_modulo("fxr")
def index():
    email = _email()
    inbox = db.listar_inbox(email)
    rendiciones = db.listar_rendiciones_usuario(email)
    preparadas = db.listar_rendiciones_preparadas() if _es_super() else []
    aprobadas = db.listar_rendiciones_aprobadas() if _es_super() else []
    return render_template(
        "fxr/index.html",
        inbox=inbox,
        rendiciones=rendiciones,
        preparadas=preparadas,
        aprobadas=aprobadas,
        es_super=_es_super(),
    )


@fxr_bp.route("/aprobadas")
@login_requerido
@permiso_modulo("fxr")
@super_requerido
def aprobadas():
    return render_template(
        "fxr/aprobadas.html",
        items=db.listar_rendiciones_aprobadas(500),
    )


@fxr_bp.route("/subir", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
def subir():
    email = _email()
    archivo = request.files.get("archivo")
    modo = request.form.get("modo") or "guardar"  # guardar | registrar
    try:
        rel, mime, pages = guardar_upload(archivo, email.split("@")[0], escaner=True)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("fxr.index"))
    cid = db.crear_comprobante(email, rel, mime, pages)
    flash("Comprobante guardado en inbox.", "success")
    if modo == "registrar":
        # crea rendición borrador de 1 ítem y abre edición
        perfil = _perfil()
        area_def = (perfil.get("fxr_cc_nombre") or "")[:120]
        rid = db.crear_rendicion(email, perfil["nombre"], area=area_def)
        db.vincular_comprobantes_a_rendicion(rid, [cid], email)
        lineas = db.listar_lineas(rid)
        if lineas:
            return redirect(url_for("fxr.editar_linea", linea_id=lineas[0]["id"], overlay=1))
        return redirect(url_for("fxr.rendicion", rid=rid))
    return redirect(url_for("fxr.index"))


def _redirect_despues_paginas(comp: dict, next_linea: str | None):
    if next_linea and str(next_linea).isdigit():
        return redirect(url_for("fxr.editar_linea", linea_id=int(next_linea)))
    if comp.get("rendicion_id"):
        return redirect(url_for("fxr.rendicion", rid=comp["rendicion_id"]))
    return redirect(url_for("fxr.index"))


@fxr_bp.route("/comprobante/<int:cid>/paginas", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fxr")
def paginas_pdf(cid):
    comp = db.obtener_comprobante(cid)
    if not comp or (comp["usuario_email"] != _email() and not _es_super()):
        abort(404)
    # Solo dueño en borrador/inbox (o super) puede recortar
    if comp["usuario_email"] == _email() and comp.get("rendicion_id"):
        r = db.obtener_rendicion(comp["rendicion_id"])
        if r and r["estado"] not in ("borrador", "rechazada") and not _es_super():
            flash("No se pueden editar páginas en este estado.", "warning")
            return redirect(url_for("fxr.rendicion", rid=r["id"]))
    if "pdf" not in (comp.get("mime") or "") and not str(comp.get("archivo_local", "")).endswith(".pdf"):
        flash("Solo aplica a PDF.", "warning")
        return _redirect_despues_paginas(comp, request.args.get("next_linea") or request.form.get("next_linea"))
    next_linea = request.args.get("next_linea") or request.form.get("next_linea")
    if request.method == "POST":
        eliminar = request.form.getlist("eliminar")
        indices = [int(x) for x in eliminar if str(x).isdigit()]
        try:
            nuevo, n = pdf_eliminar_paginas(comp["archivo_local"], indices)
            db.actualizar_comprobante_archivo(cid, nuevo, "application/pdf", n)
            flash(f"PDF actualizado ({n} página(s)).", "success")
        except ValueError as e:
            flash(str(e), "danger")
        return _redirect_despues_paginas(comp, next_linea)
    return render_template("fxr/paginas_pdf.html", comp=comp, next_linea=next_linea)


@fxr_bp.route("/archivo/<int:cid>")
@login_requerido
@permiso_modulo("fxr")
def servir_archivo(cid):
    comp = db.obtener_comprobante(cid)
    if not comp:
        abort(404)
    if comp["usuario_email"] != _email() and not _es_super():
        # permitir si está en rendición preparada/aprobada y es revisor
        if not _es_super():
            abort(403)
    path = abs_path(comp["archivo_local"])
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype=comp.get("mime") or "application/octet-stream")


@fxr_bp.route("/comprobante/<int:cid>/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
def eliminar_comprobante_inbox(cid):
    """Borra del inbox (archivo + fila). Dueño o superusuario."""
    ok, msg, rel = db.eliminar_comprobante_inbox(cid, _email(), es_super=_es_super())
    if ok and rel:
        borrar_archivo_local(rel)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("fxr.index"))


def _puede_editar_comprobante(comp: dict) -> bool:
    if not comp or comp["usuario_email"] != _email():
        return False
    if not comp.get("rendicion_id"):
        return True
    r = db.obtener_rendicion(comp["rendicion_id"])
    return bool(r and r["estado"] in ("borrador", "rechazada"))


@fxr_bp.route("/comprobante/<int:cid>/pulir", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fxr")
def pulir_comprobante(cid):
    comp = db.obtener_comprobante(cid)
    if not comp or not _puede_editar_comprobante(comp):
        abort(403)
    mime = (comp.get("mime") or "").lower()
    rel = str(comp.get("archivo_local") or "")
    if "pdf" in mime or rel.lower().endswith(".pdf"):
        flash("Pulir solo aplica a imágenes.", "warning")
        return redirect(url_for("fxr.index"))
    next_linea = request.args.get("next_linea") or request.form.get("next_linea")
    if request.method == "POST":
        archivo = request.files.get("archivo")
        if not archivo or not archivo.filename:
            flash("No se recibió la imagen pulida.", "danger")
            return redirect(url_for("fxr.pulir_comprobante", cid=cid, next_linea=next_linea or None))
        try:
            data = archivo.read()
            nuevo = guardar_jpeg_pulido(data, _email().split("@")[0])
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("fxr.pulir_comprobante", cid=cid, next_linea=next_linea or None))
        anterior = comp.get("archivo_local")
        db.actualizar_comprobante_archivo(cid, nuevo, "image/jpeg", 1)
        if anterior and anterior != nuevo:
            borrar_archivo_local(anterior)
        flash("Imagen pulida guardada.", "success")
        if next_linea and str(next_linea).isdigit():
            return redirect(url_for("fxr.editar_linea", linea_id=int(next_linea)))
        if comp.get("rendicion_id"):
            return redirect(url_for("fxr.rendicion", rid=comp["rendicion_id"]))
        return redirect(url_for("fxr.index"))
    return render_template(
        "fxr/pulir.html",
        comp=comp,
        next_linea=next_linea,
        img_url=url_for("fxr.servir_archivo", cid=cid),
        post_url=url_for("fxr.pulir_comprobante", cid=cid),
    )


# ---------- Armar rendición ----------

@fxr_bp.route("/rendicion/nueva", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
def nueva_rendicion():
    email = _email()
    ids = [int(x) for x in request.form.getlist("comp_ids") if str(x).isdigit()]
    if not ids:
        flash("Selecciona al menos un comprobante.", "warning")
        return redirect(url_for("fxr.index"))
    perfil = _perfil()
    area = (request.form.get("area") or "").strip() or (perfil.get("fxr_cc_nombre") or "")
    rid = db.crear_rendicion(email, perfil["nombre"], area=area[:120])
    n = db.vincular_comprobantes_a_rendicion(rid, ids, email)
    flash(f"Rendición creada con {n} comprobante(s).", "success")
    return redirect(url_for("fxr.rendicion", rid=rid))


@fxr_bp.route("/rendicion/<int:rid>")
@login_requerido
@permiso_modulo("fxr")
def rendicion(rid):
    r = db.obtener_rendicion(rid)
    if not r or not _puede_ver_rendicion(r):
        abort(404)
    lineas = db.listar_lineas(rid)
    dups_bloquean = db.hay_duplicados_sin_autorizar(rid)
    editable = r["estado"] in ("borrador", "rechazada") and r["usuario_email"] == _email()
    # Solo mostrar faltantes tras intentar Preparar (no al crear la rendición)
    faltantes = session.pop(f"fxr_faltantes_{rid}", None) or []
    return render_template(
        "fxr/rendicion.html",
        r=r,
        lineas=lineas,
        dups_bloquean=dups_bloquean,
        es_super=_es_super(),
        editable=editable,
        faltantes=faltantes,
        centros=db.listar_centros_costo(solo_activos=True),
        tipos_gasto=db.listar_tipos_gasto(solo_activos=True),
    )


@fxr_bp.route("/rendicion/<int:rid>/cabecera", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
def actualizar_cabecera(rid):
    r = db.obtener_rendicion(rid)
    if not r or r["usuario_email"] != _email() or r["estado"] not in ("borrador", "rechazada"):
        abort(403)
    db.actualizar_rendicion_campos(
        rid,
        area=(request.form.get("area") or "").strip()[:120],
        fecha_rendicion=request.form.get("fecha_rendicion") or None,
        nombre_snapshot=(request.form.get("nombre_snapshot") or r["nombre_snapshot"])[:190],
        comentario_firma=(request.form.get("comentario_firma") or "").strip() or None,
    )
    flash("Cabecera actualizada.", "success")
    return redirect(url_for("fxr.rendicion", rid=rid))


@fxr_bp.route("/linea/<int:linea_id>", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fxr")
def editar_linea(linea_id):
    linea = db.obtener_linea(linea_id)
    if not linea:
        abort(404)
    r = db.obtener_rendicion(linea["rendicion_id"])
    if not r or not _puede_ver_rendicion(r):
        abort(404)
    editable = r["estado"] in ("borrador", "rechazada") and r["usuario_email"] == _email()
    overlay = request.args.get("overlay") == "1" or request.form.get("overlay") == "1"
    dups = []
    if request.method == "POST":
        if not editable:
            abort(403)
        ok, msg, dups = db.guardar_linea(
            linea_id,
            {
                "tipo_doc": request.form.get("tipo_doc"),
                "n_doc": request.form.get("n_doc"),
                "fecha_comprobante": request.form.get("fecha_comprobante"),
                "concepto": request.form.get("concepto"),
                "tipo_gasto_id": request.form.get("tipo_gasto_id") or None,
                "centro_costo_id": request.form.get("centro_costo_id") or None,
                "monto": request.form.get("monto"),
                "observaciones": request.form.get("observaciones"),
            },
        )
        flash(msg, "warning" if dups else ("success" if ok else "danger"))
        if ok and request.form.get("volver"):
            return redirect(url_for("fxr.rendicion", rid=r["id"]))
        linea = db.obtener_linea(linea_id)
    else:
        if linea.get("n_doc_norm"):
            dups = db.buscar_duplicados(linea["tipo_doc"], linea["n_doc_norm"], excluir_linea_id=linea_id)
    return render_template(
        "fxr/editar_linea.html",
        linea=linea,
        r=r,
        editable=editable,
        overlay=overlay,
        dups=dups,
        centros=db.listar_centros_costo(solo_activos=True),
        tipos_gasto=db.listar_tipos_gasto(solo_activos=True),
        tipos_doc=db.TIPOS_DOC,
    )


@fxr_bp.route("/linea/<int:linea_id>/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
def eliminar_linea(linea_id):
    """Siempre vuelve el documento al inbox (no borra el archivo)."""
    ok, msg = db.quitar_linea_a_inbox(linea_id, _email())
    flash(msg, "success" if ok else "danger")
    rid = request.form.get("rid")
    if rid and str(rid).isdigit():
        return redirect(url_for("fxr.rendicion", rid=int(rid)))
    return redirect(url_for("fxr.index"))


@fxr_bp.route("/rendicion/<int:rid>/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
def eliminar_rendicion(rid):
    ok, msg = db.eliminar_rendicion_a_inbox(rid, _email())
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("fxr.index"))


@fxr_bp.route("/rendicion/<int:rid>/preview")
@login_requerido
@permiso_modulo("fxr")
def preview(rid):
    r = db.obtener_rendicion(rid)
    if not r or not _puede_ver_rendicion(r):
        abort(404)
    lineas = db.listar_lineas(rid)
    dups_info = db.info_duplicados_para_pdf(lineas)
    return render_template(
        "fxr/preview.html",
        r=r,
        lineas=lineas,
        dups_info=dups_info,
    )


# ---------- Preparar / revisión ----------

@fxr_bp.route("/rendicion/<int:rid>/preparar", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
def preparar(rid):
    r = db.obtener_rendicion(rid)
    if not r or r["usuario_email"] != _email():
        abort(403)
    if r["estado"] not in ("borrador", "rechazada"):
        flash("Estado inválido.", "danger")
        return redirect(url_for("fxr.rendicion", rid=rid))
    errs = db.validar_para_preparar(rid)
    if errs:
        session[f"fxr_faltantes_{rid}"] = errs
        flash("Completa los datos faltantes antes de marcar Preparada.", "danger")
        return redirect(url_for("fxr.rendicion", rid=rid))
    db.actualizar_rendicion_campos(
        rid, estado="preparada", preparada_at=datetime.now(), motivo_rechazo=None
    )
    db.registrar_hist(rid, r["estado"], "preparada", _email(), "Enviada a revisión")
    flash("Rendición marcada como Preparada.", "success")
    # Superusuario puede revisar/aprobar la suya de inmediato
    if _es_super():
        return redirect(url_for("fxr.revision_detalle", rid=rid))
    return redirect(url_for("fxr.rendicion", rid=rid))


@fxr_bp.route("/revision")
@login_requerido
@permiso_modulo("fxr")
@super_requerido
def revision_cola():
    return render_template("fxr/revision_cola.html", items=db.listar_rendiciones_preparadas())


@fxr_bp.route("/revision/<int:rid>")
@login_requerido
@permiso_modulo("fxr")
@super_requerido
def revision_detalle(rid):
    r = db.obtener_rendicion(rid)
    if not r or r["estado"] != "preparada":
        flash("No está en estado Preparada.", "warning")
        return redirect(url_for("fxr.revision_cola"))
    lineas = db.listar_lineas(rid)
    dups_info = db.info_duplicados_para_pdf(lineas)
    return render_template(
        "fxr/revision_detalle.html",
        r=r,
        lineas=lineas,
        dups_info=dups_info,
        dups_bloquean=db.hay_duplicados_sin_autorizar(rid),
        idx=max(0, min(int(request.args.get("i") or 0), max(0, len(lineas) - 1))),
    )


@fxr_bp.route("/linea/<int:linea_id>/autorizar-duplicado", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
@super_requerido
def autorizar_dup(linea_id):
    ok, msg = db.autorizar_duplicado(linea_id, _email())
    flash(msg, "success" if ok else "danger")
    linea = db.obtener_linea(linea_id)
    idx = request.form.get("i") or request.args.get("i") or "0"
    return redirect(url_for("fxr.revision_detalle", rid=linea["rendicion_id"], i=idx))


@fxr_bp.route("/rendicion/<int:rid>/rechazar", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
@super_requerido
def rechazar(rid):
    r = db.obtener_rendicion(rid)
    if not r or r["estado"] != "preparada":
        abort(400)
    motivo = (request.form.get("motivo") or "").strip()
    if not motivo:
        flash("Indica motivo de rechazo.", "danger")
        return redirect(url_for("fxr.revision_detalle", rid=rid))
    db.actualizar_rendicion_campos(
        rid,
        estado="rechazada",
        motivo_rechazo=motivo,
        rechazada_at=datetime.now(),
        rechazada_por=_email(),
    )
    db.registrar_hist(rid, "preparada", "rechazada", _email(), motivo)
    flash("Rendición rechazada.", "warning")
    return redirect(url_for("fxr.revision_cola"))


@fxr_bp.route("/rendicion/<int:rid>/aprobar", methods=["POST"])
@login_requerido
@permiso_modulo("fxr")
@super_requerido
def aprobar(rid):
    r = db.obtener_rendicion(rid)
    if not r or r["estado"] != "preparada":
        abort(400)
    pendientes = db.hay_duplicados_sin_autorizar(rid)
    if pendientes:
        flash("Hay N° documento duplicados sin autorizar.", "danger")
        return redirect(url_for("fxr.revision_detalle", rid=rid))

    lineas = db.listar_lineas(rid)
    dups_info = db.info_duplicados_para_pdf(lineas)
    correlativo = db.siguiente_correlativo()
    db.actualizar_rendicion_campos(rid, correlativo=correlativo)
    r = db.obtener_rendicion(rid)

    imgs = [
        l
        for l in lineas
        if l.get("archivo_local")
        and "pdf" not in (l.get("mime") or "").lower()
        and not str(l.get("archivo_local") or "").lower().endswith(".pdf")
    ]
    layout = db.obtener_layout_rendicion(rid)
    if not layout and imgs:
        layout = layout_default_para_imagenes(imgs)

    pdf_bytes = generar_pdf_rendicion(
        r, lineas, dups_info, current_app.root_path, layout=layout
    )
    nombre = f"FxR-{correlativo}-{r['nombre_snapshot'][:40].replace(' ', '_')}.pdf"
    ok, msg, url = subir_pdf_rendicion(pdf_bytes, nombre)
    if not ok:
        db.actualizar_rendicion_campos(rid, correlativo=None)
        flash(f"Error al subir a Drive (no se aprobó ni borró staging): {msg}", "danger")
        return redirect(url_for("fxr.revision_detalle", rid=rid))

    # extraer file id si viene en URL
    drive_id = None
    if url and "/d/" in url:
        try:
            drive_id = url.split("/d/")[1].split("/")[0]
        except Exception:
            pass

    db.actualizar_rendicion_campos(
        rid,
        estado="aprobada",
        aprobada_at=datetime.now(),
        aprobada_por=_email(),
        pdf_drive_id=drive_id,
        pdf_url=url,
    )
    db.registrar_hist(rid, "preparada", "aprobada", _email(), f"PDF {nombre}")

    for l in lineas:
        borrar_archivo_local(l.get("archivo_local"))
        db.marcar_comprobante_consumido(l["comprobante_id"])

    flash(f"Rendición N° {correlativo} aprobada y subida a Drive.", "success")
    return redirect(url_for("fxr.rendicion", rid=rid))


# ---------- Catálogos superusuario ----------

@fxr_bp.route("/admin/centros-costo", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fxr")
@super_requerido
def admin_cc():
    if request.method == "POST":
        db.upsert_catalogo(
            "fxr_centro_costo",
            request.form.get("codigo") or "",
            request.form.get("nombre") or "",
            1 if request.form.get("activo") else 0,
            int(request.form["id"]) if request.form.get("id") else None,
        )
        flash("Centro de costo guardado.", "success")
        return redirect(url_for("fxr.admin_cc"))
    return render_template("fxr/admin_catalogo.html", titulo="Centros de costo", items=db.listar_centros_costo(), endpoint="fxr.admin_cc")


@fxr_bp.route("/admin/tipos-gasto", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fxr")
@super_requerido
def admin_tg():
    if request.method == "POST":
        db.upsert_catalogo(
            "fxr_tipo_gasto",
            request.form.get("codigo") or "",
            request.form.get("nombre") or "",
            1 if request.form.get("activo") else 0,
            int(request.form["id"]) if request.form.get("id") else None,
            permite_agrupar=1 if request.form.get("permite_agrupar") else 0,
        )
        flash("Tipo de gasto guardado.", "success")
        return redirect(url_for("fxr.admin_tg"))
    return render_template(
        "fxr/admin_tipos_gasto.html",
        items=db.listar_tipos_gasto(),
    )


@fxr_bp.route("/rendicion/<int:rid>/collage", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fxr")
def collage(rid):
    """Editor interactivo: coloca imágenes (no PDF) en hojas Carta."""
    r = db.obtener_rendicion(rid)
    if not r or not _puede_ver_rendicion(r):
        abort(404)
    puede_editar = (
        (r["estado"] in ("borrador", "rechazada") and r["usuario_email"] == _email())
        or (_es_super() and r["estado"] == "preparada")
    )
    lineas = db.listar_lineas(rid)
    imgs = [
        {
            "id": l["id"],
            "url": url_for("fxr.servir_archivo", cid=l["comprobante_id"]),
            "concepto": l.get("concepto") or "",
            "tipo_gasto": l.get("tipo_gasto_nombre") or "",
            "permite_agrupar": bool(l.get("permite_agrupar")),
            "monto": l.get("monto") or 0,
        }
        for l in lineas
        if l.get("archivo_local")
        and "pdf" not in (l.get("mime") or "").lower()
        and not str(l.get("archivo_local") or "").lower().endswith(".pdf")
    ]
    if request.method == "POST":
        if not puede_editar:
            abort(403)
        raw = request.form.get("layout_json") or "{}"
        try:
            layout = json.loads(raw)
            if not isinstance(layout, dict) or "pages" not in layout:
                raise ValueError("layout inválido")
            db.guardar_layout_rendicion(rid, layout)
            flash("Disposición de imágenes guardada.", "success")
        except Exception as e:
            flash(f"No se pudo guardar el layout: {e}", "danger")
        return redirect(url_for("fxr.collage", rid=rid))

    layout = db.obtener_layout_rendicion(rid)
    if not layout:
        # default solo con imágenes (agrupables primero, luego el resto)
        layout = layout_default_para_imagenes(
            [{"id": i["id"]} for i in imgs]
        )
    return render_template(
        "fxr/collage.html",
        r=r,
        imgs=imgs,
        layout_json=json.dumps(layout),
        puede_editar=puede_editar,
    )
