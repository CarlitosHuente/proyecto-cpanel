from flask import Blueprint, render_template, request, redirect, url_for, abort, session, jsonify, current_app
from utils.auth import login_requerido, permiso_modulo, PERMISOS, guardar_permisos_json
from utils.db import get_db_connection
from werkzeug.security import generate_password_hash
from collections import defaultdict
import pandas as pd
import os
from werkzeug.utils import secure_filename
from utils.ventas_excel_import import ejecutar_carga_ventas, inferir_sucursal_comercial

config_bp = Blueprint('config', __name__, url_prefix='/config')

MAX_ARCHIVOS_COMERCIAL = 5

# --- FUNCIÓN AUXILIAR PARA OBTENER SUCURSALES ---
def obtener_lista_sucursales():
    """Trae la lista de sucursales para llenar el select del formulario"""
    conn = get_db_connection()
    sucursales = []
    try:
        with conn.cursor() as cur:
            # OJO: Usamos 'Sucursales' con S mayúscula para compatibilidad con Linux
            cur.execute("SELECT sucursal_id, nombre_sucursal FROM Sucursales ORDER BY nombre_sucursal")
            rows = cur.fetchall()
            
        if rows and isinstance(rows[0], (list, tuple)):
            for r in rows: sucursales.append({"id": r[0], "nombre": r[1]})
        else:
            for r in rows: sucursales.append({"id": r['sucursal_id'], "nombre": r['nombre_sucursal']})
    except Exception as e:
        print(f"Error cargando sucursales: {e}")
    finally:
        conn.close()
        
    return sucursales

@config_bp.route('/usuarios')
@login_requerido
@permiso_modulo("config")
def usuarios():
    conn = get_db_connection()
    with conn.cursor() as cur:
        # Traemos también sucursal_id por si quieres mostrarlo en el futuro
        cur.execute("SELECT id, email, rol, activo, creado_en, sucursal_id FROM usuarios_huente ORDER BY id ASC")
        usuarios = cur.fetchall()
    conn.close()
    return render_template('config/usuarios.html', usuarios=usuarios, permisos=PERMISOS)


@config_bp.route('/usuarios/<int:user_id>/editar', methods=['GET', 'POST'])
@login_requerido
@permiso_modulo("config")
def editar_usuario(user_id):
    conn = get_db_connection()

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        rol = request.form.get('rol', '').strip()
        activo = 1 if request.form.get('activo') == 'on' else 0
        nueva_clave = request.form.get('password', '').strip()
        
        # --- NUEVO: Capturar Sucursal ---
        sucursal_id = request.form.get("sucursal_id")
        if not sucursal_id: 
            sucursal_id = None # Si selecciona "Sin sucursal", guardamos NULL
        # --------------------------------

        with conn.cursor() as cur:
            if nueva_clave:
                password_hash = generate_password_hash(nueva_clave)
                cur.execute(
                    """
                    UPDATE usuarios_huente
                    SET email=%s, rol=%s, activo=%s, password_hash=%s, sucursal_id=%s
                    WHERE id=%s
                    """,
                    (email, rol, activo, password_hash, sucursal_id, user_id)
                )
            else:
                cur.execute(
                    """
                    UPDATE usuarios_huente
                    SET email=%s, rol=%s, activo=%s, sucursal_id=%s
                    WHERE id=%s
                    """,
                    (email, rol, activo, sucursal_id, user_id)
                )
            conn.commit()

        conn.close()
        return redirect(url_for('config.usuarios'))

    # GET: Cargar datos usuario + Lista de sucursales
    sucursales = obtener_lista_sucursales()
    
    with conn.cursor() as cur:
        # Asegúrate de incluir sucursal_id en el SELECT
        cur.execute(
            "SELECT id, email, rol, activo, sucursal_id FROM usuarios_huente WHERE id=%s",
            (user_id,)
        )
        usuario = cur.fetchone()
    conn.close()

    if not usuario:
        abort(404)

    return render_template('config/usuario_editar.html',
                       usuario=usuario,
                       roles=PERMISOS.keys(),
                       sucursales=sucursales) # Pasamos la lista al HTML


