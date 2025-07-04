# resumen_service.py
import pandas as pd

MESES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
         "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]

def fmt(n):
    return f"{int(n):,}".replace(",", ".") if n != 0 else "0"

def obtener_resumen_mensual(df, filtros):
    if filtros.get("sucursal") and filtros["sucursal"] != "TODAS":
        df = df[df["SUCURSAL"] == filtros["sucursal"]]

    if filtros.get("año"):
        df = df[df["AÑO"] == int(filtros["año"])]

    tipo = filtros.get("filtro_por", "FAMILIA")
    valor = filtros.get("valor", "TODOS")

    if tipo == "FAMILIA" and valor != "TODOS":
        df = df[df["FAMILIA"] == valor]
        campo = "DESCRIPCION"
    elif tipo == "DESCRIPCION" and valor != "TODOS":
        df = df[df["DESCRIPCION"] == valor]
        campo = "DESCRIPCION"
    else:
        campo = "FAMILIA"

    df["MES"] = df["FECHA"].dt.month
    etiquetas = sorted(df[campo].dropna().unique())

    total_neto_mensual = [0] * 12
    total_cant_mensual = [0] * 12
    total_neto_acum = 0
    total_cant_acum = 0

    resumen = []

    # Ordenar etiquetas por total neto
    ordenadas = df.groupby(campo)["NETO"].sum().sort_values(ascending=False).index.tolist()

    for et in ordenadas:
        row_neto = [et[:25].ljust(25), "NETO".ljust(10)]
        row_cant = ["".ljust(25), "CANTIDAD".ljust(10)]

        total_neto = 0
        total_cant = 0

        for mes in range(1, 13):
            df_mes = df[(df[campo] == et) & (df["MES"] == mes)]
            neto = df_mes["NETO"].sum()
            cant = df_mes["CANTIDAD"].sum()

            row_neto.append(fmt(neto).rjust(12))
            row_cant.append(fmt(cant).rjust(12))

            total_neto += neto
            total_cant += cant

            total_neto_mensual[mes - 1] += neto
            total_cant_mensual[mes - 1] += cant

        row_neto.append(fmt(total_neto).rjust(12))
        row_cant.append(fmt(total_cant).rjust(12))

        total_neto_acum += total_neto
        total_cant_acum += total_cant

        resumen.append("│".join(row_neto))
        resumen.append("│".join(row_cant))

    encabezado = ["".ljust(25), "".ljust(10)] + [m.center(12) for m in MESES] + ["TOTAL".center(12)]
    separador = "=" * (len(encabezado) * 1)

    fila_total_neto = ["TOTAL GENERAL".ljust(25), "NETO".ljust(10)] + \
                      [fmt(n).rjust(12) for n in total_neto_mensual] + [fmt(total_neto_acum).rjust(12)]

    fila_total_cant = ["".ljust(25), "CANTIDAD".ljust(10)] + \
                      [fmt(n).rjust(12) for n in total_cant_mensual] + [fmt(total_cant_acum).rjust(12)]

    final = ["│".join(encabezado), separador] + resumen + \
            ["│".join(fila_total_neto), "│".join(fila_total_cant)]

    return "\n".join(final)
