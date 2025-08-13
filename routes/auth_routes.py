from flask import Blueprint, render_template, request, redirect, session, url_for
from supabase import create_client, Client
import os

# --- Configuración del Cliente Supabase ---
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

auth_bp = Blueprint('auth', __name__)

# La ruta /login AHORA muestra la página de inicio de sesión
@auth_bp.route("/")
@auth_bp.route("/login")
def login():
    if "usuario" in session:
        return redirect(url_for("dashboard.dashboard"))

    # Simplemente mostramos la plantilla HTML
    return render_template("login.html")

# NUEVA RUTA /google-login para iniciar el proceso con Google
@auth_bp.route("/google-login")
def google_login():
    # Esta es la lógica que antes estaba en /login
    data = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": url_for("auth.callback", _external=True)
        }
    })
    return redirect(data.url)

# La ruta /callback no necesita cambios
@auth_bp.route("/callback")
def callback():
    try:
        code = request.args.get("code")
        data = supabase.auth.exchange_code_for_session({ "auth_code": code })

        user = supabase.auth.get_user().user
        user_email = user.email

        response = supabase.table('usuarios_autorizados').select("email").eq("email", user_email).execute()

        if response.data:
            session.permanent = True
            session["usuario"] = user_email
            return redirect(url_for("dashboard.dashboard"))
        else:
            supabase.auth.sign_out()
            return "Acceso denegado. Tu correo no está autorizado para usar esta aplicación. contactar con soporte : carlos.carvajal@huentelauquen.cl", 403

    except Exception as e:
        return f"Ha ocurrido un error durante el inicio de sesión: {e}", 500

# La ruta /logout no necesita cambios
@auth_bp.route("/logout")
def logout():
    supabase.auth.sign_out()
    session.clear()
    return redirect(url_for("auth.login"))