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

PRORRATEOS_FILENAME = "prorrateos.json"

CLASIFICACIONES_FILENAME = "clasificaciones.json"

def _ruta_clasificaciones():
    """Ruta del archivo de clasificaciones de cuentas."""
    ruta = current_app.config["UPLOAD_FOLDER_CONTAB"]
    os.makedirs(ruta, exist_ok=True)
    return os.path.join(ruta, CLASIFICACIONES_FILENAME)


def _ruta_prorrateos():
    """Devuelve la ruta completa del archivo prorrateos.json en la carpeta contab."""
    ruta = current_app.config["UPLOAD_FOLDER_CONTAB"]
    os.makedirs(ruta, exist_ok=True)
    return os.path.join(ruta, PRORRATEOS_FILENAME)


def cargar_prorrateos():
    """Carga el JSON de prorrateos; si no existe, devuelve estructura base."""
    ruta = _ruta_prorrateos()
    if not os.path.exists(ruta):
        return {"config_cuentas": {}, "reglas_mensuales": {}}
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_prorrateos(data):
    """Guarda el JSON de prorrateos con indentación bonita."""
    ruta = _ruta_prorrateos()
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
def cargar_clasificaciones():
    """Carga la estructura de clasificación."""
    ruta = _ruta_clasificaciones()
    if not os.path.exists(ruta):
        # Estructura base inicial vacía
        return {"grupos": []}
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_clasificaciones(data):
    ruta = _ruta_clasificaciones()
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Cuentas base con prorrateo (se pueden ampliar desde el front)
DEFAULT_CONFIG_CUENTAS = {
    "Costo Venta": "VENTAS_SUCURSAL",
    "Gastos Venta Empanadas": "VENTAS_SUCURSAL",
    "Gasto de Envases": "VENTAS_SUCURSAL",
    "Comision Uber Eats": "MANUAL_SUCURSAL",
    "Comision Mesa Chilena": "MANUAL_SUCURSAL",
    "Comision Mercado Pago": "MANUAL_SUCURSAL",
    "Comision Rappi": "MANUAL_SUCURSAL",
    "Comision Pedidos Ya": "MANUAL_SUCURSAL",
}


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

@contab_bp.route("/prorrateos")
@login_requerido
def prorrateos():
    """
    Vista principal de prorrateos contables:
    - Tab 'cc'       : Servicios Generales -> distribución por centro de costo
    - Tab 'cuentas'  : Cuentas globales (VENTAS_SUCURSAL / MANUAL_SUCURSAL)
    - Tab 'fabrica'  : Fábrica Empanadas (costeo básico + Costanera -> Fábrica estimado)
    """
    # Periodo en formato YYYY-MM
    periodo = request.args.get("periodo")
    if not periodo:
        periodo = datetime.now().strftime("%Y-%m")

    pestaña = request.args.get("tab", "cc")

    # 1. Cargar configuración JSON
    data = cargar_prorrateos()
    config_cuentas = data.setdefault("config_cuentas", {})
    reglas_mensuales = data.setdefault("reglas_mensuales", {})

    # Defaults
    for nombre, tipo in DEFAULT_CONFIG_CUENTAS.items():
        if nombre not in config_cuentas:
            config_cuentas[nombre] = {"tipo": tipo, "activo": True}

    # Reglas del periodo
    reglas_periodo = reglas_mensuales.get(periodo, {})
    reglas_serv_generales = reglas_periodo.get("serv_generales", {})
    reglas_cuentas = reglas_periodo.get("cuentas_globales", {})

    # Config Fábrica
    fabrica_cfg = data.setdefault("fabrica_empanadas", {})
    costeo_periodos = fabrica_cfg.setdefault("costeo_periodos", {})
    costanera_prorrateos = fabrica_cfg.setdefault("costanera_prorrateos", {})

    costeo_periodo = costeo_periodos.get(periodo, {})
    empanadas_elaboradas = costeo_periodo.get("empanadas_elaboradas", 0)
    empanadas_compradas = costeo_periodo.get("empanadas_compradas", 0)
    prorrateo_costanera_periodo = costanera_prorrateos.get(periodo, {})

    # Estructuras de salida
    cuentas_serv_generales = []
    centros_disponibles = []
    cuentas_prorrateo = []
    ventas_totales = 0.0
    ventas_por_cc = {}
    gastos_fabrica = []
    total_gastos_fabrica = 0.0
    costo_unitario_empanada = 0.0
    gastos_costanera_compartidos = []
    total_costanera_origen = 0.0
    total_costanera_a_fabrica = 0.0
    costo_unitario_empanada_estimado = 0.0
    
    # Lista para autocompletar en el modal (NUEVO)
    todas_las_cuentas = []

    # Lista de configuración de cuentas
    lista_config_cuentas = []
    for nombre, cfg in sorted(config_cuentas.items(), key=lambda x: x[0].lower()):
        lista_config_cuentas.append({
            "nombre": nombre,
            "tipo": cfg.get("tipo", ""),
            "activo": bool(cfg.get("activo", True)),
        })

    # 2. Cargar datos del Mayor
    df = obtener_datos("mayor")

    if not df.empty:
        # --- NUEVO: Obtener lista de todas las cuentas de gasto para el modal ---
        # Filtramos cuentas que empiezan con 3 (Gasto) para sugerir
        df["CUENTA_STR"] = df["CUENTA"].astype(str)
        mask_gastos = df["CUENTA_STR"].str.startswith("3")
        todas_las_cuentas = sorted(df[mask_gastos]["NOMBRE"].dropna().unique().tolist())
        # -----------------------------------------------------------------------

        df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
        year, month = map(int, periodo.split("-"))
        df_mes = df[(df["FECHA"].dt.year == year) & (df["FECHA"].dt.month == month)].copy()

        if not df_mes.empty:
            for col in ["DEBE", "HABER"]:
                df_mes[col] = pd.to_numeric(df_mes[col], errors="coerce").fillna(0)
            df_mes["SALDO"] = df_mes["DEBE"] - df_mes["HABER"]
            df_mes["CENTRO COSTO"] = df_mes["CENTRO COSTO"].astype(str)
            df_mes["CUENTA"] = df_mes["CUENTA"].astype(str)

            # Ventas
            df_ventas = df_mes[df_mes["CUENTA"].str.startswith("41")].copy()
            if not df_ventas.empty:
                ventas_por_cc = df_ventas.groupby("CENTRO COSTO")["SALDO"].sum().to_dict()
                ventas_totales = float(sum(ventas_por_cc.values()))

            # Centros disponibles
            centros_disponibles = df_mes["CENTRO COSTO"].dropna().drop_duplicates().tolist()
            centros_disponibles = sorted([c for c in centros_disponibles if c.strip().lower() != "servicios generales"])

            # TAB 1: Servicios Generales
            mask_sg = df_mes["CENTRO COSTO"].str.strip().str.lower() == "servicios generales"
            df_sg = df_mes[mask_sg].copy()
            if not df_sg.empty:
                resumen_sg = df_sg.groupby("NOMBRE", as_index=False)["SALDO"].sum().sort_values("SALDO", ascending=False)
                for _, row in resumen_sg.iterrows():
                    nombre = row["NOMBRE"]
                    cuentas_serv_generales.append({
                        "nombre": nombre,
                        "monto": float(row["SALDO"]),
                        "tiene_regla": nombre in reglas_serv_generales,
                    })

            # TAB 2: Cuentas globales
            saldos_por_cuenta = df_mes.groupby("NOMBRE")["SALDO"].sum().to_dict()
            for nombre, cfg in config_cuentas.items():
                if not cfg.get("activo", True): continue
                monto = float(saldos_por_cuenta.get(nombre, 0.0))
                regla_cuenta = reglas_cuentas.get(nombre, {})
                cuentas_prorrateo.append({
                    "nombre": nombre,
                    "tipo": cfg.get("tipo", ""),
                    "monto": monto,
                    "tiene_regla": bool(regla_cuenta),
                })

            # TAB 3: Fábrica
            aliases_fabrica = ["fca empanadas", "fca de empanadas", "fabrica empanadas", "fábrica empanadas"]
            mask_fab = df_mes["CENTRO COSTO"].str.strip().str.lower().isin(aliases_fabrica)
            df_fab = df_mes[mask_fab].copy()
            if not df_fab.empty:
                resumen_fab = df_fab.groupby(["CUENTA", "NOMBRE"], as_index=False)["SALDO"].sum().sort_values("SALDO", ascending=False)
                for _, row in resumen_fab.iterrows():
                    gastos_fabrica.append({"cuenta": row["CUENTA"], "nombre": row["NOMBRE"], "monto": float(row["SALDO"])})
                total_gastos_fabrica = float(df_fab["SALDO"].sum())
                if empanadas_elaboradas:
                    costo_unitario_empanada = total_gastos_fabrica / float(empanadas_elaboradas)

            aliases_costanera = ["costanera center", "costanera"]
            mask_cost = df_mes["CENTRO COSTO"].str.strip().str.lower().isin(aliases_costanera)
            df_cost = df_mes[mask_cost].copy()
            if not df_cost.empty:
                resumen_cost = df_cost.groupby(["CUENTA", "NOMBRE"], as_index=False)["SALDO"].sum().sort_values("SALDO", ascending=False)
                total_costanera_origen = float(df_cost["SALDO"].sum())
                for _, row in resumen_cost.iterrows():
                    pct = float(prorrateo_costanera_periodo.get(str(row["CUENTA"]), 0.0) or 0.0)
                    monto_est = float(row["SALDO"]) * pct
                    total_costanera_a_fabrica += monto_est
                    gastos_costanera_compartidos.append({
                        "cuenta": str(row["CUENTA"]), "nombre": row["NOMBRE"], "monto": float(row["SALDO"]),
                        "porcentaje": pct, "monto_estimado": monto_est
                    })
                if empanadas_elaboradas:
                    costo_unitario_empanada_estimado = (total_gastos_fabrica + total_costanera_a_fabrica) / float(empanadas_elaboradas)

    return render_template(
        "contab/prorrateos.html",
        periodo=periodo,
        pestaña=pestaña,
        cuentas_serv_generales=cuentas_serv_generales,
        centros_disponibles=centros_disponibles,
        config_cuentas=lista_config_cuentas,
        cuentas_prorrateo=cuentas_prorrateo,
        reglas_cuentas=reglas_cuentas,
        ventas_totales=ventas_totales,
        ventas_por_cc=ventas_por_cc,
        gastos_fabrica=gastos_fabrica,
        total_gastos_fabrica=total_gastos_fabrica,
        empanadas_elaboradas=empanadas_elaboradas,
        empanadas_compradas=empanadas_compradas,
        costo_unitario_empanada=costo_unitario_empanada,
        gastos_costanera_compartidos=gastos_costanera_compartidos,
        total_costanera_origen=total_costanera_origen,
        total_costanera_a_fabrica=total_costanera_a_fabrica,
        costo_unitario_empanada_estimado=costo_unitario_empanada_estimado,
        todas_las_cuentas=todas_las_cuentas # Variable nueva para el autocompletar
    )
    
