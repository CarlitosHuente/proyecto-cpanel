"""Esquema y acceso a datos del módulo Fondos por Rendir (FxR)."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from utils.db import get_db_connection

TIPOS_DOC = ("boleta", "factura", "bh", "otro")
ESTADOS_REND = ("borrador", "preparada", "aprobada", "rechazada")


def asegurar_esquema_fxr() -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fxr_centro_costo (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    codigo VARCHAR(40) NOT NULL,
                    nombre VARCHAR(120) NOT NULL,
                    activo TINYINT(1) NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_fxr_cc_codigo (codigo)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fxr_tipo_gasto (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    codigo VARCHAR(40) NOT NULL,
                    nombre VARCHAR(120) NOT NULL,
                    activo TINYINT(1) NOT NULL DEFAULT 1,
                    permite_agrupar TINYINT(1) NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_fxr_tg_codigo (codigo)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            _ensure_col(cur, "fxr_tipo_gasto", "permite_agrupar", "TINYINT(1) NOT NULL DEFAULT 0")
            # Perfil FxR en usuarios (nombre legible + CC por defecto)
            _ensure_col(cur, "usuarios_huente", "nombre", "VARCHAR(190) NULL")
            _ensure_col(cur, "usuarios_huente", "fxr_centro_costo_id", "INT NULL")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fxr_rendicion (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    correlativo INT NULL,
                    usuario_email VARCHAR(190) NOT NULL,
                    nombre_snapshot VARCHAR(190) NOT NULL DEFAULT '',
                    area VARCHAR(120) NOT NULL DEFAULT '',
                    fecha_rendicion DATE NULL,
                    tipo VARCHAR(60) NOT NULL DEFAULT 'RENDICION_DE_FONDO',
                    estado VARCHAR(20) NOT NULL DEFAULT 'borrador',
                    total INT NOT NULL DEFAULT 0,
                    motivo_rechazo TEXT NULL,
                    comentario_firma TEXT NULL,
                    layout_json MEDIUMTEXT NULL,
                    pdf_drive_id VARCHAR(120) NULL,
                    pdf_url VARCHAR(500) NULL,
                    preparada_at DATETIME NULL,
                    aprobada_at DATETIME NULL,
                    aprobada_por VARCHAR(190) NULL,
                    rechazada_at DATETIME NULL,
                    rechazada_por VARCHAR(190) NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_fxr_correlativo (correlativo),
                    KEY idx_fxr_rend_usuario (usuario_email),
                    KEY idx_fxr_rend_estado (estado)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            _ensure_col(cur, "fxr_rendicion", "layout_json", "MEDIUMTEXT NULL")
            _ensure_col(cur, "fxr_rendicion", "comentario_firma", "TEXT NULL")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fxr_comprobante (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    usuario_email VARCHAR(190) NOT NULL,
                    rendicion_id INT NULL,
                    archivo_local VARCHAR(500) NOT NULL,
                    mime VARCHAR(120) NOT NULL DEFAULT 'application/octet-stream',
                    num_paginas INT NOT NULL DEFAULT 1,
                    estado_archivo VARCHAR(30) NOT NULL DEFAULT 'staging',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    KEY idx_fxr_comp_usuario (usuario_email),
                    KEY idx_fxr_comp_rend (rendicion_id),
                    CONSTRAINT fk_fxr_comp_rend FOREIGN KEY (rendicion_id)
                        REFERENCES fxr_rendicion(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fxr_linea (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    rendicion_id INT NOT NULL,
                    comprobante_id INT NOT NULL,
                    orden INT NOT NULL DEFAULT 0,
                    tipo_doc VARCHAR(20) NOT NULL DEFAULT 'otro',
                    n_doc VARCHAR(80) NULL,
                    n_doc_norm VARCHAR(80) NULL,
                    fecha_comprobante DATE NULL,
                    concepto VARCHAR(255) NOT NULL DEFAULT '',
                    tipo_gasto_id INT NULL,
                    centro_costo_id INT NULL,
                    monto INT NOT NULL DEFAULT 0,
                    observaciones TEXT NULL,
                    duplicado_n_doc TINYINT(1) NOT NULL DEFAULT 0,
                    duplicado_autorizado TINYINT(1) NOT NULL DEFAULT 0,
                    duplicado_autorizado_por VARCHAR(190) NULL,
                    duplicado_autorizado_at DATETIME NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    KEY idx_fxr_linea_rend (rendicion_id),
                    KEY idx_fxr_linea_ndoc (tipo_doc, n_doc_norm),
                    KEY idx_fxr_linea_comp (comprobante_id),
                    CONSTRAINT fk_fxr_linea_rend FOREIGN KEY (rendicion_id)
                        REFERENCES fxr_rendicion(id) ON DELETE CASCADE,
                    CONSTRAINT fk_fxr_linea_comp FOREIGN KEY (comprobante_id)
                        REFERENCES fxr_comprobante(id) ON DELETE RESTRICT,
                    CONSTRAINT fk_fxr_linea_tg FOREIGN KEY (tipo_gasto_id)
                        REFERENCES fxr_tipo_gasto(id) ON DELETE SET NULL,
                    CONSTRAINT fk_fxr_linea_cc FOREIGN KEY (centro_costo_id)
                        REFERENCES fxr_centro_costo(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fxr_estado_hist (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    rendicion_id INT NOT NULL,
                    estado_desde VARCHAR(20) NULL,
                    estado_hasta VARCHAR(20) NOT NULL,
                    usuario_email VARCHAR(190) NOT NULL,
                    nota VARCHAR(500) NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_fxr_hist_rend (rendicion_id),
                    CONSTRAINT fk_fxr_hist_rend FOREIGN KEY (rendicion_id)
                        REFERENCES fxr_rendicion(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            _seed_catalogos(cur)
        conn.commit()
    finally:
        conn.close()


def _ensure_col(cur, tabla: str, col: str, ddl: str) -> None:
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s
        """,
        (tabla, col),
    )
    row = cur.fetchone()
    if row and int(row["n"] if isinstance(row, dict) else row[0]) == 0:
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {ddl}")


