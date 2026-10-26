# Bitácora de cambios — Huente cPanel

**Para qué sirve:** historial de **qué cambió y cuándo**.  
**Estado actual de cada módulo:** [`DICCIONARIO_APLICACIONES.md`](DICCIONARIO_APLICACIONES.md).  
**Cómo trabajar:** [`RESUMEN_OPERATIVO.md`](RESUMEN_OPERATIVO.md).

Al cerrar un cambio relevante: entrada breve aquí + actualizar diccionario si cambió el “cómo funciona”.

---

## 2026-10-26 — Fidelización: color de la franja del correo

- En configuración se elige el color de la barra superior del correo. Parte en rojo.

## 2026-10-19 — Fidelización: la caja muestra la espera

- La lista de la caja volvía a quedar en blanco porque faltaba el aviso de “esperando” y el refresco se cortaba antes de pintar al cliente.

## 2026-10-19 — Fidelización: el editor ya deja escribir

- El cuadro de bases y correo acepta texto al abrirlo con Editar.

## 2026-10-19 — Fidelización: editor contraído e imágenes movibles

- Las bases y el correo parten contraídos; se abren con Editar.
- La imagen se ve en el texto, se arrastra, se alinea y se cambia de tamaño.

## 2026-10-19 — Fidelización: bases legales y diseño del correo

- En configuración se editan las dos bases (programa de puntos, y confidencialidad con correos publicitarios) y la frase de cada casilla.
- El correo al cliente se puede armar con imagen, enlace, botón, columnas, tabla y salto de página. Si no se guarda un diseño, sigue el correo automático.

## 2026-10-19 — Fidelización: Excel y aceptaciones

- El administrador descarga clientes y movimientos en Excel.
- Crear cuenta exige aceptar las bases de puntos y las de confidencialidad con correos publicitarios.
- Al acreditar puntos se envía el correo si la casilla SMTP está configurada.

## 2026-10-19 — Fidelización: nueva sucursal

- Desde Premios y stickers se puede agregar otra sucursal. La cuenta del cliente es la misma en todos los locales.

## 2026-10-19 — Fidelización: cartel por sucursal

- El cartel se crea eligiendo una de las sucursales. En la caja de ese local se ve qué usuario de la sesión sumó los puntos.

## 2026-10-19 — Fidelización NFC

- Módulo nuevo: sticker abre una página, la cajera suma puntos (botones 8, 12 y 16) y el cliente recibe correo con saldo y premios.
- Permiso padre `fideliza` para el módulo completo. `fideliza.vender` es la caja; se asigna a mano en Accesos.
- Recuperación con RUT + código de un uso. Una espera a la vez y una suma por hora, contada por RUT.

## 2026-09-30 — FxR: corrección en revisión + selección arrastre

- Dueño: botón «Retirar y corregir» si está Preparada (vuelve a borrador).
- Revisor: editar línea o quitar boleta → inbox con motivo; historial + correo al dueño (`fxr_avisos`).
- Pulir: selección por clic+arrastre (rectángulo), «Reset selección»; esquinas siguen para ajuste fino.
- Revisión: recorte por arrastre y giro in-place (auto-guarda, sin ir a Pulir).

## 2026-09-23 — Reportería: aire bajo el encabezado

- El título del periodo queda separado de la franja roja y parte con mayúscula («Última semana», «Último mes»).

## 2026-09-23 — Reportería: Reporte Ventas con periodo elegido

- El formulario queda en empresa, periodicidad y un periodo base (vacío = última venta).
- El detalle de productos agrupa por familia. Se puede eliminar un reporte.
- El tipo guardado es `ventas`, para armar después un PDF con varios reportes.

## 2026-09-23 — Reportería: hojas y colores del dashboard

- Secciones 1 y 2 juntas; el consolidado y las sucursales parten en hoja nueva.
- Línea roja con área y año anterior punteado. En el detalle, las columnas dicen el año (2026 / 2025).

## 2026-09-23 — Reportería: dos sucursales por hoja

- Gráficos en azul pizarra y gris, con la leyenda separada del eje.
- En sucursales, dos columnas por hoja (gráfico y tabla). El detalle de productos compara semana actual y año anterior en cada sucursal.

## 2026-09-23 — Reportería: rojo corporativo y detalle de la semana

- Gráficos en rojo `#d80000` y negro, con aire entre el título y la leyenda.
- El detalle de productos nombra la semana y cierra con la misma semana del año anterior y la diferencia.

## 2026-09-23 — Reportería: semana actual, líneas y matriz

