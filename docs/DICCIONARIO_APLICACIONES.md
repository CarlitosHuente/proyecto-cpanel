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
19. [Drive vía Apps Script (archivos / fotos)](#19-drive-vía-apps-script-archivos--fotos)
20. [Fondos por Rendir (FxR)](#20-fondos-por-rendir-fxr)

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
| Otros | mayor, clasificaciones, rentabilidad gerencia, etc. |
| Prorrateos | `/contab/prorrateos` — periodo predeterminado = mes más reciente del mayor. Serv. Generales: copiar mes anterior. Comisiones: mix Arqueo (`% de este tipo`; Mercado Pago = Redelcom) con **Configurar** manual del mes (manda sobre Arqueo). |

**Estructura compartida:** `utils/gestion_estructura.py` — `ESTRUCTURA_GESTION`, helpers KPIs/resumen/`serie_kpis_mensual`.  
**Ventas brutas en KPIs:** suma cuentas 4xx (misma base que tendencia).  
**Presentación:** `|dinero`; % con 1 decimal.

---

## 8. Costeo

- Blueprint `costeo`: mapeo, costos directos, reglas, GAV, simuladores, rentabilidad. Entrada: `/costeo/mapeo` (menú Gestión → Contab → Costeo de Productos).
- Periodo **predeterminado**: mes más reciente con movimiento en el mayor. El filtro de mes se puede cambiar a cualquiera.
- Ventas: misma capa NETO/presentación que dashboard (`obtener_datos("comercial")`); agrupación con clave única `EMPANADA DE QUESO CRUDA`.
- Si Drive no entrega `mayor.xlsx` o el mes aún no tiene movimientos, las pantallas quedan vacías (no 500). El simulador inicializa costos automáticos de pizza/empanada en 0 cuando no hay mayor del periodo.
- Archivos: `routes/costeo_routes.py`, `utils/costeo_manager.py`, templates `templates/contab/costeo_*.html`.

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

- Usuarios, roles/accesos, categorías, productos, anuncios, cargas, **notificaciones**.
- **Notificaciones:** `/config/notificaciones` (permiso `config.notificaciones`). Destinatarios + envío automático (días/hora Chile) en `data/notificaciones_config.json` (por ahora solo `buk_alertas`). Cron: `GET|POST /config/notificaciones/cron` con `MAIL_SYNC_TOKEN` — **preferir 1×/día** a la hora configurada (no cada 15 min; ver resumen operativo §12). Envío vía `utils/mail_smtp.py` (`SMTP_*` o fallback `IMAP_*` de Arqueo).
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
La casilla `IMAP_*` también alimenta el envío SMTP compartido si no hay `SMTP_*` (ver Config → Notificaciones / `utils/mail_smtp.py`).  
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
| `utils/buk_alertas_correo.py` | Arma y envía resumen de alertas (destinos en Notificaciones) |
| `utils/buk_colacion_config.py` | Colación por recinto JSON |
| `utils/buk_ausencias.py` | Días sin marca en el mes |
| Encuestas | PDF + subida docs (`buk_encuesta_pdf`, `buk_documentos`, `buk_notificacion`) |
| Correo salida | `utils/mail_smtp.py` + `smtp_settings()` (SMTP_* o IMAP_*); From visible `SMTP_FROM_NAME` (default Huentelauquen) |
| Plantilla reportes | `utils/mail_reporte_html.py` — HTML con tablas/colores reutilizable por módulo |

**Rutas:** `/buk`, `/buk/asistencia`, `/buk/ausencias`, `/buk/calendario`, `/buk/alertas`, `POST /buk/alertas/enviar`, `/buk/encuestas`, APIs JSON. Overlay: `static/js/buk_loading.js`.

**Env:** `BUK_TENANT`, `BUK_AUTH_TOKEN` (RRHH); `BUK_ASISTENCIA_TOKEN` (**distinto**); opcional `BUK_ASISTENCIA_API_BASE`, `BUK_ENCUESTA_CARPETA`, flags notificación / `SMTP_*` (o casilla `IMAP_*`).

**Reglas:** consultas por id/código/RUT; horas UTC → `America/Santiago`. Horas netas = (salida − entrada) − colación (prioridad: turno Buk → grupo día → default sucursal). Alertas con corte **ayer**; sin turno mes = 0 jornadas laborales (`HH:MM-HH:MM`) en el mes. Envío de alertas: solo no revisadas; destinarios en Config → Notificaciones.

**Turnos / descanso / rotación:** Buk marca días sin jornada con `horarioTurno: "-"` (Descanso, Turno Base en otro recinto). Solo horario válido genera «Sin marca» si falta entrada. Al filtrar recinto A: jornada en B → celda **↗ sucursal**; banner evaluación (días turno aquí, descansos, días en otras sucursales).

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

## 19. Drive vía Apps Script (archivos / fotos)

**Descubrimiento operativo (2026-08-10):** para guardar desde la web documentos pesados, imágenes o fotos (cámara) en Google Drive, **no** usar la service account (`credenciales_google.json` / `drive_utils`) contra una carpeta de *Mi unidad*: suele fallar por **cuota 0 GB** de la SA. El camino que sí funciona es el mismo que el mayor: **Flask → POST → Apps Script Web App → DriveApp** (escribe con la cuenta dueña del script, que sí tiene cuota).

### Piezas en uso

| Pieza | Valor / archivo |
|--------|------------------|
| Proyecto Apps Script | `SubirArchivosRender` |
| Web App URL | `https://script.google.com/macros/s/AKfycbxUK2SQ_fDaX1wEcTDLfnefcZPCZDp3A5rrqd2gZ6KBHV7qbBuysYTXltBBLXraNGj7/exec` |
| Carpeta padre Drive | `contabilidad` ID `1zFjARS82JAuay19WxxgepBl7jYylgPIn` |
| Subcarpeta respaldos | `respaldoimagenes` (varios archivos; no borra el mayor) |
| Código canónico del script | [`docs/apps_script_SubirArchivosRender.gs`](apps_script_SubirArchivosRender.gs) |
| Contab (mayor) | [`routes/contab_routes.py`](../routes/contab_routes.py) → `enviar_archivo_a_script` |
| Prueba UI | `/drive-prueba/` — [`routes/drive_prueba_routes.py`](../routes/drive_prueba_routes.py) |

### Contrato JSON (obligatorio)

Enviar body como **texto JSON** con `Content-Type: text/plain; charset=utf-8` (evita que se confunda con form-urlencoded y caiga al camino del mayor).

**Agregar archivo/imagen/foto** (no toca `mayor.xlsx`):

```json
{"accion":"imagen","nombre":"foto.jpg","mime":"image/jpeg","base64":"..."}
```

Respuesta OK: `OK:https://drive.google.com/file/d/...`  
Cada llamada **crea un archivo nuevo** en `respaldoimagenes` (se pueden acumular muchos).

**Reemplazar libro mayor** (único camino que manda a papelera el `mayor.xlsx` anterior):

```json
{"accion":"mayor","base64":"..."}
```

Respuesta OK: `OK`

**Reglas de seguridad del script**

- Solo `accion === "mayor"` llama a `reemplazarMayor` (papelera + crear).
- `accion === "imagen"` solo `createFile` en la subcarpeta.
- Tras editar el `.gs`: **Implementar → Nueva versión** (guardar no actualiza el `/exec`).
- No probar `doPost` con el botón Ejecutar del editor (`postData` no existe).

### Cómo reutilizarlo en un módulo futuro

1. En Flask: leer bytes del upload o de la cámara → `base64` → `requests.post(URL, data=json.dumps({...}).encode("utf-8"), headers={"Content-Type": "text/plain; charset=utf-8"}, timeout=90)`.
2. Guardar en BD solo metadatos ligeros (id Drive, URL, nombre, módulo, usuario, fecha) — **no** el binario en MySQL.
3. Si hace falta otra carpeta: ampliar el script (`accion` + nombre de carpeta) o crear subcarpeta hija y apuntar ahí; no mezclar con el camino `mayor`.
4. Referencia de prueba: menú Utilidades → Prueba Drive (`permiso` `utilidades`).

### Límites y frecuencia (Apps Script / práctica Huente)

Límites oficiales de Google pueden cambiar; ver [cuotas Apps Script](https://developers.google.com/apps-script/guides/services/quotas). En la práctica para este patrón:

| Límite | Valor orientativo | Nota |
|--------|-------------------|------|
| Runtime por request | **6 min** | Suficiente para un archivo; no para lotes enormes en un solo POST |
| Ejecuciones simultáneas | **~30 / usuario** (dueño del script si “Execute as me”) | Muchos usuarios subiendo a la vez pueden fallar; reintentar |
| Tamaño POST / URL Fetch | hasta **~50 MB** teórico | Base64 infla ~33%; en Huente la web corta a **8 MB** del archivo original (`drive_prueba`) |
| Cuota Drive | Cuenta Google dueña del script | No la service account |
| Web App | No recibe bien `multipart/form-data` | Siempre JSON + base64 en el body |
| Frecuencia diaria | No hay “N fotos/día” fijo documentado para Web Apps | El cuello real suele ser runtime, simultaneidad y tamaño; uso interno moderado (decenas/cientos al día) suele ir bien |

**Recomendaciones de producto**

- Fotos: comprimir/redimensionar en el cliente (p. ej. JPEG ≤ 1–2 MB) antes del POST.
- Un archivo por request; no empaquetar ZIP gigantes en un solo `doPost`.
- Si el volumen crece mucho (miles/día o archivos muy grandes): valorar Shared Drive + API, o almacenamiento en el servidor/hosting.
- Service account: útil para **leer** Drive (mayor); no confiar en ella para **escribir** en Mi unidad.

### Relación con Contabilidad

Contab Archivos sigue siendo el dueño del mayor; el camino `imagen` es independiente y no debe usarse para pisar el Excel. Detalle Contab: §7.

---

## 20. Fondos por Rendir (FxR)

**Objetivo:** capturar comprobantes (foto/PDF) en el hosting, completar datos (prioriza PC), marcar **Preparada**, revisión por **superusuario** en pantalla completa, **Aprobar** → un PDF a Drive y borrar staging. Sin OCR.

**Permiso:** `fxr` (menú «Fondos por Rendir»). Catálogos y aprobación: rol `superusuario`.

**Visibilidad:** cada usuario ve solo su inbox y sus rendiciones. El superusuario ve la cola de **preparadas**, puede abrir cualquier rendición, y tiene listado de **todas las aprobadas** (`/fxr/aprobadas` + resumen en home) con enlace al PDF en Drive.

**Perfil usuario (Config → Usuarios):** `nombre` (aparece en la rendición en vez del email) y `fxr_centro_costo_id` (CC por defecto en líneas nuevas + área sugerida). En la rendición: `comentario_firma` bajo el total (ej. «Depositar en cuenta…»).

**Rutas:** `/fxr/` — [`routes/fxr_routes.py`](../routes/fxr_routes.py). Utils: `utils/fxr_db.py`, `fxr_files.py`, `fxr_pdf.py`, `fxr_drive.py`. Templates: `templates/fxr/*`. JS: `static/js/fxr_pulir.js`. Staging: `uploads/fxr/` (gitignored).

**Flujo captura:** móvil → **Fotografiar** guarda solo en inbox; completar/pulir en PC (misma UI si se usa el celu). Inbox → seleccionar → rendir. **Pulir imagen** (`/fxr/comprobante/<id>/pulir`): 4 esquinas + perspectiva + contraste documento → JPEG Letter (cliente; OpenCV.js opcional). **Eliminar** del inbox: dueño o superusuario (`POST …/comprobante/<id>/eliminar`); borra archivo y registro.

**Edición línea:** split imagen | formulario con fondos **opacos** (sin overlay transparente).

**Revisión:** `/fxr/revision/<id>` pantalla completa; un comprobante grande a la vez; flechas / teclado ←→; panel lateral opaco con datos y chips de navegación.

**Vista previa:** hoja blanca aislada del tema oscuro; encabezados amarillos con texto negro; concepto con wrap.

**Tablas / estados / PDF:** sin cambio de modelo; correlativo al aprobar; PDF Carta a Drive vía Apps Script (`accion=imagen`).

---

*Al agregar un módulo: nueva sección en este índice + detalle (rutas, datos, reglas, archivos).*
