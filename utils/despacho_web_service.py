"""Persistencia de órdenes DespachoWeb."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pymysql

from utils.despacho_web_celular import celular_valido, formatear_celular_chile
from utils.despacho_web_tables import TBL_DETALLE, TBL_ORDEN, TBL_PRODUCTOS


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


def _slug_sku(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "", nombre.upper())[:24] or "PROD"
    return f"DW-{base}"[:50]


def _sku_disponible(cursor, sku: str) -> bool:
    cursor.execute(f"SELECT 1 FROM {TBL_PRODUCTOS} WHERE sku = %s LIMIT 1", (sku,))
    return cursor.fetchone() is None


def _generar_sku_unico(cursor, nombre: str, sku_pdf: Optional[str] = None) -> str:
    candidatos: list[str] = []
    if sku_pdf:
        candidatos.append(str(sku_pdf).strip()[:50])
    slug = _slug_sku(nombre)
    if slug not in candidatos:
        candidatos.append(slug)
    base = candidatos[-1]
    for i in range(2, 20):
        candidatos.append(f"{base[:45]}-{i}"[:50])

    for sku in candidatos:
        if sku and _sku_disponible(cursor, sku):
            return sku
    raise ValueError(f"No se pudo generar SKU único para «{nombre}».")


def listar_productos_activos(cursor) -> list[dict]:
    cursor.execute(
        f"""
        SELECT nombre, sku, producto_id
        FROM {TBL_PRODUCTOS}
        ORDER BY nombre ASC
        """
    )
    return cursor.fetchall() or []


def listar_ordenes_recientes(cursor, limite: int = 20, comuna: Optional[str] = None):
    return listar_ordenes(cursor, comuna=comuna, limite=limite)


ESTADOS_ORDEN = (
    "Pendiente",
    "Retiro Costanera",
    "Armado",
    "En Ruta",
    "Entregada",
    "Anulado",
)
ESTADOS_INDEX_INBOX = ("Pendiente", "Retiro Costanera")
ESTADO_RETIRO_COSTANERA = "Retiro Costanera"
TRANSPORTES = ("", "Cristobal", "Matias")

_ORDENES_SORT = {
    "n_orden": "n_orden",
    "fecha_oc": "fecha_oc",
    "cliente": "cliente",
    "comuna": "comuna",
    "estado": "estado",
    "transporte": "transporte",
    "celular": "celular",
    "creado_at": "creado_at",
}

_RESUMEN_SORT = {
    "producto": "d.producto",
    "cantidad_total": "cantidad_total",
    "monto_total": "monto_total",
    "num_pedidos": "num_pedidos",
}

_DETALLE_SORT = {
    "n_orden": "o.n_orden",
    "fecha_oc": "o.fecha_oc",
    "cliente": "o.cliente",
    "comuna": "o.comuna",
    "estado": "o.estado",
    "estado_linea": "d.estado",
    "cantidad": "d.cantidad",
    "total": "d.total",
    "direccion": "o.direccion",
}


def _dir_sql(sort_dir: Optional[str]) -> str:
    return "ASC" if (sort_dir or "").lower() == "asc" else "DESC"


def _sort_col(sort: Optional[str], allowed: dict[str, str], default: str) -> str:
    if sort and sort in allowed:
        return allowed[sort]
    return default


def sanear_texto_web(val) -> str:
    """Quita surrogates UTF-16 inválidos (MySQL/AppSheet) para no romper HTML UTF-8."""
    if val is None:
        return ""
    if not isinstance(val, str):
        val = str(val)
    return val.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")


def _sanear_fila_orden(row: dict) -> dict:
    out = dict(row)
    for k, v in out.items():
        if isinstance(v, str):
            out[k] = sanear_texto_web(v)
    return out


def normalizar_estado_orden(estado: Optional[str], default: str = "Pendiente") -> str:
    e = (estado or default).strip()
    if e in ESTADOS_ORDEN:
        return e
    return default


def listar_ordenes_index_inbox(
    cursor,
    comuna: Optional[str] = None,
    limite: int = 500,
) -> list[dict]:
    """Pendientes + Retiro Costanera para la bandeja de la página inicial."""
    placeholders = ", ".join(["%s"] * len(ESTADOS_INDEX_INBOX))
    sql = f"""
        SELECT n_orden, fecha_oc, cliente, estado, comuna, transporte, celular, direccion, creado_at
        FROM {TBL_ORDEN}
        WHERE estado IN ({placeholders})
    """
    params: list[Any] = list(ESTADOS_INDEX_INBOX)
    if comuna:
        sql += " AND comuna LIKE %s"
        params.append(f"%{comuna.strip()}%")
    sql += " ORDER BY fecha_oc ASC, creado_at DESC LIMIT %s"
    params.append(limite)
    cursor.execute(sql, params)
    return cursor.fetchall() or []


def contar_ordenes_index_inbox(cursor, comuna: Optional[str] = None) -> int:
    placeholders = ", ".join(["%s"] * len(ESTADOS_INDEX_INBOX))
    sql = f"SELECT COUNT(*) AS c FROM {TBL_ORDEN} WHERE estado IN ({placeholders})"
    params: list[Any] = list(ESTADOS_INDEX_INBOX)
    if comuna:
        sql += " AND comuna LIKE %s"
        params.append(f"%{comuna.strip()}%")
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return int(row["c"] if isinstance(row, dict) else row[0])


def listar_ordenes(
    cursor,
    comuna: Optional[str] = None,
    estado: Optional[str] = None,
    buscar: Optional[str] = None,
    limite: int = 100,
    offset: int = 0,
    orden_por: Optional[str] = None,
    orden_dir: Optional[str] = None,
):
    sql = f"""
        SELECT n_orden, fecha_oc, cliente, estado, comuna, transporte, celular, direccion, creado_at
        FROM {TBL_ORDEN}
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
    col = _sort_col(orden_por, _ORDENES_SORT, "creado_at")
    sql += f" ORDER BY {col} {_dir_sql(orden_dir)} LIMIT %s OFFSET %s"
    params.extend([limite, offset])
    cursor.execute(sql, params)
    return cursor.fetchall() or []


