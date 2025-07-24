import pandas as pd
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
import re
import io
import requests

_ultima_actualizacion = {}
_cache = {}

URLS = {
    "comercial": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSwgsbEzQxQAkBXjP5LfyqOalCDCEJRq_YxMrGII-VkijQSbjm_zxMZpXMVE6LtKhIYWYyhFYC6-UwY/pub?output=csv",
    "agricola": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ5rxTxzzXBCjef9Mvoe74H95ZbZ1p2xsDrdazyk1lN1mYCaOry4PJiOrypoxNOub_T7o9fZmJ7QYHt/pub?output=csv",
    "temperatura_equipos": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?output=csv",
    "equipos_info": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?gid=946296021&single=true&output=csv",
    "mayor": "https://drive.google.com/drive/folders/1zFjARS82JAuay19WxxgepBl7jYylgPIn"
}


def obtener_datos(empresa="comercial"):
    if empresa not in _cache:
        url = URLS.get(empresa)

        if not url:
            raise Exception(f"No se ha definido la URL para '{empresa}'")

        # 🟡 ESPECIAL: archivo contable mayor.xlsx desde carpeta pública
        elif empresa == "mayor":
            folder_id = "1zFjARS82JAuay19WxxgepBl7jYylgPIn"
            embed_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"

            response = requests.get(embed_url)
            if response.status_code != 200:
                raise Exception("No se pudo acceder al listado público de la carpeta.")

            soup = BeautifulSoup(response.text, "html.parser")
            file_id = None
            for link in soup.find_all("a", href=True):
                texto = link.text.strip().lower()
                href = link["href"]
                if "mayor.xlsx" in texto and "/file/d/" in href:
                    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", href)
                    if match:
                        file_id = match.group(1)
                        break

            if not file_id:
                raise Exception("No se encontró 'mayor.xlsx' en la carpeta pública.")

            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            excel_response = requests.get(download_url)
            if excel_response.status_code != 200:
                raise Exception("Error al descargar el archivo Excel desde Google Drive.")

            df = pd.read_excel(io.BytesIO(excel_response.content), engine="openpyxl")
            df.columns = df.columns.str.strip().str.upper()
            df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
            df = df.dropna(subset=["FECHA", "NOMBRE", "DEBE", "HABER"])
            df["AÑO"] = df["FECHA"].dt.year
            df["MES"] = df["FECHA"].dt.month

        # 🟥 COMERCIAL / AGRICOLA
        else:
            df = pd.read_csv(url, encoding="utf-8")
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

