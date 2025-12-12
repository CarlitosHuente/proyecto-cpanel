from flask import Blueprint, render_template, request, redirect, session, url_for
from supabase import create_client, Client
import os
from utils.auth import autenticar_huente, crear_sesion_para_email
from utils.logger import registrar_acceso

# --- Configuración del Cliente Supabase ---
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

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
    else:
        # admin, superusuario o rol desconocido van al dashboard principal
        return url_for("dashboard.dashboard")

@auth_bp.route("/")
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


@auth_bp.route("/google-login")
def google_login():
    data = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": url_for("auth.callback", _external=True)
        }
    })
    return redirect(data.url)


@auth_bp.route("/callback")
def callback():
    try:
        code = request.args.get("code")
        supabase.auth.exchange_code_for_session({"auth_code": code})

        user = supabase.auth.get_user().user
        user_email = user.email

        usuario_local = crear_sesion_para_email(user_email)

        if not usuario_local:
            supabase.auth.sign_out()
            registrar_acceso(user_email, "DENEGADO", "Login Google OK pero correo no existe en usuarios_huente")
            return (
                "Acceso denegado. Tu correo no está autorizado para usar esta aplicación. "
                "Contactar con soporte.",
                403,
            )

        rol = usuario_local.get("rol", "invitado")
        registrar_acceso(user_email, "OK", "Login Google")
        
        # Redirección inteligente
        return redirect(obtener_ruta_inicio(rol))

    except Exception as e:
        registrar_acceso("desconocido", "ERROR", f"Error en callback Google: {e}")
        return f"Ha ocurrido un error durante el inicio de sesión: {e}", 500


@auth_bp.route("/logout")
def logout():
    supabase.auth.sign_out()
    session.clear()
    return redirect(url_for("auth.login"))