def listar_ordenes_para_ruta(
    cursor,
    comuna: Optional[str] = None,
    estados: Optional[tuple[str, ...]] = None,
    transporte: Optional[str] = None,
    buscar: Optional[str] = None,
    limite: int = 150,
):
    """Órdenes elegibles para armar ruta (excluye Anulado, Entregada, Retiro Costanera por defecto)."""
    estados = estados or ("Pendiente", "Armado", "En Ruta")
    placeholders = ",".join(["%s"] * len(estados))
    sql = f"""
        SELECT n_orden, fecha_oc, cliente, estado, comuna, transporte, celular, direccion, creado_at
        FROM {TBL_ORDEN}
        WHERE estado IN ({placeholders})
          AND COALESCE(TRIM(direccion), '') != ''
    """
    params: list[Any] = list(estados)
    if comuna:
        sql += " AND comuna LIKE %s"
        params.append(f"%{comuna.strip()}%")
    if transporte:
        sql += " AND transporte = %s"
        params.append(transporte.strip())
    if buscar:
        sql += " AND (n_orden LIKE %s OR cliente LIKE %s OR celular LIKE %s)"
        like = f"%{buscar.strip()}%"
        params.extend([like, like, like])
    sql += " ORDER BY comuna ASC, creado_at ASC LIMIT %s"
    params.append(limite)
    cursor.execute(sql, params)
    return [_sanear_fila_orden(r) for r in (cursor.fetchall() or [])]


def contar_ordenes(cursor, comuna=None, estado=None, buscar=None) -> int:
    sql = f"SELECT COUNT(*) AS c FROM {TBL_ORDEN} WHERE 1=1"
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
    cursor.execute(f"SELECT 1 FROM {TBL_ORDEN} WHERE n_orden = %s LIMIT 1", (n_orden,))
    return cursor.fetchone() is not None


