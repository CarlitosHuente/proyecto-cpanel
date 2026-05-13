import io
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

import pandas as pd
from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from utils.arqueo_caja_canal_ui_config import (
    etiqueta_canal,
    load_ui_config,
    normalizar_entradas_config,
    save_ui_config,
    sort_tuple_canal,
)
from utils.arqueo_caja_import import (
    filas_para_insert,
    leer_arqueo_excel,
    normalizar_canal,
    parse_monto_entrada,
    parse_propina_opcional,
)
from utils.auth import login_requerido, permiso_modulo
from utils.db import get_db_connection
from utils.formato_dinero import dinero_presentacion

arqueo_caja_bp = Blueprint("arqueo_caja", __name__, url_prefix="/arqueo-caja")


def _listar_sucursales():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sucursal_id, nombre_sucursal FROM Sucursales ORDER BY nombre_sucursal"
            )
            return cur.fetchall() or []
    finally:
        conn.close()


def _sumar_sistema_por_canal(rows):
    """rows: list dict desc_cta, debe, haber -> dict canal_norm -> {neto, muestra}"""
    buckets = {}
    for r in rows:
        cn = normalizar_canal(r.get("desc_cta"))
        if not cn:
            continue
        net = Decimal(str(r["debe"])) - Decimal(str(r["haber"]))
        if cn not in buckets:
            buckets[cn] = {"neto": Decimal("0"), "muestra": (r.get("desc_cta") or "").strip()}
        buckets[cn]["neto"] += net
    return buckets


def _fmt_esperado_sistema(val: Decimal) -> str:
    return dinero_presentacion(val)


def _entero_dinero(val) -> int:
    d = Decimal(str(val))
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _parse_fecha(s) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _fecha_sugerida_terreno(sucursal_id: int) -> date:
    """Última fecha con captura terreno en esa sucursal + 1; si no hay, última FEC_COMPR en líneas + 1; si no, hoy."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(fecha) AS mx FROM arqueo_caja_terreno WHERE sucursal_id = %s",
                (sucursal_id,),
            )
            row = cur.fetchone()
            mx = row["mx"] if row else None
            if mx:
                if hasattr(mx, "date"):
                    mx = mx.date()
                return mx + timedelta(days=1)
            cur.execute(
                "SELECT MAX(fec_compr) AS mx FROM arqueo_caja_lineas WHERE sucursal_id = %s",
                (sucursal_id,),
            )
            row2 = cur.fetchone()
            mx2 = row2["mx"] if row2 else None
            if mx2:
                if hasattr(mx2, "date"):
                    mx2 = mx2.date()
                return mx2 + timedelta(days=1)
    finally:
        conn.close()
    return date.today()


def _canales_dropdown(_sucursal_id: int) -> List[dict]:
    """Opciones edición puntual: mismos canales que terreno (globales por import en cualquier sucursal)."""
    merged = _distinct_norms_globales()
    norms = sorted(merged.keys(), key=lambda cn: (sort_tuple_canal(cn), cn))
    out = []
    for cn in norms:
        muestra = merged[cn]
        out.append(
            {
                "norm": cn,
                "etiqueta": etiqueta_canal(cn, muestra),
                "muestra": muestra,
            }
        )
    return out


def _filas_grilla_terreno(sucursal_id: int, fecha: date, caja: int) -> List[dict]:
    """Canales = unión(normas globales en líneas, capturas ya guardadas en terreno para esta caja/fecha).
    Esperado sistema = neto import (DEBE−HABER) solo para esta sucursal y fecha."""
    norm_map_global = _distinct_norms_globales()
    pref = {}
    sistema_rows = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT desc_cta, debe, haber FROM arqueo_caja_lineas
                   WHERE sucursal_id = %s AND fec_compr = %s""",
                (sucursal_id, fecha),
            )
            sistema_rows = cur.fetchall() or []
            cur.execute(
                """SELECT canal_norm, canal_raw, monto, propina FROM arqueo_caja_terreno
                   WHERE sucursal_id = %s AND fecha = %s AND caja = %s""",
                (sucursal_id, fecha, caja),
            )
            for r in cur.fetchall() or []:
                pref[r["canal_norm"]] = {
                    "monto": r["monto"],
                    "propina": r.get("propina"),
                }
    finally:
        conn.close()
    sis_buckets = _sumar_sistema_por_canal(sistema_rows)
    norms = set(norm_map_global.keys()) | set(pref.keys())
    norms_sorted = sorted(norms, key=lambda cn: (sort_tuple_canal(cn), cn))
    rows = []
    for cn in norms_sorted:
        p = pref.get(cn, {})
        muestra = norm_map_global.get(cn) or sis_buckets.get(cn, {}).get("muestra") or cn
        lab = etiqueta_canal(cn, muestra)
        m_pref = p.get("monto")
        prop_pref = p.get("propina")
        if cn in sis_buckets:
            esp_txt = _fmt_esperado_sistema(sis_buckets[cn]["neto"])
        else:
            esp_txt = "—"
        rows.append(
            {
                "canonical_norm": cn,
                "etiqueta": lab,
                "esperado_display": esp_txt,
                "monto_pref": "" if m_pref is None else str(m_pref),
                "propina_pref": "" if prop_pref is None else str(prop_pref),
            }
        )
    return rows


