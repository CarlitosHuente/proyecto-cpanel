
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "clave_secreta_123"

USUARIOS = {"admin": "1234"}

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        clave = request.form["clave"]
        if USUARIOS.get(usuario) == clave:
            session["usuario"] = usuario
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Credenciales incorrectas")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", usuario=session["usuario"])

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
