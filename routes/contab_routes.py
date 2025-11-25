import os
import base64
import requests
from flask import Blueprint, render_template, request, redirect, url_for, send_from_directory, flash, current_app
from utils.auth import login_requerido
from flask import request, render_template
from utils.sheet_cache import obtener_datos
from utils.auth import login_requerido, permiso_modulo
import pandas as pd
from datetime import datetime
import json


contab_bp = Blueprint("contab", __name__, url_prefix="/contab")

COMENTARIOS_FILE_NAME = "comentarios_comparativo.json"

def _ruta_comentarios():
    # Usa la misma carpeta donde guardas mayor.xlsx
    return os.path.join(current_app.config['UPLOAD_FOLDER_CONTAB'], COMENTARIOS_FILE_NAME)

def cargar_comentarios():
    ruta = _ruta_comentarios()
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_comentarios(datos: dict):
    ruta = _ruta_comentarios()
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)



# URL del webhook de Google Apps Script
URL_WEBHOOK_SCRIPT = "https://script.google.com/macros/s/AKfycbxUK2SQ_fDaX1wEcTDLfnefcZPCZDp3A5rrqd2gZ6KBHV7qbBuysYTXltBBLXraNGj7/exec"


# Función que envía el archivo al Apps Script
def enviar_archivo_a_script(path_archivo):
    with open(path_archivo, "rb") as f:
        archivo_base64 = base64.b64encode(f.read()).decode("utf-8")
    try:
        response = requests.post(URL_WEBHOOK_SCRIPT, data=archivo_base64)
        return response.text
    except Exception as e:
        return f"ERROR: {e}"

# Ruta Comparativo (vacía por ahora)
from datetime import datetime  # Asegúrate de tener esto arriba

