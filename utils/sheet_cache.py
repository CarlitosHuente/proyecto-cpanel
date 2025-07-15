import pandas as pd
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
import re 



_ultima_actualizacion = {}


URLS = {
    "comercial": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSwgsbEzQxQAkBXjP5LfyqOalCDCEJRq_YxMrGII-VkijQSbjm_zxMZpXMVE6LtKhIYWYyhFYC6-UwY/pub?output=csv",
    "agricola": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ5rxTxzzXBCjef9Mvoe74H95ZbZ1p2xsDrdazyk1lN1mYCaOry4PJiOrypoxNOub_T7o9fZmJ7QYHt/pub?output=csv",
    "temperatura_equipos": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?output=csv",
    "equipos_info": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?gid=946296021&single=true&output=csv",
    "mayor": "https://drive.google.com/drive/folders/1zFjARS82JAuay19WxxgepBl7jYylgPIn"


}


_cache = {}

from datetime import datetime

import io
import requests
import pandas as pd
from datetime import datetime
import pytz

def obtener_datos(empresa="comercial"):
    if empresa not in _cache:
        url = URLS.get(empresa)

        if not url:
            raise Exception(f"No se ha definido la URL para '{empresa}'")

        # 🟡 NUEVO: manejo especial si es el archivo contable mayor.xlsx
        elif empresa == "mayor":
            import re
            from bs4 import BeautifulSoup

            folder_id = "1zFjARS82JAuay19WxxgepBl7jYylgPIn"  # carpeta pública
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

            # Descargar archivo
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



        # 🟥 COMERCIAL / AGRICOLA (sin tocar nada de lo que ya tienes)
        else:
            df = pd.read_csv(url, encoding="utf-8")
            df.columns = df.columns.str.strip().str.upper()
            df.rename(columns={"AÃ‘O": "AÑO"}, inplace=True)
            df = df.dropna(subset=["FECHA", "DESCRIPCION", "NETO", "CANTIDAD"])
            df["FECHA"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors="coerce")
            df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
            df["NETO"] = pd.to_numeric(df["NETO"], errors="coerce").fillna(0)
            df["SEMANA"] = df["FECHA"].dt.isocalendar().week
            df["AÑO"] = df["FECHA"].dt.year

            for col in ["SUCURSAL", "FAMILIA", "DESCRIPCION"]:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip().str.replace(r"[\\\/]", "", regex=True).str.upper()

        # Guardar en caché
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