@contab_bp.route("/clasificacion_cuentas")
@login_requerido
def clasificacion_cuentas():
    # 1. Cargar datos del Mayor
    df = obtener_datos("mayor")
    
    # Diccionarios para procesar
    cuentas_en_mayor = [] # Lista para el frontend (pendientes)
    mapa_nombres = {}     # Diccionario { "3101": "Sueldos" } para buscar rápido
    
    if not df.empty:
        df["CUENTA"] = df["CUENTA"].astype(str).str.strip()
        df["NOMBRE"] = df["NOMBRE"].astype(str).str.strip()
        
        # Solo Gastos (3) e Ingresos (4)
        mask = df["CUENTA"].str.startswith("3") | df["CUENTA"].str.startswith("4")
        
        # Obtenemos únicos: Cuenta y Nombre
        temp = df[mask][["CUENTA", "NOMBRE"]].drop_duplicates().sort_values("CUENTA")
        
        # Llenamos el mapa de nombres y la lista base
        for _, row in temp.iterrows():
            cta = row["CUENTA"]
            nom = row["NOMBRE"]
            mapa_nombres[cta] = nom
            cuentas_en_mayor.append({"CUENTA": cta, "NOMBRE": nom})

    # 2. Cargar configuración existente (JSON solo tiene IDs)
    data_clasif = cargar_clasificaciones()
    grupos_raw = data_clasif.get("grupos", [])

    # 3. "Enriquecer" los grupos: Agregar el nombre a los IDs guardados
    grupos_enriquecidos = []
    cuentas_usadas = set()

    for g in grupos_raw:
        cuentas_con_info = []
        for cta_id in g.get("cuentas", []):
            cuentas_usadas.add(str(cta_id))
            nombre_cuenta = mapa_nombres.get(str(cta_id), "(Cuenta sin movimientos)")
            cuentas_con_info.append({
                "id": cta_id,
                "nombre": nombre_cuenta
            })
        
        # Reconstruimos el grupo con objetos completos
        grupos_enriquecidos.append({
            "nombre": g["nombre"],
            
            # --- AGREGA ESTA LÍNEA 👇 ---
            "macro_categoria": g.get("macro_categoria", "Otros"), 
            # ---------------------------
            
            "tipo": g["tipo"],
            "cuentas": cuentas_con_info 
        })

    # 4. Filtrar pendientes (Las que no están en ningún grupo)
    cuentas_pendientes = []
    for item in cuentas_en_mayor:
        if item["CUENTA"] not in cuentas_usadas:
            cuentas_pendientes.append(item)

    return render_template(
        "contab/clasificacion.html",
        grupos=grupos_enriquecidos, # Enviamos la versión con nombres
        cuentas_pendientes=cuentas_pendientes
    )

@contab_bp.route("/api/guardar_clasificacion", methods=["POST"])
@login_requerido
def api_guardar_clasificacion():
    data = request.get_json()
    if not data or "grupos" not in data:
        return {"ok": False, "error": "Datos inválidos"}, 400
    guardar_clasificaciones(data)
    return {"ok": True}

@contab_bp.route("/api/prorrateos/serv_generales", methods=["POST"])
@login_requerido
def api_guardar_prorrateo_serv_generales():
    """
    Guarda la distribución de una cuenta de Servicios Generales por centro de costo
    Body JSON:
    {
      "periodo": "2025-03",
      "cuenta": "Sueldos y Salarios",
      "distribucion": {
          "F.T Esc. Militar": 0.25,
          "Plaza Egaña": 0.25,
          "Costanera": 0.25,
          "MUT Tobalaba": 0.25
      }
    }
    """
    payload = request.get_json(force=True)
    periodo = payload.get("periodo")
    cuenta = payload.get("cuenta")
    distribucion = payload.get("distribucion") or {}

    if not periodo or not cuenta:
        return {"ok": False, "error": "Faltan datos"}, 400

    total = sum(distribucion.values())
    # Permitimos un pequeño margen de error por decimales
    if abs(total - 1.0) > 0.001:
        return {"ok": False, "error": "La suma de porcentajes debe ser 100%"}, 400

    data = cargar_prorrateos()
    reglas_mensuales = data.setdefault("reglas_mensuales", {})
    reglas_periodo = reglas_mensuales.setdefault(periodo, {})
    serv_generales = reglas_periodo.setdefault("serv_generales", {})

    serv_generales[cuenta] = distribucion
    guardar_prorrateos(data)

    return {"ok": True}

