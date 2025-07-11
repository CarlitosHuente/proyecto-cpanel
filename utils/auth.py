
import pandas as pd
from functools import wraps
from flask import session, redirect, url_for

URL_USUARIOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQO_cJgPykLGJIqJF3qhhg7ztxYEtBhe52UJ-UJ433BsUXXP4tV0wk_qYrQ5uo9xB-YyCqi8eRdnVaM/pub?output=csv"

def cargar_usuarios():
    df = pd.read_csv(URL_USUARIOS)
    df.columns = df.columns.str.lower().str.strip()
    return df

def verificar_usuario(usuario, password):
    df = cargar_usuarios()
    encontrado = df[df['usuario'].str.lower().str.strip() == usuario.lower()]
    if encontrado.empty:
        return False, "Usuario no encontrado"
    fila = encontrado.iloc[0]
    if str(fila.get("activo", "")).strip().lower() not in ["true", "1"]:
        return False, "Usuario inactivo"
    if str(fila.get("password", "")).strip() != str(password).strip():
        return False, "Clave incorrecta"
    return True, {"usuario": fila["usuario"], "rol": fila.get("rol", "sin rol")}

def login_requerido(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorado

