# routes/contab_routes.py

import os
from flask import Blueprint, render_template, request, redirect, url_for, send_from_directory, flash, current_app
from utils.auth import login_requerido
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

contab_bp = Blueprint("contab", __name__, url_prefix="/contab")

# ID de carpeta "contabilidad" en tu Google Drive
CARPETA_ID = "1zFjARS82JAuay19WxxgepBl7jYylgPIn"

# Función para subir archivo a Drive
def subir_archivo_a_drive(ruta_archivo, nombre_archivo, carpeta_id):
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    SERVICE_ACCOUNT_FILE = '/etc/secrets/render-huentelauquen-a209ea4553b1.json'

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    service = build('drive', 'v3', credentials=creds)

    file_metadata = {
        'name': nombre_archivo,
        'parents': [carpeta_id]
    }
    media = MediaFileUpload(
        ruta_archivo,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    archivo = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()

    return archivo.get('id')

# Comparativo (futuro)
@contab_bp.route("/comparativo")
@login_requerido
def comparativo():
    return render_template("contab/comparativo.html")

# Página de archivos
@contab_bp.route("/archivos", methods=["GET", "POST"])
@login_requerido
def archivos():
    ruta = current_app.config['UPLOAD_FOLDER_CONTAB']
    nombre_mayor = "mayor.xlsx"
    path_mayor = os.path.join(ruta, nombre_mayor)

    if request.method == "POST":
        archivo = request.files.get("archivo_excel")
        if archivo and archivo.filename.endswith(".xlsx"):
            archivo.save(path_mayor)

            try:
                subir_archivo_a_drive(path_mayor, nombre_mayor, CARPETA_ID)
                flash("Archivo cargado y subido a Drive correctamente.", "success")
            except Exception as e:
                flash(f"Error al subir a Drive: {e}", "danger")
        else:
            flash("Error: solo se aceptan archivos .xlsx", "danger")

    existe_mayor = os.path.exists(path_mayor)
    return render_template("contab/archivos.html", existe_mayor=existe_mayor)

# Descargar
@contab_bp.route("/descargar_mayor")
@login_requerido
def descargar_mayor():
    ruta = current_app.config['UPLOAD_FOLDER_CONTAB']
    return send_from_directory(ruta, "mayor.xlsx", as_attachment=True)

# Eliminar
@contab_bp.route("/eliminar_mayor")
@login_requerido
def eliminar_mayor():
    ruta = current_app.config['UPLOAD_FOLDER_CONTAB']
    try:
        os.remove(os.path.join(ruta, "mayor.xlsx"))
        flash("Archivo mayor eliminado correctamente.", "warning")
    except:
        flash("No se pudo eliminar el archivo.", "danger")
    return redirect(url_for("contab.archivos"))
