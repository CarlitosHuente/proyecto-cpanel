from utils.db import get_db_connection
import os
import json
from functools import wraps
from utils.db import get_db_connection
from werkzeug.security import check_password_hash
from flask import session, redirect, url_for, render_template, request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERMISOS_FILE = os.path.join(BASE_DIR, 'permisos.json')

DEFAULT_PERMISOS = {
    "superusuario": ["*"], 
    "admin": ["dashboard", "ventas", "clientes", "seremi", "contab", "reporte","sucursales","productos","categorias", "agricola", "utilidades", "arqueo_caja"],
    "ventas": ["dashboard", "ventas", "clientes", "utilidades"],
    "seremi2":["seremi"],
    "seremi": ["sucursales","seremi","productos","categorias"],
    "contab": ["contab", "utilidades"],
    "sucursales":["sucursales","seremi"],
    "gerencia": ["reporte", "ventas", "utilidades"],
    "logistica":["sucursales","productos","categorias", "utilidades"],
    "invitado": []
}

PERMISOS = DEFAULT_PERMISOS.copy()

# Intentar cargar permisos personalizados desde el archivo JSON
if os.path.exists(PERMISOS_FILE):
    try:
        with open(PERMISOS_FILE, 'r', encoding='utf-8') as f:
            PERMISOS.update(json.load(f))
    except Exception as e:
        print(f"Error cargando permisos.json: {e}")

def guardar_permisos_json(nuevos_permisos):
    global PERMISOS
    PERMISOS.clear()
    PERMISOS.update(nuevos_permisos)
    try:
        with open(PERMISOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(PERMISOS, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando permisos: {e}")

def tiene_permiso(rol, modulo):
    permisos = PERMISOS.get(rol, [])
    if "*" in permisos:
        return True
    return modulo in permisos

# El antiguo código de verificar_usuario y cargar_usuarios ya no es necesario.
# Esta es la nueva versión del decorador.

def login_requerido(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        # --- INICIO DEL BYPASS DE DESARROLLO ---
        # Detectamos automáticamente si estás en local (localhost o 127.0.0.1)
        if ("localhost" in request.host or "127.0.0.1" in request.host) and "usuario" not in session:
            # Creamos una sesión falsa como superusuario para no pedir login
            session["usuario"] = "developer@local.test"
            session["rol"] = "superusuario"
            session["sucursal_id"] = None
            print("=====================================================================")
            print("== MODO DESARROLLO: Bypass de login activado automáticamente.      ==")
            print("== Usuario simulado: developer@local.test (Superusuario)           ==")
            print("=====================================================================")
        # --- FIN DEL BYPASS ---

        # Esta es la comprobación original que se ejecutará siempre.
        # En producción, el bypass no se activa y esta es la única protección.
        if "usuario" not in session:
            return redirect(url_for("auth.login"))

        return f(*args, **kwargs)
    return decorado



from functools import wraps
from flask import redirect, url_for, session

def permiso_modulo(modulo):
    def wrapper(f):
        @wraps(f)
        def decorado(*args, **kwargs):
            # Si no hay sesión, que actúe login_requerido primero
            if "usuario" not in session:
                return redirect(url_for("auth.login"))

            rol = session.get("rol", "invitado")

            if not tiene_permiso(rol, modulo):
                # NO redirigimos a dashboard ni a login
                # Mostramos una página 403 para cortar el bucle
                return render_template("403.html"), 403

            return f(*args, **kwargs)
        return decorado
    return wrapper




def obtener_usuario_por_email(email: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM usuarios_huente WHERE email=%s",
                (email,)
            )
            return cur.fetchone()
    finally:
        conn.close()

def autenticar_huente(email: str, password: str):
    """Valida login Huente (correo + contraseña)."""
    user = obtener_usuario_por_email(email)
    if not user:
        return None
    if not user["activo"]:
        return None

    pwd_hash = user["password_hash"]
    if not pwd_hash:
        # este usuario no tiene una clave asignada
        return None

    if check_password_hash(pwd_hash, password):
        return user

    return None


def crear_sesion_para_email(email: str):
    """Cargar datos del usuario desde DB y guardarlos en session."""
    user = obtener_usuario_por_email(email)
    if not user:
        return None

    session.clear()

    # Activa el tiempo de vida de la sesión (45 min) configurado en app.py
    session.permanent = True

    session["usuario"] = user["email"]
    session["rol"] = user["rol"]
    # Guardamos el ID de la sucursal (será un número o None)
    session["sucursal_id"] = user.get("sucursal_id")

    return user
