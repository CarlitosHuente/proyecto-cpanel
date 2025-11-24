
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
from utils.sheet_cache import refrescar_todo_el_cache, obtener_fecha_actualizacion
from flask import redirect, request
import os

app = Flask(__name__)
app.permanent_session_lifetime = timedelta(minutes=10) #Tiempo Maximo de inactividad.


@app.context_processor
def inyectar_fecha_actualizacion():
    return {
        "fecha_actualizacion": obtener_fecha_actualizacion("comercial")  # puedes cambiar por el que consideres principal
    }

app.secret_key = "clave_secreta_web"
app.register_blueprint(ventas_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(seremi_bp)
app.register_blueprint(contab_bp)
app.register_blueprint(config_bp)



## CArga de archivos
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads', 'contab')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER_CONTAB'] = UPLOAD_FOLDER



@app.route("/refresh")
def refresh_global():
    from utils.sheet_cache import refrescar_todo_el_cache
    refrescar_todo_el_cache()
    flash("✅ Datos actualizados con éxito", "success")
    return redirect(request.referrer or "/")




#WEB
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


#LOCAL
#if __name__ == "__main__":
 #   app.run(debug=True, port=5000)
