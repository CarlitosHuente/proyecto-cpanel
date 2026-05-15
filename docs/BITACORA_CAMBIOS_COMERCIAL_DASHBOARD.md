# Bitácora — Huente cPanel: comercial, dashboard, costeo y despliegue

**Objetivo:** registrar cambios recientes, reglas de negocio y **cómo trabajar en este repo** para que cualquier persona (o IA) que lea este archivo sepa **qué tocar**, **qué no romper** y **dónde seguir el hilo**.

**Última actualización (contenido):** 2026-05-14 — `formato_huente.js` en `base.html` (head); contabilidad, ventas, arqueo terreno, utilidades alineados a `HuenteFmt` / % 1 decimal; fábrica calendario: resumen mes y modal con `|metrico` / `HuenteFmt.metrico` y % merma a 1 decimal; bitácora K y regla Cursor coherentes.

---

## A. Cómo está armado el sistema (visión rápida)

| Pieza | Rol |
|--------|-----|
| **Flask** (`app.py`) | App web: blueprints en `routes/`, plantillas en `templates/`, estáticos en `static/`. |
| **MySQL** | Datos de ventas comerciales/agrícolas, cargas, contabilidad, etc. Conexión en `utils/db.py` (variables de entorno en prod; credenciales locales en código solo para dev — **no replicar secretos en docs**). |
| **pandas** | Agregaciones y filtros en dashboard, costeo y utilidades que leen `obtener_datos`. |
| **Plotly (CDN)** | Gráficos del dashboard en el navegador; **no** va en `requirements.txt`. |
| **`utils/sheet_cache.py`** | Lectura comercial/agrícola desde BD, procesamiento NETO/presentación, **caché en memoria del proceso** (`_cache`). |
| **`utils/filters.py`** | `filtrar_dataframe` (sucursal, semana, año, fechas, familia). |
| **`utils/ventas_excel_import.py`** | Excel/CSV → `ventas_comercial` / `ventas_agricola` + `cargas_*`. |
| **`routes/config_routes.py`** | Pantallas de carga Excel (comercial/agrícola), revertir cargas, historial paginado comercial. |

**Ruta útil post-carga:** `/refresh` en `app.py` fuerza recarga del caché global (`refrescar_todo_el_cache`).

---

## B. Entorno local (desarrollo)

1. **Python:** en macOS se usa `python3` (ver `README.md` del repo).
2. **Virtualenv:** `python3 -m venv venv` → `source venv/bin/activate`.
3. **Dependencias:** `pip install -r requirements.txt` (no se añadieron paquetes nuevos en la línea comercial/dashboard descrita aquí).
4. **Arranque:** `python3 app.py` desde la raíz del proyecto.
5. **`.env`:** `app.py` carga `dotenv`; en producción suelen definirse `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` (ver `utils/db.py`).

**Lo que esta bitácora NO sabe (completar vos):** URL exacta del entorno local si usás proxy/puerto distinto; versión exacta de MySQL local; si hay segundo entorno de staging.

---

## C. Hosting / producción (HostChile u otro)

- El proyecto se despliega como **app Flask** + **MySQL** remoto.
- **Latencia:** con ~550k líneas en `ventas_comercial`, el cuello suele ser **CPU + I/O + consultas pesadas**, no solo “internet”. Mitigaciones aplicadas: endpoints livianos para semana inicial y sucursales (ver sección H); caché en servidor y en navegador (sección G).
- **Lo que esta bitácora NO sabe:** plan exacto de HostChile (compartido vs VPS), límites de workers, ni si hay CDN delante. **Anotalo acá cuando lo tengas** para futuras optimizaciones.

---

## D. Método de trabajo (hilos a seguir)

**Orden esperado (humano o IA):** no arrancar directo con código en temas de negocio o alcance ambiguo.

