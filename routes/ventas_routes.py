from flask import Blueprint, render_template, request
from utils.sheet_cache import obtener_datos
from utils.filters import filtrar_dataframe
from services.resumen_service import obtener_resumen_mensual
from services.detalle_service import obtener_detalle
import pandas as pd

ventas_bp = Blueprint("ventas", __name__)

@ventas_bp.route("/ventas", methods=["GET"])
@ventas_bp.route("/ventas", methods=["GET"])
def ventas():
    empresa = request.args.get("empresa", "comercial")
    df = obtener_datos(empresa)

    # Obtener campos del formulario
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    año_actual = request.args.get("año")
    semana_actual = request.args.get("semana")

    # Si no hay fechas, aplicar semana automática solo si no se recibe por GET
    if not desde and not hasta:
        if not semana_actual:
            if año_actual:
                semana_actual = df[df["AÑO"] == int(año_actual)]["SEMANA"].max()
            else:
                año_actual = df["AÑO"].max()
                semana_actual = df[df["AÑO"] == año_actual]["SEMANA"].max()
        else:
            semana_actual = int(semana_actual)
    else:
        # Si hay fechas, ignorar semana/año
        semana_actual = None
        año_actual = None

    # Filtros
    filtros = {
        "empresa": empresa,
        "sucursal": request.args.get("sucursal"),
        "semana": semana_actual,
        "año": año_actual,
        "desde": desde,
        "hasta": hasta,
        "filtro_por": request.args.get("filtro_por", "FAMILIA"),
        "valor": request.args.get("valor", "TODOS")
    }

    # Aplicar filtros al DataFrame
# Aplica lógica de control para evitar conflicto entre fechas y semana
    if filtros["desde"] and filtros["hasta"]:
        semana = None
        año = None
    else:
        semana = filtros["semana"]
        año = filtros["año"]

    detalle_df = filtrar_dataframe(
        df,
        filtros["filtro_por"],
        filtros["valor"],
        filtros["sucursal"],
        semana,
        año,
        filtros["desde"],
        filtros["hasta"]
    )

    import pprint
    print("=== FILTROS APLICADOS ===")
    pprint.pprint(filtros)

    # Antes de aplicar el filtro
    print("=== DATAFRAME ORIGINAL ===")
    print(df.head())


    # Aplicar filtros con debug
    detalle_df = filtrar_dataframe(
        df,
        filtros["filtro_por"],
        filtros["valor"],
        filtros["sucursal"],
        semana,
        año,
        filtros["desde"],
        filtros["hasta"]
    )

    print("=== DATAFRAME FILTRADO ===")
    print(detalle_df.head())
    print("Filas encontradas:", len(detalle_df))



    # Generar detalle
    if isinstance(detalle_df, pd.DataFrame) and not detalle_df.empty:
        detalle_df = obtener_detalle(detalle_df, filtros)
        detalle = detalle_df.to_dict(orient="records")
    else:
        detalle = []

    # Generar resumen mensual
    resumen_txt = obtener_resumen_mensual(df, filtros)

    # Select dinámico para valores
    filtro_por = filtros["filtro_por"]
    opciones_valor = []
    if filtro_por in df.columns:
        opciones_valor = sorted(df[filtro_por].dropna().unique())

    # Lista de sucursales
    sucursales = sorted(df["SUCURSAL"].dropna().unique().tolist())
    sucursales.insert(0, "TODAS")

    return render_template("ventas.html",
        detalle=detalle,
        resumen_mensual=resumen_txt,
        filtros=filtros,
        opciones_valor=opciones_valor,
        filtro_por=filtro_por,
        filtro_valor=filtros["valor"],
        sucursal=filtros["sucursal"],
        empresa=empresa,
        sucursales=sucursales
    )

from flask import send_file
import io

@ventas_bp.route("/descargar_excel")
def descargar_excel():
    empresa = request.args.get("empresa", "comercial")
    df = obtener_datos(empresa)

    # Obtener filtros
    sucursal = request.args.get("sucursal")
    semana = request.args.get("semana")
    año = request.args.get("año")
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    # Aplicar filtro
    df_filtrado = filtrar_dataframe(df, tipo="FAMILIA", valor="TODOS",  # tipo/valor no importan aquí
                                     sucursal=sucursal, semana=semana, año=año,
                                     desde=desde, hasta=hasta)

    if df_filtrado.empty:
        return "No hay datos para exportar", 204

    # Guardar en Excel (memoria)
    output = io.BytesIO()
    df_filtrado.to_excel(output, index=False)
    output.seek(0)

    return send_file(output,
                     download_name="ventas_filtradas.xlsx",
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')



