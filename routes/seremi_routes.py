# routes/seremi_routes.py
from flask import Blueprint, render_template, request, session, redirect, url_for
from utils.sheet_cache import obtener_datos, obtener_fecha_actualizacion
from services.resumen_service import MESES as NOMBRES_MESES
from datetime import datetime
from collections import defaultdict
import pandas as pd
from utils.auth import login_requerido, permiso_modulo
import calendar
from utils.db import get_db_connection # <--- IMPORTANTE: Agregamos esto

seremi_bp = Blueprint("seremi", __name__, url_prefix="/seremi")

# --- YA NO NECESITAS EL DICCIONARIO 'ACCESO_SEREMI' ---
# Lo borramos porque ahora usamos la Base de Datos.

# --- NUEVA FUNCIÓN INTELIGENTE ---
def obtener_filtro_sucursal_seremi():
    """
    1. Mira si el usuario tiene ID de sucursal en su sesión.
    2. Si tiene ID, va a la BD y busca el NOMBRE (ej: 'Costanera').
    3. Si no tiene ID, mira su ROL para ver si le deja ver TODAS.
    Retorna: (nombre_sucursal_para_filtrar, lista_para_el_html)
    """
    usuario = session.get("usuario")
    rol = session.get("rol", "invitado")
    sucursal_id = session.get("sucursal_id") # Este dato viene del Login
    
    nombre_sucursal_permitida = None

    # CASO 1: Usuario restringido por Base de Datos
    if sucursal_id:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # Buscamos el NOMBRE exacto que corresponda a ese ID
                cur.execute("SELECT nombre_sucursal FROM Sucursales WHERE sucursal_id = %s", (sucursal_id,))
                row = cur.fetchone()
                if row:
                    # OJO: Aquí asumimos que el nombre en MySQL es IGUAL al del Excel
                    nombre_sucursal_permitida = row['nombre_sucursal'] if isinstance(row, dict) else row[0]
        except Exception as e:
            print(f"Error buscando nombre sucursal: {e}")
        finally:
            conn.close()

    # CASO 2: Si no tiene restricción (es Jefe o no se asignó nada)
    if not nombre_sucursal_permitida:
        if rol in ['superusuario', 'admin', 'gerencia', 'calidad', 'seremi', 'logistica']:
            nombre_sucursal_permitida = "TODAS"
        else:
            return None, [] # No tiene acceso a nada

    # LÓGICA FINAL DE RETORNO
    solicitada = request.args.get("sucursal", "TODAS")

    if nombre_sucursal_permitida == "TODAS":
        # Es jefe: Puede ver lo que quiera o filtrar si lo pide en la URL
        return solicitada, "TODAS"
    else:
        # Es sucursal: IGNORAMOS lo que pida en la URL y forzamos su nombre
        return nombre_sucursal_permitida, [nombre_sucursal_permitida]




# --- RUTA 1: TEMPERATURA EQUIPOS (MODIFICADA) ---
@seremi_bp.route("/temperatura_equipos")
@login_requerido
@permiso_modulo("seremi")
def temperatura_equipos():
    # 1. SEGURIDAD: Determinar qué puede ver
    sucursal_activa, permisos_visuales = obtener_filtro_sucursal_seremi()
    
    if sucursal_activa is None:
        return render_template("403.html"), 403 # O un mensaje de error

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

    # Filtros de Mes
    mes = int(request.args.get("mes", default=datetime.now().month))

    # 2. APLICAR FILTRO DE SUCURSAL
    if sucursal_activa != "TODAS":
        # Aquí es donde "Esc. Militar" debe coincidir EXACTO
        df = df[df["SUCURSAL"] == sucursal_activa]

    df = df[df["MES"] == mes]

    # Agrupación por equipo
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

    # 3. PREPARAR LISTA PARA EL SELECTOR HTML
    if permisos_visuales == "TODAS":
        # Si es jefe, cargamos todas las opciones disponibles en el Excel
        sucursales = sorted(obtener_datos("temperatura_equipos")["SUCURSAL"].dropna().unique().tolist())
        sucursales.insert(0, "TODAS")
    else:
        # Si es sucursal, la lista solo tiene su propia sucursal
        sucursales = permisos_visuales

    meses = [(i+1, nombre.title()) for i, nombre in enumerate(NOMBRES_MESES)]

    return render_template("seremi/temperatura_equipos.html",
                           equipos=equipos,
                           sucursales=sucursales,     # Lista filtrada
                           sucursal_activa=sucursal_activa, # Selección forzada o elegida
                           meses=meses,
                           mes_actual=mes,
                           fecha_actualizacion=obtener_fecha_actualizacion("temperatura_equipos"))




# Reemplaza la función completa en seremi_routes.py

