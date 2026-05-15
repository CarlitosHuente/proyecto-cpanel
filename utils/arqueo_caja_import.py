"""
Importación de arqueo de caja desde Excel.

Formato típico contable / PruebaSemana (columnas B,F,G,H,K,L):
  B canal (DESC_CTA), F fecha (FECHA / serial Excel), G tipo doc (COD_COMP),
  H número boleta (N_COMP), K DEBE, L HABER.

También se reconocen encabezados por nombre (FEC_COMPR, etc.).
Si faltan nombres pero hay al menos 12 columnas, se intenta mapeo por posición.
Neto línea = DEBE − HABER.
"""
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import BinaryIO, List, Optional, Tuple

import pandas as pd


def _buffer_archivo_subido(archivo: BinaryIO) -> io.BytesIO:
    """
    pandas/openpyxl exigen un file-like con seekable().
    request.files['archivo'].stream en producción es SpooledTemporaryFile (Werkzeug)
    y no define seekable(), aunque sí seek/read.
    """
    if isinstance(archivo, io.BytesIO):
        try:
            if archivo.seekable():
                archivo.seek(0)
                return archivo
        except AttributeError:
            pass
    data = archivo.read()
    buf = io.BytesIO(data if isinstance(data, bytes) else bytes(data))
    buf.seek(0)
    return buf


def parse_monto_entrada(val) -> Decimal:
    """Parseo de monto desde formulario (formato chileno con coma decimal opcional)."""
    d = _parse_decimal(val)
    if d is None:
        raise ValueError("Monto inválido")
    return d


