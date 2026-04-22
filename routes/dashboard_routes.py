from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from utils.sheet_cache import obtener_datos, forzar_actualizacion, obtener_fecha_actualizacion
from utils.filters import filtrar_dataframe
from utils.auth import login_requerido, permiso_modulo # ← importar el decorador
import pandas as pd



dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route("/dashboard")
@login_requerido
@permiso_modulo("ventas")
def dashboard():
    if "usuario" not in session:
        return redirect(url_for("auth.login"))
    
    fecha_actualizacion = obtener_fecha_actualizacion("comercial")

    return render_template("dashboard.html", 
                           usuario=session["usuario"],
                           fecha_actualizacion=fecha_actualizacion)

# ===========================
# RUTAS PARA CARGA DINÁMICA
# ===========================

@dashboard_bp.route("/api/sucursales")
@login_requerido
def api_sucursales():
    empresa = request.args.get("empresa", "comercial")
    df = obtener_datos(empresa)
    sucursales = sorted(df["SUCURSAL"].dropna().unique().tolist())
    return jsonify(sucursales)


@dashboard_bp.route("/api/dashboard-data")
@login_requerido
def api_dashboard_data():
    empresa = request.args.get("empresa", "comercial")
    sucursal = request.args.get("sucursal")
    semana = request.args.get("semana")
    año = request.args.get("año")
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    familia = request.args.get("familia")

    df = obtener_datos(empresa)

    df_filtrado = filtrar_dataframe(
        df,
        tipo="FAMILIA",
        valor=familia or "TODOS",
        sucursal=sucursal,
        semana=semana,
        año=año,
        desde=desde,
        hasta=hasta
    )

    # Para gráfico de torta
    ventas_por_familia = (
        df_filtrado.groupby("FAMILIA")["NETO"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    ) if not df_filtrado.empty else pd.DataFrame(columns=["FAMILIA", "NETO"])

    detalle_por_familia = {}
    if not df_filtrado.empty:
        for _, row in df_filtrado.iterrows():
            familia_item = str(row["FAMILIA"]) if pd.notna(row["FAMILIA"]) else "SIN FAMILIA"
            producto = {
                "descripcion": str(row["DESCRIPCION"]),
                "neto": float(row["NETO"]) if pd.notna(row["NETO"]) else 0,
                "cantidad": float(row["CANTIDAD"]) if pd.notna(row["CANTIDAD"]) else 0
            }
            if familia_item not in detalle_por_familia:
                detalle_por_familia[familia_item] = []
            detalle_por_familia[familia_item].append(producto)

    torta_data = [
        {"nombre": str(row["FAMILIA"]) if pd.notna(row["FAMILIA"]) else "SIN FAMILIA", "valor": int(row["NETO"])}
        for _, row in ventas_por_familia.iterrows()
    ]
    total_neto = int(df_filtrado["NETO"].sum()) if not df_filtrado.empty else 0
    cantidad_total = int(df_filtrado["CANTIDAD"].sum()) if not df_filtrado.empty else 0

    # =========================================================
    # NUEVA LÓGICA: COMPARATIVO Y TENDENCIA AÑO CONTRA AÑO
    # =========================================================
    total_neto_anterior = 0
    cantidad_anterior = 0
    df_ant = pd.DataFrame()
    etiqueta_anterior = "Año Anterior"
    etiqueta_actual = "Año Actual"
    año_referencia = None
    
    try:
        if desde and hasta:
            desde_dt = pd.to_datetime(desde)
            hasta_dt = pd.to_datetime(hasta)
            año_referencia = desde_dt.year
            # Restamos 364 días (52 semanas exactas) para alinear días de la semana
            desde_ant = (desde_dt - pd.Timedelta(days=364)).strftime("%Y-%m-%d")
            hasta_ant = (hasta_dt - pd.Timedelta(days=364)).strftime("%Y-%m-%d")
            
            df_ant = filtrar_dataframe(df, tipo="FAMILIA", valor=familia or "TODOS", sucursal=sucursal, semana=None, año=None, desde=desde_ant, hasta=hasta_ant)
            total_neto_anterior = int(df_ant["NETO"].sum()) if not df_ant.empty else 0
            cantidad_anterior = int(df_ant["CANTIDAD"].sum()) if not df_ant.empty else 0
            
            etiqueta_actual = f"{desde_dt.strftime('%d/%m/%y')} - {hasta_dt.strftime('%d/%m/%y')}"
            etiqueta_anterior = f"{pd.to_datetime(desde_ant).strftime('%d/%m/%y')} - {pd.to_datetime(hasta_ant).strftime('%d/%m/%y')}"
            
        elif año and semana:
            año_referencia = int(año)
            año_ant_str = str(año_referencia - 1)
            df_ant = filtrar_dataframe(df, tipo="FAMILIA", valor=familia or "TODOS", sucursal=sucursal, semana=semana, año=año_ant_str, desde=None, hasta=None)
            total_neto_anterior = int(df_ant["NETO"].sum()) if not df_ant.empty else 0
            cantidad_anterior = int(df_ant["CANTIDAD"].sum()) if not df_ant.empty else 0
            
            etiqueta_actual = f"Sem {semana} ({año})"
            etiqueta_anterior = f"Sem {semana} ({año_ant_str})"
            
        elif año:
            año_referencia = int(año)
            año_ant_str = str(año_referencia - 1)
            df_ant = filtrar_dataframe(df, tipo="FAMILIA", valor=familia or "TODOS", sucursal=sucursal, semana=None, año=año_ant_str, desde=None, hasta=None)
            total_neto_anterior = int(df_ant["NETO"].sum()) if not df_ant.empty else 0
            cantidad_anterior = int(df_ant["CANTIDAD"].sum()) if not df_ant.empty else 0
            
            etiqueta_actual = f"Año {año}"
            etiqueta_anterior = f"Año {año_ant_str}"
    except Exception as e:
        print(f"Error calculando periodo anterior: {e}")

    if not año_referencia:
        año_referencia = pd.Timestamp.now().year
    año_ant = año_referencia - 1

    tendencia_actual = [0]*12
    tendencia_anterior = [0]*12
    meses_abrev = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    
    try:
        df_hist = filtrar_dataframe(df, tipo="FAMILIA", valor=familia or "TODOS", sucursal=sucursal, semana=None, año=None, desde=None, hasta=None).copy()
        if not df_hist.empty and "FECHA" in df_hist.columns:
            df_hist["FECHA_DT"] = pd.to_datetime(df_hist["FECHA"], errors="coerce")
            df_hist_valid = df_hist.dropna(subset=["FECHA_DT"]).copy()
            df_hist_valid["MES"] = df_hist_valid["FECHA_DT"].dt.month
            df_hist_valid["AÑO_DT"] = df_hist_valid["FECHA_DT"].dt.year
            grouped = df_hist_valid.groupby(["AÑO_DT", "MES"])["NETO"].sum().reset_index()
            for mes in range(1, 13):
                tendencia_actual[mes - 1] = int(grouped[(grouped["AÑO_DT"] == año_referencia) & (grouped["MES"] == mes)]["NETO"].sum())
                tendencia_anterior[mes - 1] = int(grouped[(grouped["AÑO_DT"] == año_ant) & (grouped["MES"] == mes)]["NETO"].sum())
    except Exception as e:
        print(f"Error calculando tendencia: {e}")

    # =========================================================
    # NUEVOS CÁLCULOS: EMPANADAS, TICKET PROMEDIO, HISTÓRICOS
    # =========================================================
    empanadas_actual = int(df_filtrado[df_filtrado["FAMILIA"].astype(str).str.contains("EMPANADA", case=False, na=False)]["CANTIDAD"].sum()) if not df_filtrado.empty else 0
    empanadas_anterior = int(df_ant[df_ant["FAMILIA"].astype(str).str.contains("EMPANADA", case=False, na=False)]["CANTIDAD"].sum()) if not df_ant.empty else 0

    ticket_promedio_actual = 0
    ticket_promedio_anterior = 0
    if empresa == "agricola":
        if not df_filtrado.empty and "N_BOLETA" in df_filtrado.columns:
            boletas_actual = df_filtrado.groupby("N_BOLETA")["NETO"].sum()
            ticket_promedio_actual = int(boletas_actual.mean()) if not boletas_actual.empty else 0
            
        if not df_ant.empty and "N_BOLETA" in df_ant.columns:
            boletas_anterior = df_ant.groupby("N_BOLETA")["NETO"].sum()
            ticket_promedio_anterior = int(boletas_anterior.mean()) if not boletas_anterior.empty else 0

    semana_consultada = int(semana) if semana else pd.Timestamp.now().isocalendar()[1]
    rango_semanas = list(range(max(1, semana_consultada - 7), min(54, semana_consultada + 8)))
    
    tendencia_semanal = {"etiquetas": [f"Sem {s}" for s in rango_semanas], "actual": [0]*len(rango_semanas), "anterior": [0]*len(rango_semanas)}
    historico_semanal = {"años": [], "datos": []}

    try:
        if not df_hist.empty and "AÑO" in df_hist.columns and "SEMANA" in df_hist.columns:
            ventas_por_semana = df_hist.groupby(["AÑO", "SEMANA"])["NETO"].sum().reset_index()
            
            for i, sem in enumerate(rango_semanas):
                tendencia_semanal["actual"][i] = int(ventas_por_semana[(ventas_por_semana["AÑO"] == año_referencia) & (ventas_por_semana["SEMANA"] == sem)]["NETO"].sum())
                tendencia_semanal["anterior"][i] = int(ventas_por_semana[(ventas_por_semana["AÑO"] == año_ant) & (ventas_por_semana["SEMANA"] == sem)]["NETO"].sum())

            años_disponibles = sorted(df_hist["AÑO"].dropna().unique().astype(int).tolist())
            historico_semanal["años"] = [str(a) for a in años_disponibles]
            
            for sem in range(1, 54):
                fila = {"semana": sem}
                for anio in años_disponibles:
                    fila[str(anio)] = int(ventas_por_semana[(ventas_por_semana["SEMANA"] == sem) & (ventas_por_semana["AÑO"] == anio)]["NETO"].sum())
                historico_semanal["datos"].append(fila)
    except Exception as e:
        print(f"Error calculando tendencia/histórico semanal: {e}")

    # =========================================================
    # ANÁLISIS AVANZADO: SUCURSALES Y TOP/BOTTOM PRODUCTOS
    # =========================================================
    ranking_sucursales = []
    top_estrellas = []
    top_alertas = []

    if empresa == "agricola":
        # Para agrícola, mostrar las últimas 5 semanas en lugar de sucursales
        if not df.empty and "FECHA" in df.columns:
            if not df_filtrado.empty and "FECHA" in df_filtrado.columns:
                fecha_ref = df_filtrado["FECHA"].max()
            elif hasta:
                fecha_ref = pd.to_datetime(hasta, errors="coerce")
            else:
                fecha_ref = pd.Timestamp.now()
            
            if pd.notna(fecha_ref):
                df_hist = df[df["FECHA"] <= fecha_ref].copy()
                if not df_hist.empty and "AÑO" in df_hist.columns and "SEMANA" in df_hist.columns:
                    df_hist = df_hist.dropna(subset=["AÑO", "SEMANA"])
                    df_hist["YW"] = df_hist["AÑO"].astype(int).astype(str) + "-" + df_hist["SEMANA"].astype(int).astype(str).str.zfill(2)
                    rank_df = df_hist.groupby("YW").agg({"NETO": "sum", "SEMANA": "first", "AÑO": "first"}).sort_index(ascending=False).head(5)
                    rank_df = rank_df.sort_index(ascending=True)
                    ranking_sucursales = [{"sucursal": f"Sem {int(row['SEMANA'])} ({int(row['AÑO'])})", "neto": int(row["NETO"])} for _, row in rank_df.iterrows()]
    elif not df_filtrado.empty:
        if not sucursal or sucursal == "TODAS":
            rank_df = df_filtrado.groupby("SUCURSAL")["NETO"].sum().sort_values(ascending=True)
            ranking_sucursales = [{"sucursal": str(k), "neto": int(v)} for k, v in rank_df.items()]

    if not df_filtrado.empty:
        if not df_ant.empty:
            curr_prod = df_filtrado.groupby("DESCRIPCION").agg({"NETO": "sum", "CANTIDAD": "sum"}).reset_index().rename(columns={"NETO": "neto_actual", "CANTIDAD": "cantidad_actual"})
            prev_prod = df_ant.groupby("DESCRIPCION").agg({"NETO": "sum", "CANTIDAD": "sum"}).reset_index().rename(columns={"NETO": "neto_anterior", "CANTIDAD": "cantidad_anterior"})
            merged = pd.merge(curr_prod, prev_prod, on="DESCRIPCION", how="outer").fillna(0)
            merged["variacion"] = merged["neto_actual"] - merged["neto_anterior"]
            
            # Top 5 Crecimientos (Variación positiva)
            estrellas = merged.sort_values(by="variacion", ascending=False).head(5)
            estrellas = estrellas[estrellas["variacion"] > 0]
            top_estrellas = estrellas.to_dict(orient="records")
            
            # Top 5 Caídas (Variación negativa)
            alertas = merged.sort_values(by="variacion", ascending=True).head(5)
            alertas = alertas[alertas["variacion"] < 0]
            top_alertas = alertas.to_dict(orient="records")
            
            # Top 10 por Cantidad Vendida para el Carrusel
            top_qty = merged.sort_values(by="cantidad_actual", ascending=False).head(10)
            top_productos_cantidad = top_qty[["DESCRIPCION", "cantidad_actual", "cantidad_anterior"]].to_dict(orient="records")
        else:
            # Si no hay año anterior, solo mostramos los más vendidos
            curr_prod = df_filtrado.groupby("DESCRIPCION").agg({"NETO": "sum", "CANTIDAD": "sum"}).sort_values(by="NETO", ascending=False).reset_index().rename(columns={"NETO": "neto_actual", "CANTIDAD": "cantidad_actual"})
            top_estrellas = [{"DESCRIPCION": str(row["DESCRIPCION"]), "neto_actual": float(row["neto_actual"]), "variacion": 0} for _, row in curr_prod.head(5).iterrows()]
            
            top_qty = curr_prod.sort_values(by="cantidad_actual", ascending=False).head(10)
            top_productos_cantidad = [{"DESCRIPCION": str(row["DESCRIPCION"]), "cantidad_actual": float(row["cantidad_actual"]), "cantidad_anterior": 0} for _, row in top_qty.iterrows()]


    return jsonify({
        "ventas_por_familia": torta_data,
        "detalle_por_familia": detalle_por_familia,
        "ventas_familia_raw": ventas_por_familia.to_dict(orient="records") if not ventas_por_familia.empty else [],
        "total_neto": total_neto,
        "kpis": {
            "neto_actual": total_neto, "neto_anterior": total_neto_anterior,
            "cantidad_actual": cantidad_total, "cantidad_anterior": cantidad_anterior,
            "empanadas_actual": empanadas_actual, "empanadas_anterior": empanadas_anterior,
            "ticket_promedio_actual": ticket_promedio_actual, "ticket_promedio_anterior": ticket_promedio_anterior,
            "top_productos_cantidad": top_productos_cantidad
        },
        "analisis_avanzado": {
            "ranking_sucursales": ranking_sucursales,
            "estrellas": top_estrellas,
            "alertas": top_alertas
        },
        "comparativo_periodo": {
            "etiquetas": [etiqueta_anterior, etiqueta_actual],
            "valores": [total_neto_anterior, total_neto]
        },
        "tendencia": {
            "etiquetas": meses_abrev,
            "actual": tendencia_actual,
            "anterior": tendencia_anterior
        },
        "tendencia_semanal": tendencia_semanal,
        "historico_semanal": historico_semanal
    })


@dashboard_bp.route("/api/dashboard-productos")
@login_requerido
def api_dashboard_productos():
    empresa = request.args.get("empresa", "comercial")
    sucursal = request.args.get("sucursal")
    semana = request.args.get("semana")
    año = request.args.get("año")
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    familia = request.args.get("familia")

    df = obtener_datos(empresa)

    df_filtrado = filtrar_dataframe(
        df,
        tipo="FAMILIA",
        valor=familia or "TODOS",
        sucursal=sucursal,
        semana=semana,
        año=año,
        desde=desde,
        hasta=hasta
    )

    productos = (
        df_filtrado.groupby("DESCRIPCION")
        .agg({"NETO": "sum", "CANTIDAD": "sum"})
        .sort_values(by="NETO", ascending=False)
        .reset_index()
    )

    data = [
        {
            "descripcion": row["DESCRIPCION"],
            "neto": int(row["NETO"]),
            "cantidad": int(row["CANTIDAD"])
        }
        for _, row in productos.iterrows()
    ]
    return jsonify(data)

# ... (al final de dashboard_routes.py)

@dashboard_bp.route("/api/latest-date-info")
@login_requerido
def api_latest_date_info():
    empresa = request.args.get("empresa", "comercial")
    try:
        df = obtener_datos(empresa)
        if not df.empty and "FECHA" in df.columns:
            fecha_mas_reciente = df["FECHA"].max()
            año = fecha_mas_reciente.year
            semana = fecha_mas_reciente.isocalendar().week
            return jsonify({"año": año, "semana": semana})
    except Exception as e:
        #print(f"Error obteniendo la última fecha: {e}")
        # Devolver valores por defecto en caso de error
        from datetime import datetime
        hoy = datetime.now()
        return jsonify({"año": hoy.year, "semana": hoy.isocalendar().week})