- El PDF abre con la última semana o mes (tortas por sucursal y familia, ticket, fichas de familias elegidas), sigue con el comparativo de sucursales, las 6 líneas año contra año y la matriz producto × sucursal.
- Filtro nuevo `familias_ficha` (columna `familias_ficha_json`).

## 2026-09-23 — Reportería: comparativo de ventas en PDF

- Módulo `/reporteria`: nombre y filtros guardados (6 semanas o 6 meses vs año anterior, empresa, sucursal, familia), PDF en neto con gráfico y variación, descarga y envío manual con adjunto.
- Tabla `reporteria_reportes`. Permiso `reporteria`. Sin cola ni cron.

## 2026-09-23 — Seremi temperatura equipos: catálogo `Activo`

- Vista e impresión listan solo equipos con `Activo=TRUE` en CSV `equipos_info`; inactivos ocultos aunque tengan lecturas; activos sin lecturas en el mes con grilla vacía.
- `routes/seremi_routes.py` — helpers `_catalogo_equipos_activos`, `_grilla_temperatura_equipos_*`.

## 2026-09-02 — DespachoWeb ruta: todos los puntos juntos en Google Maps (KML)

- Botón «Todos en Google Maps (sin ruta)» genera KML temporal y abre una sola ventana con todos los pins.

## 2026-09-02 — DespachoWeb ruta: ver solo puntos (sin trazar ruta)

- Botones «Puntos Google (sin ruta)» y «Mapa solo puntos» en `/despacho-web/ruta`.

## 2026-09-02 — DespachoWeb ruta: fix Unicode surrogates (refuerzo)

- Sanea HTML completo de `/despacho-web/ruta` además de filas MySQL (surrogates en base.html o filtros).

## 2026-09-02 — DespachoWeb ruta: fix Unicode surrogates

- `/despacho-web/ruta` fallaba con 500 si un pedido tenía caracteres inválidos en cliente/dirección (surrogates UTF-16 en MySQL). Se sanea al listar.

## 2026-09-02 — DespachoWeb: armar ruta (ORS + Google Maps)

- Pantalla `/despacho-web/ruta`: selección de pedidos Pendiente/Armado/En Ruta, reorden manual, optimización OpenRouteService (VROOM) y enlaces Google Maps directions (sin API Google).
- Utilidades `utils/despacho_web_maps.py` (URLs + split 10 paradas) y `utils/despacho_web_ors.py` (geocoding + optimización).
- Env: `ORS_API_KEY`, `ORS_ORIGEN_DESPACHO`. Ver diccionario § DespachoWeb → Armar ruta.

## 2026-08-20 — FxR: agregar inbox + completar estilo revisión

- En rendición borrador/rechazada: «Agregar del inbox» vincula staging a la rendición abierta.
- Tras «Rendir seleccionados» (y Registrar ahora): pantalla fullscreen `/fxr/rendicion/<id>/completar` (comprobante | formulario, navegación entre líneas).

## 2026-08-20 — FxR Pulir: jscanify + rotación

- Detección de papel con jscanify (OpenCV.js CDN 4.8.0 + vendor `static/js/vendor/jscanify.js` v1.4.0).
- Botones Girar ⟲/⟳ (90°) en `/fxr/…/pulir`; re-detecta tras rotar.
- Extracción con `extractPaper` + contraste; arrastre manual de esquinas se mantiene.

## 2026-08-19 — Prorrateos: comisiones según mix de Arqueo

- Cuentas Comisión Uber / Rappi / Pedidos Ya / Mercado Pago / Mesa Chilena se reparte con el `% de este tipo` del reporte mensual de tipos de pago. Mercado Pago usa el mix de Redelcom. Se puede editar % a mano en el mes o volver al mix.

## 2026-08-19 — Prorrateos: mes reciente del mayor + heredar SG

- Periodo predeterminado igual que Costeo (último YYYY-MM del mayor; el filtro se puede cambiar).
- Serv. Generales: botón para copiar la distribución del mes anterior; la matriz de 12 meses pasa a opción avanzada.

## 2026-08-19 — Costeo: periodo = mes más reciente del mayor

- Directos, GAV, simulador y rentabilidad abren en el YYYY-MM más reciente del mayor; el usuario puede cambiar el mes a cualquiera.

## 2026-08-19 — Costeo: 500 en producción

- Causa: `UnboundLocalError` al abrir Costeo si falla Drive (`mayor.xlsx`) o si el simulador corre un mes con ventas de pizza pero sin mayor de ese periodo.
- Arreglo: devolver DataFrame vacío si no carga el mayor; inicializar `costo_total_piz`; ordenar productos/sucursales como texto.

## 2026-08-19 — FxR: eliminar del inbox

- Botón Eliminar en inbox: dueño o superusuario borra comprobante staging (archivo + fila).

