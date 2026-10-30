"""Fidelización: cuentas, espera de caja, puntos y canjes."""

from __future__ import annotations

import re
import secrets
import threading
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from utils.db import get_db_connection

TZ = ZoneInfo("America/Santiago")
ESPERA_MINUTOS = 30
CODIGO_MINUTOS = 10
INTENTOS_RECUP = 5
VENTANA_INTENTOS_MIN = 15

_LISTO = False
_LOCK = threading.Lock()

_SQL = [
    """
    CREATE TABLE IF NOT EXISTS fideliza_tag (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        token VARCHAR(80) NOT NULL,
        nombre VARCHAR(80) NOT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        creado_at DATETIME NOT NULL,
        UNIQUE KEY uq_fid_tag_token (token)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS fideliza_cliente (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(120) NOT NULL,
        rut VARCHAR(12) NOT NULL,
        correo VARCHAR(180) NOT NULL,
        saldo INT NOT NULL DEFAULT 0,
        cookie_token VARCHAR(80) NOT NULL,
        ultima_acreditacion_at DATETIME NULL,
        creado_at DATETIME NOT NULL,
        UNIQUE KEY uq_fid_cliente_rut (rut),
        UNIQUE KEY uq_fid_cliente_correo (correo),
        UNIQUE KEY uq_fid_cliente_cookie (cookie_token)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS fideliza_espera (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        cliente_id INT NOT NULL,
        tag_id INT NOT NULL,
        token VARCHAR(80) NOT NULL,
        estado VARCHAR(20) NOT NULL,
        creado_at DATETIME NOT NULL,
        cerrado_at DATETIME NULL,
        UNIQUE KEY uq_fid_espera_token (token),
        KEY idx_fid_espera_estado (estado, creado_at),
        KEY idx_fid_espera_cliente (cliente_id, estado),
        CONSTRAINT fk_fid_espera_cliente FOREIGN KEY (cliente_id) REFERENCES fideliza_cliente(id),
        CONSTRAINT fk_fid_espera_tag FOREIGN KEY (tag_id) REFERENCES fideliza_tag(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS fideliza_movimiento (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        cliente_id INT NOT NULL,
        espera_id INT NULL,
        tipo VARCHAR(20) NOT NULL,
        detalle VARCHAR(180) NOT NULL,
        puntos INT NOT NULL,
        saldo_despues INT NOT NULL,
        usuario VARCHAR(120) NULL,
        correo_ok TINYINT NOT NULL DEFAULT 0,
        correo_error VARCHAR(255) NULL,
        anula_movimiento_id INT NULL,
        creado_at DATETIME NOT NULL,
        KEY idx_fid_mov_cliente (cliente_id, creado_at),
        KEY idx_fid_mov_anula (anula_movimiento_id),
        CONSTRAINT fk_fid_mov_cliente FOREIGN KEY (cliente_id) REFERENCES fideliza_cliente(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS fideliza_opcion (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        etiqueta VARCHAR(40) NOT NULL,
        puntos INT NOT NULL,
        orden INT NOT NULL DEFAULT 0,
        activo TINYINT NOT NULL DEFAULT 1
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS fideliza_premio (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(120) NOT NULL,
        puntos INT NOT NULL,
        orden INT NOT NULL DEFAULT 0,
        activo TINYINT NOT NULL DEFAULT 1
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS fideliza_config (
        id INT NOT NULL PRIMARY KEY,
        minutos_entre_puntos INT NOT NULL DEFAULT 60
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS fideliza_codigo (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        cliente_id INT NOT NULL,
        codigo VARCHAR(12) NOT NULL,
        vence_at DATETIME NOT NULL,
        usado_at DATETIME NULL,
        creado_por VARCHAR(120) NULL,
        creado_at DATETIME NOT NULL,
        KEY idx_fid_codigo_cliente (cliente_id, usado_at),
        CONSTRAINT fk_fid_codigo_cliente FOREIGN KEY (cliente_id) REFERENCES fideliza_cliente(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS fideliza_recup_intento (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        rut VARCHAR(12) NOT NULL,
        creado_at DATETIME NOT NULL,
        KEY idx_fid_intento_rut (rut, creado_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


class FidelizaError(Exception):
    pass


class HoraBloqueada(FidelizaError):
    def __init__(self, hasta: datetime):
        super().__init__("Este cliente ya sumó puntos en la última hora.")
        self.hasta = hasta


def ahora() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def _token() -> str:
    return secrets.token_urlsafe(32)


def dv_rut(cuerpo: str) -> str:
    suma = 0
    mul = 2
    for ch in reversed(cuerpo):
        suma += int(ch) * mul
        mul = 2 if mul == 7 else mul + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def normalizar_rut(raw: str) -> Optional[str]:
    s = (raw or "").strip().upper().replace(".", "").replace(" ", "")
    s = s.replace("–", "-").replace("—", "-")
    if not s:
        return None
    if "-" in s:
        cuerpo, dv = s.split("-", 1)
    elif len(s) >= 2:
        cuerpo, dv = s[:-1], s[-1]
    else:
        return None
    if not cuerpo.isdigit() or not 7 <= len(cuerpo) <= 8:
        return None
    if dv not in "0123456789K" or dv_rut(cuerpo) != dv:
        return None
    return f"{int(cuerpo)}-{dv}"


def rut_mostrar(rut: str) -> str:
    cuerpo, dv = (rut or "").split("-", 1)
    partes = []
    while cuerpo:
        partes.append(cuerpo[-3:])
        cuerpo = cuerpo[:-3]
    return ".".join(reversed(partes)) + "-" + dv


def normalizar_correo(raw: str) -> Optional[str]:
    correo = (raw or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        return None
    if len(correo) > 180:
        return None
    return correo


def normalizar_codigo(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def asegurar_esquema() -> None:
    global _LISTO
    if _LISTO:
        return
    with _LOCK:
        if _LISTO:
            return
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                for sql in _SQL:
                    cur.execute(sql)
                cur.execute("SELECT COUNT(*) AS n FROM fideliza_config")
                if cur.fetchone()["n"] == 0:
                    cur.execute(
                        "INSERT INTO fideliza_config (id, minutos_entre_puntos) VALUES (1, 60)"
                    )
                cur.execute("SELECT COUNT(*) AS n FROM fideliza_opcion")
                if cur.fetchone()["n"] == 0:
                    cur.executemany(
                        "INSERT INTO fideliza_opcion (etiqueta, puntos, orden, activo) VALUES (%s, %s, %s, 1)",
                        [("8", 1, 1), ("12", 2, 2), ("16", 3, 3)],
                    )
                _agregar_columna(cur, "fideliza_tag", "sucursal_id", "sucursal_id INT NULL")
                _agregar_columna(cur, "fideliza_movimiento", "tag_id", "tag_id INT NULL")
                _agregar_columna(cur, "fideliza_cliente", "acepta_puntos", "acepta_puntos TINYINT NOT NULL DEFAULT 0")
                _agregar_columna(cur, "fideliza_cliente", "acepta_publicidad", "acepta_publicidad TINYINT NOT NULL DEFAULT 0")
                _agregar_columna(cur, "fideliza_cliente", "acepta_at", "acepta_at DATETIME NULL")
                _agregar_columna(cur, "fideliza_config", "bases_puntos", "bases_puntos MEDIUMTEXT NULL")
                _agregar_columna(cur, "fideliza_config", "bases_confidencialidad", "bases_confidencialidad MEDIUMTEXT NULL")
                _agregar_columna(cur, "fideliza_config", "etiqueta_puntos", "etiqueta_puntos VARCHAR(240) NULL")
                _agregar_columna(
                    cur, "fideliza_config", "etiqueta_confidencialidad", "etiqueta_confidencialidad VARCHAR(240) NULL"
                )
                _agregar_columna(cur, "fideliza_config", "correo_asunto", "correo_asunto VARCHAR(180) NULL")
                _agregar_columna(cur, "fideliza_config", "correo_html", "correo_html MEDIUMTEXT NULL")
                _agregar_columna(cur, "fideliza_config", "correo_color", "correo_color VARCHAR(7) NULL")
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'fideliza_tag'
                      AND INDEX_NAME = 'uq_fid_tag_sucursal'
                    """
                )
                if cur.fetchone()["n"] == 0:
                    cur.execute(
                        "ALTER TABLE fideliza_tag ADD UNIQUE KEY uq_fid_tag_sucursal (sucursal_id)"
                    )
            conn.commit()
            _LISTO = True
        finally:
            conn.close()