@seremi_bp.route("/temperatura_productos")
@login_requerido
@permiso_modulo("seremi")
def temperatura_productos():
    sucursal_activa, permisos_visuales = obtener_filtro_sucursal_seremi()
    if sucursal_activa is None: return render_template("403.html"), 403

    df = obtener_datos("temperatura_productos")
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

    mes_actual = int(request.args.get("mes", default=datetime.now().month))

    if sucursal_activa != "TODAS":
        df = df[df["SUCURSAL"] == sucursal_activa]
    
    df = df[df["MES"] == mes_actual]

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
                
                temp_13 = f"{t_13_row['TEMPERATURA C°'].iloc[0]:.2f}°C" if not t_13_row.empty else ""
                temp_17 = f"{t_17_row['TEMPERATURA C°'].iloc[0]:.2f}°C" if not t_17_row.empty else ""
                temp_21 = f"{t_21_row['TEMPERATURA C°'].iloc[0]:.2f}°C" if not t_21_row.empty else ""
                responsables = " / ".join(registros_dia['RESPONSABLE'].unique()) if not registros_dia.empty else ""
                
                registros_mensuales.append({"dia": f"{dia:02d}", "t_13": temp_13, "t_17": temp_17, "t_21": temp_21, "responsables": responsables})
            productos_data[producto_nombre] = registros_mensuales
        sucursales_data[sucursal_nombre] = productos_data

    if permisos_visuales == "TODAS":
        sucursales_list = sorted(obtener_datos("temperatura_productos")["SUCURSAL"].dropna().unique().tolist())
        sucursales_list.insert(0, "TODAS")
    else:
        sucursales_list = permisos_visuales

    meses_list = [(i + 1, nombre.title()) for i, nombre in enumerate(NOMBRES_MESES)]

    return render_template("seremi/temperatura_productos.html", sucursales_data=sucursales_data, sucursales=sucursales_list, sucursal_activa=sucursal_activa, meses=meses_list, mes_actual=mes_actual, fecha_actualizacion=obtener_fecha_actualizacion("temperatura_productos"))


############################



@seremi_bp.route("/cambio_aceite")
@login_requerido
@permiso_modulo("seremi")
def cambio_aceite():
    sucursal_activa, permisos_visuales = obtener_filtro_sucursal_seremi()
    if sucursal_activa is None: return render_template("403.html"), 403

    df = obtener_datos("cambio_aceite")
    df.columns = df.columns.str.strip().str.upper()
    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d-%m-%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])

    if sucursal_activa != "TODAS":
        df_a_procesar = df[df["SUCURSAL"] == sucursal_activa]
    else:
        df_a_procesar = df

    data_por_sucursal = {}
    if not df_a_procesar.empty:
        for sucursal, grupo in df_a_procesar.groupby("SUCURSAL"):
            grupo_ordenado = grupo.sort_values(by="FECHA", ascending=False).head(20)
            data_por_sucursal[sucursal] = grupo_ordenado.to_dict(orient="records")

    if permisos_visuales == "TODAS":
        sucursales = sorted(obtener_datos("cambio_aceite")["SUCURSAL"].dropna().unique().tolist())
        sucursales.insert(0, "TODAS")
    else:
        sucursales = permisos_visuales

    return render_template("seremi/cambio_aceite.html", data_por_sucursal=data_por_sucursal, sucursales=sucursales, sucursal_activa=sucursal_activa, fecha_actualizacion=obtener_fecha_actualizacion("cambio_aceite"))


#############################
# Reemplaza la función recepcion_mercaderia() existente en seremi_routes.py

@seremi_bp.route("/recepcion_mercaderia")
@login_requerido
@permiso_modulo("seremi")
def recepcion_mercaderia():
    sucursal_activa, permisos_visuales = obtener_filtro_sucursal_seremi()
    if sucursal_activa is None: return render_template("403.html"), 403

    df = obtener_datos("recepcion_mercaderia")
    df.columns = df.columns.str.strip().str.upper()
    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])
    df['MES'] = df['FECHA'].dt.month

    mes_actual = int(request.args.get("mes", default=datetime.now().month))
    df_filtrado_mes = df[df["MES"] == mes_actual]

    if sucursal_activa != "TODAS":
        df_a_procesar = df_filtrado_mes[df_filtrado_mes["SUCURSAL"] == sucursal_activa]
    else:
        df_a_procesar = df_filtrado_mes

    data_final = {}
    if not df_a_procesar.empty:
        for sucursal, grupo_sucursal in df_a_procesar.groupby("SUCURSAL"):
            productos_data = {}
            for producto, grupo_producto in grupo_sucursal.groupby("PRODUCTO"):
                grupo_ordenado = grupo_producto.sort_values(by="FECHA", ascending=False)
                productos_data[producto] = grupo_ordenado.to_dict(orient="records")
            data_final[sucursal] = productos_data

    if permisos_visuales == "TODAS":
        sucursales = sorted(obtener_datos("recepcion_mercaderia")["SUCURSAL"].dropna().unique().tolist())
        sucursales.insert(0, "TODAS")
    else:
        sucursales = permisos_visuales

    meses = [(i + 1, nombre.title()) for i, nombre in enumerate(NOMBRES_MESES)]

    return render_template("seremi/recepcion_mercaderia.html", data_final=data_final, sucursales=sucursales, sucursal_activa=sucursal_activa, meses=meses, mes_actual=mes_actual, fecha_actualizacion=obtener_fecha_actualizacion("recepcion_mercaderia"))
