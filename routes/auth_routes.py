from flask import Blueprint, render_template, request, redirect, session, url_for
from utils.auth import autenticar_huente, crear_sesion_para_email, obtener_ruta_inicio_rol
from utils.logger import registrar_acceso

auth_bp = Blueprint('auth', __name__)


def obtener_ruta_inicio(rol):
    """Redirige según página de inicio configurada para el rol (Centro de Accesos)."""
    return obtener_ruta_inicio_rol(rol)

@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Si ya hay sesión activa, redirigir según su rol actual
    if "usuario" in session:
        return redirect(obtener_ruta_inicio(session.get("rol")))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = autenticar_huente(email, password)
        if user:
            # Cargar datos en sesión
            usuario_data = crear_sesion_para_email(email)
            rol = usuario_data.get("rol", "invitado")
            
            registrar_acceso(email, "OK", "Login Huente")
            
            # Redirección inteligente
            return redirect(obtener_ruta_inicio(rol))
        else:
            registrar_acceso(email or "desconocido", "ERROR", "Login Huente fallido")
            return render_template("login.html", error="Correo o contraseña incorrectos o usuario inactivo.")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))