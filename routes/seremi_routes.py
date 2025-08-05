# routes/seremi_routes.py
from flask import Blueprint, render_template, request
from utils.sheet_cache import obtener_datos
from services.resumen_service import MESES as NOMBRES_MESES
from datetime import datetime
from collections import defaultdict
import pandas as pd
from utils.sheet_cache import obtener_fecha_actualizacion
from utils.auth import login_requerido
import calendar


seremi_bp = Blueprint("seremi", __name__, url_prefix="/seremi")

@seremi_bp.route("/temperatura_equipos")
@login_requerido
def temperatura_equipos():
    df = obtener_datos("temperatura_equipos")

    # Cargar info de equipos
    df_equipos = obtener_datos("equipos_info")
    df_equipos.columns = df_equipos.columns.str.strip().str.upper()
    mapa_nombre = dict(zip(df_equipos["ID_EQUIPO"], df_equipos["NOMBRE_EQUIPO"]))

    # Normalizar datos de temperatura
    df.columns = df.columns.str.strip().str.upper()
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"])
    df["DIA"] = df["FECHA"].dt.day
    df["MES"] = df["FECHA"].dt.month
    df["AÑO"] = df["FECHA"].dt.year

    # Filtros
    sucursal = request.args.get("sucursal", default="TODAS")
    mes = int(request.args.get("mes", default=datetime.now().month))

    if sucursal != "TODAS":
        df = df[df["SUCURSAL"] == sucursal]

    df = df[df["MES"] == mes]

    # Agrupación por equipo con nombre + código
    equipos = defaultdict(list)
    for cod_equipo, grupo in df.groupby("EQUIPO"):
        nombre_equipo = mapa_nombre.get(cod_equipo, cod_equipo)
        nombre_mostrado = f"{nombre_equipo} ({cod_equipo})"

        grupo = grupo.sort_values("FECHA")

        for dia in range(1, 32):
            registros_dia = grupo[grupo["DIA"] == dia]

            temps = [
                f"{row['TEMPERATURA C°']}°C ({row['FECHA'].strftime('%H:%M')})"
                for _, row in registros_dia.iterrows()
            ]

            while len(temps) < 3:
                temps.append("")

            equipos[nombre_mostrado].append((dia, temps[:3]))

    # Sucursales
    sucursales = sorted(df["SUCURSAL"].dropna().unique().tolist())
    sucursales.insert(0, "TODAS")

    # Meses
    meses = [(i+1, nombre.title()) for i, nombre in enumerate(NOMBRES_MESES)]

    return render_template("seremi/temperatura_equipos.html",
                           equipos=equipos,
                           sucursales=sucursales,
                           sucursal_activa=sucursal,
                           meses=meses,
                           mes_actual=mes,
                           fecha_actualizacion=obtener_fecha_actualizacion("temperatura_equipos"))




# Reemplaza la función completa en seremi_routes.py

@seremi_bp.route("/temperatura_productos")
@login_requerido
def temperatura_productos():
    df = obtener_datos("temperatura_productos")

    # Normalización de datos (incluida la corrección de decimales)
    df.columns = df.columns.str.strip().str.upper()
    if 'TEMPERATURA C°' in df.columns:
        df['TEMPERATURA C°'] = df['TEMPERATURA C°'].astype(str).str.replace(',', '.', regex=False)
        df['TEMPERATURA C°'] = pd.to_numeric(df['TEMPERATURA C°'], errors='coerce')
        df.dropna(subset=['TEMPERATURA C°'], inplace=True)
    
    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d-%m-%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])
    df['DIA'] = df['FECHA'].dt.day
    df['MES'] = df['FECHA'].dt.month
    df['HORA'] = df['FECHA'].dt.hour
    df['RESPONSABLE'] = df['RESPONSABLE'].astype(str)

    # Filtros
    sucursal_activa = request.args.get("sucursal", default="TODAS")
    mes_actual = int(request.args.get("mes", default=datetime.now().month))

    if sucursal_activa != "TODAS":
        df = df[df["SUCURSAL"] == sucursal_activa]
    
    df = df[df["MES"] == mes_actual]

    # --- INICIO DEL CAMBIO EN LA LÓGICA DE AGRUPACIÓN ---
    sucursales_data = {}
    # 1. Agrupamos primero por SUCURSAL
    for sucursal_nombre, grupo_sucursal in df.groupby("SUCURSAL"):
        productos_data = {}
        # 2. Luego, dentro de cada sucursal, agrupamos por PRODUCTO
        for producto_nombre, grupo_producto in grupo_sucursal.groupby("PRODUCTO"):
            registros_mensuales = []
            
            for dia in range(1, 32):
                registros_dia = grupo_producto[grupo_producto['DIA'] == dia]
                
                t_13_row = registros_dia.iloc[(registros_dia['HORA'] - 13).abs().argsort()[:1]]
                t_17_row = registros_dia.iloc[(registros_dia['HORA'] - 17).abs().argsort()[:1]]
                t_21_row = registros_dia.iloc[(registros_dia['HORA'] - 21).abs().argsort()[:1]]
                
                temp_13 = f"{t_13_row['TEMPERATURA C°'].iloc[0]:.2f}°C" if not t_13_row.empty else ""
                temp_17 = f"{t_17_row['TEMPERATURA C°'].iloc[0]:.2f}°C" if not t_17_row.empty else ""
                temp_21 = f"{t_21_row['TEMPERATURA C°'].iloc[0]:.2f}°C" if not t_21_row.empty else ""

                responsables = " / ".join(registros_dia['RESPONSABLE'].unique()) if not registros_dia.empty else ""
                
                registros_mensuales.append({
                    "dia": f"{dia:02d}",
                    "t_13": temp_13,
                    "t_17": temp_17,
                    "t_21": temp_21,
                    "responsables": responsables
                })
            
            productos_data[producto_nombre] = registros_mensuales
        
        sucursales_data[sucursal_nombre] = productos_data
    # --- FIN DEL CAMBIO ---

    # Listas para los filtros
    sucursales_list = sorted(obtener_datos("temperatura_productos")["SUCURSAL"].dropna().unique().tolist())
    sucursales_list.insert(0, "TODAS")
    meses_list = [(i + 1, nombre.title()) for i, nombre in enumerate(NOMBRES_MESES)]

    return render_template("seremi/temperatura_productos.html",
                           sucursales_data=sucursales_data, # Enviamos la nueva estructura de datos
                           sucursales=sucursales_list,
                           sucursal_activa=sucursal_activa,
                           meses=meses_list,
                           mes_actual=mes_actual,
                           fecha_actualizacion=obtener_fecha_actualizacion("temperatura_productos"))


