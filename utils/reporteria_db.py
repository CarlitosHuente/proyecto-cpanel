"""Persistencia de reportes de Reportería."""
from __future__ import annotations

import json
import os
from typing import Any, List, Optional

from utils.db import get_db_connection

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "uploads", "reporteria")

_esquema_ok = False


def asegurar_esquema() -> None:
    global _esquema_ok
    if _esquema_ok:
        return
    os.makedirs(PDF_DIR, exist_ok=True)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reporteria_reportes (
                    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    nombre VARCHAR(160) NOT NULL,
                    empresa VARCHAR(20) NOT NULL,
                    corte VARCHAR(20) NOT NULL,
                    vista VARCHAR(20) NOT NULL,
                    sucursales_json TEXT NULL,
                    familias_json TEXT NULL,
                    familias_ficha_json TEXT NULL,
                    correos_json TEXT NULL,
                    estado VARCHAR(20) NOT NULL DEFAULT 'borrador',
                    error_msg VARCHAR(500) NULL,
                    ruta_pdf VARCHAR(255) NULL,
                    usuario VARCHAR(120) NULL,
                    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    generado_at TIMESTAMP NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                SELECT COUNT(*) AS n
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'reporteria_reportes'
                  AND COLUMN_NAME = 'familias_ficha_json'
                """
            )
            if not (cur.fetchone() or {}).get("n"):
                cur.execute(
                    "ALTER TABLE reporteria_reportes ADD COLUMN familias_ficha_json TEXT NULL"
                )
            for col, definicion in (
                ("tipo", "VARCHAR(40) NOT NULL DEFAULT 'ventas'"),
                ("periodo_num", "INT NULL"),
                ("periodo_anio", "INT NULL"),
            ):
                cur.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'reporteria_reportes'
                      AND COLUMN_NAME = %s
                    """,
                    (col,),
                )
                if not (cur.fetchone() or {}).get("n"):
                    cur.execute(f"ALTER TABLE reporteria_reportes ADD COLUMN {col} {definicion}")
        conn.commit()
        _esquema_ok = True
    finally:
        conn.close()


def _loads(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x).strip()]


def _row(r: dict) -> dict:
    r = dict(r)
    r["sucursales"] = _loads(r.get("sucursales_json"))
    r["familias"] = _loads(r.get("familias_json"))
    r["familias_ficha"] = _loads(r.get("familias_ficha_json"))
    r["correos"] = _loads(r.get("correos_json"))
    return r


def listar() -> List[dict]:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, empresa, corte, vista, sucursales_json, familias_json,
                       familias_ficha_json, correos_json, estado, error_msg, ruta_pdf, usuario,
                       creado_at, actualizado_at, generado_at, tipo, periodo_num, periodo_anio
                FROM reporteria_reportes
                ORDER BY actualizado_at DESC, id DESC
                """
            )
            return [_row(r) for r in cur.fetchall()]
    finally:
        conn.close()


def obtener(reporte_id: int) -> Optional[dict]:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, empresa, corte, vista, sucursales_json, familias_json,
                       familias_ficha_json, correos_json, estado, error_msg, ruta_pdf, usuario,
                       creado_at, actualizado_at, generado_at, tipo, periodo_num, periodo_anio
                FROM reporteria_reportes
                WHERE id = %s
                """,
                (reporte_id,),
            )
            row = cur.fetchone()
            return _row(row) if row else None
    finally:
        conn.close()


def _firma(empresa, corte, vista, sucursales, familias, familias_ficha, periodo_num, periodo_anio) -> str:
    return json.dumps(
        {
            "empresa": empresa,
            "corte": corte,
            "vista": vista,
            "sucursales": sorted(sucursales),
            "familias": sorted(familias),
            "familias_ficha": sorted(familias_ficha),
            "periodo_num": periodo_num,
            "periodo_anio": periodo_anio,
        },
        ensure_ascii=False,
    )