@config_bp.route('/usuarios/nuevo', methods=['GET', 'POST'])
@login_requerido
@permiso_modulo("config")
def nuevo_usuario():
    # GET: Necesitamos la lista para mostrar el formulario vacío
    if request.method == "GET":
        sucursales = obtener_lista_sucursales()
        return render_template("config/usuario_nuevo.html",
                           roles=PERMISOS.keys(),
                           sucursales=sucursales)

    # POST: Procesar creación
    conn = get_db_connection()
    email = request.form.get("email", "").strip()
    rol = request.form.get("rol", "").strip()
    activo = 1 if request.form.get("activo") == "on" else 0
    password = request.form.get("password", "").strip()
    
    # --- NUEVO: Capturar Sucursal ---
    sucursal_id = request.form.get("sucursal_id")
    if not sucursal_id: sucursal_id = None
    # --------------------------------

    if not email or not rol or not password:
        conn.close()
        # Si falla, recargamos la lista de sucursales
        sucursales = obtener_lista_sucursales()
        return render_template("config/usuario_nuevo.html",
                            error="Todos los campos son obligatorios.",
                            roles=PERMISOS.keys(),
                            sucursales=sucursales)
    
    password_hash = generate_password_hash(password)

    with conn.cursor() as cur:
        # Insertamos el sucursal_id
        cur.execute("""
            INSERT INTO usuarios_huente (email, rol, activo, password_hash, sucursal_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (email, rol, activo, password_hash, sucursal_id))
        conn.commit()

    conn.close()
    return redirect(url_for("config.usuarios"))

# ==========================================
# GESTIÓN KANBAN DE USUARIOS (DRAG & DROP)
# ==========================================

@config_bp.route('/usuarios_pizarra')
@login_requerido
@permiso_modulo("config")
def usuarios_pizarra():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, email, rol, activo FROM usuarios_huente ORDER BY email ASC")
        usuarios = cur.fetchall()
    conn.close()
    
    usuarios_por_rol = defaultdict(list)
    for u in usuarios:
        rol = u.get('rol', 'invitado') if isinstance(u, dict) else (u[2] if len(u) > 2 else 'invitado')
        usuarios_por_rol[rol].append(u)
        
    roles_disponibles = list(PERMISOS.keys())
    for r in usuarios_por_rol.keys():
        if r not in roles_disponibles and r:
            roles_disponibles.append(r)
            
    return render_template('config/usuarios_pizarra.html', 
                           usuarios_por_rol=usuarios_por_rol, 
                           roles=roles_disponibles)

@config_bp.route('/api/actualizar_rol_usuario', methods=['POST'])
@login_requerido
@permiso_modulo("config")
def api_actualizar_rol_usuario():
    data = request.get_json()
    user_id = data.get("user_id")
    nuevo_rol = data.get("nuevo_rol")
    
    if not user_id or not nuevo_rol:
        return jsonify({"success": False, "error": "Datos incompletos"})
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios_huente SET rol = %s WHERE id = %s", (nuevo_rol, user_id))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()

# routes/config_routes.py (AGREGAR AL FINAL)

# ==========================================
# GESTIÓN DE PERMISOS (DRAG & DROP)
# ==========================================

@config_bp.route('/permisos')
@login_requerido
@permiso_modulo("config")
def gestionar_permisos():
    # Módulos base conocidos del sistema
    modulos_conocidos = ["dashboard", "ventas", "clientes", "seremi", "contab", "reporte", "sucursales", "productos", "categorias", "agricola", "utilidades", "config"]
    
    # Recuperar cualquier módulo extra que ya esté en la configuración actual
    modulos_usados = set(modulos_conocidos)
    for mods in PERMISOS.values():
        for m in mods:
            if m != "*":
                modulos_usados.add(m)
                
    todos_modulos = sorted(list(modulos_usados))
    
    return render_template('config/permisos.html', 
                           permisos=PERMISOS, 
                           todos_modulos=todos_modulos)

@config_bp.route('/api/guardar_permisos', methods=['POST'])
@login_requerido
@permiso_modulo("config")
def api_guardar_permisos():
    nuevos_permisos = request.get_json()
    if not nuevos_permisos:
        return jsonify({"success": False, "error": "Sin datos"})
    
    # Guardamos en el JSON y actualizamos la variable global
    guardar_permisos_json(nuevos_permisos)
    return jsonify({"success": True})

# ==========================================
# GESTIÓN DE CATEGORÍAS
# ==========================================

# En routes/config_routes.py

 # <--- Asegúrate de importar esto arriba si no está

@config_bp.route('/categorias')
@login_requerido
@permiso_modulo("categorias")
def categorias():
    conn = get_db_connection()
    with conn.cursor() as cur:
        # 1. Categorías
        cur.execute("SELECT categoria_id, nombre_categoria FROM Categorias ORDER BY nombre_categoria ASC")
        cats = cur.fetchall()

        # 2. Productos (AHORA TRAEMOS TAMBIÉN EL ID)
        cur.execute("SELECT producto_id, nombre, categoria_id FROM Productos WHERE categoria_id IS NOT NULL ORDER BY nombre ASC")
        prods = cur.fetchall()
    conn.close()

    # 3. Agrupar guardando ID y NOMBRE
    productos_map = defaultdict(list)
    
    for p in prods:
        # Manejo seguro de Tupla vs Diccionario
        if isinstance(p, dict):
            pid, nom, cid = p['producto_id'], p['nombre'], p['categoria_id']
        else:
            pid, nom, cid = p[0], p[1], p[2]
        
        # Guardamos el objeto completo
        productos_map[cid].append({'id': pid, 'nombre': nom})

    return render_template('config/categorias.html', categorias=cats, productos_map=productos_map)

@config_bp.route('/categorias/nueva', methods=['POST'])
@login_requerido
@permiso_modulo("categorias")
def nueva_categoria():
    nombre = request.form.get('nombre_categoria')
    if nombre:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO Categorias (nombre_categoria) VALUES (%s)", (nombre,))
            conn.commit()
        except Exception as e:
            # Aquí podrías usar flash para mostrar error
            print(f"Error: {e}")
        finally:
            conn.close()
    return redirect(url_for('config.categorias'))

@config_bp.route('/categorias/eliminar/<int:id>')
@login_requerido
@permiso_modulo("categorias")
def eliminar_categoria(id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM Categorias WHERE categoria_id = %s", (id,))
        conn.commit()
    except Exception as e:
        # Esto pasará si hay productos usando esta categoría
        print(f"No se puede eliminar: {e}") 
    finally:
        conn.close()
    return redirect(url_for('config.categorias'))


# ==========================================
# GESTIÓN DE PRODUCTOS
# ==========================================

@config_bp.route('/productos')
@login_requerido
@permiso_modulo("productos")
def productos():
    conn = get_db_connection()
    with conn.cursor() as cur:
        # Traemos productos + nombre de su categoría
        query = """
            SELECT p.producto_id, p.sku, p.nombre, p.unidad_medida, p.stock_minimo, p.es_mayorista, c.nombre_categoria
            FROM Productos p
            LEFT JOIN Categorias c ON p.categoria_id = c.categoria_id
            ORDER BY p.nombre ASC
        """
        cur.execute(query)
        prods = cur.fetchall()
    conn.close()
    return render_template('config/productos.html', productos=prods)

# En routes/config_routes.py

# routes/config_routes.py

@config_bp.route('/productos/nuevo', methods=['GET', 'POST'])
@login_requerido
@permiso_modulo("productos")
def nuevo_producto():
    conn = get_db_connection()
    
    if request.method == 'POST':
        sku = request.form.get('sku')
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        # Ahora categoria_id viene directo del <select>, no de un input hidden
        categoria_id = request.form.get('categoria_id') 
        stock_minimo = request.form.get('stock_minimo')
        unidad = request.form.get('unidad_medida')
        es_mayorista = 1 if request.form.get('es_mayorista') == 'on' else 0
        unidades_por_caja = request.form.get('unidades_por_caja') or None

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO Productos (sku, nombre, descripcion, categoria_id, stock_minimo, unidad_medida, es_mayorista, unidades_por_caja)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (sku, nombre, descripcion, categoria_id, stock_minimo, unidad, es_mayorista, unidades_por_caja))
            conn.commit()
            conn.close()
            return redirect(url_for('config.productos'))
        except Exception as e:
            conn.close()
            return f"Error al guardar: {e}" 

    # GET: Mostrar formulario
    with conn.cursor() as cur:
        # 1. Categorías para el SELECT
        cur.execute("SELECT categoria_id, nombre_categoria FROM Categorias ORDER BY nombre_categoria")
        cats = cur.fetchall()
        
        # 2. Nombres para evitar duplicados
        cur.execute("SELECT nombre FROM Productos")
        all_prods = [row['nombre'] for row in cur.fetchall()]

        # 3. NUEVO: SKUs para sugerir (Autocomplete)
        cur.execute("SELECT sku FROM Productos")
        all_skus = [row['sku'] for row in cur.fetchall()]
        
    conn.close()
    
    return render_template('config/producto_nuevo.html', 
                           categorias=cats,
                           todos_los_productos=all_prods,
                           todos_los_skus=all_skus) # <--- Enviamos la lista de SKUs

# En routes/config_routes.py

@config_bp.route('/productos/editar/<int:id>', methods=['GET', 'POST'])
@login_requerido
@permiso_modulo("productos")
def editar_producto(id):
    conn = get_db_connection()

    if request.method == 'POST':
        sku = request.form.get('sku')
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        categoria_id = request.form.get('categoria_id')
        stock_minimo = request.form.get('stock_minimo')
        unidad = request.form.get('unidad_medida')
        es_mayorista = 1 if request.form.get('es_mayorista') == 'on' else 0
        unidades_por_caja = request.form.get('unidades_por_caja') or None

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE Productos 
                SET sku=%s, nombre=%s, descripcion=%s, categoria_id=%s, stock_minimo=%s, unidad_medida=%s, es_mayorista=%s, unidades_por_caja=%s
                WHERE producto_id=%s
            """, (sku, nombre, descripcion, categoria_id, stock_minimo, unidad, es_mayorista, unidades_por_caja, id))
        conn.commit()
        conn.close()
        return redirect(url_for('config.productos'))

    # GET: Cargar datos para el formulario
    with conn.cursor() as cur:
        # 1. El Producto a editar
        cur.execute("SELECT * FROM Productos WHERE producto_id=%s", (id,))
        prod = cur.fetchone()
        
        # 2. Categorías (Para el selector)
        cur.execute("SELECT categoria_id, nombre_categoria FROM Categorias ORDER BY nombre_categoria")
        cats = cur.fetchall()

        # 3. Listas para validar duplicados (excluyendo el actual)
        cur.execute("SELECT nombre FROM Productos WHERE producto_id != %s", (id,))
        all_prods = [row['nombre'] if isinstance(row, dict) else row[0] for row in cur.fetchall()]

        cur.execute("SELECT sku FROM Productos WHERE producto_id != %s", (id,))
        all_skus = [row['sku'] if isinstance(row, dict) else row[0] for row in cur.fetchall()]

    conn.close()

    if not prod:
        return redirect(url_for('config.productos'))

    return render_template('config/producto_editar.html', 
                           producto=prod, 
                           categorias=cats,
                           todos_los_productos=all_prods,
                           todos_los_skus=all_skus)
    
    
