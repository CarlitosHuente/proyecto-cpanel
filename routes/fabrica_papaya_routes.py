from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from utils.auth import login_requerido, permiso_modulo
from utils.db import get_db_connection
from utils.fabrica_papaya_semana import iso_anio_semana, semana_anterior, semana_siguiente
from utils.fabrica_papaya_service import (
    detalle_dia,
    eliminar_despacho,
    eliminar_snapshot_fecha,
    eliminar_transformacion,
    ensure_catalogo_base,
    guardar_despacho,
    guardar_snapshot_stock,
    guardar_stock_real_semana,
    guardar_transformacion,
    informe_mes,
    informe_semana,
    listar_conceptos_stockeables,
    listar_snapshots_stock,
    obtener_snapshot_fecha,
    stock_al_cierre,
    upsert_dia_elaboracion,
    upsert_dia_mp,
    _dec,
)

fabrica_papaya_bp = Blueprint("fabrica_papaya", __name__, url_prefix="/fabrica-papaya")


def _puede_editar() -> bool:
    return session.get("rol") in ("supervisor", "superusuario")


def _puede_admin() -> bool:
    return session.get("rol") == "superusuario"


def requiere_edicion(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        if not _puede_editar():
            flash("Solo supervisor o superusuario pueden modificar datos.", "danger")
            return redirect(request.referrer or url_for("fabrica_papaya.informe_semanal"))
        return f(*args, **kwargs)

    return decorado


def requiere_admin(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        if not _puede_admin():
            flash("Solo el superusuario puede acceder a esta pantalla.", "danger")
            return redirect(url_for("fabrica_papaya.informe_semanal"))
        return f(*args, **kwargs)

    return decorado


def _parse_fecha(s: str):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_decimal_form(name: str, default="0") -> Decimal:
    raw = request.form.get(name, default)
    return _dec(raw)


@fabrica_papaya_bp.route("/")
@fabrica_papaya_bp.route("/semana")
@login_requerido
@permiso_modulo("fabrica_papaya")
def informe_semanal():
    ensure_catalogo_base()
    hoy = date.today()
    anio_def, sem_def = iso_anio_semana(hoy)
    anio = request.args.get("anio", anio_def, type=int)
    semana = request.args.get("semana", sem_def, type=int)

    try:
        data = informe_semana(anio, semana)
    except Exception as exc:
        flash(f"Error al cargar informe: {exc}", "danger")
        data = informe_semana(anio_def, sem_def)

    prev_a, prev_s = semana_anterior(anio, semana)
    next_a, next_s = semana_siguiente(anio, semana)

    return render_template(
        "fabrica_papaya/informe_semanal.html",
        informe=data,
        anio=anio,
        semana=semana,
        prev_anio=prev_a,
        prev_semana=prev_s,
        next_anio=next_a,
        next_semana=next_s,
        puede_editar=_puede_editar(),
        puede_admin=_puede_admin(),
    )


@fabrica_papaya_bp.route("/mes")
@login_requerido
@permiso_modulo("fabrica_papaya")
def informe_mensual():
    ensure_catalogo_base()
    hoy = date.today()
    anio = request.args.get("anio", hoy.year, type=int)
    mes = request.args.get("mes", hoy.month, type=int)
    if mes > 12:
        mes = 1
        anio += 1
    elif mes < 1:
        mes = 12
        anio -= 1

    data = informe_mes(anio, mes)
    prev_mes, prev_anio = (mes - 1, anio) if mes > 1 else (12, anio - 1)
    next_mes, next_anio = (mes + 1, anio) if mes < 12 else (1, anio + 1)

    return render_template(
        "fabrica_papaya/resumen_mes.html",
        informe=data,
        anio=anio,
        mes=mes,
        prev_anio=prev_anio,
        prev_mes=prev_mes,
        next_anio=next_anio,
        next_mes=next_mes,
        puede_editar=_puede_editar(),
        puede_admin=_puede_admin(),
    )


@fabrica_papaya_bp.route("/dia/<fecha_str>")
@login_requerido
@permiso_modulo("fabrica_papaya")
def ver_dia(fecha_str):
    ensure_catalogo_base()
    fecha = _parse_fecha(fecha_str)
    if not fecha:
        flash("Fecha inválida.", "danger")
        return redirect(url_for("fabrica_papaya.informe_semanal"))

    data = detalle_dia(fecha)
    anio, semana = iso_anio_semana(fecha)

    return render_template(
        "fabrica_papaya/dia.html",
        d=data,
        fecha=fecha,
        anio_iso=anio,
        semana_iso=semana,
        puede_editar=_puede_editar(),
        puede_admin=_puede_admin(),
    )


@fabrica_papaya_bp.route("/dia/<fecha_str>/mp", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
@requiere_edicion
def guardar_mp(fecha_str):
    fecha = _parse_fecha(fecha_str)
    if not fecha:
        flash("Fecha inválida.", "danger")
        return redirect(url_for("fabrica_papaya.informe_semanal"))

    upsert_dia_mp(
        fecha,
        {
            "entrada_huerto_kg": request.form.get("entrada_huerto_kg"),
            "entrada_externa_kg": request.form.get("entrada_externa_kg"),
            "kg_a_elaboracion": request.form.get("kg_a_elaboracion"),
            "kg_descarte": request.form.get("kg_descarte"),
            "comentario_descarte": request.form.get("comentario_descarte"),
            "kg_venta_calibre": request.form.get("kg_venta_calibre"),
            "observaciones": request.form.get("observaciones"),
        },
        session.get("usuario") or "",
    )
    flash("Materia prima guardada.", "success")
    return redirect(url_for("fabrica_papaya.ver_dia", fecha_str=fecha.isoformat()))


@fabrica_papaya_bp.route("/dia/<fecha_str>/elaboracion", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
@requiere_edicion
def guardar_elaboracion(fecha_str):
    fecha = _parse_fecha(fecha_str)
    if not fecha:
        flash("Fecha inválida.", "danger")
        return redirect(url_for("fabrica_papaya.informe_semanal"))

    upsert_dia_elaboracion(
        fecha,
        {
            "kg_elaborados": request.form.get("kg_elaborados"),
            "kg_directa": request.form.get("kg_directa"),
            "kg_congelada": request.form.get("kg_congelada"),
            "observaciones": request.form.get("observaciones"),
        },
        session.get("usuario") or "",
    )
    flash("Elaboración guardada.", "success")
    return redirect(url_for("fabrica_papaya.ver_dia", fecha_str=fecha.isoformat()))


@fabrica_papaya_bp.route("/dia/<fecha_str>/transformacion", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
@requiere_edicion
def guardar_transformacion_route(fecha_str):
    fecha = _parse_fecha(fecha_str)
    if not fecha:
        flash("Fecha inválida.", "danger")
        return redirect(url_for("fabrica_papaya.informe_semanal"))

    reg_id = request.form.get("id", type=int)
    fuente = request.form.get("fuente")
    if fuente not in ("directa", "congelada"):
        flash("Fuente inválida.", "danger")
        return redirect(url_for("fabrica_papaya.ver_dia", fecha_str=fecha.isoformat()))

    guardar_transformacion(
        fecha,
        {
            "concepto_id": request.form.get("concepto_id"),
            "fuente": fuente,
            "kg_fuente": request.form.get("kg_fuente"),
            "cantidad_producida": request.form.get("cantidad_producida"),
            "observaciones": request.form.get("observaciones"),
        },
        session.get("usuario") or "",
        reg_id,
    )
    flash("Transformación guardada.", "success")
    return redirect(url_for("fabrica_papaya.ver_dia", fecha_str=fecha.isoformat()))


@fabrica_papaya_bp.route("/transformacion/<int:reg_id>/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
@requiere_edicion
def borrar_transformacion(reg_id):
    fecha_str = request.form.get("fecha")
    eliminar_transformacion(reg_id)
    flash("Línea de transformación eliminada.", "success")
    if fecha_str:
        return redirect(url_for("fabrica_papaya.ver_dia", fecha_str=fecha_str))
    return redirect(url_for("fabrica_papaya.informe_semanal"))


@fabrica_papaya_bp.route("/dia/<fecha_str>/despacho", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
@requiere_edicion
def guardar_despacho_route(fecha_str):
    fecha = _parse_fecha(fecha_str)
    if not fecha:
        flash("Fecha inválida.", "danger")
        return redirect(url_for("fabrica_papaya.informe_semanal"))

    reg_id = request.form.get("id", type=int)
    guardar_despacho(
        fecha,
        {
            "concepto_id": request.form.get("concepto_id"),
            "cantidad": request.form.get("cantidad"),
            "observaciones": request.form.get("observaciones"),
        },
        session.get("usuario") or "",
        reg_id,
    )
    flash("Despacho guardado.", "success")
    return redirect(url_for("fabrica_papaya.ver_dia", fecha_str=fecha.isoformat()))


@fabrica_papaya_bp.route("/despacho/<int:reg_id>/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
@requiere_edicion
def borrar_despacho(reg_id):
    fecha_str = request.form.get("fecha")
    eliminar_despacho(reg_id)
    flash("Despacho eliminado.", "success")
    if fecha_str:
        return redirect(url_for("fabrica_papaya.ver_dia", fecha_str=fecha_str))
    return redirect(url_for("fabrica_papaya.informe_semanal"))


@fabrica_papaya_bp.route("/stock-real", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
def stock_real():
    ensure_catalogo_base()
    hoy = date.today()
    anio_def, sem_def = iso_anio_semana(hoy)
    anio = request.args.get("anio", anio_def, type=int)
    semana = request.args.get("semana", sem_def, type=int)

    conn = get_db_connection()
    cur = conn.cursor()
    conceptos = listar_conceptos_stockeables(cur)
    cur.execute(
        """
        SELECT concepto_id, cantidad FROM papaya_semana_stock_real
        WHERE anio = %s AND semana_iso = %s
        """,
        (anio, semana),
    )
    actuales = {r["concepto_id"]: r["cantidad"] for r in cur.fetchall() or []}
    conn.close()

    if request.method == "POST" and _puede_editar():
        filas = {}
        for c in conceptos:
            cid = c["id"]
            raw = request.form.get(f"cant_{cid}", "")
            if raw is None or str(raw).strip() == "":
                continue
            filas[cid] = _dec(raw)
        guardar_stock_real_semana(anio, semana, filas, session.get("usuario") or "")
        flash("Stock real semanal guardado.", "success")
        return redirect(url_for("fabrica_papaya.stock_real", anio=anio, semana=semana))

    prev_a, prev_s = semana_anterior(anio, semana)
    next_a, next_s = semana_siguiente(anio, semana)

    from utils.fabrica_papaya_semana import rango_semana_iso

    lun, dom = rango_semana_iso(anio, semana)
    propuesta = stock_al_cierre(dom)

    filas = []
    for c in conceptos:
        cid = c["id"]
        filas.append(
            {
                "concepto": c,
                "real": actuales.get(cid),
                "propuesta": propuesta.get(cid, Decimal("0")),
            }
        )

    return render_template(
        "fabrica_papaya/stock_real.html",
        anio=anio,
        semana=semana,
        lun=lun,
        dom=dom,
        filas=filas,
        prev_anio=prev_a,
        prev_semana=prev_s,
        next_anio=next_a,
        next_semana=next_s,
        puede_editar=_puede_editar(),
    )


@fabrica_papaya_bp.route("/conceptos", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
@requiere_admin
def conceptos():
    ensure_catalogo_base()
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        accion = request.form.get("accion")
        if accion == "nuevo":
            cur.execute(
                """
                INSERT INTO papaya_conceptos (codigo, nombre, tipo, unidad, producto_erp, orden, activo)
                VALUES (%s, %s, %s, %s, %s, %s, 1)
                """,
                (
                    (request.form.get("codigo") or "").strip().lower().replace(" ", "_")[:64],
                    (request.form.get("nombre") or "").strip()[:255],
                    request.form.get("tipo"),
                    request.form.get("unidad"),
                    (request.form.get("producto_erp") or "").strip() or None,
                    request.form.get("orden", 500, type=int),
                ),
            )
            conn.commit()
            flash("Concepto creado.", "success")
        elif accion == "toggle":
            cur.execute(
                "UPDATE papaya_conceptos SET activo = NOT activo WHERE id = %s",
                (request.form.get("id"),),
            )
            conn.commit()
            flash("Estado actualizado.", "success")

    cur.execute(
        """
        SELECT * FROM papaya_conceptos ORDER BY
            FIELD(tipo, 'materia_prima', 'intermedio', 'terminado', 'movimiento'), orden, nombre
        """
    )
    lista = cur.fetchall() or []
    conn.close()

    return render_template(
        "fabrica_papaya/conceptos.html",
        conceptos=lista,
    )


@fabrica_papaya_bp.route("/cierre-stock", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
def cierre_stock():
    ensure_catalogo_base()
    conn = get_db_connection()
    cur = conn.cursor()
    conceptos = listar_conceptos_stockeables(cur)
    conn.close()

    if request.method == "POST":
        if not _puede_editar():
            flash("Solo supervisor o superusuario pueden guardar snapshots.", "danger")
            return redirect(url_for("fabrica_papaya.cierre_stock"))
        fecha = _parse_fecha(request.form.get("fecha"))
        tipo = request.form.get("tipo", "inicial")
        if tipo not in ("inicial", "ajuste"):
            tipo = "inicial"
        if not fecha:
            flash("Fecha inválida.", "danger")
        else:
            filas = {}
            for c in conceptos:
                raw = request.form.get(f"cant_{c['id']}", "")
                if str(raw).strip() == "":
                    continue
                filas[c["id"]] = _dec(raw)
            if not filas:
                flash("Ingresa al menos un concepto con cantidad.", "warning")
            else:
                n = guardar_snapshot_stock(
                    fecha,
                    tipo,
                    filas,
                    (request.form.get("notas") or "").strip() or None,
                    session.get("usuario") or "",
                )
                label = "Stock inicial" if tipo == "inicial" else "Ajuste"
                flash(f"{label} guardado ({n} conceptos) al {fecha.strftime('%d/%m/%Y')}.", "success")
                return redirect(url_for("fabrica_papaya.cierre_stock", fecha=fecha.isoformat(), tipo=tipo))

    fecha_str = request.args.get("fecha")
    fecha_sel = _parse_fecha(fecha_str) if fecha_str else None
    tipo_sel = request.args.get("tipo", "inicial")
    if tipo_sel not in ("inicial", "ajuste"):
        tipo_sel = "inicial"

    actuales = {}
    notas_sel = None
    if fecha_sel:
        tipo_db, actuales = obtener_snapshot_fecha(fecha_sel)
        if tipo_db:
            tipo_sel = tipo_db
        if actuales:
            first = next(iter(actuales.values()))
            notas_sel = first.get("notas")

    propuesta = {}
    if fecha_sel:
        propuesta_raw = stock_al_cierre(fecha_sel, excluir_snapshot_fecha=fecha_sel)
        propuesta = propuesta_raw

    historial = listar_snapshots_stock(30)

    return render_template(
        "fabrica_papaya/cierre_stock.html",
        conceptos=conceptos,
        fecha_sel=fecha_sel,
        tipo_sel=tipo_sel,
        actuales=actuales,
        notas_sel=notas_sel,
        propuesta=propuesta,
        historial=historial,
        puede_editar=_puede_editar(),
    )


@fabrica_papaya_bp.route("/cierre-stock/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica_papaya")
@requiere_edicion
def eliminar_snapshot():
    fecha = _parse_fecha(request.form.get("fecha"))
    if not fecha:
        flash("Fecha inválida.", "danger")
    else:
        n = eliminar_snapshot_fecha(fecha)
        flash(f"Snapshot eliminado ({n} filas).", "success")
    return redirect(url_for("fabrica_papaya.cierre_stock"))