1. **Debate / alineación:** aclarar el problema, restricciones (comercial vs agrícola, dashboard, costeo, BD) y qué **no** se debe tocar.
2. **Propuesta:** resumir en pocas líneas o bullets el enfoque (archivos, rutas, riesgos, si hace falta SQL en `QUERY_CAMBIOS_PRODUCCION.sql`). Conviene que el dueño del negocio o quien pide el cambio **valide** antes de implementar.
3. **Implementación:** recién ahí commits acotados + actualizar esta bitácora si cambia comportamiento documentado.

**Sobre “pedir permiso” para ejecutar:** en este proyecto el agente **no** necesita autorización explícita del usuario para correr comandos de comprobación (tests, `DESCRIBE`, lint, etc.) en el entorno de desarrollo; sí debe **alinear el enfoque** (puntos 1–2) cuando el alcance o el criterio de negocio no esté claro, para no implementar a ciegas.

**Operativo (siempre, también en cambios pequeños):**

4. **Antes de cambiar lógica comercial/dashboard/costeo:** leer esta bitácora + el SQL maestro en `docs/QUERY_CAMBIOS_PRODUCCION.sql` (cambios de esquema).
5. **Reglas de negocio:** viven en código (`sheet_cache`, `ventas_excel_import`, `dashboard_routes`); si cambiás comportamiento, **actualizá esta bitácora** en el mismo PR/commit.
6. **Cambios de BD:** documentar en `docs/QUERY_CAMBIOS_PRODUCCION.sql` con fecha, motivo, SQL y rollback.
7. **Commits:** preferible cambios **acotados** y mensajes claros en español o inglés consistente con el repo.
8. **Rama activa de esta línea:** `feature/comercial-ventas-dashboard` (integración comercial + dashboard + cargas). `main` queda como referencia estable hasta merge explícito.
9. **Assets con caché del navegador:** al tocar `static/js/dashboard.js`, subir versión en `templates/dashboard.html` (`?v=...`).

---

## E. Cachés (importante para latencia y “datos viejos”)

| Capa | Dónde | Cuándo se invalida |
|------|--------|---------------------|
| **Servidor** | `_cache` en `utils/sheet_cache.py` dentro de `obtener_datos` | Tras `forzar_actualizacion(empresa)` (p. ej. tras import/revertir comercial) o reinicio del proceso WSGI. |
| **Navegador** | `cacheConsultas` / `cacheProductos` en `static/js/dashboard.js`; `cacheResumen` / `cacheProducto` en `static/js/ventas_historico.js` | Recarga fuerte de página o cambio de query string; no es persistente entre dispositivos. |
| **Manual** | GET `/refresh` | Recarga todo el caché del servidor definido en `refrescar_todo_el_cache`. |

**Nota para IA:** si el usuario dice “no veo la última carga”, revisar **import + forzar_actualizacion** y **/refresh** antes de depurar lógica.

---

## F. Reglas de negocio (memoria / tableros; la BD de líneas no se reescribe desde presentación)

### NETO comercial (`procesar_neto_comercial_mismo_que_dashboard` en `utils/sheet_cache.py`)

- **Bruto en BD (línea con IVA):** por defecto `CANTIDAD × PRECIO_LIS` (alinea con export web y evita errores en boletas con varios ítems).
- **Excepción docena POS:** descripción normalizada contiene `DOCENA EMPANADA CRUDA` (cubre media docena) → `CANTIDAD × PRECIO`; si `PRECIO` es 0 → `PRECIO_LIS`.
- **QUESO PIEZA (KG):** lista × cant; si lista 0 → `PRECIO`.
- **DESPACHO WEB:** neto sin `/1.19` cuando la descripción indica ese artículo (sin IVA en BD).
- **Familia Promoción:** excluida del dataframe procesado (no suma en torta/KPIs que usan ese pipeline).

### Notas de crédito (import Excel web)

- No se filtran por tipo “Nota de crédito”; si el Excel trae montos negativos, **se importan** y restan en agregados.

### Presentación — producto (solo en memoria; `ventas_comercial.des_articu` en BD intacto)

