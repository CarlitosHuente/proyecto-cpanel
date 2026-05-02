# Proyecto Huente CPanel - Resumen Operativo

## 1) Finalidad del proyecto

Esta aplicacion es un ERP interno web para operacion, ventas, control sanitario y gestion financiera/contable de Huente.

En terminos practicos, centraliza:

- ventas y KPIs comerciales;
- control sanitario SEREMI (temperaturas, aceite, recepcion, personal);
- contabilidad y reportes de gestion;
- flujo de caja y tesoreria;
- operacion de sucursales (pizarra/tareas/solicitudes);
- configuracion de usuarios, roles, permisos, categorias y productos.

---

## 2) Stack y arquitectura

### Backend

- `Python` + `Flask` monolitico.
- Blueprints en `routes/`.
- Logica de negocio y helpers en `services/` y `utils/`.
- Renderizado server-side con plantillas `Jinja2` en `templates/`.

### Frontend

- HTML + JS vanilla.
- `Bootstrap 5` (CDN).
- Graficos con `Plotly` y `Chart.js` en vistas puntuales.

### Datos e integraciones

- `MySQL` via `pymysql` (`utils/db.py`).
- `Google Sheets` (CSV publicados) y `Google Drive API` (service account) para fuentes y archivos (`utils/sheet_cache.py`, `utils/drive_utils.py`).
- Archivos JSON locales de configuracion (`permisos.json`, `precios.json`).

---

## 3) Modulos principales (mapeo funcional)

- `auth`: login local Huente (`email` + `password`) y cierre de sesion.
- `dashboard`: KPIs y APIs de datos de ventas.
- `ventas`: analisis de ventas y exportacion Excel.
- `precios`: mantenimiento de listas/matriz de precios.
- `seremi`: controles sanitarios y vistas imprimibles.
- `contab`: mayor, prorrateos, clasificaciones, informe gerencial, comparativos.
- `costeo`: mapeo, costos directos, reglas, GAV, simuladores y rentabilidad.
- `finanzas`: flujo de caja, banco, pagos y respaldos.
- `sucursales`: pizarra operativa, historial, tareas, comprobantes, anuncios.
- `config`: usuarios, roles, permisos, categorias, productos, anuncios, carga agricola.
- `fabrica` / `utilidades`: funcionalidades complementarias.

---

## 4) Plataformas y entornos que hoy usa el sistema

## Plataforma de ejecucion

- Local de desarrollo (Mac + venv + `python3 app.py`).
- Produccion en hosting tipo cPanel/Passenger (segun comentarios del codigo y variables de entorno para DB/PORT).

## Plataformas externas integradas

- MySQL (local y/o hosting).
- Google Drive API (subidas y lectura de archivos).
- Google Sheets publicados como CSV.
- GitHub (versionado y ramas).

---

## 5) Configuracion de entorno (local vs produccion)

### Variables esperadas por codigo

- `DB_HOST`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `PORT` (produccion)

### Comportamiento actual del codigo

- Si no existen variables DB, `utils/db.py` cae a conexion local hardcodeada (`localhost`, `root`, `huente_app`).
- `app.py` corre en `0.0.0.0` con puerto por variable `PORT` (default `10000`).
- En local, `utils/auth.py` tiene bypass automatico de login para `localhost/127.0.0.1`.

---

## 6) Riesgos detectados para no perder local/produccion

1. **Credenciales sensibles en repositorio**
   - Existe `credenciales_google.json` en raiz.
   - Existe password local hardcodeado en `utils/db.py`.
   - `app.secret_key` esta hardcodeada.

2. **Acoplamiento de entorno**
   - Fallback de DB a local hardcodeado puede ocultar errores de configuracion.
   - Bypass de login local puede provocar sorpresas si se replica en ambientes no previstos.

3. **README con comando peligroso**
   - Aparece `git push origin main --force`; debe evitarse en flujo normal.

---

## 7) Metodo de trabajo recomendado (seguro local -> produccion)

### Rama y cambios

- Trabajar siempre en ramas tipo `feature/*` o `fix/*`.
- No trabajar directo en `main`.
- Abrir PR y hacer merge a `main` solo cuando este validado.
- Evitar `push --force` en `main`.

