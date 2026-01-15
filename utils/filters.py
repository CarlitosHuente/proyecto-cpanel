import pandas as pd

def filtrar_dataframe(df, tipo, valor, sucursal, semana, año, desde, hasta):
    df = df.copy()

    #print("=== FILTROS APLICADOS ===")
    #print({
    #    "tipo": tipo,
    #    "valor": valor,
    #    "sucursal": sucursal,
    #    "semana": semana,
    #    "año": año,
    #    "desde": desde,
    #    "hasta": hasta
    #})

    # Asegurar que FECHA sea datetime
    if "FECHA" in df.columns:
        df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")

    # Filtro por tipo
    if tipo == "FAMILIA" and valor != "TODOS":
        df = df[df["FAMILIA"] == valor]
    elif tipo == "DESCRIPCION" and valor != "TODOS":
        df = df[df["DESCRIPCION"] == valor]

    # Filtro por sucursal
    if sucursal and sucursal != "TODAS":
        df = df[df["SUCURSAL"] == sucursal]

    # Filtro por rango de fechas
    if desde and hasta:
        try:
            desde_dt = pd.to_datetime(desde, errors="coerce")
            hasta_dt = pd.to_datetime(hasta, errors="coerce")
            #print(f"➡️ Aplicando filtro de fechas desde {desde_dt.date()} hasta {hasta_dt.date()}")
            df = df[(df["FECHA"] >= desde_dt) & (df["FECHA"] <= hasta_dt)]
        except Exception as e:
            #print("⚠️ Error al convertir fechas:", e)
            return pd.DataFrame()
    
    # Solo aplicar semana y año si NO hay filtro por fechas
    elif semana and año:
        try:
           # print(f"➡️ Aplicando filtro por semana {semana} y año {año}")
            df = df[(df["SEMANA"] == int(semana)) & (df["AÑO"] == int(año))]
        except Exception as e:
            #print("⚠️ Error en filtro por semana/año:", e)
            return pd.DataFrame()

   # print(f"✅ Filas después de filtrar: {len(df)}")
    return df
