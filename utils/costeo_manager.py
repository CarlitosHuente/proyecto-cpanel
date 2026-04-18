import os
import json
from flask import current_app
import copy

COSTEO_FILENAME = "costeo_reglas.json"

def _ruta_archivo():
    # Guardamos el JSON en la misma carpeta segura que los prorrateos contables
    ruta = current_app.config.get("UPLOAD_FOLDER_CONTAB", "tmp")
    os.makedirs(ruta, exist_ok=True)
    return os.path.join(ruta, COSTEO_FILENAME)

def cargar_reglas():
    ruta = _ruta_archivo()
    if not os.path.exists(ruta):
        return {
            "mapeo_cuentas": {},
            "costos_directos_base": {},
            "reglas_gastos": {}
        }
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "mapeo_cuentas": {},
            "costos_directos_base": {},
            "reglas_gastos": {}
        }

def guardar_reglas(data):
    ruta = _ruta_archivo()
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def guardar_mapeo(producto, cuenta):
    data = cargar_reglas()
    if cuenta:
        data["mapeo_cuentas"][producto] = cuenta
    else:
        data["mapeo_cuentas"].pop(producto, None) # Desmapear si viene vacío
    guardar_reglas(data)

def guardar_costo_directo(producto, costo, periodo):
    data = cargar_reglas()
    
    if "costos_directos_base" not in data:
        data["costos_directos_base"] = {}
        
    # Migración legacy a formato diccionario de periodos
    for p, v in list(data["costos_directos_base"].items()):
        if not isinstance(v, dict):
            data["costos_directos_base"][p] = {"2000-01": float(v)}
            
    if producto not in data["costos_directos_base"]:
        data["costos_directos_base"][producto] = {}
        
    if costo == "" or costo is None:
        data["costos_directos_base"][producto].pop(periodo, None)
    else:
        try:
            data["costos_directos_base"][producto][periodo] = float(costo)
        except ValueError:
            data["costos_directos_base"][producto].pop(periodo, None)
    guardar_reglas(data)

def obtener_costos_efectivos(periodo):
    data = cargar_reglas()
    costos_efectivos = {}
    costos_propios = {}
    
    for prod, historico in data.get("costos_directos_base", {}).items():
        if isinstance(historico, dict):
            validos = [p for p in historico.keys() if p <= periodo]
            if validos:
                max_p = max(validos)
                costos_efectivos[prod] = historico[max_p]
                costos_propios[prod] = (max_p == periodo)
        else:
            costos_efectivos[prod] = float(historico)
            costos_propios[prod] = False
            
    return costos_efectivos, costos_propios

def guardar_regla_gasto(sucursal, escenario, cuenta, regla_data):
    data = cargar_reglas()
    if "reglas_gastos" not in data: data["reglas_gastos"] = {}
    if sucursal not in data["reglas_gastos"]: data["reglas_gastos"][sucursal] = {}
    if escenario not in data["reglas_gastos"][sucursal]: data["reglas_gastos"][sucursal][escenario] = {}
    
    data["reglas_gastos"][sucursal][escenario][cuenta] = regla_data
    guardar_reglas(data)

def copiar_reglas_gastos(sucursal_origen, esc_origen, sucursal_destino, esc_destino):
    data = cargar_reglas()
    reglas_origen = data.get("reglas_gastos", {}).get(sucursal_origen, {}).get(esc_origen, {})
    
    if "reglas_gastos" not in data: data["reglas_gastos"] = {}
    if sucursal_destino not in data["reglas_gastos"]: data["reglas_gastos"][sucursal_destino] = {}
    
    data["reglas_gastos"][sucursal_destino][esc_destino] = copy.deepcopy(reglas_origen)
    guardar_reglas(data)

def guardar_prorrateo_adm(distribucion):
    data = cargar_reglas()
    data["prorrateo_adm"] = distribucion
    guardar_reglas(data)

def obtener_prorrateo_adm():
    data = cargar_reglas()
    return data.get("prorrateo_adm", {})