def _distinct_norms_globales() -> dict:
    """canal_norm -> texto muestra (primer desc_cta distinto) según import en arqueo_caja_lineas, todas las sucursales."""
    norms = {}
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT DISTINCT TRIM(desc_cta) AS d FROM arqueo_caja_lineas
                   WHERE TRIM(desc_cta) <> '' ORDER BY d"""
            )
            for r in cur.fetchall() or []:
                if not r.get("d"):
                    continue
                raw = str(r["d"]).strip()
                k = normalizar_canal(raw)
                if k and k not in norms:
                    norms[k] = raw
    finally:
        conn.close()
    return norms


@arqueo_caja_bp.route("/")
@login_requerido
@permiso_modulo("arqueo_caja")
def index():
    return render_template("arqueo_caja/index.html")


@arqueo_caja_bp.route("/import", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("arqueo_caja")
def importar():
    sucursales = _listar_sucursales()
    if request.method == "POST":
        sucursal_id = request.form.get("sucursal_id", type=int)
        f = request.files.get("archivo")
        if not sucursal_id:
            flash("Seleccioná una sucursal.", "warning")
            return redirect(url_for("arqueo_caja.importar"))
        if not f or not f.filename:
            flash("Seleccioná un archivo Excel o CSV.", "warning")
            return redirect(url_for("arqueo_caja.importar"))
        fn = secure_filename(f.filename)
        try:
            data, avisos = leer_arqueo_excel(f.stream, fn)
            filas = filas_para_insert(data)
        except Exception as ex:
            flash(f"Error al leer el archivo: {ex}", "danger")
            return redirect(url_for("arqueo_caja.importar"))
        if not filas:
            flash("No quedaron filas válidas para importar.", "warning")
            return redirect(url_for("arqueo_caja.importar"))
        usuario = session.get("usuario", "")
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO arqueo_caja_cargas (sucursal_id, nombre_archivo, registros_insertados, usuario)
                       VALUES (%s, %s, 0, %s)""",
                    (sucursal_id, fn[:250], usuario),
                )
                carga_id = cur.lastrowid
                sql_linea = """INSERT INTO arqueo_caja_lineas
                    (carga_id, sucursal_id, fec_compr, n_comp, cod_comp, desc_cta, debe, haber)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
                batch = [
                    (carga_id, sucursal_id, fc, nc, cc, dc, db, hb)
                    for fc, nc, cc, dc, db, hb in filas
                ]
                cur.executemany(sql_linea, batch)
                cur.execute(
                    "UPDATE arqueo_caja_cargas SET registros_insertados = %s WHERE carga_id = %s",
                    (len(batch), carga_id),
                )
            conn.commit()
        except Exception as ex:
            conn.rollback()
            flash(f"Error al guardar en base de datos: {ex}", "danger")
            return redirect(url_for("arqueo_caja.importar"))
        finally:
            conn.close()
        for a in avisos:
            flash(a, "info")
        flash(f"Carga #{carga_id} guardada: {len(filas)} líneas.", "success")
        return redirect(url_for("arqueo_caja.importar"))

    conn = get_db_connection()
    cargas = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT c.carga_id, c.fecha_carga, c.nombre_archivo, c.registros_insertados, c.usuario,
                          s.nombre_sucursal
                   FROM arqueo_caja_cargas c
                   JOIN Sucursales s ON s.sucursal_id = c.sucursal_id
                   ORDER BY c.carga_id DESC LIMIT 25"""
            )
            cargas = cur.fetchall() or []
    finally:
        conn.close()

    return render_template(
        "arqueo_caja/import.html", sucursales=sucursales, cargas=cargas
    )


