# Asegúrate de tener estos imports al principio del archivo sheet_cache.py
import unicodedata
import pandas as pd
from datetime import datetime
import pytz
import io
import os # Necesario para construir la ruta al archivo de credenciales
from utils.db import get_db_connection

# Imports para la API de Google
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

_ultima_actualizacion = {}
_cache = {}
# ... (Aquí va tu diccionario de URLS, sin cambios)
URLS = {
    "temperatura_equipos": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?output=csv",
    "equipos_info": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?gid=946296021&single=true&output=csv",
    "mayor": "1zFjARS82JAuay19WxxgepBl7jYylgPIn",
    "temperatura_productos": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?gid=513903553&single=true&output=csv",
    "registro_personal":"https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?gid=279098862&single=true&output=csv",
    "cambio_aceite" :"https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?gid=999262441&single=true&output=csv",
    "recepcion_mercaderia":"https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?gid=1201172647&single=true&output=csv"
}

#URLS = {
#   "comercial": "https://raw.githubusercontent.com/CarlitosHuente/carlitoshuente/refs/heads/main/data2/Ventas_Comercial_24-25%20-%20Hoja%201.csv",
#  "agricola": "https://raw.githubusercontent.com/CarlitosHuente/carlitoshuente/refs/heads/main/data2/Ventas_Agricola_24-25%20-%20Hoja%201.csv",
# "temperatura_equipos": "https://raw.githubusercontent.com/CarlitosHuente/carlitoshuente/refs/heads/main/data2/Huentelauquen_Locales%20-%20Temperatura_Productos.csv",
#"equipos_info": "https://raw.githubusercontent.com/CarlitosHuente/carlitoshuente/refs/heads/main/data2/Huentelauquen_Locales%20-%20Equipos.csv",
#    "mayor": "1zFjARS82JAuay19WxxgepBl7jYylgPIn",
#    "temperatura_productos": "https://raw.githubusercontent.com/CarlitosHuente/carlitoshuente/refs/heads/main/data2/Huentelauquen_Locales%20-%20Temperatura_Productos.csv",
#    "registro_personal":"https://raw.githubusercontent.com/CarlitosHuente/carlitoshuente/refs/heads/main/data2/Huentelauquen_Locales%20-%20Registro_Personal.csv",
#    "cambio_aceite" :"https://raw.githubusercontent.com/CarlitosHuente/carlitoshuente/refs/heads/main/data2/Huentelauquen_Locales%20-%20Cambio_Aceite.csv",
#    "recepcion_mercaderia":"https://raw.githubusercontent.com/CarlitosHuente/carlitoshuente/refs/heads/main/data2/Huentelauquen_Locales%20-%20Recepcion_Mercaderia.csv"
#}


# --- Comercial: misma lógica NETO que el Dashboard (reutilizable + export diagnóstico) ---

SQL_VENTAS_COMERCIAL_LINEAS = """
    SELECT fecha, des_articu, rubro, n_comp, sub_rengl, cantidad,
           precio, precio_lis, sucursal
    FROM ventas_comercial
    WHERE UPPER(TRIM(estado)) IN ('COBRADO', 'COBRADA', 'DESPACH./COBRADA')
      AND fecha IS NOT NULL
"""

# Solo presentación en memoria (dashboard, costeo, export): BD sigue guardando texto orig. por canal.
# Unifica POS (docena/media docena empanada cruda), Página Web y cualquier variante «empanada + queso + cruda».
PRESENTACION_EMPANADAS_CRUDAS_UNIFICADA = "EMPANADA DE QUESO CRUDA"

# Familia/RUBRO solo en memoria (misma capa que dashboard/costeo).
FAMILIA_PRESENTACION_OTROS = "Otros"
FAMILIA_PRESENTACION_QUESOS = "Quesos"
FAMILIA_PRESENTACION_EMPANADAS = "Empanadas"
FAMILIA_PRESENTACION_PAPAYAS = "Papayas"
FAMILIA_PRESENTACION_BEBIDAS = "Bebidas"
FAMILIA_PRESENTACION_PIZZAS = "Pizzas"
FAMILIA_PRESENTACION_HELADOS = "Helados"


