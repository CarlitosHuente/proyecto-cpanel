import pandas as pd
from datetime import datetime
import pytz


_ultima_actualizacion = {}


URLS = {
    "comercial": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSwgsbEzQxQAkBXjP5LfyqOalCDCEJRq_YxMrGII-VkijQSbjm_zxMZpXMVE6LtKhIYWYyhFYC6-UwY/pub?output=csv",
    "agricola": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ5rxTxzzXBCjef9Mvoe74H95ZbZ1p2xsDrdazyk1lN1mYCaOry4PJiOrypoxNOub_T7o9fZmJ7QYHt/pub?output=csv",
    "temperatura_equipos": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?output=csv",
    "equipos_info": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkmW7dl4WeFzctQZhjY8ENeSkyhl1a5sy_4t9qA08QsxIbp_JiHNV8ZP6gWsA204izNAEiIPh3AUCH/pub?gid=946296021&single=true&output=csv"

}


_cache = {}

from datetime import datetime

def obtener_datos(empresa="comercial"):
    if empresa not in _cache:
        url = URLS.get(empresa)
        df = pd.read_csv(url, encoding="utf-8")
        df.columns = df.columns.str.strip().str.upper()

        # Limpieza para ventas
        if empresa in ["comercial", "agricola"]:
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