@contab_bp.route("/api/prorrateos/cuenta_manual", methods=["POST"])
@login_requerido
def api_guardar_prorrateo_cuenta_manual():
    """
    Guarda la distribución de una cuenta global (tipo MANUAL_SUCURSAL)
    Body JSON:
    {
      "periodo": "2025-03",
      "cuenta": "Comision Uber Eats",
      "distribucion": {
          "F.T Esc. Militar": 0.40,
          "Plaza Egaña": 0.30,
          "Costanera Center": 0.20,
          "MUT Tobalaba": 0.10
      }
    }
    """
    payload = request.get_json(force=True)
    periodo = payload.get("periodo")
    cuenta = payload.get("cuenta")
    distribucion = payload.get("distribucion") or {}

    if not periodo or not cuenta:
        return {"ok": False, "error": "Faltan datos"}, 400

    total = sum(distribucion.values())
    if abs(total - 1.0) > 0.001:
        return {"ok": False, "error": "La suma de porcentajes debe ser 100%"}, 400

    data = cargar_prorrateos()
    reglas_mensuales = data.setdefault("reglas_mensuales", {})
    reglas_periodo = reglas_mensuales.setdefault(periodo, {})
    cuentas_globales = reglas_periodo.setdefault("cuentas_globales", {})

    cuentas_globales[cuenta] = distribucion
    guardar_prorrateos(data)

    return {"ok": True}

@contab_bp.route("/api/prorrateos/fabrica_costeo", methods=["POST"])
@login_requerido
def api_guardar_prorrateo_fabrica():
    """
    Guarda los datos básicos de costeo de la fábrica de empanadas
    Body JSON:
    {
      "periodo": "2025-09",
      "empanadas_elaboradas": 35000,
      "empanadas_compradas": 5000
    }
    """
    payload = request.get_json(force=True) or {}
    periodo = payload.get("periodo")
    emp_elab = payload.get("empanadas_elaboradas")
    emp_comp = payload.get("empanadas_compradas")

    if not periodo:
        return {"ok": False, "error": "Falta el periodo"}, 400

    try:
        emp_elab = float(emp_elab) if emp_elab not in (None, "") else 0.0
        emp_comp = float(emp_comp) if emp_comp not in (None, "") else 0.0
    except ValueError:
        return {"ok": False, "error": "Valores numéricos inválidos"}, 400

    data = cargar_prorrateos()
    fabrica_cfg = data.setdefault("fabrica_empanadas", {})
    costeo_periodos = fabrica_cfg.setdefault("costeo_periodos", {})

    costeo_periodos[periodo] = {
        "empanadas_elaboradas": emp_elab,
        "empanadas_compradas": emp_comp,
    }

    guardar_prorrateos(data)
    return {"ok": True}

@contab_bp.route("/api/prorrateos/fabrica_costanera", methods=["POST"])
@login_requerido
def api_guardar_prorrateo_fabrica_costanera():
    """
    Guarda la estimación de prorrateo de cuentas del C.C Costanera hacia Fábrica.
    Body JSON:
    {
      "periodo": "2025-09",
      "reglas": {
        "5103001": 0.30,
        "5104001": 0.40,
        ...
      }
    }
    """
    payload = request.get_json(force=True) or {}
    periodo = payload.get("periodo")
    reglas = payload.get("reglas") or {}

    if not periodo:
        return {"ok": False, "error": "Falta el periodo"}, 400

    # Normalizamos a float 0–1
    reglas_limpias = {}
    for cuenta, val in reglas.items():
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v < 0:
            v = 0.0
        if v > 1:
            v = 1.0
        reglas_limpias[str(cuenta)] = v

    data = cargar_prorrateos()
    fabrica_cfg = data.setdefault("fabrica_empanadas", {})
    costanera_prorrateos = fabrica_cfg.setdefault("costanera_prorrateos", {})

    costanera_prorrateos[periodo] = reglas_limpias

    guardar_prorrateos(data)
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

# ==============================================================================
# INFORME GERENCIAL (MOTOR DE CÁLCULO ESTRUCTURADO)
# ==============================================================================

