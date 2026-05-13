# Bitácora — Huente cPanel: comercial, dashboard, costeo y despliegue

**Objetivo:** registrar cambios recientes, reglas de negocio y **cómo trabajar en este repo** para que cualquier persona (o IA) que lea este archivo sepa **qué tocar**, **qué no romper** y **dónde seguir el hilo**.

**Última actualización (contenido):** 2026-05-12 — incluye Histórico de Productos (comparación justa + proyección en gráficos, caché navegador), vista Acumulado de Gestión, optimización de arranque del dashboard, historial de cargas comercial y cachés.

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
| `docs/QUERY_CAMBIOS_PRODUCCION.sql` | DDL / rollbacks comercial |

---

## J. Git y despliegue

- Trabajo integrado en rama **`feature/comercial-ventas-dashboard`** hasta merge a `main`.
- **Producción:** desplegar la rama elegida en el hosting; si algo falla, volver a la rama/commit estable **sin** tocar la BD salvo que el cambio haya incluido migraciones.
- **Binarios en `docs/`:** no versionar `.xlsx` pesados si no hace falta; mantener SQL y esta bitácora sí.

---

## K. Pendiente / datos que debe completar el equipo

- [ ] Plan exacto HostChile (compartido vs VPS) y límites de workers / PHP no aplica — **Python WSGI**.
- [ ] URL de producción y si hay staging.
- [ ] Política de backups MySQL antes de `revertir` masivos.
- [ ] Índices confirmados en prod sobre `fecha`, `estado`, `sucursal` (recomendado para escala ~550k filas).

---

*Fin de bitácora orientada a humanos e IA. Mantener actualizada al cerrar cada cambio relevante de comercial, dashboard o costeo.*
