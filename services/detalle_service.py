# detalle_service.py

def obtener_detalle(df_filtrado, filtros):
    if df_filtrado.empty:
        return []

    tipo_filtro = filtros.get("filtro_por", "FAMILIA").upper()
    valor_filtro = filtros.get("valor", "TODOS")

    if tipo_filtro == "FAMILIA" and valor_filtro == "TODOS":
        # Agrupar por familia
        df = df_filtrado.groupby("FAMILIA").agg({
            "CANTIDAD": "sum",
            "NETO": "sum"
        }).reset_index()

        df["PRODUCTO"] = df["FAMILIA"]
        df["PRECIO UNITARIO"] = df.apply(
            lambda row: row["NETO"] / row["CANTIDAD"] if row["CANTIDAD"] else 0, axis=1
        )

    elif tipo_filtro == "FAMILIA" and valor_filtro != "TODOS":
        # Agrupar por producto dentro de la familia
        df = df_filtrado.groupby("DESCRIPCION").agg({
            "CANTIDAD": "sum",
            "NETO": "sum"
        }).reset_index()

        df["PRODUCTO"] = df["DESCRIPCION"]
        df["PRECIO UNITARIO"] = df.apply(
            lambda row: row["NETO"] / row["CANTIDAD"] if row["CANTIDAD"] else 0, axis=1
        )

    else:
        # Mostrar detalle línea a línea
        columnas = ["DESCRIPCION", "CANTIDAD", "NETO"]
        if not all(col in df_filtrado.columns for col in columnas):
            return []

        df = df_filtrado[columnas].copy()
        df["PRODUCTO"] = df["DESCRIPCION"]
        df["CANTIDAD"] = df["CANTIDAD"].astype(float)
        df["NETO"] = df["NETO"].astype(float)
        df["PRECIO UNITARIO"] = df.apply(
            lambda row: row["NETO"] / row["CANTIDAD"] if row["CANTIDAD"] else 0, axis=1
        )

    # Armar tabla final
    df = df[["PRODUCTO", "CANTIDAD", "NETO", "PRECIO UNITARIO"]]

    total_row = {
        "PRODUCTO": "TOTAL",
        "CANTIDAD": df["CANTIDAD"].sum(),
        "NETO": df["NETO"].sum(),
        "PRECIO UNITARIO": ""
    }

    df.loc[len(df)] = total_row
    return df
