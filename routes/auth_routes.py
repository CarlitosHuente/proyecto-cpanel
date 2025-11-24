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

# La ruta /login AHORA muestra la página de inicio de sesión
@auth_bp.route("/")
@auth_bp.route("/login")
@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Si ya hay sesión activa, manda directo al dashboard
    if "usuario" in session:
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = autenticar_huente(email, password)
        if user:
            crear_sesion_para_email(email)
            registrar_acceso(email, "OK", "Login Huente")
            return redirect(url_for("dashboard.dashboard"))
        else:
            registrar_acceso(email or "desconocido", "ERROR", "Login Huente fallido")
            # Volvemos a mostrar el login con mensaje de error simple
            return render_template("login.html", error="Correo o contraseña incorrectos o usuario inactivo.")

    # GET → solo mostramos la página de login
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
        supabase.auth.exchange_code_for_session({"auth_code": code})

        user = supabase.auth.get_user().user
        user_email = user.email

        # Usamos la misma lógica que Login Huente:
        # leer usuario y rol desde usuarios_huente
        usuario_local = crear_sesion_para_email(user_email)

        if not usuario_local:
            supabase.auth.sign_out()
            registrar_acceso(
                user_email,
                "DENEGADO",
                "Login Google OK pero correo no existe en usuarios_huente"
            )
            return (
                "Acceso denegado. Tu correo no está autorizado para usar esta aplicación. "
                "Contactar con soporte: carlos.carvajal@huentelauquen.cl",
                403,
            )

        # Si llegó aquí, ya dejó en session["usuario"] y session["rol"]
        registrar_acceso(user_email, "OK", "Login Google")
        return redirect(url_for("dashboard.dashboard"))

    except Exception as e:
        registrar_acceso("desconocido", "ERROR", f"Error en callback Google: {e}")
        return f"Ha ocurrido un error durante el inicio de sesión: {e}", 500


# La ruta /logout no necesita cambios
@auth_bp.route("/logout")
def logout():
    supabase.auth.sign_out()
    session.clear()
    return redirect(url_for("auth.login"))