############################



@seremi_bp.route("/cambio_aceite")
@login_requerido
def cambio_aceite():
    return render_template("seremi/cambio_aceite.html")
#############################
@seremi_bp.route("/mantenciones")
@login_requerido
def mantenciones():
    return render_template("seremi/mantenciones.html")

#############################################


@seremi_bp.route("/personal")
@login_requerido
def personal():
    df = obtener_datos("registro_personal")

    # Normalización de datos
    df.columns = df.columns.str.strip().str.upper()
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols[cols == dup].index.values.tolist()] = [f'{dup}.{i}' if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols

    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d-%m-%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])
    df['MES'] = df['FECHA'].dt.month
    df['AÑO'] = df['FECHA'].dt.year # Añadimos año para cálculos precisos

    # Filtros
    sucursal_activa = request.args.get("sucursal", default="TODAS")
    mes_actual = int(request.args.get("mes", default=datetime.now().month))
    # Usamos el año del dato más reciente como referencia, o el año actual
    año_actual = df['AÑO'].max() if not df.empty else datetime.now().year

    df_filtrado_mes = df[df["MES"] == mes_actual]

    if sucursal_activa != "TODAS":
        df_a_procesar = df_filtrado_mes[df_filtrado_mes["SUCURSAL"] == sucursal_activa]
    else:
        df_a_procesar = df_filtrado_mes

    # --- LÓGICA MEJORADA: INCLUIR TODOS LOS DÍAS DEL MES ---
    data_por_sucursal = {}
    for sucursal, grupo_sucursal in df_a_procesar.groupby("SUCURSAL"):
        # Obtenemos los registros existentes y los agrupamos por día
        registros_existentes = {}
        for fecha, grupo_dia in grupo_sucursal.groupby(grupo_sucursal['FECHA'].dt.date):
            grupo_renombrado = grupo_dia.rename(columns={
                "NOMBRE TRABAJADOR": "nombre_manipulador", "PELO LIMPIO": "pelo_limpio",
                "AFEITADO": "afeitado", "¿UÑAS CORTAS?": "unas_cortas",
                "AUSENCIA DE JOYAS": "joyas", "UNIFORME LIMPIO": "uniforme",
                "COFIA BIEN PUESTA": "cofia", "MASCARILLA": "mascarilla",
                "SALUD": "salud", "OBSERVACIONES": "acciones_correctivas"
            })
            registros_existentes[fecha] = grupo_renombrado.to_dict(orient="records")

        # Creamos una estructura para el mes completo
        registros_mes_completo = {}
        num_dias_mes = calendar.monthrange(año_actual, mes_actual)[1]
        for dia in range(1, num_dias_mes + 1):
            fecha_actual = datetime(año_actual, mes_actual, dia).date()
            # Añadimos los registros si existen, si no, una lista vacía
            registros_mes_completo[fecha_actual] = registros_existentes.get(fecha_actual, [])

        if registros_mes_completo:
            data_por_sucursal[sucursal] = registros_mes_completo

    # Listas para los filtros
    sucursales = sorted(obtener_datos("registro_personal")["SUCURSAL"].dropna().unique().tolist())
    sucursales.insert(0, "TODAS")
    meses = [(i + 1, nombre.title()) for i, nombre in enumerate(NOMBRES_MESES)]

    return render_template("seremi/personal.html",
                           data_por_sucursal=data_por_sucursal,
                           sucursales=sucursales,
                           sucursal_activa=sucursal_activa,
                           meses=meses,
                           mes_actual=mes_actual,
                           fecha_actualizacion=obtener_fecha_actualizacion("registro_personal"))

