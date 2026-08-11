/**
 * SubirArchivosRender — Código.gs
 *
 * Patrón oficial Huente: ver docs/DICCIONARIO_APLICACIONES.md §19
 * y docs/RESUMEN_OPERATIVO.md §11.
 *
 * IMPORTANTE: solo reemplaza mayor.xlsx si accion === "mayor".
 * accion === "imagen" → crea archivo NUEVO en respaldoimagenes (no borra nada).
 *
 * Contab y Prueba Drive deben enviar JSON (Content-Type: text/plain).
 * Compat: body base64 crudo (sin {) sigue actualizando el mayor.
 */

function doPost(e) {
  var raw = "";
  try {
    if (!e || !e.postData || e.postData.contents == null) {
      return ContentService.createTextOutput(
        "ERROR: sin postData (no uses Ejecutar; llama desde la web)"
      );
    }
    raw = String(e.postData.contents);
    var data = intentarJson(raw);

    if (data) {
      if (data.accion === "imagen") {
        return guardarEnRespaldoImagenes(data);
      }
      if (data.accion === "mayor") {
        if (!data.base64) {
          return ContentService.createTextOutput("ERROR: falta base64 para mayor");
        }
        return reemplazarMayor(data.base64);
      }
      return ContentService.createTextOutput(
        "ERROR: accion desconocida (use mayor o imagen)"
      );
    }

    // Legacy Contab: solo base64 del xlsx (sin JSON)
    return reemplazarMayor(raw.trim());
  } catch (err) {
    Logger.log("ERROR DETALLE: " + err.stack);
    return ContentService.createTextOutput("ERROR: " + err.message);
  }
}

/** Intenta parsear JSON; tolera BOM y URL-encoding (%7B...). */
function intentarJson(raw) {
  var s = String(raw || "").replace(/^\uFEFF/, "").trim();
  if (!s) return null;
  var candidates = [s];
  if (s.indexOf("%7B") === 0 || s.indexOf("%7b") === 0 || s.indexOf("%22") >= 0) {
    try {
      candidates.push(decodeURIComponent(s.replace(/\+/g, " ")));
    } catch (ignore) {}
  }
  for (var i = 0; i < candidates.length; i++) {
    var c = candidates[i].trim();
    if (c.charAt(0) !== "{") continue;
    try {
      return JSON.parse(c);
    } catch (ignore2) {}
  }
  return null;
}

/** Único lugar que mueve mayor.xlsx a la papelera. */
function reemplazarMayor(base64str) {
  var folder = DriveApp.getFolderById("1zFjARS82JAuay19WxxgepBl7jYylgPIn");
  var archivos = folder.getFilesByName("mayor.xlsx");
  while (archivos.hasNext()) {
    archivos.next().setTrashed(true);
  }
  var blob = Utilities.newBlob(
    Utilities.base64Decode(String(base64str).trim()),
    MimeType.MICROSOFT_EXCEL,
    "mayor.xlsx"
  );
  folder.createFile(blob);
  return ContentService.createTextOutput("OK");
}

/** Solo agrega archivos; no borra mayor ni otros respaldos. */
function guardarEnRespaldoImagenes(data) {
  var parent = DriveApp.getFolderById("1zFjARS82JAuay19WxxgepBl7jYylgPIn");
  var folders = parent.getFoldersByName("respaldoimagenes");
  if (!folders.hasNext()) {
    return ContentService.createTextOutput("ERROR: no existe carpeta respaldoimagenes");
  }
  var dest = folders.next();
  if (!data.base64) {
    return ContentService.createTextOutput("ERROR: falta data.base64");
  }
  var nombre = data.nombre || "archivo_" + new Date().getTime();
  var mime = data.mime || MimeType.JPEG;
  var blob = Utilities.newBlob(
    Utilities.base64Decode(data.base64),
    mime,
    nombre
  );
  var file = dest.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return ContentService.createTextOutput("OK:" + file.getUrl());
}

function doGet(e) {
  var fileName = e && e.parameter ? e.parameter.nombre : null;
  if (!fileName) {
    return ContentService.createTextOutput("Falta el parámetro 'nombre'");
  }
  try {
    var folder = DriveApp.getFolderById("1zFjARS82JAuay19WxxgepBl7jYylgPIn");
    var files = folder.getFilesByName(fileName);
    if (!files.hasNext()) {
      return ContentService.createTextOutput("Archivo no encontrado");
    }
    var file = files.next();
    var downloadUrl = "https://drive.google.com/uc?export=download&id=" + file.getId();
    var template = HtmlService.createTemplateFromFile("redirect");
    template.url = downloadUrl;
    return HtmlService.createHtmlOutput(template.evaluate().getContent()).setXFrameOptionsMode(
      HtmlService.XFrameOptionsMode.ALLOWALL
    );
  } catch (err) {
    return ContentService.createTextOutput("ERROR: " + err.message);
  }
}
