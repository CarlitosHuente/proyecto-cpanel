from flask import Blueprint, render_template, request, redirect, session, url_for
from utils.auth import autenticar_huente, crear_sesion_para_email
from utils.logger import registrar_acceso

auth_bp = Blueprint('auth', __name__)

# --- Función Helper para decidir a dónde ir ---
def obtener_ruta_inicio(rol):
    """Devuelve la URL de destino según el rol del usuario."""
    if rol == "gerencia":
        return url_for("contab.dashboard_gestion")
    elif rol == "contab":
        return url_for("contab.dashboard_gestion")
    elif rol == "seremi":
        # Ajusta esto a la ruta principal de seremi que prefieras
        return url_for("seremi.temperatura_equipos") 
    elif rol == "ventas":
        return url_for("ventas.ventas")
    elif rol == "sucursales":
        return url_for("sucursales.pizarra")
    elif rol == "logistica":
        return url_for("sucursales.pizarra")
    elif rol == "invitado":
        return url_for("config.gestion_agricola")
    else:
        # admin, superusuario o rol desconocido van al dashboard principal
        return url_for("dashboard.dashboard")

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