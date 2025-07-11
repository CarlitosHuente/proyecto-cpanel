
from flask import Flask
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.ventas_routes import ventas_bp
from routes.seremi_routes import seremi_bp
from datetime import timedelta
from routes.contab_routes import contab_bp









app = Flask(__name__)
app.permanent_session_lifetime = timedelta(minutes=10) #Tiempo Maximo de inactividad.
app.secret_key = "clave_secreta_web"
app.register_blueprint(ventas_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(seremi_bp)
app.register_blueprint(contab_bp)

import os

## CArga de archivos
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads', 'contab')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER_CONTAB'] = UPLOAD_FOLDER


#WEB
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


#LOCAL
#if __name__ == "__main__":
 #   app.run(debug=True, port=5000)