@arqueo_caja_bp.route("/revertir/<int:carga_id>", methods=["POST"])
@login_requerido
@permiso_modulo("arqueo_caja")
def revertir(carga_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM arqueo_caja_cargas WHERE carga_id = %s", (carga_id,))
            n = cur.rowcount
        conn.commit()
    except Exception as ex:
        conn.rollback()
        flash(f"No se pudo revertir: {ex}", "danger")
        return redirect(url_for("arqueo_caja.importar"))
    finally:
        conn.close()
    if n:
        flash(f"Carga #{carga_id} revertida.", "success")
    else:
        flash("No se encontró esa carga.", "warning")
    return redirect(url_for("arqueo_caja.importar"))


@arqueo_caja_bp.route("/canales-ui", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("arqueo_caja")
def canales_ui():
    """Etiquetas y orden de canales (JSON en instance/; conciliación sigue por canal_norm)."""
    norm_map = _distinct_norms_globales()
    norms_sorted = sorted(norm_map.keys(), key=lambda cn: (sort_tuple_canal(cn), cn))
    cfg = load_ui_config()
    by_norm = {}
    for e in cfg.get("entries", []):
        k = normalizar_canal(e.get("canonical_norm", "") or "")
        if k:
            by_norm[k] = e

    if request.method == "POST":
        canons = request.form.getlist("canonical_norm")
        labels = request.form.getlist("label")
        sorts = request.form.getlist("sort")
        entries_in = []
        for i, cn in enumerate(canons):
            cn = (cn or "").strip()
            if not cn:
                continue
            lab = (labels[i] if i < len(labels) else "") or ""
            lab = str(lab).strip()
            sort_raw = (sorts[i] if i < len(sorts) else "9999") or "9999"
            try:
                srt = int(sort_raw)
            except (TypeError, ValueError):
                srt = 9999
            entries_in.append({"canonical_norm": cn, "label": lab, "sort": srt})
        entries_in.extend(
            [
                x
                for x in cfg.get("entries", [])
                if normalizar_canal(x.get("canonical_norm", "")) not in norm_map
            ]
        )
        save_ui_config({"entries": normalizar_entradas_config(entries_in)})
        flash("Configuración de canales guardada.", "success")
        return redirect(url_for("arqueo_caja.canales_ui"))

    filas = []
    for cn in norms_sorted:
        muestra = norm_map[cn]
        ex = by_norm.get(cn, {})
        try:
            sort_val = int(ex.get("sort", 9999))
        except (TypeError, ValueError):
            sort_val = 9999
        filas.append(
            {
                "canonical_norm": cn,
                "muestra_bd": muestra,
                "label": (ex.get("label") or "").strip(),
                "sort": sort_val,
                "etiqueta": etiqueta_canal(cn, muestra),
            }
        )
    return render_template(
        "arqueo_caja/canales_ui.html",
        filas=filas,
        config_path="instance/arqueo_canales_ui.json",
    )


@arqueo_caja_bp.route("/terreno", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("arqueo_caja")
def terreno():
    sucursales = _listar_sucursales()

    if request.method == "POST" and request.form.get("bulk_terreno") == "1":
        sucursal_id = request.form.get("sucursal_id", type=int)
        fecha = _parse_fecha(request.form.get("fecha") or "")
        caja = request.form.get("caja", type=int) or 1
        if caja not in (1, 2):
            caja = 1
        if not sucursal_id or not fecha:
            flash("Faltan sucursal o fecha.", "warning")
            return redirect(url_for("arqueo_caja.terreno"))
        canons = request.form.getlist("canon_norm")
        montos = request.form.getlist("monto")
        propinas = request.form.getlist("propina")
        usuario = session.get("usuario", "")
        nm_global = _distinct_norms_globales()
        if len(montos) < len(canons):
            montos.extend([""] * (len(canons) - len(montos)))
        if len(propinas) < len(canons):
            propinas.extend([""] * (len(canons) - len(propinas)))
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                upsert_sql = """INSERT INTO arqueo_caja_terreno
                    (sucursal_id, fecha, caja, canal_raw, canal_norm, monto, propina, notas, usuario)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                    canal_raw=VALUES(canal_raw), monto=VALUES(monto), propina=VALUES(propina),
                    usuario=VALUES(usuario)"""
                for cn, mraw, praw in zip(canons, montos, propinas):
                    cn = (cn or "").strip()
                    if not cn:
                        continue
                    mraw = (mraw or "").strip()
                    if not mraw:
                        cur.execute(
                            """DELETE FROM arqueo_caja_terreno
                               WHERE sucursal_id=%s AND fecha=%s AND caja=%s AND canal_norm=%s""",
                            (sucursal_id, fecha, caja, cn),
                        )
                        continue
                    try:
                        monto = parse_monto_entrada(mraw)
                    except Exception:
                        flash(f"Monto inválido para canal {cn}.", "danger")
                        conn.rollback()
                        return redirect(
                            url_for(
                                "arqueo_caja.terreno",
                                sucursal_id=sucursal_id,
                                fecha=fecha.isoformat(),
                                caja=caja,
                            )
                        )
                    try:
                        propina = parse_propina_opcional(praw)
                    except Exception:
                        flash(f"Propina inválida para canal {cn}.", "danger")
                        conn.rollback()
                        return redirect(
                            url_for(
                                "arqueo_caja.terreno",
                                sucursal_id=sucursal_id,
                                fecha=fecha.isoformat(),
                                caja=caja,
                            )
                        )
                    muestra = nm_global.get(cn, cn)
                    canal_raw = etiqueta_canal(cn, muestra)[:255]
                    cur.execute(
                        upsert_sql,
                        (
                            sucursal_id,
                            fecha,
                            caja,
                            canal_raw,
                            cn,
                            monto,
                            propina,
                            None,
                            usuario,
                        ),
                    )
            conn.commit()
        except Exception as ex:
            conn.rollback()
            flash(f"Error al guardar: {ex}", "danger")
            return redirect(
                url_for(
                    "arqueo_caja.terreno",
                    sucursal_id=sucursal_id,
                    fecha=fecha.isoformat() if fecha else "",
                    caja=caja,
                )
            )
        finally:
            conn.close()
        flash("Totales terreno guardados.", "success")
        return redirect(
            url_for(
                "arqueo_caja.terreno",
                sucursal_id=sucursal_id,
                fecha=fecha.isoformat(),
                caja=caja,
            )
        )

    capturas_agrupadas = []
    filtro_suc = request.args.get("sucursal_id", type=int)
    filtro_fecha = _parse_fecha(request.args.get("fecha") or "")
    filtro_caja = request.args.get("caja", type=int) or None
    if filtro_caja not in (None, 1, 2):
        filtro_caja = None

    fecha_default = _fecha_sugerida_terreno(filtro_suc) if filtro_suc else date.today()
    caja_grilla = request.args.get("caja", type=int) or 1
    if caja_grilla not in (1, 2):
        caja_grilla = 1
    fecha_grilla = filtro_fecha
    if filtro_suc and not fecha_grilla:
        fecha_grilla = fecha_default
    mostrar_grilla = bool(filtro_suc and fecha_grilla)
    canales_filas = []
    if mostrar_grilla:
        canales_filas = _filas_grilla_terreno(filtro_suc, fecha_grilla, caja_grilla)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            q = """SELECT t.sucursal_id, t.fecha, t.caja, s.nombre_sucursal AS nombre_sucursal,
                          COUNT(*) AS n_lineas,
                          COALESCE(SUM(t.monto), 0) AS total_monto,
                          MAX(t.usuario) AS usuario
                   FROM arqueo_caja_terreno t
                   JOIN Sucursales s ON s.sucursal_id = t.sucursal_id
                   WHERE 1=1"""
            params = []
            if filtro_suc:
                q += " AND t.sucursal_id = %s"
                params.append(filtro_suc)
            if filtro_caja in (1, 2):
                q += " AND t.caja = %s"
                params.append(filtro_caja)
            q += """ GROUP BY t.sucursal_id, t.fecha, t.caja, s.nombre_sucursal
                     ORDER BY t.fecha DESC, s.nombre_sucursal, t.caja LIMIT 120"""
            cur.execute(q, params)
            for row in cur.fetchall() or []:
                r = dict(row)
                fe = r["fecha"]
                r["fecha_iso"] = fe.isoformat() if hasattr(fe, "isoformat") else str(fe)[:10]
                capturas_agrupadas.append(r)
    finally:
        conn.close()

    fecha_form_val = (
        fecha_grilla.isoformat()
        if fecha_grilla
        else (filtro_fecha.isoformat() if filtro_fecha else fecha_default.isoformat())
    )
    caja_form_default = filtro_caja if filtro_caja in (1, 2) else caja_grilla

    return render_template(
        "arqueo_caja/terreno.html",
        sucursales=sucursales,
        capturas_agrupadas=capturas_agrupadas,
        filtro_suc=filtro_suc,
        filtro_fecha=filtro_fecha.isoformat() if filtro_fecha else "",
        filtro_caja=filtro_caja or "",
        fecha_form_val=fecha_form_val,
        caja_form_default=caja_form_default,
        mostrar_grilla=mostrar_grilla,
        fecha_grilla=fecha_grilla.isoformat() if fecha_grilla else "",
        caja_grilla=caja_grilla,
        canales_filas=canales_filas,
    )


@arqueo_caja_bp.route("/terreno/bundle/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("arqueo_caja")
def terreno_eliminar_bundle():
    sucursal_id = request.form.get("sucursal_id", type=int)
    fecha = _parse_fecha(request.form.get("fecha") or "")
    caja = request.form.get("caja", type=int) or 1
    if caja not in (1, 2):
        caja = 1
    if not sucursal_id or not fecha:
        flash("Faltan datos para eliminar.", "warning")
        return redirect(url_for("arqueo_caja.terreno"))
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM arqueo_caja_terreno
                   WHERE sucursal_id = %s AND fecha = %s AND caja = %s""",
                (sucursal_id, fecha, caja),
            )
            n = cur.rowcount
        conn.commit()
    except Exception as ex:
        conn.rollback()
        flash(f"No se pudo eliminar: {ex}", "danger")
        return redirect(
            url_for(
                "arqueo_caja.terreno",
                sucursal_id=sucursal_id,
                fecha=fecha.isoformat(),
                caja=caja,
            )
        )
    finally:
        conn.close()
    flash(f"Captura terreno eliminada ({n} filas).", "success")
    return redirect(
        url_for(
            "arqueo_caja.terreno",
            sucursal_id=sucursal_id,
            fecha=fecha.isoformat(),
            caja=caja,
        )
    )


@arqueo_caja_bp.route("/terreno/bundle/notas", methods=["POST"])
@login_requerido
@permiso_modulo("arqueo_caja")
def terreno_bundle_notas():
    """Replica la misma observación en todas las filas terreno de ese día/caja (columna notas existente)."""
    sucursal_id = request.form.get("sucursal_id", type=int)
    fecha = _parse_fecha(request.form.get("fecha") or "")
    caja = request.form.get("caja", type=int) or 1
    semana_ref = _parse_fecha(request.form.get("semana_ref") or "")
    vista_ret = (request.form.get("vista_ret") or "").strip().lower()
    notas = (request.form.get("notas") or "").strip()[:500] or None
    if caja not in (1, 2):
        caja = 1
    if not sucursal_id or not fecha:
        flash("Faltan datos para guardar la observación.", "warning")
        return redirect(url_for("arqueo_caja.cuadratura"))
    conn = get_db_connection()
    n = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE arqueo_caja_terreno SET notas=%s
                   WHERE sucursal_id=%s AND fecha=%s AND caja=%s""",
                (notas, sucursal_id, fecha, caja),
            )
            n = cur.rowcount
        conn.commit()
    except Exception as ex:
        conn.rollback()
        flash(f"No se pudo guardar: {ex}", "danger")
        return redirect(url_for("arqueo_caja.cuadratura"))
    finally:
        conn.close()
    if n == 0:
        flash(
            "No hay captura terreno ese día/caja: cargá la grilla terreno antes de anotar.",
            "warning",
        )
    else:
        flash("Observación guardada en todos los canales de esa caja y día.", "success")
    if vista_ret == "semana" and semana_ref:
        return redirect(
            url_for(
                "arqueo_caja.cuadratura",
                sucursal_id=sucursal_id,
                fecha=semana_ref.isoformat(),
                vista="semana",
                caja=caja,
            )
        )
    return redirect(
        url_for(
            "arqueo_caja.cuadratura",
            sucursal_id=sucursal_id,
            fecha=fecha.isoformat(),
            caja=caja,
            vista="dia",
        )
    )


@arqueo_caja_bp.route("/terreno/editar/<int:registro_id>", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("arqueo_caja")
def terreno_editar(registro_id):
    conn = get_db_connection()
    reg = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT t.*, s.nombre_sucursal FROM arqueo_caja_terreno t
                   JOIN Sucursales s ON s.sucursal_id = t.sucursal_id WHERE t.id = %s""",
                (registro_id,),
            )
            reg = cur.fetchone()
    finally:
        conn.close()
    if not reg:
        flash("Registro no encontrado.", "warning")
        return redirect(url_for("arqueo_caja.terreno"))

    if request.method == "GET":
        fe = reg["fecha"]
        fds = fe.isoformat() if hasattr(fe, "isoformat") else str(fe)[:10]
        cj = int(reg.get("caja") or 1)
        if cj not in (1, 2):
            cj = 1
        return redirect(
            url_for(
                "arqueo_caja.terreno",
                sucursal_id=reg["sucursal_id"],
                fecha=fds,
                caja=cj,
            )
        )

    canales_opciones = _canales_dropdown(reg["sucursal_id"])

    if request.method == "POST":
        fecha = _parse_fecha(request.form.get("fecha") or "")
        caja = request.form.get("caja", type=int) or 1
        if caja not in (1, 2):
            caja = 1
        canal_sel = (request.form.get("canal") or "").strip()
        canal_otro = (request.form.get("canal_otro") or "").strip()
        if canal_sel == "__OTRO__":
            canal_txt = canal_otro
            if not canal_txt.strip():
                flash('Escribí el canal en "Otro".', "warning")
                return redirect(url_for("arqueo_caja.terreno_editar", registro_id=registro_id))
            cn = normalizar_canal(canal_txt)
            canal_raw_display = canal_txt[:255]
        else:
            cn = normalizar_canal(canal_sel)
            muestra = _distinct_norms_globales().get(cn, cn)
            canal_raw_display = etiqueta_canal(cn, muestra)[:255]
        notas = (request.form.get("notas") or "").strip()[:500]
        monto_raw = request.form.get("monto", "")
        propina_raw = request.form.get("propina", "")
        try:
            monto = parse_monto_entrada(monto_raw)
        except Exception:
            flash("Monto inválido.", "warning")
            return redirect(url_for("arqueo_caja.terreno_editar", registro_id=registro_id))
        try:
            propina = parse_propina_opcional(propina_raw)
        except Exception:
            flash("Propina inválida.", "warning")
            return redirect(url_for("arqueo_caja.terreno_editar", registro_id=registro_id))
        if not fecha or not cn:
            flash("Completá fecha y canal.", "warning")
            return redirect(url_for("arqueo_caja.terreno_editar", registro_id=registro_id))
        usuario = session.get("usuario", "")
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id FROM arqueo_caja_terreno
                       WHERE sucursal_id = %s AND fecha = %s AND caja = %s AND canal_norm = %s AND id <> %s""",
                    (reg["sucursal_id"], fecha, caja, cn, registro_id),
                )
                if cur.fetchone():
                    flash(
                        "Ya existe otro registro con esa sucursal, fecha, caja y canal. No se guardó.",
                        "danger",
                    )
                    return redirect(url_for("arqueo_caja.terreno_editar", registro_id=registro_id))
                cur.execute(
                    """UPDATE arqueo_caja_terreno SET fecha=%s, caja=%s, canal_raw=%s, canal_norm=%s,
                       monto=%s, propina=%s, notas=%s, usuario=%s WHERE id=%s""",
                    (
                        fecha,
                        caja,
                        canal_raw_display,
                        cn,
                        monto,
                        propina,
                        notas or None,
                        usuario,
                        registro_id,
                    ),
                )
            conn.commit()
        except Exception as ex:
            conn.rollback()
            flash(f"Error al actualizar: {ex}", "danger")
            return redirect(url_for("arqueo_caja.terreno_editar", registro_id=registro_id))
        finally:
            conn.close()
        flash("Registro actualizado.", "success")
        return redirect(
            url_for(
                "arqueo_caja.terreno",
                sucursal_id=reg["sucursal_id"],
                fecha=fecha.isoformat(),
                caja=caja,
            )
        )

    return render_template(
        "arqueo_caja/terreno_editar.html",
        reg=reg,
        canales_opciones=canales_opciones,
    )


def _lunes_semana(d: date) -> date:
    """Lunes ISO de la semana que contiene d."""
    return d - timedelta(days=d.weekday())


def _sort_filas_resumen(filas: List[dict], key: str, desc: bool) -> List[dict]:
    if not key or not filas:
        return filas
    ks = {
        "etiqueta": lambda r: (r.get("etiqueta") or "").lower(),
        "norm": lambda r: (r.get("canal_norm") or "").lower(),
        "sistema": lambda r: r.get("sistema") or Decimal("0"),
        "terreno": lambda r: r.get("terreno") or Decimal("0"),
        "diff": lambda r: r.get("diff") or Decimal("0"),
    }
    if key == "propina":
        lo = Decimal("-999999999999999999")
        hi = Decimal("999999999999999999")

        def pk(r):
            p = r.get("propina")
            if p is None:
                return hi if desc else lo
            return Decimal(str(p))

        return sorted(filas, key=pk, reverse=desc)
    if key not in ks:
        return filas
    return sorted(filas, key=ks[key], reverse=desc)


def _neto_linea_row(r: dict) -> Decimal:
    return Decimal(str(r["debe"])) - Decimal(str(r["haber"]))


def _sort_detalle_auditoria(rows: List[dict], key: str, desc: bool) -> List[dict]:
    if not key or not rows:
        return rows
    ks = {
        "fecha": lambda r: str(r.get("fec_compr") or ""),
        "tipo": lambda r: (r.get("cod_comp") or "").lower(),
        "n_comp": lambda r: str(r.get("n_comp") or ""),
        "desc": lambda r: (r.get("desc_cta") or "").lower(),
        "debe": lambda r: Decimal(str(r.get("debe") or 0)),
        "haber": lambda r: Decimal(str(r.get("haber") or 0)),
        "neto": lambda r: _neto_linea_row(r),
    }
    if key not in ks:
        return rows
    return sorted(rows, key=ks[key], reverse=desc)


def _cuadratura_data(sucursal_id: int, fecha: date, caja: int = 1):
    conn = get_db_connection()
    sistema_rows = []
    detalle_sistema = []
    terreno_map = {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT desc_cta, debe, haber FROM arqueo_caja_lineas
                   WHERE sucursal_id = %s AND fec_compr = %s""",
                (sucursal_id, fecha),
            )
            sistema_rows = cur.fetchall() or []
            cur.execute(
                """SELECT fec_compr, n_comp, cod_comp, desc_cta, debe, haber FROM arqueo_caja_lineas
                   WHERE sucursal_id = %s AND fec_compr = %s ORDER BY n_comp, desc_cta, id""",
                (sucursal_id, fecha),
            )
            detalle_sistema = cur.fetchall() or []
            cur.execute(
                """SELECT canal_norm, canal_raw, monto, notas, propina FROM arqueo_caja_terreno
                   WHERE sucursal_id = %s AND fecha = %s AND caja = %s""",
                (sucursal_id, fecha, caja),
            )
            for r in cur.fetchall() or []:
                terreno_map[r["canal_norm"]] = {
                    "monto": Decimal(str(r["monto"])),
                    "canal_raw": r["canal_raw"],
                    "notas": r.get("notas"),
                    "propina": r.get("propina"),
                }
    finally:
        conn.close()

    sis_buckets = _sumar_sistema_por_canal(sistema_rows)
    canales = sorted(set(sis_buckets.keys()) | set(terreno_map.keys()))
    filas = []
    total_diff = Decimal("0")
    total_propina = Decimal("0")
    notas_vals: List[str] = []
    for cn in canales:
        snet = sis_buckets.get(cn, {}).get("neto", Decimal("0"))
        smuestra = sis_buckets.get(cn, {}).get("muestra", cn)
        tinfo = terreno_map.get(cn)
        tmont = tinfo["monto"] if tinfo else Decimal("0")
        diff = tmont - snet
        total_diff += diff
        if tinfo and tinfo.get("propina") is not None:
            total_propina += Decimal(str(tinfo["propina"]))
        if tinfo and (tinfo.get("notas") or "").strip():
            notas_vals.append((tinfo.get("notas") or "").strip())
        filas.append(
            {
                "canal_norm": cn,
                "etiqueta": etiqueta_canal(cn, smuestra),
                "sistema_muestra": smuestra,
                "sistema": snet,
                "terreno": tmont,
                "terreno_raw": tinfo["canal_raw"] if tinfo else None,
                "propina": tinfo.get("propina") if tinfo else None,
                "diff": diff,
                "descuadrado": diff != 0,
                "sin_terreno": tinfo is None,
                "sin_sistema": cn not in sis_buckets,
            }
        )
    uniq_notas = list(dict.fromkeys(notas_vals))
    if len(uniq_notas) <= 1:
        notas_bundle = uniq_notas[0] if uniq_notas else ""
    else:
        notas_bundle = " · ".join(uniq_notas)
    return {
        "filas": filas,
        "total_diff": total_diff,
        "total_propina_terreno": total_propina,
        "notas_bundle": notas_bundle,
        "detalle_sistema": detalle_sistema,
        "hay_sistema": len(sistema_rows) > 0,
        "hay_terreno": len(terreno_map) > 0,
    }


@arqueo_caja_bp.route("/cuadratura", methods=["GET"])
@login_requerido
@permiso_modulo("arqueo_caja")
def cuadratura():
    sucursales = _listar_sucursales()
    sucursal_id = request.args.get("sucursal_id", type=int)
    fecha = _parse_fecha(request.args.get("fecha") or "")
    caja = request.args.get("caja", type=int) or 1
    vista = (request.args.get("vista") or "dia").strip().lower()
    if vista not in ("dia", "semana"):
        vista = "dia"
    if caja not in (1, 2):
        caja = 1
    data = None
    semana_filas = []
    suma_semana_diff = Decimal("0")
    suma_semana_propina = Decimal("0")
    lunes_iso = ""
    domingo_iso = ""
    if sucursal_id and fecha:
        if vista == "semana":
            lunes = _lunes_semana(fecha)
            domingo = lunes + timedelta(days=6)
            lunes_iso = lunes.isoformat()
            domingo_iso = domingo.isoformat()
            es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            for i in range(7):
                d = lunes + timedelta(days=i)
                for caj in (1, 2):
                    dd = _cuadratura_data(sucursal_id, d, caj)
                    hay = dd["hay_sistema"] or dd["hay_terreno"]
                    td = dd["total_diff"]
                    tp = dd.get("total_propina_terreno", Decimal("0"))
                    conc = td == Decimal("0")
                    if not hay:
                        estado = "Sin datos"
                        row_cls = "table-secondary"
                    elif conc:
                        estado = "Conciliado"
                        row_cls = ""
                    else:
                        estado = "Descuadrado"
                        row_cls = "table-danger"
                    if hay:
                        suma_semana_diff += td
                        suma_semana_propina += tp
                    semana_filas.append(
                        {
                            "dia": es[i],
                            "fecha_iso": d.isoformat(),
                            "caja": caj,
                            "estado": estado,
                            "row_cls": row_cls,
                            "hay_datos": hay,
                            "total_diff": td,
                            "total_propina": tp,
                            "notas": dd.get("notas_bundle") or "",
                        }
                    )
        else:
            data = _cuadratura_data(sucursal_id, fecha, caja)
    return render_template(
        "arqueo_caja/cuadratura.html",
        sucursales=sucursales,
        sucursal_id=sucursal_id,
        fecha=fecha.isoformat() if fecha else "",
        caja=caja,
        vista=vista,
        data=data,
        semana_filas=semana_filas,
        suma_semana_diff=suma_semana_diff,
        suma_semana_propina=suma_semana_propina,
        lunes_iso=lunes_iso,
        domingo_iso=domingo_iso,
    )


@arqueo_caja_bp.route("/cuadratura/auditoria", methods=["GET"])
@login_requerido
@permiso_modulo("arqueo_caja")
def auditoria():
    sucursal_id = request.args.get("sucursal_id", type=int)
    fecha = _parse_fecha(request.args.get("fecha") or "")
    caja = request.args.get("caja", type=int) or 1
    if caja not in (1, 2):
        caja = 1
    if not sucursal_id or not fecha:
        flash("Indicá sucursal y fecha.", "warning")
        return redirect(url_for("arqueo_caja.cuadratura"))
    data = _cuadratura_data(sucursal_id, fecha, caja)
    ord_res = request.args.get("ord_res", "").strip()
    dir_res_desc = request.args.get("dir_res", "asc").strip().lower() == "desc"
    ord_det = request.args.get("ord_det", "").strip()
    dir_det_desc = request.args.get("dir_det", "asc").strip().lower() == "desc"
    data = {
        **data,
        "filas": _sort_filas_resumen(list(data["filas"]), ord_res, dir_res_desc),
        "detalle_sistema": _sort_detalle_auditoria(
            list(data["detalle_sistema"]), ord_det, dir_det_desc
        ),
    }
    nombre_suc = ""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nombre_sucursal FROM Sucursales WHERE sucursal_id = %s",
                (sucursal_id,),
            )
            row = cur.fetchone()
            if row:
                nombre_suc = row["nombre_sucursal"]
    finally:
        conn.close()
    return render_template(
        "arqueo_caja/auditoria.html",
        sucursal_id=sucursal_id,
        nombre_suc=nombre_suc,
        fecha=fecha.isoformat(),
        caja=caja,
        data=data,
        ord_res=ord_res,
        dir_res="desc" if dir_res_desc else "asc",
        ord_det=ord_det,
        dir_det="desc" if dir_det_desc else "asc",
    )


@arqueo_caja_bp.route("/cuadratura/export.xlsx", methods=["GET"])
@login_requerido
@permiso_modulo("arqueo_caja")
def export_auditoria_xlsx():
    sucursal_id = request.args.get("sucursal_id", type=int)
    fecha = _parse_fecha(request.args.get("fecha") or "")
    caja = request.args.get("caja", type=int) or 1
    if caja not in (1, 2):
        caja = 1
    if not sucursal_id or not fecha:
        flash("Indicá sucursal y fecha.", "warning")
        return redirect(url_for("arqueo_caja.cuadratura"))
    data = _cuadratura_data(sucursal_id, fecha, caja)
    nombre_suc = str(sucursal_id)
    terreno_rows = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nombre_sucursal FROM Sucursales WHERE sucursal_id = %s",
                (sucursal_id,),
            )
            row = cur.fetchone()
            if row:
                nombre_suc = row["nombre_sucursal"]
            cur.execute(
                """SELECT caja, canal_raw, canal_norm, monto, propina, notas, usuario
                   FROM arqueo_caja_terreno
                   WHERE sucursal_id = %s AND fecha = %s AND caja = %s""",
                (sucursal_id, fecha, caja),
            )
            terreno_rows = cur.fetchall() or []
    finally:
        conn.close()

    resumen = []
    for f in data["filas"]:
        resumen.append(
            {
                "Caja": caja,
                "Nombre_pantalla": f["etiqueta"],
                "Canal_norm": f["canal_norm"],
                "Etiqueta_sistema": f["sistema_muestra"],
                "Sistema_neto": _entero_dinero(f["sistema"]),
                "Terreno": _entero_dinero(f["terreno"]),
                "Propina_info": _entero_dinero(f["propina"])
                if f.get("propina") is not None
                else "",
                "Diferencia": _entero_dinero(f["diff"]),
            }
        )
    df_r = pd.DataFrame(resumen)
    det = []
    for r in data["detalle_sistema"]:
        det.append(
            {
                "FEC_COMPR": r["fec_compr"],
                "N_COMP": r["n_comp"],
                "COD_COMP": r.get("cod_comp") or "",
                "DESC_CTA": r["desc_cta"],
                "DEBE": _entero_dinero(r["debe"]),
                "HABER": _entero_dinero(r["haber"]),
                "Neto": _entero_dinero(Decimal(str(r["debe"])) - Decimal(str(r["haber"]))),
            }
        )
    df_d = pd.DataFrame(det)
    tlist = [
        {
            "Caja": r["caja"],
            "Canal_raw": r["canal_raw"],
            "Canal_norm": r["canal_norm"],
            "Monto": _entero_dinero(r["monto"]),
            "Propina": _entero_dinero(r["propina"]) if r.get("propina") is not None else "",
            "Notas": r.get("notas") or "",
            "Usuario": r.get("usuario") or "",
        }
        for r in terreno_rows
    ]
    df_t = pd.DataFrame(tlist) if tlist else pd.DataFrame({"Mensaje": ["Sin captura terreno"]})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_r.to_excel(w, sheet_name="Resumen_cuadratura", index=False)
        if not df_d.empty:
            df_d.to_excel(w, sheet_name="Detalle_sistema", index=False)
        else:
            pd.DataFrame({"Mensaje": ["Sin líneas sistema para esta fecha"]}).to_excel(
                w, sheet_name="Detalle_sistema", index=False
            )
        df_t.to_excel(w, sheet_name="Terreno_captura", index=False)
    buf.seek(0)
    safe = secure_filename(f"auditoria_arqueo_{nombre_suc}_caja{caja}_{fecha}.xlsx")
    return Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={safe}"},
    )