def _seed_catalogos(cur) -> None:
    seeds_tg = [
        ("estacionamiento", "Estacionamiento", 1),
        ("peaje", "Peaje", 1),
        ("viatico", "Viático", 0),
        ("otro", "Otro", 0),
    ]
    for codigo, nombre, agrupar in seeds_tg:
        cur.execute(
            """
            INSERT IGNORE INTO fxr_tipo_gasto (codigo, nombre, activo, permite_agrupar)
            VALUES (%s, %s, 1, %s)
            """,
            (codigo, nombre, agrupar),
        )
    cur.execute(
        "UPDATE fxr_tipo_gasto SET permite_agrupar=1 WHERE codigo IN ('peaje','estacionamiento')"
    )
    seeds_cc = [
        ("ADM", "Administración"),
        ("OPE", "Operaciones"),
        ("COM", "Comercial"),
    ]
    for codigo, nombre in seeds_cc:
        cur.execute(
            """
            INSERT IGNORE INTO fxr_centro_costo (codigo, nombre, activo)
            VALUES (%s, %s, 1)
            """,
            (codigo, nombre),
        )


def normalizar_n_doc(n_doc: Optional[str]) -> Optional[str]:
    if not n_doc:
        return None
    s = re.sub(r"[^a-zA-Z0-9]", "", str(n_doc)).upper()
    return s or None


