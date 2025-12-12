from utils.db import get_db_connection
import os
from functools import wraps
from utils.db import get_db_connection
from werkzeug.security import check_password_hash
from flask import session, redirect, url_for, render_template



PERMISOS = {
    "superusuario": ["*"], 
    "admin": ["dashboard", "ventas", "clientes", "seremi", "contab", "reporte"],
    "ventas": ["dashboard", "ventas", "clientes"],
    "seremi": ["seremi"],
    "contab": ["contab"],
    "gerencia": ["reporte", "ventas"],
    "invitado": []
}

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
        # Verificamos si la variable de entorno está en modo "development"
        # y si no hay un usuario en la sesión.
        # # if os.environ.get("FLASK_ENV") == "development" and "usuario" not in session:
        # #     # Si se cumplen las condiciones, creamos una sesión falsa para el desarrollador.
        # #     session["usuario"] = "developer@local.test"
        # #     print("=====================================================================")
        # #     print("== MODO DESARROLLO: Bypass de login activado.                        ==")
        # #     print("== Usuario simulado: developer@local.test                            ==")
        # #     print("=====================================================================")
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
    session["usuario"] = user["email"]
    session["rol"] = user["rol"]

    return user
