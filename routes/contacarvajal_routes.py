from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from utils.db import get_db_connection
from utils.auth import login_requerido, permiso_modulo
import requests # <--- Agregar importación
import calendar # <--- Para saber el último día del mes
from datetime import datetime # <--- Para manejar fechas

contacarvajal_bp = Blueprint('contacarvajal', __name__, url_prefix='/contacarvajal')

@contacarvajal_bp.route('/clientes', methods=['GET', 'POST'])
@login_requerido
@permiso_modulo('contacarvajal')
def clientes():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        # Lógica para CREAR cliente
        try:
            sql = """INSERT INTO clientes_contables 
                     (tipo_contribuyente, rut, razon_social, rut_rep, nombre_rep, 
                      clave_sii, clave_previred, honorario_pactado, email_contacto)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            datos = (
                request.form['tipo'], request.form['rut'], request.form['nombre'],
                request.form['rut_rep'], request.form['nombre_rep'],
                request.form['clave_sii'], request.form['clave_previred'],
                request.form['honorario'] or 0, request.form['email']
            )
            cursor.execute(sql, datos)
            conn.commit()
            flash('Cliente registrado correctamente.', 'success')
        except Exception as e:
            flash(f'Error al guardar: {e}', 'danger')
        
    # Obtener lista de clientes
    cursor.execute("SELECT * FROM clientes_contables WHERE activo = 1 ORDER BY razon_social ASC")
    clientes = cursor.fetchall()
    conn.close()
    
    return render_template('contacarvajal/clientes.html', clientes=clientes)

@contacarvajal_bp.route('/control', methods=['GET'])
@login_requerido
@permiso_modulo('contacarvajal')
def control():
    # Obtener mes/año del request o usar actuales por defecto
    hoy = datetime.now()
    mes = request.args.get('mes', hoy.month)
    anio = request.args.get('anio', hoy.year)
    
    # 1. LLAMAMOS A LA NUEVA FUNCIÓN
    valor_uf = obtener_uf_al_cierre(mes, anio)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # ... (Tu Query SQL original LEFT JOIN sigue igual) ...
    sql = """
        SELECT c.id, c.razon_social, c.honorario_pactado, 
               h.id as control_id, h.boleta_emitida, h.nro_boleta, h.monto_boleta
        FROM clientes_contables c
        LEFT JOIN control_honorarios h 
        ON c.id = h.cliente_id AND h.mes = %s AND h.anio = %s
        WHERE c.activo = 1
        ORDER BY c.razon_social
    """
    cursor.execute(sql, (mes, anio))
    registros = cursor.fetchall()
    conn.close()
    
    # Pasamos 'valor_uf' al template
    return render_template('contacarvajal/control.html', 
                           registros=registros, 
                           mes=mes, 
                           anio=anio, 
                           valor_uf=valor_uf) # <--- IMPORTANTE

@contacarvajal_bp.route('/actualizar_boleta', methods=['POST'])
@login_requerido
@permiso_modulo('contacarvajal')
def actualizar_boleta():
    try:
        # 1. Obtener datos y limpiar espacios vacíos
        cliente_id = request.form['cliente_id']
        mes = request.form['mes']
        anio = request.form['anio']
        
        raw_nro = request.form.get('nro_boleta', '').strip()
        raw_monto = request.form.get('monto', '').strip()

        # 2. Conversión inteligente: Si está vacío es None (NULL en SQL), si tiene dato es int
        nro_boleta = int(raw_nro) if raw_nro else None
        monto_boleta = int(raw_monto) if raw_monto else None
        
        # 3. Determinar si está emitida (Si hay número, está emitida)
        boleta_emitida = 1 if nro_boleta else 0

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 4. Upsert (Insertar o Actualizar)
        sql = """
            INSERT INTO control_honorarios 
            (cliente_id, mes, anio, nro_boleta, monto_boleta, boleta_emitida)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            nro_boleta = VALUES(nro_boleta), 
            monto_boleta = VALUES(monto_boleta),
            boleta_emitida = VALUES(boleta_emitida)
        """
        cursor.execute(sql, (cliente_id, mes, anio, nro_boleta, monto_boleta, boleta_emitida))
        conn.commit()
        conn.close()
        
        flash('Registro actualizado correctamente', 'success')

    except ValueError:
        flash('Error: Debes ingresar números válidos, no texto.', 'danger')
    except Exception as e:
        flash(f'Error inesperado: {str(e)}', 'danger')
    
    return redirect(url_for('contacarvajal.control', mes=mes, anio=anio))

def obtener_uf_al_cierre(mes, anio):
    """
    Obtiene la UF del último día del mes seleccionado.
    Si el mes es el actual, obtiene la de hoy.
    """
    try:
        mes = int(mes)
        anio = int(anio)
        hoy = datetime.now()
        
        # Determinar la fecha de cierre
        if mes == hoy.month and anio == hoy.year:
            # Si es el mes en curso, usamos la UF de HOY
            dia = hoy.day
        else:
            # Si es un mes pasado (o futuro), usamos el último día del mes
            _, dia = calendar.monthrange(anio, mes)
        
        # Formato para la API: dd-mm-yyyy
        fecha_str = f"{dia}-{mes}-{anio}"
        url = f"https://mindicador.cl/api/uf/{fecha_str}"
        
        response = requests.get(url, timeout=3) # Timeout de 3 seg para no pegar la app
        if response.status_code == 200:
            data = response.json()
            if data['serie']:
                return data['serie'][0]['valor'] # Retorna float (ej: 38000.55)
    except Exception as e:
        print(f"Error obteniendo UF: {e}")
    
    return 0 # Si falla, retorna 0