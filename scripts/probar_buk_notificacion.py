#!/usr/bin/env python3
"""
Prueba subida + notificación de firma Buk (Carlos Carvajal por defecto).

Desde la raíz:
  python3 scripts/probar_buk_notificacion.py
  python3 scripts/probar_buk_notificacion.py --rut 17761384-3
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.buk_documentos import buscar_empleado_vigente_por_rut, subir_pdf_con_firma_empleado, carpeta_encuestas
from utils.buk_encuesta_pdf import generar_pdf_encuesta
from utils.buk_notificacion import _smtp_configurado, url_portal_buk
from utils.env_config import ENV_FILE, load_env, buk_settings


def main():
    parser = argparse.ArgumentParser(description="Prueba subida Buk + notificación firma")
    parser.add_argument("--rut", default="17761384-3", help="RUT colaborador vigente")
    args = parser.parse_args()

    load_env()
    cfg = buk_settings()
    print("=== Prueba Buk — subida + notificación ===")
    print(f".env: {ENV_FILE} ({'OK' if ENV_FILE.is_file() else 'NO existe'})")
    print(f"Tenant: {cfg['tenant']} | API: {cfg['base_url']}")
    print(f"Portal: {url_portal_buk()}")
    print(f"SMTP respaldo: {'configurado' if _smtp_configurado() else 'no (opcional)'}")

    if not cfg["token_configurado"]:
        print("ERROR: Falta BUK_AUTH_TOKEN")
        sys.exit(1)

    busqueda = buscar_empleado_vigente_por_rut(args.rut)
    if not busqueda["ok"]:
        print(f"ERROR: {busqueda['error']}")
        sys.exit(2)

    empleado = busqueda["empleado"]
    print(f"Colaborador: {empleado.get('full_name')} | {empleado.get('rut')} | id={empleado.get('id')}")
    print(f"Email Buk: {empleado.get('email') or '—'}")

    ahora = datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")
    form = {
        "campo_1": f"Prueba notificación Huente ({ahora})",
        "campo_2": "Capacitación POC",
        "campo_3": "Verificar aviso de firma",
        "campo_4": "5",
        "campo_5": "Documento de prueba — puede eliminarse en Buk.",
    }
    pdf = generar_pdf_encuesta(
        titulo="Encuesta de Capacitación — prueba notificación",
        empleado=empleado,
        respuestas=form,
    )
    rut_corto = (empleado.get("rut") or "test").replace(".", "").replace("-", "")[:12]
    nombre = f"Encuesta_Notif_{rut_corto}.pdf"

    print(f"\nSubiendo {nombre} → carpeta {carpeta_encuestas()} …")
    upload = subir_pdf_con_firma_empleado(
        employee_id=int(empleado["id"]),
        pdf_bytes=pdf,
        filename=nombre,
        carpeta=carpeta_encuestas(),
        empleado=empleado,
    )

    if not upload.get("ok"):
        print(f"ERROR subida: {upload.get('error')}")
        sys.exit(3)

    print(f"OK subida — file_id={upload.get('file_id')} | firma={upload.get('requiere_firma_empleado')}")
    print(f"Flujo automático solicitado: {upload.get('flujo_automatico_solicitado')}")

    notif = upload.get("notificacion") or {}
    print("\n--- Notificación ---")
    if notif.get("ok"):
        print(f"ÉXITO canal={notif.get('canal')}")
        det = notif.get("detalle") or {}
        if det.get("destino"):
            print(f"Correo enviado a: {det['destino']}")
        if det.get("endpoint"):
            print(f"Endpoint Buk: {det['endpoint']} (HTTP {det.get('http_status')})")
    else:
        print(f"PENDIENTE / MANUAL: {notif.get('error') or 'sin detalle'}")
        intentos = notif.get("intentos") or []
        if intentos:
            print(f"Endpoints API probados: {len(intentos)} (todos 404 o error)")
        print("\nSiguiente paso:")
        print(f"  1. Revisar bandeja/correo del colaborador ({empleado.get('email')})")
        print(f"  2. Si no llega: en Buk → Documentos del colaborador → campana «Notificar»")
        print(f"  3. O configurar SMTP_* en .env para aviso Huente automático")

    print("\n=== Fin ===")


if __name__ == "__main__":
    main()
