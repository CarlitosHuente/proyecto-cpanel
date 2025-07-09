import pandas as pd

MESES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
         "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]

def fmt(n):
    return f"${int(n):,}".replace(",", ".") if n != 0 else "$0"

def obtener_resumen_mensual_tabular(df, filtros):
    if filtros.get("sucursal") and filtros["sucursal"] != "TODAS":
        df = df[df["SUCURSAL"] == filtros["sucursal"]]

    if filtros.get("desde") and filtros.get("hasta"):
        try:
            desde_dt = pd.to_datetime(filtros["desde"])
            hasta_dt = pd.to_datetime(filtros["hasta"])
            df = df[(df["FECHA"] >= desde_dt) & (df["FECHA"] <= hasta_dt)]
        except:
            return []

    elif filtros.get("año"):
        df = df[df["AÑO"] == int(filtros["año"])]

    tipo = filtros.get("filtro_por", "FAMILIA")
    valor = filtros.get("valor", "TODOS")

    if tipo == "FAMILIA":
        if valor != "TODOS":
            df = df[df["FAMILIA"] == valor]
            campo = "DESCRIPCION"  # Agrupa por productos si filtraste una familia
        else:
            campo = "FAMILIA"      # Agrupa por familias si no hay filtro
    elif tipo == "DESCRIPCION":
        if valor != "TODOS":
            df = df[df["DESCRIPCION"] == valor]
        campo = "DESCRIPCION"
    else:
        campo = "FAMILIA"


    df["MES"] = df["FECHA"].dt.month
    etiquetas = sorted(df[campo].dropna().unique())

    tabla = []
    totales_mes = {mes: {"neto": 0, "cant": 0} for mes in range(1, 13)}
    total_neto_general = 0

    for et in etiquetas:
        fila_neto = []
        fila_cant = []
        fila_unit = []
        neto_total = 0
        cant_total = 0

        for mes in range(1, 13):
            df_mes = df[(df[campo] == et) & (df["MES"] == mes)]
            neto = df_mes["NETO"].sum()
            cant = df_mes["CANTIDAD"].sum()
            unit = neto / cant if cant else 0

            fila_neto.append(fmt(neto))
            fila_cant.append(f"{int(cant):,}".replace(",", "."))
            fila_unit.append(fmt(unit))

            totales_mes[mes]["neto"] += neto
            totales_mes[mes]["cant"] += cant

            neto_total += neto
            cant_total += cant

        total_unit = neto_total / cant_total if cant_total else 0
        total_neto_general += neto_total

        tabla.append({
            "producto": et,
            "neto": fila_neto,
            "cant": fila_cant,
            "unit": fila_unit,
            "total_neto": fmt(neto_total),
            "total_cant": f"{int(cant_total):,}".replace(",", "."),
            "total_unit": fmt(total_unit)
        })

    fila_total_neto = [fmt(totales_mes[mes]["neto"]) for mes in range(1, 13)]

    return {
        "tabla": tabla,
        "total": {
            "neto": fila_total_neto,
            "total_neto": fmt(total_neto_general)
        }
    }
