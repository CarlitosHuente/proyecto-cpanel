from flask import Blueprint, render_template, request
from utils.sheet_cache import obtener_datos
from utils.filters import filtrar_dataframe
from services.resumen_service import obtener_resumen_mensual_tabular, MESES
from services.detalle_service import obtener_detalle
import pandas as pd
from utils.utils_excel import aplicar_formato_numerico_excel
from openpyxl import load_workbook
import io
from flask import send_file
from utils.sheet_cache import obtener_fecha_actualizacion
from utils.auth import login_requerido
from services.ventas_por_dia_service import obtener_detalle_por_dia






ventas_bp = Blueprint("ventas", __name__)

#@ventas_bp.route("/ventas", methods=["GET"])
@ventas_bp.route("/ventas", methods=["GET"])
@login_requerido
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
        "valor": request.args.get("valor", "TODOS"),
        "tab": request.args.get("tab", "detalle")  # << ESTA LÍNEA es CLAVE
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
###
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

    # === Lógica para la nueva pestaña "Detalle por Día" ===
    filtros["dia_semana"] = request.args.get("dia_semana", "TODOS")

    # El servicio interno se encargará de filtrar por día de la semana.
    if not detalle_df.empty:
        detalle_dia_data = obtener_detalle_por_dia(detalle_df.copy(), filtros)
    else:
        detalle_dia_data = {"tabla": [], "columnas": [], "titulo": "No hay datos para los filtros seleccionados"}

    # Generar detalle
# Generar detalle agrupado visualmente (sin afectar Excel)
    if isinstance(detalle_df, pd.DataFrame) and not detalle_df.empty:
        detalle_df = obtener_detalle(detalle_df, filtros)

        # Agrupación visual solo para la vista
        # Reemplaza esto en la función ventas() de ventas_routes.py

        # Agrupación visual solo para la vista
        detalle_agrupado = (
            detalle_df.groupby("PRODUCTO", as_index=False)
            .agg(
                CANTIDAD=("CANTIDAD", "sum"),
                NETO=("NETO", "sum")
            )
        )
        # Calculamos el precio unitario de forma segura
        detalle_agrupado["PRECIO_UNITARIO"] = detalle_agrupado.apply(
            lambda row: row["NETO"] / row["CANTIDAD"] if row["CANTIDAD"] != 0 else 0,
            axis=1
        )

        detalle = detalle_agrupado.to_dict(orient="records")
    else:
        detalle = []

    # Generar resumen mensual
    resumen_mensual = obtener_resumen_mensual_tabular(df, filtros)


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
        resumen_mensual=resumen_mensual,
        meses=MESES,
        filtros=filtros,
        opciones_valor=opciones_valor,
        filtro_por=filtro_por,
        filtro_valor=filtros["valor"],
        sucursal=filtros["sucursal"],
        empresa=empresa,
        sucursales=sucursales,
        fecha_actualizacion=obtener_fecha_actualizacion("temperatura_equipos"),
        detalle_dia_data=detalle_dia_data)



@ventas_bp.route("/descargar_excel")
@login_requerido
def descargar_excel():
    empresa = request.args.get("empresa", "comercial")
    df = obtener_datos(empresa)

    sucursal = request.args.get("sucursal")
    semana = request.args.get("semana")
    año = request.args.get("año")
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    filtro_por = request.args.get("filtro_por", "FAMILIA")
    valor = request.args.get("valor", "TODOS")
    tab = request.args.get("tab", "detalle")

    filtros = {
        "empresa": empresa,
        "sucursal": sucursal,
        "semana": semana,
        "año": año,
        "desde": desde,
        "hasta": hasta,
        "filtro_por": filtro_por,
        "valor": valor
    }

    output = io.BytesIO()

    if tab == "detalle":
        df_filtrado = filtrar_dataframe(df, filtro_por, valor, sucursal, semana, año, desde, hasta)
        if df_filtrado.empty:
            return "No hay datos para exportar", 204

        df_filtrado.to_excel(output, index=False)
        output.seek(0)

        # Formatear usando openpyxl
        wb = load_workbook(output)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, min_col=1):
            for cell in row:
                aplicar_formato_numerico_excel(cell)

        output = io.BytesIO()
        wb.save(output)

    elif tab == "resumen":
        resumen = obtener_resumen_mensual_tabular(df, filtros)
        if not resumen or not resumen.get("tabla"):
            return "No hay resumen para exportar", 204

        filas = []
        for item in resumen["tabla"]:
            neto_f = [float(str(v).replace("$", "").replace(".", "").replace(",", ".").strip()) for v in item["neto"]]
            unit_f = [float(str(v).replace("$", "").replace(".", "").replace(",", ".").strip()) for v in item["unit"]]
            cant_f = [int(str(v).replace(".", "").strip()) for v in item["cant"]]

            filas.append(["", item["producto"]] + neto_f + [float(item["total_neto"].replace("$", "").replace(".", "").replace(",", ".").strip())])
            filas.append(["", ""] + cant_f + [int(item["total_cant"].replace(".", "").strip())])
            filas.append(["", ""] + unit_f + [float(item["total_unit"].replace("$", "").replace(".", "").replace(",", ".").strip())])

        encabezados = ["Tipo", "Producto"] + MESES + ["Total"]
        df_export = pd.DataFrame(filas, columns=encabezados)
        df_export.to_excel(output, index=False)
        output.seek(0)

        wb = load_workbook(output)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, min_col=3):  # Desde col C (primer número)
            for cell in row:
                aplicar_formato_numerico_excel(cell)

        output = io.BytesIO()
        wb.save(output)

    output.seek(0)
    return send_file(output,
                     download_name=f"ventas_{tab}.xlsx",
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
