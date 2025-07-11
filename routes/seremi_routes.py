# routes/seremi_routes.py
from flask import Blueprint, render_template, request
from utils.sheet_cache import obtener_datos
from services.resumen_service import MESES as NOMBRES_MESES
from datetime import datetime
from collections import defaultdict
import pandas as pd
from utils.sheet_cache import obtener_fecha_actualizacion
from utils.auth import login_requerido


seremi_bp = Blueprint("seremi", __name__, url_prefix="/seremi")

@seremi_bp.route("/temperatura_equipos")
@login_requerido
def temperatura_equipos():
    df = obtener_datos("temperatura_equipos")

    # Cargar info de equipos
    df_equipos = obtener_datos("equipos_info")
    df_equipos.columns = df_equipos.columns.str.strip().str.upper()
    mapa_nombre = dict(zip(df_equipos["ID_EQUIPO"], df_equipos["NOMBRE_EQUIPO"]))

    # Normalizar datos de temperatura
    df.columns = df.columns.str.strip().str.upper()
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"])
    df["DIA"] = df["FECHA"].dt.day
    df["MES"] = df["FECHA"].dt.month
    df["AÑO"] = df["FECHA"].dt.year

    # Filtros
    sucursal = request.args.get("sucursal", default="TODAS")
    mes = int(request.args.get("mes", default=datetime.now().month))

    if sucursal != "TODAS":
        df = df[df["SUCURSAL"] == sucursal]

    df = df[df["MES"] == mes]

    # Agrupación por equipo con nombre + código
    equipos = defaultdict(list)
    for cod_equipo, grupo in df.groupby("EQUIPO"):
        nombre_equipo = mapa_nombre.get(cod_equipo, cod_equipo)
        nombre_mostrado = f"{nombre_equipo} ({cod_equipo})"

        grupo = grupo.sort_values("FECHA")

        for dia in range(1, 32):
            registros_dia = grupo[grupo["DIA"] == dia]

            temps = [
                f"{row['TEMPERATURA C°']}°C ({row['FECHA'].strftime('%H:%M')})"
                for _, row in registros_dia.iterrows()
            ]

            while len(temps) < 3:
                temps.append("")

            equipos[nombre_mostrado].append((dia, temps[:3]))

    # Sucursales
    sucursales = sorted(df["SUCURSAL"].dropna().unique().tolist())
    sucursales.insert(0, "TODAS")

    # Meses
    meses = [(i+1, nombre.title()) for i, nombre in enumerate(NOMBRES_MESES)]

    return render_template("seremi/temperatura_equipos.html",
                           equipos=equipos,
                           sucursales=sucursales,
                           sucursal_activa=sucursal,
                           meses=meses,
                           mes_actual=mes,
                           fecha_actualizacion=obtener_fecha_actualizacion("temperatura_equipos"))


@seremi_bp.route("/temperatura_productos")
@login_requerido
def temperatura_productos():
    return render_template("seremi/temperatura_productos.html")

@seremi_bp.route("/cambio_aceite")
@login_requerido
def cambio_aceite():
    return render_template("seremi/cambio_aceite.html")

@seremi_bp.route("/mantenciones")
@login_requerido
def mantenciones():
    return render_template("seremi/mantenciones.html")

@seremi_bp.route("/personal")
@login_requerido
def personal():
    return render_template("seremi/personal.html")

@seremi_bp.route("/temperatura_equipos/print")
@login_requerido
def imprimir_temperatura_equipos():
    df = obtener_datos("temperatura_equipos")
    df_equipos = obtener_datos("equipos_info")
    df_equipos.columns = df_equipos.columns.str.strip().str.upper()
    mapa_nombre = dict(zip(df_equipos["ID_EQUIPO"], df_equipos["NOMBRE_EQUIPO"]))

    df.columns = df.columns.str.strip().str.upper()
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"])
    df["DIA"] = df["FECHA"].dt.day
    df["MES"] = df["FECHA"].dt.month
    df["AÑO"] = df["FECHA"].dt.year

    sucursal = request.args.get("sucursal", default="TODAS")
    mes = int(request.args.get("mes", default=datetime.now().month))

    if sucursal != "TODAS":
        df = df[df["SUCURSAL"] == sucursal]
    df = df[df["MES"] == mes]

    equipos_data = []
    for cod_equipo, grupo in df.groupby("EQUIPO"):
        nombre_equipo = mapa_nombre.get(cod_equipo, cod_equipo)
        nombre_mostrado = f"{nombre_equipo} ({cod_equipo})"
        registros = []

        for dia in range(1, 32):
            registros_dia = grupo[grupo["DIA"] == dia]

            temps = []
            responsables = []
            for _, row in registros_dia.iterrows():
                temp_hora = f"{row['TEMPERATURA C°']}°C ({row['FECHA'].strftime('%H:%M')})"
                responsable = str(row.get("RESPONSABLE", "")).strip()
                temps.append(temp_hora)
                responsables.append(responsable if responsable else "-")

            # Completar si faltan
            while len(temps) < 3:
                temps.append("")
                responsables.append("-")

            registros.append({
                "dia": f"{dia:02d}",
                "ingreso": temps[0],
                "intermedio": temps[1],
                "salida": temps[2],
                "responsables": " / ".join(responsables[:3])
            })

        equipos_data.append({
            "nombre": nombre_mostrado,
            "sucursal": sucursal,
            "mes": mes,
            "registros": registros
        })

    return render_template("seremi/print_temperatura.html", equipos=equipos_data)