def _mask_presentacion_empanada_queso_cruda(df):
    """
    Mismo producto vendido en Web (suelen venir por unidad) y en sucursales (a veces mín. 6 / docena en POS).
    No altera precios: solo identifica filas cuya DESCRIPCION se reemplaza por PRESENTACION_*.
    En Web no hay empanada frita; el filtro ``~frita`` evita mezclar en POS líneas «… QUESO FRITA» con las crudas.
    """
    if "DESCRIPCION" not in df.columns:
        return pd.Series(False, index=df.index)
    d = df["DESCRIPCION"].astype(str).map(_fold_sin_tilde)
    mask_docenas_pos = d.str.contains("DOCENA EMPANADA CRUDA", na=False)
    emp = d.str.contains("EMPANADA", na=False)
    queso = d.str.contains("QUESO", na=False)
    cruda = d.str.contains("CRUDA", na=False) | d.str.contains("CRUDAS", na=False)
    # Web no cataloga frita; en sucursales sí puede existir «EMPANADA DE QUESO FRITA».
    frita = d.str.contains("FRITA", na=False)
    mask_nombre_web = emp & queso & cruda & ~frita
    return mask_docenas_pos | mask_nombre_web


def _aplicar_familia_presentacion_comercial(df, mask_empanada_queso_cruda):
    """
    Normaliza rubros para tableros sin tocar MySQL: quita prefijos raros del POS (p. ej. ``\\Empanadas``);
    Malla/Otros → Otros; Queso/Quesos → Quesos; EMPANADAS/Empanadas → Empanadas; Papaya/Papayas → Papayas;
    Bebida(s), Pizza(s), Helado(s) → nombres únicos; líneas empanada queso cruda (máscara) → Empanadas al final.
    """
    if "FAMILIA" not in df.columns or df.empty:
        return df
    df["FAMILIA"] = (
        df["FAMILIA"]
        .astype(str)
        .str.strip()
        .str.replace(r"^[\\/]+", "", regex=True)
        .str.strip()
    )
    fam0 = df["FAMILIA"].map(_fold_sin_tilde)
    mask_otros = fam0.isin(["MALLA", "MALLAS", "OTROS", "OTRO"])
    mask_queso_fam = fam0.isin(["QUESO", "QUESOS"])
    df.loc[mask_otros, "FAMILIA"] = FAMILIA_PRESENTACION_OTROS
    df.loc[mask_queso_fam, "FAMILIA"] = FAMILIA_PRESENTACION_QUESOS

    fam0 = df["FAMILIA"].map(_fold_sin_tilde)
    df.loc[fam0.isin(["EMPANADAS", "EMPANADA"]), "FAMILIA"] = FAMILIA_PRESENTACION_EMPANADAS
    df.loc[fam0.isin(["PAPAYA", "PAPAYAS"]), "FAMILIA"] = FAMILIA_PRESENTACION_PAPAYAS
    df.loc[fam0.isin(["BEBIDAS", "BEBIDA"]), "FAMILIA"] = FAMILIA_PRESENTACION_BEBIDAS
    df.loc[fam0.isin(["PIZZA", "PIZZAS"]), "FAMILIA"] = FAMILIA_PRESENTACION_PIZZAS
    df.loc[fam0.isin(["HELADO", "HELADOS"]), "FAMILIA"] = FAMILIA_PRESENTACION_HELADOS

    desc_fold_f = df["DESCRIPCION"].astype(str).map(_fold_sin_tilde)
    mask_emp_queso_frita = (
        desc_fold_f.str.contains("EMPANADA", na=False)
        & desc_fold_f.str.contains("QUESO", na=False)
        & desc_fold_f.str.contains("FRITA", na=False)
    )
    df.loc[mask_emp_queso_frita, "FAMILIA"] = FAMILIA_PRESENTACION_EMPANADAS

    if mask_empanada_queso_cruda.any():
        df.loc[mask_empanada_queso_cruda, "FAMILIA"] = FAMILIA_PRESENTACION_EMPANADAS
    return df


