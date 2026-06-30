"""Lógica Fábrica Papaya: stocks, rendimiento e informes."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from utils.db import get_db_connection
from utils.fabrica_papaya_semana import (
    dias_semana_iso,
    iso_anio_semana,
    iterar_dias,
    lunes_de_semana_iso,
    NOMBRES_DIA,
    rango_semana_iso,
)

COD_MP = "mp_huerto"
COD_DIRECTA = "papaya_directa"
COD_CONGELADA = "papaya_congelada"
COD_CONGELADA_PARTIDA = "congelada_partida_kg"

CODIGOS_NECTAR = (
    "nectar_300cc",
    "nectar_300cc_light",
    "nectar_1lt",
    "nectar_1lt_light",
)

PRODUCTOS_TERMINADOS_SEED = [
    ("nectar_300cc", "Néctar 300cc", "und", 100),
    ("nectar_300cc_light", "Néctar 300cc light", "und", 110),
    ("nectar_1lt", "Néctar 1 lt", "und", 120),
    ("nectar_1lt_light", "Néctar 1 lt light", "und", 130),
    ("jugo_1kg", "Papaya Jugo 1 Kg", "und", 140),
    ("jugo_460g", "Papaya Jugo 460 grs", "und", 150),
    ("jugo_cubitos_150g", "Papaya Jugo Cubitos 150gr", "und", 160),
    ("jugo_cubitos_460g", "Papaya Jugo Cubitos 460gr", "und", 170),
    ("mermelada_825g", "Mermelada 825gr", "und", 180),
    ("mermelada_440g", "Mermelada 440gr", "und", 190),
    ("congelada_partida_kg", "Papaya Congelada Partida (Kg)", "kg", 200),
    ("congelada_cubos_kg", "Papaya Congelada Cubos (Kg)", "kg", 210),
    ("jarabe_500cc", "Jarabe Papaya 500 cc", "und", 230),
    ("papayas_confitadas", "Papayas Confitadas", "und", 240),
    ("trozos_confitados", "Trozos Confitados", "und", 250),
]


def _dec(val) -> Decimal:
    if val is None or val == "":
        return Decimal("0")
    try:
        return Decimal(str(val).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def calcular_rendimiento_pct(kg_elaborados, kg_directa, kg_congelada) -> Optional[float]:
    elab = float(_dec(kg_elaborados))
    if elab <= 0:
        return None
    util = float(_dec(kg_directa) + _dec(kg_congelada))
    if util <= 0:
        return None
    return round(util / elab * 100, 1)


def promedio_rendimiento_pelador(rends: List[Optional[float]]) -> Optional[float]:
    """Promedio de rendimiento pelador; excluye días sin elaboración o sin kg útiles."""
    valid = [r for r in rends if r is not None and r > 0]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 1)


def _fecha_row(val) -> date:
    if hasattr(val, "date"):
        return val.date()
    return val


def _agrupar_transform_por_fecha(transf_list: list) -> Dict[date, list]:
    out: Dict[date, list] = {}
    for t in transf_list:
        out.setdefault(_fecha_row(t["fecha"]), []).append(t)
    return out


def _pelador_kg_desde_transform(
    transf_dia: list, id_partida: Optional[int]
) -> Tuple[Decimal, Decimal]:
    """Kg directa en destinos (bloques) + partida congelada producida (fila 30 Excel)."""
    kg_directa = Decimal("0")
    kg_partida = Decimal("0")
    for t in transf_dia:
        if t.get("fuente") == "directa":
            kg_directa += _dec(t.get("kg_fuente"))
        if id_partida and t.get("concepto_id") == id_partida:
            kg_partida += _dec(t.get("cantidad_producida"))
    return kg_directa, kg_partida


def metricas_pelador_dia(
    elab: Optional[dict],
    mp: Optional[dict],
    transf_dia: list,
    id_partida: Optional[int],
) -> dict:
    """
    Rendimiento pelador (Excel fila 40):
    (directa bloques + confites + partida congelada) / kg elaborados.
    Si hay transformación del día, deriva kg desde ahí; si no, usa captura manual.
    """
    kg_elab = Decimal("0")
    if elab and _dec(elab.get("kg_elaborados")) > 0:
        kg_elab = _dec(elab["kg_elaborados"])
    elif mp and _dec(mp.get("kg_a_elaboracion")) > 0:
        kg_elab = _dec(mp["kg_a_elaboracion"])

    kg_dir_t, kg_partida = _pelador_kg_desde_transform(transf_dia, id_partida)
    if kg_dir_t > 0 or kg_partida > 0:
        kg_directa, kg_congelada = kg_dir_t, kg_partida
    elif elab:
        kg_directa = _dec(elab.get("kg_directa"))
        kg_congelada = _dec(elab.get("kg_congelada"))
    else:
        kg_directa, kg_congelada = Decimal("0"), Decimal("0")

    kg_utiles = kg_directa + kg_congelada
    rend = calcular_rendimiento_pct(kg_elab, kg_directa, kg_congelada)

    return {
        "kg_elaborados": kg_elab,
        "kg_directa": kg_directa,
        "kg_congelada": kg_congelada,
        "kg_utiles": kg_utiles,
        "rendimiento_pct": rend,
    }


MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _depurar_confites_directa(cur) -> None:
    """Papaya Directa Confites no es producto; desactivar y limpiar datos asociados."""
    cur.execute("SELECT id FROM papaya_conceptos WHERE codigo = 'confites_directa'")
    row = cur.fetchone()
    if not row:
        return
    cid = row["id"]
    for tabla in (
        "papaya_dia_transformacion",
        "papaya_dia_despacho",
        "papaya_cierre_stock",
        "papaya_semana_stock_real",
    ):
        cur.execute(f"DELETE FROM {tabla} WHERE concepto_id = %s", (cid,))
    cur.execute("UPDATE papaya_conceptos SET activo = 0 WHERE id = %s", (cid,))


def ensure_catalogo_base(conn=None) -> None:
    own = conn is None
    if own:
        conn = get_db_connection()
    cur = conn.cursor()
    for codigo, nombre, unidad, orden in PRODUCTOS_TERMINADOS_SEED:
        cur.execute(
            """
            INSERT INTO papaya_conceptos (codigo, nombre, tipo, unidad, orden)
            VALUES (%s, %s, 'terminado', %s, %s)
            ON DUPLICATE KEY UPDATE nombre = VALUES(nombre), unidad = VALUES(unidad), orden = VALUES(orden)
            """,
            (codigo, nombre, unidad, orden),
        )
    _depurar_confites_directa(cur)
    if own:
        conn.commit()
        conn.close()


def _mapa_conceptos_por_codigo(cur) -> Dict[str, dict]:
    cur.execute("SELECT * FROM papaya_conceptos WHERE activo = 1 ORDER BY orden, nombre")
    rows = cur.fetchall() or []
    return {r["codigo"]: r for r in rows}


def _mapa_conceptos_por_id(cur) -> Dict[int, dict]:
    cur.execute("SELECT * FROM papaya_conceptos WHERE activo = 1 ORDER BY orden, nombre")
    rows = cur.fetchall() or []
    return {r["id"]: r for r in rows}


def _fecha_inicio_simulacion(cur) -> date:
    cur.execute("SELECT MIN(fecha) AS m FROM papaya_cierre_stock")
    c = cur.fetchone()
    cur.execute("SELECT MIN(fecha) AS m FROM papaya_dia_mp")
    mp = cur.fetchone()
    cur.execute("SELECT MIN(fecha) AS m FROM papaya_dia_elaboracion")
    el = cur.fetchone()
    fechas = []
    for row in (c, mp, el):
        if row and row.get("m"):
            fechas.append(row["m"])
    if not fechas:
        return date.today()
    return min(fechas)


def _cierres_hasta(cur, fecha: date) -> Dict[int, Decimal]:
    """Último snapshot por concepto con fecha <= `fecha` (para arranque de simulación)."""
    cur.execute(
        """
        SELECT c.concepto_id, c.cantidad
        FROM papaya_cierre_stock c
        INNER JOIN (
            SELECT concepto_id, MAX(fecha) AS mf
            FROM papaya_cierre_stock
            WHERE fecha <= %s
            GROUP BY concepto_id
        ) t ON t.concepto_id = c.concepto_id AND t.mf = c.fecha
        """,
        (fecha,),
    )
    return {r["concepto_id"]: _dec(r["cantidad"]) for r in cur.fetchall() or []}


def _snapshots_en_rango(cur, desde: date, hasta: date) -> Dict[date, Dict[int, Decimal]]:
    """Snapshots concretos por fecha (inicial o ajuste) dentro del rango."""
    cur.execute(
        """
        SELECT fecha, concepto_id, cantidad
        FROM papaya_cierre_stock
        WHERE fecha BETWEEN %s AND %s
        ORDER BY fecha, concepto_id
        """,
        (desde, hasta),
    )
    out: Dict[date, Dict[int, Decimal]] = {}
    for r in cur.fetchall() or []:
        f = r["fecha"]
        if hasattr(f, "date"):
            f = f.date()
        out.setdefault(f, {})[r["concepto_id"]] = _dec(r["cantidad"])
    return out


def _aplicar_snapshot(stocks: Dict[int, Decimal], snapshot: Dict[int, Decimal]) -> None:
    """Reemplaza stock calculado por valores concretos del snapshot."""
    for cid, cant in snapshot.items():
        stocks[cid] = cant


def _cargar_movimientos(cur, desde: date, hasta: date) -> Tuple[dict, dict, list, list]:
    cur.execute(
        "SELECT * FROM papaya_dia_mp WHERE fecha BETWEEN %s AND %s ORDER BY fecha",
        (desde, hasta),
    )
    mp = {r["fecha"]: r for r in cur.fetchall() or []}

    cur.execute(
        "SELECT * FROM papaya_dia_elaboracion WHERE fecha BETWEEN %s AND %s ORDER BY fecha",
        (desde, hasta),
    )
    elab = {r["fecha"]: r for r in cur.fetchall() or []}

    cur.execute(
        "SELECT * FROM papaya_dia_transformacion WHERE fecha BETWEEN %s AND %s ORDER BY fecha, id",
        (desde, hasta),
    )
    transf = cur.fetchall() or []

    cur.execute(
        "SELECT * FROM papaya_dia_despacho WHERE fecha BETWEEN %s AND %s ORDER BY fecha, id",
        (desde, hasta),
    )
    desp = cur.fetchall() or []
    return mp, elab, transf, desp


def simular_stocks(
    fecha_hasta: date,
    fecha_desde: Optional[date] = None,
    excluir_snapshot_fecha: Optional[date] = None,
) -> Dict[date, Dict[int, Decimal]]:
    conn = get_db_connection()
    cur = conn.cursor()
    ensure_catalogo_base(conn)
    por_codigo = _mapa_conceptos_por_codigo(cur)

    id_mp = por_codigo[COD_MP]["id"]
    id_dir = por_codigo[COD_DIRECTA]["id"]
    id_cong = por_codigo[COD_CONGELADA]["id"]
    terminados = [r["id"] for r in por_codigo.values() if r["tipo"] == "terminado"]

    if fecha_desde is None:
        ini = _fecha_inicio_simulacion(cur)
    else:
        ini = fecha_desde

    # Stock al cierre del día anterior al inicio de simulación
    prev = ini - timedelta(days=1)
    stocks: Dict[int, Decimal] = _cierres_hasta(cur, prev)
    for cid in [id_mp, id_dir, id_cong] + terminados:
        stocks.setdefault(cid, Decimal("0"))

    mp_map, elab_map, transf_list, desp_list = _cargar_movimientos(cur, ini, fecha_hasta)
    snapshots_dia = _snapshots_en_rango(cur, ini, fecha_hasta)
    transf_por_fecha: Dict[date, list] = {}
    for t in transf_list:
        transf_por_fecha.setdefault(t["fecha"], []).append(t)
    desp_por_fecha: Dict[date, list] = {}
    for d in desp_list:
        desp_por_fecha.setdefault(d["fecha"], []).append(d)

    snapshots: Dict[date, Dict[int, Decimal]] = {}
    for d in iterar_dias(ini, fecha_hasta):
        row_mp = mp_map.get(d)
        if row_mp:
            stocks[id_mp] = (
                stocks.get(id_mp, Decimal("0"))
                + _dec(row_mp["entrada_huerto_kg"])
                + _dec(row_mp["entrada_externa_kg"])
                - _dec(row_mp["kg_a_elaboracion"])
                - _dec(row_mp["kg_descarte"])
                - _dec(row_mp["kg_venta_calibre"])
            )

        row_e = elab_map.get(d)
        # Elaboración manual (AppSheet) puede registrar salida a intermedios; no usar
        # kg derivados del import pelador (son destinos de transformación, no stock).
        if row_e and _dec(row_e["kg_directa"]) + _dec(row_e["kg_congelada"]) > 0:
            capturado = (row_e.get("capturado_por") or "")
            if not str(capturado).startswith("import:"):
                stocks[id_dir] = stocks.get(id_dir, Decimal("0")) + _dec(row_e["kg_directa"])
                stocks[id_cong] = stocks.get(id_cong, Decimal("0")) + _dec(row_e["kg_congelada"])

        for t in transf_por_fecha.get(d, []):
            # kg_fuente alimenta KPI pelador/transformación; propuesta de stock de
            # terminados usa cantidad_producida (no descuenta intermedios).
            cid = t["concepto_id"]
            stocks[cid] = stocks.get(cid, Decimal("0")) + _dec(t["cantidad_producida"])

        for row_d in desp_por_fecha.get(d, []):
            cid = row_d["concepto_id"]
            stocks[cid] = stocks.get(cid, Decimal("0")) - _dec(row_d["cantidad"])

        if d in snapshots_dia and d != excluir_snapshot_fecha:
            _aplicar_snapshot(stocks, snapshots_dia[d])

        snapshots[d] = dict(stocks)

    conn.close()
    return snapshots


def stock_al_cierre(fecha: date, excluir_snapshot_fecha: Optional[date] = None) -> Dict[int, Decimal]:
    snaps = simular_stocks(fecha, excluir_snapshot_fecha=excluir_snapshot_fecha)
    return snaps.get(fecha, {})


def listar_conceptos_stockeables(cur) -> List[dict]:
    cur.execute(
        """
        SELECT * FROM papaya_conceptos
        WHERE activo = 1
          AND tipo IN ('materia_prima', 'intermedio', 'terminado')
        ORDER BY
            FIELD(tipo, 'materia_prima', 'intermedio', 'terminado'),
            orden, nombre
        """
    )
    return cur.fetchall() or []


def stock_real_semana(cur, anio: int, semana: int) -> Dict[int, Decimal]:
    cur.execute(
        """
        SELECT concepto_id, cantidad FROM papaya_semana_stock_real
        WHERE anio = %s AND semana_iso = %s
        """,
        (anio, semana),
    )
    return {r["concepto_id"]: _dec(r["cantidad"]) for r in cur.fetchall() or []}


def informe_semana(anio: int, semana: int) -> dict:
    ensure_catalogo_base()
    lun, dom = rango_semana_iso(anio, semana)
    dias = dias_semana_iso(anio, semana)

    conn = get_db_connection()
    cur = conn.cursor()
    por_id = _mapa_conceptos_por_id(cur)
    por_codigo = _mapa_conceptos_por_codigo(cur)
    conceptos = listar_conceptos_stockeables(cur)

    mp_map, elab_map, transf_list, desp_list = _cargar_movimientos(cur, lun, dom)
    transf_por_fecha = _agrupar_transform_por_fecha(transf_list)
    id_partida = por_codigo.get(COD_CONGELADA_PARTIDA, {}).get("id")

    tot_mp = {
        "entrada_huerto_kg": Decimal("0"),
        "entrada_externa_kg": Decimal("0"),
        "kg_a_elaboracion": Decimal("0"),
        "kg_descarte": Decimal("0"),
        "kg_venta_calibre": Decimal("0"),
    }
    tot_elab = {"kg_elaborados": Decimal("0"), "kg_directa": Decimal("0"), "kg_congelada": Decimal("0")}
    tot_pelador = {"kg_directa": Decimal("0"), "kg_congelada": Decimal("0")}
    rends_pelador: List[Optional[float]] = []
    dias_capturados = set()

    detalle_dias: List[dict] = []
    for i, d in enumerate(dias):
        mp = mp_map.get(d)
        el = elab_map.get(d)
        if mp or el:
            dias_capturados.add(d)
        if mp:
            for k in tot_mp:
                tot_mp[k] += _dec(mp.get(k))
        if el:
            tot_elab["kg_elaborados"] += _dec(el["kg_elaborados"])

        pelador = metricas_pelador_dia(el, mp, transf_por_fecha.get(d, []), id_partida)
        tot_pelador["kg_directa"] += pelador["kg_directa"]
        tot_pelador["kg_congelada"] += pelador["kg_congelada"]
        if pelador["rendimiento_pct"] is not None:
            rends_pelador.append(pelador["rendimiento_pct"])

        detalle_dias.append(
            {
                "fecha": d,
                "nombre_dia": NOMBRES_DIA[i],
                "tiene_datos": bool(mp or el),
                "mp": mp,
                "elaboracion": el,
                "pelador": pelador,
                "rendimiento_pct": pelador["rendimiento_pct"],
            }
        )

    prod_transf: Dict[int, Decimal] = {}
    cons_directa = Decimal("0")
    cons_congelada = Decimal("0")
    for t in transf_list:
        prod_transf[t["concepto_id"]] = prod_transf.get(t["concepto_id"], Decimal("0")) + _dec(
            t["cantidad_producida"]
        )
        if t["fuente"] == "directa":
            cons_directa += _dec(t["kg_fuente"])
        else:
            cons_congelada += _dec(t["kg_fuente"])

    prod_desp: Dict[int, Decimal] = {}
    for row in desp_list:
        prod_desp[row["concepto_id"]] = prod_desp.get(row["concepto_id"], Decimal("0")) + _dec(
            row["cantidad"]
        )

    rend_semana = promedio_rendimiento_pelador(rends_pelador)
    tot_elab["kg_directa"] = tot_pelador["kg_directa"]
    tot_elab["kg_congelada"] = tot_pelador["kg_congelada"]

    stock_teorico = stock_al_cierre(dom)
    stock_real = stock_real_semana(cur, anio, semana)

    filas_stock = []
    for c in conceptos:
        cid = c["id"]
        teo = stock_teorico.get(cid, Decimal("0"))
        real = stock_real.get(cid)
        diff = (real - teo) if real is not None else None
        filas_stock.append(
            {
                "concepto": c,
                "propuesta": teo,
                "real": real,
                "diferencia": diff,
            }
        )

    produccion_terminados = []
    for c in conceptos:
        if c["tipo"] != "terminado":
            continue
        cid = c["id"]
        produccion_terminados.append(
            {
                "concepto": c,
                "producido": prod_transf.get(cid, Decimal("0")),
                "despachado": prod_desp.get(cid, Decimal("0")),
            }
        )

    conn.close()

    return {
        "anio": anio,
        "semana": semana,
        "lun": lun,
        "dom": dom,
        "dias": dias,
        "detalle_dias": detalle_dias,
        "dias_capturados": len(dias_capturados),
        "tot_mp": tot_mp,
        "tot_elab": tot_elab,
        "rendimiento_semana_pct": rend_semana,
        "cons_directa_kg": cons_directa,
        "cons_congelada_kg": cons_congelada,
        "filas_stock": filas_stock,
        "produccion_terminados": produccion_terminados,
        "id_mp": por_codigo.get(COD_MP, {}).get("id"),
    }


def informe_mes(anio: int, mes: int) -> dict:
    import calendar

    ensure_catalogo_base()
    ultimo = calendar.monthrange(anio, mes)[1]
    d_ini = date(anio, mes, 1)
    d_fin = date(anio, mes, ultimo)

    conn = get_db_connection()
    cur = conn.cursor()
    conceptos = listar_conceptos_stockeables(cur)
    por_codigo = _mapa_conceptos_por_codigo(cur)
    ids_nectar = [por_codigo[c]["id"] for c in CODIGOS_NECTAR if c in por_codigo]

    mp_map, elab_map, transf_list, desp_list = _cargar_movimientos(cur, d_ini, d_fin)
    transf_por_fecha = _agrupar_transform_por_fecha(transf_list)
    id_partida = por_codigo.get(COD_CONGELADA_PARTIDA, {}).get("id")

    tot_mp = {
        "entrada_huerto_kg": Decimal("0"),
        "entrada_externa_kg": Decimal("0"),
        "kg_a_elaboracion": Decimal("0"),
        "kg_descarte": Decimal("0"),
        "kg_venta_calibre": Decimal("0"),
    }
    tot_elab = {"kg_elaborados": Decimal("0"), "kg_directa": Decimal("0"), "kg_congelada": Decimal("0")}
    rends_pelador: List[Optional[float]] = []
    dias_con_datos = 0

    for d in iterar_dias(d_ini, d_fin):
        mp = mp_map.get(d)
        el = elab_map.get(d)
        if mp or el:
            dias_con_datos += 1
        if mp:
            for k in tot_mp:
                tot_mp[k] += _dec(mp.get(k))
        if el:
            tot_elab["kg_elaborados"] += _dec(el["kg_elaborados"])

        pelador = metricas_pelador_dia(el, mp, transf_por_fecha.get(d, []), id_partida)
        tot_elab["kg_directa"] += pelador["kg_directa"]
        tot_elab["kg_congelada"] += pelador["kg_congelada"]
        if pelador["rendimiento_pct"] is not None:
            rends_pelador.append(pelador["rendimiento_pct"])

    rend_mes = promedio_rendimiento_pelador(rends_pelador)

    prod_transf: Dict[int, Decimal] = {}
    prod_desp: Dict[int, Decimal] = {}
    for t in transf_list:
        prod_transf[t["concepto_id"]] = prod_transf.get(t["concepto_id"], Decimal("0")) + _dec(
            t["cantidad_producida"]
        )
    for row in desp_list:
        prod_desp[row["concepto_id"]] = prod_desp.get(row["concepto_id"], Decimal("0")) + _dec(
            row["cantidad"]
        )

    produccion_terminados = []
    for c in conceptos:
        if c["tipo"] != "terminado":
            continue
        cid = c["id"]
        produccion_terminados.append(
            {
                "concepto": c,
                "producido": prod_transf.get(cid, Decimal("0")),
                "despachado": prod_desp.get(cid, Decimal("0")),
            }
        )

    # Néctar por fuente — detalle línea a línea
    nectar_lineas = []
    nectar_por_fuente = {
        "directa": {"unidades": Decimal("0"), "kg_fuente": Decimal("0"), "registros": 0},
        "congelada": {"unidades": Decimal("0"), "kg_fuente": Decimal("0"), "registros": 0},
    }
    nectar_sin_fuente = {"unidades": Decimal("0"), "registros": 0}

    if ids_nectar:
        placeholders = ",".join(["%s"] * len(ids_nectar))
        cur.execute(
            f"""
            SELECT t.fecha, t.fuente, t.kg_fuente, t.cantidad_producida, t.observaciones,
                   c.nombre AS producto, c.unidad, c.codigo
            FROM papaya_dia_transformacion t
            JOIN papaya_conceptos c ON c.id = t.concepto_id
            WHERE t.fecha BETWEEN %s AND %s AND t.concepto_id IN ({placeholders})
            ORDER BY t.fecha, c.orden, t.id
            """,
            (d_ini, d_fin, *ids_nectar),
        )
        for r in cur.fetchall() or []:
            cant = _dec(r["cantidad_producida"])
            kg = _dec(r["kg_fuente"])
            fuente = r["fuente"]
            sin_kg = kg == 0
            nectar_lineas.append(
                {
                    "fecha": r["fecha"],
                    "producto": r["producto"],
                    "unidad": r["unidad"],
                    "codigo": r["codigo"],
                    "fuente": fuente,
                    "kg_fuente": kg,
                    "cantidad": cant,
                    "sin_kg_fuente": sin_kg,
                    "observaciones": r.get("observaciones"),
                }
            )
            if sin_kg:
                nectar_sin_fuente["unidades"] += cant
                nectar_sin_fuente["registros"] += 1
            elif fuente in nectar_por_fuente:
                nectar_por_fuente[fuente]["unidades"] += cant
                nectar_por_fuente[fuente]["kg_fuente"] += kg
                nectar_por_fuente[fuente]["registros"] += 1

    stock_fin_mes = stock_al_cierre(d_fin)
    conn.close()

    return {
        "anio": anio,
        "mes": mes,
        "mes_nombre": MESES_ES[mes - 1],
        "d_ini": d_ini,
        "d_fin": d_fin,
        "dias_con_datos": dias_con_datos,
        "tot_mp": tot_mp,
        "tot_elab": tot_elab,
        "rendimiento_mes_pct": rend_mes,
        "produccion_terminados": produccion_terminados,
        "nectar_lineas": nectar_lineas,
        "nectar_por_fuente": nectar_por_fuente,
        "nectar_sin_fuente": nectar_sin_fuente,
        "stock_fin_mes": stock_fin_mes,
        "conceptos": conceptos,
    }


def detalle_dia(fecha: date) -> dict:
    ensure_catalogo_base()
    conn = get_db_connection()
    cur = conn.cursor()
    anio, semana = iso_anio_semana(fecha)

    cur.execute("SELECT * FROM papaya_dia_mp WHERE fecha = %s", (fecha,))
    mp = cur.fetchone()
    cur.execute("SELECT * FROM papaya_dia_elaboracion WHERE fecha = %s", (fecha,))
    elab = cur.fetchone()
    cur.execute(
        """
        SELECT t.*, c.nombre AS concepto_nombre, c.unidad
        FROM papaya_dia_transformacion t
        JOIN papaya_conceptos c ON c.id = t.concepto_id
        WHERE t.fecha = %s ORDER BY t.id
        """,
        (fecha,),
    )
    transf = cur.fetchall() or []
    cur.execute(
        """
        SELECT d.*, c.nombre AS concepto_nombre, c.unidad, c.tipo
        FROM papaya_dia_despacho d
        JOIN papaya_conceptos c ON c.id = d.concepto_id
        WHERE d.fecha = %s ORDER BY d.id
        """,
        (fecha,),
    )
    desp = cur.fetchall() or []

    cur.execute(
        "SELECT * FROM papaya_conceptos WHERE activo = 1 AND tipo = 'terminado' ORDER BY orden, nombre"
    )
    terminados = cur.fetchall() or []
    cur.execute(
        """
        SELECT * FROM papaya_conceptos
        WHERE activo = 1 AND tipo IN ('intermedio', 'terminado', 'materia_prima')
        ORDER BY orden, nombre
        """
    )
    conceptos_despacho = cur.fetchall() or []

    stocks = stock_al_cierre(fecha)
    por_codigo = _mapa_conceptos_por_codigo(cur)
    stock_resumen = {}
    for cod in (COD_MP, COD_DIRECTA, COD_CONGELADA):
        if cod in por_codigo:
            cid = por_codigo[cod]["id"]
            stock_resumen[cod] = {
                "nombre": por_codigo[cod]["nombre"],
                "cantidad": stocks.get(cid, Decimal("0")),
            }

    conn.close()

    pelador = metricas_pelador_dia(
        elab,
        mp,
        transf,
        por_codigo.get(COD_CONGELADA_PARTIDA, {}).get("id"),
    )

    kg_merma = None
    if pelador["kg_elaborados"] > 0 and pelador["kg_utiles"] > 0:
        merma = pelador["kg_elaborados"] - pelador["kg_utiles"]
        kg_merma = float(merma) if merma > 0 else 0.0

    return {
        "fecha": fecha,
        "anio_iso": anio,
        "semana_iso": semana,
        "mp": mp,
        "elaboracion": elab,
        "transformaciones": transf,
        "despachos": desp,
        "terminados": terminados,
        "conceptos_despacho": conceptos_despacho,
        "stock_resumen": stock_resumen,
        "pelador": pelador,
        "rendimiento_pct": pelador["rendimiento_pct"],
        "kg_merma_elaboracion": kg_merma,
    }


def upsert_dia_mp(fecha: date, data: dict, capturado_por: str) -> None:
    anio, semana = iso_anio_semana(fecha)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO papaya_dia_mp (
            fecha, anio, semana_iso,
            entrada_huerto_kg, entrada_externa_kg, kg_a_elaboracion,
            kg_descarte, comentario_descarte, kg_venta_calibre, observaciones, capturado_por
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            anio = VALUES(anio), semana_iso = VALUES(semana_iso),
            entrada_huerto_kg = VALUES(entrada_huerto_kg),
            entrada_externa_kg = VALUES(entrada_externa_kg),
            kg_a_elaboracion = VALUES(kg_a_elaboracion),
            kg_descarte = VALUES(kg_descarte),
            comentario_descarte = VALUES(comentario_descarte),
            kg_venta_calibre = VALUES(kg_venta_calibre),
            observaciones = VALUES(observaciones),
            capturado_por = VALUES(capturado_por)
        """,
        (
            fecha,
            anio,
            semana,
            _dec(data.get("entrada_huerto_kg")),
            _dec(data.get("entrada_externa_kg")),
            _dec(data.get("kg_a_elaboracion")),
            _dec(data.get("kg_descarte")),
            (data.get("comentario_descarte") or "").strip() or None,
            _dec(data.get("kg_venta_calibre")),
            (data.get("observaciones") or "").strip() or None,
            capturado_por,
        ),
    )
    conn.commit()
    conn.close()