def obtener_orden(cursor, n_orden: str) -> Optional[Dict]:
    cursor.execute(f"SELECT * FROM {TBL_ORDEN} WHERE n_orden = %s", (n_orden,))
    return cursor.fetchone()


def listar_detalle_orden(cursor, n_orden: str) -> list[dict]:
    cursor.execute(
        f"""
        SELECT detalle_id, n_orden, producto, cantidad, total, estado
        FROM {TBL_DETALLE}
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
    Alta automática en Productos (por nombre) para líneas del PDF.
    Devuelve nombres recién creados.
    """
    creados: list[str] = []
    vistos: set[str] = set()
    for ln in lineas or []:
        nombre = (ln.get("producto") or "").strip()
        if not nombre or nombre in vistos:
            continue
        vistos.add(nombre)

        cursor.execute(
            f"SELECT producto_id FROM {TBL_PRODUCTOS} WHERE nombre = %s LIMIT 1",
            (nombre,),
        )
        if cursor.fetchone():
            continue

        sku_pdf = (ln.get("sku") or "").strip() or None
        sku = _generar_sku_unico(cursor, nombre, sku_pdf)
        cursor.execute(
            f"""
            INSERT INTO {TBL_PRODUCTOS} (sku, nombre, descripcion, unidad_medida)
            VALUES (%s, %s, %s, 'unidad')
            """,
            (sku, nombre, f"Alta automática DespachoWeb"),
        )
        creados.append(nombre)
    return creados


def guardar_orden(
    conn,
    datos: dict,
    lineas: list[dict],
    usuario: str,
    respaldo_ruta: Optional[str] = None,
) -> str:
    n_orden = str(datos.get("n_orden", "")).strip()
    if not n_orden:
        raise ValueError("N° Orden obligatorio")

    celular = _normalizar_celular_guardar(datos)
    direccion = _resolver_direccion(datos)
    if not direccion.strip():
        raise ValueError("Dirección obligatoria (incluya comuna para Maps).")
    if not lineas:
        raise ValueError("Debe incluir al menos una línea de detalle.")

    estado_inicial = normalizar_estado_orden(datos.get("estado"))

    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            INSERT INTO {TBL_ORDEN} (
                n_orden, fecha_oc, cliente, estado, transporte, fecha_estado,
                respaldo, direccion, comuna, celular, email, url, obs, creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                n_orden,
                datos.get("fecha_oc"),
                (datos.get("cliente") or "").strip(),
                estado_inicial,
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
                f"""
                INSERT INTO {TBL_DETALLE} (n_orden, producto, cantidad, total, estado)
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
            f"""
            UPDATE {TBL_ORDEN} SET
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
        cursor.execute(f"DELETE FROM {TBL_DETALLE} WHERE n_orden = %s", (n_orden,))
        for ln in lineas:
            producto = (ln.get("producto") or "").strip()
            if not producto:
                continue
            cantidad = float(ln.get("cantidad") or 1)
            total = int(ln.get("total") or 0)
            estado_ln = (ln.get("estado") or estado).strip()
            cursor.execute(
                f"""
                INSERT INTO {TBL_DETALLE} (n_orden, producto, cantidad, total, estado)
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
        cursor.execute(f"DELETE FROM {TBL_ORDEN} WHERE n_orden = %s", (n_orden,))
        if cursor.rowcount == 0:
            raise ValueError(f"Orden N° {n_orden} no encontrada.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def _filtros_orden_sql(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    comuna: Optional[str] = None,
    estado: Optional[str] = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if desde:
        clauses.append("o.fecha_oc >= %s")
        params.append(desde)
    if hasta:
        clauses.append("o.fecha_oc <= %s")
        params.append(hasta)
    if comuna:
        clauses.append("o.comuna LIKE %s")
        params.append(f"%{comuna.strip()}%")
    if estado:
        clauses.append("o.estado = %s")
        params.append(estado.strip())
    if not clauses:
        return "", params
    return " AND " + " AND ".join(clauses), params


def resumir_ventas_por_producto(
    cursor,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    comuna: Optional[str] = None,
    estado: Optional[str] = None,
    orden_por: Optional[str] = None,
    orden_dir: Optional[str] = None,
) -> list[dict]:
    extra, params = _filtros_orden_sql(desde, hasta, comuna, estado)
    col = _sort_col(orden_por, _RESUMEN_SORT, "cantidad_total")
    cursor.execute(
        f"""
        SELECT
            d.producto,
            SUM(d.cantidad) AS cantidad_total,
            SUM(d.total) AS monto_total,
            COUNT(DISTINCT d.n_orden) AS num_pedidos
        FROM {TBL_DETALLE} d
        INNER JOIN {TBL_ORDEN} o ON o.n_orden = d.n_orden
        WHERE 1=1{extra}
        GROUP BY d.producto
        ORDER BY {col} {_dir_sql(orden_dir)}, d.producto ASC
        """,
        params,
    )
    rows = cursor.fetchall() or []
    for row in rows:
        cant = float(row.get("cantidad_total") or 0)
        monto = int(row.get("monto_total") or 0)
        row["precio_prom"] = round(monto / cant) if cant else 0
    return rows


def listar_lineas_por_producto(
    cursor,
    producto: str,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    comuna: Optional[str] = None,
    estado: Optional[str] = None,
    orden_por: Optional[str] = None,
    orden_dir: Optional[str] = None,
) -> list[dict]:
    extra, params = _filtros_orden_sql(desde, hasta, comuna, estado)
    col = _sort_col(orden_por, _DETALLE_SORT, "o.fecha_oc")
    cursor.execute(
        f"""
        SELECT
            o.n_orden,
            o.fecha_oc,
            o.cliente,
            o.comuna,
            o.direccion,
            o.estado,
            d.cantidad,
            d.total,
            d.estado AS estado_linea
        FROM {TBL_DETALLE} d
        INNER JOIN {TBL_ORDEN} o ON o.n_orden = d.n_orden
        WHERE d.producto = %s{extra}
        ORDER BY {col} {_dir_sql(orden_dir)}, o.n_orden DESC
        """,
        [producto.strip()] + params,
    )
    return cursor.fetchall() or []


def listar_detalle_export_lineas(
    cursor,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    comuna: Optional[str] = None,
    estado: Optional[str] = None,
    producto: Optional[str] = None,
) -> list[dict]:
    """Todas las líneas de detalle con datos de cabecera (export Excel)."""
    extra, params = _filtros_orden_sql(desde, hasta, comuna, estado)
    producto_clause = ""
    query_params: list[Any] = []
    if producto:
        producto_clause = " AND d.producto = %s"
        query_params.append(producto.strip())
    query_params.extend(params)
    cursor.execute(
        f"""
        SELECT
            d.detalle_id,
            d.producto,
            d.cantidad,
            d.total,
            d.estado AS estado_linea,
            o.n_orden,
            o.fecha_oc,
            o.cliente,
            o.estado AS estado_orden,
            o.transporte,
            o.fecha_estado,
            o.direccion,
            o.comuna,
            o.celular,
            o.email,
            o.url,
            o.obs,
            o.creado_por,
            o.creado_at
        FROM {TBL_DETALLE} d
        INNER JOIN {TBL_ORDEN} o ON o.n_orden = d.n_orden
        WHERE 1=1{producto_clause}{extra}
        ORDER BY d.producto ASC, o.fecha_oc DESC, o.n_orden DESC, d.detalle_id ASC
        """,
        query_params,
    )
    return cursor.fetchall() or []


def contar_ordenes_filtradas(
    cursor,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    comuna: Optional[str] = None,
    estado: Optional[str] = None,
) -> int:
    extra, params = _filtros_orden_sql(desde, hasta, comuna, estado)
    cursor.execute(f"SELECT COUNT(*) AS c FROM {TBL_ORDEN} o WHERE 1=1{extra}", params)
    row = cursor.fetchone()
    return int(row["c"] if isinstance(row, dict) else row[0])
