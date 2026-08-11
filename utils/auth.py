from functools import wraps
import os

from werkzeug.security import check_password_hash
from flask import session, redirect, url_for, render_template, request

from utils.db import get_db_connection
from utils.permisos_catalogo import tiene_permiso_en_lista
from utils.roles_config import (
    cargar_config,
    guardar_permisos,
    obtener_permisos,
    pagina_inicio_para_rol,
)

# Compatibilidad con código que importa PERMISOS (siempre leer vía obtener_permisos())
PERMISOS = obtener_permisos()


def _allow_dev_login() -> bool:
    """Solo con ALLOW_DEV_LOGIN=1 en .env local. Nunca usar Host header."""
    return (os.environ.get("ALLOW_DEV_LOGIN") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def recargar_permisos():
    """Recarga permisos desde disco (tras guardar en Centro de Accesos)."""
    global PERMISOS
    cargar_config(forzar=True)
    PERMISOS = obtener_permisos()


def guardar_permisos_json(nuevos_permisos):
    ok, msg = guardar_permisos(nuevos_permisos)
    if ok:
        recargar_permisos()
    return ok, msg


def _permisos_del_rol(rol) -> list:
    return obtener_permisos().get(rol, [])


def tiene_permiso(rol, modulo):
    return tiene_permiso_en_lista(_permisos_del_rol(rol), modulo)


def tiene_seccion(rol, seccion_id: str) -> bool:
    """True si el rol tiene el permiso padre o algún hijo de esa sección del menú."""
    from utils.permisos_catalogo import hijos_de, permisos_expandidos

    permisos = _permisos_del_rol(rol)
    if "*" in permisos:
        return True
    expandido = permisos_expandidos(permisos)
    if seccion_id in expandido:
        return True
    return any(h in expandido for h in hijos_de(seccion_id))


def login_requerido(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        if "usuario" not in session and _allow_dev_login():
            session["usuario"] = "developer@local.test"
            session["rol"] = "superusuario"
            session["sucursal_id"] = None
            print("=====================================================================")
            print("== MODO DESARROLLO: Bypass de login (ALLOW_DEV_LOGIN=1).            ==")
            print("== Usuario simulado: developer@local.test (Superusuario)           ==")
            print("=====================================================================")

        if "usuario" not in session:
            return redirect(url_for("auth.login"))

        return f(*args, **kwargs)
    return decorado


def permiso_modulo(modulo):
    def wrapper(f):
        @wraps(f)
        def decorado(*args, **kwargs):
            if "usuario" not in session:
                return redirect(url_for("auth.login"))

            rol = session.get("rol", "invitado")

            if not tiene_permiso(rol, modulo):
                return render_template("403.html"), 403

            return f(*args, **kwargs)
        return decorado
    return wrapper


def obtener_ruta_inicio_rol(rol: str):
    """URL de inicio configurable por rol (roles_config.json)."""
    endpoint = pagina_inicio_para_rol(rol)
    try:
        return url_for(endpoint)
    except Exception:
        try:
            return url_for("dashboard.dashboard")
        except Exception:
            return url_for("auth.login")


def obtener_usuario_por_email(email: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM usuarios_huente WHERE email=%s",
                (email,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def autenticar_huente(email: str, password: str):
    user = obtener_usuario_por_email(email)
    if not user:
        return None
    if not user["activo"]:
        return None

    pwd_hash = user["password_hash"]
    if not pwd_hash:
        return None

    if check_password_hash(pwd_hash, password):
        return user

    return None


def crear_sesion_para_email(email: str):
    user = obtener_usuario_por_email(email)
    if not user:
        return None

    session.clear()
    session.permanent = True
    session["usuario"] = user["email"]
    session["rol"] = user["rol"]
    session["sucursal_id"] = user.get("sucursal_id")

    return user
