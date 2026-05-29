"""Persistencia de órdenes DespachoWeb."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pymysql

from utils.despacho_web_celular import celular_valido, formatear_celular_chile


class OrdenDuplicadaError(Exception):
    def __init__(self, n_orden: str):
        self.n_orden = n_orden
        super().__init__(f"La Orden N° {n_orden} ya existe en el sistema")


def _direccion_completa(calle_o_direccion: str, comuna: str) -> str:
    direccion = (calle_o_direccion or "").strip()
    comuna = (comuna or "").strip()
    if comuna and comuna.lower() not in direccion.lower():
        if direccion:
            return f"{direccion}, {comuna}"
        return comuna
    return direccion


def listar_productos_activos(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT nombre, precio, sku_referencia
        FROM dw_productos
        WHERE activo = 1
        ORDER BY nombre ASC
        """
    )
    return cursor.fetchall() or []


def listar_ordenes_recientes(cursor, limite: int = 20, comuna: str | None = None):
    return listar_ordenes(cursor, comuna=comuna, limite=limite)


ESTADOS_ORDEN = ("Pendiente", "Armado", "En Ruta", "Entregada")
TRANSPORTES = ("", "Cristobal", "Matias")


def listar_ordenes(
    cursor,
    comuna: str | None = None,
    estado: str | None = None,
    buscar: str | None = None,
    limite: int = 100,
    offset: int = 0,
):
    sql = """
        SELECT n_orden, fecha_oc, cliente, estado, comuna, transporte, celular, direccion, creado_at
        FROM dw_orden
        WHERE 1=1
    """
    params: list[Any] = []
    if comuna:
        sql += " AND comuna LIKE %s"
        params.append(f"%{comuna.strip()}%")
    if estado:
        sql += " AND estado = %s"
        params.append(estado.strip())
    if buscar:
        sql += " AND (n_orden LIKE %s OR cliente LIKE %s OR celular LIKE %s)"
        like = f"%{buscar.strip()}%"
        params.extend([like, like, like])
    sql += " ORDER BY creado_at DESC LIMIT %s OFFSET %s"
    params.extend([limite, offset])
    cursor.execute(sql, params)
    return cursor.fetchall() or []


def contar_ordenes(cursor, comuna=None, estado=None, buscar=None) -> int:
    sql = "SELECT COUNT(*) AS c FROM dw_orden WHERE 1=1"
    params: list[Any] = []
    if comuna:
        sql += " AND comuna LIKE %s"
        params.append(f"%{comuna.strip()}%")
    if estado:
        sql += " AND estado = %s"
        params.append(estado.strip())
    if buscar:
        sql += " AND (n_orden LIKE %s OR cliente LIKE %s OR celular LIKE %s)"
        like = f"%{buscar.strip()}%"
        params.extend([like, like, like])
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return int(row["c"] if isinstance(row, dict) else row[0])


def orden_existe(cursor, n_orden: str) -> bool:
    cursor.execute("SELECT 1 FROM dw_orden WHERE n_orden = %s LIMIT 1", (n_orden,))
    return cursor.fetchone() is not None


def obtener_orden(cursor, n_orden: str) -> dict | None:
    cursor.execute("SELECT * FROM dw_orden WHERE n_orden = %s", (n_orden,))
    return cursor.fetchone()


def listar_detalle_orden(cursor, n_orden: str) -> list[dict]:
    cursor.execute(
        """
        SELECT detalle_id, n_orden, producto, cantidad, total, estado
        FROM dw_detalle_oc
        WHERE n_orden = %s
        ORDER BY detalle_id ASC
        """,
        (n_orden,),
    )
    return cursor.fetchall() or []


def _resolver_direccion(datos: dict) -> str:
    explicita = (datos.get("direccion") or "").strip()
    if explicita:
        return explicita
    return _direccion_completa(
        datos.get("calle") or "",
        datos.get("comuna") or "",
    )


def _normalizar_celular_guardar(datos: dict) -> str:
    raw = datos.get("celular") or datos.get("celular_raw") or ""
    celular = formatear_celular_chile(raw)
    if not celular_valido(celular):
        raise ValueError(
            f'Celular inválido ("{raw}"). Use 9 dígitos (ej. 999393805) o +569XXXXXXXX.'
        )
    return celular


def asegurar_productos(cursor, lineas: list[dict]) -> list[str]:
    """
    Alta automática en dw_productos de nombres que vienen del PDF.
    No sobrescribe precio/SKU de productos ya existentes.
    Devuelve la lista de nombres recién creados.
    """
    creados: list[str] = []
    vistos: set[str] = set()
    for ln in lineas or []:
        nombre = (ln.get("producto") or "").strip()
        if not nombre or nombre in vistos:
            continue
        vistos.add(nombre)

        cursor.execute(
            "SELECT nombre, activo FROM dw_productos WHERE nombre = %s LIMIT 1",
            (nombre,),
        )
        row = cursor.fetchone()
        if row:
            if isinstance(row, dict) and not row.get("activo"):
                cursor.execute(
                    "UPDATE dw_productos SET activo = 1 WHERE nombre = %s",
                    (nombre,),
                )
            continue

        precio = None
        total = ln.get("total")
        if total is not None and str(total).strip() != "":
            precio = str(int(total))
        sku = (ln.get("sku") or "").strip() or None
        cursor.execute(
            """
            INSERT INTO dw_productos (nombre, precio, sku_referencia, activo)
            VALUES (%s, %s, %s, 1)
            """,
            (nombre, precio, sku),
        )
        creados.append(nombre)
    return creados


