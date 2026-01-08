from flask import Blueprint, render_template, session, redirect, url_for, flash
from utils.auth import tiene_permiso
from utils.db import get_db_connection
from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify
from flask import request
from datetime import datetime, timedelta
from utils.auth import login_requerido, permiso_modulo

sucursales_bp = Blueprint('sucursales', __name__, url_prefix='/sucursales')

# --- CONFIGURACIÓN DE ACCESO MANUAL ---
# Define aquí qué sucursales ve cada correo.
# "TODAS": Ve todo (Tú / Logística)
# [ID, ID]: Lista de IDs de sucursales permitidas
ACCESO_SUCURSALES = {
    "carloscarvajal2.0@gmail.com": "TODAS",       # <--- CAMBIAR POR TU CORREO REAL
    "logistica1@huente.com": "TODAS",
    "sucursal1@huente.com": [1],          # Ejemplo: Solo ve sucursal ID 1
    "sucursal2@huente.com": [2]
}

@sucursales_bp.route("/pizarra")
@login_requerido
@permiso_modulo("sucursales")
def pizarra():
    if "usuario" not in session: return redirect(url_for("auth.login"))
    
    usuario_actual = session["usuario"]
    rol = session.get("rol", "invitado")

    permiso_sucursales = ACCESO_SUCURSALES.get(usuario_actual, [])
    
    if rol in ['superusuario', 'gerencia', 'admin', 'logistica'] and not permiso_sucursales:
        permiso_sucursales = "TODAS"

    if not permiso_sucursales:
        flash("No tienes sucursales asignadas.", "warning")
        return redirect(url_for("dashboard.dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor() 

    # 1. QUERY SOLICITUDES (Igual que antes)
    query_sol = """
        SELECT 
            s.solicitud_id, s.fecha_solicitud, s.estado, s.prioridad, 
            suc.nombre_sucursal, suc.sucursal_id,
            COUNT(d.detalle_id) as items_count, s.requiere_confirmacion
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

   # 2. QUERY TAREAS (LOGICA MIXTA: 3 VIDAS + 20 MINUTOS + HISTORIAL)
    tareas_campana = [] # Las últimas 10 (para el desplegable)
    tareas_popup = []   # Las que saltan a la vista ahora mismo
    
    if permiso_sucursales != "TODAS":
        # Traemos las últimas 10 tareas pendientes
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
        
        # Ordenamos por fecha descendente para tener las últimas 10 "notificaciones"
        query_tareas += " ORDER BY t.fecha_creacion DESC LIMIT 10"
        
        cursor.execute(query_tareas, tuple(params_tareas))
        raw_tareas = cursor.fetchall()
        
        ahora = datetime.now()

        # Procesamos
        if raw_tareas and isinstance(raw_tareas[0], (list, tuple)):
            for t in raw_tareas:
                obj_tarea = {
                    "id": t[0], "mensaje": t[1], "prioridad": t[2], 
                    "fecha": t[3], "sucursal": t[4], 
                    "postergaciones": t[5], "postergado_hasta": t[6]
                }
                tareas_campana.append(obj_tarea)
                
                # LÓGICA DEL POP-UP:
                # Salta si: (Nunca se ha postergado) O (Ya pasó el tiempo de espera)
                esta_durmiendo = obj_tarea['postergado_hasta'] and obj_tarea['postergado_hasta'] > ahora
                if not esta_durmiendo:
                    tareas_popup.append(obj_tarea)
        else:
             for t in raw_tareas:
                 obj_tarea = {
                    "id": t['tarea_id'], "mensaje": t['mensaje'], "prioridad": t['prioridad'], 
                    "fecha": t['fecha_creacion'], "sucursal": t['nombre_sucursal'],
                    "postergaciones": t['postergaciones'], "postergado_hasta": t['postergado_hasta']
                }
                 tareas_campana.append(obj_tarea)
                 
                 esta_durmiendo = obj_tarea['postergado_hasta'] and obj_tarea['postergado_hasta'] > ahora
                 if not esta_durmiendo:
                     tareas_popup.append(obj_tarea)

    # 3. LISTA SUCURSALES (Para que los Jefes puedan elegir destino)
    sucursales_lista = []
    if rol in ['superusuario', 'admin', 'logistica']:
        cursor.execute("SELECT sucursal_id, nombre_sucursal FROM Sucursales ORDER BY nombre_sucursal")
        suc_rows = cursor.fetchall()
        
        if suc_rows and isinstance(suc_rows[0], (list, tuple)):
             for s in suc_rows: sucursales_lista.append({"id": s[0], "nombre": s[1]})
        else:
             for s in suc_rows: sucursales_lista.append({"id": s['sucursal_id'], "nombre": s['nombre_sucursal']})

    conn.close()

    return render_template("sucursales/pizarra.html", 
                           solicitudes=solicitudes, 
                           datetime=datetime, 
                           tareas_campana=tareas_campana, # Para el desplegable
                           tareas_popup=tareas_popup,     # Para el modal invasivo
                           sucursales_select=sucursales_lista)
    

@sucursales_bp.route("/api/detalle/<int:solicitud_id>")
@login_requerido
@permiso_modulo("sucursales")
def api_detalle_solicitud(solicitud_id):
    # ... (validaciones de sesión) ...
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Asegúrate de incluir 'd.cantidad_recepcionada' aquí:
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
        JOIN productos p ON d.producto_id = p.producto_id 
        WHERE d.solicitud_id = %s
    """
    cursor.execute(query, (solicitud_id,))
    rows = cursor.fetchall()
    conn.close()
    
    items_list = []
    for row in rows:
        # Detectamos si es Dict o Tupla para evitar errores
        if isinstance(row, dict):
             items_list.append({
                "detalle_id": row['detalle_id'],
                "cantidad_solicitada": float(row['cantidad_solicitada']),
                "cantidad_despachada": float(row['cantidad_despachada']),
                "cantidad_recepcionada": float(row['cantidad_recepcionada'] or 0), # <--- ESTO ARREGLA EL UNDEFINED
                "estado_linea": row['estado_linea'],
                "nombre_producto": row['nombre'],
                "unidad_medida": row['unidad_medida'],
                "sku": row['sku']
            })
        else:
             # Si es tupla (índices numéricos)
             items_list.append({
                "detalle_id": row[0],
                "cantidad_solicitada": float(row[1]),
                "cantidad_despachada": float(row[2]),
                "cantidad_recepcionada": float(row[3] or 0), # <--- ÍNDICE 3
                "estado_linea": row[4],
                "nombre_producto": row[5],
                "unidad_medida": row[6],
                "sku": row[7]
            })
    
    return jsonify(items_list)

@sucursales_bp.route("/despachar", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def guardar_despacho():
    if "usuario" not in session:
        return jsonify({"success": False, "error": "No autorizado"}), 401

    data = request.get_json()
    solicitud_id = data.get("solicitud_id")
    items_despacho = data.get("items") 
    comentario = data.get("comentario", "")

    if not solicitud_id or not items_despacho:
        return jsonify({"success": False, "error": "Datos incompletos"})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for item in items_despacho:
            detalle_id = item["detalle_id"]
            cantidad_enviada_ahora = float(item["cantidad"])
            
            if cantidad_enviada_ahora > 0:
                # --- CORRECCIÓN CRÍTICA ---
                # Invertimos el orden: 
                # 1. Definimos el estado (usando el valor original + lo nuevo)
                # 2. Actualizamos la cantidad (sumando lo nuevo)
                update_query = """
                    UPDATE solicitudes_detalle 
                    SET 
                        estado_linea = CASE 
                            WHEN (cantidad_despachada + %s) >= cantidad_solicitada THEN 'Completo'
                            WHEN (cantidad_despachada + %s) > 0 THEN 'Parcial'
                            ELSE 'Pendiente'
                        END,
                        cantidad_despachada = cantidad_despachada + %s
                    WHERE detalle_id = %s
                """
                cursor.execute(update_query, (cantidad_enviada_ahora, cantidad_enviada_ahora, cantidad_enviada_ahora, detalle_id))

        cabecera_query = """
            UPDATE solicitudes 
            SET estado = 'Por Confirmar', 
                requiere_confirmacion = 1,
                comentario_logistica = %s
            WHERE solicitud_id = %s
        """
        cursor.execute(cabecera_query, (comentario, solicitud_id))

        conn.commit()
        return jsonify({"success": True, "message": "Despacho registrado correctamente"})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()
        
        # --- Agrega esto al final de routes/sucursales_routes.py ---

@sucursales_bp.route("/eliminar/<int:solicitud_id>", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def eliminar_solicitud(solicitud_id):
    # 1. CANDADO DE SEGURIDAD: Solo el jefe pasa
    if session.get("rol") != "superusuario":
        return jsonify({"success": False, "error": "⛔ Acceso Denegado: Solo Superusuario."}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 2. BORRADO TOTAL
        # Gracias a que configuramos "ON DELETE CASCADE" en la base de datos,
        # al borrar la cabecera, se borran solos los detalles.
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
    if "usuario" not in session:
        return redirect(url_for("auth.login"))

    usuario_actual = session["usuario"]
    rol = session.get("rol", "invitado")
    
    # --- CAMBIO: FILTRO DE SUCURSALES EN EL SELECTOR ---
    permiso_sucursales = ACCESO_SUCURSALES.get(usuario_actual, [])
    if rol in ['superusuario', 'gerencia'] and not permiso_sucursales:
        permiso_sucursales = "TODAS"

    conn = get_db_connection()
    cursor = conn.cursor()

    # Query Dinámica para Sucursales (Solo trae las permitidas)
    query_suc = "SELECT sucursal_id, nombre_sucursal FROM Sucursales"
    params_suc = []

    if permiso_sucursales != "TODAS":
        if not permiso_sucursales: # Si está vacío no ve nada
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
    
    # Normalización a listas de diccionarios
    lista_sucursales = []
    if sucursales and isinstance(sucursales[0], (list, tuple)):
        for s in sucursales:
            lista_sucursales.append({"sucursal_id": s[0], "nombre_sucursal": s[1]})
    else:
        lista_sucursales = sucursales
        
    lista_productos = []
    if productos and isinstance(productos[0], (list, tuple)):
        for p in productos:
            lista_productos.append({
                "producto_id": p[0], "nombre": p[1], "unidad_medida": p[2],
                "sku": p[3], "categoria_id": p[4]
            })
    else:
        lista_productos = productos

    lista_categorias = []
    if categorias and isinstance(categorias[0], (list, tuple)):
        for c in categorias:
            lista_categorias.append({"categoria_id": c[0], "nombre_categoria": c[1]})
    else:
        lista_categorias = categorias

    return render_template("sucursales/nueva_solicitud.html", 
                           sucursales=lista_sucursales, 
                           categorias=lista_categorias,
                           productos=lista_productos)


@sucursales_bp.route("/crear", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def crear_solicitud_api():
    if "usuario" not in session:
        return jsonify({"success": False, "error": "No autorizado"}), 401

    data = request.get_json()
    sucursal_id = data.get("sucursal_id")
    prioridad = data.get("prioridad")
    items = data.get("items")
    
    # --- CAMBIO: VALIDACIÓN DE SEGURIDAD EXTRA ---
    # Verificar que el usuario tenga permiso para esta sucursal_id específica
    usuario_actual = session["usuario"]
    permiso_sucursales = ACCESO_SUCURSALES.get(usuario_actual, [])
    
    # Si no es superusuario ni gerencia, validamos el permiso explícito
    if session.get("rol") not in ['superusuario', 'gerencia']:
         if permiso_sucursales != "TODAS":
             # Convertimos a int para comparar seguro
             try:
                 suc_id_int = int(sucursal_id)
             except:
                 return jsonify({"success": False, "error": "ID de sucursal inválido"}), 400

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
# Reemplaza la función historial existente en sucursales_routes.py

@sucursales_bp.route("/historial")
@login_requerido
@permiso_modulo("sucursales")
def historial():
    if "usuario" not in session:
        return redirect(url_for("auth.login"))
    
    usuario_actual = session["usuario"]
    rol = session.get("rol", "invitado")

    # 1. RECUPERAR LÓGICA DE PERMISOS (Igual que en Pizarra)
    # Definir aquí o importar ACCESO_SUCURSALES si está arriba en el archivo
    # (Asegúrate de que ACCESO_SUCURSALES esté definido al inicio del archivo py)
    permiso_sucursales = ACCESO_SUCURSALES.get(usuario_actual, [])
    
    if rol in ['superusuario', 'gerencia', 'admin'] and not permiso_sucursales:
        permiso_sucursales = "TODAS"

    if not permiso_sucursales:
        flash("No tienes acceso al historial.", "warning")
        return redirect(url_for("sucursales.pizarra"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 2. CONSTRUIR QUERY CON FILTRO
    query = """
        SELECT s.solicitud_id, s.fecha_solicitud, suc.nombre_sucursal, 
               s.usuario_solicitante, s.estado, s.prioridad
        FROM solicitudes s
        JOIN Sucursales suc ON s.sucursal_id = suc.sucursal_id
    """
    params = []

    # Si NO es "TODAS", filtramos por los IDs permitidos
    if permiso_sucursales != "TODAS":
        # Truco para crear string "1, 2" para el IN de SQL
        format_strings = ','.join(['%s'] * len(permiso_sucursales))
        query += f" WHERE s.sucursal_id IN ({format_strings})"
        params.extend(permiso_sucursales)

    # Ordenar y Limitar
    query += " ORDER BY s.solicitud_id DESC LIMIT 100"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    
    # 3. NORMALIZAR DATOS (Lista de diccionarios)
    historial_data = []
    # Detectamos si es lista (tupla) o dict para ser compatibles
    if rows and isinstance(rows[0], (list, tuple)):
        for r in rows:
            historial_data.append({
                "id": r[0], "fecha": r[1], "sucursal": r[2], 
                "usuario": r[3], "estado": r[4], "prioridad": r[5]
            })
    else:
        # Si ya son diccionarios
        for r in rows:
            historial_data.append({
                 "id": r['solicitud_id'], "fecha": r['fecha_solicitud'], 
                 "sucursal": r['nombre_sucursal'], "usuario": r['usuario_solicitante'], 
                 "estado": r['estado'], "prioridad": r['prioridad']
            })

    return render_template("sucursales/historial.html", historial=historial_data)

@sucursales_bp.route("/recepcionar", methods=["POST"])
@login_requerido
@permiso_modulo("sucursales")
def recepcionar_pedido():
    if "usuario" not in session:
        return jsonify({"success": False, "error": "No autorizado"}), 401

    data = request.get_json()
    solicitud_id = data.get("solicitud_id")
    items_recibidos = data.get("items") # --- CAMBIO: Recibe lista con cantidades

    if not solicitud_id or not items_recibidos:
        return jsonify({"success": False, "error": "Datos incompletos"})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Actualizar cantidades reales
        for item in items_recibidos:
            d_id = item['detalle_id']
            cant_recibida = float(item['cantidad'])
            
            # Sumamos lo que llega ahora a lo que ya había
            cursor.execute("""
                UPDATE solicitudes_detalle 
                SET cantidad_recepcionada = cantidad_recepcionada + %s
                WHERE detalle_id = %s
            """, (cant_recibida, d_id))

        # 2. Verificar si Logística ya envió todo (Ciclo de Envío Completo)
        # Se considera completado si logística no debe nada (despachada < solicitada)
        cursor.execute("""
            SELECT COUNT(*) as pendientes 
            FROM solicitudes_detalle 
            WHERE solicitud_id = %s AND cantidad_despachada < cantidad_solicitada
        """, (solicitud_id,))
        
        row = cursor.fetchone()
        pendientes = row['pendientes'] if isinstance(row, dict) else row[0]

        # 3. Cerrar ciclo
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
    # Solo Jefes pueden crear
    if session.get("rol") not in ['superusuario', 'admin', 'logistica']:
        return jsonify({"success": False, "error": "No tienes permiso para enviar alertas"}), 403

    data = request.get_json()
    sucursal_id = data.get("sucursal_id") # Puede ser un ID o "TODAS"
    mensaje = data.get("mensaje")
    prioridad = data.get("prioridad", "Normal")

    if not mensaje: return jsonify({"success": False, "error": "Mensaje vacío"})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if sucursal_id == "TODAS":
            # Enviamos a TODAS las sucursales existentes
            cursor.execute("SELECT sucursal_id FROM Sucursales")
            ids = cursor.fetchall()
            for row in ids:
                sid = row['sucursal_id'] if isinstance(row, dict) else row[0]
                cursor.execute("""
                    INSERT INTO tareas_sucursal (sucursal_id, mensaje, prioridad, usuario_creador)
                    VALUES (%s, %s, %s, %s)
                """, (sid, mensaje, prioridad, session["usuario"]))
        else:
            # Una sola
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
        # Sumamos 1 a postergaciones Y agregamos 20 minutos al reloj
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
        