def _agregar_columna(cur, tabla: str, columna: str, ddl: str) -> None:
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (tabla, columna),
    )
    if cur.fetchone()["n"] == 0:
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {ddl}")


def nombre_usuario(email: str) -> str:
    email = (email or "").strip()
    if not email:
        return ""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nombre FROM usuarios_huente WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row and (row.get("nombre") or "").strip():
        return row["nombre"].strip()
    return email


def _expirar_esperas(cur, momento: datetime) -> None:
    limite = momento - timedelta(minutes=ESPERA_MINUTOS)
    cur.execute(
        """
        UPDATE fideliza_espera
        SET estado = 'expirada', cerrado_at = %s
        WHERE estado = 'esperando' AND creado_at < %s
        """,
        (momento, limite),
    )


def minutos_entre_puntos(cur=None) -> int:
    propia = cur is None
    conn = None
    if propia:
        asegurar_esquema()
        conn = get_db_connection()
        cur = conn.cursor()
    try:
        cur.execute("SELECT minutos_entre_puntos FROM fideliza_config WHERE id = 1")
        row = cur.fetchone()
        minutos = int(row["minutos_entre_puntos"]) if row else 60
        return max(1, min(minutos, 1440))
    finally:
        if propia and conn is not None:
            conn.close()


def premios_activos() -> list:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, puntos, orden, activo
                FROM fideliza_premio
                WHERE activo = 1
                ORDER BY orden, id
                """
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def faltan_premios(saldo: int, premios: Optional[list] = None) -> list:
    saldo = int(saldo or 0)
    salida = []
    for premio in premios if premios is not None else premios_activos():
        costo = int(premio["puntos"])
        faltan = max(0, costo - saldo)
        salida.append(
            {
                "id": premio["id"],
                "nombre": premio["nombre"],
                "puntos": costo,
                "faltan": faltan,
                "listo": faltan == 0,
            }
        )
    return salida


def obtener_tag(token: str) -> Optional[dict]:
    if not token or len(token) < 20:
        return None
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM fideliza_tag WHERE token = %s AND activo = 1",
                (token,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def obtener_cliente_cookie(cookie: str) -> Optional[dict]:
    if not cookie:
        return None
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM fideliza_cliente WHERE cookie_token = %s",
                (cookie,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def bloqueo_hora(cliente: dict, momento: Optional[datetime] = None, minutos: Optional[int] = None) -> Optional[datetime]:
    ultima = cliente.get("ultima_acreditacion_at")
    if not ultima:
        return None
    momento = momento or ahora()
    minutos = minutos if minutos is not None else minutos_entre_puntos()
    hasta = ultima + timedelta(minutes=int(minutos))
    if momento < hasta:
        return hasta
    return None


def crear_cliente(nombre: str, rut: str, correo: str, acepta_puntos: bool = False, acepta_publicidad: bool = False) -> dict:
    nombre = (nombre or "").strip()
    if len(nombre) < 2 or len(nombre) > 120:
        raise FidelizaError("Escribe tu nombre.")
    rut_n = normalizar_rut(rut)
    if not rut_n:
        raise FidelizaError("El RUT no es válido.")
    correo_n = normalizar_correo(correo)
    if not correo_n:
        raise FidelizaError("El correo no es válido.")
    if not acepta_puntos:
        raise FidelizaError("Para crear la cuenta hay que aceptar las bases.")
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM fideliza_cliente WHERE rut = %s", (rut_n,))
            if cur.fetchone():
                raise FidelizaError("Este RUT ya está registrado. Entra con Ya tengo cuenta.")
            cur.execute("SELECT id FROM fideliza_cliente WHERE correo = %s", (correo_n,))
            if cur.fetchone():
                raise FidelizaError("Este correo ya está registrado. Entra con Ya tengo cuenta.")
            token = _token()
            cur.execute(
                """
                INSERT INTO fideliza_cliente
                    (nombre, rut, correo, saldo, cookie_token, creado_at,
                     acepta_puntos, acepta_publicidad, acepta_at)
                VALUES (%s, %s, %s, 0, %s, %s, 1, 0, %s)
                """,
                (nombre, rut_n, correo_n, token, momento, momento),
            )
            cur.execute("SELECT * FROM fideliza_cliente WHERE id = %s", (cur.lastrowid,))
            cliente = cur.fetchone()
        conn.commit()
        return cliente
    except FidelizaError:
        conn.rollback()
        raise
    finally:
        conn.close()


def abrir_espera(cliente_id: int, tag_id: int) -> dict:
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            _expirar_esperas(cur, momento)
            cur.execute(
                "SELECT * FROM fideliza_cliente WHERE id = %s FOR UPDATE",
                (cliente_id,),
            )
            cliente = cur.fetchone()
            if not cliente:
                raise FidelizaError("No encontramos la cuenta.")
            hasta = bloqueo_hora(cliente, momento, minutos_entre_puntos(cur))
            if hasta:
                raise HoraBloqueada(hasta)
            cur.execute(
                """
                SELECT * FROM fideliza_espera
                WHERE cliente_id = %s AND estado = 'esperando'
                ORDER BY id DESC LIMIT 1
                FOR UPDATE
                """,
                (cliente_id,),
            )
            espera = cur.fetchone()
            if not espera:
                token = _token()
                cur.execute(
                    """
                    INSERT INTO fideliza_espera
                        (cliente_id, tag_id, token, estado, creado_at)
                    VALUES (%s, %s, %s, 'esperando', %s)
                    """,
                    (cliente_id, tag_id, token, momento),
                )
                cur.execute("SELECT * FROM fideliza_espera WHERE id = %s", (cur.lastrowid,))
                espera = cur.fetchone()
        conn.commit()
        return espera
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def espera_publica(token: str) -> Optional[dict]:
    if not token:
        return None
    asegurar_esquema()
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            _expirar_esperas(cur, momento)
            cur.execute(
                """
                SELECT e.*, c.nombre, c.saldo, c.correo
                FROM fideliza_espera e
                JOIN fideliza_cliente c ON c.id = e.cliente_id
                WHERE e.token = %s
                """,
                (token,),
            )
            row = cur.fetchone()
        conn.commit()
        return row
    finally:
        conn.close()


def listar_cola(tag_id: Optional[int] = None) -> list:
    asegurar_esquema()
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            _expirar_esperas(cur, momento)
            sql = """
                SELECT e.id, e.cliente_id, e.tag_id, e.creado_at,
                       c.nombre, c.correo, c.saldo, c.rut, t.nombre AS sucursal
                FROM fideliza_espera e
                JOIN fideliza_cliente c ON c.id = e.cliente_id
                JOIN fideliza_tag t ON t.id = e.tag_id
                WHERE e.estado = 'esperando'
            """
            params = []
            if tag_id:
                sql += " AND e.tag_id = %s"
                params.append(tag_id)
            sql += " ORDER BY e.creado_at, e.id"
            cur.execute(sql, params)
            filas = list(cur.fetchall())
        conn.commit()
        return filas
    finally:
        conn.close()


def opciones_activas() -> list:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, etiqueta, puntos, orden, activo
                FROM fideliza_opcion
                WHERE activo = 1
                ORDER BY orden, id
                """
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def _marcar_correo(cur, mov_id: int, ok: bool, error: str = "") -> None:
    cur.execute(
        "UPDATE fideliza_movimiento SET correo_ok = %s, correo_error = %s WHERE id = %s",
        (1 if ok else 0, (error or "")[:255] or None, mov_id),
    )


