from flask import Blueprint, render_template, request, redirect, url_for, abort
from utils.auth import login_requerido, permiso_modulo, PERMISOS
from utils.db import get_db_connection
from werkzeug.security import generate_password_hash


config_bp = Blueprint('config', __name__, url_prefix='/config')

@config_bp.route('/usuarios')
@login_requerido
@permiso_modulo("config")
def usuarios():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, email, rol, activo, creado_en FROM usuarios_huente ORDER BY id ASC")
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

        with conn.cursor() as cur:
            if nueva_clave:
                password_hash = generate_password_hash(nueva_clave)
                cur.execute(
                    """
                    UPDATE usuarios_huente
                    SET email=%s, rol=%s, activo=%s, password_hash=%s
                    WHERE id=%s
                    """,
                    (email, rol, activo, password_hash, user_id)
                )
            else:
                cur.execute(
                    """
                    UPDATE usuarios_huente
                    SET email=%s, rol=%s, activo=%s
                    WHERE id=%s
                    """,
                    (email, rol, activo, user_id)
                )
            conn.commit()

        conn.close()
        return redirect(url_for('config.usuarios'))

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, rol, activo FROM usuarios_huente WHERE id=%s",
            (user_id,)
        )
        usuario = cur.fetchone()
    conn.close()

    if not usuario:
        abort(404)

    return render_template('config/usuario_editar.html',
                       usuario=usuario,
                       roles=PERMISOS.keys())



@config_bp.route('/usuarios/nuevo', methods=['GET', 'POST'])
@login_requerido
@permiso_modulo("config")
def nuevo_usuario():
    conn = get_db_connection()

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        rol = request.form.get("rol", "").strip()
        activo = 1 if request.form.get("activo") == "on" else 0
        password = request.form.get("password", "").strip()

        if not email or not rol or not password:
            conn.close()
            return render_template("config/usuario_nuevo.html",
                                error="Todos los campos son obligatorios.",
                                roles=PERMISOS.keys())
        password_hash = generate_password_hash(password)

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO usuarios_huente (email, rol, activo, password_hash)
                VALUES (%s, %s, %s, %s)
            """, (email, rol, activo, password_hash))
            conn.commit()

        conn.close()
        return redirect(url_for("config.usuarios"))

    conn.close()
    return render_template("config/usuario_nuevo.html",
                       roles=PERMISOS.keys())

