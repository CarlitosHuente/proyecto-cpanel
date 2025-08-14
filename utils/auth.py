import os
from flask import session, redirect, url_for
from functools import wraps

# El antiguo código de verificar_usuario y cargar_usuarios ya no es necesario.
# Esta es la nueva versión del decorador.

def login_requerido(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        # --- INICIO DEL BYPASS DE DESARROLLO ---
        # Verificamos si la variable de entorno está en modo "development"
        # y si no hay un usuario en la sesión.
        if os.environ.get("FLASK_ENV") == "development" and "usuario" not in session:
            # Si se cumplen las condiciones, creamos una sesión falsa para el desarrollador.
            session["usuario"] = "developer@local.test"
            print("=====================================================================")
            print("== MODO DESARROLLO: Bypass de login activado.                        ==")
            print("== Usuario simulado: developer@local.test                            ==")
            print("=====================================================================")
        # --- FIN DEL BYPASS ---

        # Esta es la comprobación original que se ejecutará siempre.
        # En producción, el bypass no se activa y esta es la única protección.
        if "usuario" not in session:
            return redirect(url_for("auth.login"))

        return f(*args, **kwargs)
    return decorado

