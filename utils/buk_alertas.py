"""
Motor de alertas Buk: sin turno mes, sin marca, atrasos, extras.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

from utils.buk_alertas_revisadas import esta_revisada, ids_revisadas
from utils.buk_asistencia_api import (
    configuracion_resumen,
    listar_recintos,
    listar_registros_recinto,
    listar_turnos_rango,
    normalizar_rut,
)
from utils.buk_calendario import (
    MESES_ES,
    _agregar_marcajes_por_dia,
    _construir_celda,
    _rango_mes,
    _turno_programado,
)
from utils.buk_colacion_config import DIAS_SEMANA, resolver_minutos_colacion
from utils.buk_presencia import listar_todos_vigentes_enriquecidos

UMBRAL_ALERTA_MINUTOS = 60

_ESTADOS_NO_VIGENTE = frozenset({
    "inactivo", "inactive", "terminated", "desvinculado", "pendiente", "pending",
    "finiquitado", "retirado", "desactivado",
})


def _es_vigente_rrhh(emp: dict) -> bool:
    """Solo colaboradores activos en RRHH (employees/active con status operativo)."""
    if not emp:
        return False
    st = (emp.get("status") or "").strip().lower()
    if st in _ESTADOS_NO_VIGENTE:
        return False
    return bool(normalizar_rut(emp.get("rut")) or emp.get("id"))


def _fecha_corte() -> date:
    """Último día evaluable: ayer (no incluye hoy)."""
    return date.today() - timedelta(days=1)


def _eval_hasta(anio: int, mes: int, fin: date, inicio: date) -> date:
    """
    Fecha fin del periodo evaluado.
    Mes en curso: hasta ayer (hoy − 1). Meses pasados: hasta fin de mes.
    """
    corte = _fecha_corte()
    if (anio, mes) == (corte.year, corte.month) or (anio, mes) == (date.today().year, date.today().month):
        if corte < inicio:
            return inicio - timedelta(days=1)
        return min(fin, corte)
    if (anio, mes) < (corte.year, corte.month):
        return fin
    return inicio - timedelta(days=1)


def alerta_id(
    tipo: str,
    rut_norm: str,
    *,
    fecha: Optional[date] = None,
    obra_id: str = "",
    mes_key: str = "",
) -> str:
    f = mes_key or (fecha.isoformat() if isinstance(fecha, date) else "")
    return f"{tipo}|{rut_norm or ''}|{f}|{obra_id or ''}"


def _turno_cuenta_asignacion(t: dict) -> bool:
    """Al menos una fila de asignación en el mes (cualquier sucursal, incl. licencia/permiso)."""
    if not (t.get("rut_norm") and t.get("fecha")):
        return False
    if t.get("licencia") or t.get("permiso") or t.get("vacaciones"):
        return True
    return bool((t.get("horario_turno") or "").strip())


def _mes_label(anio: int, mes: int) -> str:
    return f"{MESES_ES[mes - 1].capitalize()} {anio}"


def _resumen_turnos_rut(turnos_rut: List[dict]) -> str:
    """Días con turno y patrón Lun–Dom (informativo; no exige cobertura total del mes)."""
    dias = sorted({t["fecha"] for t in turnos_rut if isinstance(t.get("fecha"), date)})
    if not dias:
        return ""
    wd = sorted({d.weekday() for d in dias})
    nombres = [DIAS_SEMANA[w] for w in wd]
    if len(wd) == 1:
        pat = nombres[0]
    elif wd == list(range(wd[0], wd[-1] + 1)):
        pat = f"{nombres[0]}–{nombres[-1]}"
    else:
        pat = ", ".join(nombres)
    return f"{len(dias)} día(s) asignados ({pat})"


def _consolidar_sin_marca(items: List[dict]) -> List[dict]:
    """Una fila por persona+día aunque tenga turno en varias sucursales."""
    merged: Dict[Tuple[str, str], dict] = {}
    for it in items:
        key = (it.get("rut_norm") or "", it.get("fecha") or "")
        if key not in merged:
            entry = dict(it)
            entry["_obras"] = [it.get("obra_nombre") or ""]
            merged[key] = entry
        else:
            m = merged[key]
            ob = it.get("obra_nombre") or ""
            if ob and ob not in m["_obras"]:
                m["_obras"].append(ob)
    out: List[dict] = []
    for m in merged.values():
        obras = [o for o in m.pop("_obras", []) if o]
        if len(obras) > 1:
            m["obra_nombre"] = ", ".join(obras)
            m["detalle"] = f"Turno sin marcaje de entrada ({len(obras)} sucursales: {', '.join(obras)})."
        elif obras:
            m["obra_nombre"] = obras[0]
        m["obra_id"] = ""
        dia = m.get("fecha")
        fd = date.fromisoformat(dia) if dia else None
        m["id"] = alerta_id("sin_marca", m.get("rut_norm") or "", fecha=fd, obra_id="")
        out.append(m)
    return out


def _item_alerta(
    *,
    tipo: str,
    rut_norm: str,
    nombre: str,
    rut: str,
    detalle: str,
    fecha: Optional[date] = None,
    obra_id: str = "",
    obra_nombre: str = "",
    minutos: int = 0,
    mes_key: str = "",
    revisadas: Set[str],
    incluir_revisadas: bool,
    status_rrhh: str = "",
) -> Optional[dict]:
    aid = alerta_id(tipo, rut_norm, fecha=fecha, obra_id=obra_id, mes_key=mes_key)
    rev = aid in revisadas
    if rev and not incluir_revisadas:
        return None
    return {
        "id": aid,
        "tipo": tipo,
        "rut": rut,
        "rut_norm": rut_norm,
        "nombre": nombre,
        "fecha": fecha.isoformat() if isinstance(fecha, date) else "",
        "fecha_txt": fecha.strftime("%d/%m") if isinstance(fecha, date) else "",
        "obra_id": obra_id,
        "obra_nombre": obra_nombre,
        "detalle": detalle,
        "minutos": minutos,
        "revisada": rev,
        "status_rrhh": status_rrhh,
    }


def _turnos_por_obra_rut(turnos: List[dict]) -> Dict[Tuple[str, str], Dict[date, dict]]:
    out: Dict[Tuple[str, str], Dict[date, dict]] = defaultdict(dict)
    for t in turnos:
        rut = t.get("rut_norm") or ""
        oid = t.get("id_recinto")
        dia = t.get("fecha")
        if not rut or oid is None or not isinstance(dia, date):
            continue
        out[(str(oid), rut)][dia] = t
    return out


def _registros_por_rut(registros: List[dict]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = defaultdict(list)
    for r in registros:
        rut = r.get("rut_norm") or ""
        if rut:
            out[rut].append(r)
    return out


def reporte_alertas_mes(
    anio: int,
    mes: int,
    obra_id: Optional[str] = None,
    *,
    incluir_revisadas: bool = False,
) -> dict:
    cfg = configuracion_resumen()
    inicio, fin = _rango_mes(anio, mes)
    eval_fin = _eval_hasta(anio, mes, fin, inicio)
    fecha_corte = _fecha_corte()
    mes_key = f"{anio}-{mes:02d}"
    revisadas = ids_revisadas()

    warnings: List[str] = []
    if not cfg.get("token_configurado"):
        warnings.append("Configure BUK_ASISTENCIA_TOKEN en .env.")

    nomina = listar_todos_vigentes_enriquecidos()
    if not nomina.get("ok"):
        return {
            "ok": False,
            "error": nomina.get("error") or "No se pudo cargar nómina.",
            "grupos": {},
            "warnings": warnings,
        }

    empleados_map: Dict[str, dict] = {}
    for emp in nomina.get("empleados") or []:
        rn = emp.get("rut_norm") or normalizar_rut(emp.get("rut"))
        if rn and _es_vigente_rrhh(emp):
            emp = dict(emp)
            emp["rut_norm"] = rn
            empleados_map[rn] = emp

    vigentes_set = set(empleados_map.keys())

    turnos_res = listar_turnos_rango(inicio, fin)
    if not turnos_res["ok"]:
        return {
            "ok": False,
            "error": turnos_res.get("error"),
            "grupos": {},
            "warnings": warnings,
        }

    turnos = turnos_res.get("turnos") or []
    turnos = [t for t in turnos if (t.get("rut_norm") or "") in vigentes_set]
    turnos_por_rut: Dict[str, List[dict]] = defaultdict(list)
    for t in turnos:
        rn = t.get("rut_norm") or ""
        if rn and _turno_cuenta_asignacion(t):
            turnos_por_rut[rn].append(t)
    ruts_con_turno: Set[str] = set(turnos_por_rut.keys())
    por_obra_rut = _turnos_por_obra_rut(turnos)

    recintos_res = listar_recintos()
    recintos_nombre = {
        str(r.get("obra_id")): r.get("nombre") or str(r.get("obra_id"))
        for r in (recintos_res.get("recintos") or [])
    }

    grupos: Dict[str, List[dict]] = {
        "sin_turno_mes": [],
        "sin_marca": [],
        "atraso_entrada": [],
        "salida_anticipada": [],
        "marcaje_descanso": [],
        "jornada_abierta": [],
    }

    for emp in nomina.get("empleados") or []:
        rut_norm = emp.get("rut_norm") or ""
        if not rut_norm or rut_norm in ruts_con_turno:
            continue
        item = _item_alerta(
            tipo="sin_turno_mes",
            rut_norm=rut_norm,
            nombre=emp.get("full_name") or rut_norm,
            rut=emp.get("rut") or "",
            detalle=(
                f"Sin ningún turno asignado en {_mes_label(anio, mes)} "
                f"(0 días en cualquier sucursal; solo vigentes)."
            ),
            mes_key=mes_key,
            revisadas=revisadas,
            incluir_revisadas=incluir_revisadas,
        )
        if item:
            grupos["sin_turno_mes"].append(item)

    if eval_fin < inicio:
        warnings.append(
            f"Periodo evaluado vacío: corte ayer ({fecha_corte.strftime('%d/%m/%Y')}) "
            f"anterior al inicio del mes consultado."
        )

    if obra_id:
        obras_scan = [str(obra_id)]
    else:
        obras_scan = sorted({k[0] for k in por_obra_rut})
        if len(obras_scan) > 1:
            warnings.append(
                "Sin filtro de sucursal: la consulta puede tardar. Seleccione recinto para acelerar."
            )

    for oid in obras_scan:
        reg_res = listar_registros_recinto(oid, inicio, fin)
        if not reg_res["ok"]:
            warnings.append(reg_res.get("error") or f"Error marcajes obra {oid}.")
            continue
        por_rut_reg = _registros_por_rut(reg_res.get("registros") or [])
        obra_nom = recintos_nombre.get(oid, oid)

        for (o, rut_norm), turnos_map in por_obra_rut.items():
            if o != oid:
                continue
            if rut_norm not in empleados_map:
                continue
            emp = empleados_map.get(rut_norm, {})
            nombre = emp.get("full_name") or next(
                (t.get("nombre_trabajador") for t in turnos_map.values() if t.get("nombre_trabajador")),
                rut_norm,
            )
            rut = emp.get("rut") or ""
            marcas_map = _agregar_marcajes_por_dia(por_rut_reg.get(rut_norm, []), rut_norm)
            tiene_turnos_mes = len(turnos_map) > 0

            if eval_fin < inicio:
                continue

            cursor = inicio
            while cursor <= eval_fin:
                if cursor.month != mes:
                    cursor += timedelta(days=1)
                    continue
                turno = turnos_map.get(cursor)
                marca = marcas_map.get(cursor)
                col = resolver_minutos_colacion(oid, cursor, turno)
                celda = _construir_celda(
                    cursor,
                    fuera_mes=False,
                    turno=turno,
                    marca=marca,
                    colacion_min=col["minutos"],
                    colacion_fuente=col["fuente"],
                    tiene_turnos_mes=tiene_turnos_mes,
                )

                base = dict(
                    rut_norm=rut_norm,
                    nombre=nombre,
                    rut=rut,
                    fecha=cursor,
                    obra_id=oid,
                    obra_nombre=obra_nom,
                    revisadas=revisadas,
                    incluir_revisadas=incluir_revisadas,
                    status_rrhh=emp.get("status") or "",
                )

                if celda.get("sin_marca"):
                    it = _item_alerta(
                        **base,
                        tipo="sin_marca",
                        detalle=f"Turno {celda.get('turno_horario') or '—'} sin marcaje de entrada.",
                    )
                    if it:
                        grupos["sin_marca"].append(it)

                mins_atraso = celda.get("minutos_atraso") or 0
                if mins_atraso > UMBRAL_ALERTA_MINUTOS:
                    it = _item_alerta(
                        **base,
                        tipo="atraso_entrada",
                        detalle=celda.get("entrada_tarde_txt") or f"Atraso {mins_atraso} min",
                        minutos=mins_atraso,
                    )
                    if it:
                        grupos["atraso_entrada"].append(it)

                mins_sal = celda.get("minutos_salida_anticipada") or 0
                if mins_sal > UMBRAL_ALERTA_MINUTOS:
                    it = _item_alerta(
                        **base,
                        tipo="salida_anticipada",
                        detalle=celda.get("salida_anticipada_txt") or f"Salida anticipada {mins_sal} min",
                        minutos=mins_sal,
                    )
                    if it:
                        grupos["salida_anticipada"].append(it)

                if celda.get("descanso") and marca and marca.get("entrada"):
                    it = _item_alerta(
                        **base,
                        tipo="marcaje_descanso",
                        detalle=f"Marcaje en día descanso (entrada {celda.get('entrada') or '—'}).",
                    )
                    if it:
                        grupos["marcaje_descanso"].append(it)

                if (
                    marca
                    and marca.get("entrada")
                    and not marca.get("salida")
                    and cursor <= fecha_corte
                    and turno
                    and _turno_programado(turno)
                ):
                    it = _item_alerta(
                        **base,
                        tipo="jornada_abierta",
                        detalle=f"Entrada {celda.get('entrada') or '—'} sin salida registrada.",
                    )
                    if it:
                        grupos["jornada_abierta"].append(it)

                cursor += timedelta(days=1)

    grupos["sin_marca"] = _consolidar_sin_marca(grupos["sin_marca"])
    for key in grupos:
        grupos[key].sort(key=lambda x: (x.get("fecha") or "", x.get("nombre") or ""))

    total_pendientes = sum(
        1 for g in grupos.values() for a in g if not a.get("revisada")
    )

    return {
        "ok": True,
        "anio": anio,
        "mes": mes,
        "mes_label": _mes_label(anio, mes),
        "mes_key": mes_key,
        "obra_id": obra_id or "",
        "periodo_desde": inicio.strftime("%d-%m-%Y"),
        "periodo_hasta": eval_fin.strftime("%d-%m-%Y") if eval_fin >= inicio else "—",
        "fecha_corte": fecha_corte.strftime("%d-%m-%Y"),
        "total_vigentes": len(empleados_map),
        "vigentes_con_turno_mes": len(ruts_con_turno),
        "total_pendientes": total_pendientes,
        "grupos": grupos,
        "warnings": warnings,
        "umbral_minutos": UMBRAL_ALERTA_MINUTOS,
        "config": cfg,
    }


def contador_alertas_mes(anio: int, mes: int, obra_id: Optional[str] = None) -> dict:
    rep = reporte_alertas_mes(anio, mes, obra_id, incluir_revisadas=False)
    return {
        "ok": rep.get("ok", False),
        "total": rep.get("total_pendientes", 0),
        "error": rep.get("error"),
    }
