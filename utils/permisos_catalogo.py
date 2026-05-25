"""
Catálogo de permisos alineado al menú lateral.
Un permiso padre (ej. ventas) implica acceso a todos sus hijos (ventas.historico, etc.).
"""

from __future__ import annotations

from typing import Dict, List, Optional

# id, label, descripción corta, hijos (ids)
CATALOGO: List[dict] = [
    {
        "id": "dashboard",
        "label": "Dashboard KPIs",
        "desc": "Panel gerencial: neto, empanadas, ticket, gráficos y tendencias.",
        "hijos": [
            {"id": "dashboard.kpis", "label": "Dashboard KPIs", "desc": "Vista principal de KPIs y gráficos de ventas."},
            {"id": "dashboard.horario", "label": "Ventas por Horario", "desc": "Neto y boletas por hora del pedido (hora_pedid) por sucursal y período."},
        ],
    },
    {
        "id": "ventas",
        "label": "Ventas",
        "desc": "Análisis comercial y operativo de ventas.",
        "hijos": [
            {"id": "ventas.resumen", "label": "Dashboard Ventas", "desc": "Resumen diario/semanal por sucursal y familia."},
            {"id": "ventas.historico", "label": "Histórico Productos", "desc": "Evolución de producto vs año anterior."},
            {"id": "ventas.precios", "label": "Lista de Precios", "desc": "Matriz de listas de precios e IVA."},
            {"id": "ventas.agricola", "label": "Importar Agrícola", "desc": "Carga Excel/CSV ventas agrícolas."},
        ],
    },
    {
        "id": "clientes",
        "label": "Clientes",
        "desc": "Base de entidades y clientes (en desarrollo).",
        "hijos": [],
    },
    {
        "id": "seremi",
        "label": "Seremi",
        "desc": "Control sanitario y calidad.",
        "hijos": [
            {"id": "seremi.equipos", "label": "Temperatura Equipos", "desc": "Monitoreo de equipos de frío."},
            {"id": "seremi.productos", "label": "Temperatura Productos", "desc": "Control de temperatura de productos."},
            {"id": "seremi.aceite", "label": "Cambio de Aceite", "desc": "Registro de cambio de aceite."},
            {"id": "seremi.recepcion", "label": "Recepción Mercadería", "desc": "Control de recepción."},
            {"id": "seremi.personal", "label": "Registro Personal", "desc": "Asistencia y personal en local."},
        ],
    },
    {
        "id": "sucursales",
        "label": "Sucursales / Pedidos",
        "desc": "Pizarra operativa, tareas y solicitudes por local.",
        "hijos": [],
    },
    {
        "id": "arqueo_caja",
        "label": "Arqueo de Caja",
        "desc": "Import sistema, terreno, cuadratura y auditoría.",
        "hijos": [],
    },
    {
        "id": "flujo",
        "label": "Finanzas / Tesorería",
        "desc": "Flujo de caja y pagos.",
        "hijos": [
            {"id": "flujo.dashboard", "label": "Flujo de Caja", "desc": "Calendario ingresos vs egresos."},
            {"id": "flujo.pagos", "label": "Registrar Pago/Ingreso", "desc": "Movimientos manuales."},
            {"id": "flujo.banco", "label": "Pagos Masivos (TXT)", "desc": "Generación archivo banco."},
        ],
    },
    {
        "id": "contab",
        "label": "Contabilidad operativa",
        "desc": "Mayor, prorrateos, costeo y clasificación.",
        "hijos": [
            {"id": "contab.comparativo", "label": "Comparativo", "desc": "Comparativo contable."},
            {"id": "contab.archivos", "label": "Archivos", "desc": "Libro mayor y detalle."},
            {"id": "contab.prorrateos", "label": "Prorrateos", "desc": "Asignación de cuentas a centros."},
            {"id": "contab.costeo", "label": "Costeo de Productos", "desc": "Mapeo, directos, reglas, GAV, simulador."},
            {"id": "contab.clasificacion", "label": "Clasificación Cuentas", "desc": "Grupos y clasificación."},
        ],
    },
    {
        "id": "reporte",
        "label": "Informes gerenciales",
        "desc": "Estado de resultados y rentabilidad (solo lectura gerencial).",
        "hijos": [
            {"id": "reporte.informe", "label": "Informe Gerencial", "desc": "Estado de resultados mensual."},
            {"id": "reporte.comparativo", "label": "Comparativo Gestión", "desc": "Comparativo de gestión."},
            {"id": "reporte.acumulado", "label": "Acumulado Gestión", "desc": "Resultado acumulado en rango."},
            {"id": "reporte.rentabilidad", "label": "Rentabilidad Productos", "desc": "Rentabilidad por producto."},
        ],
    },
    {
        "id": "fabrica",
        "label": "Fábrica Empanadas",
        "desc": "Calendario y registro de producción.",
        "hijos": [],
    },
    {
        "id": "utilidades",
        "label": "Utilidades",
        "desc": "Calculadoras y herramientas de apoyo.",
        "hijos": [],
    },
    {
        "id": "config",
        "label": "Configuración",
        "desc": "Usuarios, permisos, catálogo y anuncios.",
        "hijos": [
            {"id": "config.usuarios", "label": "Usuarios", "desc": "Alta/edición de cuentas."},
            {"id": "config.accesos", "label": "Centro de Accesos", "desc": "Roles, correos y permisos."},
            {"id": "config.productos", "label": "Productos", "desc": "Mantenedor de productos."},
            {"id": "config.categorias", "label": "Categorías", "desc": "Familias y rubros."},
            {"id": "config.anuncios", "label": "Anuncios Pop-Up", "desc": "Banners globales."},
            {"id": "config.comercial", "label": "Import Comercial", "desc": "Carga Excel ventas comerciales."},
        ],
    },
    {
        "id": "agricola",
        "label": "Agrícola (legacy)",
        "desc": "Alias de ventas.agricola para compatibilidad.",
        "hijos": [],
    },
    {
        "id": "productos",
        "label": "Productos (legacy)",
        "desc": "Alias de config.productos para compatibilidad.",
        "hijos": [],
    },
    {
        "id": "categorias",
        "label": "Categorías (legacy)",
        "desc": "Alias de config.categorias para compatibilidad.",
        "hijos": [],
    },
]