#############################################


@seremi_bp.route("/personal")
@login_requerido
@permiso_modulo("seremi")
def personal():
    sucursal_activa, permisos_visuales = obtener_filtro_sucursal_seremi()
    if sucursal_activa is None: return render_template("403.html"), 403

    df = obtener_datos("registro_personal")
    df.columns = df.columns.str.strip().str.upper()
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols[cols == dup].index.values.tolist()] = [f'{dup}.{i}' if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols

    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d-%m-%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])
    df['MES'] = df['FECHA'].dt.month
    df['AÑO'] = df['FECHA'].dt.year

    mes_actual = int(request.args.get("mes", default=datetime.now().month))
    año_actual = df['AÑO'].max() if not df.empty else datetime.now().year
    df_filtrado_mes = df[df["MES"] == mes_actual]

    if sucursal_activa != "TODAS":
        df_a_procesar = df_filtrado_mes[df_filtrado_mes["SUCURSAL"] == sucursal_activa]
    else:
        df_a_procesar = df_filtrado_mes

    data_por_sucursal = {}
    for sucursal, grupo_sucursal in df_a_procesar.groupby("SUCURSAL"):
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

        registros_mes_completo = {}
        num_dias_mes = calendar.monthrange(año_actual, mes_actual)[1]
        for dia in range(1, num_dias_mes + 1):
            fecha_actual = datetime(año_actual, mes_actual, dia).date()
            registros_mes_completo[fecha_actual] = registros_existentes.get(fecha_actual, [])

        if registros_mes_completo:
            data_por_sucursal[sucursal] = registros_mes_completo

    if permisos_visuales == "TODAS":
        sucursales = sorted(obtener_datos("registro_personal")["SUCURSAL"].dropna().unique().tolist())
        sucursales.insert(0, "TODAS")
    else:
        sucursales = permisos_visuales
    
    meses = [(i + 1, nombre.title()) for i, nombre in enumerate(NOMBRES_MESES)]

    return render_template("seremi/personal.html", data_por_sucursal=data_por_sucursal, sucursales=sucursales, sucursal_activa=sucursal_activa, meses=meses, mes_actual=mes_actual, fecha_actualizacion=obtener_fecha_actualizacion("registro_personal"))

############ IMPRIMIR PDF #################

@seremi_bp.route("/temperatura_equipos/print")
@login_requerido
@permiso_modulo("seremi")
def imprimir_temperatura_equipos():
    # 1. SEGURIDAD
    sucursal_activa, _ = obtener_filtro_sucursal_seremi()
    if sucursal_activa is None: return "Acceso Denegado", 403

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

    mes = int(request.args.get("mes", default=datetime.now().month))

    # 2. FILTRADO OBLIGATORIO
    if sucursal_activa != "TODAS":
        df = df[df["SUCURSAL"] == sucursal_activa]
        
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
                temps.append(f"{row['TEMPERATURA C°']}°C ({row['FECHA'].strftime('%H:%M')})")
                responsable = str(row.get("RESPONSABLE", "")).strip()
                responsables.append(responsable if responsable else "-")

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
            "sucursal": sucursal_activa if sucursal_activa != "TODAS" else "Varias", # Ajuste visual
            "mes": mes,
            "registros": registros
        })

    return render_template("seremi/print_temperatura.html", equipos=equipos_data)


@seremi_bp.route("/temperatura_productos/print")
@login_requerido
@permiso_modulo("seremi")
def imprimir_temperatura_productos():
    # 1. SEGURIDAD
    sucursal_activa, _ = obtener_filtro_sucursal_seremi()
    if sucursal_activa is None: return "Acceso Denegado", 403

    df = obtener_datos("temperatura_productos")

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

    mes_actual = int(request.args.get("mes", default=datetime.now().month))
    nombre_mes = NOMBRES_MESES[mes_actual - 1].title()

    # 2. FILTRADO OBLIGATORIO
    if sucursal_activa != "TODAS":
        df = df[df["SUCURSAL"] == sucursal_activa]
    
    df = df[df["MES"] == mes_actual]

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
                    "dia": f"{dia:02d}", "t_13": temp_13, "t_17": temp_17, "t_21": temp_21, "responsables": responsables
                })
            productos_data[producto_nombre] = registros_mensuales
        sucursales_data[sucursal_nombre] = productos_data
    
    return render_template("seremi/print_temperatura_productos.html", sucursales_data=sucursales_data, mes=f"{nombre_mes} {datetime.now().year}")