def upsert_dia_elaboracion(fecha: date, data: dict, capturado_por: str) -> None:
    anio, semana = iso_anio_semana(fecha)
    kg_e = _dec(data.get("kg_elaborados"))
    kg_d = _dec(data.get("kg_directa"))
    kg_c = _dec(data.get("kg_congelada"))
    rend = calcular_rendimiento_pct(kg_e, kg_d, kg_c)
    rend_db = round(rend / 100, 4) if rend is not None else None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO papaya_dia_elaboracion (
            fecha, anio, semana_iso,
            kg_elaborados, kg_directa, kg_congelada, rendimiento_pct,
            observaciones, capturado_por
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            anio = VALUES(anio), semana_iso = VALUES(semana_iso),
            kg_elaborados = VALUES(kg_elaborados),
            kg_directa = VALUES(kg_directa),
            kg_congelada = VALUES(kg_congelada),
            rendimiento_pct = VALUES(rendimiento_pct),
            observaciones = VALUES(observaciones),
            capturado_por = VALUES(capturado_por)
        """,
        (
            fecha,
            anio,
            semana,
            kg_e,
            kg_d,
            kg_c,
            rend_db,
            (data.get("observaciones") or "").strip() or None,
            capturado_por,
        ),
    )
    conn.commit()
    conn.close()


def guardar_transformacion(fecha: date, data: dict, capturado_por: str, registro_id: Optional[int] = None) -> int:
    anio, semana = iso_anio_semana(fecha)
    conn = get_db_connection()
    cur = conn.cursor()
    vals = (
        fecha,
        anio,
        semana,
        int(data["concepto_id"]),
        data["fuente"],
        _dec(data.get("kg_fuente")),
        _dec(data.get("cantidad_producida")),
        (data.get("observaciones") or "").strip() or None,
        capturado_por,
    )
    if registro_id:
        cur.execute(
            """
            UPDATE papaya_dia_transformacion SET
                anio=%s, semana_iso=%s, concepto_id=%s, fuente=%s,
                kg_fuente=%s, cantidad_producida=%s, observaciones=%s, capturado_por=%s
            WHERE id=%s
            """,
            vals[1:] + (registro_id,),
        )
        rid = registro_id
    else:
        cur.execute(
            """
            INSERT INTO papaya_dia_transformacion (
                fecha, anio, semana_iso, concepto_id, fuente,
                kg_fuente, cantidad_producida, observaciones, capturado_por
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            vals,
        )
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def guardar_despacho(fecha: date, data: dict, capturado_por: str, registro_id: Optional[int] = None) -> int:
    anio, semana = iso_anio_semana(fecha)
    conn = get_db_connection()
    cur = conn.cursor()
    vals = (
        fecha,
        anio,
        semana,
        int(data["concepto_id"]),
        _dec(data.get("cantidad")),
        (data.get("observaciones") or "").strip() or None,
        capturado_por,
    )
    if registro_id:
        cur.execute(
            """
            UPDATE papaya_dia_despacho SET
                anio=%s, semana_iso=%s, concepto_id=%s, cantidad=%s,
                observaciones=%s, capturado_por=%s
            WHERE id=%s
            """,
            vals[1:] + (registro_id,),
        )
        rid = registro_id
    else:
        cur.execute(
            """
            INSERT INTO papaya_dia_despacho (
                fecha, anio, semana_iso, concepto_id, cantidad, observaciones, capturado_por
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            vals,
        )
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def eliminar_transformacion(registro_id: int) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM papaya_dia_transformacion WHERE id = %s", (registro_id,))
    conn.commit()
    conn.close()


def eliminar_despacho(registro_id: int) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM papaya_dia_despacho WHERE id = %s", (registro_id,))
    conn.commit()
    conn.close()


def guardar_stock_real_semana(anio: int, semana: int, filas: Dict[int, Decimal], capturado_por: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    for concepto_id, cantidad in filas.items():
        cur.execute(
            """
            INSERT INTO papaya_semana_stock_real (anio, semana_iso, concepto_id, cantidad, capturado_por)
            VALUES (%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE cantidad=VALUES(cantidad), capturado_por=VALUES(capturado_por)
            """,
            (anio, semana, concepto_id, cantidad, capturado_por),
        )
    conn.commit()
    conn.close()


def listar_snapshots_stock(limite: int = 30) -> List[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT fecha, tipo, COUNT(*) AS n, MAX(notas) AS notas, MAX(capturado_por) AS capturado_por
        FROM papaya_cierre_stock
        GROUP BY fecha, tipo
        ORDER BY fecha DESC, FIELD(tipo, 'inicial', 'ajuste')
        LIMIT %s
        """,
        (limite,),
    )
    rows = cur.fetchall() or []
    conn.close()
    return rows


def obtener_snapshot_fecha(fecha: date) -> Tuple[str | None, dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT concepto_id, cantidad, notas, tipo
        FROM papaya_cierre_stock WHERE fecha = %s
        """,
        (fecha,),
    )
    rows = cur.fetchall() or []
    conn.close()
    if not rows:
        return None, {}
    tipo = rows[0].get("tipo") or "inicial"
    actuales = {r["concepto_id"]: r for r in rows}
    return tipo, actuales


def guardar_snapshot_stock(
    fecha: date,
    tipo: str,
    filas: Dict[int, Decimal],
    notas: str | None,
    capturado_por: str,
) -> int:
    if tipo not in ("inicial", "ajuste"):
        raise ValueError("tipo inválido")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM papaya_cierre_stock WHERE fecha = %s", (fecha,))
    n = 0
    for concepto_id, cantidad in filas.items():
        cur.execute(
            """
            INSERT INTO papaya_cierre_stock (
                fecha, tipo, concepto_id, cantidad, es_manual, notas, capturado_por
            ) VALUES (%s, %s, %s, %s, 1, %s, %s)
            """,
            (fecha, tipo, concepto_id, cantidad, notas, capturado_por),
        )
        n += 1
    conn.commit()
    conn.close()
    return n


def eliminar_snapshot_fecha(fecha: date) -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM papaya_cierre_stock WHERE fecha = %s", (fecha,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n