@contab_bp.route("/comparativo")
@login_requerido
@permiso_modulo("admin")
def comparativo():
    from datetime import datetime

    # Parámetros GET
    fecha_corte = request.args.get("fecha_corte")
    clasif = request.args.get("clasificacion", "Todas")
    centro_costo = request.args.get("centro_costo", "Todos")
    modo = request.args.get("modo", "normal")  # "normal" o "alertas"

    # Cargar datos
    df = obtener_datos("mayor")

    # Excluir conceptos contables no deseados
    excluir = [
        "COMPROBANTE DE APERTURA",
        "COMPROBANTE DE CIERRE",
        "COMPROBANTE DE REGULARIZACIÓN"
    ]
    df["CONCEPTO"] = df["CONCEPTO"].astype(str).str.upper()
    df = df[~df["CONCEPTO"].isin(excluir)]

    # Capturar todos los centros de costo antes de filtrar
    todos_centros = sorted(df["CENTRO COSTO"].astype(str).str.strip().unique().tolist())

    # Aplicar filtro por centro de costo
    if centro_costo != "Todos":
        df = df[df["CENTRO COSTO"].astype(str).str.strip().str.upper() == centro_costo.upper()]

    # Filtro por fecha de corte
    if fecha_corte:
        corte = pd.to_datetime(fecha_corte)
        df = df[df["FECHA"] <= corte]

    # Clasificación contable
    df["CUENTA"] = df["CUENTA"].astype(str)
    df["CLASIFICACION"] = df["CUENTA"].str[0].map({
        "3": "Gastos",
        "4": "Ingresos"
    }).fillna("Otros")

    if clasif != "Todas":
        df = df[df["CLASIFICACION"] == clasif]

    # PERIODO ordenado y legible
    df["PERIODO_DT"] = df["FECHA"].apply(lambda x: datetime(x.year, x.month, 1))
    ultimos_12_dt = sorted(df["PERIODO_DT"].unique())[-12:]
    meses_es = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", 
                "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    etiquetas = [f"{meses_es[d.month - 1]}-{d.year}" for d in ultimos_12_dt]
    df["PERIODO"] = df["PERIODO_DT"].map(dict(zip(ultimos_12_dt, etiquetas)))

    # Tabla dinámica
    pivot_raw = (
        df[df["PERIODO"].isin(etiquetas)]
        .groupby(["NOMBRE", "PERIODO"])
        .agg(DEBE=("DEBE", "sum"), HABER=("HABER", "sum"))
        .reset_index()
    )
    pivot_raw["SALDO"] = pivot_raw["DEBE"] - pivot_raw["HABER"]

    pivot = (
        pivot_raw.pivot(index="NOMBRE", columns="PERIODO", values="SALDO")
        .reindex(columns=etiquetas, fill_value=0)
        .reset_index()
    )
    
    # Adjuntar CUENTA y CLASIFICACION para ordenar
    datos_aux = df[["NOMBRE", "CUENTA", "CLASIFICACION"]].drop_duplicates()
    pivot = pd.merge(datos_aux, pivot, on="NOMBRE", how="right")
    pivot = pivot.sort_values("CUENTA")


    # Cálculo de ratios para "modo alertas"
    # pivot tiene columnas: NOMBRE, CUENTA, CLASIFICACION, <meses>
    # --- ALERTAS POR CENTRO DE COSTO ---
    # detalle_raw: NOMBRE, CENTRO COSTO, PERIODO, SALDO_MES
    detalle_raw = (
        df[df["PERIODO"].isin(etiquetas)]
        .assign(SALDO_MES=lambda x: x["DEBE"] - x["HABER"])
        .groupby(["NOMBRE", "CENTRO COSTO", "PERIODO"], as_index=False)
        .agg(SALDO_MES=("SALDO_MES", "sum"))
    )

    # Pivot por centro de costo
    pivot_cc = detalle_raw.pivot_table(
        index=["NOMBRE", "CENTRO COSTO"],
        columns="PERIODO",
        values="SALDO_MES",
        aggfunc="sum",
    ).reset_index()

    # Ratios por centro de costo
    ratios_cc = {}          # clave: NOMBRE||CENTRO||PERIODO  → ratio
    alertas_macro = {}      # clave: NOMBRE||PERIODO → cantidad de CC con alerta

    if not pivot_cc.empty:
        valores_cc = pivot_cc[etiquetas].replace(0, pd.NA)
        promedios_cc = valores_cc.mean(axis=1, skipna=True)

        for idx, row in pivot_cc.iterrows():
            nombre = row["NOMBRE"]
            centro = row["CENTRO COSTO"]
            prom = promedios_cc.iloc[idx]
            if pd.isna(prom) or prom == 0:
                continue

            for periodo in etiquetas:
                val = row[periodo]
                if pd.isna(val) or val == 0:
                    continue
                ratio = float(val / prom)
                if ratio >= 1.3:
                    key_cc = f"{nombre}||{centro}||{periodo}"
                    ratios_cc[key_cc] = ratio

                    key_macro = f"{nombre}||{periodo}"
                    alertas_macro[key_macro] = alertas_macro.get(key_macro, 0) + 1


    # Columnas visuales
    columnas = ["NOMBRE"] + etiquetas
    final = pivot[columnas]

    # Adjuntar centro de costo sin reindex (robusto)
    centros_df = df[["NOMBRE", "CENTRO COSTO"]].drop_duplicates(subset=["NOMBRE"])
    final = pd.merge(final, centros_df, on="NOMBRE", how="left")

    # Agrupar por centro de costo
    detalle_raw = (
        df[df["PERIODO"].isin(etiquetas)]
        .groupby(["NOMBRE", "CENTRO COSTO", "PERIODO"])
        .agg(DEBE=("DEBE", "sum"), HABER=("HABER", "sum"))
        .reset_index()
    )
    detalle_raw["SALDO"] = detalle_raw["DEBE"] - detalle_raw["HABER"]

    # Pivot por centro de costo
    detalle = detalle_raw.pivot_table(
        index=["NOMBRE", "CENTRO COSTO"],
        columns="PERIODO",
        values="SALDO",
        fill_value=0
    ).reset_index()

    # Comentarios persistentes (para alertas y vista ejecutiva)
    comentarios = cargar_comentarios()


    # Preparar formato para JS o HTML
    detalle_dict = detalle.to_dict(orient="records")

    return render_template(
        "contab/comparativo.html",
        tabla=final.to_dict(orient="records"),
        columnas=columnas,
        fecha_corte=fecha_corte,
        clasificacion=clasif,
        centro_costo=centro_costo,
        centros=todos_centros,
        detalle=detalle_dict,
        modo=modo,
        alertas_macro=alertas_macro,
        ratios_cc=ratios_cc,
        comentarios=comentarios,
    )


