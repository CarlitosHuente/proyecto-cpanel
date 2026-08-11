
# Al principio de app.py
from dotenv import load_dotenv
load_dotenv() # Carga las variables del archivo .env

from flask import Flask, redirect, request, flash
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.ventas_routes import ventas_bp
from routes.seremi_routes import seremi_bp
from routes.config_routes import config_bp
from datetime import timedelta
from routes.contab_routes import contab_bp
from utils.sheet_cache import obtener_fecha_actualizacion
from utils.auth import tiene_permiso, tiene_seccion, login_requerido
from utils.secret_key import obtener_secret_key
from utils.safe_redirect import url_interna_segura
from routes.finanzas_routes import finanzas_bp
from routes.sucursales_routes import sucursales_bp
from routes.fabrica_routes import fabrica_bp
from routes.costeo_routes import costeo_bp
from routes.utilidades_routes import utilidades_bp
from routes.precios_routes import precios_bp
from routes.arqueo_caja_routes import arqueo_caja_bp
from routes.despacho_web_routes import despacho_web_bp
from routes.buk_routes import buk_bp
from routes.fabrica_papaya_routes import fabrica_papaya_bp
from routes.drive_prueba_routes import drive_prueba_bp
from routes.fxr_routes import fxr_bp
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

from utils.formato_dinero import dinero_presentacion, metrico_presentacion
from utils.formato_fecha import fecha_ddmmaaaa

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))
app.permanent_session_lifetime = timedelta(minutes=45) #Tiempo Maximo de inactividad.
app.secret_key = obtener_secret_key()

# Cookies de sesión: HttpOnly + SameSite=Lax siempre.
# Secure: apagado por defecto (local HTTP y deploy sin tocar cPanel).
# En HostChile con HTTPS conviene SESSION_COOKIE_SECURE=1 (opcional).
_secure_env = (os.environ.get("SESSION_COOKIE_SECURE") or "").strip().lower()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = _secure_env in ("1", "true", "yes", "on")

UPLOAD_FOLDER_CONTAB = os.path.join(BASE_DIR, "uploads", "contab")
# Crea la carpeta si no existe
os.makedirs(UPLOAD_FOLDER_CONTAB, exist_ok=True)

# Deja la ruta disponible para toda la app
app.config["UPLOAD_FOLDER_CONTAB"] = UPLOAD_FOLDER_CONTAB
# Guardar imagenes
UPLOAD_FOLDER_ANUNCIOS = os.path.join(BASE_DIR, "uploads", "anuncios")
os.makedirs(UPLOAD_FOLDER_ANUNCIOS, exist_ok=True)
app.config["UPLOAD_FOLDER_ANUNCIOS"] = UPLOAD_FOLDER_ANUNCIOS


@app.context_processor
def inyectar_fecha_actualizacion():
    return {
        "fecha_actualizacion": obtener_fecha_actualizacion("comercial")  # puedes cambiar por el que consideres principal
    }

app.register_blueprint(ventas_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(seremi_bp)
app.register_blueprint(contab_bp)
app.register_blueprint(config_bp)
app.register_blueprint(finanzas_bp)
app.register_blueprint(sucursales_bp)
app.register_blueprint(fabrica_bp)
app.register_blueprint(costeo_bp)
app.register_blueprint(utilidades_bp)
app.register_blueprint(precios_bp)
app.register_blueprint(arqueo_caja_bp)
app.register_blueprint(despacho_web_bp)
app.register_blueprint(buk_bp)
app.register_blueprint(fabrica_papaya_bp)
app.register_blueprint(drive_prueba_bp)
app.register_blueprint(fxr_bp)



## CArga de archivos
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads', 'contab')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER_CONTAB'] = UPLOAD_FOLDER


@app.before_request
def _sincronizar_permisos_desde_disco():
    """Evita menú desactualizado entre workers o tras guardar en Centro de Accesos."""
    from utils.auth import recargar_permisos
    from utils.roles_config import sincronizar_si_cambio

    if sincronizar_si_cambio():
        recargar_permisos()


@app.context_processor
def utility_processor():
    """Esto permite usar la función tiene_permiso dentro de los HTML"""
    return dict(tiene_permiso=tiene_permiso, tiene_seccion=tiene_seccion)


@app.template_filter("dinero")
def filtro_dinero(val):
    """Montos en pantalla sin decimales (pesos). Ver `utils/formato_dinero.py` y bitácora."""
    return dinero_presentacion(val)


@app.template_filter("metrico")
def filtro_metrico(val, decimales=2):
    """Kg, litros, etc.: máximo decimales (default 2). Ver bitácora sección K."""
    try:
        d = int(decimales)
    except (TypeError, ValueError):
        d = 2
    return metrico_presentacion(val, decimales=max(0, min(d, 6)))


@app.template_filter("ddmmaaaa")
def filtro_ddmmaaaa(val, con_hora=False):
    """Fecha DDMMAAAA (ej. 28052026). Ver `utils/formato_fecha.py`."""
    out = fecha_ddmmaaaa(val, con_hora=bool(con_hora))
    return out if out else "—"

@app.route("/refresh")
@login_requerido
def refresh_global():
    from utils.sheet_cache import refrescar_todo_el_cache
    refrescar_todo_el_cache()
    flash("✅ Datos actualizados con éxito", "success")
    destino = url_interna_segura(request.referrer, fallback="/")
    return redirect(destino)





#WEB
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


#LOCAL
#if __name__ == "__main__":
 #   app.run(debug=True, port=5000)
