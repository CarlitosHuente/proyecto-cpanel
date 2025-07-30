import pandas as pd
from datetime import timedelta

def obtener_detalle_por_dia(df, filtros):
    """
    Prepara los datos para la pestaña "Detalle por Día".
    Maneja 4 escenarios basados en los filtros de día y fecha/semana.
    """
    dia_semana_filtro = filtros.get("dia_semana", "TODOS")
    campo_agrupacion = filtros.get("filtro_por", "FAMILIA")

    # Aseguramos que la columna de fecha sea datetime
    df['FECHA'] = pd.to_datetime(df['FECHA'])
    # Lunes=1, Martes=2, ..., Domingo=7
    df['DIA_SEMANA'] = df['FECHA'].dt.isocalendar().day.astype(str)

    # ----- Escenario 1 y 2: Vista por Días de la Semana -----
    if dia_semana_filtro == "TODOS":
        dias_semana_cols = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        
        # Agrupamos por el campo principal y el día de la semana, sumando cantidades
        pivot_df = df.pivot_table(
            index=campo_agrupacion,
            columns='DIA_SEMANA',
            values='CANTIDAD',
            aggfunc='sum',
            fill_value=0
        )

        # Si se usa un rango de fechas, calculamos promedios
        if filtros.get("desde") and filtros.get("hasta"):
            titulo = f"Promedio de Ventas por Día de la Semana"
            try:
                desde = pd.to_datetime(filtros["desde"])
                hasta = pd.to_datetime(filtros["hasta"])
                # Calculamos el número de semanas en el rango
                num_semanas = (hasta - desde).days / 7
                if num_semanas > 0:
                    pivot_df = pivot_df / num_semanas
            except Exception:
                # Si hay error en las fechas, simplemente mostramos la suma
                pass
        else:
            titulo = f"Total de Ventas por Día de la Semana"
        
        # Formatear y preparar salida
        pivot_df = pivot_df.round(0).astype(int)
        # Asegurarse que todas las columnas de días de la semana existan
        for i, dia in enumerate(dias_semana_cols, 1):
            if str(i) not in pivot_df.columns:
                pivot_df[str(i)] = 0
        
        # Ordenar columnas por día de la semana
        pivot_df = pivot_df[[str(i) for i in range(1, 8)]]
        pivot_df.columns = dias_semana_cols # Renombrar columnas

        return {
            "titulo": titulo,
            "columnas": dias_semana_cols,
            "tabla": pivot_df.reset_index().to_dict(orient="records"),
            "tipo_vista": "dias_semana"
        }

    # ----- Escenario 3 y 4: Vista Histórica para un Día Específico -----
    # ----- REEMPLAZA ESTE BLOQUE ELSE COMPLETO -----
    else:
        df_dia_especifico = df[df['DIA_SEMANA'] == dia_semana_filtro]
        
        # Escenario con rango de fechas: mostrar cada fecha
        if filtros.get("desde") and filtros.get("hasta"):
            dias_semana_nombres = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
            nombre_dia = dias_semana_nombres[int(dia_semana_filtro) - 1]
            titulo = f"Historial de Ventas para los días {nombre_dia}"
            
            if df_dia_especifico.empty:
                 return {"titulo": titulo, "columnas": [], "tabla": [], "tipo_vista": "fechas"}

            pivot_df = df_dia_especifico.pivot_table(
                index=campo_agrupacion,
                columns='FECHA',
                values='CANTIDAD',
                aggfunc='sum',
                fill_value=0
            ).round(0).astype(int)

            columnas_dt = sorted(pivot_df.columns)
            pivot_df = pivot_df[columnas_dt]
            
            # --- INICIO DE LA CORRECCIÓN ---
            # Convertimos las columnas de fecha a texto ANTES de enviar los datos
            columnas_str = [d.strftime('%d-%m-%Y') for d in columnas_dt]
            pivot_df.columns = columnas_str
            # --- FIN DE LA CORRECCIÓN ---

            return {
                "titulo": titulo,
                "columnas": columnas_str,
                "tabla": pivot_df.reset_index().to_dict(orient="records"),
                "tipo_vista": "fechas"
            }
        
        # Escenario con semana
        else:
            semana = filtros.get("semana", "N/A")
            año = filtros.get("año", "N/A")
            titulo = f"Ventas para el día seleccionado en la Semana {semana} ({año})"

            if df_dia_especifico.empty:
                 return {"titulo": titulo, "columnas": [], "tabla": [], "tipo_vista": "fechas"}
            
            pivot_df = df_dia_especifico.pivot_table(
                index=campo_agrupacion,
                columns='FECHA',
                values='CANTIDAD',
                aggfunc='sum',
                fill_value=0
            ).round(0).astype(int)

            columnas_dt = sorted(pivot_df.columns)
            
            # --- INICIO DE LA CORRECCIÓN ---
            columnas_str = [d.strftime('%d-%m-%Y') for d in columnas_dt]
            pivot_df.columns = columnas_str
            # --- FIN DE LA CORRECCIÓN ---
            
            return {
                "titulo": titulo,
                "columnas": columnas_str,
                "tabla": pivot_df.reset_index().to_dict(orient="records"),
                "tipo_vista": "fechas"
            }

    return {"tabla": [], "columnas": [], "titulo": "Seleccione filtros para ver datos"}