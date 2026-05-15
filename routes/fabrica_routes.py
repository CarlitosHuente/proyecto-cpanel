from collections import defaultdict
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from utils.auth import login_requerido, permiso_modulo
from utils.db import get_db_connection
import calendar

fabrica_bp = Blueprint("fabrica", __name__)


def solo_superusuario(f):
    """Solo rol superusuario (pantallas de mantenimiento directo de datos)."""

    @wraps(f)
    def decorado(*args, **kwargs):
        if session.get("rol") != "superusuario":
            flash("Solo el superusuario puede acceder al administrador de datos de fábrica.", "danger")
            return redirect(url_for("fabrica.calendario_produccion"))
        return f(*args, **kwargs)

    return decorado


def _optional_decimal(val):
    if val is None or (isinstance(val, str) and not val.strip()):
        return None
    try:
        return Decimal(str(val).replace(",", ".").strip())
    except InvalidOperation:
        return None


def _decimal_or_zero(val):
    if val is None or val == "":
        return Decimal("0")
    try:
        return Decimal(str(val).replace(",", ".").strip())
    except InvalidOperation:
        return Decimal("0")


def _int_or_zero(val):
    if val is None or val == "":
        return 0
    try:
        return int(float(str(val).replace(",", ".").strip()))
    except (TypeError, ValueError):
        return 0


def _neto_gr(queso_inicial, queso_pizza, queso_merma):
    return float(queso_inicial or 0) - float(queso_pizza or 0) - float(queso_merma or 0)


def _rendimiento_pct(queso_inicial, queso_pizza, queso_merma):
    """% del queso inicial que queda neto para empanada (tras pizza y merma)."""
    try:
        qi = float(queso_inicial or 0)
        if qi <= 0:
            return Decimal("0.00")
        neto = _neto_gr(qi, queso_pizza, queso_merma)
        return Decimal(str(round(max(0.0, neto) / qi * 100, 2)))
    except (TypeError, ValueError, ZeroDivisionError):
        return Decimal("0.00")


def _jsonable_fila(row):
    """Serialización segura para `tojson` en plantilla (date/Decimal)."""
    out = {}
    for k, v in dict(row).items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, date) and not isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


