from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify
from flask import request
from datetime import datetime, timedelta
from utils.auth import login_requerido, permiso_modulo
from utils.db import get_db_connection

sucursales_bp = Blueprint('sucursales', __name__, url_prefix='/sucursales')

# --- CONFIGURACIÓN DE ACCESO MANUAL ---
ACCESO_SUCURSALES = {
    "carloscarvajal2.0@gmail.com": "TODAS",
    "jessicanoemiherrera@gmail.com": "TODAS",
    "becar.cristobal@gmail.com":"TODAS",
    "foodtrucklascondes@gmail.com": [1],
    "huentelauquenmut@gmail.com": [2],
    "huentelauquenplazaegana@gmail.com": [3],  
    "huentecostanera@gmail.com": [4],
    "conchali@gmail.com": [5],
    "sucursal1@huente.com":[1]  
}

@sucursales_bp.route("/pizarra")
@login_requerido
@permiso_modulo("sucursales")
def pizarra():
    if "usuario" not in session: return redirect(url_for("auth.login"))
    
    usuario_actual = session["usuario"]
    rol = session.get("rol", "invitado")
    
    # --- NUEVA LÓGICA AUTOMÁTICA ---
    sucursal_asignada = session.get("sucursal_id")
    
    permiso_sucursales = []

    if sucursal_asignada:
        permiso_sucursales = [int(sucursal_asignada)]
    else:
        if rol in ['superusuario', 'gerencia', 'admin', 'logistica',"seremi"]:
            permiso_sucursales = "TODAS"
        else:
            permiso_sucursales = []

    if not permiso_sucursales:
        flash("No tienes sucursales asignadas.", "warning")
        return redirect(url_for("dashboard.dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor() 

    # 1. QUERY SOLICITUDES
    query_sol = """
        SELECT 
            s.solicitud_id, s.fecha_solicitud, s.estado, s.prioridad, 
            suc.nombre_sucursal, suc.sucursal_id,
            COUNT(d.detalle_id) as items_count, s.requiere_confirmacion,
            s.tipo_solicitud, s.descripcion_servicio
        FROM solicitudes s
        JOIN Sucursales suc ON s.sucursal_id = suc.sucursal_id
        LEFT JOIN solicitudes_detalle d ON s.solicitud_id = d.solicitud_id
        WHERE 
            ((s.estado != 'Completado' AND s.estado != 'Cerrado')
            OR (s.estado = 'Completado' AND s.requiere_confirmacion = 1))
    """
    params = []
    if permiso_sucursales != "TODAS":
        format_strings = ','.join(['%s'] * len(permiso_sucursales))
        query_sol += f" AND s.sucursal_id IN ({format_strings})"
        params.extend(permiso_sucursales)

    query_sol += " GROUP BY s.solicitud_id ORDER BY s.fecha_solicitud DESC"
    cursor.execute(query_sol, tuple(params))
    solicitudes = cursor.fetchall()

   # 2. QUERY TAREAS
    tareas_campana = []
    tareas_popup = []
    
    if permiso_sucursales != "TODAS":
        query_tareas = """
            SELECT t.tarea_id, t.mensaje, t.prioridad, t.fecha_creacion, 
                   suc.nombre_sucursal, t.postergaciones, t.postergado_hasta
            FROM tareas_sucursal t
            JOIN Sucursales suc ON t.sucursal_id = suc.sucursal_id
            WHERE t.estado = 'Pendiente'
        """
        params_tareas = []
        format_strings = ','.join(['%s'] * len(permiso_sucursales))
        query_tareas += f" AND t.sucursal_id IN ({format_strings})"
        params_tareas.extend(permiso_sucursales)
        
        query_tareas += " ORDER BY t.fecha_creacion DESC LIMIT 10"
        
        cursor.execute(query_tareas, tuple(params_tareas))
        raw_tareas = cursor.fetchall()
        
        ahora = datetime.now()

        if raw_tareas:
            is_dict = isinstance(raw_tareas[0], dict)
            for t in raw_tareas:
                if is_dict:
                    obj_tarea = {
                        "id": t['tarea_id'], "mensaje": t['mensaje'], "prioridad": t['prioridad'], 
                        "fecha": t['fecha_creacion'], "sucursal": t['nombre_sucursal'], 
                        "postergaciones": t['postergaciones'], "postergado_hasta": t['postergado_hasta']
                    }
                else:
                    obj_tarea = {
                        "id": t[0], "mensaje": t[1], "prioridad": t[2], 
                        "fecha": t[3], "sucursal": t[4], 
                        "postergaciones": t[5], "postergado_hasta": t[6]
                    }
                tareas_campana.append(obj_tarea)
                
                esta_durmiendo = obj_tarea['postergado_hasta'] and obj_tarea['postergado_hasta'] > ahora
                if not esta_durmiendo:
                    tareas_popup.append(obj_tarea)

    # 3. LISTA SUCURSALES
    sucursales_lista = []
    if rol in ['superusuario', 'admin', 'logistica', "seremi"]:
        cursor.execute("SELECT sucursal_id, nombre_sucursal FROM Sucursales ORDER BY nombre_sucursal")
        suc_rows = cursor.fetchall()
        if suc_rows:
            is_dict = isinstance(suc_rows[0], dict)
            for s in suc_rows: 
                sucursales_lista.append({"id": s['sucursal_id'] if is_dict else s[0], "nombre": s['nombre_sucursal'] if is_dict else s[1]})
    
    elif sucursal_asignada:
        cursor.execute("SELECT sucursal_id, nombre_sucursal FROM Sucursales WHERE sucursal_id = %s", (sucursal_asignada,))
        row = cursor.fetchone()
        if row:
            is_dict = isinstance(row, dict)
            sucursales_lista.append({"id": row['sucursal_id'] if is_dict else row[0], "nombre": row['nombre_sucursal'] if is_dict else row[1]})

    conn.close()

    return render_template("sucursales/pizarra.html", 
                           solicitudes=solicitudes, 
                           datetime=datetime, 
                           tareas_campana=tareas_campana, 
                           tareas_popup=tareas_popup,     
                           sucursales_select=sucursales_lista)
    

@sucursales_bp.route("/api/detalle/<int:solicitud_id>")
@login_requerido
@permiso_modulo("sucursales")
def api_detalle_solicitud(solicitud_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            d.detalle_id,
            d.cantidad_solicitada,
            d.cantidad_despachada,
            d.cantidad_recepcionada, 
            d.estado_linea,
            p.nombre,
            p.unidad_medida,
            p.sku
        FROM solicitudes_detalle d
        JOIN Productos p ON d.producto_id = p.producto_id 
        WHERE d.solicitud_id = %s
    """
    cursor.execute(query, (solicitud_id,))
    rows = cursor.fetchall()
    conn.close()
    
    items_list = []
    if rows:
        is_dict = isinstance(rows[0], dict)
        for row in rows:
            if is_dict:
                 items_list.append({
                    "detalle_id": row['detalle_id'],
                    "cantidad_solicitada": float(row['cantidad_solicitada']),
                    "cantidad_despachada": float(row['cantidad_despachada']),
                    "cantidad_recepcionada": float(row['cantidad_recepcionada'] or 0),
                    "estado_linea": row['estado_linea'],
                    "nombre_producto": row['nombre'],
                    "unidad_medida": row['unidad_medida'],
                    "sku": row['sku']
                })
            else:
                 items_list.append({
                    "detalle_id": row[0],
                    "cantidad_solicitada": float(row[1]),
                    "cantidad_despachada": float(row[2]),
                    "cantidad_recepcionada": float(row[3] or 0),
                    "estado_linea": row[4],
                    "nombre_producto": row[5],
                    "unidad_medida": row[6],
                    "sku": row[7]
                })
    
    return jsonify(items_list)

@sucursales_bp.route("/terminar_servicio", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def terminar_servicio():
    if session.get("rol") != "superusuario":
        return jsonify({"success": False, "error": "⛔ Solo el Superusuario puede cerrar servicios."}), 403

    data = request.get_json()
    solicitud_id = data.get("solicitud_id")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE solicitudes 
            SET estado = 'Completado', requiere_confirmacion = 0
            WHERE solicitud_id = %s
        """, (solicitud_id,))
        conn.commit()
        return jsonify({"success": True, "message": "Servicio cerrado correctamente"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()
        
@sucursales_bp.route("/eliminar/<int:solicitud_id>", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def eliminar_solicitud(solicitud_id):
    if session.get("rol") != "superusuario":
        return jsonify({"success": False, "error": "⛔ Acceso Denegado: Solo Superusuario."}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM solicitudes WHERE solicitud_id = %s", (solicitud_id,))
        conn.commit()
        return jsonify({"success": True, "message": "Solicitud eliminada correctamente"})
        
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()
        

@sucursales_bp.route("/nueva")
@login_requerido
@permiso_modulo("sucursales")
def vista_nueva_solicitud():
    if "usuario" not in session: return redirect(url_for("auth.login"))

    usuario_actual = session["usuario"]
    rol = session.get("rol", "invitado")
    
    permiso_sucursales = ACCESO_SUCURSALES.get(usuario_actual, [])
    if rol in ['superusuario', 'adm',"seremi"] and not permiso_sucursales:
        permiso_sucursales = "TODAS"

    conn = get_db_connection()
    cursor = conn.cursor()

    query_suc = "SELECT sucursal_id, nombre_sucursal FROM Sucursales"
    params_suc = []

    if permiso_sucursales != "TODAS":
        if not permiso_sucursales:
            query_suc += " WHERE 1=0" 
        else:
            format_strings = ','.join(['%s'] * len(permiso_sucursales))
            query_suc += f" WHERE sucursal_id IN ({format_strings})"
            params_suc.extend(permiso_sucursales)
            
    query_suc += " ORDER BY nombre_sucursal"
    
    cursor.execute(query_suc, tuple(params_suc))
    sucursales = cursor.fetchall()

    cursor.execute("SELECT categoria_id, nombre_categoria FROM Categorias ORDER BY nombre_categoria")
    categorias = cursor.fetchall()

    cursor.execute("SELECT p.producto_id, p.nombre, p.unidad_medida, p.sku, p.categoria_id FROM Productos p ORDER BY p.nombre ASC")
    productos = cursor.fetchall()
    
    conn.close()
    
    lista_sucursales = []
    if sucursales:
        is_dict = isinstance(sucursales[0], dict)
        for s in sucursales:
            lista_sucursales.append({"sucursal_id": s['sucursal_id'] if is_dict else s[0], "nombre_sucursal": s['nombre_sucursal'] if is_dict else s[1]})
        
    lista_productos = []
    if productos:
        is_dict = isinstance(productos[0], dict)
        for p in productos:
            lista_productos.append({
                "producto_id": p['producto_id'] if is_dict else p[0], 
                "nombre": p['nombre'] if is_dict else p[1], 
                "unidad_medida": p['unidad_medida'] if is_dict else p[2],
                "sku": p['sku'] if is_dict else p[3], 
                "categoria_id": p['categoria_id'] if is_dict else p[4]
            })

    lista_categorias = []
    if categorias:
        is_dict = isinstance(categorias[0], dict)
        for c in categorias:
            lista_categorias.append({"categoria_id": c['categoria_id'] if is_dict else c[0], "nombre_categoria": c['nombre_categoria'] if is_dict else c[1]})

    return render_template("sucursales/nueva_solicitud.html", 
                           sucursales=lista_sucursales, 
                           categorias=lista_categorias,
                           productos=lista_productos)


@sucursales_bp.route("/crear", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def crear_solicitud_api():
    if "usuario" not in session: return jsonify({"success": False, "error": "No autorizado"}), 401

    data = request.get_json()
    sucursal_id = data.get("sucursal_id")
    prioridad = data.get("prioridad")
    items = data.get("items")
    
    usuario_actual = session["usuario"]
    permiso_sucursales = ACCESO_SUCURSALES.get(usuario_actual, [])
    
    if session.get("rol") not in ['superusuario', 'adm', "seremi"]:
         if permiso_sucursales != "TODAS":
             try: suc_id_int = int(sucursal_id)
             except: return jsonify({"success": False, "error": "ID de sucursal inválido"}), 400

             if suc_id_int not in permiso_sucursales:
                 return jsonify({"success": False, "error": "No tienes permiso para crear pedidos en esta sucursal"}), 403

    if not sucursal_id or not items:
        return jsonify({"success": False, "error": "Faltan datos obligatorios"})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query_cabecera = """
            INSERT INTO solicitudes (sucursal_id, usuario_solicitante, estado, prioridad, fecha_solicitud)
            VALUES (%s, %s, 'Pendiente', %s, NOW())
        """
        cursor.execute(query_cabecera, (sucursal_id, session["usuario"], prioridad))
        solicitud_id = cursor.lastrowid 

        query_detalle = """
            INSERT INTO solicitudes_detalle (solicitud_id, producto_id, cantidad_solicitada, estado_linea)
            VALUES (%s, %s, %s, 'Pendiente')
        """
        
        for item in items:
            p_id = item["id"]
            cant = float(item["cantidad"])
            if cant > 0:
                cursor.execute(query_detalle, (solicitud_id, p_id, cant))

        conn.commit()
        return jsonify({"success": True, "message": "Solicitud creada correctamente"})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()

# --- AQUÍ ESTÁ LA FUNCIÓN HISTORIAL ACTUALIZADA ---
@sucursales_bp.route("/historial")
@login_requerido
@permiso_modulo("sucursales")
def historial():
    if "usuario" not in session: return redirect(url_for("auth.login"))
    
    usuario_actual = session["usuario"]
    rol = session.get("rol", "invitado")

    permiso_sucursales = ACCESO_SUCURSALES.get(usuario_actual, [])
    if rol in ['superusuario', 'gerencia', 'admin', "seremi"] and not permiso_sucursales:
        permiso_sucursales = "TODAS"

    if not permiso_sucursales:
        flash("No tienes acceso al historial.", "warning")
        return redirect(url_for("sucursales.pizarra"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # CAMBIO 1: Agregamos comprobante_obs al SELECT
    query = """
        SELECT s.solicitud_id, s.fecha_solicitud, suc.nombre_sucursal, 
               s.usuario_solicitante, s.estado, s.prioridad, 
               s.observacion_despacho, s.descripcion_servicio,
               s.comprobante_obs
        FROM solicitudes s
        JOIN Sucursales suc ON s.sucursal_id = suc.sucursal_id
    """
    params = []

    if permiso_sucursales != "TODAS":
        format_strings = ','.join(['%s'] * len(permiso_sucursales))
        query += f" WHERE s.sucursal_id IN ({format_strings})"
        params.extend(permiso_sucursales)

    query += " ORDER BY s.solicitud_id DESC LIMIT 100"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    
    historial_data = []
    
    if rows:
        is_dict = isinstance(rows[0], dict)
        for r in rows:
            if is_dict:
                historial_data.append({
                    "id": r['solicitud_id'], "fecha": r['fecha_solicitud'], 
                    "sucursal": r['nombre_sucursal'], "usuario": r['usuario_solicitante'], 
                    "estado": r['estado'], "prioridad": r['prioridad'],
                    "obs_despacho": r['observacion_despacho'],
                    "descripcion": r['descripcion_servicio'],
                    "comprobante": r['comprobante_obs'] # <--- NUEVO CAMPO
                })
            else:
                historial_data.append({
                    "id": r[0], "fecha": r[1], 
                    "sucursal": r[2], "usuario": r[3], 
                    "estado": r[4], "prioridad": r[5],
                    "obs_despacho": r[6],
                    "descripcion": r[7],
                    "comprobante": r[8] # <--- NUEVO CAMPO
                })

    return render_template("sucursales/historial.html", historial=historial_data)

@sucursales_bp.route("/despachar", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def guardar_despacho():
    if "usuario" not in session:
        return jsonify({"success": False, "error": "No autorizado"}), 401

    data = request.get_json()
    solicitud_id = data.get("solicitud_id")
    # ACEPTAMOS lista vacía por si ya todo está 'Listo' y solo queremos guardar obs
    items_despacho = data.get("items", []) 
    
    observacion_despacho = data.get("observacion_despacho", "") 
    comentario = data.get("comentario", "")

    # VALIDACIÓN CORREGIDA: Solo exigimos el ID de solicitud
    if not solicitud_id:
        return jsonify({"success": False, "error": "Falta ID de solicitud"})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # A. Actualizar Items (Solo si hay algo en la lista)
        if items_despacho:
            for item in items_despacho:
                detalle_id = item["detalle_id"]
                val = item.get("cantidad")
                cantidad_enviada_ahora = float(val) if val else 0
                
                if cantidad_enviada_ahora > 0:
                    cursor.execute("""
                        UPDATE solicitudes_detalle 
                        SET 
                            estado_linea = CASE 
                                WHEN (cantidad_despachada + %s) >= cantidad_solicitada THEN 'Completo'
                                WHEN (cantidad_despachada + %s) > 0 THEN 'Parcial'
                                ELSE 'Pendiente'
                            END,
                            cantidad_despachada = cantidad_despachada + %s
                        WHERE detalle_id = %s
                    """, (cantidad_enviada_ahora, cantidad_enviada_ahora, cantidad_enviada_ahora, detalle_id))

        # B. Actualizar Cabecera (Siempre se ejecuta para guardar la nota)
        cursor.execute("""
            UPDATE solicitudes 
            SET estado = 'Por Confirmar', 
                requiere_confirmacion = 1,
                comentario_logistica = %s,
                observacion_despacho = %s
            WHERE solicitud_id = %s
        """, (comentario, observacion_despacho, solicitud_id))

        conn.commit()
        return jsonify({"success": True, "message": "Actualizado correctamente"})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()

@sucursales_bp.route("/recepcionar", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def recepcionar_pedido():
    if "usuario" not in session: return jsonify({"success": False, "error": "No autorizado"}), 401

    data = request.get_json()
    solicitud_id = data.get("solicitud_id")
    items_recibidos = data.get("items") 

    if not solicitud_id or not items_recibidos:
        return jsonify({"success": False, "error": "Datos incompletos"})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for item in items_recibidos:
            d_id = item['detalle_id']
            cant_recibida = float(item['cantidad'])
            
            cursor.execute("""
                UPDATE solicitudes_detalle 
                SET cantidad_recepcionada = cantidad_recepcionada + %s
                WHERE detalle_id = %s
            """, (cant_recibida, d_id))

        cursor.execute("""
            SELECT COUNT(*) as pendientes 
            FROM solicitudes_detalle 
            WHERE solicitud_id = %s AND cantidad_despachada < cantidad_solicitada
        """, (solicitud_id,))
        
        row = cursor.fetchone()
        pendientes = row['pendientes'] if isinstance(row, dict) else row[0]

        nuevo_estado = 'Completado' if pendientes == 0 else 'Pendiente'
        
        cursor.execute("""
            UPDATE solicitudes 
            SET estado = %s, requiere_confirmacion = 0 
            WHERE solicitud_id = %s
        """, (nuevo_estado, solicitud_id))

        conn.commit()
        return jsonify({"success": True, "message": "Recepción registrada correctamente"})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()
        
@sucursales_bp.route("/tarea/crear", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def crear_tarea():
    if session.get("rol") not in ['superusuario', 'admin', 'logistica',"seremi"]:
        return jsonify({"success": False, "error": "No tienes permiso para enviar alertas"}), 403

    data = request.get_json()
    sucursal_id = data.get("sucursal_id") 
    mensaje = data.get("mensaje")
    prioridad = data.get("prioridad", "Normal")

    if not mensaje: return jsonify({"success": False, "error": "Mensaje vacío"})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if sucursal_id == "TODAS":
            cursor.execute("SELECT sucursal_id FROM Sucursales")
            ids = cursor.fetchall()
            for row in ids:
                sid = row['sucursal_id'] if isinstance(row, dict) else row[0]
                cursor.execute("""
                    INSERT INTO tareas_sucursal (sucursal_id, mensaje, prioridad, usuario_creador)
                    VALUES (%s, %s, %s, %s)
                """, (sid, mensaje, prioridad, session["usuario"]))
        else:
            cursor.execute("""
                INSERT INTO tareas_sucursal (sucursal_id, mensaje, prioridad, usuario_creador)
                VALUES (%s, %s, %s, %s)
            """, (sucursal_id, mensaje, prioridad, session["usuario"]))

        conn.commit()
        return jsonify({"success": True, "message": "Alerta enviada"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()

@sucursales_bp.route("/tarea/completar", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def completar_tarea():
    data = request.get_json()
    tarea_id = data.get("tarea_id")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE tareas_sucursal 
            SET estado = 'Realizado', fecha_realizado = NOW()
            WHERE tarea_id = %s
        """, (tarea_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()
        
@sucursales_bp.route("/tarea/postergar", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def postergar_tarea():
    data = request.get_json()
    tarea_id = data.get("tarea_id")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE tareas_sucursal 
            SET postergaciones = postergaciones + 1,
                postergado_hasta = DATE_ADD(NOW(), INTERVAL 20 MINUTE)
            WHERE tarea_id = %s
        """, (tarea_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()
        
@sucursales_bp.route("/crear_servicio", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def crear_servicio_api():
    if "usuario" not in session: return jsonify({"success": False, "error": "No autorizado"}), 401

    data = request.get_json()
    sucursal_id = data.get("sucursal_id")
    prioridad = data.get("prioridad")
    descripcion = data.get("descripcion")
    
    if not descripcion:
        return jsonify({"success": False, "error": "Debes describir el problema"})
        
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query_cabecera = """
            INSERT INTO solicitudes (sucursal_id, usuario_solicitante, estado, prioridad, fecha_solicitud, tipo_solicitud, descripcion_servicio)
            VALUES (%s, %s, 'Pendiente', %s, NOW(), 'Servicio', %s)
        """
        cursor.execute(query_cabecera, (sucursal_id, session["usuario"], prioridad, descripcion))
        conn.commit()
        return jsonify({"success": True, "message": "Solicitud de servicio creada"})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()

# --- CAMBIO 2: NUEVA RUTA PARA GUARDAR EL COMPROBANTE ---
@sucursales_bp.route("/actualizar_comprobante", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def actualizar_comprobante():
    data = request.get_json()
    sol_id = data.get("solicitud_id")
    texto = data.get("texto")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE solicitudes SET comprobante_obs = %s WHERE solicitud_id = %s", (texto, sol_id))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()
        
# --- PEGAR AL FINAL DE routes/sucursales_routes.py ---

@sucursales_bp.route("/tareas/historial_api")
@login_requerido
@permiso_modulo("sucursales")
def historial_tareas_api():
    # 1. Solo Jefes pueden ver el historial de alertas
    if session.get("rol") not in ['superusuario', 'admin', 'logistica', "seremi"]:
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Traemos todas las tareas, ordenadas por las más recientes
        query = """
            SELECT t.tarea_id, t.mensaje, t.prioridad, t.estado, 
                   t.fecha_creacion, t.fecha_realizado, s.nombre_sucursal, t.usuario_creador
            FROM tareas_sucursal t
            JOIN Sucursales s ON t.sucursal_id = s.sucursal_id
            ORDER BY t.fecha_creacion DESC
            LIMIT 50
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        lista = []
        if rows:
            is_dict = isinstance(rows[0], dict)
            for r in rows:
                if is_dict:
                    lista.append({
                        "id": r['tarea_id'], "mensaje": r['mensaje'], "prioridad": r['prioridad'],
                        "estado": r['estado'], "creado": r['fecha_creacion'], 
                        "realizado": r['fecha_realizado'], "sucursal": r['nombre_sucursal'],
                        "creador": r['usuario_creador']
                    })
                else:
                    lista.append({
                        "id": r[0], "mensaje": r[1], "prioridad": r[2],
                        "estado": r[3], "creado": r[4], 
                        "realizado": r[5], "sucursal": r[6],
                        "creador": r[7]
                    })
        return jsonify(lista)
    except Exception as e:
        return jsonify({"error": str(e)})
    finally:
        conn.close()
        
# --- PEGAR AL FINAL DE routes/sucursales_routes.py ---

@sucursales_bp.route("/item/actualizar", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def actualizar_cantidad_item():
    if session.get("rol") != "superusuario": return jsonify({"success": False, "error": "Acceso Denegado"}), 403

    data = request.get_json()
    detalle_id = data.get("detalle_id")
    nueva_cantidad = float(data.get("cantidad"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Obtener ID de la solicitud padre antes de nada
        cursor.execute("SELECT solicitud_id FROM solicitudes_detalle WHERE detalle_id = %s", (detalle_id,))
        row = cursor.fetchone()
        if not row: return jsonify({"success": False, "error": "Item no encontrado"})
        solicitud_id = row['solicitud_id'] if isinstance(row, dict) else row[0]

        # 2. Actualizar cantidad y estado de la línea
        cursor.execute("UPDATE solicitudes_detalle SET cantidad_solicitada = %s WHERE detalle_id = %s", (nueva_cantidad, detalle_id))
        cursor.execute("""
            UPDATE solicitudes_detalle 
            SET estado_linea = CASE 
                WHEN cantidad_despachada >= cantidad_solicitada THEN 'Completo'
                WHEN cantidad_despachada > 0 THEN 'Parcial'
                ELSE 'Pendiente'
            END
            WHERE detalle_id = %s
        """, (detalle_id,))
        
        # 3. AUTO-VERIFICACIÓN: ¿Ya están todos completos?
        cursor.execute("""
            SELECT COUNT(*) as pendientes 
            FROM solicitudes_detalle 
            WHERE solicitud_id = %s AND estado_linea != 'Completo'
        """, (solicitud_id,))
        res = cursor.fetchone()
        pendientes = res['pendientes'] if isinstance(res, dict) else res[0]

        if pendientes == 0:
            # ¡Si todo está completo, cerramos la solicitud y la mandamos al historial!
            cursor.execute("UPDATE solicitudes SET estado = 'Completado', requiere_confirmacion = 0 WHERE solicitud_id = %s", (solicitud_id,))

        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()

@sucursales_bp.route("/item/eliminar", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def eliminar_item_detalle():
    if session.get("rol") != "superusuario": return jsonify({"success": False, "error": "Acceso Denegado"}), 403

    data = request.get_json()
    detalle_id = data.get("detalle_id")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Obtener ID padre
        cursor.execute("SELECT solicitud_id FROM solicitudes_detalle WHERE detalle_id = %s", (detalle_id,))
        row = cursor.fetchone()
        if not row: return jsonify({"success": False, "error": "Item no encontrado"})
        solicitud_id = row['solicitud_id'] if isinstance(row, dict) else row[0]

        # 2. Borrar línea
        cursor.execute("DELETE FROM solicitudes_detalle WHERE detalle_id = %s", (detalle_id,))
        
        # 3. AUTO-VERIFICACIÓN: ¿Queda algo pendiente?
        cursor.execute("""
            SELECT COUNT(*) as pendientes 
            FROM solicitudes_detalle 
            WHERE solicitud_id = %s AND estado_linea != 'Completo'
        """, (solicitud_id,))
        res = cursor.fetchone()
        pendientes = res['pendientes'] if isinstance(res, dict) else res[0]

        if pendientes == 0:
            # Si al borrar este ítem ya no queda nada pendiente, ¡cerrar solicitud!
            cursor.execute("UPDATE solicitudes SET estado = 'Completado', requiere_confirmacion = 0 WHERE solicitud_id = %s", (solicitud_id,))

        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()