#!/usr/bin/env python3
"""Prueba rápida de conexión Buk. Desde la raíz: python3 scripts/probar_buk.py"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.env_config import ENV_FILE, load_env
from utils.buk_api import listar_trabajadores_vigentes, probar_conexion, configuracion_resumen


def main():
    load_env()
    cfg = configuracion_resumen()
    print("=== Prueba Buk ===")
    print(f"Archivo: {ENV_FILE} ({'existe' if ENV_FILE.is_file() else 'NO existe'})")
    print(f"Tenant:  {cfg['tenant']}")
    print(f"API:     {cfg['base_url']}")
    print(f"Token:   {'OK' if cfg['token_configurado'] else 'FALTA — agregar BUK_AUTH_TOKEN en .env'}")

    if not cfg["token_configurado"]:
        sys.exit(1)

    ping = probar_conexion()
    if not ping["ok"]:
        print(f"ERROR: {ping['error']}")
        sys.exit(2)

    print(f"Conexión OK — muestra: {ping['muestra_recibida']} colaborador(es) en página 1")
    pag = ping.get("pagination") or {}
    if pag.get("total_pages"):
        print(f"Páginas totales (API): {pag['total_pages']}")

    resultado = listar_trabajadores_vigentes(page=1, page_size=25)
    for i, emp in enumerate(resultado.get("empleados") or [], 1):
        print(f"  {i}. {emp.get('full_name')} | {emp.get('rut')} | {emp.get('cargo') or '—'}")

    print("=== Fin ===")


if __name__ == "__main__":
    main()