def _datos_aviso(cur, mov_id: int) -> dict:
    cur.execute(
        """
        SELECT m.*, c.nombre, c.correo, c.saldo, IFNULL(t.nombre, '') AS sucursal
        FROM fideliza_movimiento m
        JOIN fideliza_cliente c ON c.id = m.cliente_id
        LEFT JOIN fideliza_tag t ON t.id = m.tag_id
        WHERE m.id = %s
        """,
        (mov_id,),
    )
    mov = cur.fetchone()
    if not mov:
        return None
    cur.execute(
        "SELECT id, nombre, puntos FROM fideliza_premio WHERE activo = 1 ORDER BY orden, id"
    )
    premios = list(cur.fetchall())
    return {"mov": mov, "premios": faltan_premios(mov["saldo_despues"], premios)}


def registrar_resultado_correo(mov_id: int, ok: bool, error: str = "") -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            _marcar_correo(cur, mov_id, ok, error)
        conn.commit()
    finally:
        conn.close()


def datos_aviso(mov_id: int) -> Optional[dict]:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            return _datos_aviso(cur, mov_id)
    finally:
        conn.close()


def acreditar(espera_id: int, opcion_id: int, usuario: str, tag_id: Optional[int] = None) -> dict:
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            _expirar_esperas(cur, momento)
            cur.execute(
                "SELECT * FROM fideliza_espera WHERE id = %s FOR UPDATE",
                (espera_id,),
            )
            espera = cur.fetchone()
            if not espera or espera["estado"] != "esperando":
                raise FidelizaError("Este turno ya no está en espera.")
            if tag_id and int(espera["tag_id"]) != int(tag_id):
                raise FidelizaError("Este cliente acercó el teléfono en otra sucursal.")
            cur.execute(
                "SELECT * FROM fideliza_cliente WHERE id = %s FOR UPDATE",
                (espera["cliente_id"],),
            )
            cliente = cur.fetchone()
            minutos = minutos_entre_puntos(cur)
            if bloqueo_hora(cliente, momento, minutos):
                raise FidelizaError("Este cliente ya sumó puntos en la última hora.")
            cur.execute(
                "SELECT * FROM fideliza_opcion WHERE id = %s AND activo = 1",
                (opcion_id,),
            )
            opcion = cur.fetchone()
            if not opcion or int(opcion["puntos"]) < 1:
                raise FidelizaError("Esa opción no está disponible.")
            cur.execute(
                """
                UPDATE fideliza_espera
                SET estado = 'acreditada', cerrado_at = %s
                WHERE id = %s AND estado = 'esperando'
                """,
                (momento, espera_id),
            )
            if cur.rowcount != 1:
                raise FidelizaError("Este turno ya fue aceptado.")
            puntos = int(opcion["puntos"])
            saldo = int(cliente["saldo"]) + puntos
            cur.execute(
                """
                UPDATE fideliza_cliente
                SET saldo = %s, ultima_acreditacion_at = %s
                WHERE id = %s
                """,
                (saldo, momento, cliente["id"]),
            )
            cur.execute(
                """
                INSERT INTO fideliza_movimiento
                    (cliente_id, espera_id, tag_id, tipo, detalle, puntos, saldo_despues,
                     usuario, creado_at)
                VALUES (%s, %s, %s, 'acumulacion', %s, %s, %s, %s, %s)
                """,
                (
                    cliente["id"],
                    espera_id,
                    espera["tag_id"],
                    str(opcion["etiqueta"]),
                    puntos,
                    saldo,
                    usuario,
                    momento,
                ),
            )
            mov_id = cur.lastrowid
            aviso = _datos_aviso(cur, mov_id)
        conn.commit()
        return aviso
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def canjear(cliente_id: int, premio_id: int, usuario: str, tag_id: Optional[int] = None) -> dict:
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM fideliza_cliente WHERE id = %s FOR UPDATE",
                (cliente_id,),
            )
            cliente = cur.fetchone()
            if not cliente:
                raise FidelizaError("No encontramos la cuenta.")
            cur.execute(
                "SELECT * FROM fideliza_premio WHERE id = %s AND activo = 1",
                (premio_id,),
            )
            premio = cur.fetchone()
            if not premio:
                raise FidelizaError("Ese canje no está disponible.")
            costo = int(premio["puntos"])
            if int(cliente["saldo"]) < costo:
                raise FidelizaError("No alcanza el saldo para ese canje.")
            saldo = int(cliente["saldo"]) - costo
            cur.execute(
                "UPDATE fideliza_cliente SET saldo = %s WHERE id = %s",
                (saldo, cliente_id),
            )
            cur.execute(
                """
                INSERT INTO fideliza_movimiento
                    (cliente_id, tag_id, tipo, detalle, puntos, saldo_despues, usuario, creado_at)
                VALUES (%s, %s, 'canje', %s, %s, %s, %s, %s)
                """,
                (cliente_id, tag_id, premio["nombre"], -costo, saldo, usuario, momento),
            )
            aviso = _datos_aviso(cur, cur.lastrowid)
        conn.commit()
        return aviso
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def quitar_espera(espera_id: int) -> None:
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fideliza_espera
                SET estado = 'cancelada', cerrado_at = %s
                WHERE id = %s AND estado = 'esperando'
                """,
                (momento, espera_id),
            )
            if cur.rowcount != 1:
                raise FidelizaError("Esa espera ya no está activa.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def anular_movimiento(mov_id: int, usuario: str) -> dict:
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM fideliza_movimiento WHERE id = %s FOR UPDATE",
                (mov_id,),
            )
            original = cur.fetchone()
            if not original or original["tipo"] not in ("acumulacion", "canje"):
                raise FidelizaError("Ese movimiento no se puede anular.")
            cur.execute(
                "SELECT id FROM fideliza_movimiento WHERE anula_movimiento_id = %s",
                (mov_id,),
            )
            if cur.fetchone():
                raise FidelizaError("Ese movimiento ya fue anulado.")
            cur.execute(
                "SELECT * FROM fideliza_cliente WHERE id = %s FOR UPDATE",
                (original["cliente_id"],),
            )
            cliente = cur.fetchone()
            delta = -int(original["puntos"])
            saldo = int(cliente["saldo"]) + delta
            if saldo < 0:
                raise FidelizaError("Anular dejaría el saldo en negativo.")
            cur.execute(
                "UPDATE fideliza_cliente SET saldo = %s WHERE id = %s",
                (saldo, cliente["id"]),
            )
            if original["tipo"] == "acumulacion":
                cur.execute(
                    """
                    SELECT creado_at FROM fideliza_movimiento m
                    WHERE m.cliente_id = %s AND m.tipo = 'acumulacion' AND m.id <> %s
                      AND NOT EXISTS (
                        SELECT 1 FROM fideliza_movimiento a
                        WHERE a.anula_movimiento_id = m.id
                      )
                    ORDER BY m.creado_at DESC LIMIT 1
                    """,
                    (cliente["id"], mov_id),
                )
                previa = cur.fetchone()
                cur.execute(
                    "UPDATE fideliza_cliente SET ultima_acreditacion_at = %s WHERE id = %s",
                    (previa["creado_at"] if previa else None, cliente["id"]),
                )
            detalle = f"Anulación: {original['detalle']}"
            cur.execute(
                """
                INSERT INTO fideliza_movimiento
                    (cliente_id, tipo, detalle, puntos, saldo_despues, usuario,
                     anula_movimiento_id, creado_at)
                VALUES (%s, 'anulacion', %s, %s, %s, %s, %s, %s)
                """,
                (cliente["id"], detalle, delta, saldo, usuario, mov_id, momento),
            )
            aviso = _datos_aviso(cur, cur.lastrowid)
        conn.commit()
        return aviso
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def generar_codigo(cliente_id: int, usuario: str) -> str:
    momento = ahora()
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM fideliza_cliente WHERE id = %s", (cliente_id,))
            if not cur.fetchone():
                raise FidelizaError("No encontramos la cuenta.")
            cur.execute(
                """
                UPDATE fideliza_codigo
                SET usado_at = %s
                WHERE cliente_id = %s AND usado_at IS NULL
                """,
                (momento, cliente_id),
            )
            cur.execute(
                """
                INSERT INTO fideliza_codigo
                    (cliente_id, codigo, vence_at, creado_por, creado_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    cliente_id,
                    codigo,
                    momento + timedelta(minutes=CODIGO_MINUTOS),
                    usuario,
                    momento,
                ),
            )
        conn.commit()
        return codigo
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _bloqueado_recup(cur, rut: str, momento: datetime) -> bool:
    desde = momento - timedelta(minutes=VENTANA_INTENTOS_MIN)
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM fideliza_recup_intento
        WHERE rut = %s AND creado_at >= %s
        """,
        (rut, desde),
    )
    return int(cur.fetchone()["n"]) >= INTENTOS_RECUP


def validar_codigo(rut: str, codigo: str) -> dict:
    rut_n = normalizar_rut(rut)
    codigo_n = normalizar_codigo(codigo)
    if not rut_n or len(codigo_n) != 6:
        raise FidelizaError("RUT o código no válido.")
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if _bloqueado_recup(cur, rut_n, momento):
                raise FidelizaError("Demasiados intentos. Espera unos minutos.")
            cur.execute("SELECT * FROM fideliza_cliente WHERE rut = %s", (rut_n,))
            cliente = cur.fetchone()
            codigo_row = None
            if cliente:
                cur.execute(
                    """
                    SELECT * FROM fideliza_codigo
                    WHERE cliente_id = %s AND usado_at IS NULL AND vence_at > %s
                    ORDER BY id DESC LIMIT 1
                    """,
                    (cliente["id"], momento),
                )
                codigo_row = cur.fetchone()
            ok = bool(
                codigo_row and secrets.compare_digest(str(codigo_row["codigo"]), codigo_n)
            )
            if not ok:
                cur.execute(
                    "INSERT INTO fideliza_recup_intento (rut, creado_at) VALUES (%s, %s)",
                    (rut_n, momento),
                )
                conn.commit()
                raise FidelizaError("RUT o código no válido.")
            cur.execute(
                "UPDATE fideliza_codigo SET usado_at = %s WHERE id = %s",
                (momento, codigo_row["id"]),
            )
            cur.execute("SELECT * FROM fideliza_cliente WHERE id = %s", (cliente["id"],))
            cliente = cur.fetchone()
        conn.commit()
        return cliente
    except FidelizaError:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def exportar_clientes() -> list:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT nombre, rut, correo, saldo, acepta_puntos, acepta_publicidad,
                       acepta_at, creado_at
                FROM fideliza_cliente
                ORDER BY nombre
                """
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def exportar_movimientos(tag_id: Optional[int] = None) -> list:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT m.creado_at, t.nombre AS sucursal, c.nombre AS cliente, c.rut, c.correo,
                       m.tipo, m.detalle, m.puntos, m.saldo_despues, m.usuario, m.correo_ok
                FROM fideliza_movimiento m
                JOIN fideliza_cliente c ON c.id = m.cliente_id
                LEFT JOIN fideliza_tag t ON t.id = m.tag_id
            """
            params = []
            if tag_id:
                sql += " WHERE m.tag_id = %s"
                params.append(tag_id)
            sql += " ORDER BY m.creado_at, m.id"
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def buscar_clientes(q: str) -> list:
    asegurar_esquema()
    q = (q or "").strip()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if not q:
                cur.execute(
                    """
                    SELECT id, nombre, rut, correo, saldo, creado_at
                    FROM fideliza_cliente
                    ORDER BY creado_at DESC
                    LIMIT 80
                    """
                )
            else:
                like = f"%{q}%"
                rut = normalizar_rut(q) or q
                cur.execute(
                    """
                    SELECT id, nombre, rut, correo, saldo, creado_at
                    FROM fideliza_cliente
                    WHERE nombre LIKE %s OR correo LIKE %s OR rut LIKE %s OR rut = %s
                    ORDER BY nombre
                    LIMIT 80
                    """,
                    (like, like, like, rut),
                )
            return list(cur.fetchall())
    finally:
        conn.close()


def obtener_cliente(cliente_id: int) -> Optional[dict]:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM fideliza_cliente WHERE id = %s", (cliente_id,))
            return cur.fetchone()
    finally:
        conn.close()


def movimientos(cliente_id: int, tipo: str = "") -> list:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if tipo in ("acumulacion", "canje", "anulacion"):
                cur.execute(
                    """
                    SELECT * FROM fideliza_movimiento
                    WHERE cliente_id = %s AND tipo = %s
                    ORDER BY creado_at DESC, id DESC
                    LIMIT 200
                    """,
                    (cliente_id, tipo),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM fideliza_movimiento
                    WHERE cliente_id = %s
                    ORDER BY creado_at DESC, id DESC
                    LIMIT 200
                    """,
                    (cliente_id,),
                )
            filas = list(cur.fetchall())
            cur.execute(
                "SELECT anula_movimiento_id FROM fideliza_movimiento WHERE cliente_id = %s AND anula_movimiento_id IS NOT NULL",
                (cliente_id,),
            )
            anulados = {row["anula_movimiento_id"] for row in cur.fetchall()}
            for fila in filas:
                fila["ya_anulado"] = fila["id"] in anulados
            return filas
    finally:
        conn.close()


