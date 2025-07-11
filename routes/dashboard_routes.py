from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from utils.sheet_cache import obtener_datos, forzar_actualizacion, obtener_fecha_actualizacion
from utils.filters import filtrar_dataframe
from utils.auth import login_requerido  # ← importar el decorador


dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route("/dashboard")
@login_requerido
def dashboard():
    if "usuario" not in session:
        return redirect(url_for("auth.login"))
    
    fecha_actualizacion = obtener_fecha_actualizacion("comercial")

    return render_template("dashboard.html", 
                           usuario=session["usuario"],
                           fecha_actualizacion=fecha_actualizacion)


@dashboard_bp.route("/refresh")
@login_requerido
def refrescar_datos():
    from utils.sheet_cache import URLS, forzar_actualizacion
    for nombre in URLS.keys():
        forzar_actualizacion(nombre)
    return redirect(request.referrer or url_for("dashboard.dashboard"))

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
    )

    detalle_por_familia = {}
    for _, row in df_filtrado.iterrows():
        familia = row["FAMILIA"]
        producto = {
            "descripcion": row["DESCRIPCION"],
            "neto": row["NETO"],
            "cantidad": row["CANTIDAD"]
        }
        if familia not in detalle_por_familia:
            detalle_por_familia[familia] = []
        detalle_por_familia[familia].append(producto)

    torta_data = [
        {"nombre": row["FAMILIA"], "valor": int(row["NETO"])}
        for _, row in ventas_por_familia.iterrows()
    ]
    total_neto = int(df_filtrado["NETO"].sum())

    return jsonify({
        "ventas_por_familia": torta_data,
        "detalle_por_familia": detalle_por_familia,
        "ventas_familia_raw": ventas_por_familia.to_dict(orient="records"),
        "total_neto": total_neto
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

