#!/usr/bin/env python3
"""Exporta tablas papaya_* a docs/DATA_FABRICA_PAPAYA_IMPORT.sql"""

from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.db import get_db_connection

OUT = ROOT / "docs" / "DATA_FABRICA_PAPAYA_IMPORT.sql"

TABLES = [
    (
        "papaya_conceptos",
        ["id", "codigo", "nombre", "tipo", "unidad", "producto_erp", "activo", "orden"],
    ),
    (
        "papaya_cierre_stock",
        ["id", "fecha", "tipo", "concepto_id", "cantidad", "es_manual", "notas", "capturado_por"],
    ),
    (
        "papaya_dia_mp",
        [
            "id", "fecha", "anio", "semana_iso", "entrada_huerto_kg", "entrada_externa_kg",
            "kg_a_elaboracion", "kg_descarte", "comentario_descarte", "kg_venta_calibre",
            "observaciones", "capturado_por",
        ],
    ),
    (
        "papaya_dia_elaboracion",
        [
            "id", "fecha", "anio", "semana_iso", "kg_elaborados", "kg_directa", "kg_congelada",
            "rendimiento_pct", "observaciones", "capturado_por",
        ],
    ),
    (
        "papaya_dia_transformacion",
        [
            "id", "fecha", "anio", "semana_iso", "concepto_id", "fuente", "kg_fuente",
            "cantidad_producida", "observaciones", "capturado_por",
        ],
    ),
    (
        "papaya_dia_despacho",
        ["id", "fecha", "anio", "semana_iso", "guia_id", "concepto_id", "cantidad", "numero_doc", "destino", "observaciones", "capturado_por"],
    ),
    (
        "papaya_despacho_guia",
        ["id", "fecha", "anio", "semana_iso", "numero_doc", "destino", "observaciones", "capturado_por"],
    ),
    (
        "papaya_semana_stock_real",
        ["id", "anio", "semana_iso", "concepto_id", "cantidad", "observaciones", "capturado_por"],
    ),
]


def sql_val(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    if isinstance(v, (date, datetime)):
        return f"'{v.date() if isinstance(v, datetime) else v.isoformat()}'"
    s = str(v).replace("\\", "\\\\").replace("'", "''")
    return f"'{s}'"


def main() -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    lines = [
        "-- =============================================================================",
        "-- Fábrica Papaya — datos históricos (import Excel 2026)",
        "-- Ejecutar DESPUÉS de docs/QUERY_FABRICA_PAPAYA_PRODUCCION.sql",
        f"-- Generado: {date.today().isoformat()}",
        "-- =============================================================================",
        "",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "",
        "-- Vaciar tablas (DELETE: compatible phpMyAdmin; TRUNCATE falla con FK #1701).",
        "DELETE FROM papaya_semana_stock_real;",
        "DELETE FROM papaya_dia_despacho;",
        "DELETE FROM papaya_despacho_guia;",
        "DELETE FROM papaya_dia_transformacion;",
        "DELETE FROM papaya_dia_elaboracion;",
        "DELETE FROM papaya_dia_mp;",
        "DELETE FROM papaya_cierre_stock;",
        "DELETE FROM papaya_conceptos;",
        "",
    ]

    for table, cols in TABLES:
        cur.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY id")
        rows = cur.fetchall() or []
        lines.append(f"-- {table} ({len(rows)} filas)")
        if not rows:
            lines.append("")
            continue
        col_list = ", ".join(cols)
        batch: list[str] = []
        for row in rows:
            vals = ", ".join(sql_val(row[c]) for c in cols)
            batch.append(f"({vals})")
        chunk = 50
        for i in range(0, len(batch), chunk):
            part = batch[i : i + chunk]
            lines.append(f"INSERT INTO {table} ({col_list}) VALUES")
            lines.append(",\n".join(part) + ";")
        lines.append("")

    lines.extend(
        [
            "SET FOREIGN_KEY_CHECKS = 1;",
            "",
        ]
    )

    conn.close()
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Escrito {OUT} ({len(lines)} líneas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
