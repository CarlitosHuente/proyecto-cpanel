#!/usr/bin/env python3
"""
Importa datos históricos desde Inf. Sem. Fca. Papaya *.xlsx hacia tablas papaya_*.

Uso:
  python3 scripts/import_fabrica_papaya_excel.py --dry-run
  python3 scripts/import_fabrica_papaya_excel.py
  python3 scripts/import_fabrica_papaya_excel.py --clear   # borra capturas previas
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openpyxl

from utils.db import get_db_connection
from utils.fabrica_papaya_semana import iso_anio_semana, lunes_de_semana_iso
from utils.fabrica_papaya_service import (
    COD_CONGELADA,
    COD_CONGELADA_PARTIDA,
    COD_DIRECTA,
    COD_MP,
    PRODUCTOS_TERMINADOS_SEED,
    _dec,
    ensure_catalogo_base,
    metricas_pelador_dia,
)

DEFAULT_XLSX = ROOT / "docs" / "Inf. Sem. Fca. Papaya 2026.rev1.xlsx"
IMPORT_USER = "import:excel"

# Produccion_2026 — filas Excel → campo / concepto
FILAS_MP = {
    4: "entrada_huerto_kg",
    5: "entrada_externa_kg",
    9: "kg_a_elaboracion",
    10: "kg_descarte",
    11: "kg_venta_calibre",
}
FILA_ELAB_KG = 9

# Bloques Excel: fila kg congelada, fila kg directa, luego filas producto debajo.
# La fila «Papaya directa/congelada» = kg fuente consumidos ese día en ese bloque.
BLOQUES_TRANSFORMACION = [
    (13, 14, {15: "nectar_300cc", 16: "nectar_300cc_light", 17: "nectar_1lt", 18: "nectar_1lt_light"}),
    (19, 20, {21: "jugo_1kg", 22: "jugo_460g", 23: "jugo_cubitos_150g", 24: "jugo_cubitos_460g"}),
    (25, 26, {27: "mermelada_825g", 28: "mermelada_440g"}),
    (31, 32, {30: "congelada_partida_kg", 33: "congelada_cubos_kg"}),
    (None, 34, {36: "papayas_confitadas", 37: "trozos_confitados"}),
]
PRODUCTOS_SUELTOS = {35: "jarabe_500cc"}

# Col B stock inicial (solo productos terminados, no filas de fuente)
STOCK_INICIAL_FILAS = {
    3: COD_MP,
    15: "nectar_300cc",
    16: "nectar_300cc_light",
    17: "nectar_1lt",
    18: "nectar_1lt_light",
    21: "jugo_1kg",
    22: "jugo_460g",
    23: "jugo_cubitos_150g",
    24: "jugo_cubitos_460g",
    27: "mermelada_825g",
    28: "mermelada_440g",
    30: "congelada_partida_kg",
    33: "congelada_cubos_kg",
    35: "jarabe_500cc",
    36: "papayas_confitadas",
    37: "trozos_confitados",
}
FILAS_SEMANAL = {
    3: COD_MP,
    11: "nectar_300cc",
    12: "nectar_300cc_light",
    13: "nectar_1lt",
    14: "nectar_1lt_light",
    17: "jugo_1kg",
    18: "jugo_460g",
    19: "jugo_cubitos_150g",
    20: "jugo_cubitos_460g",
    23: "mermelada_825g",
    24: "mermelada_440g",
    26: "congelada_partida_kg",
    29: "congelada_cubos_kg",
    31: "jarabe_500cc",
    32: "papayas_confitadas",
    33: "trozos_confitados",
    9: COD_CONGELADA,
    10: COD_DIRECTA,
}


def _lineas_transformacion_dia(grilla: dict, col_idx: int, ids: dict[str, int]) -> list[tuple[int, str, Decimal, Decimal]]:
    """Por bloque: kg fuente en fila cong/directa → reparto proporcional entre productos del bloque."""
    lineas: list[tuple[int, str, Decimal, Decimal]] = []
    for row_cong, row_dir, productos in BLOQUES_TRANSFORMACION:
        prods: list[tuple[str, int, Decimal]] = []
        for row_p, codigo in productos.items():
            qty = _num(_celda(grilla, row_p, col_idx))
            if qty is not None and codigo in ids:
                prods.append((codigo, ids[codigo], qty))
        if not prods:
            if row_dir is not None:
                kg_solo = _num(_celda(grilla, row_dir, col_idx))
                if kg_solo is not None and row_dir == 34 and "papayas_confitadas" in ids:
                    lineas.append((ids["papayas_confitadas"], "directa", kg_solo, Decimal("0")))
            continue
        total_qty = sum(q for _, _, q in prods)
        fuentes: list[tuple[str, Decimal]] = []
        for fuente, row_f in (("congelada", row_cong), ("directa", row_dir)):
            if row_f is None:
                continue
            kg = _num(_celda(grilla, row_f, col_idx))
            if kg is not None and kg > 0:
                fuentes.append((fuente, kg))
        if not fuentes:
            for _codigo, cid, qty in prods:
                lineas.append((cid, "directa", Decimal("0"), qty))
            continue
        total_kg_fuentes = sum(kg for _, kg in fuentes)
        for fuente, kg in fuentes:
            for _codigo, cid, qty in prods:
                kg_asign = (kg * qty / total_qty).quantize(Decimal("0.001"))
                qty_asign = (qty * kg / total_kg_fuentes).quantize(Decimal("0.001"))
                lineas.append((cid, fuente, kg_asign, qty_asign))

    for row_p, codigo in PRODUCTOS_SUELTOS.items():
        qty = _num(_celda(grilla, row_p, col_idx))
        if qty is not None and codigo in ids:
            lineas.append((ids[codigo], "directa", Decimal("0"), qty))

    return lineas


def _num(val) -> Decimal | None:
    if val is None or val == "":
        return None
    if isinstance(val, str) and not val.strip():
        return None
    d = _dec(val)
    if d == 0:
        return None
    return d


def _parse_fecha_cell(val) -> date | None:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return None


def _cargar_grilla(ws, max_row: int) -> dict[int, list]:
    grilla = {}
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=max_row, values_only=True), 1):
        grilla[i] = list(row)
    return grilla


def _celda(grilla: dict, row_idx: int, col_idx: int):
    row = grilla.get(row_idx, [])
    if col_idx - 1 < len(row):
        return row[col_idx - 1]
    return None


def _columnas_fecha_produccion(grilla: dict) -> list[tuple[int, date]]:
    row2 = grilla.get(2, [])
    out = []
    for col_idx, val in enumerate(row2, start=1):
        f = _parse_fecha_cell(val)
        if f:
            out.append((col_idx, f))
    return out


def _columnas_semana_grilla(grilla: dict) -> list[tuple[int, int]]:
    r1 = grilla.get(1, [])
    r2 = grilla.get(2, [])
    out = []
    for col_idx in range(3, max(len(r1), len(r2)) + 1):
        n = r1[col_idx - 1] if col_idx - 1 < len(r1) else None
        if n is None:
            label = r2[col_idx - 1] if col_idx - 1 < len(r2) else None
            if label and "Semana" in str(label):
                try:
                    n = int(str(label).replace("Semana", "").strip())
                except ValueError:
                    continue
            else:
                continue
        try:
            sem = int(n)
        except (TypeError, ValueError):
            continue
        if sem > 0:
            out.append((col_idx, sem))
    return out


def _anio_iso_semana_excel(num_semana: int, anio_hoja: int = 2026) -> tuple[int, int]:
    """Semanas del Excel 2026: semana 1 ISO empieza 2025-12-29."""
    lun = lunes_de_semana_iso(anio_hoja, num_semana)
    return iso_anio_semana(lun)


def _id_por_codigo(cur) -> dict[str, int]:
    cur.execute("SELECT id, codigo FROM papaya_conceptos")
    return {r["codigo"]: r["id"] for r in cur.fetchall()}


def limpiar_tablas(cur, dry_run: bool) -> None:
    tablas = [
        "papaya_semana_stock_real",
        "papaya_dia_despacho",
        "papaya_dia_transformacion",
        "papaya_dia_elaboracion",
        "papaya_dia_mp",
        "papaya_cierre_stock",
    ]
    for t in tablas:
        if dry_run:
            cur.execute(f"SELECT COUNT(*) AS n FROM {t}")
            print(f"  [dry-run] {t}: {cur.fetchone()['n']} filas a borrar")
        else:
            cur.execute(f"DELETE FROM {t}")


def importar_produccion(grilla: dict, cur, ids: dict, dry_run: bool, stats: dict) -> date | None:
    cols = _columnas_fecha_produccion(grilla)
    if not cols:
        raise RuntimeError("No se encontraron fechas en Produccion_2026 fila 2")

    primera = cols[0][1]
    for col_idx, fecha in cols:
        mp_data = {}
        tiene_mp = False
        for row_idx, field in FILAS_MP.items():
            val = _num(_celda(grilla, row_idx, col_idx))
            if val is not None:
                mp_data[field] = val
                tiene_mp = True

        kg_elab = _num(_celda(grilla, FILA_ELAB_KG, col_idx))
        tiene_elab = kg_elab is not None and kg_elab > 0

        trans_lines = _lineas_transformacion_dia(grilla, col_idx, ids)

        if not (tiene_mp or tiene_elab or trans_lines):
            continue

        anio, sem = iso_anio_semana(fecha)

        if tiene_mp:
            stats["mp"] += 1
            if not dry_run:
                cur.execute(
                    """
                    INSERT INTO papaya_dia_mp (
                        fecha, anio, semana_iso,
                        entrada_huerto_kg, entrada_externa_kg, kg_a_elaboracion,
                        kg_descarte, kg_venta_calibre, capturado_por
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        anio=VALUES(anio), semana_iso=VALUES(semana_iso),
                        entrada_huerto_kg=VALUES(entrada_huerto_kg),
                        entrada_externa_kg=VALUES(entrada_externa_kg),
                        kg_a_elaboracion=VALUES(kg_a_elaboracion),
                        kg_descarte=VALUES(kg_descarte),
                        kg_venta_calibre=VALUES(kg_venta_calibre),
                        capturado_por=VALUES(capturado_por)
                    """,
                    (
                        fecha,
                        anio,
                        sem,
                        mp_data.get("entrada_huerto_kg", Decimal("0")),
                        mp_data.get("entrada_externa_kg", Decimal("0")),
                        mp_data.get("kg_a_elaboracion", Decimal("0")),
                        mp_data.get("kg_descarte", Decimal("0")),
                        mp_data.get("kg_venta_calibre", Decimal("0")),
                        IMPORT_USER,
                    ),
                )

        if tiene_elab:
            stats["elab"] += 1
            if not dry_run:
                transf_for = [
                    {
                        "fuente": fuente,
                        "kg_fuente": kg,
                        "concepto_id": cid,
                        "cantidad_producida": cant,
                    }
                    for cid, fuente, kg, cant in trans_lines
                ]
                pel = metricas_pelador_dia(
                    {"kg_elaborados": kg_elab},
                    mp_data if tiene_mp else None,
                    transf_for,
                    ids.get(COD_CONGELADA_PARTIDA),
                )
                rend = pel["rendimiento_pct"]
                rend_db = round(rend / 100, 4) if rend is not None else None
                cur.execute(
                    """
                    INSERT INTO papaya_dia_elaboracion (
                        fecha, anio, semana_iso,
                        kg_elaborados, kg_directa, kg_congelada, rendimiento_pct, capturado_por
                    ) VALUES (%s,%s,%s,%s,0,0,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        anio=VALUES(anio), semana_iso=VALUES(semana_iso),
                        kg_elaborados=VALUES(kg_elaborados),
                        kg_directa=0,
                        kg_congelada=0,
                        rendimiento_pct=VALUES(rendimiento_pct),
                        capturado_por=VALUES(capturado_por)
                    """,
                    (
                        fecha,
                        anio,
                        sem,
                        kg_elab,
                        rend_db,
                        IMPORT_USER,
                    ),
                )

        if trans_lines:
            stats["transf"] += len(trans_lines)
            if not dry_run:
                cur.execute("DELETE FROM papaya_dia_transformacion WHERE fecha = %s", (fecha,))
                for cid, fuente, kg_fuente, cant in trans_lines:
                    cur.execute(
                        """
                        INSERT INTO papaya_dia_transformacion (
                            fecha, anio, semana_iso, concepto_id, fuente,
                            kg_fuente, cantidad_producida, observaciones, capturado_por
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (fecha, anio, sem, cid, fuente, kg_fuente, cant, "Import Excel (bloques)", IMPORT_USER),
                    )

    return primera


def importar_cierre_inicial(grilla: dict, cur, ids: dict, primera_fecha: date, dry_run: bool, stats: dict) -> None:
    fecha_cierre = primera_fecha - __import__("datetime").timedelta(days=1)
    count = 0
    for row_idx, codigo in STOCK_INICIAL_FILAS.items():
        if codigo not in ids:
            continue
        val = _num(_celda(grilla, row_idx, 2))
        if val is None:
            continue
        count += 1
        if not dry_run:
            cur.execute(
                """
                INSERT INTO papaya_cierre_stock (fecha, tipo, concepto_id, cantidad, es_manual, notas, capturado_por)
                VALUES (%s, 'inicial', %s, %s, 1, %s, %s)
                ON DUPLICATE KEY UPDATE
                    tipo = 'inicial',
                    cantidad = VALUES(cantidad),
                    es_manual = 1,
                    notas = VALUES(notas),
                    capturado_por = VALUES(capturado_por)
                """,
                (fecha_cierre, ids[codigo], val, "Stock inicial col B — import Excel", IMPORT_USER),
            )
    stats["cierre"] = count
    print(f"  Cierre stock {fecha_cierre.isoformat()}: {count} conceptos")


def importar_hoja_semanal(wb, hoja: str, cur, ids: dict, dry_run: bool, stats: dict, es_despacho: bool) -> None:
    ws = wb[hoja]
    grilla = _cargar_grilla(ws, 35)
    cols = _columnas_semana_grilla(grilla)
    key = "despacho" if es_despacho else "stock_real"

    for col_idx, num_sem in cols:
        anio, sem = _anio_iso_semana_excel(num_sem)
        lun = lunes_de_semana_iso(anio, sem)
        dom = lun + __import__("datetime").timedelta(days=6)

        filas_sem = []
        for row_idx, codigo in FILAS_SEMANAL.items():
            if codigo not in ids:
                continue
            val = _num(_celda(grilla, row_idx, col_idx))
            if val is not None:
                filas_sem.append((ids[codigo], val))

        if not filas_sem:
            continue

        if es_despacho:
            stats[key] += len(filas_sem)
            if not dry_run:
                cur.execute(
                    "DELETE FROM papaya_dia_despacho WHERE fecha = %s AND capturado_por = %s",
                    (dom, IMPORT_USER),
                )
                for cid, cant in filas_sem:
                    cur.execute(
                        """
                        INSERT INTO papaya_dia_despacho (
                            fecha, anio, semana_iso, concepto_id, cantidad, observaciones, capturado_por
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (dom, anio, sem, cid, cant, f"Import {hoja} semana {num_sem}", IMPORT_USER),
                    )
        else:
            stats[key] += len(filas_sem)
            if not dry_run:
                for cid, cant in filas_sem:
                    cur.execute(
                        """
                        INSERT INTO papaya_semana_stock_real (anio, semana_iso, concepto_id, cantidad, capturado_por)
                        VALUES (%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE cantidad=VALUES(cantidad), capturado_por=VALUES(capturado_por)
                        """,
                        (anio, sem, cid, cant, IMPORT_USER),
                    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Importar Excel Fábrica Papaya a MySQL")
    parser.add_argument("--path", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clear", action="store_true", help="Borra datos papaya_* antes de importar")
    args = parser.parse_args()

    if not args.path.exists():
        print(f"No existe: {args.path}")
        return 1

    print(f"Leyendo {args.path} …")
    wb = openpyxl.load_workbook(args.path, read_only=True, data_only=True)

    ensure_catalogo_base()
    conn = get_db_connection()
    cur = conn.cursor()
    ids = _id_por_codigo(cur)

    stats = {"mp": 0, "elab": 0, "transf": 0, "cierre": 0, "despacho": 0, "stock_real": 0}

    if args.clear:
        print("Limpiando tablas papaya_* …")
        limpiar_tablas(cur, args.dry_run)

    print("Importando Produccion_2026 …")
    grilla_prod = _cargar_grilla(wb["Produccion_2026"], 44)
    primera = importar_produccion(grilla_prod, cur, ids, args.dry_run, stats)
    if primera:
        print(f"  Desde {primera.isoformat()} — MP:{stats['mp']} Elab:{stats['elab']} Transf líneas:{stats['transf']}")

    print("Importando cierre stock inicial (col B) …")
    if primera:
        importar_cierre_inicial(grilla_prod, cur, ids, primera, args.dry_run, stats)

    print("Importando Ventas_Des2 (despacho domingo) …")
    importar_hoja_semanal(wb, "Ventas_Des2", cur, ids, args.dry_run, stats, es_despacho=True)
    print(f"  Líneas despacho: {stats['despacho']}")

    print("Importando Stock_Real2 …")
    importar_hoja_semanal(wb, "Stock_Real2", cur, ids, args.dry_run, stats, es_despacho=False)
    print(f"  Celdas stock real: {stats['stock_real']}")

    wb.close()

    if args.dry_run:
        print("\n[dry-run] Sin cambios en BD.")
        conn.rollback()
    else:
        conn.commit()
        print("\nImportación completada.")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