def actualizar_cliente(cliente_id: int, nombre: str, correo: str) -> None:
    nombre = (nombre or "").strip()
    correo_n = normalizar_correo(correo)
    if len(nombre) < 2:
        raise FidelizaError("Escribe el nombre.")
    if not correo_n:
        raise FidelizaError("El correo no es válido.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM fideliza_cliente WHERE correo = %s AND id <> %s",
                (correo_n, cliente_id),
            )
            if cur.fetchone():
                raise FidelizaError("Ese correo ya está en otra cuenta.")
            cur.execute("SELECT id FROM fideliza_cliente WHERE id = %s", (cliente_id,))
            if not cur.fetchone():
                raise FidelizaError("No encontramos la cuenta.")
            cur.execute(
                "UPDATE fideliza_cliente SET nombre = %s, correo = %s WHERE id = %s",
                (nombre, correo_n, cliente_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def listar_opciones() -> list:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM fideliza_opcion ORDER BY orden, id")
            return list(cur.fetchall())
    finally:
        conn.close()


def listar_premios() -> list:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM fideliza_premio ORDER BY orden, id")
            return list(cur.fetchall())
    finally:
        conn.close()


def listar_tags() -> list:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM fideliza_tag ORDER BY id")
            return list(cur.fetchall())
    finally:
        conn.close()


def leer_textos() -> dict:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT bases_puntos, bases_confidencialidad, etiqueta_puntos,
                       etiqueta_confidencialidad, correo_asunto, correo_html, correo_color
                FROM fideliza_config WHERE id = 1
                """
            )
            row = cur.fetchone() or {}
    finally:
        conn.close()
    return {
        "bases_puntos": row.get("bases_puntos"),
        "bases_confidencialidad": row.get("bases_confidencialidad"),
        "etiqueta_puntos": row.get("etiqueta_puntos"),
        "etiqueta_confidencialidad": row.get("etiqueta_confidencialidad"),
        "correo_asunto": row.get("correo_asunto"),
        "correo_html": row.get("correo_html"),
        "correo_color": row.get("correo_color"),
    }


def _guardar_columnas(valores: dict) -> None:
    permitidas = {
        "bases_puntos",
        "bases_confidencialidad",
        "etiqueta_puntos",
        "etiqueta_confidencialidad",
        "correo_asunto",
        "correo_html",
        "correo_color",
    }
    if not valores or any(clave not in permitidas for clave in valores):
        raise FidelizaError("No se pudo guardar.")
    asegurar_esquema()
    asignaciones = ", ".join(f"{clave} = %s" for clave in valores)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE fideliza_config SET {asignaciones} WHERE id = 1",
                list(valores.values()),
            )
        conn.commit()
    finally:
        conn.close()


def guardar_minutos(minutos: int) -> None:
    minutos = int(minutos)
    if not 1 <= minutos <= 1440:
        raise FidelizaError("La espera entre puntos debe estar entre 1 y 1440 minutos.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fideliza_config SET minutos_entre_puntos = %s WHERE id = 1",
                (minutos,),
            )
        conn.commit()
    finally:
        conn.close()


def guardar_opcion(opcion_id: int, etiqueta: str, puntos: int, orden: int, activo: bool) -> None:
    etiqueta = (etiqueta or "").strip()
    if not etiqueta or len(etiqueta) > 40:
        raise FidelizaError("La etiqueta del botón es obligatoria.")
    puntos = int(puntos)
    if puntos < 1 or puntos > 100000:
        raise FidelizaError("Los puntos del botón no son válidos.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fideliza_opcion
                SET etiqueta = %s, puntos = %s, orden = %s, activo = %s
                WHERE id = %s
                """,
                (etiqueta, puntos, int(orden), 1 if activo else 0, opcion_id),
            )
        conn.commit()
    finally:
        conn.close()


def crear_opcion(etiqueta: str, puntos: int) -> None:
    etiqueta = (etiqueta or "").strip()
    if not etiqueta:
        raise FidelizaError("Escribe la etiqueta del botón.")
    puntos = int(puntos)
    if puntos < 1:
        raise FidelizaError("Los puntos deben ser al menos 1.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(orden), 0) AS n FROM fideliza_opcion")
            orden = int(cur.fetchone()["n"]) + 1
            cur.execute(
                "INSERT INTO fideliza_opcion (etiqueta, puntos, orden, activo) VALUES (%s, %s, %s, 1)",
                (etiqueta, puntos, orden),
            )
        conn.commit()
    finally:
        conn.close()


def guardar_premio(premio_id: int, nombre: str, puntos: int, orden: int, activo: bool) -> None:
    nombre = (nombre or "").strip()
    if not nombre:
        raise FidelizaError("El premio necesita un nombre.")
    puntos = int(puntos)
    if puntos < 1:
        raise FidelizaError("El premio debe costar al menos 1 punto.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fideliza_premio
                SET nombre = %s, puntos = %s, orden = %s, activo = %s
                WHERE id = %s
                """,
                (nombre, puntos, int(orden), 1 if activo else 0, premio_id),
            )
        conn.commit()
    finally:
        conn.close()


def crear_premio(nombre: str, puntos: int) -> None:
    nombre = (nombre or "").strip()
    puntos = int(puntos)
    if not nombre or puntos < 1:
        raise FidelizaError("Indica nombre y puntos del premio.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(orden), 0) AS n FROM fideliza_premio")
            orden = int(cur.fetchone()["n"]) + 1
            cur.execute(
                "INSERT INTO fideliza_premio (nombre, puntos, orden, activo) VALUES (%s, %s, %s, 1)",
                (nombre, puntos, orden),
            )
        conn.commit()
    finally:
        conn.close()


def crear_sucursal(nombre: str) -> dict:
    nombre = (nombre or "").strip()
    if len(nombre) < 2 or len(nombre) > 100:
        raise FidelizaError("Escribe el nombre de la sucursal.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sucursal_id FROM Sucursales WHERE nombre_sucursal = %s",
                (nombre,),
            )
            if cur.fetchone():
                raise FidelizaError("Ya existe una sucursal con ese nombre.")
            cur.execute(
                "INSERT INTO Sucursales (nombre_sucursal) VALUES (%s)",
                (nombre,),
            )
            nuevo = {"sucursal_id": cur.lastrowid, "nombre_sucursal": nombre}
        conn.commit()
        return nuevo
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def listar_locales() -> list:
    """Las sucursales del sistema, con el sticker de fidelización si ya existe."""
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sucursal_id, nombre_sucursal FROM Sucursales ORDER BY nombre_sucursal"
            )
            locales = list(cur.fetchall())
            cur.execute("SELECT * FROM fideliza_tag")
            tags = {row["sucursal_id"]: row for row in cur.fetchall() if row.get("sucursal_id")}
        for local in locales:
            local["tag"] = tags.get(local["sucursal_id"])
        return locales
    finally:
        conn.close()


def obtener_tag_id(tag_id: int) -> Optional[dict]:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM fideliza_tag WHERE id = %s", (tag_id,))
            return cur.fetchone()
    finally:
        conn.close()


def tag_de_sucursal(sucursal_id) -> Optional[dict]:
    if not sucursal_id:
        return None
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM fideliza_tag WHERE sucursal_id = %s AND activo = 1",
                (sucursal_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def crear_tag_sucursal(sucursal_id: int) -> dict:
    momento = ahora()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sucursal_id, nombre_sucursal FROM Sucursales WHERE sucursal_id = %s",
                (sucursal_id,),
            )
            local = cur.fetchone()
            if not local:
                raise FidelizaError("Esa sucursal no existe.")
            cur.execute(
                "SELECT id FROM fideliza_tag WHERE sucursal_id = %s",
                (sucursal_id,),
            )
            if cur.fetchone():
                raise FidelizaError("Esa sucursal ya tiene sticker.")
            token = _token()
            cur.execute(
                """
                INSERT INTO fideliza_tag (token, nombre, sucursal_id, activo, creado_at)
                VALUES (%s, %s, %s, 1, %s)
                """,
                (token, local["nombre_sucursal"][:80], sucursal_id, momento),
            )
            cur.execute("SELECT * FROM fideliza_tag WHERE id = %s", (cur.lastrowid,))
            tag = cur.fetchone()
        conn.commit()
        return tag
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def movimientos_sucursal(tag_id: int) -> list:
    asegurar_esquema()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.*, c.nombre AS cliente
                FROM fideliza_movimiento m
                JOIN fideliza_cliente c ON c.id = m.cliente_id
                WHERE m.tag_id = %s
                ORDER BY m.creado_at DESC, m.id DESC
                LIMIT 80
                """,
                (tag_id,),
            )
            filas = list(cur.fetchall())
            emails = sorted({(f.get("usuario") or "") for f in filas if f.get("usuario")})
            nombres = {}
            if emails:
                marcas = ",".join(["%s"] * len(emails))
                cur.execute(
                    f"SELECT email, nombre FROM usuarios_huente WHERE email IN ({marcas})",
                    emails,
                )
                for row in cur.fetchall():
                    nombres[row["email"]] = (row.get("nombre") or "").strip() or row["email"]
            for fila in filas:
                fila["usuario_nombre"] = nombres.get(fila.get("usuario") or "", fila.get("usuario") or "—")
            return filas
    finally:
        conn.close()


def toggle_tag(tag_id: int, activo: bool) -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fideliza_tag SET activo = %s WHERE id = %s",
                (1 if activo else 0, tag_id),
            )
        conn.commit()
    finally:
        conn.close()
