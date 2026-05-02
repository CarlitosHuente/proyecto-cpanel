#!/usr/bin/env python3
"""
Corrige columna ventas_comercial.sucursal para cargas ya existentes.
Usa el mismo criterio que la carga de Excel (inferir_sucursal_comercial + nombre_archivo en cargas_comercial).

Uso (desde la raíz del proyecto, con .env y venv activo):
  python scripts/fix_sucursal_ventas_comercial.py          # aplica cambios
  python scripts/fix_sucursal_ventas_comercial.py --dry-run # solo muestra qué haría

Luego refresca el cache del dashboard (/refresh en la app o reinicio).
"""
import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

from utils.db import get_db_connection
from utils.ventas_excel_import import inferir_sucursal_comercial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="No escribe en BD, solo lista cambios.")
    args = ap.parse_args()

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT carga_id, nombre_archivo FROM cargas_comercial ORDER BY carga_id"
            )
            cargas = cur.fetchall()
        total_rows = 0
        for row in cargas:
            cid = row["carga_id"]
            nombre = row["nombre_archivo"] or ""
            nuevo = inferir_sucursal_comercial(nombre)
            cur2 = conn.cursor()
            cur2.execute(
                "SELECT COUNT(*) AS n FROM ventas_comercial WHERE carga_id = %s AND sucursal <> %s",
                (cid, nuevo),
            )
            diff = cur2.fetchone()["n"]
            cur2.close()
            if diff == 0:
                continue
            print(f"carga_id={cid} archivo={nombre!r} -> sucursal={nuevo!r} (filas a actualizar: {diff})")
            total_rows += diff
            if not args.dry_run:
                cur3 = conn.cursor()
                cur3.execute(
                    "UPDATE ventas_comercial SET sucursal = %s WHERE carga_id = %s",
                    (nuevo, cid),
                )
                cur3.close()
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
        print(f"Hecho. {'[dry-run]' if args.dry_run else ''} Filas que {'cambiarían' if args.dry_run else 'actualizadas'} en total (suma por carga): {total_rows}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
