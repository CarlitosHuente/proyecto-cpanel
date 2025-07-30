# Asegúrate de tener estos imports al principio del archivo sheet_cache.py
import pandas as pd
from datetime import datetime
import pytz
import io
import os # Necesario para construir la ruta al archivo de credenciales

# Imports para la API de Google
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

_ultima_actualizacion = {}
_cache = {}
# ... (Aquí va tu diccionario de URLS, sin cambios)
URLS = {
    "comercial": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSwgsbEzQxQAkBXjP5LfyqOalCDCEJRq_YxMrGII-VkijQSbjm_zxMZpXMVE6LtKhIYWYyhFYC6-UwY/pub?output=csv",
    "agricola": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ5rxTxzzXBCjef9Mvoe74H95ZbZ1p2xsDrdazyk1lN1mYCaOry4PJiOrypoxNOub_T7o9fZmJ7QYHt/pub?output=csv",
    "temperatura_equipos": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?output=csv",
    "equipos_info": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?gid=946296021&single=true&output=csv",
    "mayor": "1zFjARS82JAuay19WxxgepBl7jYylgPIn" # Ahora aquí solo guardamos el ID de la carpeta
}


# --- REEMPLAZA TU FUNCIÓN obtener_datos CON ESTA ---

def obtener_datos(empresa="comercial"):
    if empresa not in _cache:
        url_o_id = URLS.get(empresa)

        if not url_o_id:
            raise Exception(f"No se ha definido la URL o ID para '{empresa}'")

        # 🟡 NUEVA LÓGICA PARA EL ARCHIVO CONTABLE "MAYOR" USANDO LA API
        elif empresa == "mayor":
            try:
                # 1. Configurar credenciales
                SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
                # Construye la ruta al archivo de credenciales en la raíz del proyecto
                BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Directorio de este archivo (utils)
                ROOT_DIR = os.path.dirname(BASE_DIR) # Raíz del proyecto
                SERVICE_ACCOUNT_FILE = os.path.join(ROOT_DIR, 'credenciales_google.json')

                creds = service_account.Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_FILE, scopes=SCOPES)

                # 2. Construir el servicio de la API de Drive
                drive_service = build('drive', 'v3', credentials=creds)
                
                folder_id = url_o_id # Usamos el ID de la carpeta guardado en URLS
                file_name = 'mayor.xlsx'

                # 3. Buscar el archivo por nombre dentro de la carpeta específica
                query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
                results = drive_service.files().list(q=query, fields="files(id, name)").execute()
                items = results.get('files', [])

                if not items:
                    raise Exception(f"No se encontró el archivo '{file_name}' en la carpeta de Drive.")

                file_id = items[0]['id']

                # 4. Descargar el contenido del archivo
                request = drive_service.files().get_media(fileId=file_id)
                file_content = io.BytesIO()
                downloader = MediaIoBaseDownload(file_content, request)
                
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                    print(f"Descargando archivo... {int(status.progress() * 100)}%.")

                file_content.seek(0) # Mover el cursor al inicio del contenido en memoria

                # 5. Cargar en Pandas y procesar (misma lógica que ya tenías)
                df = pd.read_excel(file_content, engine="openpyxl")
                df.columns = df.columns.str.strip().str.upper()
                df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
                df = df.dropna(subset=["FECHA", "NOMBRE", "DEBE", "HABER"])
                df["AÑO"] = df["FECHA"].dt.year
                df["MES"] = df["FECHA"].dt.month
            
            except Exception as e:
                # Si algo falla (ej: credenciales mal puestas), la app no se caerá
                print(f"ERROR al cargar 'mayor.xlsx' desde la API de Drive: {e}")
                return pd.DataFrame() # Devuelve un DataFrame vacío en caso de error

        # 🟥 LÓGICA PARA COMERCIAL / AGRICOLA (QUEDA IGUAL)
        else:
            df = pd.read_csv(url_o_id, encoding="utf-8")
            df.columns = df.columns.str.strip().str.upper()

            if empresa in ["comercial", "agricola"]:
                df.rename(columns={"AÃ‘O": "AÑO"}, inplace=True)

                columnas_requeridas = ["FECHA", "DESCRIPCION", "NETO", "CANTIDAD"]
                faltantes = [col for col in columnas_requeridas if col not in df.columns]
                if faltantes:
                    raise KeyError(f"❌ Columnas faltantes en '{empresa}': {faltantes}")

                df = df.dropna(subset=columnas_requeridas)
                df["FECHA"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors="coerce")
                df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
                df["NETO"] = pd.to_numeric(df["NETO"], errors="coerce").fillna(0)
                df["SEMANA"] = df["FECHA"].dt.isocalendar().week
                df["AÑO"] = df["FECHA"].dt.year

                for col in ["SUCURSAL", "FAMILIA", "DESCRIPCION"]:
                    if col in df.columns:
                        df[col] = df[col].astype(str).str.strip().str.replace(r"[\\\/]", "", regex=True).str.upper()

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
    for key in URLS.keys():
        if key in _cache:
            del _cache[key]
        obtener_datos(key)  # fuerza recarga inmediata

