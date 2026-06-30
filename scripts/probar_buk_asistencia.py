#!/usr/bin/env python3
"""
Prueba conexión Buk Asistencia (marcajes del día).

  python3 scripts/probar_buk_asistencia.py
  python3 scripts/probar_buk_asistencia.py --fecha 2026-06-25
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.buk_asistencia_api import listar_asistencia_dia, probar_conexion
from utils.buk_presencia import listar_presencia_dia
from utils.env_config import ENV_FILE, load_env, buk_asistencia_settings


def _parse_fecha(s: str | None) -> date | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser(description="Prueba API Buk Asistencia")
    parser.add_argument("--fecha", help="YYYY-MM-DD (default hoy)")
    args = parser.parse_args()

    load_env()
    cfg = buk_asistencia_settings()
    dia = _parse_fecha(args.fecha) or date.today()

    print("=== Prueba Buk Asistencia ===")
    print(f".env: {ENV_FILE} ({'OK' if ENV_FILE.is_file() else 'NO existe'})")
    print(f"API base: {cfg['base_url']}")
    print(f"Token: {'OK' if cfg['token_configurado'] else 'FALTA — pegar BUK_ASISTENCIA_TOKEN en .env'}")
    print(f"Fecha: {dia.strftime('%d-%m-%Y')}")

    if not cfg["token_configurado"]:
        sys.exit(1)

    ping = probar_conexion()
    if not ping["ok"]:
        print(f"ERROR ping: {ping['error']}")
        sys.exit(2)
    print(f"Ping OK — muestra API: {ping['muestra']} registro(s)")

    asist = listar_asistencia_dia(dia)
    if not asist["ok"]:
        print(f"ERROR asistencia: {asist['error']}")
        sys.exit(3)
    print(f"Marcajes del día: {len(asist['registros'])}")

    for i, r in enumerate(asist["registros"][:8], 1):
        print(
            f"  {i}. {r.get('nombre') or '—'} | {r.get('rut')} | "
            f"{r.get('estado_presencia')} | {r.get('nombre_recinto') or r.get('codigo_recinto')} | "
            f"E:{r.get('entrada_hora') or '—'} S:{r.get('salida_hora') or '—'}"
        )
    if len(asist["registros"]) > 8:
        print(f"  … y {len(asist['registros']) - 8} más")

    pres = listar_presencia_dia(dia)
    print(f"\nReporte cruzado (nómina + marcaje): {pres.get('total')} vigentes | "
          f"{pres.get('trabajando')} trabajando | {pres.get('con_marca')} con marca")
    if pres.get("warnings"):
        for w in pres["warnings"]:
            print(f"  AVISO: {w}")

    print("\nWeb: /buk/asistencia")
    print("=== Fin ===")


if __name__ == "__main__":
    main()