@fabrica_bp.route("/fabrica/calendario")
@login_requerido
@permiso_modulo("fabrica")
def calendario_produccion():
    anio = request.args.get("anio", datetime.now().year, type=int)
    mes = request.args.get("mes", datetime.now().month, type=int)

    if mes > 12:
        mes = 1
        anio += 1
    elif mes < 1:
        mes = 12
        anio -= 1

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *, DAY(fecha) AS dia, DATE_FORMAT(fecha, '%%Y-%%m-%%d') AS fecha_str
        FROM fabrica_produccion
        WHERE MONTH(fecha) = %s AND YEAR(fecha) = %s
        ORDER BY fecha ASC, id ASC
        """,
        (mes, anio),
    )
    rows = cur.fetchall()

    by_dia = defaultdict(list)
    for row in rows:
        by_dia[row["dia"]].append(row)

    datos = {}
    for dia, filas in by_dia.items():
        filas = sorted(filas, key=lambda r: r["id"])
        total_cant = sum(int(f.get("cant_producida") or 0) for f in filas)
        neto = sum(
            _neto_gr(f.get("queso_inicial_gr"), f.get("queso_pizza_gr"), f.get("queso_merma_gr"))
            for f in filas
        )
        prom = round(neto / total_cant, 1) if total_cant > 0 else 0.0
        tot_ini = sum(float(f.get("queso_inicial_gr") or 0) for f in filas)
        tot_merma = sum(float(f.get("queso_merma_gr") or 0) for f in filas)
        merma_pct_dia = round(tot_merma / tot_ini * 100, 1) if tot_ini > 0 else 0.0
        fecha_label = filas[0].get("fecha_str") or str(filas[0].get("fecha"))
        datos[dia] = {
            "filas": [_jsonable_fila(f) for f in filas],
            "n": len(filas),
            "total_cant": total_cant,
            "prom_queso": prom,
            "merma_pct_dia": merma_pct_dia,
            "fecha_label": fecha_label,
        }

    cur.execute(
        """
        SELECT
            COALESCE(SUM(cant_producida), 0) AS total_cant,
            COALESCE(SUM(queso_inicial_gr), 0) AS total_inicial_gr,
            COALESCE(SUM(COALESCE(queso_pizza_gr, 0)), 0) AS total_pizza_gr,
            COALESCE(SUM(queso_merma_gr), 0) AS merma_gr,
            COALESCE(
                SUM(
                    queso_inicial_gr - COALESCE(queso_pizza_gr, 0) - queso_merma_gr
                ),
                0
            ) AS queso_neto_gr,
            COUNT(*) AS num_registros
        FROM fabrica_produccion
        WHERE MONTH(fecha) = %s AND YEAR(fecha) = %s
        """,
        (mes, anio),
    )
    agg = cur.fetchone() or {}
    conn.close()

    total_cant = int(agg.get("total_cant") or 0)
    total_inicial = float(agg.get("total_inicial_gr") or 0)
    total_pizza = float(agg.get("total_pizza_gr") or 0)
    merma_gr = float(agg.get("merma_gr") or 0)
    queso_neto = float(agg.get("queso_neto_gr") or 0)
    num_reg = int(agg.get("num_registros") or 0)
    prom_queso = (queso_neto / total_cant) if total_cant > 0 else None
    merma_pct = (merma_gr / total_inicial * 100) if total_inicial > 0 else None

    resumen_mes = {
        "total_elaborado": total_cant,
        "total_inicial_gr": round(total_inicial, 2),
        "total_pizza_gr": round(total_pizza, 2),
        "merma_total_gr": round(merma_gr, 2),
        "merma_pct": round(merma_pct, 2) if merma_pct is not None else None,
        "queso_utilizado_gr": round(queso_neto, 2),
        "promedio_gr_por_empanada": round(prom_queso, 2) if prom_queso is not None else None,
        "num_registros": num_reg,
    }

    cal = calendar.monthcalendar(anio, mes)
    meses_es = [
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    ]

    ultimo_dia = calendar.monthrange(anio, mes)[1]
    fecha_min = date(anio, mes, 1)
    fecha_max = date(anio, mes, ultimo_dia)
    hoy = date.today()
    if hoy.year == anio and hoy.month == mes and fecha_min <= hoy <= fecha_max:
        fecha_default = hoy
    else:
        fecha_default = fecha_min

    return render_template(
        "fabrica/calendario.html",
        calendario=cal,
        datos=datos,
        mes_nombre=meses_es[mes - 1],
        mes=mes,
        anio=anio,
        resumen_mes=resumen_mes,
        fecha_min_str=fecha_min.isoformat(),
        fecha_max_str=fecha_max.isoformat(),
        fecha_default_str=fecha_default.isoformat(),
        es_superusuario=session.get("rol") == "superusuario",
    )


@fabrica_bp.route("/fabrica/registro", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica")
def nuevo_registro_produccion():
    mes = request.form.get("mes", type=int) or datetime.now().month
    anio = request.form.get("anio", type=int) or datetime.now().year

    def _redirect_error(msg):
        flash(msg, "danger")
        return redirect(url_for("fabrica.calendario_produccion", mes=mes, anio=anio))

    fecha_raw = (request.form.get("fecha") or "").strip()
    try:
        fecha_d = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
    except ValueError:
        return _redirect_error("Fecha inválida.")

    if fecha_d.month != mes or fecha_d.year != anio:
        return _redirect_error("La fecha debe pertenecer al mes que estás viendo.")

    cant = _int_or_zero(request.form.get("cant_producida"))
    if cant <= 0:
        return _redirect_error("Cantidad producida debe ser mayor a cero.")

    q_ini = _decimal_or_zero(request.form.get("queso_inicial_gr"))
    q_pizza = _decimal_or_zero(request.form.get("queso_pizza_gr"))
    q_mer = _decimal_or_zero(request.form.get("queso_merma_gr"))
    if q_ini < 0 or q_mer < 0 or q_pizza < 0:
        return _redirect_error("Los gramos de queso no pueden ser negativos.")
    if q_pizza + q_mer > q_ini:
        return _redirect_error("Pizza + merma no puede superar el queso inicial.")

    encargada = (request.form.get("encargada") or "").strip()[:100] or None
    observaciones = (request.form.get("observaciones") or "").strip() or None
    drive_id = (request.form.get("drive_id") or "").strip()[:255] or None

    rend = _rendimiento_pct(q_ini, q_pizza, q_mer)

    queso_unidad = _int_or_zero(request.form.get("queso_unidad_stock"))
    queso_trozos = _decimal_or_zero(request.form.get("queso_trozos_gr_stock"))
    harina_sacos = _int_or_zero(request.form.get("harina_sacos_stock"))
    sal_kg = _decimal_or_zero(request.form.get("sal_kg_stock"))
    manteca_und = _int_or_zero(request.form.get("manteca_und_stock"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO fabrica_produccion (
            fecha, encargada, cant_producida,
            queso_inicial_gr, queso_pizza_gr, queso_merma_gr, rendimiento,
            drive_id, observaciones,
            queso_unidad_stock, queso_trozos_gr_stock, harina_sacos_stock, sal_kg_stock, manteca_und_stock
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            fecha_d,
            encargada,
            cant,
            q_ini,
            q_pizza,
            q_mer,
            rend,
            drive_id,
            observaciones,
            queso_unidad,
            queso_trozos,
            harina_sacos,
            sal_kg,
            manteca_und,
        ),
    )
    conn.commit()
    conn.close()

    flash("Registro de producción guardado correctamente.", "success")
    return redirect(url_for("fabrica.calendario_produccion", mes=mes, anio=anio))


def _admin_redirect():
    mes = request.form.get("redir_mes", type=int) or datetime.now().month
    anio = request.form.get("redir_anio", type=int) or datetime.now().year
    return redirect(url_for("fabrica.admin_datos", mes=mes, anio=anio))


@fabrica_bp.route("/fabrica/admin/datos")
@login_requerido
@permiso_modulo("fabrica")
@solo_superusuario
def admin_datos():
    anio = request.args.get("anio", datetime.now().year, type=int)
    mes = request.args.get("mes", datetime.now().month, type=int)
    if mes > 12:
        mes = 1
        anio += 1
    elif mes < 1:
        mes = 12
        anio -= 1

    meses_es = [
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    ]

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM fabrica_produccion
        WHERE MONTH(fecha) = %s AND YEAR(fecha) = %s
        ORDER BY fecha DESC, id DESC
        """,
        (mes, anio),
    )
    registros = cur.fetchall()
    conn.close()

    return render_template(
        "fabrica/admin_datos.html",
        registros=registros,
        mes=mes,
        anio=anio,
        mes_nombre=meses_es[mes - 1],
    )