############ IMPRIMIR PDF #################

@seremi_bp.route("/temperatura_equipos/print")
@login_requerido
def imprimir_temperatura_equipos():
    df = obtener_datos("temperatura_equipos")
    df_equipos = obtener_datos("equipos_info")
    df_equipos.columns = df_equipos.columns.str.strip().str.upper()
    mapa_nombre = dict(zip(df_equipos["ID_EQUIPO"], df_equipos["NOMBRE_EQUIPO"]))

    df.columns = df.columns.str.strip().str.upper()
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"])
    df["DIA"] = df["FECHA"].dt.day
    df["MES"] = df["FECHA"].dt.month
    df["AÑO"] = df["FECHA"].dt.year

    sucursal = request.args.get("sucursal", default="TODAS")
    mes = int(request.args.get("mes", default=datetime.now().month))

    if sucursal != "TODAS":
        df = df[df["SUCURSAL"] == sucursal]
    df = df[df["MES"] == mes]

    equipos_data = []
    for cod_equipo, grupo in df.groupby("EQUIPO"):
        nombre_equipo = mapa_nombre.get(cod_equipo, cod_equipo)
        nombre_mostrado = f"{nombre_equipo} ({cod_equipo})"
        registros = []

        for dia in range(1, 32):
            registros_dia = grupo[grupo["DIA"] == dia]

            temps = []
            responsables = []
            for _, row in registros_dia.iterrows():
                temp_hora = f"{row['TEMPERATURA C°']}°C ({row['FECHA'].strftime('%H:%M')})"
                responsable = str(row.get("RESPONSABLE", "")).strip()
                temps.append(temp_hora)
                responsables.append(responsable if responsable else "-")

            # Completar si faltan
            while len(temps) < 3:
                temps.append("")
                responsables.append("-")

            registros.append({
                "dia": f"{dia:02d}",
                "ingreso": temps[0],
                "intermedio": temps[1],
                "salida": temps[2],
                "responsables": " / ".join(responsables[:3])
            })

        equipos_data.append({
            "nombre": nombre_mostrado,
            "sucursal": sucursal,
            "mes": mes,
            "registros": registros
        })

    return render_template("seremi/print_temperatura.html", equipos=equipos_data)


@seremi_bp.route("/temperatura_productos/print")
@login_requerido
def imprimir_temperatura_productos():
    # Esta lógica es una copia exacta de la función principal 'temperatura_productos'
    df = obtener_datos("temperatura_productos")

    # Normalización de datos
    df.columns = df.columns.str.strip().str.upper()
    if 'TEMPERATURA C°' in df.columns:
        df['TEMPERATURA C°'] = df['TEMPERATURA C°'].astype(str).str.replace(',', '.', regex=False)
        df['TEMPERATURA C°'] = pd.to_numeric(df['TEMPERATURA C°'], errors='coerce')
        df.dropna(subset=['TEMPERATURA C°'], inplace=True)
    
    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d-%m-%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])
    df['DIA'] = df['FECHA'].dt.day
    df['MES'] = df['FECHA'].dt.month
    df['HORA'] = df['FECHA'].dt.hour
    df['RESPONSABLE'] = df['RESPONSABLE'].astype(str)

    # Filtros
    sucursal_activa = request.args.get("sucursal", default="TODAS")
    mes_actual = int(request.args.get("mes", default=datetime.now().month))
    nombre_mes = NOMBRES_MESES[mes_actual - 1].title()

    if sucursal_activa != "TODAS":
        df = df[df["SUCURSAL"] == sucursal_activa]
    
    df = df[df["MES"] == mes_actual]

    # Lógica de agrupación anidada
    sucursales_data = {}
    for sucursal_nombre, grupo_sucursal in df.groupby("SUCURSAL"):
        productos_data = {}
        for producto_nombre, grupo_producto in grupo_sucursal.groupby("PRODUCTO"):
            registros_mensuales = []
            
            for dia in range(1, 32):
                registros_dia = grupo_producto[grupo_producto['DIA'] == dia]
                
                t_13_row = registros_dia.iloc[(registros_dia['HORA'] - 13).abs().argsort()[:1]]
                t_17_row = registros_dia.iloc[(registros_dia['HORA'] - 17).abs().argsort()[:1]]
                t_21_row = registros_dia.iloc[(registros_dia['HORA'] - 21).abs().argsort()[:1]]
                
                temp_13 = f"{t_13_row['TEMPERATURA C°'].iloc[0]:.1f}°C" if not t_13_row.empty else ""
                temp_17 = f"{t_17_row['TEMPERATURA C°'].iloc[0]:.1f}°C" if not t_17_row.empty else ""
                temp_21 = f"{t_21_row['TEMPERATURA C°'].iloc[0]:.1f}°C" if not t_21_row.empty else ""

                responsables = " / ".join(registros_dia['RESPONSABLE'].unique()) if not registros_dia.empty else ""
                
                registros_mensuales.append({
                    "dia": f"{dia:02d}",
                    "t_13": temp_13,
                    "t_17": temp_17,
                    "t_21": temp_21,
                    "responsables": responsables
                })
            
            productos_data[producto_nombre] = registros_mensuales
        
        sucursales_data[sucursal_nombre] = productos_data
    
    # Renderizamos la nueva plantilla de impresión
    return render_template("seremi/print_temperatura_productos.html",
                           sucursales_data=sucursales_data,
                           mes=f"{nombre_mes} {datetime.now().year}")