from flask import send_file
import tempfile

@contab_bp.route("/descargar_detalle")
@login_requerido
@permiso_modulo("admin")
def descargar_detalle():
    fecha_corte = request.args.get("fecha_corte")
    clasif = request.args.get("clasificacion", "Todas")
    centro_costo = request.args.get("centro_costo", "Todos")

    df = obtener_datos("mayor")

    excluir = [
        "COMPROBANTE DE APERTURA",
        "COMPROBANTE DE CIERRE",
        "COMPROBANTE DE REGULARIZACIÓN"
    ]
    df["CONCEPTO"] = df["CONCEPTO"].astype(str).str.upper()
    df = df[~df["CONCEPTO"].isin(excluir)]

    # Filtros
    if fecha_corte:
        corte = pd.to_datetime(fecha_corte)
        df = df[df["FECHA"] <= corte]

    if centro_costo != "Todos":
        df = df[df["CENTRO COSTO"].astype(str).str.strip().str.upper() == centro_costo.upper()]

    df["CUENTA"] = df["CUENTA"].astype(str)
    df["CLASIFICACION"] = df["CUENTA"].str[0].map({
        "1": "Activo",
        "2": "Pasivo",
        "3": "Gastos",
        "4": "Ingresos"
    }).fillna("Otros")

    if clasif != "Todas":
        df = df[df["CLASIFICACION"] == clasif]

    # Guardar temporal y enviar
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        df.to_excel(tmp.name, index=False)
        return send_file(tmp.name, as_attachment=True, download_name="detalle_contable.xlsx")




# Página de carga y visualización
@contab_bp.route("/archivos", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("admin")
def archivos():
    ruta = current_app.config['UPLOAD_FOLDER_CONTAB']
    nombre_mayor = "mayor.xlsx"
    path_mayor = os.path.join(ruta, nombre_mayor)

    if request.method == "POST":
        archivo = request.files.get("archivo_excel")
        if archivo and archivo.filename.endswith(".xlsx"):
            archivo.save(path_mayor)

            resultado = enviar_archivo_a_script(path_mayor)
            if "ERROR" in resultado.upper():
                flash(f"Error al subir a Google Drive: {resultado}", "danger")
            else:
                flash("Archivo cargado y subido a Google Drive correctamente.", "success")
        else:
            flash("Error: solo se aceptan archivos .xlsx", "danger")

    existe_mayor = os.path.exists(path_mayor)
    return render_template("contab/archivos.html", existe_mayor=existe_mayor)


@contab_bp.route("/guardar_comentario", methods=["POST"])
@login_requerido
def guardar_comentario_api():
    data = request.get_json() or {}
    nombre = (data.get("nombre") or "").strip()
    periodo = (data.get("periodo") or "").strip()
    centro = (data.get("centro_costo") or "").strip()
    comentario = (data.get("comentario") or "").strip()

    if not nombre or not periodo or not centro:
        return {"ok": False, "error": "Faltan datos"}, 400

    comentarios = cargar_comentarios()
    key = f"{nombre}||{centro}||{periodo}"

    if comentario:
        comentarios[key] = comentario
    else:
        comentarios.pop(key, None)

    guardar_comentarios(comentarios)
    return {"ok": True}

# Descargar archivo local
@contab_bp.route("/descargar_mayor")
@login_requerido
@permiso_modulo("admin")
def descargar_mayor():
    ruta = current_app.config['UPLOAD_FOLDER_CONTAB']
    return send_from_directory(ruta, "mayor.xlsx", as_attachment=True)

# Eliminar archivo local
@contab_bp.route("/eliminar_mayor")
@login_requerido
@permiso_modulo("admin")
def eliminar_mayor():
    ruta = current_app.config['UPLOAD_FOLDER_CONTAB']
    try:
        os.remove(os.path.join(ruta, "mayor.xlsx"))
        flash("Archivo mayor eliminado correctamente.", "warning")
    except:
        flash("No se pudo eliminar el archivo.", "danger")
    return redirect(url_for("contab.archivos"))
