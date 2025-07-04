
from flask import Blueprint, render_template, session, redirect, url_for

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        return redirect(url_for("auth.login"))
    return render_template("dashboard.html", usuario=session["usuario"])

from flask import redirect, request
from utils.sheet_cache import forzar_actualizacion

@dashboard_bp.route("/refresh")
def refrescar_datos():
    empresa = request.args.get("empresa", "comercial")
    forzar_actualizacion(empresa)
    return redirect(request.referrer or url_for("dashboard.dashboard"))

