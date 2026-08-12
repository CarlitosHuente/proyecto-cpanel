# Resumen operativo — Huente cPanel

**Para qué sirve este archivo:** cómo trabajar en el proyecto (equipo + IA), entornos, deploy, reglas transversales, rendimiento y checklist.  
**Lectura obligatoria** al iniciar cualquier cambio (humano o IA): este resumen primero; luego el diccionario del módulo tocado.  
**No documenta módulos:** eso vive en [`DICCIONARIO_APLICACIONES.md`](DICCIONARIO_APLICACIONES.md).  
**No es historial de cambios:** eso vive en [`BITACORA.md`](BITACORA.md).

| Documento | Contenido |
|-----------|-----------|
| **Este** | Método de trabajo, stack, entornos, SQL, presentación, seguridad, **rendimiento / cron** |
| [`DICCIONARIO_APLICACIONES.md`](DICCIONARIO_APLICACIONES.md) | Cómo funciona cada módulo (rutas, datos, reglas, archivos) |
| [`BITACORA.md`](BITACORA.md) | Qué cambió y cuándo (changelog) |
| [`QUERY_CAMBIOS_PRODUCCION.sql`](QUERY_CAMBIOS_PRODUCCION.sql) | DDL/DML a replicar en producción |

---

## 1. Finalidad

ERP interno web para operación, ventas, control sanitario y gestión financiera/contable de Huente: KPIs comerciales, SEREMI, contabilidad, flujo de caja, sucursales, fábricas, Buk RRHH/asistencia, despacho web, arqueo de caja, configuración de accesos.

---

## 2. Stack

| Capa | Tecnología |
|------|------------|
| Backend | Python + Flask monolítico; blueprints en `routes/`; lógica en `services/` y `utils/` |
| Frontend | Jinja2 + JS vanilla + Bootstrap 5 (CDN); Plotly / Chart.js donde aplique |
| Datos | MySQL (`pymysql`, `utils/db.py` + `utils/env_config.py`) |
| Integraciones | Google Sheets CSV / Drive (lectura SA + escritura vía Apps Script); Buk RRHH + Buk Asistencia; IMAP/SMTP (casilla HostChile) |
| Config local | `.env` (plantilla `.env.example`); JSON en `data/` / `instance/` según módulo |

**Regla HostingChile:** priorizar compatibilidad Linux/cPanel/Passenger; stack simple (`Flask + MySQL + templates`); rutas case-sensitive; no dependencias que el hosting no soporte.

---

## 3. Documentación obligatoria al crear o cambiar un módulo

> **Regla fija:** cada vez que se **cree un módulo nuevo** (o se agregue una pieza grande a uno existente), debe quedar descrito en [`DICCIONARIO_APLICACIONES.md`](DICCIONARIO_APLICACIONES.md): objetivo, rutas, tablas/datos, reglas de negocio, permisos, archivos clave y cómo se usa cada parte relevante.

Además, en el mismo cambio:

1. Entrada breve en [`BITACORA.md`](BITACORA.md) (fecha + qué cambió).
2. Si hay SQL: bloque en `QUERY_CAMBIOS_PRODUCCION.sql` (fecha, motivo, SQL, rollback).
3. Si toca JS cacheado: subir `?v=` en el template que lo enlaza.
4. Si cambia comportamiento de UI/negocio ya documentado: actualizar el **diccionario** (estado actual), no solo la bitácora.

No duplicar el mismo detalle en los tres archivos: el diccionario es la verdad del “cómo funciona hoy”; la bitácora es el “qué pasó”.

---

## 4. Método de trabajo (equipo + IA)

**Orden obligatorio** en cambios de negocio o alcance ambiguo:

0. En desarrollo, pruebas/scripts/lint se ejecutan **sin pedir RUN** al usuario en cada paso (salvo acciones destructivas o deploy a producción).
1. Entender objetivo, alcance e impacto (**incluir costo en CPU/red/hosting** — ver §12).
2. Proponer 1–3 enfoques (archivos, riesgos, BD).
3. Validar el camino con quien pide el cambio.
4. Implementar (commits acotados).
5. Validar (módulo tocado + un flujo transversal).
6. Documentar (diccionario y/o bitácora según §3).
7. Preparar producción (checklist §8).