## 2026-08-19 — FxR: pulir, flujo captura y revisión fullscreen

- Móvil: fotografiar → inbox automático; completar/pulir prioriza PC.
- Pulir imagen (4 esquinas + perspectiva + contraste Letter) en `/fxr/comprobante/<id>/pulir`.
- Edición línea sin overlay transparente; vista previa con contraste forzado (texto negro / amarillo).
- Revisión super a pantalla completa: un respaldo grande + navegación global (flechas/teclado).

## 2026-08-12 — Notificaciones + envío Alertas Buk

- Config → **Notificaciones** (`/config/notificaciones`): destinarios en `data/notificaciones_config.json` (bloque Alertas Buk).
- Envío automático: días + hora (Chile); cron `/config/notificaciones/cron` + `MAIL_SYNC_TOKEN` (**1×/día** recomendado, no cada 15 min).
- Resumen operativo §12: reglas de rendimiento / crons livianos.
- Mailer común `utils/mail_smtp.py` + `smtp_settings()`: `SMTP_*` o fallback a casilla `IMAP_*` (Arqueo); remitente visible **Huentelauquen** (`SMTP_FROM_NAME`).
- Plantilla HTML reutilizable `utils/mail_reporte_html.py` (tablas/colores; RUT en una línea).
- Buk Alertas: botón **Enviar por correo** con confirmación de destinarios; `POST /buk/alertas/enviar`.
- Menú lateral: scroll interno (`.sidebar-nav`) para ver todos los módulos.
- Aviso firma Buk reusa el mismo mailer.

## 2026-08-11 — Deploy FxR en producción + docs

- Código FxR en rama `feature/comercial-ventas-dashboard` (commit con módulo + Drive Apps Script).
- SQL de FxR aplicado en prod (phpMyAdmin); sin guía SSH larga en resumen operativo (deploy vía cPanel / pull en `datoshuente.com`).
- Checklist deploy: `Pillow` en requirements; permiso `fxr` en Config → Accesos (`roles_config` es local al hosting); perfiles Nombre + CC FxR en Usuarios.

## 2026-08-11 — Buk calendario: descanso y rotación

- Días con `horarioTurno: "-"` → **Descanso** (no «Sin marca»). Placeholder `vacaciones: true` + «-» ignorado como vacaciones reales.
- Filtro por recinto: si la jornada está en otra sucursal → celda **↗** + banner evaluación rápida (turnos aquí / descansos / rotación).
- Alertas alineadas con la misma regla de jornada laboral.

## 2026-08-11 — Módulo Fondos por Rendir (FxR)

- Nuevo módulo `/fxr`: inbox foto/PDF (staging hosting), tipos de gasto y centros de costo globales, líneas con alerta/autorización de `n_doc` duplicado, estados borrador→preparada→aprobada/rechazada, revisión superusuario, PDF estilo formato (logo, Comercial SpA / 77.332.804-8, comentario/firma), listado aprobadas para super, perfil usuario (nombre + CC). Ver diccionario §20.

## 2026-08-10 — Prueba Drive (imágenes / Apps Script)

- Módulo local `/drive-prueba` (permiso utilidades): sube archivo a `respaldoimagenes` vía JSON al Apps Script `SubirArchivosRender`.
- Script: `accion=imagen` solo agrega archivos (no borra mayor); `accion=mayor` es el único que reemplaza `mayor.xlsx`.
- Contab envía JSON `{accion:"mayor", base64}` (mismo webhook). Ver `docs/apps_script_SubirArchivosRender.gs`.
- Documentado como patrón operativo futuro (fotos/docs pesados → Drive): diccionario §19 + resumen operativo §11 (límites Apps Script, no usar SA para escribir en Mi unidad).

## 2026-08-10 — Seguridad perimetral (externos)

- `SECRET_KEY` por env o `instance/flask_secret_key` (sin hardcode).
- Bypass login por `Host: localhost` eliminado; solo `ALLOW_DEV_LOGIN=1` local.
- `/refresh` exige sesión; redirect interno seguro.
- Rate-limit login; cookies `HttpOnly` + `SameSite=Lax`.
- Rama de restauración: `RestauracionAntesdeSeguridad`.
- Documentación reorganizada: este archivo + resumen + diccionario (reemplazan bitácora monolítica y resumen operativo antiguos).

## 2026-08-10 — UX filtros de reportes

- Reportes no auto-aplican al cambiar controles; botón «Aplicar filtros» / «Consultar» + overlay.
- Excepción: carga inicial y limpiezas cruzadas de campos.

## 2026-08-10 — Buk: calendario, alertas, overlay

