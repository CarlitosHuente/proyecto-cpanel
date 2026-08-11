# Diccionario de aplicaciones — Huente cPanel

**Para qué sirve:** descripción de **cómo funciona cada módulo hoy** (objetivo, rutas, datos, reglas, permisos, archivos).  
**No es changelog:** ver [`BITACORA.md`](BITACORA.md).  
**Cómo trabajar / deploy:** ver [`RESUMEN_OPERATIVO.md`](RESUMEN_OPERATIVO.md).

**Obligatorio:** al crear un módulo nuevo o una pieza grande, agregar aquí una sección con el mismo nivel de detalle (objetivo, rutas, datos, reglas, archivos).

---

## Índice

1. [Arquitectura y piezas transversales](#1-arquitectura-y-piezas-transversales)
2. [Auth y Centro de Accesos](#2-auth-y-centro-de-accesos)
3. [Dashboard](#3-dashboard)
4. [Ventas](#4-ventas)
5. [Precios](#5-precios)
6. [Seremi](#6-seremi)
7. [Contabilidad / Gestión](#7-contabilidad--gestión)
8. [Costeo](#8-costeo)
9. [Finanzas](#9-finanzas)
10. [Sucursales](#10-sucursales)
11. [Configuración](#11-configuración)
12. [Arqueo de caja](#12-arqueo-de-caja)
13. [DespachoWeb](#13-despachoweb)
14. [Fábrica (empanadas)](#14-fábrica-empanadas)
15. [Fábrica Papaya](#15-fábrica-papaya)
16. [Buk (RRHH + Asistencia)](#16-buk-rrhh--asistencia)
17. [Reglas NETO y presentación comercial](#17-reglas-neto-y-presentación-comercial)
18. [Cachés y `/refresh`](#18-cachés-y-refresh)

---

## 1. Arquitectura y piezas transversales

| Pieza | Rol |
|--------|-----|
| `app.py` | Flask app, blueprints, filtros Jinja (`dinero`, `metrico`, `ddmmaaaa`), `/refresh` |
| `routes/*_routes.py` | Endpoints por dominio |
| `utils/`, `services/` | Negocio, APIs externas, helpers |
| `templates/`, `static/` | UI |
| `utils/db.py` + `utils/env_config.py` | MySQL y variables `.env` |
| `utils/sheet_cache.py` | Ventas comercial/agrícola desde BD, NETO/presentación, caché proceso |
| `utils/filters.py` | `filtrar_dataframe` (sucursal, semana, año, fechas, familia) |
| `utils/ventas_excel_import.py` | Excel/CSV → `ventas_*` + `cargas_*` |
| `utils/formato_dinero.py` + `static/js/formato_huente.js` | Presentación CLP / métricos |
| `utils/secret_key.py` | `SECRET_KEY` env o `instance/flask_secret_key` |

---

## 2. Auth y Centro de Accesos

**Auth (`auth`)**

- Login local: email + password (hash Werkzeug) en `usuarios_huente`.
- Rutas: `/`, `/login`, `/logout` (`routes/auth_routes.py`).
- Sesión: `usuario`, `rol`, `sucursal_id`; lifetime ~45 min.
- Rate-limit de fallos: `utils/login_rate_limit.py`.
- Decoradores: `@login_requerido`, `@permiso_modulo` (`utils/auth.py`).
- Bypass login **solo** con `ALLOW_DEV_LOGIN=1` en `.env` local (nunca por `Host`).

**Centro de Accesos (`config` / accesos)**

- UI: `/config/accesos` — pestañas Correos por rol, Secciones por rol, Página de inicio.
- Catálogo árbol: `utils/permisos_catalogo.py` (padre implica hijos).
- Persistencia: `data/roles_config.json` vía `utils/roles_config.py` (mtime + recarga).
- Login usa `obtener_ruta_inicio_rol()`; menú `base.html` usa `tiene_seccion()` / `tiene_permiso()`.
- `/config/permisos` y `/config/usuarios_pizarra` redirigen a accesos.
- Deploy: carpeta `data/` escribible en hosting para guardar desde la UI.

---

## 3. Dashboard

**Permisos:** `dashboard` (padre); hijos `dashboard.horario`, `dashboard.promos`.

### 3.1 KPIs ventas

- Ruta UI: dashboard principal; APIs en `routes/dashboard_routes.py` (`/api/dashboard-data`, productos, `latest-date-info`, `sucursales`).
- Filtros: empresa, sucursal, semana/año o desde/hasta → solo con **Aplicar filtros**.
- Ticket promedio: por `N_BOLETA` (neto por comprobante).
- `latest-date-info` / `sucursales`: SQL liviano (`MAX(fecha)` / `DISTINCT sucursal`); fallback a `obtener_datos`.
- Archivos: `templates/dashboard.html`, `static/js/dashboard.js` (subir `?v=`).

### 3.2 Ventas por horario

- Rutas: `/dashboard/ventas-horario`, `/api/dashboard-ventas-horario`, `/api/sucursales-horario`.
- Lógica: `services/ventas_horario_service.py` — neto por `hora_pedid`; agrícola con canal desde `des_client`.
- UI: comparar 7 días o detalle un día; `templates/dashboard_ventas_horario.html`, `static/js/dashboard_ventas_horario.js`.

### 3.3 Promoción vs Individual

- Rutas: `/dashboard/promos`, `/api/dashboard-promos`.
- **Por qué aparte:** el pipeline KPI excluye rubro `PROMOCIÓN`; este módulo sí la lee.
- Unidades: packs promo × receta (`RECETAS_PROMO` en `services/promos_vs_individual_service.py`); individual = total − promo.
- KPIs: % boletas con promo, ticket con/sin, precio efectivo, packs/día, mix, acompañamiento; simulador what-if en cliente.
- Archivos: `templates/dashboard_promos.html`, `static/js/dashboard_promos.js`.

---

## 4. Ventas

- Análisis / export Excel: `routes/ventas_routes.py`.
- **Histórico de productos:** `/ventas/historico`; APIs `/api/historico-resumen`, `/api/historico-producto`.
  - Comparación año actual vs anterior por **mismas semanas** (cards, KPIs, totales).
  - Tabla mensual: mes en curso recortado a mismas semanas; futuros con tooltip proyección.
  - Gráficos semanales: año anterior completo como referencia visual.
  - UI: `templates/ventas_historico.html`, `static/js/ventas_historico.js` (caché en memoria + `?v=`).

---

## 5. Precios

- Mantenedor listas/matriz de precios (`precios` blueprint / JSON según implementación en `routes/precios_routes.py` y config asociada).
- Presentación montos con reglas de proyecto (`|dinero` / `HuenteFmt`).

---

## 6. Seremi

**Objetivo:** controles sanitarios desde Google Sheets CSV (`utils/sheet_cache.py`).

- Vistas + prints: `routes/seremi_routes.py`, `templates/seremi/*.html`, `templates/seremi/print_*.html`.
- Filtros mensuales: sucursal + mes + año (`?año=` / `?anio=`). Default año: actual con datos o más reciente; años &lt; 2010 ignorados.
- Grillas día 1…N con `calendar.monthrange`.
- Cambio aceite: filtro mes+año; últimos 20 del período.

---

## 7. Contabilidad / Gestión

Blueprint `contab` — `routes/contab_routes.py`.

| Vista | Ruta / notas |
|-------|----------------|
| Dashboard gestión | `/contab/dashboard_gestion` — KPIs alineados a EERR; resumen % s/ ventas; ranking CC; drill-down cards (serie YoY) |
| Vista mensual | `/contab/informe_gerencial` — tooltips % s/ ventas |
| Comparativo | comparativo gestión |
| Acumulado | `/contab/acumulado_gestion` — rango de meses + mismo rango año anterior |
| Macros P&amp;L | `/contab/macros_gestion` + `macros_gestion.json` opcional (`activo: false` → comportamiento previo) |
| Otros | mayor, prorrateos, clasificaciones, rentabilidad gerencia, etc. |

**Estructura compartida:** `utils/gestion_estructura.py` — `ESTRUCTURA_GESTION`, helpers KPIs/resumen/`serie_kpis_mensual`.  
**Ventas brutas en KPIs:** suma cuentas 4xx (misma base que tendencia).  
**Presentación:** `|dinero`; % con 1 decimal.

---

## 8. Costeo

- Blueprint `costeo`: mapeo, costos directos, reglas, GAV, simuladores, rentabilidad.
- Ventas: misma capa NETO/presentación que dashboard (`obtener_datos("comercial")`); agrupación con clave única `EMPANADA DE QUESO CRUDA`.
- Archivos: `routes/costeo_routes.py`, `utils/costeo_manager.py`, templates `templates/costeo/*` / contab relacionados.

---

## 9. Finanzas

- Flujo de caja, banco, pagos, respaldos (`routes/finanzas_routes.py`, `templates/finanzas/*`).
- Archivos de respaldo bajo uploads/finanzas según rutas del blueprint.

---

## 10. Sucursales

- Pizarra operativa, historial, tareas, comprobantes, anuncios (`routes/sucursales_routes.py`).
- Anuncios HTML desde config; API anuncio activo para pizarra.

---

## 11. Configuración

- Usuarios, roles/accesos, categorías, productos, anuncios, cargas.
- **Import comercial:** `/config/comercial` (últimas 15 + upload); historial `/config/comercial/cargas`; revertir `POST …/revertir/<carga_id>` (CASCADE a `ventas_comercial`).
- Carga agrícola y utilidades asociadas en el mismo blueprint (`routes/config_routes.py`).
- Tras import: invalidar caché (`forzar_actualizacion`) / `/refresh` con sesión.

---

## 12. Arqueo de caja

**Permiso:** `arqueo_caja`. **Base:** `/arqueo-caja`.

**Objetivo:** import Excel sistema, captura terreno por día/caja/canal, cuadratura, auditoría, export, reporte tipos de pago, bandeja PDF correo.

### Datos

| Tabla | Rol |
|--------|-----|
| `arqueo_caja_cargas` | Cabecera carga |
| `arqueo_caja_lineas` | Líneas import; base de canales (`desc_cta`) |
| `arqueo_caja_terreno` | UK sucursal+fecha+canal_norm+caja; monto, propina, notas |
| `mail_pdf_inbox` | Metadata PDFs IMAP |

JSON UI (sin tabla): `instance/arqueo_canales_ui.json`, `instance/arqueo_tipos_pago.json`.

### Rutas clave

| Ruta | Uso |
|------|-----|
| `…/import`, `…/revertir/<id>` | Carga / borrado sistema |
| `…/terreno` (+ bundle eliminar/notas) | Captura grilla |
| `…/canales-ui`, `…/tipos-pago` | Admin etiquetas / agrupación |
| `…/cuadratura` | Día o `?vista=semana` |
| `…/cuadratura/auditoria`, `…/export.xlsx` | Detalle / Excel |
| `…/reporte-tipos-pago` | % tipos y sucursales; corrección canal terreno |
| `…/correo-pdf*` | Bandeja IMAP; sync sesión o cron `MAIL_SYNC_TOKEN` |

**Cuadratura:** terreno = Caja1+Caja2 por canal; sistema = total sucursal/día. Conciliado si diff 0 y hay datos.  
**Cron sync PDF:** `POST …/correo-pdf/sync-token` + header `X-Mail-Sync-Token`.  
**Archivos:** `routes/arqueo_caja_routes.py`, `utils/arqueo_caja_*`, `utils/mail_imap_inbox.py`, `utils/correo_pdf_service.py`, `templates/arqueo_caja/*`.

---

## 13. DespachoWeb

**Permiso:** `despacho_web` (roles tipicos: superusuario, admin, logistica). **Base:** `/despacho-web`.

**Objetivo:** cargar facturas PDF tienda web, validar split-screen, persistir órdenes MySQL para AppSheet (AppSheet solo visualiza).

### Datos

| Tabla | Rol |
|--------|-----|
| `Productos` | Catálogo; alta automática desde PDF |
| `Orden` | Cabecera (`n_orden` PK, estados, comuna, etc.) |
| `` `Detalle O.C` `` | Líneas |

### Flujos

| Modo | Entrada | Flujo |
|------|---------|--------|
| Unitario | 1–5 PDFs | Validación split-screen |
| Masivo | 1 PDF multipágina (máx. 100) | Resumen lote → validar una a una |

Estados: Pendiente, Retiro Costanera, Armado, En Ruta, Entregada, Anulado.  
Celular normalizado `+569…`. Impresión operacional: `…/ordenes/<n>/imprimir` (no DTE SII).  
Dependencias: `pdfplumber`, `pypdf`.  
**Archivos:** `routes/despacho_web_routes.py`, `utils/despacho_web_*.py`, `templates/despacho_web/*`, `static/js/despacho_web_validar.js`.

---

## 14. Fábrica (empanadas)

**Permiso:** `fabrica`. Rutas en `routes/fabrica_routes.py`.

- Calendario: `/fabrica/calendario` — grilla + **resumen mensual** (kg/g `|metrico`, merma/%, g/empanada, unidades).
- Tabla `fabrica_produccion` (fecha, cant_producida, quesos, rendimiento, stocks, etc.).
- Modal detalle: neto empanada = inicial − pizza − merma; promedios con `HuenteFmt.metrico`.
- Admin datos: `templates/fabrica/admin_datos.html` (según desplegado).

**Pendiente de negocio (no implementado aún):** campos explícitos “Empanada” vs `cant_producida` y “Queso cortado para empanada” — definir con operaciones antes de ALTER (ver bitácora).

---

## 15. Fábrica Papaya

**Permiso:** `fabrica_papaya`. Captura principal **AppSheet** → MySQL; web consulta/corrige (supervisor+).

### Tablas

`papaya_conceptos`, `papaya_cierre_stock` (inicial/ajuste), `papaya_dia_mp`, `papaya_dia_elaboracion`, `papaya_dia_transformacion`, `papaya_despacho_guia`, `papaya_dia_despacho`, `papaya_semana_stock_real`.

DDL: `QUERY_FABRICA_PAPAYA_PRODUCCION.sql` + migraciones en `QUERY_CAMBIOS_PRODUCCION.sql`.  
Datos: `DATA_FABRICA_PAPAYA_IMPORT.sql` / `scripts/export_fabrica_papaya_sql.py` / import Excel `scripts/import_fabrica_papaya_excel.py`.

### AppSheet guías

1. Cabecera `papaya_despacho_guia` → 2. líneas `papaya_dia_despacho` con `guia_id` → stock por línea. Histórico Excel puede tener `guia_id` NULL.

### Reglas

- Semana lun–dom ISO (Chile).
- Stock MP, intermedios, rendimiento pelador (días con elaboración y kg útiles &gt; 0).
- Propuesta stock domingo; cierres inicial/ajuste pisan calculado.

### Rutas web

`/fabrica-papaya/semana`, `/mes`, `/dia/<fecha>`, POST correcciones mp/elaboracion/transformacion/despacho, `/stock-real`, `/conceptos`, `/cierre-stock`.

**Archivos:** `routes/fabrica_papaya_routes.py`, `utils/fabrica_papaya_*.py`, `templates/fabrica_papaya/*`.

---

## 16. Buk (RRHH + Asistencia)

**Solo lectura / documentos hacia Buk** (no persiste nómina en Huente salvo JSON locales de UI). Permiso menú Buk.

| Pieza | Rol |
|--------|-----|
| `utils/buk_api.py` | RRHH: empleados, áreas, recintos |
| `utils/buk_asistencia_api.py` | Marcajes, turnos, recintos Ctrlit |
| `utils/buk_presencia.py` | Cruce nómina + marcaje día |
| `utils/buk_calendario.py` | Mes: turnos + marcajes, horas netas |
| `utils/buk_alertas.py` + `buk_alertas_revisadas.py` | Alertas + checkbox revisada (`data/buk_alertas_revisadas.json`) |
| `utils/buk_colacion_config.py` | Colación por recinto JSON |
| `utils/buk_ausencias.py` | Días sin marca en el mes |
| Encuestas | PDF + subida docs (`buk_encuesta_pdf`, `buk_documentos`, `buk_notificacion`) |

**Rutas:** `/buk`, `/buk/asistencia`, `/buk/ausencias`, `/buk/calendario`, `/buk/alertas`, `/buk/encuestas`, APIs JSON. Overlay: `static/js/buk_loading.js`.

**Env:** `BUK_TENANT`, `BUK_AUTH_TOKEN` (RRHH); `BUK_ASISTENCIA_TOKEN` (**distinto**); opcional `BUK_ASISTENCIA_API_BASE`, `BUK_ENCUESTA_CARPETA`, flags notificación / `SMTP_*`.

**Reglas:** consultas por id/código/RUT; horas UTC → `America/Santiago`. Horas netas = (salida − entrada) − colación (prioridad: turno Buk → grupo día → default sucursal). Alertas con corte **ayer**; sin turno mes = 0 asignaciones en el mes.

---

## 17. Reglas NETO y presentación comercial

*(Compartidas por dashboard, costeo, horario, histórico, etc. Código: `utils/sheet_cache.py`.)*

**NETO comercial**

- Bruto línea con IVA (default): `CANTIDAD × PRECIO_LIS`.
- Excepción docena POS (`DOCENA EMPANADA CRUDA`…): `CANTIDAD × PRECIO` (si PRECIO 0 → LISTA).
- QUESO PIEZA (KG): lista × cant; lista 0 → PRECIO.
- DESPACHO WEB: neto sin `/1.19` cuando aplica.
- Familia Promoción: **excluida** del dataframe KPI (salvo módulo Promos).

**Notas de crédito:** se importan si vienen negativas (restan).

**Presentación (solo memoria; BD intacta)**

- Unificación producto a `EMPANADA DE QUESO CRUDA` cuando aplica máscara.
- Familias/rubros normalizados (Otros, Quesos, Empanadas, Papaya, etc.); empanada queso frita → familia Empanadas.

---

## 18. Cachés y `/refresh`

| Capa | Dónde | Invalidación |
|------|--------|----------------|
| Servidor | `_cache` en `sheet_cache.obtener_datos` | `forzar_actualizacion` / import / reinicio WSGI |
| Navegador | JS dashboard / histórico | Recarga página o cambio de query |
| Manual | `GET /refresh` | Requiere **sesión**; `refrescar_todo_el_cache` |

Si “no veo la última carga”: import + invalidación + `/refresh` logueado antes de depurar lógica.

---

*Al agregar un módulo: nueva sección en este índice + detalle (rutas, datos, reglas, archivos).*
