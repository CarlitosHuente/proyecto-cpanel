"""
Importación unificada de ventas desde Excel/CSV hacia tablas separadas (agrícola vs comercial).
Misma forma de filas en BD; comercial añade columna `sucursal` por archivo.
"""
import os
import re
import unicodedata
import pandas as pd

# Nombres canónicos de sucursal (filtros dashboard / costeo). Claves = slug normalizado sin tildes.
SUCURSAL_ALIAS = {
    "COSTANERA": "Costanera Center",
    "COSTANERA CENTER": "Costanera Center",
    "PLAZA EGANA": "Plaza Egaña",
    "PLAZAEGAÑA": "Plaza Egaña",
    "PLAZAEGANA": "Plaza Egaña",
    "EGANA": "Plaza Egaña",
    "MUT": "MUT",
    "ESC MILITAR": "Esc.Militar",
    "ESC. MILITAR": "Esc.Militar",
    "ESCMILITAR": "Esc.Militar",
    "FOOD TRUCK": "Food Truck",
    "FOODTRUCK": "Food Truck",
    "PAGINA WEB": "Pagina Web",
    "PAGINAWEB": "Pagina Web",
    "WEB": "Pagina Web",
    "COCINA CIEGA I": "Cocina Ciega I",
    "COCINA CIEGA": "Cocina Ciega I",
    "MESA CHILENA": "Mesa Chilena",
}

COLUMNAS_NUMERICAS_VENTAS = [
    "PROPINA", "SUBTOTAL", "TOTAL", "CANTIDAD", "PRECIO", "PRECIO_LIS",
    "SUB_RENGL", "TOT_RENGL",
]