def guardar_orden(
    conn,
    datos: dict,
    lineas: list[dict],
    usuario: str,
    respaldo_ruta: str | None = None,
) -> str:
    """
    Inserta orden + detalle en transacción.
    datos: n_orden, fecha_oc, cliente, direccion, comuna, celular, email, url, obs, transporte
    lineas: [{producto, cantidad, total}, ...]
    """
    n_orden = str(datos.get("n_orden", "")).strip()
    if not n_orden:
        raise ValueError("N° Orden obligatorio")

    celular = _normalizar_celular_guardar(datos)

    direccion = _resolver_direccion(datos)
    if not direccion.strip():
        raise ValueError("Dirección obligatoria (incluya comuna para Maps).")

    if not lineas:
        raise ValueError("Debe incluir al menos una línea de detalle.")

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO dw_orden (
                n_orden, fecha_oc, cliente, estado, transporte, fecha_estado,
                respaldo, direccion, comuna, celular, email, url, obs, creado_por
            ) VALUES (
                %s, %s, %s, 'Pendiente', %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                n_orden,
                datos.get("fecha_oc"),
                (datos.get("cliente") or "").strip(),
                (datos.get("transporte") or "").strip() or None,
                datetime.now(),
                respaldo_ruta,
                direccion,
                (datos.get("comuna") or "").strip() or None,
                celular,
                (datos.get("email") or "").strip() or None,
                (datos.get("url") or "").strip() or None,
                (datos.get("obs") or "").strip() or None,
                usuario,
            ),
        )

        asegurar_productos(cursor, lineas)

        for ln in lineas:
            producto = (ln.get("producto") or "").strip()
            if not producto:
                continue
            cantidad = float(ln.get("cantidad") or 1)
            total = int(ln.get("total") or 0)
            cursor.execute(
                """
                INSERT INTO dw_detalle_oc (n_orden, producto, cantidad, total, estado)
                VALUES (%s, %s, %s, %s, 'Pendiente')
                """,
                (n_orden, producto, cantidad, total),
            )

        conn.commit()
        return n_orden
    except pymysql.err.IntegrityError as e:
        conn.rollback()
        if e.args[0] == 1062:
            raise OrdenDuplicadaError(n_orden) from e
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def actualizar_orden(conn, n_orden: str, datos: dict, lineas: list[dict]) -> None:
    n_orden = str(n_orden).strip()
    if not n_orden:
        raise ValueError("N° Orden obligatorio")

    celular = _normalizar_celular_guardar(datos)
    direccion = _resolver_direccion(datos)
    if not direccion.strip():
        raise ValueError("Dirección obligatoria.")
    if not lineas:
        raise ValueError("Debe incluir al menos una línea de detalle.")

    estado = (datos.get("estado") or "Pendiente").strip()
    if estado not in ESTADOS_ORDEN:
        raise ValueError("Estado no válido.")

    transporte = (datos.get("transporte") or "").strip() or None

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE dw_orden SET
                fecha_oc = %s,
                cliente = %s,
                estado = %s,
                transporte = %s,
                fecha_estado = %s,
                direccion = %s,
                comuna = %s,
                celular = %s,
                email = %s,
                url = %s,
                obs = %s
            WHERE n_orden = %s
            """,
            (
                datos.get("fecha_oc"),
                (datos.get("cliente") or "").strip(),
                estado,
                transporte,
                datetime.now(),
                direccion,
                (datos.get("comuna") or "").strip() or None,
                celular,
                (datos.get("email") or "").strip() or None,
                (datos.get("url") or "").strip() or None,
                (datos.get("obs") or "").strip() or None,
                n_orden,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Orden N° {n_orden} no encontrada.")

        asegurar_productos(cursor, lineas)
        cursor.execute("DELETE FROM dw_detalle_oc WHERE n_orden = %s", (n_orden,))
        for ln in lineas:
            producto = (ln.get("producto") or "").strip()
            if not producto:
                continue
            cantidad = float(ln.get("cantidad") or 1)
            total = int(ln.get("total") or 0)
            estado_ln = (ln.get("estado") or estado).strip()
            cursor.execute(
                """
                INSERT INTO dw_detalle_oc (n_orden, producto, cantidad, total, estado)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (n_orden, producto, cantidad, total, estado_ln),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def eliminar_orden(conn, n_orden: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM dw_orden WHERE n_orden = %s", (n_orden,))
        if cursor.rowcount == 0:
            raise ValueError(f"Orden N° {n_orden} no encontrada.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
