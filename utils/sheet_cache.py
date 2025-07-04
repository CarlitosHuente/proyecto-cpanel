import pandas as pd

URLS = {
    "comercial": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSwgsbEzQxQAkBXjP5LfyqOalCDCEJRq_YxMrGII-VkijQSbjm_zxMZpXMVE6LtKhIYWYyhFYC6-UwY/pub?output=csv",
    "agricola": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ5rxTxzzXBCjef9Mvoe74H95ZbZ1p2xsDrdazyk1lN1mYCaOry4PJiOrypoxNOub_T7o9fZmJ7QYHt/pub?output=csv"
}

_cache = {}

def obtener_datos(empresa="comercial"):
    if empresa not in _cache:
        url = URLS.get(empresa)
        df = pd.read_csv(url, encoding="utf-8")
        df.columns = df.columns.str.strip().str.upper()

        # Corregimos el problema de codificación en "AÑO"
        df.rename(columns={"AÃ‘O": "AÑO"}, inplace=True)

        # Limpieza básica
        df = df.dropna(subset=["FECHA", "DESCRIPCION", "NETO", "CANTIDAD"])
        df["FECHA"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors="coerce")
        df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0)
        df["NETO"] = pd.to_numeric(df["NETO"], errors="coerce").fillna(0)
        df["SEMANA"] = df["FECHA"].dt.isocalendar().week
        df["AÑO"] = df["FECHA"].dt.year

        # Limpieza de texto
        for col in ["SUCURSAL", "FAMILIA", "DESCRIPCION"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().str.replace(r"[\\\/]", "", regex=True).str.upper()

        _cache[empresa] = df

    return _cache[empresa].copy()


def forzar_actualizacion(empresa="comercial"):
    global _cache
    if empresa in _cache:
        del _cache[empresa]

