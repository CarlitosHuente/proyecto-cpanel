# Bitácora — Comercial, dashboard y presentación de ventas

Registro orientado a **despliegue** y **soporte**. Las reglas de negocio viven en código; aquí se resumen para quien despliegue o audite.

---

## 1. Dependencias (`requirements.txt`)

- **No se agregaron paquetes nuevos** en esta línea de trabajo (gráficos del dashboard usan Plotly por CDN, no por pip).
- Antes de producción: `pip install -r requirements.txt` en el servidor como siempre; solo hace falta actualizar el **código** y **assets estáticos** (p. ej. `static/js/dashboard.js`).

---

## 2. Reglas de negocio (memoria / tableros; la BD de ventas no se reescribe desde aquí)

### NETO comercial (`procesar_neto_comercial_mismo_que_dashboard` en `utils/sheet_cache.py`)

- **Bruto línea (con IVA en BD):** por defecto `CANTIDAD × PRECIO_LIS` (evita errores en boletas con varios ítems).
- **Excepción docena POS:** descripción contiene `DOCENA EMPANADA CRUDA` (incluye media docena) → `CANTIDAD × PRECIO`; si `PRECIO` es 0 → lista.
- **QUESO PIEZA (KG):** lista × cant; si lista 0 → `PRECIO`.
- **DESPACHO WEB:** neto sin dividir entre 1,19 (artículo sin IVA en BD según descripción).
- **Familia Promoción:** líneas excluidas (no suman en dashboard/caché comercial).

### Notas de crédito (import Excel web)

- Ya no se descartan por tipo; si vienen negativas en Excel, se importan y restan.

### Presentación — producto

- Variantes **empanada queso cruda** (web, docena, texto con empanada+queso+cruda, sin frita) → descripción unificada **`EMPANADA DE QUESO CRUDA`** (solo en memoria para dashboard, costeo que lee `obtener_datos`, export diagnóstico).

### Presentación — familia / rubro

- Limpieza de prefijos tipo `\` en rubro del POS.
- Malla / Otros / Mallas / Otro → **`Otros`**; Queso / Quesos → **`Quesos`**.
- EMPANADAS / Empanadas → **`Empanadas`**; Papaya(s), Bebida(s), Pizza(s), Helado(s) → nombre único cada uno.
- Descripción **empanada + queso + frita** → familía **`Empanadas`** (para torta/detalle coherentes).
- Líneas de empanada queso cruda (máscara) → **`Empanadas`**.

### Dashboard — KPIs

- **Ticket promedio** (comercial y agrícola): por `N_BOLETA`, suma `NETO` por comprobante, luego promedio; histórico semanal de ticket en modal (análogo al neto).
- Tercera tarjeta: ticket (sin carrusel de top productos en comercial).

### Dashboard — gráficos

- Detalle por familia: barras **horizontales** con etiquetas de producto visibles.
- Torta: familias normalizadas para no duplicar EMPANADAS / Empanadas, etc.

### Costeo

- Usa `obtener_datos("comercial")` → aplica las mismas reglas de presentación y NETO. **Empanada de queso cruda** queda una sola clave de producto (alineado al otro sistema de costeo).

---

## 3. Archivos tocados (referencia rápida)

- `utils/sheet_cache.py` — NETO, familias, empanada cruda presentación, export diagnóstico.
- `utils/ventas_excel_import.py` — notas de crédito ya no filtradas por tipo.
- `routes/dashboard_routes.py` — ticket, histórico ticket, helper ticket.
- `static/js/dashboard.js` — ticket KPI, modal ticket, barras horizontales.
- `templates/dashboard.html` — modales, tarjeta ticket, versión JS cache-bust.
- `routes/dashboard_routes.py` (export Excel) — leyenda/columnas acorde a diagnóstico.

---

## 4. Git y ramas

- **Subir a otra rama** (ej. `feature/ventas-comercial-2026`) **no modifica** la rama que hoy usás en producción (ej. `main`) hasta que hagas **merge** o cambies qué rama desplegás.
- Si algo falla: volvé a **checkout** de la rama operativa y seguís igual; la rama nueva puede borrarse o dejarse sin merge.
- **Producción:** o bien desplegás **solo** desde la rama nueva cuando esté probada, o mergeás a `main` y desplegás desde ahí. Lo importante es **no** mezclar deploy automático de `main` con merges experimentales sin probar.

---

## 5. ¿Subir `docs/` a Git?

- **No es obligatorio** para que Git funcione.
- **Sí es recomendable** si querés historial de decisiones y reglas en el repo (auditoría, onboarding, despliegue).
- Los **Excel u otros binarios grandes** en `docs/`: conviene **no** subirlos si pesan o tienen datos sensibles; esta bitácora en Markdown sí suele ir bien.

---

*Última actualización de esta bitácora: alineada al estado del proyecto con los cambios de comercial / dashboard / presentación descritos arriba.*
