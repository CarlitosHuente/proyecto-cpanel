from flask import Blueprint, render_template, request, redirect, session, url_for
from utils.auth import autenticar_huente, crear_sesion_para_email, obtener_ruta_inicio_rol
from utils.logger import registrar_acceso
from utils.login_rate_limit import (
    login_bloqueado,
    registrar_login_fallido,
    registrar_login_ok,
)

auth_bp = Blueprint('auth', __name__)


def obtener_ruta_inicio(rol):
    """Redirige según página de inicio configurada para el rol (Centro de Accesos)."""
    return obtener_ruta_inicio_rol(rol)


def _client_ip() -> str:
    # Si el hosting envía X-Forwarded-For, usar el primero (cliente).
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "")


@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Si ya hay sesión activa, redirigir según su rol actual
    if "usuario" in session:
        return redirect(obtener_ruta_inicio(session.get("rol")))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        ip = _client_ip()

        bloqueado, msg_bloqueado = login_bloqueado(ip, email)
        if bloqueado:
            registrar_acceso(email or "desconocido", "ERROR", "Login bloqueado rate-limit")
            return render_template("login.html", error=msg_bloqueado), 429

        user = autenticar_huente(email, password)
        if user:
            usuario_data = crear_sesion_para_email(email)
            rol = usuario_data.get("rol", "invitado")
            registrar_login_ok(ip, email)
            registrar_acceso(email, "OK", "Login Huente")
            return redirect(obtener_ruta_inicio(rol))

        registrar_login_fallido(ip, email)
        registrar_acceso(email or "desconocido", "ERROR", "Login Huente fallido")
        return render_template("login.html", error="Correo o contraseña incorrectos o usuario inactivo.")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))