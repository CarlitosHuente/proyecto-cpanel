from flask import Blueprint, render_template, request, redirect, url_for, abort
from utils.auth import login_requerido, permiso_modulo, PERMISOS
from utils.db import get_db_connection
from werkzeug.security import generate_password_hash
from collections import defaultdict

config_bp = Blueprint('config', __name__, url_prefix='/config')

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

# routes/config_routes.py (AGREGAR AL FINAL)

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
            SELECT p.producto_id, p.sku, p.nombre, p.unidad_medida, p.stock_minimo, c.nombre_categoria
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

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO Productos (sku, nombre, descripcion, categoria_id, stock_minimo, unidad_medida)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (sku, nombre, descripcion, categoria_id, stock_minimo, unidad))
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

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE Productos 
                SET sku=%s, nombre=%s, descripcion=%s, categoria_id=%s, stock_minimo=%s, unidad_medida=%s
                WHERE producto_id=%s
            """, (sku, nombre, descripcion, categoria_id, stock_minimo, unidad, id))
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