SQL_INSERT_VENTAS_AGRICOLA = """INSERT INTO ventas_agricola (
    carga_id, id_comanda, estado, estado_stk, fecha, apertura, hora_pedid, hora_entre, hora_acord, cierre,
    cod_horari, des_horari, cod_repart, des_repart, cod_zona, des_zona, cod_client, des_client,
    propina, impresion, subtotal, total, t_comp, n_comp, cod_articu, des_articu, tipo, rubro,
    cod_bodega, des_bodega, cantidad, precio, precio_lis, sub_rengl, tot_rengl, hora_coci, envio_coci,
    modificado, motivo, autoriza, usuario, fecha_anu, hora_anu
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""

SQL_INSERT_VENTAS_COMERCIAL = """INSERT INTO ventas_comercial (
    carga_id, id_comanda, estado, estado_stk, fecha, apertura, hora_pedid, hora_entre, hora_acord, cierre,
    cod_horari, des_horari, cod_repart, des_repart, cod_zona, des_zona, cod_client, des_client,
    propina, impresion, subtotal, total, t_comp, n_comp, cod_articu, des_articu, tipo, rubro,
    cod_bodega, des_bodega, cantidad, precio, precio_lis, sub_rengl, tot_rengl, hora_coci, envio_coci,
    modificado, motivo, autoriza, usuario, fecha_anu, hora_anu, sucursal
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""


def limpiar_numericos_ventas(df):
    for col in COLUMNAS_NUMERICAS_VENTAS:
        if col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str).str.replace("$", "", regex=False).str.strip()
                df[col] = df[col].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _norm_nombre_columna(name):
    """Upper sin tildes (para reconocer encabezados Excel en español)."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = unicodedata.normalize("NFD", str(name).strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s.strip().upper()


def _limpiar_rubro_desde_export_web(val):
    """Quita prefijos tipo '\\Empanadas' del export de página web."""
    if pd.isna(val):
        return val
    t = str(val).strip().lstrip("\\").strip().lstrip("/").strip()
    return t.upper() if t else None


def es_formato_export_web_comercial(columnas_canonicas):
    """
    Export alternativo (p. ej. ventas página web): columnas tipo NÚMERO, NETO línea,
    DESCRIPCIÓN producto — distinto del Resumen estándar (DES_ARTICU, SUB_RENGL).
    """
    c = {_norm_nombre_columna(col) for col in columnas_canonicas}
    if "DES_ARTICU" in c:
        return False
    need = {"DESCRIPCION", "NUMERO", "NETO"}
    return need.issubset(c)


def _fold_upper_sin_tildes(x):
    s = unicodedata.normalize("NFD", str(x).strip().upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def adaptar_dataframe_export_web_a_esquema_resumen(df):
    """
    Mapea el export web al esquema POS en BD: columnas como SUB_RENGL/PRECIO en **bruto con IVA (×1,19)**
    respecto al NETO/P. unitario del Excel (que vienen netos), **salvo** el artículo **DESPACHO WEB** (sin IVA:
    se guarda el neto tal cual, igual que en el Excel). Así el dashboard usa la misma regla /1,19 para todo
    excepto DESPACHO WEB. Las líneas tipo Nota de Crédito (columna **TIPO**) se mantienen: suelen venir en
    negativo y restan igual que en el archivo (×1,19 como el resto, salvo DESPACHO WEB).
    """
    if df is None or getattr(df, "empty", False):
        return df
    if not es_formato_export_web_comercial(df.columns):
        return df

    out = df.copy()
    out.rename(columns=lambda x: _norm_nombre_columna(x), inplace=True)

    desc_fold = out["DESCRIPCION"].astype(str).map(_fold_upper_sin_tildes)
    mask_despacho = desc_fold.str.contains("DESPACHO WEB", na=False)

    neto_ln = pd.to_numeric(out["NETO"], errors="coerce").fillna(0)
    sub_bruto = neto_ln * 1.19
    sub_rengl_calc = sub_bruto.mask(mask_despacho, neto_ln)

    out["DES_ARTICU"] = out["DESCRIPCION"].astype(str).str.strip()
    out["N_COMP"] = out["NUMERO"]

    if "PRODUCTO" in out.columns:
        out["COD_ARTICU"] = out["PRODUCTO"]
    if "CLIENTE" in out.columns:
        out["DES_CLIENT"] = out["CLIENTE"]

    if "FAMILIA" in out.columns:
        out["RUBRO"] = out["FAMILIA"].map(_limpiar_rubro_desde_export_web)

    if "TIPO" in out.columns:
        primera = (
            out["TIPO"].astype(str).str.strip().str.upper().str.split().str[0]
        )
        out["T_COMP"] = primera.where(
            primera.notna() & (primera.astype(str).str.len() > 0),
            other="WEB",
        )
    else:
        out["T_COMP"] = "WEB"

    px = pd.to_numeric(out["PRECIO UNITARIO"], errors="coerce") if "PRECIO UNITARIO" in out.columns else None
    if px is not None:
        px_f = px.astype(float)
        precio_bruto = px_f * 1.19
        out["PRECIO"] = precio_bruto.mask(mask_despacho, px_f)
        if "PRECIO_LIS" not in out.columns:
            out["PRECIO_LIS"] = out["PRECIO"]

    out["SUB_RENGL"] = sub_rengl_calc
    out["TOT_RENGL"] = sub_rengl_calc

    out["ESTADO"] = "COBRADO"

    return out


def leer_dataframe_desde_archivo(file_path, fuente):
    """
    fuente: 'AGRICOLA' | 'COMERCIAL'
    Comercial: hoja 'Resumen' si existe; Agrícola: 'Hoja1' si existe.
    """
    lower = file_path.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(file_path, encoding="utf-8", low_memory=False)
        return df, "CSV"

    xl = pd.ExcelFile(file_path)
    if fuente == "COMERCIAL":
        hoja = "Resumen" if "Resumen" in xl.sheet_names else xl.sheet_names[0]
    else:
        hoja = "Hoja1" if "Hoja1" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(file_path, sheet_name=hoja)
    return df, hoja


def _normalizar_clave_sucursal(texto):
    """Mayúsculas, sin tildes, espacios colapsados (para matchear alias)."""
    if not texto:
        return ""
    s = unicodedata.normalize("NFD", str(texto).strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).upper().strip()


def extraer_semana_y_sucursal_desde_archivo(nombre_archivo):
    """
    Convención: Sem. <número de semana> <nombre sucursal> [Comercial]
    Acepta espacios o guiones bajos: Sem._09_COSTANERA, Sem. 12 Plaza Egaña Comercial
    Retorna (semana int | None, nombre_sucursal crudo sin alias).
    """
    base = os.path.splitext(nombre_archivo)[0].strip()
    if base.lower().endswith(" comercial"):
        base = base[: -len(" Comercial")].strip()

    # Sem. [sep] NN [sep] resto
    m = re.match(r"^Sem\.[\s_]*(\d+)[\s_]+(.+)$", base, re.IGNORECASE)
    if m:
        semana = int(m.group(1))
        raw = m.group(2).replace("_", " ")
        raw = re.sub(r"\s+", " ", raw).strip()
        return semana, raw

    m2 = re.match(r"^Sem\.[\s_]*(.+)$", base, re.IGNORECASE)
    if m2:
        resto = m2.group(1).replace("_", " ")
        resto = re.sub(r"\s+", " ", resto).strip()
        num = re.match(r"^(\d+)\s+(.+)$", resto)
        if num:
            return int(num.group(1)), num.group(2).strip()
        return None, resto

    return None, base or "COMERCIAL"


def _aplicar_alias_sucursal(nombre_limpio):
    clave = _normalizar_clave_sucursal(nombre_limpio)
    return SUCURSAL_ALIAS.get(clave)


def _titulo_legible(nombre):
    """Mantiene palabras cortas en mayúsculas razonables; no fuerza todo TITLE."""
    if not nombre:
        return "COMERCIAL"
    partes = nombre.split()
    out = []
    for p in partes:
        low = p.lower()
        if low in ("de", "del", "la", "y"):
            out.append(low)
        elif p.isupper() or (len(p) <= 3 and p.isalpha()):
            out.append(p if p.isupper() else p.title())
        else:
            out.append(p[:1].upper() + p[1:].lower() if len(p) > 1 else p.upper())
    return " ".join(out)


def inferir_sucursal_comercial(nombre_archivo):
    """
    Devuelve el nombre de sucursal para filtros (misma familia que la segunda captura: Plaza Egaña, MUT, etc.).
    """
    _semana, raw = extraer_semana_y_sucursal_desde_archivo(nombre_archivo)
    alias = _aplicar_alias_sucursal(raw)
    if alias:
        return alias
    if not raw or raw.upper() == "COMERCIAL":
        return "COMERCIAL"
    return _titulo_legible(raw)


def _tupla_detalle_base(row_dict, carga_id):
    fecha_val = None
    if row_dict.get("FECHA"):
        try:
            fecha_val = pd.to_datetime(row_dict.get("FECHA")).strftime("%Y-%m-%d")
        except Exception:
            fecha_val = None
    return (
        carga_id,
        row_dict.get("ID_COMANDA"),
        row_dict.get("ESTADO"),
        row_dict.get("ESTADO_STK"),
        fecha_val,
        row_dict.get("APERTURA"),
        row_dict.get("HORA_PEDID"),
        row_dict.get("HORA_ENTRE"),
        row_dict.get("HORA_ACORD"),
        row_dict.get("CIERRE"),
        row_dict.get("COD_HORARI"),
        row_dict.get("DES_HORARI"),
        row_dict.get("COD_REPART"),
        row_dict.get("DES_REPART"),
        row_dict.get("COD_ZONA"),
        row_dict.get("DES_ZONA"),
        row_dict.get("COD_CLIENT"),
        row_dict.get("DES_CLIENT"),
        row_dict.get("PROPINA"),
        row_dict.get("IMPRESION"),
        row_dict.get("SUBTOTAL"),
        row_dict.get("TOTAL"),
        row_dict.get("T_COMP"),
        row_dict.get("N_COMP"),
        row_dict.get("COD_ARTICU"),
        row_dict.get("DES_ARTICU"),
        row_dict.get("TIPO"),
        row_dict.get("RUBRO"),
        row_dict.get("COD_BODEGA"),
        row_dict.get("DES_BODEGA"),
        row_dict.get("CANTIDAD"),
        row_dict.get("PRECIO"),
        row_dict.get("PRECIO_LIS"),
        row_dict.get("SUB_RENGL"),
        row_dict.get("TOT_RENGL"),
        row_dict.get("HORA_COCI"),
        row_dict.get("ENVIO_COCI"),
        row_dict.get("MODIFICADO"),
        row_dict.get("MOTIVO"),
        row_dict.get("AUTORIZA"),
        row_dict.get("USUARIO"),
        row_dict.get("FECHA_ANU"),
        row_dict.get("HORA_ANU"),
    )


def construir_filas_insert(df, carga_id, sucursal=None):
    """sucursal: str si comercial; None si agrícola."""
    df = limpiar_numericos_ventas(df.copy())
    df.columns = [str(c).strip().upper() for c in df.columns]
    df = df.where(pd.notnull(df), None)

    filas = []
    for _, row in df.iterrows():
        row_dict = {str(k).strip().upper(): (None if pd.isna(v) else v) for k, v in row.items()}
        base = _tupla_detalle_base(row_dict, carga_id)
        if sucursal is not None:
            filas.append(base + (sucursal,))
        else:
            filas.append(base)
    return filas


def ejecutar_carga_ventas(cursor, file_path, nombre_archivo, fuente, usuario, sucursal_comercial=None):
    """
    Inserta en cargas_* y ventas_* según fuente.
    fuente: 'AGRICOLA' | 'COMERCIAL'
    """
    df, _hoja = leer_dataframe_desde_archivo(file_path, fuente)
    if fuente == "COMERCIAL":
        df = adaptar_dataframe_export_web_a_esquema_resumen(df)
    n = len(df)

    if fuente == "COMERCIAL":
        if not sucursal_comercial:
            sucursal_comercial = inferir_sucursal_comercial(nombre_archivo)
        cursor.execute(
            "INSERT INTO cargas_comercial (nombre_archivo, registros_insertados, usuario) VALUES (%s, %s, %s)",
            (nombre_archivo, n, usuario),
        )
        carga_id = cursor.lastrowid
        filas = construir_filas_insert(df, carga_id, sucursal=sucursal_comercial)
        sql = SQL_INSERT_VENTAS_COMERCIAL
    else:
        cursor.execute(
            "INSERT INTO cargas_agricola (nombre_archivo, registros_insertados, usuario) VALUES (%s, %s, %s)",
            (nombre_archivo, n, usuario),
        )
        carga_id = cursor.lastrowid
        filas = construir_filas_insert(df, carga_id, sucursal=None)
        sql = SQL_INSERT_VENTAS_AGRICOLA

    chunk = 1000
    for i in range(0, len(filas), chunk):
        cursor.executemany(sql, filas[i : i + chunk])

    return n, carga_id