### Configuracion por entorno

- Crear y usar archivo `.env` local (no versionado).
- En produccion, definir variables en cPanel (Application Environment / Passenger).
- Eliminar secretos del repo y moverlos a variables/secret manager.

### Despliegue

- Estandarizar deploy con checklist:
  1) backup DB;
  2) pull de rama aprobada;
  3) instalar dependencias;
  4) migraciones/scripts SQL si aplica;
  5) reinicio app;
  6) smoke test de rutas criticas.

### Validacion minima antes de subir

- Login local y permisos por rol.
- Dashboard + ventas.
- Seremi (al menos una vista y un print).
- Contab/prorrateos.
- Flujo de caja/pagos.
- Pizarra sucursales.

---

## 8) Estandar minimo que conviene implementar ahora

1. Crear `.env.example` sin secretos con todas las variables requeridas.
2. Mover `secret_key`, DB y rutas sensibles a variables.
3. Agregar `.gitignore` para evitar versionar credenciales y archivos de entorno.
4. Definir documento de deploy cPanel (paso a paso) en `docs/DEPLOY_CPANEL.md`.
5. Agregar respaldo automatico previo a cambios de esquema/datos.

---

## 9) Checklist operativo diario (equipo)

- Confirmar rama correcta (`feature/*`).
- Sincronizar con remoto (`git pull`).
- Ejecutar app local.
- Probar modulo tocado + 1 flujo transversal.
- Commit con mensaje claro.
- PR con resumen de impacto y prueba manual.

---

## 10) Preguntas pendientes para cerrar una operacion 100% robusta

1. Cual es el flujo exacto de despliegue actual en cPanel (comando, ruta y reinicio)?
2. Donde viven hoy las variables reales de produccion?
3. Existe base de datos separada para staging?
4. Hay respaldo automatico de MySQL antes de cada deploy?
5. Quieren mantener bypass local de login o reemplazarlo por flag `FLASK_ENV=development`?

---

## 11) Restriccion clave de compatibilidad (HostingChile Linux)

Para este proyecto se define como regla principal:

- priorizar compatibilidad con HostingChile (Linux/cPanel) por sobre cambios "modernos" de framework;
- no introducir dependencias o features que requieran runtime no soportado por cPanel, salvo necesidad critica;
- mantener stack simple y portable (`Flask + MySQL + templates`) mientras no exista plan formal de migracion.

Buenas practicas concretas para evitar quiebres local -> produccion:

- usar rutas y nombres de archivo compatibles con Linux (case-sensitive);
- evitar comandos o scripts amarrados a Windows;
- fijar versiones de librerias en `requirements.txt` cuando ya esten probadas en hosting;
- probar siempre en un entorno local lo mas parecido posible a Linux antes de deploy.

---

## 12) Metodologia de trabajo acordada (equipo + IA)

Flujo de trabajo obligatorio por tarea:

1. **Entender primero**: se pregunta objetivo, alcance e impacto.
2. **Proponer opciones**: se presentan 1-3 alternativas con pros/contras.
3. **Debatir breve**: se valida contigo el camino elegido.
4. **Implementar**: recien aqui se escribe/modifica codigo.
5. **Validar estricto**: pruebas funcionales y chequeo de no regresion.
6. **Documentar**: dejar evidencia de cambios tecnicos y operativos.
7. **Preparar produccion**: checklist de deploy + pasos de rollback.

Principio rector:

- priorizar estabilidad y continuidad operacional; cada cambio debe reducir riesgo, no aumentarlo.

---

## 13) Politica SQL para replicar en produccion

Toda modificacion a BD debe quedar registrada en:

- `docs/QUERY_CAMBIOS_PRODUCCION.sql`

Regla:

- ningun cambio de estructura/datos se considera cerrado si no deja su query en ese archivo, con fecha, contexto y modulo afectado.

Formato minimo sugerido por bloque:

- fecha;
- autor;
- motivo;
- entorno probado;
- SQL de cambio;
- SQL de rollback (si aplica).

---

Documento generado a partir del estado actual del repositorio y criterios operativos acordados.