def dinero_entero(valor) -> int:
    if valor is None or valor == "":
        return 0
    if isinstance(valor, int):
        return valor
    s = str(valor).strip().replace("$", "").replace(".", "").replace(" ", "").replace(",", ".")
    try:
        return int(Decimal(s).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0


def _fetchall(sql: str, params=()) -> List[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall() or [])
    finally:
        conn.close()


def _fetchone(sql: str, params=()) -> Optional[dict]:
    rows = _fetchall(sql, params)
    return rows[0] if rows else None


def _execute(sql: str, params=(), many: bool = False) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if many:
                cur.executemany(sql, params)
            else:
                cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid or cur.rowcount
    finally:
        conn.close()


# --- catálogos ---

def listar_centros_costo(solo_activos: bool = False) -> List[dict]:
    sql = "SELECT * FROM fxr_centro_costo"
    if solo_activos:
        sql += " WHERE activo=1"
    sql += " ORDER BY nombre"
    return _fetchall(sql)


def listar_tipos_gasto(solo_activos: bool = False) -> List[dict]:
    sql = "SELECT * FROM fxr_tipo_gasto"
    if solo_activos:
        sql += " WHERE activo=1"
    sql += " ORDER BY nombre"
    return _fetchall(sql)


def upsert_catalogo(
    tabla: str,
    codigo: str,
    nombre: str,
    activo: int = 1,
    id_: Optional[int] = None,
    permite_agrupar: Optional[int] = None,
) -> None:
    assert tabla in ("fxr_centro_costo", "fxr_tipo_gasto")
    if tabla == "fxr_tipo_gasto":
        agr = 1 if permite_agrupar else 0
        if id_:
            _execute(
                """
                UPDATE fxr_tipo_gasto
                SET codigo=%s, nombre=%s, activo=%s, permite_agrupar=%s
                WHERE id=%s
                """,
                (codigo.strip(), nombre.strip(), int(activo), agr, id_),
            )
        else:
            _execute(
                """
                INSERT INTO fxr_tipo_gasto (codigo, nombre, activo, permite_agrupar)
                VALUES (%s,%s,%s,%s)
                """,
                (codigo.strip(), nombre.strip(), int(activo), agr),
            )
        return
    if id_:
        _execute(
            f"UPDATE {tabla} SET codigo=%s, nombre=%s, activo=%s WHERE id=%s",
            (codigo.strip(), nombre.strip(), int(activo), id_),
        )
    else:
        _execute(
            f"INSERT INTO {tabla} (codigo, nombre, activo) VALUES (%s,%s,%s)",
            (codigo.strip(), nombre.strip(), int(activo)),
        )


def guardar_layout_rendicion(rid: int, layout: dict) -> None:
    _execute("UPDATE fxr_rendicion SET layout_json=%s WHERE id=%s", (json.dumps(layout), rid))


def obtener_layout_rendicion(rid: int) -> Optional[dict]:
    r = obtener_rendicion(rid)
    if not r or not r.get("layout_json"):
        return None
    try:
        return json.loads(r["layout_json"])
    except Exception:
        return None


# --- comprobantes ---

def crear_comprobante(usuario_email: str, archivo_local: str, mime: str, num_paginas: int = 1) -> int:
    return _execute(
        """
        INSERT INTO fxr_comprobante (usuario_email, archivo_local, mime, num_paginas, estado_archivo)
        VALUES (%s,%s,%s,%s,'staging')
        """,
        (usuario_email, archivo_local, mime, num_paginas),
    )


def listar_inbox(usuario_email: str) -> List[dict]:
    return _fetchall(
        """
        SELECT * FROM fxr_comprobante
        WHERE usuario_email=%s AND rendicion_id IS NULL AND estado_archivo='staging'
        ORDER BY id DESC
        """,
        (usuario_email,),
    )


def obtener_comprobante(comp_id: int) -> Optional[dict]:
    return _fetchone("SELECT * FROM fxr_comprobante WHERE id=%s", (comp_id,))


def actualizar_comprobante_archivo(comp_id: int, archivo_local: str, mime: str, num_paginas: int) -> None:
    _execute(
        """
        UPDATE fxr_comprobante
        SET archivo_local=%s, mime=%s, num_paginas=%s
        WHERE id=%s
        """,
        (archivo_local, mime, num_paginas, comp_id),
    )


# --- rendiciones ---

def crear_rendicion(usuario_email: str, nombre: str, area: str = "") -> int:
    rid = _execute(
        """
        INSERT INTO fxr_rendicion (usuario_email, nombre_snapshot, area, fecha_rendicion, estado)
        VALUES (%s,%s,%s,%s,'borrador')
        """,
        (usuario_email, nombre or usuario_email, area or "", date.today()),
    )
    registrar_hist(rid, None, "borrador", usuario_email, "Creación")
    return rid


def obtener_rendicion(rid: int) -> Optional[dict]:
    return _fetchone("SELECT * FROM fxr_rendicion WHERE id=%s", (rid,))


def listar_rendiciones_usuario(usuario_email: str) -> List[dict]:
    return _fetchall(
        """
        SELECT * FROM fxr_rendicion
        WHERE usuario_email=%s
        ORDER BY FIELD(estado,'borrador','preparada','rechazada','aprobada'), id DESC
        """,
        (usuario_email,),
    )


def listar_rendiciones_preparadas() -> List[dict]:
    return _fetchall(
        """
        SELECT * FROM fxr_rendicion
        WHERE estado='preparada'
        ORDER BY preparada_at ASC, id ASC
        """
    )


def listar_rendiciones_todas(limit: int = 100) -> List[dict]:
    return _fetchall(
        """
        SELECT * FROM fxr_rendicion
        ORDER BY id DESC
        LIMIT %s
        """,
        (limit,),
    )


def listar_rendiciones_aprobadas(limit: int = 200) -> List[dict]:
    return _fetchall(
        """
        SELECT * FROM fxr_rendicion
        WHERE estado='aprobada'
        ORDER BY correlativo DESC, id DESC
        LIMIT %s
        """,
        (limit,),
    )


def registrar_hist(rid: int, desde: Optional[str], hasta: str, email: str, nota: str = "") -> None:
    _execute(
        """
        INSERT INTO fxr_estado_hist (rendicion_id, estado_desde, estado_hasta, usuario_email, nota)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (rid, desde, hasta, email, nota or None),
    )


def actualizar_rendicion_campos(rid: int, **campos) -> None:
    if not campos:
        return
    cols = ", ".join(f"{k}=%s" for k in campos)
    _execute(f"UPDATE fxr_rendicion SET {cols} WHERE id=%s", (*campos.values(), rid))


def recalcular_total(rid: int) -> int:
    row = _fetchone("SELECT COALESCE(SUM(monto),0) AS t FROM fxr_linea WHERE rendicion_id=%s", (rid,))
    total = int(row["t"] if row else 0)
    _execute("UPDATE fxr_rendicion SET total=%s WHERE id=%s", (total, rid))
    return total


def siguiente_correlativo() -> int:
    row = _fetchone("SELECT COALESCE(MAX(correlativo),0)+1 AS n FROM fxr_rendicion")
    return int(row["n"] if row else 1)


# --- líneas ---

def listar_lineas(rid: int) -> List[dict]:
    return _fetchall(
        """
        SELECT l.*, c.archivo_local, c.mime, c.num_paginas,
               tg.nombre AS tipo_gasto_nombre, tg.permite_agrupar AS permite_agrupar,
               cc.nombre AS centro_costo_nombre,
               cc.codigo AS centro_costo_codigo
        FROM fxr_linea l
        JOIN fxr_comprobante c ON c.id = l.comprobante_id
        LEFT JOIN fxr_tipo_gasto tg ON tg.id = l.tipo_gasto_id
        LEFT JOIN fxr_centro_costo cc ON cc.id = l.centro_costo_id
        WHERE l.rendicion_id=%s
        ORDER BY l.orden, l.id
        """,
        (rid,),
    )


def obtener_linea(linea_id: int) -> Optional[dict]:
    return _fetchone(
        """
        SELECT l.*, c.archivo_local, c.mime, c.usuario_email AS comp_usuario,
               r.usuario_email AS rend_usuario, r.estado AS rend_estado,
               r.correlativo, r.nombre_snapshot, r.aprobada_at
        FROM fxr_linea l
        JOIN fxr_comprobante c ON c.id = l.comprobante_id
        JOIN fxr_rendicion r ON r.id = l.rendicion_id
        WHERE l.id=%s
        """,
        (linea_id,),
    )


def buscar_duplicados(tipo_doc: str, n_doc_norm: str, excluir_linea_id: Optional[int] = None) -> List[dict]:
    if not n_doc_norm or tipo_doc not in ("factura", "bh"):
        return []
    sql = """
        SELECT l.id, l.rendicion_id, l.monto, l.fecha_comprobante, l.n_doc, l.tipo_doc,
               l.created_at, r.usuario_email, r.nombre_snapshot, r.correlativo, r.estado,
               r.aprobada_at
        FROM fxr_linea l
        JOIN fxr_rendicion r ON r.id = l.rendicion_id
        WHERE l.tipo_doc=%s AND l.n_doc_norm=%s AND r.estado <> 'rechazada'
    """
    params: List[Any] = [tipo_doc, n_doc_norm]
    if excluir_linea_id:
        sql += " AND l.id <> %s"
        params.append(excluir_linea_id)
    sql += " ORDER BY l.id ASC"
    return _fetchall(sql, tuple(params))


def perfil_usuario(email: str) -> dict:
    """Nombre legible y centro de costo FxR por defecto (usuarios_huente)."""
    row = _fetchone(
        """
        SELECT u.email, u.nombre, u.fxr_centro_costo_id,
               cc.codigo AS fxr_cc_codigo, cc.nombre AS fxr_cc_nombre
        FROM usuarios_huente u
        LEFT JOIN fxr_centro_costo cc ON cc.id = u.fxr_centro_costo_id
        WHERE u.email=%s
        """,
        (email,),
    )
    if not row:
        return {
            "email": email,
            "nombre": email,
            "fxr_centro_costo_id": None,
            "fxr_cc_codigo": None,
            "fxr_cc_nombre": None,
        }
    nombre = (row.get("nombre") or "").strip() or email
    return {
        "email": row.get("email") or email,
        "nombre": nombre,
        "fxr_centro_costo_id": row.get("fxr_centro_costo_id"),
        "fxr_cc_codigo": row.get("fxr_cc_codigo"),
        "fxr_cc_nombre": row.get("fxr_cc_nombre"),
    }


def vincular_comprobantes_a_rendicion(rid: int, comp_ids: List[int], usuario_email: str) -> int:
    """Crea líneas vacías para comprobantes del inbox. Devuelve cantidad vinculada."""
    n = 0
    perfil = perfil_usuario(usuario_email)
    cc_default = perfil.get("fxr_centro_costo_id")
    orden_row = _fetchone("SELECT COALESCE(MAX(orden),0) AS m FROM fxr_linea WHERE rendicion_id=%s", (rid,))
    orden = int(orden_row["m"] if orden_row else 0)
    for cid in comp_ids:
        comp = obtener_comprobante(cid)
        if not comp or comp["usuario_email"] != usuario_email:
            continue
        if comp["rendicion_id"]:
            continue
        orden += 1
        _execute(
            """
            UPDATE fxr_comprobante
            SET rendicion_id=%s, estado_archivo='en_rendicion'
            WHERE id=%s
            """,
            (rid, cid),
        )
        _execute(
            """
            INSERT INTO fxr_linea (rendicion_id, comprobante_id, orden, tipo_doc, concepto, monto, centro_costo_id)
            VALUES (%s,%s,%s,'otro','',0,%s)
            """,
            (rid, cid, orden, cc_default),
        )
        n += 1
    recalcular_total(rid)
    return n


def guardar_linea(linea_id: int, data: dict) -> Tuple[bool, str, List[dict]]:
    linea = obtener_linea(linea_id)
    if not linea:
        return False, "Línea no encontrada", []
    if linea["rend_estado"] not in ("borrador", "rechazada"):
        return False, "La rendición no está editable", []

    tipo_doc = (data.get("tipo_doc") or "otro").strip().lower()
    if tipo_doc not in TIPOS_DOC:
        tipo_doc = "otro"
    n_doc = (data.get("n_doc") or "").strip() or None
    n_norm = normalizar_n_doc(n_doc)
    if tipo_doc in ("factura", "bh") and not n_norm:
        return False, "N° documento obligatorio para factura/BH", []

    dups = buscar_duplicados(tipo_doc, n_norm, excluir_linea_id=linea_id) if n_norm else []
    es_dup = 1 if dups else 0

    _execute(
        """
        UPDATE fxr_linea SET
            tipo_doc=%s, n_doc=%s, n_doc_norm=%s,
            fecha_comprobante=%s, concepto=%s,
            tipo_gasto_id=%s, centro_costo_id=%s,
            monto=%s, observaciones=%s,
            duplicado_n_doc=%s,
            duplicado_autorizado=IF(%s=0, 0, duplicado_autorizado),
            duplicado_autorizado_por=IF(%s=0, NULL, duplicado_autorizado_por),
            duplicado_autorizado_at=IF(%s=0, NULL, duplicado_autorizado_at)
        WHERE id=%s
        """,
        (
            tipo_doc,
            n_doc,
            n_norm,
            data.get("fecha_comprobante") or None,
            (data.get("concepto") or "").strip()[:255],
            data.get("tipo_gasto_id") or None,
            data.get("centro_costo_id") or None,
            dinero_entero(data.get("monto")),
            (data.get("observaciones") or "").strip() or None,
            es_dup,
            es_dup,
            es_dup,
            es_dup,
            linea_id,
        ),
    )
    recalcular_total(linea["rendicion_id"])
    msg = "Guardado"
    if es_dup:
        msg = "Guardado con alerta: N° documento ya existe en otra rendición"
    return True, msg, dups


def autorizar_duplicado(linea_id: int, email: str) -> Tuple[bool, str]:
    linea = obtener_linea(linea_id)
    if not linea:
        return False, "Línea no encontrada"
    if not linea["duplicado_n_doc"]:
        return False, "La línea no está marcada como duplicado"
    _execute(
        """
        UPDATE fxr_linea
        SET duplicado_autorizado=1, duplicado_autorizado_por=%s, duplicado_autorizado_at=%s
        WHERE id=%s
        """,
        (email, datetime.now(), linea_id),
    )
    return True, "Duplicado autorizado"


def validar_para_preparar(rid: int) -> List[str]:
    errores = []
    lineas = listar_lineas(rid)
    if not lineas:
        errores.append("Debe tener al menos un comprobante")
        return errores
    for i, l in enumerate(lineas, 1):
        if not l.get("concepto"):
            errores.append(f"Línea {i}: falta concepto")
        if int(l.get("monto") or 0) <= 0:
            errores.append(f"Línea {i}: monto debe ser > 0")
        if not l.get("centro_costo_id"):
            errores.append(f"Línea {i}: falta centro de costo")
        if not l.get("tipo_gasto_id"):
            errores.append(f"Línea {i}: falta tipo de gasto")
        if l.get("tipo_doc") in ("factura", "bh") and not l.get("n_doc_norm"):
            errores.append(f"Línea {i}: falta N° documento")
        if not l.get("fecha_comprobante"):
            errores.append(f"Línea {i}: falta fecha")
    return errores


def hay_duplicados_sin_autorizar(rid: int) -> List[dict]:
    return [l for l in listar_lineas(rid) if l.get("duplicado_n_doc") and not l.get("duplicado_autorizado")]


def marcar_comprobante_consumido(comp_id: int) -> None:
    _execute(
        "UPDATE fxr_comprobante SET estado_archivo='consumido', archivo_local='' WHERE id=%s",
        (comp_id,),
    )


def quitar_linea_a_inbox(linea_id: int, usuario_email: str) -> Tuple[bool, str]:
    """Quita la línea de la rendición; el comprobante vuelve al inbox (nunca se borra el archivo)."""
    linea = obtener_linea(linea_id)
    if not linea:
        return False, "Línea no encontrada"
    if linea["rend_usuario"] != usuario_email:
        return False, "No autorizado"
    if linea["rend_estado"] not in ("borrador", "rechazada"):
        return False, "Solo se puede quitar en borrador o rechazada"

    rid = linea["rendicion_id"]
    cid = linea["comprobante_id"]
    _execute("DELETE FROM fxr_linea WHERE id=%s", (linea_id,))
    _execute(
        """
        UPDATE fxr_comprobante
        SET rendicion_id=NULL, estado_archivo='staging'
        WHERE id=%s
        """,
        (cid,),
    )
    recalcular_total(rid)
    return True, "Documento vuelto al inbox"


def eliminar_rendicion_a_inbox(rid: int, usuario_email: str) -> Tuple[bool, str]:
    """Elimina la rendición entera; todos los comprobantes vuelven al inbox."""
    r = obtener_rendicion(rid)
    if not r:
        return False, "Rendición no encontrada"
    if r["usuario_email"] != usuario_email:
        return False, "No autorizado"
    if r["estado"] not in ("borrador", "rechazada"):
        return False, "Solo se puede eliminar rendiciones en borrador o rechazada"

    lineas = listar_lineas(rid)
    for l in lineas:
        _execute("DELETE FROM fxr_linea WHERE id=%s", (l["id"],))
        _execute(
            """
            UPDATE fxr_comprobante
            SET rendicion_id=NULL, estado_archivo='staging'
            WHERE id=%s
            """,
            (l["comprobante_id"],),
        )
    # Por si quedan comprobantes vinculados sin línea
    _execute(
        """
        UPDATE fxr_comprobante
        SET rendicion_id=NULL, estado_archivo='staging'
        WHERE rendicion_id=%s
        """,
        (rid,),
    )
    _execute("DELETE FROM fxr_estado_hist WHERE rendicion_id=%s", (rid,))
    _execute("DELETE FROM fxr_rendicion WHERE id=%s", (rid,))
    return True, "Rendición eliminada; documentos en inbox"


def info_duplicados_para_pdf(lineas: List[dict]) -> List[dict]:
    """Para cada línea duplicada autorizada, adjunta datos del otro registro."""
    out = []
    for l in lineas:
        if not l.get("duplicado_n_doc"):
            continue
        dups = buscar_duplicados(l["tipo_doc"], l.get("n_doc_norm") or "", excluir_linea_id=l["id"])
        for d in dups:
            out.append(
                {
                    "linea_id": l["id"],
                    "n_doc": l.get("n_doc"),
                    "tipo_doc": l.get("tipo_doc"),
                    "otro_rendicion_id": d["rendicion_id"],
                    "otro_correlativo": d.get("correlativo"),
                    "otro_usuario": d.get("nombre_snapshot") or d.get("usuario_email"),
                    "otro_email": d.get("usuario_email"),
                    "otro_cuando": d.get("aprobada_at") or d.get("created_at"),
                    "otro_monto": d.get("monto"),
                    "otro_estado": d.get("estado"),
                    "autorizado": bool(l.get("duplicado_autorizado")),
                    "autorizado_por": l.get("duplicado_autorizado_por"),
                }
            )
    return out