@contab_bp.route("/informe_gerencial")
@login_requerido
def informe_gerencial():
    # 1. Cargar Datos PRIMERO (para detectar fecha máxima)
    df = obtener_datos("mayor")
    data_prorrateos = cargar_prorrateos()
    data_clasif = cargar_clasificaciones()
    
    # Preprocesar fechas para buscar el último mes con datos
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    
    # 2. Definir Periodo por defecto (Último mes con datos real)
    periodo = request.args.get("periodo")
    if not periodo:
        if not df.empty:
            max_fecha = df["FECHA"].max()
            # Validamos que no sea NaT (Not a Time)
            if pd.notna(max_fecha):
                periodo = max_fecha.strftime("%Y-%m")
            else:
                periodo = datetime.now().strftime("%Y-%m")
        else:
            periodo = datetime.now().strftime("%Y-%m")

    # Parámetros de Switches
    switch_sg = request.args.get("distribuir_sg") == "on"
    switch_fab = request.args.get("ajuste_fabrica") == "on"
    
    # Cargar configuraciones (Esto se mantiene igual, solo que ahora 'periodo' ya es el correcto)
    reglas_periodo = data_prorrateos.get("reglas_mensuales", {}).get(periodo, {})
    reglas_cuentas = reglas_periodo.get("cuentas_globales", {})
    reglas_sg = reglas_periodo.get("serv_generales", {})
    config_cuentas = data_prorrateos.get("config_cuentas", {})
    prorrateo_costanera = data_prorrateos.get("fabrica_empanadas", {}).get("costanera_prorrateos", {}).get(periodo, {})

    # 3. Filtrado Base
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    year, month = map(int, periodo.split("-"))
    df = df[(df["FECHA"].dt.year == year) & (df["FECHA"].dt.month == month)].copy()
    
    # CAMBIO CLAVE 1: SIGNO DE GESTIÓN
    # Contabilidad: Gasto es Positivo (Debe). Gestión: Gasto es Negativo.
    # Contabilidad: Ingreso es Negativo (Haber). Gestión: Ingreso es Positivo.
    # Solución: Multiplicar (Debe - Haber) * -1
    df["SALDO_REAL"] = (df["DEBE"] - df["HABER"]) * -1

    df["CUENTA"] = df["CUENTA"].astype(str).str.strip()
    df["NOMBRE"] = df["NOMBRE"].astype(str).str.strip()
    df["CENTRO COSTO"] = df["CENTRO COSTO"].astype(str).str.strip()
    
    mask_res = df["CUENTA"].str.startswith("3") | df["CUENTA"].str.startswith("4")
    df = df[mask_res]

    # 4. Construcción de Matriz
    matriz = {}
    todos_cc = set(df["CENTRO COSTO"].unique())
    todos_cc = sorted(list(todos_cc))

    for _, row in df.iterrows():
        cta = row["CUENTA"]
        if cta not in matriz: 
            matriz[cta] = {"nombre": row["NOMBRE"], "montos": {}}
        # Sumamos
        cc = row["CENTRO COSTO"]
        matriz[cta]["montos"][cc] = matriz[cta]["montos"].get(cc, 0) + row["SALDO_REAL"]

    # 5. Prorrateos (Ventas Globales)
    ventas_por_cc = {}
    total_ventas = 0
    # Buscar cuentas 41... (Ingresos)
    for cta, data in matriz.items():
        if cta.startswith("41"):
            for cc, monto in data["montos"].items():
                # En gestión Ingresos son positivos, usamos el valor directo si es >0
                if monto > 0:
                    ventas_por_cc[cc] = ventas_por_cc.get(cc, 0) + monto
                    total_ventas += monto

    for cta_codigo, data_cta in matriz.items():
        nombre_cta = data_cta["nombre"]
        cfg = config_cuentas.get(nombre_cta)
        if cfg and cfg.get("activo"):
            tipo = cfg.get("tipo")
            distribucion = {}
            if tipo == "MANUAL_SUCURSAL":
                distribucion = reglas_cuentas.get(nombre_cta, {})
            elif tipo == "VENTAS_SUCURSAL":
                if total_ventas > 0:
                    for cc_v, monto_v in ventas_por_cc.items():
                        distribucion[cc_v] = monto_v / total_ventas
            
            if distribucion:
                # Sumamos el total (ojo con el signo, se mantiene)
                total_cuenta = sum(data_cta["montos"].values())
                data_cta["montos"] = {} # Limpiamos origen
                for cc_dest, pct in distribucion.items():
                    data_cta["montos"][cc_dest] = data_cta["montos"].get(cc_dest, 0) + (total_cuenta * pct)

    # 6. Switch Servicios Generales
    if switch_sg:
        for cta_codigo, data_cta in matriz.items():
            montos_cc = data_cta["montos"]
            ccs = list(montos_cc.keys())
            for cc in ccs:
                if "servicios generales" in cc.lower():
                    val = montos_cc[cc]
                    if val == 0: continue
                    regla = reglas_sg.get(data_cta["nombre"])
                    if regla:
                        montos_cc[cc] -= val
                        for cc_dest, pct in regla.items():
                            montos_cc[cc_dest] = montos_cc.get(cc_dest, 0) + (val * pct)

    # 7. Switch Fábrica
    if switch_fab:
        cc_costanera = next((c for c in todos_cc if "costanera" in c.lower()), None)
        cc_fabrica = next((c for c in todos_cc if "fca" in c.lower() or "fabrica" in c.lower()), None)
        
        if cc_costanera and cc_fabrica:
            # Nota: prorrateo_costanera viene con %, se aplica sobre gastos (que ahora son negativos)
            # Ejemplo: Gasto Arriendo -1.000.000 * 0.30 = -300.000 a transferir
            for cta_codigo, pct in prorrateo_costanera.items():
                if cta_codigo in matriz:
                    montos = matriz[cta_codigo]["montos"]
                    val_cost = montos.get(cc_costanera, 0)
                    if val_cost != 0:
                        transferencia = val_cost * pct
                        montos[cc_costanera] -= transferencia
                        montos[cc_fabrica] = montos.get(cc_fabrica, 0) + transferencia

    # ==========================================================================
    # 8. ARMADO DEL REPORTE ESTRUCTURADO (ESTILO EER)
    # ==========================================================================
    
    # Paso A: Agrupar todo por Macro Categoría en un diccionario temporal
    # macros_data = { "Ingresos Operacionales": {grupos: [], totales_cc: {}}, ... }
    macros_data = {}
    grupos_config = data_clasif.get("grupos", [])
    cuentas_procesadas = set()

    # Inicializar macros_data con los datos reales
    for grp in grupos_config:
        macro_nombre = grp.get("macro_categoria", "Otros")
        if macro_nombre not in macros_data:
            macros_data[macro_nombre] = {"grupos": [], "totales_cc": {cc: 0.0 for cc in todos_cc}}
        
        fila_grupo = {
            "nombre": grp["nombre"],
            "tipo": grp["tipo"],
            "totales_cc": {cc: 0.0 for cc in todos_cc},
            "detalle_cuentas": []
        }
        
        for cta_id_raw in grp["cuentas"]:
            cta_id = str(cta_id_raw)
            if cta_id in matriz:
                cuentas_procesadas.add(cta_id)
                data_cta = matriz[cta_id]
                for cc, val in data_cta["montos"].items():
                    fila_grupo["totales_cc"][cc] += val
                    macros_data[macro_nombre]["totales_cc"][cc] += val
                
                fila_grupo["detalle_cuentas"].append({
                    "codigo": cta_id, "nombre": data_cta["nombre"], "montos_cc": data_cta["montos"]
                })
        
        macros_data[macro_nombre]["grupos"].append(fila_grupo)

    # Paso B: Recoger huérfanos ("Sin Clasificar")
    sin_clasif = {"nombre": "Cuentas Pendientes", "totales_cc": {cc:0.0 for cc in todos_cc}, "detalle_cuentas": []}
    hay_pendientes = False
    for cta_id, data_cta in matriz.items():
        if cta_id not in cuentas_procesadas:
            if sum(abs(v) for v in data_cta["montos"].values()) > 1:
                hay_pendientes = True
                for cc, val in data_cta["montos"].items():
                    sin_clasif["totales_cc"][cc] += val
                sin_clasif["detalle_cuentas"].append({
                    "codigo": cta_id, "nombre": data_cta["nombre"], "montos_cc": data_cta["montos"]
                })
    
    if hay_pendientes:
        if "Sin Clasificar" not in macros_data:
            macros_data["Sin Clasificar"] = {"grupos": [], "totales_cc": {cc:0.0 for cc in todos_cc}}
        macros_data["Sin Clasificar"]["grupos"].append(sin_clasif)
        # Sumar al total macro
        for cc, val in sin_clasif["totales_cc"].items():
            macros_data["Sin Clasificar"]["totales_cc"][cc] += val


    # Paso C: DEFINICIÓN DE LA ESTRUCTURA FIJA (Aquí ocurre la magia del orden)
    # ids_fuente: Son los nombres EXACTOS de los "Macros" que pusiste en el configurador
    ESTRUCTURA = [
        {
            "id": "ingresos_op",
            "titulo": "INGRESOS DE EXPLOTACIÓN",
            "tipo": "macro", # Muestra detalle
            "fuente": ["Ingresos Operacionales", "Ingresos Venta"] 
        },
        {
            "id": "costos_op",
            "titulo": "COSTOS DE EXPLOTACIÓN",
            "tipo": "macro",
            "fuente": ["Costos de Explotación", "Costo Venta"]
        },
        {
            "id": "margen",
            "titulo": "MARGEN DE EXPLOTACIÓN",
            "tipo": "calculo",
            "color": "warning", # amarillo
            "operacion": ["ingresos_op", "costos_op"] # Suma lineal (ya tienen signo)
        },
        {
            "id": "gastos_adm",
            "titulo": "GASTOS DE ADMINISTRACIÓN Y VENTAS",
            "tipo": "macro",
            "fuente": ["Gastos de Administración y Ventas", "Gastos Administración"]
        },
        {
            "id": "res_op",
            "titulo": "RESULTADO OPERACIONAL",
            "tipo": "calculo",
            "color": "info", # celeste
            "operacion": ["margen", "gastos_adm"]
        },
        {
            "id": "no_op",
            "titulo": "INGRESOS Y EGRESOS NO OPERACIONALES",
            "tipo": "macro",
            "fuente": ["Ingresos No Operacionales", "Otros Ingresos/Egresos"]
        },
        {
            "id": "res_final",
            "titulo": "RESULTADO ANTES DE IMPTO",
            "tipo": "calculo",
            "color": "success", # verde
            "operacion": ["res_op", "no_op"]
        },
        {
            "id": "otros",
            "titulo": "SIN CLASIFICAR / OTROS",
            "tipo": "macro",
            "fuente": ["Sin Clasificar", "Otros"]
        }
    ]

    # Paso D: Construir Lista Final
    reporte_final = []
    # Diccionario temporal para guardar los totales de cada fila (para los cálculos)
    # cache_calculos = { "ingresos_op": {cc: 100}, "costos_op": {cc: -80} }
    cache_calculos = {}

    for linea in ESTRUCTURA:
        fila_salida = {
            "titulo": linea["titulo"],
            "tipo": linea["tipo"],
            "color": linea.get("color", "secondary"),
            "grupos": [], # Solo si es macro
            "totales_cc": {cc: 0.0 for cc in todos_cc}
        }

        if linea["tipo"] == "macro":
            # Buscamos en macros_data las fuentes
            encontro_algo = False
            for fuente in linea["fuente"]:
                if fuente in macros_data:
                    datos = macros_data[fuente]
                    # Agregamos los grupos de esa macro a esta sección
                    fila_salida["grupos"].extend(datos["grupos"])
                    # Sumamos totales
                    for cc, val in datos["totales_cc"].items():
                        fila_salida["totales_cc"][cc] += val
                    encontro_algo = True
            
            # Guardamos para futuros cálculos
            cache_calculos[linea["id"]] = fila_salida["totales_cc"]
            
            # Solo agregamos al reporte si tiene datos o si es obligatorio
            if encontro_algo or linea["id"] == "otros":
                if not encontro_algo and linea["id"] != "otros": continue
                # Si es "Otros" y está vacío, lo saltamos
                if linea["id"] == "otros" and not encontro_algo: continue
                reporte_final.append(fila_salida)

        elif linea["tipo"] == "calculo":
            # Operar sobre cache_calculos
            # Por defecto es suma lineal de los IDs en "operacion"
            operandos = linea["operacion"]
            for op_id in operandos:
                totales_op = cache_calculos.get(op_id, {})
                for cc in todos_cc:
                    fila_salida["totales_cc"][cc] += totales_op.get(cc, 0.0)
            
            # Guardar este resultado también por si se usa después
            cache_calculos[linea["id"]] = fila_salida["totales_cc"]
            reporte_final.append(fila_salida)

    return render_template(
        "contab/informe_gerencial.html",
        periodo=periodo,
        reporte=reporte_final,
        columnas_cc=todos_cc,
        switch_sg=switch_sg,
        switch_fab=switch_fab
    )
    