# Reemplaza la función imprimir_personal() completa en seremi_routes.py

@seremi_bp.route("/personal/print")
@login_requerido
def imprimir_personal():
    df = obtener_datos("registro_personal")
    df.columns = df.columns.str.strip().str.upper()
    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d-%m-%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])
    df['MES'] = df['FECHA'].dt.month
    df['AÑO'] = df['FECHA'].dt.year

    sucursal_activa = request.args.get("sucursal", default="TODAS")
    mes_actual = int(request.args.get("mes", default=datetime.now().month))
    nombre_mes = NOMBRES_MESES[mes_actual - 1].title()
    año_actual = df['AÑO'].max() if not df.empty else datetime.now().year

    df_filtrado_mes = df[df["MES"] == mes_actual]
    if sucursal_activa != "TODAS":
        df_a_procesar = df_filtrado_mes[df_filtrado_mes["SUCURSAL"] == sucursal_activa]
    else:
        df_a_procesar = df_filtrado_mes

    # Lógica de Acciones Correctivas
    acciones_map = {
        '¿UÑAS CORTAS?': 'Corregir uñas.', 'AUSENCIA DE JOYAS': 'Retirar joyas.',
        'UNIFORME LIMPIO': 'Corregir uniforme.', 'COFIA BIEN PUESTA': 'Ajustar cofia.',
        'MASCARILLA': 'Corregir mascarilla.', 'AFEITADO': 'Afeitar.'
    }
    registros_procesados = []
    for index, row in df_a_procesar.iterrows():
        acciones = []
        for columna, mensaje in acciones_map.items():
            if 'NO CUMPLE' in str(row.get(columna, '')).upper():
                acciones.append(mensaje)
        observaciones = str(row.get('OBSERVACIONES', ''))
        if observaciones and observaciones.lower() != 'nan':
            acciones.append(observaciones)
        row['ACCIONES_FINALES'] = ' '.join(acciones)
        registros_procesados.append(row)
    df_final = pd.DataFrame(registros_procesados)

    # Lógica de reporte continuo por mes
    data_para_imprimir = {}
    for sucursal, grupo_sucursal in df_final.groupby("SUCURSAL"):
        
        # --- INICIO DE LA CORRECCIÓN ---
        # Agrupamos por DÍA (dt.date) en lugar de por fecha y hora exacta
        # LÍNEA CORREGIDA
        registros_existentes = {fecha: grupo.to_dict(orient="records") 
                                for fecha, grupo in grupo_sucursal.groupby(grupo_sucursal['FECHA'].dt.date)}
        # --- FIN DE LA CORRECCIÓN ---
        
        lista_mes_completo = []
        num_dias_mes = calendar.monthrange(año_actual, mes_actual)[1]

        for dia in range(1, num_dias_mes + 1):
            fecha_actual = datetime(año_actual, mes_actual, dia).date()
            
            if fecha_actual in registros_existentes:
                for registro in registros_existentes[fecha_actual]:
                    registro['FECHA_EVALUACION'] = fecha_actual
                    lista_mes_completo.append(registro)
            else:
                lista_mes_completo.append({'FECHA_EVALUACION': fecha_actual, 'is_empty': True})
        
        data_para_imprimir[sucursal] = lista_mes_completo

    return render_template("seremi/print_personal.html",
                           data_para_imprimir=data_para_imprimir,
                           mes=f"{nombre_mes} {año_actual}")