def parse_propina_opcional(val):
    """Propina informativa; vacío = None."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return parse_monto_entrada(s)


def normalizar_canal(val) -> str:
    """Clave única para comparar canales (terreno vs sistema)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = unicodedata.normalize("NFD", str(val).strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def _norm_nombre_columna(name) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = unicodedata.normalize("NFD", str(name).strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def _mapear_columnas(df: pd.DataFrame) -> dict:
    """Devuelve dict canónico -> nombre real en el DataFrame."""
    canon = {
        "FEC_COMPR": ["FEC_COMPR", "FECHA", "FEC COMP", "FECHA_COMPRA", "FECHA COMP"],
        "N_COMP": [
            "N_COMP",
            "N COMP",
            "NUMERO",
            "NUMERO BOLETA",
            "Nº COMP",
            "N° COMP",
            "N_COMP.",
            "N BOLETA",
        ],
        "DESC_CTA": [
            "DESC_CTA",
            "DESC CTA",
            "CUENTA",
            "DESCRIPCION",
            "DESCRIPCIÓN",
            "CANAL",
        ],
        "COD_COMP": [
            "COD_COMP",
            "COD COMP",
            "TIPO DOC",
            "TIPO_DOC",
            "TIPO DOCUMENTO",
            "T_COMP",
            "T COMP",
        ],
        "DEBE": ["DEBE"],
        "HABER": ["HABER"],
    }
    inv = {}
    for col in df.columns:
        inv[_norm_nombre_columna(col)] = col
    out = {}
    for key, aliases in canon.items():
        found = None
        for a in aliases:
            na = _norm_nombre_columna(a)
            if na in inv:
                found = inv[na]
                break
        if found is not None:
            out[key] = found
    return out


def _mapear_por_posicion_bfghkl(df: pd.DataFrame) -> dict:
    """
    Respaldo: columnas Excel B,F,G,H,K,L → índices 1,5,6,7,10,11 (0-based).
    Útil si el archivo no trae encabezados reconocibles pero el layout es el estándar contable.
    """
    if df.shape[1] < 12:
        return {}
    cols = list(df.columns)
    return {
        "DESC_CTA": cols[1],
        "FEC_COMPR": cols[5],
        "COD_COMP": cols[6],
        "N_COMP": cols[7],
        "DEBE": cols[10],
        "HABER": cols[11],
    }


def _fusionar_mapeo_por_nombre_y_posicion(df: pd.DataFrame) -> dict:
    por_nombre = _mapear_columnas(df)
    faltan_req = [k for k in ("FEC_COMPR", "N_COMP", "DESC_CTA", "DEBE") if k not in por_nombre]
    if not faltan_req:
        return por_nombre
    por_pos = _mapear_por_posicion_bfghkl(df)
    if not por_pos:
        return por_nombre
    out = dict(por_pos)
    for k, v in por_nombre.items():
        out[k] = v
    return out


def _parse_decimal(val) -> Optional[Decimal]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        try:
            return Decimal(str(val))
        except InvalidOperation:
            return None
    s = str(val).strip().replace("$", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_fechas(series: pd.Series) -> pd.Series:
    """Convierte a datetime.date; soporta serial Excel numérico."""
    s = series.copy()
    num = pd.to_numeric(s, errors="coerce")
    mask_num = num.notna() & (num > 200) & (num < 600000)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if mask_num.any():
        excel_dates = pd.to_datetime(num[mask_num], unit="D", origin="1899-12-30", errors="coerce")
        out.loc[mask_num] = excel_dates
    rest = ~mask_num
    if rest.any():
        parsed = pd.to_datetime(s[rest], dayfirst=True, errors="coerce")
        out.loc[rest] = parsed
    return out.dt.date


def leer_arqueo_excel(archivo: BinaryIO, filename: str) -> Tuple[pd.DataFrame, List[str]]:
    """
    Lee Excel/CSV y devuelve DataFrame con columnas:
    fec_compr (date), n_comp, cod_comp (opcional), desc_cta, debe, haber
    """
    errores: List[str] = []
    archivo = _buffer_archivo_subido(archivo)
    low = (filename or "").lower()
    if low.endswith(".csv"):
        df = pd.read_csv(archivo, dtype=str, encoding="utf-8", errors="replace")
    else:
        df = pd.read_excel(archivo, dtype=None, engine="openpyxl")

    if df.empty:
        raise ValueError("El archivo no tiene filas.")

    required = ["FEC_COMPR", "N_COMP", "DESC_CTA", "DEBE"]
    cmap_nombre = _mapear_columnas(df)
    faltaban_nombres = [k for k in required if k not in cmap_nombre]
    cmap = _fusionar_mapeo_por_nombre_y_posicion(df)
    faltan = [k for k in required if k not in cmap]
    if faltan:
        raise ValueError(
            "Faltan columnas obligatorias: "
            + ", ".join(faltan)
            + ". Encontradas: "
            + ", ".join(str(c) for c in df.columns)
            + ". Si el layout es B=canal, F=fecha, G=tipo, H=boleta, K=debe, L=haber, "
            "asegurate de tener al menos 12 columnas (A..L)."
        )
    if faltaban_nombres and all(k in cmap for k in required):
        errores.append(
            "Algunas columnas no tenían encabezado reconocible; se usó posición fija "
            "B=canal, F=fecha, G=tipo doc, H=n° boleta, K=debe, L=haber."
        )

    out = pd.DataFrame()
    out["fec_compr"] = _parse_fechas(df[cmap["FEC_COMPR"]])
    out["n_comp"] = df[cmap["N_COMP"]].astype(str).str.strip()
    out["desc_cta"] = df[cmap["DESC_CTA"]].astype(str).str.strip()
    if "COD_COMP" in cmap:
        cc = df[cmap["COD_COMP"]].astype(str).str.strip()
        out["cod_comp"] = cc.replace({"nan": "", "None": "", "<NA>": ""})
    else:
        out["cod_comp"] = ""
    out["debe"] = df[cmap["DEBE"]].map(_parse_decimal)
    if "HABER" in cmap:
        out["haber"] = df[cmap["HABER"]].map(_parse_decimal)
    else:
        out["haber"] = pd.Series([None] * len(out), dtype=object)

    def _zero_haber(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return Decimal("0")
        return x

    out["haber"] = out["haber"].map(_zero_haber)

    nulos_fecha = out["fec_compr"].isna().sum()
    if nulos_fecha:
        errores.append(f"{nulos_fecha} filas con FEC_COMPR inválida (se omiten).")
    out = out.dropna(subset=["fec_compr"])
    out = out[out["desc_cta"].str.len() > 0]
    # Quitar fila si quedó encabezado pegado como dato
    _hdr = out["desc_cta"].str.upper().str.strip()
    out = out[~_hdr.isin(["DESC_CTA", "CANAL", "CUENTA"])]

    def _zero_debe(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return Decimal("0")
        return x

    out["debe"] = out["debe"].map(_zero_debe)
    if out["debe"].map(lambda d: d < 0).any():
        errores.append("Advertencia: hay valores DEBE negativos (se importan tal cual).")

    return out, errores


def filas_para_insert(out: pd.DataFrame) -> List[tuple]:
    """Tuplas (fec_compr, n_comp, cod_comp, desc_cta, debe, haber) para executemany."""
    rows = []
    for _, r in out.iterrows():
        debe = r["debe"] if isinstance(r["debe"], Decimal) else Decimal(str(r["debe"]))
        hab = r["haber"] if isinstance(r["haber"], Decimal) else Decimal(str(r["haber"]))
        cc = r.get("cod_comp", "") or ""
        cc = str(cc).strip()[:30] if str(cc).strip() and str(cc).strip().lower() != "nan" else None
        rows.append(
            (
                r["fec_compr"],
                str(r["n_comp"])[:120],
                cc,
                str(r["desc_cta"])[:255],
                debe,
                hab,
            )
        )
    return rows