# ==============================================================================
# NUEVO MÓDULO: COMPARATIVO DE GESTIÓN (FULL PRORRATEO)
# ==============================================================================
@contab_bp.route("/comparativo_gestion")
@login_requerido
def comparativo_gestion():
    # 1. Parámetros
    comp_cc = request.args.get("comp_cc", "Total Empresa")
    comp_modo = request.args.get("comp_modo", "last_6") 
    
    # Switches
    switch_sg = request.args.get("distribuir_sg") == "on"
    switch_fab = request.args.get("ajuste_fabrica") == "on"
    
    # 2. Cargar Datos y Configuración
    df = obtener_datos("mayor")
    data_prorrateos = cargar_prorrateos()
    data_clasif = cargar_clasificaciones()
    
    config_cuentas = data_prorrateos.get("config_cuentas", {}) # Para saber cuáles son VENTAS_SUCURSAL
    reglas_cuentas_mensuales = data_prorrateos.get("reglas_mensuales", {}) # Para MANUAL_SUCURSAL

    # Cargar reglas SG y Fábrica
    pool_reglas_sg = {}
    pool_reglas_fab = {}
    for p, datos in reglas_cuentas_mensuales.items():
        if "serv_generales" in datos: pool_reglas_sg[p] = datos["serv_generales"]
    for p, datos in data_prorrateos.get("fabrica_empanadas", {}).get("costanera_prorrateos", {}).items():
        pool_reglas_fab[p] = datos

    def obtener_regla_vigente(pool_reglas, periodo_actual):
        if periodo_actual in pool_reglas: return pool_reglas[periodo_actual]
        anteriores = [p for p in pool_reglas.keys() if p < periodo_actual]
        if not anteriores: return {} 
        return pool_reglas[max(anteriores)]

    # 3. Preparar Fechas
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    if not df.empty: fecha_fin = df["FECHA"].max()
    else: fecha_fin = datetime.now()

    columnas_periodos = []
    if comp_modo == "last_6":
        for i in range(5, -1, -1): columnas_periodos.append((fecha_fin - pd.DateOffset(months=i)).strftime("%Y-%m"))
    elif comp_modo == "last_12":
        for i in range(11, -1, -1): columnas_periodos.append((fecha_fin - pd.DateOffset(months=i)).strftime("%Y-%m"))
    elif comp_modo == "anual":
        for i in range(2, -1, -1): columnas_periodos.append(datetime(fecha_fin.year - i, fecha_fin.month, 1).strftime("%Y-%m"))

    # 4. Pre-procesamiento
    df["SALDO_REAL"] = (df["DEBE"] - df["HABER"]) * -1
    df["PERIODO_STR"] = df["FECHA"].dt.strftime("%Y-%m")
    df["CENTRO COSTO"] = df["CENTRO COSTO"].astype(str).str.strip()
    df["CUENTA"] = df["CUENTA"].astype(str).str.strip()
    df["NOMBRE"] = df["NOMBRE"].astype(str).str.strip()
    
    mask = df["CUENTA"].str.startswith(('3', '4')) & df["PERIODO_STR"].isin(columnas_periodos)
    df = df[mask].copy()

    # ==========================================================================
    # 5. CÁLCULO DE VENTAS (Para Prorrateo Automático)
    # ==========================================================================
    # Necesitamos saber cuánto vendió la empresa TOTAL y cuánto la sucursal seleccionada en cada mes
    ventas_totales_mes = {} # { "2025-01": 100000 }
    ventas_sucursal_mes = {} # { "2025-01": 20000 } (Si comp_cc != Total Empresa)

    # Cuentas 41... son ventas. En gestión son positivas.
    df_ventas = df[df["CUENTA"].str.startswith("41")]
    
    # Agrupamos por mes para total empresa
    ventas_totales_mes = df_ventas[df_ventas["SALDO_REAL"] > 0].groupby("PERIODO_STR")["SALDO_REAL"].sum().to_dict()

    if comp_cc != "Total Empresa":
        # Agrupamos por mes para la sucursal seleccionada
        df_ventas_cc = df_ventas[(df_ventas["CENTRO COSTO"] == comp_cc) & (df_ventas["SALDO_REAL"] > 0)]
        ventas_sucursal_mes = df_ventas_cc.groupby("PERIODO_STR")["SALDO_REAL"].sum().to_dict()

    # ==========================================================================
    # 6. DISTRIBUCIÓN Y FILTRADO
    # ==========================================================================
    # Aquí ocurre la magia. Iteramos todo, aplicamos reglas y decidimos si la fila entra al reporte.
    
    filas_trabajo = df.to_dict("records")
    filas_finales = []
    
    # Cache para optimizar
    mov_fabrica = df[ (df["CUENTA"] == "3101002") & (abs(df["SALDO_REAL"]) > 1) ]
    meses_activos_fabrica = set(mov_fabrica["PERIODO_STR"].unique())
    cache_reglas_sg = {}
    cache_reglas_fab = {}

    for row in filas_trabajo:
        periodo = row["PERIODO_STR"]
        cc_row = row["CENTRO COSTO"]
        nombre_cta = row["NOMBRE"]
        monto = row["SALDO_REAL"]
        
        # --- PASO A: CUENTAS GLOBALES (Costo Venta, Uber, etc.) ---
        # Si la cuenta es global, debemos ver si le corresponde un pedazo a la sucursal seleccionada
        cfg_global = config_cuentas.get(nombre_cta)
        
        if cfg_global and cfg_global.get("activo"):
            tipo = cfg_global.get("tipo")
            
            if comp_cc == "Total Empresa":
                # Si es total empresa, entra todo (suma directa), no hay que repartir
                filas_finales.append(row)
                continue
            
            # Si es una sucursal específica, calculamos su cuota
            monto_asignado = 0
            
            if tipo == "VENTAS_SUCURSAL":
                total_mes = ventas_totales_mes.get(periodo, 0)
                venta_cc = ventas_sucursal_mes.get(periodo, 0)
                if total_mes > 0:
                    ratio = venta_cc / total_mes
                    monto_asignado = monto * ratio # Asignamos proporción
            
            elif tipo == "MANUAL_SUCURSAL":
                # Buscar regla manual histórica
                reglas_mes = reglas_cuentas_mensuales.get(periodo, {}).get("cuentas_globales", {})
                distribucion = reglas_mes.get(nombre_cta, {})
                pct = distribucion.get(comp_cc, 0)
                monto_asignado = monto * pct

            # Creamos la fila virtual para esta sucursal
            if monto_asignado != 0:
                nueva = row.copy()
                nueva["CENTRO COSTO"] = comp_cc # Forzamos que sea de esta sucursal para que pase el filtro
                nueva["SALDO_REAL"] = monto_asignado
                filas_finales.append(nueva)
            
            # IMPORTANTE: No agregamos la fila original "row" porque ya procesamos su asignación
            continue 

        # --- Si NO es cuenta global, sigue el flujo normal ---
        
        # --- PASO B: SWITCHES (SG y Fábrica) ---
        # Solo procesamos si la fila original pertenece a los centros de origen (SG o Costanera)
        
        filas_generadas_switches = []
        fila_desaparece = False

        # Lógica SG
        if switch_sg and "servicios generales" in cc_row.lower():
            if periodo not in cache_reglas_sg: cache_reglas_sg[periodo] = obtener_regla_vigente(pool_reglas_sg, periodo)
            regla_cta = cache_reglas_sg[periodo].get(nombre_cta)
            
            if regla_cta:
                fila_desaparece = True # La original se va
                # Si estamos viendo Total Empresa, esto da suma cero, pero visualmente se redistribuye
                # Si estamos viendo Sucursal, solo nos importa si recibimos algo
                for destino, pct in regla_cta.items():
                    if comp_cc == "Total Empresa" or destino == comp_cc:
                        nueva = row.copy()
                        nueva["CENTRO COSTO"] = destino
                        nueva["SALDO_REAL"] = monto * pct
                        filas_generadas_switches.append(nueva)

        # Lógica Fábrica
        elif switch_fab and "costanera" in cc_row.lower():
            if periodo in meses_activos_fabrica:
                if periodo not in cache_reglas_fab: cache_reglas_fab[periodo] = obtener_regla_vigente(pool_reglas_fab, periodo)
                pct_traslado = cache_reglas_fab[periodo].get(row["CUENTA"])
                
                if pct_traslado:
                    monto_traslado = monto * pct_traslado
                    
                    # Costanera se reduce
                    if comp_cc == "Total Empresa" or "costanera" in comp_cc.lower():
                        ajuste = row.copy()
                        ajuste["SALDO_REAL"] = -monto_traslado
                        filas_generadas_switches.append(ajuste)
                    
                    # Fábrica recibe
                    cc_fabrica = "Fca de Empanadas"
                    if comp_cc == "Total Empresa" or comp_cc == cc_fabrica:
                        destino = row.copy()
                        destino["CENTRO COSTO"] = cc_fabrica
                        destino["SALDO_REAL"] = monto_traslado
                        filas_generadas_switches.append(destino)

        # --- PASO C: FILTRADO FINAL ---
        
        # 1. Agregamos las filas generadas por switches
        for f in filas_generadas_switches:
            filas_finales.append(f)
            
        # 2. Agregamos la fila original SI NO desapareció Y SI corresponde al CC filtro
        if not fila_desaparece:
            # Si es Total Empresa, pasa todo. Si es sucursal, solo si coincide.
            if comp_cc == "Total Empresa" or row["CENTRO COSTO"] == comp_cc:
                filas_finales.append(row)

    # ==========================================================================
    # 7. ARMADO DE MATRIZ Y REPORTE (Igual que antes)
    # ==========================================================================
    # ... (El resto del código de agrupación, macros y estructura fija se mantiene IDÉNTICO)
    # Copia desde aquí hacia abajo del código anterior, o te lo pego completo si prefieres.
    
    # Para ahorrar espacio en el chat, asumo que la parte de "7. Agrupar Clasificados" 
    # hasta el final "return render_template" es la misma que la versión anterior.
    # Solo cambió la lógica de generación de filas (Paso 5 y 6).
    
    # AQUI ABAJO VA LA PARTE DE MATRIZ (Repetirla del mensaje anterior)
    
    df_final = pd.DataFrame(filas_finales)
    
    if df_final.empty:
         return render_template("contab/comparativo_gestion.html", 
                               reporte=[], columnas=columnas_periodos, 
                               todos_cc=[], comp_cc=comp_cc, comp_modo=comp_modo,
                               switch_sg=switch_sg, switch_fab=switch_fab)

    todos_cc = sorted(list(set(obtener_datos("mayor")["CENTRO COSTO"].dropna().unique())))

    matriz = {}
    for _, row in df_final.iterrows():
        cta = str(row["CUENTA"]).strip()
        per = row["PERIODO_STR"]
        if cta not in matriz:
            matriz[cta] = {"nombre": row["NOMBRE"], "montos": {}}
        matriz[cta]["montos"][per] = matriz[cta]["montos"].get(per, 0) + row["SALDO_REAL"]

    # 7. Agrupar Clasificados (COPIAR IGUAL)
    macros_data = {}
    grupos_config = data_clasif.get("grupos", [])
    cuentas_procesadas = set()

    for grp in grupos_config:
        macro_nombre = grp.get("macro_categoria", "Otros")
        if macro_nombre not in macros_data:
            macros_data[macro_nombre] = {"grupos": [], "totales_col": {c: 0.0 for c in columnas_periodos}}
        
        fila_grupo = {
            "nombre": grp["nombre"],
            "tipo": grp["tipo"],
            "totales_col": {c: 0.0 for c in columnas_periodos},
            "detalle_cuentas": []
        }
        
        for cta_id_raw in grp["cuentas"]:
            cta_id = str(cta_id_raw)
            if cta_id in matriz:
                cuentas_procesadas.add(cta_id)
                data_cta = matriz[cta_id]
                for col in columnas_periodos:
                    val = data_cta["montos"].get(col, 0)
                    fila_grupo["totales_col"][col] += val
                    macros_data[macro_nombre]["totales_col"][col] += val
                
                fila_grupo["detalle_cuentas"].append({
                    "codigo": cta_id, "nombre": data_cta["nombre"], "montos_col": data_cta["montos"]
                })
        
        macros_data[macro_nombre]["grupos"].append(fila_grupo)

    # 8. Huérfanos (COPIAR IGUAL)
    sin_clasif = {"nombre": "Cuentas Pendientes", "tipo": "GASTO", "totales_col": {c:0.0 for c in columnas_periodos}, "detalle_cuentas": []}
    hay_pendientes = False
    for cta_id, data_cta in matriz.items():
        if cta_id not in cuentas_procesadas:
            if sum(abs(data_cta["montos"].get(c, 0)) for c in columnas_periodos) > 1:
                hay_pendientes = True
                for col in columnas_periodos:
                    val = data_cta["montos"].get(col, 0)
                    sin_clasif["totales_col"][col] += val
                sin_clasif["detalle_cuentas"].append({
                    "codigo": cta_id, "nombre": data_cta["nombre"], "montos_col": data_cta["montos"]
                })
    if hay_pendientes:
        if "Sin Clasificar" not in macros_data:
            macros_data["Sin Clasificar"] = {"grupos": [], "totales_col": {c:0.0 for c in columnas_periodos}}
        macros_data["Sin Clasificar"]["grupos"].append(sin_clasif)
        for col in columnas_periodos:
            macros_data["Sin Clasificar"]["totales_col"][col] += sin_clasif["totales_col"][col]

    # 9. Estructura Fija (COPIAR IGUAL)
    ESTRUCTURA = [
        {"id": "ingresos_op", "titulo": "INGRESOS DE EXPLOTACIÓN", "tipo": "macro", "fuente": ["Ingresos Operacionales", "Ingresos Venta"]},
        {"id": "costos_op", "titulo": "COSTOS DE EXPLOTACIÓN", "tipo": "macro", "fuente": ["Costos de Explotación", "Costo Venta"]},
        {"id": "margen", "titulo": "MARGEN DE EXPLOTACIÓN", "tipo": "calculo", "color": "warning", "operacion": ["ingresos_op", "costos_op"]},
        {"id": "gastos_adm", "titulo": "GASTOS DE ADMINISTRACIÓN Y VENTAS", "tipo": "macro", "fuente": ["Gastos de Administración y Ventas"]},
        {"id": "res_op", "titulo": "RESULTADO OPERACIONAL", "tipo": "calculo", "color": "info", "operacion": ["margen", "gastos_adm"]},
        {"id": "no_op", "titulo": "INGRESOS Y EGRESOS NO OPERACIONALES", "tipo": "macro", "fuente": ["Ingresos No Operacionales"]},
        {"id": "res_final", "titulo": "RESULTADO ANTES DE IMPTO", "tipo": "calculo", "color": "success", "operacion": ["res_op", "no_op"]},
        {"id": "otros", "titulo": "SIN CLASIFICAR / OTROS", "tipo": "macro", "fuente": ["Sin Clasificar", "Otros"]}
    ]

    reporte_final = []
    cache_calculos = {}

    for linea in ESTRUCTURA:
        fila_salida = {
            "titulo": linea["titulo"],
            "tipo": linea["tipo"],
            "color": linea.get("color", "secondary"),
            "grupos": [],
            "totales_col": {c: 0.0 for c in columnas_periodos}
        }

        if linea["tipo"] == "macro":
            encontro = False
            for fuente in linea["fuente"]:
                if fuente in macros_data:
                    d = macros_data[fuente]
                    fila_salida["grupos"].extend(d["grupos"])
                    for col in columnas_periodos:
                        fila_salida["totales_col"][col] += d["totales_col"][col]
                    encontro = True
            cache_calculos[linea["id"]] = fila_salida["totales_col"]
            if encontro or linea["id"] == "otros":
                if not encontro and linea["id"] != "otros": continue
                reporte_final.append(fila_salida)

        elif linea["tipo"] == "calculo":
            for op_id in linea["operacion"]:
                totales_op = cache_calculos.get(op_id, {})
                for col in columnas_periodos:
                    fila_salida["totales_col"][col] += totales_op.get(col, 0.0)
            cache_calculos[linea["id"]] = fila_salida["totales_col"]
            reporte_final.append(fila_salida)

    return render_template(
        "contab/comparativo_gestion.html",
        reporte=reporte_final,
        columnas=columnas_periodos,
        todos_cc=todos_cc,
        comp_cc=comp_cc,
        comp_modo=comp_modo,
        switch_sg=switch_sg,
        switch_fab=switch_fab
    )
    