# Páginas de inicio disponibles al configurar un rol (endpoint Flask → etiqueta)
PAGINAS_INICIO: List[dict] = [
    {"endpoint": "dashboard.dashboard", "label": "Dashboard KPIs"},
    {"endpoint": "dashboard.ventas_horario", "label": "Ventas por Horario"},
    {"endpoint": "ventas.ventas", "label": "Ventas — Resumen"},
    {"endpoint": "ventas.ventas_historico", "label": "Histórico Productos"},
    {"endpoint": "precios.vista_precios", "label": "Lista de Precios"},
    {"endpoint": "seremi.temperatura_equipos", "label": "Seremi — Temperatura Equipos"},
    {"endpoint": "sucursales.pizarra", "label": "Sucursales / Pedidos"},
    {"endpoint": "arqueo_caja.index", "label": "Arqueo de Caja"},
    {"endpoint": "finanzas.flujo", "label": "Flujo de Caja"},
    {"endpoint": "contab.dashboard_gestion", "label": "Informe Gerencial"},
    {"endpoint": "contab.comparativo", "label": "Comparativo Contable"},
    {"endpoint": "costeo.rentabilidad_gerencia", "label": "Rentabilidad Productos"},
    {"endpoint": "fabrica.calendario_produccion", "label": "Fábrica — Calendario"},
    {"endpoint": "utilidades.calculadora_margen", "label": "Utilidades — Calculadoras"},
    {"endpoint": "config.usuarios", "label": "Config — Usuarios"},
    {"endpoint": "config.accesos", "label": "Config — Centro de Accesos"},
    {"endpoint": "config.gestion_agricola", "label": "Import Agrícola"},
]

