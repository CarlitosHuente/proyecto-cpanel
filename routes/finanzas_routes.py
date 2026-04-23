from flask import Blueprint, render_template, request, flash, redirect, url_for, session, send_from_directory, Response
from utils.db import get_db_connection
from utils.auth import login_requerido, permiso_modulo
from datetime import datetime, date, timedelta
import calendar
import os
import time
from werkzeug.utils import secure_filename

finanzas_bp = Blueprint('finanzas', __name__, url_prefix='/finanzas')

# --- CONFIGURACIÓN DE CARPETA LOCAL PARA RESPALDOS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_FOLDER_PAGOS = os.path.join(BASE_DIR, "uploads", "pagos")
os.makedirs(UPLOAD_FOLDER_PAGOS, exist_ok=True)

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}
DIAS_ES = { 0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom" }

BANCOS_CHILE = {
    "001": {"nombre": "Banco de Chile / Edwards", "rut": "970040005"},
    "012": {"nombre": "Banco del Estado de Chile", "rut": "970300007"},
    "037": {"nombre": "Banco Santander Chile", "rut": "97036000K"},
    "016": {"nombre": "Banco BCI / Mach", "rut": "970060006"},
    "039": {"nombre": "Banco Itaú Chile", "rut": "970230009"},
    "014": {"nombre": "Scotiabank Chile", "rut": "970180001"},
    "051": {"nombre": "Banco Falabella", "rut": "965096604"},
    "053": {"nombre": "Banco Ripley", "rut": "979470002"},
    "049": {"nombre": "Banco Security", "rut": "970530002"},
    "028": {"nombre": "Banco BICE", "rut": "97080000K"},
    "055": {"nombre": "Banco Consorcio", "rut": "995004100"},
    "009": {"nombre": "Banco Internacional", "rut": "970110003"},
    "060": {"nombre": "Coopeuch", "rut": "815010007"},
    "076": {"nombre": "Mercado Pago", "rut": "774565721"},
    "074": {"nombre": "Tenpo Prepago", "rut": "771339462"},
    "081": {"nombre": "Tapp (Caja Los Andes)", "rut": "772612804"},
    "073": {"nombre": "Global66", "rut": "769534571"},
    "077": {"nombre": "Prepago Los Héroes", "rut": "768042845"},
    "031": {"nombre": "HSBC Bank Chile", "rut": "970430008"},
    "059": {"nombre": "Banco BTG Pactual", "rut": "970340009"}
}

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

# --- NUEVO MÓDULO: BANCO Y PAGOS MASIVOS ---
@finanzas_bp.route('/banco', methods=['GET', 'POST'])
@login_requerido
@permiso_modulo('flujo')
def banco():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if request.method == 'POST':
            accion = request.form.get('accion')
            
            # --- AGREGAR PROVEEDOR (AGENDA) ---
            if accion == 'add_proveedor':
                # Limpiamos el RUT de puntos, guiones y lo dejamos en mayúscula
                rut = request.form.get('rut').replace(".", "").replace("-", "").strip().upper()
                nombre = request.form.get('nombre').strip()
                email = request.form.get('email').strip()
                banco_codigo = request.form.get('banco_codigo')
                tipo_cuenta = request.form.get('tipo_cuenta')
                numero_cuenta = request.form.get('numero_cuenta').replace("-", "").strip()
                
                if not rut or not nombre or not email or not numero_cuenta:
                    flash("Todos los campos son obligatorios.", "warning")
                else:
                    try:
                        cursor.execute("""
                            INSERT INTO banco_proveedores 
                            (rut, nombre, email, banco_codigo, tipo_cuenta, numero_cuenta) 
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (rut, nombre, email, banco_codigo, tipo_cuenta, numero_cuenta))
                        conn.commit()
                        flash(f"Destinatario '{nombre}' agregado a la agenda.", "success")
                    except Exception as db_err:
                        if "Duplicate entry" in str(db_err):
                            flash("Ese RUT ya se encuentra registrado en tu agenda.", "danger")
                        else:
                            raise db_err

            # --- AGREGAR PAGO AL CARRITO ---
            elif accion == 'add_pago':
                proveedor_id = request.form.get('proveedor_id')
                monto = request.form.get('monto')
                motivo = request.form.get('motivo')
                asunto_email = request.form.get('asunto_email')
                
                respaldo_file_id = None
                respaldo_url = None
                
                try:
                    cursor.execute("""
                        INSERT INTO banco_transferencias 
                        (proveedor_id, monto, motivo, asunto_email, respaldo_file_id, respaldo_url)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (proveedor_id, monto, motivo, asunto_email, respaldo_file_id, respaldo_url))
                    conn.commit()
                    flash("Pago agregado a la nómina correctamente.", "success")
                except Exception as db_err:
                    conn.rollback()
                    flash(f"Error al guardar el pago: {db_err}", "danger")

            # --- ELIMINAR PAGO DEL CARRITO ---
            elif accion == 'delete_pago':
                pago_id = request.form.get('pago_id')
                try:
                    # Solo permite borrar si nomina_id es NULL (aún no se genera el TXT)
                    cursor.execute("DELETE FROM banco_transferencias WHERE id = %s AND nomina_id IS NULL", (pago_id,))
                    conn.commit()
                    flash("Pago eliminado de la nómina actual.", "success")
                except Exception as e:
                    flash(f"Error al eliminar: {e}", "danger")
                    
            # --- EDITAR PAGO EN EL CARRITO ---
            elif accion == 'edit_pago':
                pago_id = request.form.get('pago_id')
                monto = request.form.get('monto')
                motivo = request.form.get('motivo')
                asunto_email = request.form.get('asunto_email')
                
                try:
                    # Solo permite editar si nomina_id es NULL
                    cursor.execute("""
                        UPDATE banco_transferencias 
                        SET monto = %s, motivo = %s, asunto_email = %s 
                        WHERE id = %s AND nomina_id IS NULL
                    """, (monto, motivo, asunto_email, pago_id))
                    conn.commit()
                    flash("Pago actualizado correctamente.", "success")
                except Exception as e:
                    flash(f"Error al actualizar: {e}", "danger")

            # --- GENERAR TXT Y DESCARGAR ---
            elif accion == 'generar_txt':
                try:
                    cursor.execute("""
                        SELECT t.*, p.nombre as proveedor_nombre, p.rut as proveedor_rut, p.banco_codigo,
                               p.tipo_cuenta, p.numero_cuenta, p.email
                        FROM banco_transferencias t
                        JOIN banco_proveedores p ON t.proveedor_id = p.id
                        WHERE t.nomina_id IS NULL AND t.estado = 'pendiente'
                        ORDER BY t.creado_en ASC
                    """)
                    pagos = cursor.fetchall()
                    
                    if not pagos:
                        flash("No hay pagos en la nómina para generar.", "warning")
                        return redirect(url_for('finanzas.banco'))
                        
                    # ---> ¡ATENCIÓN AQUÍ! REEMPLAZA CON LOS DATOS DE TU EMPRESA <---
                    RUT_EMPRESA = "773328048" 
                    CUENTA_EMPRESA = "008040118010"
                    
                    lineas = []
                    monto_total = 0
                    
                    for pago in pagos:
                        tipo_op = "TOB"
                        rut_cliente = str(RUT_EMPRESA).replace(".", "").replace("-", "").upper().zfill(10)
                        cuenta_cargo = str(CUENTA_EMPRESA).replace("-", "").zfill(12)
                        
                        rut_benef = str(pago['proveedor_rut']).replace(".", "").replace("-", "").upper().zfill(10)
                        nombre = str(pago['proveedor_nombre']).ljust(30)[:30]
                        cuenta_benef = str(pago['numero_cuenta']).replace("-", "").ljust(18)[:18]
                        rut_banco = str(BANCOS_CHILE.get(pago['banco_codigo'], {}).get('rut', '')).upper().zfill(10)
                        
                        monto_val = int(pago['monto'])
                        monto_total += monto_val
                        monto = str(monto_val).zfill(11)
                        
                        espacio = " "
                        motivo = str(pago['motivo']).ljust(30)[:30]
                        notificacion = "1" # "1" para enviar email automático
                        asunto = str(pago['asunto_email']).ljust(30)[:30]
                        email = str(pago['email']).ljust(50)[:50]
                        tipo_cuenta = str(pago['tipo_cuenta']).ljust(3)[:3]
                        
                        linea = f"{tipo_op}{rut_cliente}{cuenta_cargo}{rut_benef}{nombre}{cuenta_benef}{rut_banco}{monto}{espacio}{motivo}{notificacion}{asunto}{email}{tipo_cuenta}"
                        lineas.append(linea)
                        
                    contenido_txt = "\n".join(lineas)
                    
                    # Congelar pagos asignándoles una nómina
                    cursor.execute("""
                        INSERT INTO banco_nominas (cantidad_pagos, monto_total, usuario_responsable)
                        VALUES (%s, %s, %s)
                    """, (len(pagos), monto_total, session.get('usuario')))
                    nomina_id = cursor.lastrowid
                    
                    cursor.execute("""
                        UPDATE banco_transferencias
                        SET nomina_id = %s, estado = 'procesado'
                        WHERE nomina_id IS NULL AND estado = 'pendiente'
                    """, (nomina_id,))
                    conn.commit()
                    
                    # Devolver el TXT de inmediato como archivo adjunto (Download)
                    nombre_archivo = f"Nomina_BancoChile_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    
                    return Response(
                        contenido_txt,
                        mimetype="text/plain",
                        headers={"Content-disposition": f"attachment; filename={nombre_archivo}"}
                    )
                    
                except Exception as e:
                    conn.rollback()
                    flash(f"Error al generar TXT: {e}", "danger")
                    
            # --- RE-DESCARGAR TXT (HISTORIAL) ---
            elif accion == 'redescargar_txt':
                nomina_id = request.form.get('nomina_id')
                try:
                    cursor.execute("""
                        SELECT t.*, p.nombre as proveedor_nombre, p.rut as proveedor_rut, p.banco_codigo,
                               p.tipo_cuenta, p.numero_cuenta, p.email
                        FROM banco_transferencias t
                        JOIN banco_proveedores p ON t.proveedor_id = p.id
                        WHERE t.nomina_id = %s
                        ORDER BY t.creado_en ASC
                    """, (nomina_id,))
                    pagos = cursor.fetchall()
                    
                    if not pagos:
                        flash("No se encontraron pagos para esta nómina.", "warning")
                        return redirect(url_for('finanzas.banco'))
                        
                    # ---> ¡ATENCIÓN AQUÍ! REEMPLAZA CON LOS DATOS DE TU EMPRESA <---
                    RUT_EMPRESA = "773328048" 
                    CUENTA_EMPRESA = "008040118010"
                    
                    lineas = []
                    
                    for pago in pagos:
                        tipo_op = "TOB"
                        rut_cliente = str(RUT_EMPRESA).replace(".", "").replace("-", "").upper().zfill(10)
                        cuenta_cargo = str(CUENTA_EMPRESA).replace("-", "").zfill(12)
                        
                        rut_benef = str(pago['proveedor_rut']).replace(".", "").replace("-", "").upper().zfill(10)
                        nombre = str(pago['proveedor_nombre']).ljust(30)[:30]
                        cuenta_benef = str(pago['numero_cuenta']).replace("-", "").ljust(18)[:18]
                        rut_banco = str(BANCOS_CHILE.get(pago['banco_codigo'], {}).get('rut', '')).upper().zfill(10)
                        
                        monto = str(int(pago['monto'])).zfill(11)
                        
                        espacio = " "
                        motivo = str(pago['motivo']).ljust(30)[:30]
                        notificacion = "1"
                        asunto = str(pago['asunto_email']).ljust(30)[:30]
                        email = str(pago['email']).ljust(50)[:50]
                        tipo_cuenta = str(pago['tipo_cuenta']).ljust(3)[:3]
                        
                        lineas.append(f"{tipo_op}{rut_cliente}{cuenta_cargo}{rut_benef}{nombre}{cuenta_benef}{rut_banco}{monto}{espacio}{motivo}{notificacion}{asunto}{email}{tipo_cuenta}")
                        
                    # Descargar archivo con nombre indicando que es redescarga
                    nombre_archivo = f"Nomina_BancoChile_Lote{nomina_id}_ReDescarga_{datetime.now().strftime('%Y%m%d')}.txt"
                    return Response("\n".join(lineas), mimetype="text/plain", headers={"Content-disposition": f"attachment; filename={nombre_archivo}"})
                    
                except Exception as e:
                    flash(f"Error al re-descargar TXT: {e}", "danger")

            return redirect(url_for('finanzas.banco'))

        # --- CARGAR VISTAS (GET) ---
        cursor.execute("SELECT * FROM banco_proveedores WHERE activo = 1 ORDER BY nombre")
        proveedores = cursor.fetchall()
        
        cursor.execute("""
            SELECT t.*, p.nombre as proveedor_nombre, p.rut as proveedor_rut, p.banco_codigo 
            FROM banco_transferencias t
            JOIN banco_proveedores p ON t.proveedor_id = p.id
            WHERE t.nomina_id IS NULL AND t.estado = 'pendiente'
            ORDER BY t.creado_en DESC
        """)
        carrito = cursor.fetchall()
        
        # --- HISTORIAL DE NÓMINAS ---
        cursor.execute("SELECT * FROM banco_nominas ORDER BY fecha_generacion DESC LIMIT 50")
        nominas = cursor.fetchall()
        
        cursor.execute("""
            SELECT t.*, p.nombre as proveedor_nombre, p.rut as proveedor_rut, p.banco_codigo 
            FROM banco_transferencias t
            JOIN banco_proveedores p ON t.proveedor_id = p.id
            WHERE t.nomina_id IS NOT NULL
            ORDER BY t.creado_en ASC
        """)
        todos_detalles = cursor.fetchall()
        
        historial = []
        for n in nominas:
            n_dict = dict(n)
            n_dict['detalles'] = [d for d in todos_detalles if d['nomina_id'] == n['id']]
            historial.append(n_dict)
        
        return render_template('finanzas/banco.html',
                               bancos=BANCOS_CHILE,
                               proveedores=proveedores,
                               carrito=carrito,
                               historial=historial)

    except Exception as e:
        conn.rollback()
        print(f"Error en módulo banco: {e}")
        flash(f"Error crítico: {e}", "danger")
        return redirect(url_for('finanzas.flujo'))
    finally:
        cursor.close()
        conn.close()

# --- RUTA PARA VISUALIZAR LOS RESPALDOS LOCALES ---
@finanzas_bp.route('/respaldo/<filename>')
@login_requerido
def ver_respaldo(filename):
    return send_from_directory(UPLOAD_FOLDER_PAGOS, filename)

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