- Unificación a **`EMPANADA DE QUESO CRUDA`** cuando aplica máscara (web + docenas + texto empanada+queso+cruda, excluye frita en la rama “nombre web”).
- Export diagnóstico puede incluir columna con texto BD original donde aplique.

### Presentación — familia / rubro

- Limpieza de prefijos tipo `\` en rubro POS.
- **Otros:** Malla, Mallas, Otros, Otro → `Otros`.
- **Quesos:** Queso, Quesos → `Quesos`.
- **Empanadas / categorías:** EMPANADAS/Empanadas → `Empanadas`; Papaya(s), Bebida(s), Pizza(s), Helado(s) → nombre único.
- **Empanada queso frita por descripción:** empanada + queso + frita → familia `Empanadas` (para torta/detalle con POS).

### Dashboard — KPIs y gráficos

- **Ticket promedio** (comercial y agrícola): `N_BOLETA` → suma `NETO` por comprobante → promedio entre comprobantes. Histórico semanal en modal (paralelo al neto).
- **Tercera tarjeta:** siempre ticket (no carrusel de top productos en comercial).
- **Detalle por familia:** barras horizontales con etiquetas de producto legibles.
- **Torta:** familias normalizadas para no duplicar variantes de nombre.

### Costeo (`routes/costeo_routes.py` → `obtener_datos("comercial")`)

- Misma capa de presentación/NETO que el dashboard. **Una sola clave** `EMPANADA DE QUESO CRUDA` al agrupar ventas, alineado al otro sistema de costeo (no se usaban docenas como producto distinto allí).

---

## G. Import comercial y administración de cargas

- **Pantalla principal:** `/config/comercial` — muestra últimas **15** cargas + upload.
- **Historial completo (paginación, búsqueda, revertir cualquier ID):** `/config/comercial/cargas` — enlace desde la pantalla de import.
- **Revertir:** `POST /config/comercial/revertir/<carga_id>` — borra fila en `cargas_comercial`; líneas en `ventas_comercial` caen por **ON DELETE CASCADE** (esquema en `docs/QUERY_CAMBIOS_PRODUCCION.sql`).

---

## H. Rendimiento del dashboard (cambios recientes)

**Problema:** al entrar al dashboard, `api/latest-date-info` y `api/sucursales` llamaban a `obtener_datos()` → lectura y procesamiento de **todo** el dataset.

**Solución aplicada (sin cambiar reglas de NETO del `api/dashboard-data`):**

- **`/api/latest-date-info`:** primero intenta `SELECT MAX(fecha)` sobre `ventas_comercial` o `ventas_agricola` con el mismo filtro de `estado` que el SQL del caché; si falla, cae al método anterior con `obtener_datos`.
- **`/api/sucursales`:** primero `SELECT DISTINCT sucursal` en la tabla correspondiente; si falla, cae a `obtener_datos`.

**UX:**

- Overlay **fijo** inicial “Cargando dashboard…” (`initial-loading-overlay` en `templates/dashboard.html`) hasta el primer `renderizarDatosDashboard`.
- Overlay existente de gráficos (`charts-loading-overlay`) pasa a `position: fixed` para cubrir bien la vista durante `dashboard-data`.
- **Cache-bust** de `dashboard.js` actualizado (`?v=...` en el template).

---

## H-bis. Reporte Acumulado de Gestión (nuevo 2026-05-11)

**Problema:** el módulo de Gestión (Estado de Resultados) solo permitía ver un mes individual (Vista Mensual) o meses comparados lado a lado (Comparativo). No había forma de ver el resultado operacional **acumulado** en un rango de meses elegido libremente.

**Solución:**

- **Nueva ruta:** `/contab/acumulado_gestion` en `routes/contab_routes.py` — función `acumulado_gestion()`.
- **Nuevo template:** `templates/contab/acumulado_gestion.html` — 4.ª pestaña del módulo de Gestión.
- **Lógica:** reutiliza 100 % `calcular_matriz_gestion()` y la misma `ESTRUCTURA` del Estado de Resultados. Suma los saldos de todos los meses en el rango seleccionado (Acumulado Actual) y del mismo rango del año anterior (Acumulado Anterior). Muestra columna de Variación %.
- **Filtros:** Desde (mes) / Hasta (mes), Centro de Costo, Dist. SG, Aj. Fábrica.
- **Sin cambios de BD** ni en reglas de negocio existentes.
- **Pestañas actualizadas:** se agregó enlace "Acumulado" en `dashboard_gestion.html`, `informe_gerencial.html` y `comparativo_gestion.html`.

---

## H-ter. Histórico de Productos (nuevo 2026-05-11; reglas finales 2026-05-12)

**Problema:** no existía forma de ver la evolución histórica de un producto específico (neto, cantidad, precio) comparando año actual vs anterior, ni identificar productos con mayor crecimiento o caída.

**Solución:**

- **Nueva ruta:** `/ventas/historico` en `routes/ventas_routes.py` — función `ventas_historico()`.
- **APIs:** `/api/historico-resumen` (cards top neto, crecimiento, caída) y `/api/historico-producto` (series semanales + resumen mensual de un producto).
- **Nuevo template:** `templates/ventas_historico.html` + `static/js/ventas_historico.js` (cache-bust `?v=...` en el template al cambiar el JS).
- **Lógica:** reutiliza `obtener_datos(empresa)`; en resumen se filtra sucursal/familia sin copiar el DataFrame completo cuando basta un slice. Gráficos Plotly (CDN).
- **Filtros:** Empresa (Comercial/Agrícola), Sucursal, Familia.
- **Interacción:** cards clickeables + selector de producto → muestra 3 gráficos (neto semanal, cantidad, precio unitario) y tabla resumen mensual.
- **Sidebar:** enlace "Histórico Productos" agregado en dropdown Ventas de `base.html`.

**Comparación año actual vs anterior (comportamiento final):**

- **Cards (`/api/historico-resumen`):** el % de variación compara **las mismas semanas** del año actual y del anterior (según la última semana con datos del año actual, p. ej. Sem 1–18 en ambos años). Así no se penaliza un año parcial frente a un año completo.
- **Etiqueta en pantalla:** los títulos de sección muestran el rango de semanas comparado (ej. `Sem 1-18 — 2026 vs 2025`).
- **Detalle de producto (`/api/historico-producto`):** los **gráficos** usan el año anterior **completo** (52 semanas) para ver tendencia y “proyección”; los **KPIs / totales** de variación siguen alineados al periodo comparable (mismas semanas y totales por meses comparables en la fila de totales).
- **Caché en navegador:** `static/js/ventas_historico.js` guarda en memoria las respuestas de resumen y de detalle por combinación de filtros/producto; repetir la misma consulta no vuelve a llamar al servidor hasta recargar la página.
- **Presentación $ en cards:** montos en pesos **sin decimales** (`HuenteFmt` en `static/js/formato_huente.js`, incluido desde `base.html`). Cards de crecimiento/caída muestran la **variación en $** (entero) como importe principal y el neto actual/anterior como línea secundaria.

---

## I. Archivos clave tocados en esta línea (referencia)

| Archivo | Tema |
|---------|------|
| `utils/sheet_cache.py` | NETO, presentación familia/producto, SQL comercial, caché, export diagnóstico |
| `utils/ventas_excel_import.py` | Import Excel/CSV, notas de crédito |
| `routes/dashboard_routes.py` | API dashboard, ticket, históricos, export Excel, **latest-date/sucursales livianos** |
| `routes/contab_routes.py` | Informe gerencial, comparativo, dashboard gestión, **acumulado gestión** |
| `routes/ventas_routes.py` | Ventas detalle/resumen, **histórico de productos** |
| `routes/config_routes.py` | Comercial upload, revertir, **historial paginado** |
| `templates/config/comercial_upload.html` | UI import + enlaces |
| `templates/config/comercial_cargas_historial.html` | Lista completa de cargas |
| `templates/contab/acumulado_gestion.html` | **Vista acumulado de gestión (nueva)** |
| `templates/ventas_historico.html` | **Vista histórico de productos (nueva)** |
| `static/js/ventas_historico.js` | **JS histórico: cards, gráficos Plotly, tabla** |
| `templates/dashboard.html` | Overlays, modales ticket/neto, versión JS |
| `static/js/dashboard.js` | KPIs, caché navegador, modales, barras, **overlay inicial** |
| `routes/arqueo_caja_routes.py` | Blueprint arqueo: import, terreno, cuadratura, auditoría, export, canales UI, bundles eliminar/notas |
| `utils/arqueo_caja_import.py` | Lectura Excel arqueo, normalización de canal, parse montos |
| `utils/arqueo_caja_canal_ui_config.py` | Etiquetas/orden canales → JSON en `instance/` |
| `utils/formato_dinero.py` | `dinero_presentacion`, **`metrico_presentacion`** (kg, etc.; máx. 2 dec.) |
- **JavaScript:** `static/js/formato_huente.js` (`HuenteFmt`); carga global en `templates/base.html` (head). No formatear CLP con `toLocaleString("es-CL")` sobre floats sin fijar cero decimales.
| `utils/arqueo_caja_canales.py` | Lista legacy (puede quedar sin uso; canales “admin” salen de `arqueo_caja_lineas`) |
| `templates/arqueo_caja/*.html` | UI arqueo (terreno, cuadratura, auditoría, import, canales, flashes) |
| `docs/QUERY_CAMBIOS_PRODUCCION.sql` | DDL `arqueo_caja_*` (cargas, líneas, terreno; índices, `cod_comp`, caja/propina) |
| `instance/arqueo_canales_ui.json` | Preferencias UI canales; **no versionar** si es local; se crea al guardar en “Administrar nombres de canales” |

---

## J. Git y despliegue

- Trabajo integrado en rama **`feature/comercial-ventas-dashboard`** hasta merge a `main`.
- **Producción:** desplegar la rama elegida en el hosting; si algo falla, volver a la rama/commit estable **sin** tocar la BD salvo que el cambio haya incluido migraciones.
- **Binarios en `docs/`:** no versionar `.xlsx` pesados si no hace falta; mantener SQL y esta bitácora sí.

---

## K. Presentación de dinero (regla de proyecto)

- **En pantalla y exportes orientados a usuarios**, los montos en **pesos chilenos** se muestran **sin decimales** (redondeo HALF_UP al entero más cercano). Separador de miles: punto (ej. `12.345.678`).
- **Implementación:** `utils/formato_dinero.py` (`dinero_presentacion`) y filtro Jinja `{{ valor|dinero }}` registrado en `app.py`.
- **JavaScript:** `static/js/formato_huente.js` — `HuenteFmt.peso`, `HuenteFmt.pesoConSigno`, `HuenteFmt.metrico`; **carga global** en `templates/base.html` (head). Subir `?v=` en el template al cambiar el JS. No formatear CLP con `toLocaleString("es-CL")` sobre floats sin fijar cero decimales (evita valores tipo `$243.361,345`).
- **Cantidades no monetarias** (kg, litros, m³, etc.): como máximo **2 decimales** en presentación; sin forzar decimales innecesarios. **Python/Jinja:** filtro `{{ valor|metrico }}` → `metrico_presentacion` en el mismo módulo.
- **Porcentajes** (variación vs anterior, participación, etc.): criterio habitual **1 decimal** (`%.1f` / `toFixed(1)`), salvo requisito explícito distinto.
- **Cálculos internos** (cuadratura, import, BD) siguen usando `Decimal` con la precisión que defina el esquema; solo cambia la **presentación** salvo que se indique lo contrario en una pantalla específica.

**Regla Cursor:** `.cursor/rules/huente-presentacion-trabajo.mdc` (`alwaysApply`) resume lo anterior para el agente.

## M. Módulo Arqueo de caja (`/arqueo-caja`)

**Objetivo:** importar movimientos **sistema** (Excel) por sucursal, cargar totales **terreno** por día/caja/canal, **cuadrar** terreno vs sistema por canal, revisar **auditoría** y exportar Excel.

### Datos (MySQL)

| Tabla | Rol |
|--------|-----|
| `arqueo_caja_cargas` | Cabecera de carga (archivo, sucursal, usuario, contador líneas). Borrar carga en cascada borra líneas. |
| `arqueo_caja_lineas` | Líneas import: `fec_compr`, `n_comp`, `cod_comp`, `desc_cta`, `debe`, `haber`, `sucursal_id`, `carga_id`. Base para **canales** (texto único `desc_cta` normalizado). |
| `arqueo_caja_terreno` | Una fila por `(sucursal_id, fecha, canal_norm, caja)`: `monto`, `propina` (info), `notas` (hasta 500), `canal_raw` (etiqueta mostrada). **UK** por sucursal+fecha+canal_norm+caja. |

Esquema y migraciones comentadas: `docs/QUERY_CAMBIOS_PRODUCCION.sql`.

### Rutas principales

| Ruta | Descripción |
|------|----------------|
| `GET/POST …/import` | Subir Excel sistema → `cargas` + `lineas`. |
| `POST …/revertir/<carga_id>` | Elimina carga y líneas asociadas. |
| `GET/POST …/terreno` | Barra sucursal+caja+fecha (GET al cambiar barra); **grilla** de montos por canal; POST masivo `bulk_terreno`. |
| `POST …/terreno/bundle/eliminar` | Borra **todas** las filas terreno de un día/sucursal/caja. |
| `POST …/terreno/bundle/notas` | `UPDATE` el mismo `notas` en **todas** las filas terreno de ese día/caja (no inserta filas si no hay captura). |
| `GET …/terreno/editar/<id>` | **GET** redirige a terreno con sucursal/fecha/caja (edición vía grilla). POST reservado por compatibilidad. |
| `GET/POST …/canales-ui` | Admin **presentación**: etiqueta por canal canónico + orden; persiste en `instance/arqueo_canales_ui.json` (**sin tabla nueva**). Canales listados = `DISTINCT` de `arqueo_caja_lineas` (global). |
| `GET …/cuadratura` | **Vista día** o **vista semana** (`?vista=semana`): semana lun–dom que contiene la fecha elegida. |
| `GET …/cuadratura/auditoria` | Resumen por canal + detalle líneas; **orden** por columnas (`ord_res`/`dir_res`, `ord_det`/`dir_det`). |
| `GET …/cuadratura/export.xlsx` | Excel resumen + detalle + terreno (montos enteros en hojas exportadas). |

### Terreno — UX

- **Canales en grilla:** unión de (1) `desc_cta` distintos de **toda** la BD en `arqueo_caja_lineas` y (2) canales ya guardados en terreno para esa sucursal/fecha/caja. Orden: JSON `sort` + nombre.
- **Esperado sistema:** neto import (DEBE−HABER) **solo** para la sucursal y fecha elegidas (columna informativa).
- **Etiquetas visibles:** configurables en “Administrar nombres de canales”; la conciliación sigue por `canal_norm` (hidden en el POST).
- **Capturas guardadas:** tabla **agrupada** por día·sucursal·caja. Filtros de lista: **solo sucursal y caja** (sin filtro por fecha en la consulta; orden por fecha descendente). El formulario inferior lleva `fecha` **oculta** para conservar la fecha de la grilla superior al filtrar la lista.
- **Enter:** foco monto → propina → siguiente fila.

### Cuadratura — día y semana

- **Día:** por canal; totales **diferencia** y **propinas** terreno; observación del día/caja vía `terreno/bundle/notas`.
- **Semana:** por cada día, **Caja 1 y Caja 2** (hasta 14 filas): diferencia total día/caja, suma propinas, estado, observación, enlaces a cuadratura día y auditoría. **Pie:** suma semanal de diferencias y propinas (solo días/caja con datos).
- **Conciliado:** `total_diff == 0` y hay sistema o terreno.

### Presentación monetaria

Ver **sección K** (`|dinero` en plantillas y reglas de export).

### Permisos

Rutas con `@permiso_modulo("arqueo_caja")` (detalle de roles según tu `utils/auth` / BD).

---

## L. Pendiente / datos que debe completar el equipo

- [ ] Plan exacto HostChile (compartido vs VPS) y límites de workers / PHP no aplica — **Python WSGI**.
- [ ] URL de producción y si hay staging.
- [ ] Política de backups MySQL antes de `revertir` masivos.
- [ ] Índices confirmados en prod sobre `fecha`, `estado`, `sucursal` (recomendado para escala ~550k filas).

---

## N. Próximos pasos — Fábrica de empanadas (producción)

**Contexto actual:** ya existe el calendario en `routes/fabrica_routes.py` → `/fabrica/calendario`, plantilla `templates/fabrica/calendario.html`, datos en tabla **`fabrica_produccion`** (campos usados en UI: entre otros `fecha`, `cant_producida`, `queso_inicial_gr`, `queso_merma_gr`, `rendimiento`, stocks; el detalle día a día abre modal con promedio queso **(queso_inicial_gr − queso_merma_gr) / cant_producida**).

### N.1 Resumen mensual bajo el calendario

**Objetivo:** para el **mes y año** que se está viendo, mostrar **debajo de la grilla del calendario** un bloque de resumen (tarjetas o fila compacta) con:

| Indicador | Definición sugerida (alinear con negocio antes de implementar) |
|-----------|----------------------------------------------------------------|
| **Total elaborado en el mes** | Suma de `cant_producida` (o unidad acordada: empanadas elaboradas) de todas las filas del mes con dato. |
| **Queso utilizado en el mes** | Suma de **queso neto** por día: suma de `(queso_inicial_gr − queso_merma_gr)` en cada fila del mes, **o** otra regla si “utilizado” debe ser solo inicial u otra cuenta. |
| **Merma total en el mes** | Suma de `queso_merma_gr` en el mes. |
| **Promedio de queso (g) por empanada (mes)** | `sum(queso_inicial_gr − queso_merma_gr) / sum(cant_producida)` solo si el denominador es mayor que cero; los días sin producción no aportan al denominador. |

**UX:** mismo selector de mes/año que hoy; el resumen se recalcula con la misma consulta ampliada (agregados `SUM`/`COUNT` sobre el rango del mes).

**Técnico:** extender la query en `calendario_produccion()` o segunda query ligera; pasar al template variables `resumen_mes: dict`; documentar en `QUERY_CAMBIOS_PRODUCCION.sql` si se agregan columnas o vistas.

### N.2 Nuevos datos de producción a registrar

Además de los campos actuales del día, incorporar **dos magnitudes explícitas** (nombres tentativos; validar con operaciones):

1. **Empanada** — cantidad o flujo acordado (p. ej. unidades de empanada asociadas a esa jornada de línea, si debe diferenciarse de `cant_producida` o refinarse).
2. **Queso cortado para empanada** — gramos o kg según estándar del resto del formulario (alinear con `queso_inicial_gr` / merma para no duplicar concepto: definir si es “cortado del día”, “asignado a línea”, etc.).

**Implementación típica:** `ALTER TABLE fabrica_produccion ADD COLUMN …` (tipos `DECIMAL` o `INT` según caso) + formulario en modal “Nuevo registro” / edición + validación; permisos existentes `@permiso_modulo('fabrica')`.

**Pendiente de definición con el usuario:** si “empanada” y `cant_producida` conviven como la misma métrica o dos conceptos distintos (elaborado vs otra categoría), y cómo cruza **queso cortado** con queso inicial/merma para no confundir KPIs del resumen N.1.

---

*Fin de bitácora orientada a humanos e IA. Mantener actualizada al cerrar cada cambio relevante de comercial, dashboard o costeo.*
