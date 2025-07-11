
from flask import Blueprint, render_template, request, redirect, session, url_for
from utils.auth import verificar_usuario
from utils.logger import registrar_acceso

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]
        ok, info = verificar_usuario(usuario, password)
        if ok:
            session.permanent = True
            session["usuario"] = info["usuario"]
            registrar_acceso(usuario, "EXITO", "acceso concedido")
            return redirect(url_for("dashboard.dashboard"))
        else:
            registrar_acceso(usuario, "ERROR", info)
            return render_template("login.html", error=info)
    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
