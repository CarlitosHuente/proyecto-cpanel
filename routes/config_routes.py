from flask import Blueprint, render_template, request, redirect, url_for, abort
from utils.auth import login_requerido, permiso_modulo, PERMISOS
from utils.db import get_db_connection
from werkzeug.security import generate_password_hash

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