DEFAULT_PAGINA_INICIO: Dict[str, str] = {
    "superusuario": "contab.dashboard_gestion",
    "admin": "dashboard.dashboard",
    "gerencia": "contab.dashboard_gestion",
    "contab": "contab.dashboard_gestion",
    "seremi": "seremi.temperatura_equipos",
    "seremi2": "seremi.temperatura_equipos",
    "ventas": "ventas.ventas",
    "sucursales": "sucursales.pizarra",
    "logistica": "sucursales.pizarra",
    "invitado": "config.gestion_agricola",
    "default": "dashboard.dashboard",
}

# Mapeo permiso granular → permiso legacy en rutas (decorador actual)
PERMISO_RUTA_LEGACY: Dict[str, str] = {
    "ventas.resumen": "ventas",
    "ventas.historico": "ventas",
    "ventas.precios": "ventas",
    "ventas.agricola": "agricola",
    "seremi.equipos": "seremi",
    "seremi.productos": "seremi",
    "seremi.aceite": "seremi",
    "seremi.recepcion": "seremi",
    "seremi.personal": "seremi",
    "flujo.dashboard": "flujo",
    "flujo.pagos": "flujo",
    "flujo.banco": "flujo",
    "contab.comparativo": "contab",
    "contab.archivos": "contab",
    "contab.prorrateos": "contab",
    "contab.costeo": "contab",
    "contab.clasificacion": "contab",
    "reporte.informe": "reporte",
    "reporte.comparativo": "reporte",
    "reporte.acumulado": "reporte",
    "reporte.rentabilidad": "reporte",
    "config.usuarios": "config",
    "config.accesos": "config",
    "config.productos": "productos",
    "config.categorias": "categorias",
    "config.anuncios": "config",
    "config.comercial": "config",
    "dashboard.kpis": "dashboard",
    "dashboard.horario": "dashboard",
}


def _todos_ids() -> List[str]:
    ids: List[str] = []
    for grupo in CATALOGO:
        ids.append(grupo["id"])
        for h in grupo.get("hijos") or []:
            ids.append(h["id"])
    return ids


def permiso_padre(modulo: str) -> Optional[str]:
    """Devuelve el id del grupo padre, o None si es raíz."""
    for grupo in CATALOGO:
        if modulo == grupo["id"]:
            return None
        for h in grupo.get("hijos") or []:
            if h["id"] == modulo:
                return grupo["id"]
    return None


def hijos_de(padre_id: str) -> List[str]:
    for grupo in CATALOGO:
        if grupo["id"] == padre_id:
            return [h["id"] for h in grupo.get("hijos") or []]
    return []


def permisos_expandidos(permisos_rol: List[str]) -> set:
    """Expande '*' y permisos padre a conjunto completo de ids."""
    if "*" in permisos_rol:
        return set(_todos_ids()) | {"*"}

    expandido = set(permisos_rol)
    for p in list(permisos_rol):
        expandido.update(hijos_de(p))
        # aliases legacy
        if p == "agricola":
            expandido.add("ventas.agricola")
        if p == "productos":
            expandido.add("config.productos")
        if p == "categorias":
            expandido.add("config.categorias")
    return expandido


def tiene_permiso_en_lista(permisos_rol: List[str], modulo: str) -> bool:
    if "*" in permisos_rol:
        return True
    expandido = permisos_expandidos(permisos_rol)
    if modulo in expandido:
        return True
    # legacy: ruta protegida con "ventas" acepta permiso granular ventas.*
    padre = permiso_padre(modulo)
    if padre and padre in expandido:
        return True
    legacy = PERMISO_RUTA_LEGACY.get(modulo)
    if legacy and legacy in expandido:
        return True
    return False


def catalogo_para_template() -> List[dict]:
    """Catálogo listo para Jinja (sin mutar original)."""
    return CATALOGO


def modulos_planos_catalogo() -> List[str]:
    return sorted(_todos_ids())
