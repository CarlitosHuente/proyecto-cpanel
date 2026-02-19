from flask import Blueprint, render_template, session
from utils.db import get_db_connection
from utils.auth import login_requerido, permiso_modulo
import calendar
from datetime import datetime
from flask import request

fabrica_bp = Blueprint('fabrica', __name__)

# Modifica la ruta en fabrica_routes.py
@fabrica_bp.route('/fabrica/calendario')
@login_requerido
@permiso_modulo('fabrica')
def calendario_produccion():
    # Obtener mes y año de la URL o usar los actuales
    anio = request.args.get('anio', datetime.now().year, type=int)
    mes = request.args.get('mes', datetime.now().month, type=int)
    
    # Lógica para evitar meses fuera de rango (1-12)
    if mes > 12: 
        mes = 1
        anio += 1
    elif mes < 1:
        mes = 12
        anio -= 1

# INICIO LOGICA DE CONSULTA CORREGIDA #}
    # Obtener datos de la DB para el mes solicitado
    conn = get_db_connection()
    cur = conn.cursor()
    
    # IMPORTANTE: Usamos %%Y y %%m-%%d para que Python no se confunda
    cur.execute("""
        SELECT *, DAY(fecha) as dia, DATE_FORMAT(fecha, '%%Y-%%m-%%d') as fecha_str 
        FROM fabrica_produccion 
        WHERE MONTH(fecha) = %s AND YEAR(fecha) = %s
    """, (mes, anio))
    
    produccion_mes = {row['dia']: row for row in cur.fetchall()}
    conn.close()
# FIN LOGICA DE CONSULTA #}

    cal = calendar.monthcalendar(anio, mes)
    
    # Nombres de meses en español para la cabecera
    meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    
    return render_template('fabrica/calendario.html', 
                           calendario=cal, 
                           datos=produccion_mes, 
                           mes_nombre=meses_es[mes-1],
                           mes=mes,
                           anio=anio)