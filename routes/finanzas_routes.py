from flask import Blueprint, render_template, request, flash, redirect, url_for
from utils.db import get_db_connection
from utils.auth import login_requerido, permiso_modulo
from datetime import datetime, date, timedelta
import calendar

finanzas_bp = Blueprint('finanzas', __name__, url_prefix='/finanzas')

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}
DIAS_ES = { 0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom" }

@finanzas_bp.route('/flujo')
@login_requerido
@permiso_modulo('flujo')
def flujo():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # --- 1. Filtros ---
        anio_actual = datetime.now().year
        mes_actual = datetime.now().month
        
        try:
            anio = int(request.args.get('anio', anio_actual))
            mes = int(request.args.get('mes', mes_actual))
        except ValueError:
            anio = anio_actual
            mes = mes_actual
            
        vista = request.args.get('vista', 'diaria')

        # --- 2. Definir Rango de Datos (La lógica inteligente) ---
        _, num_dias_mes = calendar.monthrange(anio, mes)
        
        # Fechas "Duras" del mes (1 al 30/31)
        fecha_primero_mes = date(anio, mes, 1)
        fecha_ultimo_mes = date(anio, mes, num_dias_mes)

        if vista == 'semanal':
            # Si es semanal, extendemos el rango para completar semanas (Lun-Dom)
            # Retrocedemos al Lunes de la primera semana
            dias_retroceder = fecha_primero_mes.weekday() # 0=Lun, 6=Dom
            fecha_inicio_vista = fecha_primero_mes - timedelta(days=dias_retroceder)
            
            # Avanzamos al Domingo de la última semana
            dias_avanzar = 6 - fecha_ultimo_mes.weekday()
            fecha_fin_vista = fecha_ultimo_mes + timedelta(days=dias_avanzar)
        else:
            # Si es diario, respetamos estrictamente el mes
            fecha_inicio_vista = fecha_primero_mes
            fecha_fin_vista = fecha_ultimo_mes

        # --- 3. Construcción de Columnas ---
        columnas = []
        mapa_fecha_columna = {}

        if vista == 'semanal':
            # Iteramos desde el Lunes (posiblemente mes anterior) hasta el Domingo (posiblemente mes siguiente)
            delta_total = (fecha_fin_vista - fecha_inicio_vista).days + 1
            semanas_temp = {}
            
            for i in range(delta_total):
                dia_obj = fecha_inicio_vista + timedelta(days=i)
                # Usamos el número de semana ISO y el año ISO para evitar bugs en cambio de año
                year_iso, week_iso, _ = dia_obj.isocalendar()
                
                # Clave única para la semana (Ej: 2025-52 o 2026-01)
                key_semana = f"{year_iso}-{week_iso}"
                
                if key_semana not in semanas_temp:
                    semanas_temp[key_semana] = {
                        'id': key_semana,
                        'titulo': f"Sem {week_iso}",
                        'subtitulo': "", 
                        'inicio': dia_obj,
                        'fin': dia_obj,
                        'es_finde': False
                    }
                
                # Actualizamos el fin de la semana
                semanas_temp[key_semana]['fin'] = dia_obj
                mapa_fecha_columna[dia_obj] = key_semana

            # Formatear subtítulos (Ej: 29/12 - 04/01)
            for s_id, s_data in semanas_temp.items():
                ini = s_data['inicio']
                fin = s_data['fin']
                s_data['subtitulo'] = f"{ini.day}/{ini.month} - {fin.day}/{fin.month}"
                columnas.append(s_data)
        
        else:
            # Vista Diaria (1 al 31)
            delta_total = (fecha_fin_vista - fecha_inicio_vista).days + 1
            for i in range(delta_total):
                dia_obj = fecha_inicio_vista + timedelta(days=i)
                col_id = dia_obj
                mapa_fecha_columna[dia_obj] = col_id
                
                columnas.append({
                    'id': col_id,
                    'titulo': str(dia_obj.day),
                    'subtitulo': DIAS_ES[dia_obj.weekday()],
                    'es_finde': dia_obj.weekday() >= 5
                })

        # --- 4. Saldo Inicial Acumulado ---
        # OJO: Calculamos el saldo hasta ANTES de la 'fecha_inicio_vista'.
        # Si la vista empieza el 29 Dic (siendo Enero el mes seleccionado), el saldo inicial es hasta el 28 Dic.
        query_saldo = """
            SELECT COALESCE(SUM(CASE WHEN tipo='ingreso' THEN monto ELSE -monto END), 0) as saldo
            FROM flujo_movimientos 
            WHERE fecha < %s AND estado != 'anulado'
        """
        cursor.execute(query_saldo, (fecha_inicio_vista,))
        saldo_inicial_acumulado = cursor.fetchone()['saldo']

        # --- 5. Cargar Datos (Rango Extendido) ---
        cursor.execute("SELECT * FROM flujo_categorias WHERE activo = 1 ORDER BY nombre")
        categorias_db = cursor.fetchall()

        # Buscamos datos entre el inicio y fin VISTA (que puede incluir días de otros meses)
        query_movs = """
            SELECT fecha, categoria_id, tipo, descripcion, monto 
            FROM flujo_movimientos 
            WHERE fecha BETWEEN %s AND %s AND estado != 'anulado'
        """
        cursor.execute(query_movs, (fecha_inicio_vista, fecha_fin_vista))
        movimientos_db = cursor.fetchall()

        # --- 6. Procesamiento (Igual que antes) ---
        totales_por_columna = {col['id']: {'ingreso': 0, 'egreso': 0} for col in columnas}
        
        tree = {}
        for cat in categorias_db:
            tree[cat['id']] = {
                'info': cat,
                'total_periodo': 0, # Cambié nombre a 'total_periodo' para ser más exacto
                'valores': {},
                'subitems': {}
            }

        for mov in movimientos_db:
            fecha = mov['fecha']
            cat_id = mov['categoria_id']
            monto = mov['monto']
            tipo = mov['tipo']
            desc = mov['descripcion'] if mov['descripcion'] else "General"
            
            col_id = mapa_fecha_columna.get(fecha)
            
            if col_id is not None:
                totales_por_columna[col_id][tipo] += monto
                
                if cat_id in tree:
                    tree[cat_id]['valores'][col_id] = tree[cat_id]['valores'].get(col_id, 0) + monto
                    tree[cat_id]['total_periodo'] += monto # Suma total visible

                    if desc not in tree[cat_id]['subitems']:
                        tree[cat_id]['subitems'][desc] = {'valores': {}, 'total_sub': 0}
                    
                    tree[cat_id]['subitems'][desc]['valores'][col_id] = \
                        tree[cat_id]['subitems'][desc]['valores'].get(col_id, 0) + monto
                    tree[cat_id]['subitems'][desc]['total_sub'] += monto

        data_view = {
            'ingreso': [v for k, v in tree.items() if v['info']['tipo'] == 'ingreso'],
            'egreso': [v for k, v in tree.items() if v['info']['tipo'] == 'egreso']
        }

        return render_template('finanzas/flujo.html', 
                               anio=anio, mes=mes,
                               columnas=columnas,
                               vista=vista,
                               data_view=data_view,
                               totales_por_columna=totales_por_columna,
                               saldo_inicial_acumulado=saldo_inicial_acumulado,
                               nombre_mes=MESES_ES[mes])

    except Exception as e:
        print(f"Error flujo: {e}")
        return redirect(url_for('dashboard.dashboard'))
    finally:
        cursor.close()
        conn.close()

# Ruta Pagos (Placeholder)
@finanzas_bp.route('/pagos', methods=['GET', 'POST'])
@login_requerido
@permiso_modulo('flujo')
def pagos():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # --- PROCESAR FORMULARIO (GUARDAR) ---
        if request.method == 'POST':
            fecha = request.form['fecha']
            tipo = request.form['tipo'] # 'ingreso' o 'egreso'
            categoria_id = request.form['categoria_id']
            entidad_id = request.form['entidad_id']
            monto = request.form['monto']
            descripcion = request.form['descripcion']
            
            # Validaciones básicas
            if not monto or float(monto) <= 0:
                flash("El monto debe ser mayor a 0", "warning")
            elif not categoria_id or not entidad_id:
                flash("Debe seleccionar Categoría y Entidad", "warning")
            else:
                # Insertar en DB
                query_insert = """
                    INSERT INTO flujo_movimientos 
                    (fecha, tipo, monto, categoria_id, entidad_id, descripcion, estado, usuario_responsable)
                    VALUES (%s, %s, %s, %s, %s, %s, 'real', %s)
                """
                cursor.execute(query_insert, (
                    fecha, tipo, monto, categoria_id, entidad_id, descripcion, session.get('usuario')
                ))
                conn.commit()
                
                flash(f"✅ Movimiento registrado correctamente.", "success")
                return redirect(url_for('finanzas.flujo'))

        # --- CARGAR VISTA (GET) ---
        
        # 1. Cargar Categorías separadas para el Select Dinámico
        cursor.execute("SELECT * FROM flujo_categorias WHERE activo = 1 ORDER BY nombre")
        cats = cursor.fetchall()
        cats_ingreso = [c for c in cats if c['tipo'] == 'ingreso']
        cats_egreso = [c for c in cats if c['tipo'] == 'egreso']

        # 2. Cargar Entidades
        cursor.execute("SELECT * FROM flujo_entidades WHERE activo = 1 ORDER BY nombre")
        entidades = cursor.fetchall()
        
        # Fecha por defecto: Hoy
        hoy = date.today().strftime('%Y-%m-%d')

        return render_template('finanzas/pagos.html', 
                               cats_ingreso=cats_ingreso,
                               cats_egreso=cats_egreso,
                               entidades=entidades,
                               hoy=hoy)

    except Exception as e:
        conn.rollback()
        print(f"Error en pagos: {e}")
        flash(f"Error al procesar: {e}", "danger")
        return redirect(url_for('finanzas.flujo'))
    finally:
        cursor.close()
        conn.close()