@fabrica_bp.route("/fabrica/admin/datos/actualizar/<int:registro_id>", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica")
@solo_superusuario
def admin_datos_actualizar(registro_id):
    fecha_raw = (request.form.get("fecha") or "").strip()
    try:
        fecha_d = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
    except ValueError:
        flash("Fecha inválida.", "danger")
        return _admin_redirect()

    cant = _int_or_zero(request.form.get("cant_producida"))
    if cant <= 0:
        flash("Cantidad producida debe ser mayor a cero.", "danger")
        return _admin_redirect()

    q_ini = _decimal_or_zero(request.form.get("queso_inicial_gr"))
    q_pizza = _decimal_or_zero(request.form.get("queso_pizza_gr"))
    q_mer = _decimal_or_zero(request.form.get("queso_merma_gr"))
    if q_ini < 0 or q_mer < 0 or q_pizza < 0:
        flash("Los gramos de queso no pueden ser negativos.", "danger")
        return _admin_redirect()
    if q_pizza + q_mer > q_ini:
        flash("Pizza + merma no puede superar el queso inicial.", "danger")
        return _admin_redirect()

    encargada = (request.form.get("encargada") or "").strip()[:100] or None
    observaciones = (request.form.get("observaciones") or "").strip() or None
    drive_id = (request.form.get("drive_id") or "").strip()[:255] or None
    rend = _rendimiento_pct(q_ini, q_pizza, q_mer)

    queso_unidad = _int_or_zero(request.form.get("queso_unidad_stock"))
    queso_trozos = _decimal_or_zero(request.form.get("queso_trozos_gr_stock"))
    harina_sacos = _int_or_zero(request.form.get("harina_sacos_stock"))
    sal_kg = _decimal_or_zero(request.form.get("sal_kg_stock"))
    manteca_und = _int_or_zero(request.form.get("manteca_und_stock"))
    harina_qty = _optional_decimal(request.form.get("harina_qty"))
    manteca_qty = _optional_decimal(request.form.get("manteca_qty"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM fabrica_produccion WHERE id = %s", (registro_id,))
    if not cur.fetchone():
        conn.close()
        flash("Registro no encontrado.", "danger")
        return _admin_redirect()

    cur.execute(
        """
        UPDATE fabrica_produccion SET
            fecha = %s,
            encargada = %s,
            cant_producida = %s,
            queso_inicial_gr = %s,
            queso_pizza_gr = %s,
            queso_merma_gr = %s,
            rendimiento = %s,
            harina_qty = %s,
            manteca_qty = %s,
            drive_id = %s,
            observaciones = %s,
            queso_unidad_stock = %s,
            queso_trozos_gr_stock = %s,
            harina_sacos_stock = %s,
            sal_kg_stock = %s,
            manteca_und_stock = %s
        WHERE id = %s
        """,
        (
            fecha_d,
            encargada,
            cant,
            q_ini,
            q_pizza,
            q_mer,
            rend,
            harina_qty,
            manteca_qty,
            drive_id,
            observaciones,
            queso_unidad,
            queso_trozos,
            harina_sacos,
            sal_kg,
            manteca_und,
            registro_id,
        ),
    )
    conn.commit()
    conn.close()
    flash(f"Registro #{registro_id} actualizado.", "success")
    return _admin_redirect()


@fabrica_bp.route("/fabrica/admin/datos/eliminar/<int:registro_id>", methods=["POST"])
@login_requerido
@permiso_modulo("fabrica")
@solo_superusuario
def admin_datos_eliminar(registro_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM fabrica_produccion WHERE id = %s", (registro_id,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    if n:
        flash(f"Registro #{registro_id} eliminado.", "success")
    else:
        flash("Registro no encontrado.", "warning")
    return _admin_redirect()
