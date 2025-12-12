import os
import base64
import requests
import pandas as pd
import json
import tempfile
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, send_from_directory, flash, current_app, send_file
from utils.auth import login_requerido, permiso_modulo
from utils.sheet_cache import obtener_datos

contab_bp = Blueprint("contab", __name__, url_prefix="/contab")

# ==============================================================================
# 1. CONSTANTES Y CONFIGURACIÓN DE ARCHIVOS
# ==============================================================================

COMENTARIOS_FILE_NAME = "comentarios_comparativo.json"
PRORRATEOS_FILENAME = "prorrateos.json"
CLASIFICACIONES_FILENAME = "clasificaciones.json"

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

URL_WEBHOOK_SCRIPT = "https://script.google.com/macros/s/AKfycbxUK2SQ_fDaX1wEcTDLfnefcZPCZDp3A5rrqd2gZ6KBHV7qbBuysYTXltBBLXraNGj7/exec"

# ==============================================================================
# 2. FUNCIONES HELPER (CARGA/GUARDA DATOS)
# ==============================================================================

def _ruta_archivo(filename):
    ruta = current_app.config["UPLOAD_FOLDER_CONTAB"]
    os.makedirs(ruta, exist_ok=True)
    return os.path.join(ruta, filename)

def cargar_json(filename, default=None):
    if default is None: default = {}
    ruta = _ruta_archivo(filename)
    if not os.path.exists(ruta): return default
    try:
        with open(ruta, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def guardar_json(filename, data):
    ruta = _ruta_archivo(filename)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def cargar_prorrateos(): return cargar_json(PRORRATEOS_FILENAME, {"config_cuentas": {}, "reglas_mensuales": {}})
def guardar_prorrateos(data): guardar_json(PRORRATEOS_FILENAME, data)
def cargar_clasificaciones(): return cargar_json(CLASIFICACIONES_FILENAME, {"grupos": []})
def guardar_clasificaciones(data): guardar_json(CLASIFICACIONES_FILENAME, data)
def cargar_comentarios(): return cargar_json(COMENTARIOS_FILE_NAME, {})
def guardar_comentarios(data): guardar_json(COMENTARIOS_FILE_NAME, data)

def enviar_archivo_a_script(path_archivo):
    with open(path_archivo, "rb") as f:
        archivo_base64 = base64.b64encode(f.read()).decode("utf-8")
    try:
        response = requests.post(URL_WEBHOOK_SCRIPT, data=archivo_base64)
        return response.text
    except Exception as e:
        return f"ERROR: {e}"

# ==============================================================================
# 3. RUTAS DE ADMINISTRACIÓN Y ARCHIVOS
# ==============================================================================

@contab_bp.route("/archivos", methods=["GET", "POST"])
@login_requerido
@permiso_modulo("contab")
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

@contab_bp.route("/descargar_mayor")
@login_requerido
@permiso_modulo("contab")
def descargar_mayor():
    ruta = current_app.config['UPLOAD_FOLDER_CONTAB']
    return send_from_directory(ruta, "mayor.xlsx", as_attachment=True)

@contab_bp.route("/eliminar_mayor")
@login_requerido
@permiso_modulo("contab")
def eliminar_mayor():
    ruta = current_app.config['UPLOAD_FOLDER_CONTAB']
    try:
        os.remove(os.path.join(ruta, "mayor.xlsx"))
        flash("Archivo eliminado.", "warning")
    except:
        flash("No se pudo eliminar.", "danger")
    return redirect(url_for("contab.archivos"))

@contab_bp.route("/descargar_detalle")
@login_requerido
@permiso_modulo("contab")
def descargar_detalle():
    fecha_corte = request.args.get("fecha_corte")
    centro_costo = request.args.get("centro_costo", "Todos")
    clasif = request.args.get("clasificacion", "Todas")
    
    df = obtener_datos("mayor")
    excluir = ["COMPROBANTE DE APERTURA", "COMPROBANTE DE CIERRE", "COMPROBANTE DE REGULARIZACIÓN"]
    df["CONCEPTO"] = df["CONCEPTO"].astype(str).str.upper()
    df = df[~df["CONCEPTO"].isin(excluir)]

    if fecha_corte: 
        df["FECHA"] = pd.to_datetime(df["FECHA"])
        df = df[df["FECHA"] <= pd.to_datetime(fecha_corte)]
    
    if centro_costo != "Todos": 
        df = df[df["CENTRO COSTO"].astype(str).str.strip().str.upper() == centro_costo.upper()]
    
    df["CUENTA"] = df["CUENTA"].astype(str)
    df["CLASIFICACION"] = df["CUENTA"].str[0].map({"1": "Activo", "2": "Pasivo", "3": "Gastos", "4": "Ingresos"}).fillna("Otros")
    if clasif != "Todas": df = df[df["CLASIFICACION"] == clasif]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        df.to_excel(tmp.name, index=False)
        return send_file(tmp.name, as_attachment=True, download_name="detalle.xlsx")

# ==============================================================================
# 4. RUTAS DE CONFIGURACIÓN (PRORRATEOS Y CLASIFICACIÓN)
# ==============================================================================

@contab_bp.route("/prorrateos")
@login_requerido
@permiso_modulo("contab")
def prorrateos():
    periodo = request.args.get("periodo") or datetime.now().strftime("%Y-%m")
    pestaña = request.args.get("tab", "cc")

    data = cargar_prorrateos()
    config_cuentas = data.setdefault("config_cuentas", {})
    reglas_mensuales = data.setdefault("reglas_mensuales", {})

    for nombre, tipo in DEFAULT_CONFIG_CUENTAS.items():
        if nombre not in config_cuentas: config_cuentas[nombre] = {"tipo": tipo, "activo": True}

    cuentas_serv_generales = []
    centros_disponibles = []
    cuentas_prorrateo = []
    gastos_fabrica = []
    gastos_costanera_compartidos = []
    todas_las_cuentas = []
    
    ventas_totales = 0.0
    ventas_por_cc = {}
    total_gastos_fabrica = 0.0
    costo_unitario_empanada = 0.0
    total_costanera_origen = 0.0
    total_costanera_a_fabrica = 0.0
    costo_unitario_empanada_estimado = 0.0

    reglas_periodo = reglas_mensuales.get(periodo, {})
    fabrica_cfg = data.get("fabrica_empanadas", {})
    costeo_periodo = fabrica_cfg.get("costeo_periodos", {}).get(periodo, {})
    prorrateo_costanera_periodo = fabrica_cfg.get("costanera_prorrateos", {}).get(periodo, {})
    
    empanadas_elaboradas = costeo_periodo.get("empanadas_elaboradas", 0)
    empanadas_compradas = costeo_periodo.get("empanadas_compradas", 0)

    lista_config_cuentas = []
    for nombre, cfg in sorted(config_cuentas.items(), key=lambda x: x[0].lower()):
        lista_config_cuentas.append({
            "nombre": nombre, "tipo": cfg.get("tipo", ""), "activo": bool(cfg.get("activo", True))
        })

    df = obtener_datos("mayor")
    if not df.empty:
        df["CUENTA_STR"] = df["CUENTA"].astype(str)
        todas_las_cuentas = sorted(df[df["CUENTA_STR"].str.startswith("3")]["NOMBRE"].dropna().unique().tolist())

        df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
        y, m = map(int, periodo.split("-"))
        df_mes = df[(df["FECHA"].dt.year == y) & (df["FECHA"].dt.month == m)].copy()

        if not df_mes.empty:
            for col in ["DEBE", "HABER"]: df_mes[col] = pd.to_numeric(df_mes[col], errors="coerce").fillna(0)
            df_mes["SALDO"] = df_mes["DEBE"] - df_mes["HABER"]
            df_mes["CENTRO COSTO"] = df_mes["CENTRO COSTO"].astype(str)
            
            df_v = df_mes[df_mes["CUENTA"].astype(str).str.startswith("41")]
            if not df_v.empty:
                # FIX: .astype(float) para evitar errores de JSON con int64
                ventas_por_cc = df_v.groupby("CENTRO COSTO")["SALDO"].sum().astype(float).to_dict()
                ventas_totales = sum(ventas_por_cc.values())

            centros_disponibles = sorted([c for c in df_mes["CENTRO COSTO"].unique() if c.strip().lower() != "servicios generales"])

            df_sg = df_mes[df_mes["CENTRO COSTO"].str.lower().str.strip() == "servicios generales"]
            if not df_sg.empty:
                for _, r in df_sg.groupby("NOMBRE")["SALDO"].sum().reset_index().iterrows():
                    cuentas_serv_generales.append({
                        "nombre": r["NOMBRE"], "monto": float(r["SALDO"]), 
                        "tiene_regla": r["NOMBRE"] in reglas_periodo.get("serv_generales", {})
                    })

            saldos_cta = df_mes.groupby("NOMBRE")["SALDO"].sum().astype(float).to_dict()
            for nom, cfg in config_cuentas.items():
                if cfg.get("activo"):
                    cuentas_prorrateo.append({
                        "nombre": nom, "tipo": cfg.get("tipo"), "monto": saldos_cta.get(nom, 0),
                        "tiene_regla": bool(reglas_periodo.get("cuentas_globales", {}).get(nom))
                    })

            aliases_fab = ["fca empanadas", "fca de empanadas", "fabrica empanadas"]
            df_fab = df_mes[df_mes["CENTRO COSTO"].str.lower().str.strip().isin(aliases_fab)]
            if not df_fab.empty:
                res_fab = df_fab.groupby(["CUENTA", "NOMBRE"])["SALDO"].sum().reset_index().sort_values("SALDO", ascending=False)
                for _, r in res_fab.iterrows():
                    gastos_fabrica.append({"cuenta": r["CUENTA"], "nombre": r["NOMBRE"], "monto": float(r["SALDO"])})
                total_gastos_fabrica = float(df_fab["SALDO"].sum())
                if empanadas_elaboradas: costo_unitario_empanada = total_gastos_fabrica / empanadas_elaboradas

            aliases_cost = ["costanera center", "costanera"]
            df_cost = df_mes[df_mes["CENTRO COSTO"].str.lower().str.strip().isin(aliases_cost)]
            if not df_cost.empty:
                res_cost = df_cost.groupby(["CUENTA", "NOMBRE"])["SALDO"].sum().reset_index().sort_values("SALDO", ascending=False)
                total_costanera_origen = float(df_cost["SALDO"].sum())
                for _, r in res_cost.iterrows():
                    pct = float(prorrateo_costanera_periodo.get(str(r["CUENTA"]), 0))
                    est = float(r["SALDO"]) * pct
                    total_costanera_a_fabrica += est
                    gastos_costanera_compartidos.append({
                        "cuenta": str(r["CUENTA"]), "nombre": r["NOMBRE"], "monto": float(r["SALDO"]),
                        "porcentaje": pct, "monto_estimado": est
                    })
                if empanadas_elaboradas:
                    costo_unitario_empanada_estimado = (total_gastos_fabrica + total_costanera_a_fabrica) / empanadas_elaboradas

    return render_template("contab/prorrateos.html", 
                           periodo=periodo, pestaña=pestaña, 
                           cuentas_serv_generales=cuentas_serv_generales, centros_disponibles=centros_disponibles,
                           config_cuentas=lista_config_cuentas, cuentas_prorrateo=cuentas_prorrateo, reglas_cuentas=reglas_periodo.get("cuentas_globales", {}),
                           gastos_fabrica=gastos_fabrica, total_gastos_fabrica=total_gastos_fabrica,
                           empanadas_elaboradas=empanadas_elaboradas, empanadas_compradas=empanadas_compradas,
                           costo_unitario_empanada=costo_unitario_empanada,
                           gastos_costanera_compartidos=gastos_costanera_compartidos,
                           total_costanera_origen=total_costanera_origen, total_costanera_a_fabrica=total_costanera_a_fabrica,
                           costo_unitario_empanada_estimado=costo_unitario_empanada_estimado,
                           ventas_totales=ventas_totales, ventas_por_cc=ventas_por_cc,
                           todas_las_cuentas=todas_las_cuentas)

@contab_bp.route("/clasificacion_cuentas")
@login_requerido
@permiso_modulo("contab")
def clasificacion_cuentas():
    df = obtener_datos("mayor")
    cuentas_en_mayor = []
    mapa_nombres = {}
    if not df.empty:
        df["CUENTA"] = df["CUENTA"].astype(str).str.strip()
        df["NOMBRE"] = df["NOMBRE"].astype(str).str.strip()
        mask = df["CUENTA"].str.startswith(('3', '4'))
        temp = df[mask][["CUENTA", "NOMBRE"]].drop_duplicates().sort_values("CUENTA")
        for _, row in temp.iterrows():
            mapa_nombres[row["CUENTA"]] = row["NOMBRE"]
            cuentas_en_mayor.append({"CUENTA": row["CUENTA"], "NOMBRE": row["NOMBRE"]})

    data_clasif = cargar_clasificaciones()
    grupos_enriquecidos = []
    cuentas_usadas = set()
    for g in data_clasif.get("grupos", []):
        cuentas_info = []
        for cid in g.get("cuentas", []):
            cuentas_usadas.add(str(cid))
            cuentas_info.append({"id": cid, "nombre": mapa_nombres.get(str(cid), "(Sin nombre)")})
        grupos_enriquecidos.append({
            "nombre": g["nombre"], "macro_categoria": g.get("macro_categoria", "Otros"),
            "tipo": g["tipo"], "cuentas": cuentas_info
        })
    pendientes = [c for c in cuentas_en_mayor if c["CUENTA"] not in cuentas_usadas]
    return render_template("contab/clasificacion.html", grupos=grupos_enriquecidos, cuentas_pendientes=pendientes)

# ----------------- APIs DE GUARDADO -----------------

@contab_bp.route("/api/config_cuenta_global", methods=["POST"])
@login_requerido
@permiso_modulo("contab")
def api_config_cuenta_global():
    data = request.get_json()
    nombre, tipo, accion = data.get("nombre"), data.get("tipo", "MANUAL_SUCURSAL"), data.get("accion")
    if not nombre or not accion: return {"ok": False}, 400
    prorrateos = cargar_prorrateos()
    config = prorrateos.setdefault("config_cuentas", {})
    if accion == "agregar": config[nombre] = {"tipo": tipo, "activo": True}
    elif accion == "eliminar": 
        if nombre in config: del config[nombre]
    guardar_prorrateos(prorrateos)
    return {"ok": True}

@contab_bp.route("/api/guardar_clasificacion", methods=["POST"])
@login_requerido
@permiso_modulo("contab")
def api_guardar_clasificacion():
    data = request.get_json()
    if not data or "grupos" not in data: return {"ok": False}, 400
    guardar_clasificaciones(data)
    return {"ok": True}

@contab_bp.route("/api/prorrateos/serv_generales", methods=["POST"])
@login_requerido
@permiso_modulo("contab")
def api_guardar_prorrateo_serv_generales():
    payload = request.get_json(force=True)
    periodo, cuenta, dist = payload.get("periodo"), payload.get("cuenta"), payload.get("distribucion")
    if not periodo or not cuenta: return {"ok": False}, 400
    data = cargar_prorrateos()
    data.setdefault("reglas_mensuales", {}).setdefault(periodo, {}).setdefault("serv_generales", {})[cuenta] = dist
    guardar_prorrateos(data)
    return {"ok": True}

@contab_bp.route("/api/prorrateos/cuenta_manual", methods=["POST"])
@login_requerido
@permiso_modulo("contab")
def api_guardar_prorrateo_cuenta_manual():
    payload = request.get_json(force=True)
    periodo, cuenta, dist = payload.get("periodo"), payload.get("cuenta"), payload.get("distribucion")
    if not periodo or not cuenta: return {"ok": False}, 400
    data = cargar_prorrateos()
    data.setdefault("reglas_mensuales", {}).setdefault(periodo, {}).setdefault("cuentas_globales", {})[cuenta] = dist
    guardar_prorrateos(data)
    return {"ok": True}

@contab_bp.route("/api/prorrateos/fabrica_costeo", methods=["POST"])
@login_requerido
@permiso_modulo("contab")
def api_guardar_prorrateo_fabrica():
    payload = request.get_json(force=True)
    periodo = payload.get("periodo")
    if not periodo: return {"ok": False}, 400
    data = cargar_prorrateos()
    data.setdefault("fabrica_empanadas", {}).setdefault("costeo_periodos", {})[periodo] = {
        "empanadas_elaboradas": float(payload.get("empanadas_elaboradas", 0)),
        "empanadas_compradas": float(payload.get("empanadas_compradas", 0))
    }
    guardar_prorrateos(data)
    return {"ok": True}

@contab_bp.route("/api/prorrateos/fabrica_costanera", methods=["POST"])
@login_requerido
@permiso_modulo("contab")
def api_guardar_prorrateo_fabrica_costanera():
    payload = request.get_json(force=True)
    periodo, reglas = payload.get("periodo"), payload.get("reglas", {})
    if not periodo: return {"ok": False}, 400
    reglas_limpias = {str(k): float(v) for k, v in reglas.items()}
    data = cargar_prorrateos()
    data.setdefault("fabrica_empanadas", {}).setdefault("costanera_prorrateos", {})[periodo] = reglas_limpias
    guardar_prorrateos(data)
    return {"ok": True}

@contab_bp.route("/guardar_comentario", methods=["POST"])
@login_requerido
@permiso_modulo("contab")
def guardar_comentario_api():
    data = request.get_json()
    nombre, periodo, centro = data.get("nombre"), data.get("periodo"), data.get("centro_costo")
    if not nombre: return {"ok": False}, 400
    comentarios = cargar_comentarios()
    key = f"{nombre}||{centro}||{periodo}"
    if data.get("comentario"): comentarios[key] = data.get("comentario")
    else: comentarios.pop(key, None)
    guardar_comentarios(comentarios)
    return {"ok": True}

# ==============================================================================
# 6. REPORTES GERENCIALES (MOTOR CENTRALIZADO)
# ==============================================================================

def calcular_matriz_gestion(df, periodo, switch_sg, switch_fab, data_config):
    """
    Función CENTRALIZADA que aplica toda la matemática de prorrateos.
    Devuelve un DataFrame 'df_procesado' listo para ser agrupado.
    """
    config_cuentas = data_config.get("config_cuentas", {})
    reglas_mensuales = data_config.get("reglas_mensuales", {})
    costanera_prorrateos = data_config.get("fabrica_empanadas", {}).get("costanera_prorrateos", {})

    pool_sg = {}
    pool_fab = {}
    for p, d in reglas_mensuales.items():
        if "serv_generales" in d: pool_sg[p] = d["serv_generales"]
    for p, d in costanera_prorrateos.items(): pool_fab[p] = d

    def get_regla(pool, per):
        if per in pool: return pool[per]
        ants = [p for p in pool.keys() if p < per]
        return pool[max(ants)] if ants else {}

    # Pre-cálculos Ventas
    df_ventas = df[df["CUENTA"].str.startswith("41")]
    # Ventas totales por mes (para ratio global)
    vtas_tot_mes = df_ventas[df_ventas["SALDO_REAL"] > 0].groupby("PERIODO_STR")["SALDO_REAL"].sum().to_dict()
    # Ventas por sucursal por mes (para ratio específico)
    vtas_suc_mes = df_ventas[df_ventas["SALDO_REAL"] > 0].groupby(["PERIODO_STR", "CENTRO COSTO"])["SALDO_REAL"].sum().to_dict()

    # Ratios Empanada (4101004)
    dist_empanadas = {}
    df_emp = df[df["CUENTA"] == "4101004"]
    if not df_emp.empty:
        grupos = df_emp.groupby(["PERIODO_STR", "CENTRO COSTO"])["SALDO_REAL"].sum()
        for per in grupos.index.get_level_values(0).unique():
            v_mes = grupos[per]
            tot = v_mes.sum()
            if tot > 0: dist_empanadas[per] = (v_mes / tot).to_dict()

    mov_fab = df[(df["CUENTA"]=="3101002") & (abs(df["SALDO_REAL"])>1)]
    meses_activos_fab = set(mov_fab["PERIODO_STR"].unique())

    filas_finales = []
    filas_trabajo = df.to_dict("records")
    cache_sg = {}
    cache_fab = {}

    for row in filas_trabajo:
        per = row["PERIODO_STR"]
        cc = row["CENTRO COSTO"]
        nom = row["NOMBRE"]
        monto = row["SALDO_REAL"]
        
        # --- 1. CUENTAS GLOBALES ---
        cfg = config_cuentas.get(nom)
        es_global_procesada = False
        
        if cfg and cfg.get("activo"):
            tipo = cfg["tipo"]
            es_global_procesada = True
            
            # Caso Ventas (Automático)
            if tipo == "VENTAS_SUCURSAL":
                tot = vtas_tot_mes.get(per, 0)
                if tot > 0:
                    keys_periodo = [k for k in vtas_suc_mes.keys() if k[0] == per]
                    for key in keys_periodo:
                        cc_dest = key[1]
                        venta_suc = vtas_suc_mes[key]
                        asig = monto * (venta_suc / tot)
                        if asig != 0:
                            r = row.copy()
                            r["CENTRO COSTO"] = cc_dest
                            r["SALDO_REAL"] = asig
                            filas_finales.append(r)
                else:
                    filas_finales.append(row)

            # Caso Manual
            elif tipo == "MANUAL_SUCURSAL":
                reglas_glob_mes = reglas_mensuales.get(per, {}).get("cuentas_globales", {})
                if nom in reglas_glob_mes:
                    dist = reglas_glob_mes[nom]
                    for dst, pct in dist.items():
                        asig = monto * pct
                        if asig != 0:
                            r = row.copy()
                            r["CENTRO COSTO"] = dst
                            r["SALDO_REAL"] = asig
                            filas_finales.append(r)
                else:
                    es_global_procesada = False # Si no tiene regla, pasa normal

        if es_global_procesada: continue

        # --- 2. SWITCHES ---
        generadas = []
        borrar = False
        
        # A. SG
        if switch_sg and "servicios generales" in cc.lower():
            if per not in cache_sg: cache_sg[per] = get_regla(pool_sg, per)
            reg = cache_sg[per].get(nom)
            if reg:
                borrar = True
                for dst, pct in reg.items():
                    n = row.copy()
                    n["CENTRO COSTO"] = dst
                    n["SALDO_REAL"] = monto * pct
                    generadas.append(n)

        # B. Fábrica
        elif switch_fab:
            es_costanera = "costanera" in cc.lower()
            es_fabrica = "fca" in cc.lower() or "fabrica" in cc.lower()
            
            if per in meses_activos_fab:
                # Caso B1: Costanera -> Sucursales
                if es_costanera:
                    if per not in cache_fab: cache_fab[per] = get_regla(pool_fab, per)
                    pct = cache_fab[per].get(row["CUENTA"])
                    
                    if pct and pct > 0:
                        traslado = monto * pct
                        r1 = row.copy()
                        r1["SALDO_REAL"] = -traslado
                        generadas.append(r1)
                        
                        mapa_ventas = dist_empanadas.get(per, {})
                        if mapa_ventas:
                            for cc_dest, ratio in mapa_ventas.items():
                                r2 = row.copy()
                                r2["CENTRO COSTO"] = cc_dest
                                r2["CUENTA"] = "3101002"
                                r2["NOMBRE"] = f"{nom} (Absorbido Fca)"
                                r2["SALDO_REAL"] = traslado * ratio
                                generadas.append(r2)
                        else:
                            r2 = row.copy()
                            r2["CENTRO COSTO"] = "Fca de Empanadas"
                            r2["CUENTA"] = "3101002"
                            r2["SALDO_REAL"] = traslado
                            generadas.append(r2)

                # Caso B2: Vaciar Fábrica -> Sucursales
                elif es_fabrica:
                    mapa_ventas = dist_empanadas.get(per, {})
                    if mapa_ventas:
                        borrar = True 
                        for cc_dest, ratio in mapa_ventas.items():
                            n = row.copy()
                            n["CENTRO COSTO"] = cc_dest
                            n["CUENTA"] = "3101002"
                            n["NOMBRE"] = f"{nom} (Absorbido Fca)"
                            n["SALDO_REAL"] = monto * ratio
                            generadas.append(n)

        for f in generadas: filas_finales.append(f)
        if not borrar: filas_finales.append(row)

    return pd.DataFrame(filas_finales)

# --- RUTAS DE VISTAS ---

@contab_bp.route("/informe_gerencial")
@login_requerido
@permiso_modulo("reporte")
def informe_gerencial():
    df = obtener_datos("mayor")
    data_config = {"config_cuentas": cargar_prorrateos().get("config_cuentas", {}),
                   "reglas_mensuales": cargar_prorrateos().get("reglas_mensuales", {}),
                   "fabrica_empanadas": cargar_prorrateos().get("fabrica_empanadas", {})}
    data_clasif = cargar_clasificaciones()

    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    periodo = request.args.get("periodo")
    if not periodo:
        max_fecha = df["FECHA"].max() if not df.empty else datetime.now()
        periodo = max_fecha.strftime("%Y-%m") if pd.notna(max_fecha) else datetime.now().strftime("%Y-%m")

    # Filtros
    df["SALDO_REAL"] = (df["DEBE"] - df["HABER"]) * -1
    df["PERIODO_STR"] = df["FECHA"].dt.strftime("%Y-%m")
    df["CENTRO COSTO"] = df["CENTRO COSTO"].astype(str).str.strip()
    df["CUENTA"] = df["CUENTA"].astype(str).str.strip()
    df["NOMBRE"] = df["NOMBRE"].astype(str).str.strip()
    df = df[df["CUENTA"].str.startswith(('3', '4'))]
    df = df[df["PERIODO_STR"] == periodo].copy()

    switch_sg = request.args.get("distribuir_sg") == "on"
    switch_fab = request.args.get("ajuste_fabrica") == "on"
    
    df_final = calcular_matriz_gestion(df, periodo, switch_sg, switch_fab, data_config)
    
    todos_cc = sorted(list(set(obtener_datos("mayor")["CENTRO COSTO"].dropna().unique())))
    matriz = {}
    for _, row in df_final.iterrows():
        cta = row["CUENTA"]
        if cta not in matriz: matriz[cta] = {"nombre": row["NOMBRE"], "montos": {}}
        matriz[cta]["montos"][row["CENTRO COSTO"]] = matriz[cta]["montos"].get(row["CENTRO COSTO"], 0) + row["SALDO_REAL"]

    macros_data = {}
    for grp in data_clasif.get("grupos", []):
        m = grp.get("macro_categoria", "Otros")
        if m not in macros_data: macros_data[m] = {"grupos": [], "totales_cc": {c:0.0 for c in todos_cc}}
        fg = {"nombre": grp["nombre"], "tipo": grp["tipo"], "totales_cc": {c:0.0 for c in todos_cc}, "detalle_cuentas": []}
        for cta_id in grp["cuentas"]:
            cid = str(cta_id)
            if cid in matriz:
                data_cta = matriz[cid]
                for cc, val in data_cta["montos"].items():
                    fg["totales_cc"][cc] += val
                    macros_data[m]["totales_cc"][cc] += val
                fg["detalle_cuentas"].append({"codigo": cid, "nombre": data_cta["nombre"], "montos_cc": data_cta["montos"]})
        macros_data[m]["grupos"].append(fg)

    sin_clasif = {"nombre": "Pendientes", "totales_cc": {c:0.0 for c in todos_cc}, "detalle_cuentas": []}
    procesadas = set([str(c) for g in data_clasif.get("grupos", []) for c in g["cuentas"]])
    hay_pend = False
    for cta, data in matriz.items():
        if cta not in procesadas and sum(abs(v) for v in data["montos"].values()) > 1:
            hay_pend = True
            for cc, val in data["montos"].items(): sin_clasif["totales_cc"][cc] += val
            sin_clasif["detalle_cuentas"].append({"codigo": cta, "nombre": data["nombre"], "montos_cc": data["montos"]})
    if hay_pend:
        if "Sin Clasificar" not in macros_data: macros_data["Sin Clasificar"] = {"grupos": [], "totales_cc": {c:0.0 for c in todos_cc}}
        macros_data["Sin Clasificar"]["grupos"].append(sin_clasif)
        for cc in todos_cc: macros_data["Sin Clasificar"]["totales_cc"][cc] += sin_clasif["totales_cc"][cc]

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
    
    reporte = []
    cache = {}
    for l in ESTRUCTURA:
        f = {"titulo": l["titulo"], "tipo": l["tipo"], "color": l.get("color", "secondary"), "grupos": [], "totales_cc": {c:0.0 for c in todos_cc}}
        if l["tipo"] == "macro":
            enc = False
            for src in l["fuente"]:
                if src in macros_data:
                    d = macros_data[src]
                    f["grupos"].extend(d["grupos"])
                    for cc in todos_cc: f["totales_cc"][cc] += d["totales_cc"][cc]
                    enc = True
            cache[l["id"]] = f["totales_cc"]
            if enc or l["id"] == "otros": reporte.append(f)
        elif l["tipo"] == "calculo":
            for op in l["operacion"]:
                tot = cache.get(op, {})
                for cc in todos_cc: f["totales_cc"][cc] += tot.get(cc, 0)
            cache[l["id"]] = f["totales_cc"]
            reporte.append(f)

    return render_template("contab/informe_gerencial.html", periodo=periodo, reporte=reporte, columnas_cc=todos_cc, switch_sg=switch_sg, switch_fab=switch_fab)

@contab_bp.route("/comparativo_gestion")
@login_requerido
@permiso_modulo("reporte")
def comparativo_gestion():
    df = obtener_datos("mayor")
    data_config = {"config_cuentas": cargar_prorrateos().get("config_cuentas", {}),
                   "reglas_mensuales": cargar_prorrateos().get("reglas_mensuales", {}),
                   "fabrica_empanadas": cargar_prorrateos().get("fabrica_empanadas", {})}
    data_clasif = cargar_clasificaciones()

    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    comp_cc = request.args.get("comp_cc", "Total Empresa")
    comp_modo = request.args.get("comp_modo", "last_6")
    
    if not df.empty: fecha_fin = df["FECHA"].max()
    else: fecha_fin = datetime.now()

    cols = []
    if comp_modo == "last_6":
        for i in range(5, -1, -1): cols.append((fecha_fin - pd.DateOffset(months=i)).strftime("%Y-%m"))
    elif comp_modo == "last_12":
        for i in range(11, -1, -1): cols.append((fecha_fin - pd.DateOffset(months=i)).strftime("%Y-%m"))
    elif comp_modo == "anual":
        for i in range(2, -1, -1): cols.append(datetime(fecha_fin.year - i, fecha_fin.month, 1).strftime("%Y-%m"))

    df["SALDO_REAL"] = (df["DEBE"] - df["HABER"]) * -1
    df["PERIODO_STR"] = df["FECHA"].dt.strftime("%Y-%m")
    df["CENTRO COSTO"] = df["CENTRO COSTO"].astype(str).str.strip()
    df["CUENTA"] = df["CUENTA"].astype(str).str.strip()
    df["NOMBRE"] = df["NOMBRE"].astype(str).str.strip()
    df = df[df["CUENTA"].str.startswith(('3', '4'))]
    df = df[df["PERIODO_STR"].isin(cols)]

    switch_sg = request.args.get("distribuir_sg") == "on"
    switch_fab = request.args.get("ajuste_fabrica") == "on"

    # Calculo centralizado
    df_final = calcular_matriz_gestion(df, None, switch_sg, switch_fab, data_config)
    
    if comp_cc != "Total Empresa":
        df_final = df_final[df_final["CENTRO COSTO"] == comp_cc]

    matriz = {}
    for _, row in df_final.iterrows():
        cta = row["CUENTA"]
        p = row["PERIODO_STR"]
        if cta not in matriz: matriz[cta] = {"nombre": row["NOMBRE"], "montos": {}}
        matriz[cta]["montos"][p] = matriz[cta]["montos"].get(p, 0) + row["SALDO_REAL"]

    macros_data = {}
    for grp in data_clasif.get("grupos", []):
        m = grp.get("macro_categoria", "Otros")
        if m not in macros_data: macros_data[m] = {"grupos": [], "totales_col": {c:0.0 for c in cols}}
        fg = {"nombre": grp["nombre"], "tipo": grp["tipo"], "totales_col": {c:0.0 for c in cols}, "detalle_cuentas": []}
        for cta_id in grp["cuentas"]:
            cid = str(cta_id)
            if cid in matriz:
                data_cta = matriz[cid]
                for c in cols:
                    val = data_cta["montos"].get(c, 0)
                    fg["totales_col"][c] += val
                    macros_data[m]["totales_col"][c] += val
                fg["detalle_cuentas"].append({"codigo": cid, "nombre": data_cta["nombre"], "montos_col": data_cta["montos"]})
        macros_data[m]["grupos"].append(fg)

    sin_clasif = {"nombre": "Pendientes", "totales_col": {c:0.0 for c in cols}, "detalle_cuentas": []}
    procesadas = set([str(c) for g in data_clasif.get("grupos", []) for c in g["cuentas"]])
    hay_pend = False
    for cta, data in matriz.items():
        if cta not in procesadas and sum(abs(v) for v in data["montos"].values()) > 1:
            hay_pend = True
            for c in cols:
                val = data["montos"].get(c, 0)
                sin_clasif["totales_col"][c] += val
            sin_clasif["detalle_cuentas"].append({"codigo": cta, "nombre": data["nombre"], "montos_col": data["montos"]})
    if hay_pend:
        if "Sin Clasificar" not in macros_data: macros_data["Sin Clasificar"] = {"grupos": [], "totales_col": {c:0.0 for c in cols}}
        macros_data["Sin Clasificar"]["grupos"].append(sin_clasif)
        for c in cols: macros_data["Sin Clasificar"]["totales_col"][c] += sin_clasif["totales_col"][c]

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

    reporte = []
    cache = {}
    for l in ESTRUCTURA:
        f = {"titulo": l["titulo"], "tipo": l["tipo"], "color": l.get("color", "secondary"), "grupos": [], "totales_col": {c:0.0 for c in cols}}
        if l["tipo"] == "macro":
            enc = False
            for src in l["fuente"]:
                if src in macros_data:
                    d = macros_data[src]
                    f["grupos"].extend(d["grupos"])
                    for c in cols: f["totales_col"][c] += d["totales_col"][c]
                    enc = True
            cache[l["id"]] = f["totales_col"]
            if enc or l["id"] == "otros": reporte.append(f)
        elif l["tipo"] == "calculo":
            for op in l["operacion"]:
                tot = cache.get(op, {})
                for c in cols: f["totales_col"][c] += tot.get(c, 0)
            cache[l["id"]] = f["totales_col"]
            reporte.append(f)

    todos_cc = sorted(list(set(obtener_datos("mayor")["CENTRO COSTO"].dropna().unique())))
    return render_template("contab/comparativo_gestion.html", reporte=reporte, columnas=cols, todos_cc=todos_cc, comp_cc=comp_cc, comp_modo=comp_modo, switch_sg=switch_sg, switch_fab=switch_fab)

@contab_bp.route("/dashboard_gestion")
@login_requerido
@permiso_modulo("reporte")
def dashboard_gestion():
    df = obtener_datos("mayor")
    data_config = {"config_cuentas": cargar_prorrateos().get("config_cuentas", {}),
                   "reglas_mensuales": cargar_prorrateos().get("reglas_mensuales", {}),
                   "fabrica_empanadas": cargar_prorrateos().get("fabrica_empanadas", {})}
    data_clasif = cargar_clasificaciones()
    grupos_config = data_clasif.get("grupos", [])

    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    if df.empty: return render_template("contab/dashboard_gestion.html", dash_cc="Total", kpis={}, charts={})

    per_solicitado = request.args.get("periodo")
    if per_solicitado:
        max_f = pd.to_datetime(per_solicitado + "-01") + pd.offsets.MonthEnd(0)
    else:
        max_f = df["FECHA"].max()

    anio_act = max_f.year
    anio_ant = anio_act - 1
    
    df["SALDO_REAL"] = (df["DEBE"] - df["HABER"]) * -1
    df["PERIODO_STR"] = df["FECHA"].dt.strftime("%Y-%m")
    df["CENTRO COSTO"] = df["CENTRO COSTO"].astype(str).str.strip()
    df["CUENTA"] = df["CUENTA"].astype(str).str.strip()
    df["NOMBRE"] = df["NOMBRE"].astype(str).str.strip()
    df = df[df["CUENTA"].str.startswith(('3', '4'))]
    df = df[df["FECHA"].dt.year >= anio_ant].copy()

    dash_cc = request.args.get("dash_cc", "Total Empresa")
    
    # Calculo centralizado (siempre ON para dashboard)
    df_final = calcular_matriz_gestion(df, None, True, True, data_config)
    
    if dash_cc != "Total Empresa":
        df_final = df_final[df_final["CENTRO COSTO"] == dash_cc]

    ult_mes_str = max_f.strftime("%Y-%m")
    ant_mes_str = (max_f - pd.DateOffset(years=1)).strftime("%Y-%m")

    def get_kpi(dframe, per):
        d = dframe[dframe["PERIODO_STR"] == per]
        i = d[d["CUENTA"].str.startswith("4")]["SALDO_REAL"].sum()
        g = d[d["CUENTA"].str.startswith("3")]["SALDO_REAL"].sum()
        res = i + g
        m = (res/i*100) if i > 0 else 0
        return i, g, res, m

    v_act, g_act, r_act, m_act = get_kpi(df_final, ult_mes_str)
    v_ant, _, r_ant, _ = get_kpi(df_final, ant_mes_str)

    kpis = {
        "venta": v_act,
        "var_venta": ((v_act - v_ant)/v_ant*100) if v_ant > 0 else 0,
        "resultado": r_act,
        "var_resultado": ((r_act - r_ant)/abs(r_ant)*100) if abs(r_ant) > 0 else 0,
        "margen": m_act,
        "costo_total": g_act
    }

    df_final["MES_NUM"] = pd.to_datetime(df_final["PERIODO_STR"] + "-01").dt.month
    df_final["YEAR"] = pd.to_datetime(df_final["PERIODO_STR"] + "-01").dt.year
    
    ing = df_final[df_final["CUENTA"].str.startswith("4")]
    v_curr = ing[ing["YEAR"] == anio_act].groupby("MES_NUM")["SALDO_REAL"].sum().reindex(range(1,13), fill_value=0)
    v_prev = ing[ing["YEAR"] == anio_ant].groupby("MES_NUM")["SALDO_REAL"].sum().reindex(range(1,13), fill_value=0)

    mix = {}
    gastos_mes = df_final[(df_final["PERIODO_STR"] == ult_mes_str) & (df_final["CUENTA"].str.startswith("3"))]
    mapa = {}
    for g in grupos_config:
        m = g.get("macro_categoria", "Otros")
        for c in g["cuentas"]: mapa[str(c)] = m
    
    for _, r in gastos_mes.iterrows():
        m = mapa.get(r["CUENTA"], "Sin Clasificar")
        mix[m] = mix.get(m, 0) + abs(r["SALDO_REAL"])
    
    mix_ord = sorted(mix.items(), key=lambda x: x[1], reverse=True)[:5]
    
    charts = {
        "season_labels": ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"],
        "season_actual": v_curr.tolist(),
        "season_prev": v_prev.tolist(),
        "mix_labels": [x[0] for x in mix_ord],
        "mix_data": [x[1] for x in mix_ord]
    }

    todos_cc = sorted(list(set(obtener_datos("mayor")["CENTRO COSTO"].dropna().unique())))
    return render_template("contab/dashboard_gestion.html", dash_cc=dash_cc, todos_cc=todos_cc, kpis=kpis, charts=charts, ultimo_mes=ult_mes_str, anio_actual=anio_act, anio_anterior=anio_ant)

@contab_bp.route("/comparativo")
@login_requerido
@permiso_modulo("contab")
def comparativo():
    fecha_corte = request.args.get("fecha_corte")
    clasif = request.args.get("clasificacion", "Todas")
    centro_costo = request.args.get("centro_costo", "Todos")
    modo = request.args.get("modo", "normal")

    df = obtener_datos("mayor")
    excluir = ["COMPROBANTE DE APERTURA", "COMPROBANTE DE CIERRE", "COMPROBANTE DE REGULARIZACIÓN"]
    df["CONCEPTO"] = df["CONCEPTO"].astype(str).str.upper()
    df = df[~df["CONCEPTO"].isin(excluir)]
    todos_centros = sorted(df["CENTRO COSTO"].astype(str).str.strip().unique().tolist())

    if centro_costo != "Todos": df = df[df["CENTRO COSTO"].astype(str).str.strip().str.upper() == centro_costo.upper()]
    if fecha_corte: df = df[df["FECHA"] <= pd.to_datetime(fecha_corte)]

    df["CUENTA"] = df["CUENTA"].astype(str)
    df["CLASIFICACION"] = df["CUENTA"].str[0].map({"3": "Gastos", "4": "Ingresos"}).fillna("Otros")
    if clasif != "Todas": df = df[df["CLASIFICACION"] == clasif]

    df["PERIODO_DT"] = df["FECHA"].apply(lambda x: datetime(x.year, x.month, 1))
    ultimos_12_dt = sorted(df["PERIODO_DT"].unique())[-12:]
    meses_es = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    etiquetas = [f"{meses_es[d.month - 1]}-{d.year}" for d in ultimos_12_dt]
    df["PERIODO"] = df["PERIODO_DT"].map(dict(zip(ultimos_12_dt, etiquetas)))

    pivot_raw = df[df["PERIODO"].isin(etiquetas)].groupby(["NOMBRE", "PERIODO"]).agg(DEBE=("DEBE", "sum"), HABER=("HABER", "sum")).reset_index()
    pivot_raw["SALDO"] = pivot_raw["DEBE"] - pivot_raw["HABER"]
    pivot = pivot_raw.pivot(index="NOMBRE", columns="PERIODO", values="SALDO").reindex(columns=etiquetas, fill_value=0).reset_index()
    
    datos_aux = df[["NOMBRE", "CUENTA", "CLASIFICACION"]].drop_duplicates()
    pivot = pd.merge(datos_aux, pivot, on="NOMBRE", how="right").sort_values("CUENTA")

    detalle_raw = df[df["PERIODO"].isin(etiquetas)].assign(SALDO_MES=lambda x: x["DEBE"] - x["HABER"]).groupby(["NOMBRE", "CENTRO COSTO", "PERIODO"], as_index=False).agg(SALDO_MES=("SALDO_MES", "sum"))
    pivot_cc = detalle_raw.pivot_table(index=["NOMBRE", "CENTRO COSTO"], columns="PERIODO", values="SALDO_MES", aggfunc="sum").reset_index()

    ratios_cc = {}
    alertas_macro = {}
    if not pivot_cc.empty:
        valores_cc = pivot_cc[etiquetas].replace(0, pd.NA)
        promedios_cc = valores_cc.mean(axis=1, skipna=True)
        for idx, row in pivot_cc.iterrows():
            nombre = row["NOMBRE"]
            centro = row["CENTRO COSTO"]
            prom = promedios_cc.iloc[idx]
            if pd.isna(prom) or prom == 0: continue
            for periodo in etiquetas:
                val = row[periodo]
                if pd.isna(val) or val == 0: continue
                ratio = float(val / prom)
                if ratio >= 1.3:
                    ratios_cc[f"{nombre}||{centro}||{periodo}"] = ratio
                    key_macro = f"{nombre}||{periodo}"
                    alertas_macro[key_macro] = alertas_macro.get(key_macro, 0) + 1

    columnas = ["NOMBRE"] + etiquetas
    final = pivot[columnas]
    centros_df = df[["NOMBRE", "CENTRO COSTO"]].drop_duplicates(subset=["NOMBRE"])
    final = pd.merge(final, centros_df, on="NOMBRE", how="left")

    detalle_raw_2 = df[df["PERIODO"].isin(etiquetas)].groupby(["NOMBRE", "CENTRO COSTO", "PERIODO"]).agg(DEBE=("DEBE", "sum"), HABER=("HABER", "sum")).reset_index()
    detalle_raw_2["SALDO"] = detalle_raw_2["DEBE"] - detalle_raw_2["HABER"]
    detalle = detalle_raw_2.pivot_table(index=["NOMBRE", "CENTRO COSTO"], columns="PERIODO", values="SALDO", fill_value=0).reset_index()

    return render_template("contab/comparativo.html", tabla=final.to_dict(orient="records"), columnas=columnas, fecha_corte=fecha_corte, clasificacion=clasif, centro_costo=centro_costo, centros=todos_centros, detalle=detalle.to_dict(orient="records"), modo=modo, alertas_macro=alertas_macro, ratios_cc=ratios_cc, comentarios=cargar_comentarios())