def guardar(datos: dict, usuario: str) -> int:
    """Inserta o actualiza filtros. Si cambia el corte de datos, invalida el PDF."""
    asegurar_esquema()
    nombre = (datos.get("nombre") or "").strip()[:160]
    empresa = datos.get("empresa")
    corte = datos.get("corte")
    vista = datos.get("vista")
    sucursales = datos.get("sucursales") or []
    familias = datos.get("familias") or []
    familias_ficha = datos.get("familias_ficha") or []
    correos = datos.get("correos") or []
    periodo_num = datos.get("periodo_num")
    periodo_anio = datos.get("periodo_anio")
    reporte_id = datos.get("id")

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if reporte_id:
                cur.execute(
                    """
                    SELECT empresa, corte, vista, sucursales_json, familias_json,
                           familias_ficha_json, ruta_pdf, periodo_num, periodo_anio
                    FROM reporteria_reportes WHERE id = %s
                    """,
                    (reporte_id,),
                )
                prev = cur.fetchone()
                if not prev:
                    reporte_id = None
            if reporte_id:
                firma_prev = _firma(
                    prev["empresa"],
                    prev["corte"],
                    prev["vista"],
                    _loads(prev.get("sucursales_json")),
                    _loads(prev.get("familias_json")),
                    _loads(prev.get("familias_ficha_json")),
                    prev.get("periodo_num"),
                    prev.get("periodo_anio"),
                )
                firma_nueva = _firma(
                    empresa, corte, vista, sucursales, familias, familias_ficha, periodo_num, periodo_anio
                )
                invalida = firma_prev != firma_nueva
                if invalida and prev.get("ruta_pdf"):
                    _borrar_pdf(prev["ruta_pdf"])
                cur.execute(
                    """
                    UPDATE reporteria_reportes
                    SET nombre=%s, empresa=%s, corte=%s, vista=%s,
                        sucursales_json=%s, familias_json=%s, familias_ficha_json=%s,
                        correos_json=%s, periodo_num=%s, periodo_anio=%s,
                        estado=IF(%s, 'borrador', estado),
                        error_msg=IF(%s, NULL, error_msg),
                        ruta_pdf=IF(%s, NULL, ruta_pdf),
                        generado_at=IF(%s, NULL, generado_at)
                    WHERE id=%s
                    """,
                    (
                        nombre,
                        empresa,
                        corte,
                        vista,
                        json.dumps(sucursales, ensure_ascii=False),
                        json.dumps(familias, ensure_ascii=False),
                        json.dumps(familias_ficha, ensure_ascii=False),
                        json.dumps(correos, ensure_ascii=False),
                        periodo_num,
                        periodo_anio,
                        1 if invalida else 0,
                        1 if invalida else 0,
                        1 if invalida else 0,
                        1 if invalida else 0,
                        reporte_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO reporteria_reportes
                        (nombre, empresa, corte, vista, sucursales_json, familias_json,
                         familias_ficha_json, correos_json, estado, usuario, tipo,
                         periodo_num, periodo_anio)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'borrador', %s, 'ventas', %s, %s)
                    """,
                    (
                        nombre,
                        empresa,
                        corte,
                        vista,
                        json.dumps(sucursales, ensure_ascii=False),
                        json.dumps(familias, ensure_ascii=False),
                        json.dumps(familias_ficha, ensure_ascii=False),
                        json.dumps(correos, ensure_ascii=False),
                        usuario,
                        periodo_num,
                        periodo_anio,
                    ),
                )
                reporte_id = cur.lastrowid
        conn.commit()
        return int(reporte_id)
    finally:
        conn.close()


def actualizar_correos(reporte_id: int, correos: List[str]) -> None:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reporteria_reportes SET correos_json=%s WHERE id=%s",
                (json.dumps(correos, ensure_ascii=False), reporte_id),
            )
        conn.commit()
    finally:
        conn.close()


def marcar_listo(reporte_id: int, ruta_rel: str) -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE reporteria_reportes
                SET estado='listo', error_msg=NULL, ruta_pdf=%s, generado_at=CURRENT_TIMESTAMP
                WHERE id=%s
                """,
                (ruta_rel, reporte_id),
            )
        conn.commit()
    finally:
        conn.close()


def marcar_error(reporte_id: int, mensaje: str) -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE reporteria_reportes
                SET estado='error', error_msg=%s
                WHERE id=%s
                """,
                ((mensaje or "Error al generar")[:500], reporte_id),
            )
        conn.commit()
    finally:
        conn.close()


def ruta_absoluta(ruta_rel: Optional[str]) -> Optional[str]:
    if not ruta_rel:
        return None
    abs_path = os.path.abspath(os.path.join(BASE_DIR, ruta_rel))
    raiz = os.path.abspath(PDF_DIR)
    if not abs_path.startswith(raiz + os.sep) and abs_path != raiz:
        return None
    return abs_path


def guardar_pdf(reporte_id: int, pdf_bytes: bytes) -> str:
    asegurar_esquema()
    nombre = f"reporte_{int(reporte_id)}.pdf"
    abs_path = os.path.join(PDF_DIR, nombre)
    with open(abs_path, "wb") as fh:
        fh.write(pdf_bytes)
    return f"uploads/reporteria/{nombre}"


def _borrar_pdf(ruta_rel: Optional[str]) -> None:
    path = ruta_absoluta(ruta_rel) if ruta_rel else None
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def eliminar(reporte_id: int) -> bool:
    row = obtener(reporte_id)
    if not row:
        return False
    _borrar_pdf(row.get("ruta_pdf"))
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM reporteria_reportes WHERE id=%s", (reporte_id,))
        conn.commit()
        return True
    finally:
        conn.close()
    path = ruta_absoluta(ruta_rel)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
