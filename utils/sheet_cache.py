# Asegúrate de tener estos imports al principio del archivo sheet_cache.py
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
    "comercial": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSwgsbEzQxQAkBXjP5LfyqOalCDCEJRq_YxMrGII-VkijQSbjm_zxMZpXMVE6LtKhIYWYyhFYC6-UwY/pub?output=csv",
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


# --- REEMPLAZA TU FUNCIÓN obtener_datos CON ESTA ---

# Reemplaza la función completa en utils/sheet_cache.py

def obtener_datos(empresa="comercial", raise_errors=False):
    if empresa not in _cache:
        url_o_id = URLS.get(empresa)

        # "agricola" no usa url_o_id porque lee directo de la Base de Datos
        if not url_o_id and empresa != "agricola":
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
                cursor.execute("SELECT * FROM ventas_agricola")
                rows = cursor.fetchall()
                conn.close()
                
                cols_base = ["FECHA", "DESCRIPCION", "NETO", "CANTIDAD", "SUCURSAL", "FAMILIA", "AÑO", "SEMANA"]
                if not rows:
                    return pd.DataFrame(columns=cols_base)
                    
                df = pd.DataFrame(rows)
                df.columns = df.columns.str.strip().str.upper()

                # 1. Filtro 'Cobrado'
                if "ESTADO" in df.columns:
                    df = df[df["ESTADO"].astype(str).str.strip().str.upper().isin(["COBRADO", "COBRADA", "DESPACH./COBRADA"])]
                
                # 2. Renombrar para el Dashboard estándar
                df.rename(columns={
                    "DES_ARTICU": "DESCRIPCION",
                    "RUBRO": "FAMILIA",
                    "PRECIO": "NETO",
                    "DES_BODEGA": "SUCURSAL",
                    "N_COMP": "N_BOLETA"
                }, inplace=True)
                
                # 3. Asegurar que Sucursal siempre exista (Por defecto: SALA DE VENTAS)
                if "SUCURSAL" not in df.columns:
                    df["SUCURSAL"] = "SALA DE VENTAS"
                else:
                    df["SUCURSAL"] = df["SUCURSAL"].fillna("SALA DE VENTAS").replace("", "SALA DE VENTAS")

                columnas_requeridas = ["FECHA", "DESCRIPCION", "NETO", "CANTIDAD"]
                df = df.dropna(subset=columnas_requeridas)
                df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
                df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
                df["NETO"] = pd.to_numeric(df["NETO"], errors="coerce").fillna(0)
                df["SEMANA"] = df["FECHA"].dt.isocalendar().week
                df["AÑO"] = df["FECHA"].dt.year

            except Exception as e:
                print(f"❌ Error crítico procesando '{empresa}': {e}")
                if raise_errors:
                    raise e
                return pd.DataFrame(columns=["FECHA", "DESCRIPCION", "NETO", "CANTIDAD", "SUCURSAL", "FAMILIA", "AÑO", "SEMANA"])

        else:
            try:
                # --- INICIO DE LA SOLUCIÓN ---
                # Añadimos un User-Agent para simular una petición de navegador
                storage_options = {'User-Agent': 'Mozilla/5.0'}
                df = pd.read_csv(url_o_id, encoding="utf-8", storage_options=storage_options, low_memory=False)
                # --- FIN DE LA SOLUCIÓN ---
                
                df.columns = df.columns.str.strip().str.upper()

                if empresa == "comercial":
                    df.rename(columns={"AÃ‘O": "AÑO"}, inplace=True)
                    columnas_requeridas = ["FECHA", "DESCRIPCION", "NETO", "CANTIDAD"]
                    faltantes = [col for col in columnas_requeridas if col not in df.columns]
                    if faltantes:
                        raise KeyError(f"❌ Columnas faltantes en '{empresa}': {faltantes}")

                    # FIX: Asegurarse de que la columna FAMILIA siempre exista para evitar que el dashboard se caiga.
                    if "FAMILIA" not in df.columns:
                        df["FAMILIA"] = "SIN FAMILIA"

                    df = df.dropna(subset=columnas_requeridas)
                    df["FECHA"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors="coerce")
                    df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
                    df["NETO"] = pd.to_numeric(df["NETO"], errors="coerce").fillna(0)
                    df["SEMANA"] = df["FECHA"].dt.isocalendar().week
                    df["AÑO"] = df["FECHA"].dt.year

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
