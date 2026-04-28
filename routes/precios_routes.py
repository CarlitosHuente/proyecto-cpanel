from flask import Blueprint, render_template, request, jsonify
from utils.auth import login_requerido, permiso_modulo
from utils.db import get_db_connection
from utils.precios_manager import cargar_precios, guardar_precios

precios_bp = Blueprint("precios", __name__, url_prefix="/ventas/precios")

@precios_bp.route("/")
@login_requerido
@permiso_modulo("ventas")
def vista_precios():
    # Extraemos el catálogo de productos actualizados desde la BD
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT p.nombre, p.es_mayorista, p.unidades_por_caja, c.nombre_categoria 
            FROM Productos p
            LEFT JOIN Categorias c ON p.categoria_id = c.categoria_id
            ORDER BY p.nombre ASC
        """)
        rows = cursor.fetchall()
        productos = []
        for r in rows:
            if isinstance(r, dict):
                productos.append(r)
            else:
                productos.append({'nombre': r[0], 'es_mayorista': r[1], 'unidades_por_caja': r[2], 'nombre_categoria': r[3]})
                
        cursor.execute("SELECT nombre_categoria FROM Categorias ORDER BY nombre_categoria ASC")
        cats = cursor.fetchall()
        categorias = [c['nombre_categoria'] if isinstance(c, dict) else c[0] for c in cats]
        
    conn.close()

    data = cargar_precios()
    listas = data.get("listas", [])
    precios = data.get("precios", {})

    return render_template("ventas/lista_precios.html", productos=productos, categorias=categorias, listas=listas, precios=precios)

@precios_bp.route("/agregar_lista", methods=["POST"])
@login_requerido
@permiso_modulo("ventas")
def agregar_lista():
    nombre = request.get_json().get("nombre", "").strip()
    if not nombre:
        return jsonify({"success": False, "error": "Nombre inválido"})
    
    data = cargar_precios()
    if nombre not in data["listas"]:
        data["listas"].append(nombre)
        guardar_precios(data)
        
    return jsonify({"success": True})

@precios_bp.route("/eliminar_lista", methods=["POST"])
@login_requerido
@permiso_modulo("ventas")
def eliminar_lista():
    nombre = request.get_json().get("nombre")
    data = cargar_precios()
    if nombre in data["listas"]:
        data["listas"].remove(nombre)
        # Limpiamos el nombre de esa lista dentro de cada producto
        for p in data["precios"]:
            data["precios"][p].pop(nombre, None)
        guardar_precios(data)
    return jsonify({"success": True})

@precios_bp.route("/guardar_matriz", methods=["POST"])
@login_requerido
@permiso_modulo("ventas")
def guardar_matriz():
    data_frontend = request.get_json()
    data = cargar_precios()
    data["precios"] = data_frontend.get("precios", {})
    guardar_precios(data)
    return jsonify({"success": True})

@precios_bp.route("/reordenar_listas", methods=["POST"])
@login_requerido
@permiso_modulo("ventas")
def reordenar_listas():
    req = request.get_json()
    dragged = req.get("dragged")
    target = req.get("target")
    
    data = cargar_precios()
    listas = data.get("listas", [])
    
    if dragged in listas and target in listas:
        listas.remove(dragged)
        listas.insert(listas.index(target), dragged)
        data["listas"] = listas
        guardar_precios(data)
        
    return jsonify({"success": True})