#la función imprimir_personal() completa en seremi_routes.py

@seremi_bp.route("/personal/print")
@login_requerido
@permiso_modulo("seremi")
def imprimir_personal():
    # 1. SEGURIDAD
    sucursal_activa, _ = obtener_filtro_sucursal_seremi()
    if sucursal_activa is None: return "Acceso Denegado", 403

    df = obtener_datos("registro_personal")
    df.columns = df.columns.str.strip().str.upper()
    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d-%m-%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])
    df['MES'] = df['FECHA'].dt.month
    df['AÑO'] = df['FECHA'].dt.year

    mes_actual = int(request.args.get("mes", default=datetime.now().month))
    nombre_mes = NOMBRES_MESES[mes_actual - 1].title()
    año_actual = df['AÑO'].max() if not df.empty else datetime.now().year

    df_filtrado_mes = df[df["MES"] == mes_actual]
    
    # 2. FILTRADO OBLIGATORIO
    if sucursal_activa != "TODAS":
        df_a_procesar = df_filtrado_mes[df_filtrado_mes["SUCURSAL"] == sucursal_activa]
    else:
        df_a_procesar = df_filtrado_mes

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

    data_para_imprimir = {}
    if not df_final.empty:
        for sucursal, grupo_sucursal in df_final.groupby("SUCURSAL"):
            registros_existentes = {fecha: grupo.to_dict(orient="records") 
                                    for fecha, grupo in grupo_sucursal.groupby(grupo_sucursal['FECHA'].dt.date)}
            
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

    return render_template("seremi/print_personal.html", data_para_imprimir=data_para_imprimir, mes=f"{nombre_mes} {año_actual}")

@seremi_bp.route("/cambio_aceite/print")
@login_requerido
@permiso_modulo("seremi")
def imprimir_cambio_aceite():
    # 1. SEGURIDAD
    sucursal_activa, _ = obtener_filtro_sucursal_seremi()
    if sucursal_activa is None: return "Acceso Denegado", 403

    df = obtener_datos("cambio_aceite")
    df.columns = df.columns.str.strip().str.upper()
    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d-%m-%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])

    # 2. FILTRADO OBLIGATORIO
    if sucursal_activa != "TODAS":
        df_a_procesar = df[df["SUCURSAL"] == sucursal_activa]
    else:
        df_a_procesar = df

    data_por_sucursal = {}
    if not df_a_procesar.empty:
        for sucursal, grupo in df_a_procesar.groupby("SUCURSAL"):
            grupo_ordenado = grupo.sort_values(by="FECHA", ascending=False).head(20)
            data_por_sucursal[sucursal] = grupo_ordenado.to_dict(orient="records")

    return render_template("seremi/print_cambio_aceite.html", data_por_sucursal=data_por_sucursal)

# Pega esta nueva función al final de seremi_routes.py

@seremi_bp.route("/recepcion_mercaderia/print")
@login_requerido
@permiso_modulo("seremi")
def imprimir_recepcion_mercaderia():
    # 1. SEGURIDAD
    sucursal_activa, _ = obtener_filtro_sucursal_seremi()
    if sucursal_activa is None: return "Acceso Denegado", 403

    df = obtener_datos("recepcion_mercaderia")
    df.columns = df.columns.str.strip().str.upper()
    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['FECHA'])
    df['MES'] = df['FECHA'].dt.month

    mes_actual = int(request.args.get("mes", default=datetime.now().month))
    df_filtrado_mes = df[df["MES"] == mes_actual]

    # 2. FILTRADO OBLIGATORIO
    if sucursal_activa != "TODAS":
        df_a_procesar = df_filtrado_mes[df_filtrado_mes["SUCURSAL"] == sucursal_activa]
    else:
        df_a_procesar = df_filtrado_mes

    data_final = {}
    if not df_a_procesar.empty:
        for sucursal, grupo_sucursal in df_a_procesar.groupby("SUCURSAL"):
            productos_data = {}
            for producto, grupo_producto in grupo_sucursal.groupby("PRODUCTO"):
                grupo_ordenado = grupo_producto.sort_values(by="FECHA", ascending=False)
                productos_data[producto] = grupo_ordenado.to_dict(orient="records")
            data_final[sucursal] = productos_data

    nombre_mes = NOMBRES_MESES[mes_actual - 1].title()
    año = df['FECHA'].dt.year.max() if not df.empty else datetime.now().year

    return render_template("seremi/print_recepcion_mercaderia.html",
                           data_final=data_final,
                           mes=f"{nombre_mes} {año}",
                           sucursal_activa=sucursal_activa)