@config_bp.route('/productos/eliminar/<int:id>')
@login_requerido
@permiso_modulo("productos")
def eliminar_producto(id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM Productos WHERE producto_id=%s", (id,))
        conn.commit()
    except Exception as e:
        print(f"Error al eliminar: {e}")
    finally:
        conn.close()
    return redirect(url_for('config.productos'))

@config_bp.route('/productos/toggle_mayorista', methods=['POST'])
@login_requerido
@permiso_modulo("productos")
def toggle_mayorista():
    data = request.get_json()
    producto_id = data.get("producto_id")
    es_mayorista = 1 if data.get("es_mayorista") else 0
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE Productos SET es_mayorista = %s WHERE producto_id = %s", (es_mayorista, producto_id))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()


import os
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, render_template, current_app

@config_bp.route("/anuncios")
@login_requerido
@permiso_modulo("config") # O el permiso que uses para superusuario
def gestion_anuncios():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM anuncios_globales ORDER BY fecha_creacion DESC")
    anuncios = cursor.fetchall()
    conn.close()
    return render_template("config/anuncios.html", anuncios=anuncios)

@config_bp.route("/anuncios/guardar", methods=["POST"])
@login_requerido
@permiso_modulo("config")
def guardar_anuncio():
    anuncio_id = request.form.get("anuncio_id") # <-- NUEVO: Capturamos si viene un ID
    titulo = request.form.get("titulo")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    contenido_html = request.form.get("contenido_html")
    
    imagen_ruta = None
    if 'imagen' in request.files:
        file = request.files['imagen']
        if file.filename != '':
            filename = secure_filename(file.filename)
            ruta_guardado = os.path.join(current_app.config['UPLOAD_FOLDER_ANUNCIOS'], filename)
            file.save(ruta_guardado)
            imagen_ruta = filename

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if anuncio_id:
            # === MODO EDICIÓN (UPDATE) ===
            if imagen_ruta:
                # Si subió una nueva imagen, actualizamos todo
                cursor.execute("""
                    UPDATE anuncios_globales 
                    SET titulo=%s, contenido_html=%s, imagen_ruta=%s, fecha_inicio=%s, fecha_fin=%s
                    WHERE anuncio_id=%s
                """, (titulo, contenido_html, imagen_ruta, fecha_inicio, fecha_fin, anuncio_id))
            else:
                # Si no subió imagen, actualizamos todo menos la foto (conserva la que tenía)
                cursor.execute("""
                    UPDATE anuncios_globales 
                    SET titulo=%s, contenido_html=%s, fecha_inicio=%s, fecha_fin=%s
                    WHERE anuncio_id=%s
                """, (titulo, contenido_html, fecha_inicio, fecha_fin, anuncio_id))
        else:
            # === MODO NUEVO (INSERT) ===
            cursor.execute("""
                INSERT INTO anuncios_globales (titulo, contenido_html, imagen_ruta, fecha_inicio, fecha_fin, activo)
                VALUES (%s, %s, %s, %s, %s, 0)
            """, (titulo, contenido_html, imagen_ruta, fecha_inicio, fecha_fin))
            
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()

@config_bp.route("/anuncios/toggle", methods=["POST"])
@login_requerido
def toggle_anuncio():
    data = request.get_json()
    anuncio_id = data.get("anuncio_id")
    nuevo_estado = data.get("activo") # 1 o 0

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if nuevo_estado == 1:
            # 1. Regla de Exclusividad: Apagamos TODOS los demás
            cursor.execute("UPDATE anuncios_globales SET activo = 0")
            # 2. Encendemos el que pidieron
            cursor.execute("UPDATE anuncios_globales SET activo = 1 WHERE anuncio_id = %s", (anuncio_id,))
            # 3. RESET DE VISTAS: Borramos el historial para que vuelva a aparecer a todos
            cursor.execute("DELETE FROM anuncios_vistas WHERE anuncio_id = %s", (anuncio_id,))
        else:
            # Solo lo apagamos
            cursor.execute("UPDATE anuncios_globales SET activo = 0 WHERE anuncio_id = %s", (anuncio_id,))
            
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()
        
from flask import send_from_directory, current_app

# --- PEGAR AL FINAL DE config_routes.py ---
@config_bp.route("/uploads/anuncios/<filename>")
def ver_imagen_anuncio(filename):
    """Esta ruta permite al navegador leer la imagen desde la carpeta uploads protegida"""
    return send_from_directory(current_app.config['UPLOAD_FOLDER_ANUNCIOS'], filename)

# ==========================================
# GESTIÓN DE CARGA AGRÍCOLA (EXCEL -> DB)
# ==========================================

@config_bp.route("/agricola")
@login_requerido
@permiso_modulo("agricola")
def gestion_agricola():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cargas_agricola ORDER BY fecha_carga DESC LIMIT 5")
    cargas = cursor.fetchall()
    conn.close()
    return render_template("config/agricola_upload.html", cargas=cargas)

@config_bp.route("/agricola/upload", methods=["POST"])
@login_requerido
@permiso_modulo("agricola")
def upload_agricola():
    if 'archivo_excel' not in request.files:
        return jsonify({"success": False, "error": "No se envió ningún archivo"})
        
    file = request.files['archivo_excel']
    if file.filename == '':
        return jsonify({"success": False, "error": "Archivo vacío"})

    filename = secure_filename(file.filename)
    temp_dir = os.path.join(current_app.root_path, 'uploads', 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, filename)
    file.save(file_path)

    conn = get_db_connection()
    cursor = conn.cursor()
    usuario_actual = session.get("usuario", "desconocido")

    try:
        n, _cid = ejecutar_carga_ventas(cursor, file_path, filename, "AGRICOLA", usuario_actual)
        conn.commit()
        from utils.sheet_cache import forzar_actualizacion
        forzar_actualizacion("agricola")
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()
        if os.path.exists(file_path):
            os.remove(file_path)

    return jsonify({"success": True, "mensaje": f"Se procesaron {n} registros exitosamente."})

@config_bp.route("/agricola/revertir/<int:carga_id>", methods=["POST"])
@login_requerido
@permiso_modulo("agricola")
def revertir_carga_agricola(carga_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cargas_agricola WHERE carga_id = %s", (carga_id,))
        conn.commit()
        from utils.sheet_cache import forzar_actualizacion
        forzar_actualizacion("agricola")
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()


# ==========================================
# GESTIÓN DE CARGA COMERCIAL (EXCEL -> ventas_comercial, una sucursal por archivo)
# ==========================================

@config_bp.route("/comercial")
@login_requerido
@permiso_modulo("agricola")
def gestion_comercial():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cargas_comercial ORDER BY fecha_carga DESC LIMIT 15")
    cargas = cursor.fetchall()
    conn.close()
    return render_template("config/comercial_upload.html", cargas=cargas, max_comercial=MAX_ARCHIVOS_COMERCIAL)


@config_bp.route("/comercial/cargas")
@login_requerido
@permiso_modulo("agricola")
def historial_cargas_comercial():
    """
    Listado paginado de todas las cargas comerciales (revertir cualquier ID).
    Query: page (default 1), per (10–100, default 30), q (opcional: ID exacto o texto en nombre de archivo).
    """
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per = int(request.args.get("per", 30))
    except (TypeError, ValueError):
        per = 30
    per = max(10, min(100, per))
    q = (request.args.get("q") or "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    where_sql = ""
    params = []
    if q:
        if q.isdigit():
            where_sql = "WHERE (carga_id = %s OR nombre_archivo LIKE %s)"
            params = [int(q), f"%{q}%"]
        else:
            where_sql = "WHERE nombre_archivo LIKE %s"
            params = [f"%{q}%"]

    cursor.execute(f"SELECT COUNT(*) AS n FROM cargas_comercial {where_sql}", params)
    total = int(cursor.fetchone()["n"])
    total_pages = max(1, (total + per - 1) // per) if total else 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per
    cursor.execute(
        f"SELECT * FROM cargas_comercial {where_sql} ORDER BY fecha_carga DESC LIMIT %s OFFSET %s",
        params + [per, offset],
    )
    cargas = cursor.fetchall()
    conn.close()

    return render_template(
        "config/comercial_cargas_historial.html",
        cargas=cargas,
        page=page,
        per_page=per,
        total=total,
        total_pages=total_pages,
        q=q,
    )


@config_bp.route("/comercial/upload", methods=["POST"])
@login_requerido
@permiso_modulo("agricola")
def upload_comercial():
    archivos = request.files.getlist("archivos_comercial")
    archivos = [f for f in archivos if f and f.filename]
    if not archivos:
        return jsonify({"success": False, "error": "No se enviaron archivos."})
    if len(archivos) > MAX_ARCHIVOS_COMERCIAL:
        return jsonify({"success": False, "error": f"Máximo {MAX_ARCHIVOS_COMERCIAL} archivos por carga."})

    temp_dir = os.path.join(current_app.root_path, "uploads", "temp_comercial")
    os.makedirs(temp_dir, exist_ok=True)
    usuario_actual = session.get("usuario", "desconocido")
    reporte = []

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for file in archivos:
            filename = secure_filename(file.filename)
            file_path = os.path.join(temp_dir, filename)
            file.save(file_path)
            try:
                sucursal = inferir_sucursal_comercial(filename)
                n, _cid = ejecutar_carga_ventas(
                    cursor, file_path, filename, "COMERCIAL", usuario_actual, sucursal_comercial=sucursal
                )
                reporte.append({"archivo": filename, "sucursal": sucursal, "estado": "ok", "registros": n})
            except Exception as e:
                reporte.append({"archivo": filename, "estado": "error", "error": str(e)})
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)

        conn.commit()
        from utils.sheet_cache import forzar_actualizacion
        forzar_actualizacion("comercial")
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()

    errores = [r for r in reporte if r.get("estado") == "error"]
    return jsonify({
        "success": len(errores) == 0,
        "mensaje": f"Comercial: OK {len(reporte) - len(errores)}, error {len(errores)}",
        "reporte": reporte,
    })


@config_bp.route("/comercial/revertir/<int:carga_id>", methods=["POST"])
@login_requerido
@permiso_modulo("agricola")
def revertir_carga_comercial(carga_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cargas_comercial WHERE carga_id = %s", (carga_id,))
        conn.commit()
        from utils.sheet_cache import forzar_actualizacion
        forzar_actualizacion("comercial")
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        conn.close()