**Principio:** estabilidad, continuidad operacional y **rapidez percibida** en hosting compartido.

**Git**

- Trabajar en `feature/*` o `fix/*`; no en `main` directo.
- Rama activa de integración reciente: `feature/comercial-ventas-dashboard` (hasta merge explícito a `main`).
- Evitar `push --force` en `main`.
- Punto de restauración seguridad (2026-08-10): rama `RestauracionAntesdeSeguridad`.

**Filtros de reportes (UX)**

- No auto-consultar al cambiar controles.
- Confirmar con botón («Aplicar filtros» / «Consultar») + overlay de carga.
- Excepción: carga inicial de página y limpiezas cruzadas de campos (sin llamar al API de datos).

**Presentación de números** (detalle también en regla Cursor `.cursor/rules/huente-presentacion-trabajo.mdc`)

- Pesos CLP en UI: **sin decimales** (`|dinero` / `HuenteFmt.peso`).
- Cantidades (kg, etc.): máx. **2 decimales** (`|metrico` / `HuenteFmt.metrico`).
- Porcentajes en KPIs: **1 decimal**.

---

## 5. Entorno local

1. `python3 -m venv venv` → `source venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copiar `.env.example` → `.env` y completar `DB_*` (y tokens que uses).
4. `python3 app.py` desde la raíz.
5. Opcional desarrollo sin login: `ALLOW_DEV_LOGIN=1` en `.env` **solo local** (nunca en cPanel).

Variables habituales: ver `.env.example` (`DB_*`, `SECRET_KEY`, `BUK_*`, `IMAP_*`, `MAIL_SYNC_TOKEN`, `SMTP_*` opcionales, etc.). Lectura central: `utils/env_config.py`.

---

## 6. Producción (HostChile / cPanel)

- App Flask + MySQL remoto; reinicio WSGI/Passenger tras deploy.
- Variables en Application Environment de cPanel (no versionar secretos).
- `SECRET_KEY`: opcional en env; si falta, se crea `instance/flask_secret_key` (gitignored). Tras rotar clave → re-login.
- Latencia: tablas grandes (`ventas_comercial` ~550k filas) → CPU/I/O; hay endpoints livianos y caché (ver diccionario § Cachés).
- Binarios pesados (`.xlsx`/PDF de prueba) en `docs/`: preferir no versionar si no son necesarios; sí versionar SQL y estos tres markdown.
- App en hosting: directorio del dominio `datoshuente.com` (código Flask + Passenger). SQL vía phpMyAdmin; deps/reinicio desde la app Python de cPanel cuando aplique.

**Checklist deploy**

1. Backup DB (sobre todo si hay SQL).
2. Pull de rama aprobada.
3. `pip install -r requirements.txt` si cambiaron deps (FxR añade `Pillow`; verificar que importen `PIL`, `reportlab`, `pypdf`).
4. Ejecutar bloques nuevos de `QUERY_CAMBIOS_PRODUCCION.sql` si aplica (phpMyAdmin).
5. Reiniciar app.
6. Smoke test: login, módulo tocado, un flujo transversal; Contab mayor sigue OK si se tocó Apps Script.

**Rollback:** volver a commit/rama estable; no tocar BD salvo que el cambio hubiera incluido migraciones.

---

## 7. Política SQL

Toda modificación de estructura/datos a replicar en prod → `docs/QUERY_CAMBIOS_PRODUCCION.sql` con: fecha, autor/motivo, entorno probado, SQL, rollback si aplica.  
DDL Papaya: también `QUERY_FABRICA_PAPAYA_PRODUCCION.sql` (+ datos `DATA_FABRICA_PAPAYA_IMPORT.sql` si corresponde).

---

## 8. Seguridad operativa (resumen)

Enfoque actual: mitigar **ataques externos** (sin cuenta). Detalle de cambios en bitácora (2026-08-10).

- Login con email/password hasheado; usuarios creados por admin.
- Sin bypass por cabecera `Host`; solo `ALLOW_DEV_LOGIN` local.
- `/refresh` requiere sesión.
- Rate-limit de intentos fallidos de login.
- Cookies: `HttpOnly` + `SameSite=Lax`; opcional `SESSION_COOKIE_SECURE=1` en HTTPS.
- Endpoints de cron (`MAIL_SYNC_TOKEN`): no exponer el token; no loguear el valor.

---

## 9. Checklist diario del equipo

- [ ] Rama correcta (`feature/*` / `fix/*`)
- [ ] `git pull`
- [ ] App local OK
- [ ] Probar módulo tocado + 1 flujo transversal
- [ ] Actualizar diccionario y/o bitácora (§3)
- [ ] Commit claro; PR con impacto y prueba manual

---

## 10. Pendientes operativos (equipo)

- [ ] Plan HostChile (compartido vs VPS), workers, URL prod / staging
- [ ] Política backups MySQL antes de revertir cargas masivas
- [ ] Confirmar índices en prod (`fecha`, `estado`, `sucursal`) en tablas de ventas
- [ ] Documentar paso a paso deploy cPanel cuando esté cerrado (`DEPLOY_CPANEL.md` si se escribe)

---

## 11. Guardar archivos/fotos en Drive desde la web (patrón oficial)

**Usar Apps Script Web App** (`SubirArchivosRender`), no la service account, para escribir en la carpeta compartida de contabilidad / `respaldoimagenes`.

- Contrato, URL, acciones `mayor` vs `imagen`, límites: **[`DICCIONARIO_APLICACIONES.md` §19](DICCIONARIO_APLICACIONES.md#19-drive-vía-apps-script-archivos--fotos)**.
- Código del script: [`docs/apps_script_SubirArchivosRender.gs`](apps_script_SubirArchivosRender.gs).
- Tras cambiar el `.gs` en Google: siempre **Nueva versión** de la implementación.
- **FxR:** staging de comprobantes en `uploads/fxr/`; a Drive solo el PDF final al aprobar (diccionario §20).

---

## 12. Rendimiento y carga en hosting (prioridad alta)

El sitio corre en **cPanel / Passenger compartido**: CPU, workers y memoria son limitados. Toda feature nueva debe **velar por la rapidez del sistema**.

**Reglas**

- Preferir trabajo **bajo demanda** (usuario pulsa Consultar / Enviar) frente a jobs frecuentes en background.
- **No** diseñar crons agresivos (cada 1–15 min) “por si acaso”. Preferir **1 ejecución/día** (o solo los días de negocio) alineada a la hora configurada.
- Llamadas a **Buk / APIs externas** y reportes de alertas son caros: no recalcularlos en cada tick de cron si no corresponde enviar.
- Consultas MySQL: filtrar por fecha/índices; evitar full scans en tablas grandes; reutilizar cachés existentes (`/refresh`, sheet_cache) en vez de invalidar a ciegas.
- UI: overlays de carga en acciones lentas; no auto-disparar APIs pesadas al mover un filtro.
- Correo: una casilla HostChile (`IMAP_*` recepción Arqueo; mismo fallback para SMTP salida). Mailer común `utils/mail_smtp.py` + plantilla `utils/mail_reporte_html.py`.

**Notificaciones / cron (Alertas Buk y futuros)**

- Config UI: `/config/notificaciones` → destinarios + días + hora (Chile).
- Endpoint: `GET|POST /config/notificaciones/cron?token=MAIL_SYNC_TOKEN` (o header `X-Mail-Sync-Token`).
- **Recomendado en cPanel:** un cron **diario** a la hora elegida (ej. `curl` a las 08:00 sobre el dominio prod), no cada 15 minutos. Si el día no está marcado o ya se envió hoy, el endpoint sale rápido sin armar el reporte Buk.
- Envío manual sigue disponible en Buk → Alertas (sin cron).

**Al diseñar jobs futuros:** preguntar “¿puede ser 1×/día o bajo demanda?” antes de proponer polling frecuente.

---

*Documento operativo. Al crear módulos: actualizar el diccionario (obligatorio). IA: leer este archivo al inicio de cada tarea.*