# ==============================================================================
# DASHBOARD DE GESTIÓN (KPIs ANUALES)
# ==============================================================================
@contab_bp.route("/dashboard_gestion")
@login_requerido
def dashboard_gestion():
    # 1. Parámetros
    dash_cc = request.args.get("dash_cc", "Total Empresa")
    periodo_solicitado = request.args.get("periodo") 
    
    switch_sg = True
    switch_fab = True

    # 2. Cargar Datos
    df = obtener_datos("mayor")
    data_prorrateos = cargar_prorrateos()
    data_clasif = cargar_clasificaciones()
    
    grupos_config = data_clasif.get("grupos", [])
    
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    if df.empty:
        return render_template("contab/dashboard_gestion.html", dash_cc=dash_cc, kpis={}, charts={})

    # --- LÓGICA DE FECHA ---
    if periodo_solicitado:
        fecha_max = pd.to_datetime(periodo_solicitado + "-01") + pd.offsets.MonthEnd(0)
    else:
        fecha_max = df["FECHA"].max()

    anio_actual = fecha_max.year
    anio_anterior = anio_actual - 1
    
    # Filtramos datos necesarios (Año actual y anterior)
    df = df[df["FECHA"].dt.year >= anio_anterior].copy()

    # 3. Lógica de Prorrateo
    df["SALDO_REAL"] = (df["DEBE"] - df["HABER"]) * -1
    df["PERIODO_STR"] = df["FECHA"].dt.strftime("%Y-%m")
    df["CENTRO COSTO"] = df["CENTRO COSTO"].astype(str).str.strip()
    df["CUENTA"] = df["CUENTA"].astype(str).str.strip()
    df["NOMBRE"] = df["NOMBRE"].astype(str).str.strip()
    
    df = df[df["CUENTA"].str.startswith(('3', '4'))].copy()

    config_cuentas = data_prorrateos.get("config_cuentas", {})
    reglas_mensuales = data_prorrateos.get("reglas_mensuales", {})
    costanera_prorrateos = data_prorrateos.get("fabrica_empanadas", {}).get("costanera_prorrateos", {})
    
    pool_reglas_sg = {}
    pool_reglas_fab = {}
    for p, d in reglas_mensuales.items():
        if "serv_generales" in d: pool_reglas_sg[p] = d["serv_generales"]
    for p, d in costanera_prorrateos.items(): pool_reglas_fab[p] = d

    def get_regla(pool, per):
        if per in pool: return pool[per]
        ants = [p for p in pool.keys() if p < per]
        return pool[max(ants)] if ants else {}

    df_ventas = df[df["CUENTA"].str.startswith("41")]
    vtas_tot = df_ventas[df_ventas["SALDO_REAL"]>0].groupby("PERIODO_STR")["SALDO_REAL"].sum().to_dict()
    vtas_cc = {}
    if dash_cc != "Total Empresa":
        vtas_cc = df_ventas[(df_ventas["CENTRO COSTO"]==dash_cc) & (df_ventas["SALDO_REAL"]>0)].groupby("PERIODO_STR")["SALDO_REAL"].sum().to_dict()

    filas_finales = []
    mov_fabrica = df[(df["CUENTA"]=="3101002")&(abs(df["SALDO_REAL"])>1)]
    meses_activos_fab = set(mov_fabrica["PERIODO_STR"].unique())
    cache_sg = {}
    cache_fab = {}

    for row in df.to_dict("records"):
        per = row["PERIODO_STR"]
        cc_row = row["CENTRO COSTO"]
        nom = row["NOMBRE"]
        monto = row["SALDO_REAL"]
        
        cfg = config_cuentas.get(nom)
        if cfg and cfg.get("activo"):
            if dash_cc == "Total Empresa":
                filas_finales.append(row)
            else:
                asig = 0
                if cfg["tipo"] == "VENTAS_SUCURSAL":
                    tot = vtas_tot.get(per, 0)
                    if tot > 0: asig = monto * (vtas_cc.get(per, 0)/tot)
                elif cfg["tipo"] == "MANUAL_SUCURSAL":
                    reg = reglas_mensuales.get(per, {}).get("cuentas_globales", {}).get(nom, {})
                    asig = monto * reg.get(dash_cc, 0)
                
                if asig != 0:
                    r = row.copy()
                    r["CENTRO COSTO"] = dash_cc
                    r["SALDO_REAL"] = asig
                    filas_finales.append(r)
            continue

        generadas = []
        borrar = False
        
        if switch_sg and "servicios generales" in cc_row.lower():
            if per not in cache_sg: cache_sg[per] = get_regla(pool_reglas_sg, per)
            reg = cache_sg[per].get(nom)
            if reg:
                borrar = True
                for dst, pct in reg.items():
                    if dash_cc == "Total Empresa" or dst == dash_cc:
                        r = row.copy()
                        r["CENTRO COSTO"] = dst
                        r["SALDO_REAL"] = monto * pct
                        generadas.append(r)
        
        elif switch_fab and "costanera" in cc_row.lower():
            if per in meses_activos_fab:
                if per not in cache_fab: cache_fab[per] = get_regla(pool_reglas_fab, per)
                pct = cache_fab[per].get(row["CUENTA"])
                if pct:
                    traslado = monto * pct
                    if dash_cc=="Total Empresa" or "costanera" in dash_cc.lower():
                        r1 = row.copy()
                        r1["SALDO_REAL"] = -traslado
                        generadas.append(r1)
                    if dash_cc=="Total Empresa" or dash_cc=="Fca de Empanadas":
                        r2 = row.copy()
                        r2["CENTRO COSTO"] = "Fca de Empanadas"
                        r2["SALDO_REAL"] = traslado
                        generadas.append(r2)

        for f in generadas: filas_finales.append(f)
        if not borrar:
            if dash_cc == "Total Empresa" or row["CENTRO COSTO"] == dash_cc:
                filas_finales.append(row)

    # 4. Agregación para Dashboard
    df_fin = pd.DataFrame(filas_finales)
    
    ultimo_mes = fecha_max.strftime("%Y-%m")
    
    # --- CAMBIO AQUÍ: Calculamos el mes del año ANTERIOR para comparar ---
    mes_anio_anterior = (fecha_max - pd.DateOffset(years=1)).strftime("%Y-%m")
    # ---------------------------------------------------------------------
    
    def calc_kpis(dframe, periodo):
        if dframe.empty: return 0, 0, 0, 0
        d_p = dframe[dframe["PERIODO_STR"] == periodo]
        ingresos = d_p[d_p["CUENTA"].str.startswith("4")]["SALDO_REAL"].sum()
        gastos = d_p[d_p["CUENTA"].str.startswith("3")]["SALDO_REAL"].sum()
        resultado = ingresos + gastos 
        margen = (resultado / ingresos * 100) if ingresos > 0 else 0
        return ingresos, gastos, resultado, margen

    i_act, g_act, r_act, m_act = calc_kpis(df_fin, ultimo_mes)
    i_ant, g_ant, r_ant, m_ant = calc_kpis(df_fin, mes_anio_anterior) # Usamos el año anterior

    kpis = {
        "venta": i_act,
        # La variación ahora es interanual
        "var_venta": ((i_act - i_ant)/i_ant*100) if i_ant > 0 else 0,
        "resultado": r_act,
        "var_resultado": ((r_act - r_ant)/abs(r_ant)*100) if abs(r_ant) > 0 else 0,
        "margen": m_act,
        "costo_total": g_act
    }

    # Gráficos
    df_fin["MES_NUM"] = pd.to_datetime(df_fin["PERIODO_STR"] + "-01").dt.month
    df_fin["YEAR"] = pd.to_datetime(df_fin["PERIODO_STR"] + "-01").dt.year
    
    df_ing = df_fin[df_fin["CUENTA"].str.startswith("4")]
    
    ventas_actual = df_ing[df_ing["YEAR"] == anio_actual].groupby("MES_NUM")["SALDO_REAL"].sum().reindex(range(1,13), fill_value=0)
    ventas_anterior = df_ing[df_ing["YEAR"] == anio_anterior].groupby("MES_NUM")["SALDO_REAL"].sum().reindex(range(1,13), fill_value=0)

    # Mix Gastos
    mix_gastos = {}
    df_mes_gasto = df_fin[(df_fin["PERIODO_STR"] == ultimo_mes) & (df_fin["CUENTA"].str.startswith("3"))]
    
    mapa_macro = {}
    for g in grupos_config:
        macro = g.get("macro_categoria", "Otros")
        for c in g["cuentas"]: mapa_macro[str(c)] = macro
            
    for _, r in df_mes_gasto.iterrows():
        m = mapa_macro.get(r["CUENTA"], "Sin Clasificar")
        mix_gastos[m] = mix_gastos.get(m, 0) + abs(r["SALDO_REAL"])

    mix_ordenado = sorted(mix_gastos.items(), key=lambda x: x[1], reverse=True)
    labels_mix = [x[0] for x in mix_ordenado[:5]]
    data_mix = [x[1] for x in mix_ordenado[:5]]

    charts = {
        "season_labels": ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"],
        "season_actual": ventas_actual.tolist(),
        "season_prev": ventas_anterior.tolist(),
        "mix_labels": labels_mix,
        "mix_data": data_mix
    }
    
    todos_cc = sorted(list(set(obtener_datos("mayor")["CENTRO COSTO"].dropna().unique())))

    return render_template(
        "contab/dashboard_gestion.html",
        dash_cc=dash_cc,
        todos_cc=todos_cc,
        kpis=kpis,
        charts=charts,
        ultimo_mes=ultimo_mes,
        anio_actual=anio_actual,
        anio_anterior=anio_anterior
    )
    
@contab_bp.route("/api/config_cuenta_global", methods=["POST"])
@login_requerido
def api_config_cuenta_global():
    """
    Agrega o elimina una cuenta de la configuración global de prorrateos.
    JSON: { "nombre": "Combustible", "tipo": "MANUAL_SUCURSAL", "accion": "agregar"|"eliminar" }
    """
    data = request.get_json()
    nombre = data.get("nombre")
    tipo = data.get("tipo", "MANUAL_SUCURSAL")
    accion = data.get("accion") # 'agregar' o 'eliminar'

    if not nombre or not accion:
        return {"ok": False, "error": "Datos incompletos"}, 400

    prorrateos = cargar_prorrateos()
    config = prorrateos.setdefault("config_cuentas", {})

    if accion == "agregar":
        config[nombre] = {
            "tipo": tipo,
            "activo": True
        }
    elif accion == "eliminar":
        # Si existe, lo sacamos del diccionario
        if nombre in config:
            del config[nombre]

    guardar_prorrateos(prorrateos)
    return {"ok": True}