def _fold_sin_tilde(texto):
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    s = unicodedata.normalize("NFD", str(texto).strip().upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _mask_articulo_despacho_web_sin_iva(df):
    """DESPACHO WEB: articulo sin IVA — en BD viene sin factor 1,19; NETO = bruto de linea tal cual."""
    if "DESCRIPCION" not in df.columns:
        return pd.Series(False, index=df.index)
    d = df["DESCRIPCION"].astype(str).map(_fold_sin_tilde)
    return d.str.contains("DESPACHO WEB", na=False)


def procesar_neto_comercial_mismo_que_dashboard(df, diagnostico=False):
    """
    df: columnas MAYÚSCULAS con DESCRIPCION (ex DES_ARTICU), FAMILIA/RUBRO, SUCURSAL,
    CANTIDAD, PRECIO, PRECIO_LIS, SUB_RENGL.
    - Excluye familia Promoción (evita doble conteo respecto líneas ya valorizadas).
    - Bruto línea (con IVA en BD para el resto): en general **CANTIDAD × PRECIO_LIS** (mismo criterio que
      export Web: evita errores en boletas con varios artículos al no depender de SUB_RENGL ni de PRECIO
      cuando el POS repite subtotales).
    - **Excepción:** MEDIA / DOCENA **EMPANADA CRUDA** (descripción contiene «DOCENA EMPANADA CRUDA»):
      **CANTIDAD × PRECIO** facturado. Si **PRECIO** viene 0 → se usa lista.
      En dashboard/export todas esas líneas muestran DESCRIPCION ``EMPANADA DE QUESO CRUDA`` (Web, docenas en
      POS, etc.; la cantidad sigue como en BD); ``ventas_comercial`` no se modifica (ver ``PRESENTACION_*``).
    - **FAMILIA** (presentación): limpia prefijos ``\\`` del POS; Malla/Otros → ``Otros``; Queso/Quesos →
      ``Quesos``; EMPANADAS/Empanadas → ``Empanadas``; Papaya/Papayas, Bebida(s), Pizza(s), Helado(s) →
      nombre único; descripción con empanada+queso+frita → ``Empanadas``; empanada queso cruda (máscara) →
      ``Empanadas``. BD intacta.
    - **QUESO PIEZA (KG):** **PRECIO_LIS × CANTIDAD** (equivale al caso general); si **PRECIO_LIS** es 0
      → **PRECIO**.
    - Solo DESPACHO WEB: sin IVA en BD → NETO = bruto línea sin /1,19.

    Si diagnostico=True, columnas _d_* para Excel de auditoría.
    """
    df = df.copy()
    if "FAMILIA" in df.columns:
        fam_fold = df["FAMILIA"].map(_fold_sin_tilde)
        es_promocion = fam_fold.str.contains("PROMOCION", na=False)
        df = df.loc[~es_promocion].copy()
    if df.empty:
        return df

    cant = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
    precio_u = pd.to_numeric(df.get("PRECIO"), errors="coerce").fillna(0)
    precio_lis_u = pd.to_numeric(df.get("PRECIO_LIS"), errors="coerce").fillna(0)
    sub = pd.to_numeric(df.get("SUB_RENGL"), errors="coerce").fillna(0)
    desc_u = df["DESCRIPCION"].astype(str).str.upper()
    desc_fold = df["DESCRIPCION"].astype(str).map(_fold_sin_tilde)

    px_l = precio_lis_u.astype(float)
    px_u = precio_u.astype(float)

    mask_queso_pieza_kg = desc_u.str.contains(
        "QUESO PIEZA", na=False
    ) & desc_u.str.contains("(KG)", na=False)
    # Cubre «MEDIA DOCENA EMPANADA CRUDA» y «DOCENA EMPANADA CRUDA».
    mask_emp_cruda_precio_fact = desc_fold.str.contains(
        "DOCENA EMPANADA CRUDA", na=False
    )

    precio_efec = px_l.copy()
    sin_lista_queso = mask_queso_pieza_kg & (precio_lis_u == 0)
    precio_efec.loc[sin_lista_queso] = px_u.loc[sin_lista_queso]

    precio_efec.loc[mask_emp_cruda_precio_fact] = px_u.loc[mask_emp_cruda_precio_fact]
    sin_precio_emp = mask_emp_cruda_precio_fact & (precio_u == 0)
    precio_efec.loc[sin_precio_emp] = px_l.loc[sin_precio_emp]

    bruto_ref_lista = cant * px_l
    bruto_linea = cant * precio_efec

    mask_despacho_sin_iva = _mask_articulo_despacho_web_sin_iva(df)
    df["NETO"] = bruto_linea / 1.19
    df.loc[mask_despacho_sin_iva, "NETO"] = bruto_linea.loc[mask_despacho_sin_iva]
    df["CANTIDAD"] = cant

    if diagnostico:
        sub_safe = sub.mask(sub == 0, pd.NA)
        ratio = bruto_linea / sub_safe
        df["_d_bruto_cant_x_precio"] = bruto_ref_lista
        df["_d_bruto_final_iva"] = bruto_linea
        df["_d_flag_queso_pieza_kg"] = mask_queso_pieza_kg.astype(int)
        df["_d_flag_empanada_cruda_precio_fact"] = mask_emp_cruda_precio_fact.astype(
            int
        )
        df["_d_ratio_bruto_vs_sub_rengl"] = ratio
        df["_d_sin_iva_despacho_web"] = mask_despacho_sin_iva.astype(int)
        ref_sub_div = sub / 1.19
        ref_sub_div.loc[mask_despacho_sin_iva] = sub.loc[mask_despacho_sin_iva]
        df["_d_neto_solo_sub_rengl_div_119"] = ref_sub_div

    mask_presentacion_eqc = _mask_presentacion_empanada_queso_cruda(df)
    if mask_presentacion_eqc.any():
        if diagnostico:
            df["_d_descripcion_articulo_bd"] = pd.NA
            df.loc[mask_presentacion_eqc, "_d_descripcion_articulo_bd"] = (
                df.loc[mask_presentacion_eqc, "DESCRIPCION"]
                .astype(str)
                .str.strip()
            )
        df.loc[mask_presentacion_eqc, "DESCRIPCION"] = (
            PRESENTACION_EMPANADAS_CRUDAS_UNIFICADA
        )
    _aplicar_familia_presentacion_comercial(df, mask_presentacion_eqc)
    return df


def obtener_dataframe_comercial_export_diagnostico():
    """
    Todas las líneas comerciales (mismos filtros SQL que el cache) con columnas de diagnóstico para Excel.
    No usa caché en memoria; lectura directa a BD.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(SQL_VENTAS_COMERCIAL_LINEAS)
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.columns = df.columns.str.strip().str.upper()
    df.rename(
        columns={"DES_ARTICU": "DESCRIPCION", "RUBRO": "FAMILIA", "N_COMP": "N_BOLETA"},
        inplace=True,
    )
    if "FAMILIA" not in df.columns:
        df["FAMILIA"] = "SIN FAMILIA"
    df = procesar_neto_comercial_mismo_que_dashboard(df, diagnostico=True)
    if df.empty:
        return df
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA", "DESCRIPCION"])
    df["SEMANA"] = df["FECHA"].dt.isocalendar().week
    df["AÑO"] = df["FECHA"].dt.year
    return df


# --- REEMPLAZA TU FUNCIÓN obtener_datos CON ESTA ---

# Reemplaza la función completa en utils/sheet_cache.py

def obtener_datos(empresa="comercial", raise_errors=False):
    if empresa not in _cache:
        url_o_id = URLS.get(empresa)

        # "agricola" y "comercial" leen desde MySQL (tablas separadas)
        if not url_o_id and empresa not in ("agricola", "comercial"):
            if raise_errors:
                raise Exception(f"No se ha definido la URL o ID para '{empresa}'")
            return pd.DataFrame()

        elif empresa == "mayor":
            try:
                SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
                BASE_DIR = os.path.dirname(os.path.abspath(__file__))
                ROOT_DIR = os.path.dirname(BASE_DIR)
                SERVICE_ACCOUNT_FILE = os.path.join(ROOT_DIR, 'credenciales_google.json')

                creds = service_account.Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_FILE, scopes=SCOPES)

                drive_service = build('drive', 'v3', credentials=creds)
                folder_id = url_o_id
                file_name = 'mayor.xlsx'

                query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
                results = drive_service.files().list(q=query, fields="files(id, name)").execute()
                items = results.get('files', [])

                if not items:
                    raise Exception(f"No se encontró el archivo '{file_name}' en la carpeta de Drive.")

                file_id = items[0]['id']
                request = drive_service.files().get_media(fileId=file_id)
                file_content = io.BytesIO()
                downloader = MediaIoBaseDownload(file_content, request)
                
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                
                file_content.seek(0)
                df = pd.read_excel(file_content, engine="openpyxl")
                df.columns = df.columns.str.strip().str.upper()
                df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
                df = df.dropna(subset=["FECHA", "NOMBRE", "DEBE", "HABER"])
                df["AÑO"] = df["FECHA"].dt.year
                df["MES"] = df["FECHA"].dt.month
            
            except Exception as e:
                print(f"ERROR al cargar 'mayor.xlsx' desde la API de Drive: {e}")
            if raise_errors:
                raise e
                return pd.DataFrame()

        elif empresa == "agricola":
            try:
                # --- LEER DESDE LA BASE DE DATOS LOCAL ---
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Optimizamos la consulta para traer SOLO las columnas necesarias
                # y filtrar directo en MySQL, reduciendo drásticamente el uso de RAM y tiempo.
                query = """
                    SELECT fecha, des_articu, rubro, n_comp, sub_rengl, des_client, cantidad
                    FROM ventas_agricola
                    WHERE UPPER(TRIM(estado)) IN ('COBRADO', 'COBRADA', 'DESPACH./COBRADA')
                      AND fecha IS NOT NULL
                """
                cursor.execute(query)
                rows = cursor.fetchall()
                conn.close()
                
                cols_base = ["FECHA", "DESCRIPCION", "NETO", "CANTIDAD", "SUCURSAL", "FAMILIA", "AÑO", "SEMANA"]
                if not rows:
                    return pd.DataFrame(columns=cols_base)
                    
                df = pd.DataFrame(rows)
                df.columns = df.columns.str.strip().str.upper()

                # 1. Renombrar para el Dashboard estándar (El filtro de estado ya se hizo en SQL)
                df.rename(columns={
                    "DES_ARTICU": "DESCRIPCION",
                    "RUBRO": "FAMILIA",
                    "N_COMP": "N_BOLETA"
                }, inplace=True)
                
                # Usamos 'SUB_RENGL' de la base de datos y lo dividimos por 1.19 para obtener el Neto real por línea.
                df["NETO"] = pd.to_numeric(df["SUB_RENGL"], errors='coerce').fillna(0) / 1.19

                # 3. Clasificar Sucursal usando DES_CLIENT
                def clasificar_cliente(cliente):
                    if pd.isna(cliente):
                        return "FACTURA"
                    cliente_str = str(cliente).upper()
                    if "OCASIONAL" in cliente_str:
                        return "BOLETAS"
                    elif "TRABAJADOR" in cliente_str:
                        return "TRABAJADOR"
                    else:
                        return "FACTURA"

                if "DES_CLIENT" in df.columns:
                    df["SUCURSAL"] = df["DES_CLIENT"].apply(clasificar_cliente)
                else:
                    df["SUCURSAL"] = "FACTURA"

                columnas_requeridas = ["FECHA", "DESCRIPCION", "NETO", "CANTIDAD"]
                df = df.dropna(subset=columnas_requeridas)
                df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
                df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
                df["SEMANA"] = df["FECHA"].dt.isocalendar().week
                df["AÑO"] = df["FECHA"].dt.year

            except Exception as e:
                print(f"❌ Error crítico procesando '{empresa}': {e}")
                if raise_errors:
                    raise e
                return pd.DataFrame(columns=["FECHA", "DESCRIPCION", "NETO", "CANTIDAD", "SUCURSAL", "FAMILIA", "AÑO", "SEMANA"])

        elif empresa == "comercial":
            cols_out = ["FECHA", "DESCRIPCION", "NETO", "CANTIDAD", "SUCURSAL", "FAMILIA", "AÑO", "SEMANA", "N_BOLETA"]
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(SQL_VENTAS_COMERCIAL_LINEAS)
                rows = cursor.fetchall()
                conn.close()
                if not rows:
                    df = pd.DataFrame(columns=cols_out)
                else:
                    df = pd.DataFrame(rows)
                    df.columns = df.columns.str.strip().str.upper()
                    df.rename(columns={
                        "DES_ARTICU": "DESCRIPCION",
                        "RUBRO": "FAMILIA",
                        "N_COMP": "N_BOLETA",
                    }, inplace=True)
                    df = procesar_neto_comercial_mismo_que_dashboard(df, diagnostico=False)
                    if df.empty:
                        df = pd.DataFrame(columns=cols_out)
                    else:
                        if "FAMILIA" not in df.columns:
                            df["FAMILIA"] = "SIN FAMILIA"
                        df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
                        df = df.dropna(subset=["FECHA", "DESCRIPCION"])
                        df["SEMANA"] = df["FECHA"].dt.isocalendar().week
                        df["AÑO"] = df["FECHA"].dt.year
            except Exception as e:
                print(f"❌ Error crítico procesando '{empresa}' (DB): {e}")
                if raise_errors:
                    raise e
                df = pd.DataFrame(columns=cols_out)

        else:
            try:
                storage_options = {'User-Agent': 'Mozilla/5.0'}
                df = pd.read_csv(url_o_id, encoding="utf-8", storage_options=storage_options, low_memory=False)
                df.columns = df.columns.str.strip().str.upper()

            except Exception as e:
                print(f"❌ Error crítico procesando '{empresa}': {e}")
                if raise_errors:
                    raise e
                return pd.DataFrame(columns=["FECHA", "DESCRIPCION", "NETO", "CANTIDAD", "SUCURSAL", "FAMILIA", "AÑO", "SEMANA"])

        _cache[empresa] = df
        chile = pytz.timezone("America/Santiago")
        _ultima_actualizacion[empresa] = datetime.now(chile)

    return _cache[empresa].copy()

def obtener_fecha_actualizacion(empresa="comercial"):
    return _ultima_actualizacion.get(empresa)


def forzar_actualizacion(empresa="comercial"):
    global _cache
    if empresa in _cache:
        del _cache[empresa]

def refrescar_todo_el_cache():
    resultados = []
    fuentes = list(URLS.keys())
    if "agricola" not in fuentes:
        fuentes.append("agricola")
    if "comercial" not in fuentes:
        fuentes.append("comercial")
        
    for key in fuentes:
        try:
            if key in _cache:
                del _cache[key]
            obtener_datos(key, raise_errors=True)  # Forza recarga y lanza error si hay problema
            resultados.append({"fuente": key, "status": "success", "error": None})
        except Exception as e:
            print(f"⚠️ Error recargando '{key}': {e}")
            resultados.append({"fuente": key, "status": "error", "error": str(e)})
    return resultados