- Calendario mensual (turnos + marcajes + horas netas + colación por recinto).
- Panel alertas agrupadas por tipo (colapsable) + revisadas en JSON.
- Overlay de carga al consultar/navegar (`buk_loading.js`).
- Ver diccionario § Buk.

## 2026-07-11 — Promoción vs Individual (dashboard)

- Submódulo `/dashboard/promos`: lee líneas PROMOCIÓN (excluidas del KPI principal).
- Recetas de combo, KPIs ticket/mix/acompañamiento, simulador what-if cliente.
- Ver diccionario § Dashboard → Promos.

## 2026-07-11 — Arqueo: bandeja PDF por IMAP

- Tabla `mail_pdf_inbox`, sync IMAP HostChile, UI ver/descargar/ignorar, cron con `MAIL_SYNC_TOKEN`.
- Ver diccionario § Arqueo.

## 2026-07-11 — Contab: drill-down KPIs dashboard gestión

- Cards clickeables → modal serie ene–dic YoY (`serie_kpis_mensual`).
- Ver diccionario § Contabilidad.

## 2026-07-07 — Seremi: filtros mes/año

- Vistas mensuales y prints con sucursal + mes + año; cambio aceite por período.
- Ver diccionario § Seremi.

## 2026-07-07 — Contab: macros P&amp;L opcionales

- `/contab/macros_gestion` + `macros_gestion.json` (`activo: false` por defecto = sin cambio de comportamiento).

## 2026-07-06 — Contab: KPIs unificados y resumen %

- `utils/gestion_estructura.py` compartido; dashboard e informe alineados; ventas brutas = suma 4xx; ranking sucursales.
- Ver diccionario § Contabilidad.

## 2026-05-28 — DespachoWeb

- Carga PDF unitario/masivo, validación, órdenes MySQL AppSheet, resumen productos, impresión comprobante.
- Dep `pypdf` para masivo. Ver diccionario § DespachoWeb.

## 2026-05-24 — Centro de Accesos

- `permisos_catalogo` + `data/roles_config.json`; UI `/config/accesos`; menú granular; inicio por rol.
- Fix escritura en `data/` + recarga por mtime. Ver diccionario § Auth.

## 2026-05-24 — Ventas por horario

- `/dashboard/ventas-horario` + service; comparar 7 días / detalle día. Ver diccionario § Dashboard.

## 2026-05-11 / 05-12 — Histórico de productos

- `/ventas/historico`; comparación por mismas semanas; cache JS. Ver diccionario § Ventas.

## 2026-05-11 — Acumulado de gestión

- `/contab/acumulado_gestion` (4.ª pestaña gestión). Ver diccionario § Contabilidad.

## 2026-05 — Fábrica empanadas: resumen mensual

- Bloque resumen bajo calendario (`|metrico`, % merma 1 decimal). Ver diccionario § Fábrica.

## 2026-05 (línea comercial/dashboard)

- Pipeline NETO/presentación en `sheet_cache`; import/revertir comercial + historial cargas.
- Endpoints livianos `latest-date-info` / `sucursales`.
- Presentación CLP global (`formato_dinero` / `HuenteFmt` en `base.html`).
- Rendimiento overlays dashboard. Ver diccionario §§ Ventas/Dashboard/Config/NETO.

## Arqueo de caja (módulo)

- Import sistema, terreno, cuadratura día/semana, auditoría, export, canales UI, tipos de pago, reporte mensual.
- Ver diccionario § Arqueo (estado actual completo).

## Fábrica Papaya (módulo)

- Tablas MySQL + AppSheet + informe semanal/mes/día web. Ver diccionario § Fábrica Papaya.

---

## Pendiente (no cerrado)

| Ítem | Notas |
|------|--------|
| Fábrica empanadas N.2 | Definir con ops: campo “Empanada” vs `cant_producida` y “Queso cortado”; luego ALTER + UI |
| Hosting | Plan HostChile, URL prod/staging, backups, índices ventas en prod |
| Deploy doc | Checklist cPanel paso a paso cuando el equipo lo cierre |

---

## Referencia rápida de archivos tocados en la línea comercial (histórico)

`utils/sheet_cache.py`, `utils/ventas_excel_import.py`, `routes/dashboard_routes.py`, `routes/ventas_routes.py`, `routes/contab_routes.py`, `routes/config_routes.py`, `utils/gestion_estructura.py`, `static/js/dashboard.js`, `static/js/ventas_historico.js`, `static/js/formato_huente.js`, `utils/formato_dinero.py`, blueprints arqueo/despacho/buk/fábricas según módulos.

Rama de integración frecuente: `feature/comercial-ventas-dashboard`.

---

*Entradas nuevas arriba. Detalle de funcionamiento → diccionario.*
