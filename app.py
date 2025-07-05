
from flask import Flask
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.ventas_routes import ventas_bp




app = Flask(__name__)
app.secret_key = "clave_secreta_web"
app.register_blueprint(ventas_bp)

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)

import os

#WEB
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


#LOCAL
#if __name__ == "__main__":
 #   app.run(debug=True, port=5000)
