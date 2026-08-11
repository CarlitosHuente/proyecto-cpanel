/**
 * Overlay ligero al consultar pantallas Buk (GET + recarga).
 */
(function (global) {
  var DEFAULT_MSGS = [
    "Conectando con Buk…",
    "Cargando turnos y marcajes…",
    "Cruzando información con nómina…",
    "Falta poco…",
  ];
  var rotateTimer = null;
  var msgIndex = 0;

  function overlayEl() {
    return document.getElementById("loading-overlay");
  }

  function msgEl() {
    return document.getElementById("loading-overlay-msg");
  }

  function setMsg(text) {
    var el = msgEl();
    if (el) el.textContent = text;
  }

  function stopRotate() {
    if (rotateTimer) {
      clearInterval(rotateTimer);
      rotateTimer = null;
    }
  }

  function startRotate(mensajes) {
    stopRotate();
    var msgs = mensajes && mensajes.length ? mensajes : DEFAULT_MSGS;
    msgIndex = 0;
    setMsg(msgs[0]);
    rotateTimer = setInterval(function () {
      msgIndex = (msgIndex + 1) % msgs.length;
      setMsg(msgs[msgIndex]);
    }, 2500);
  }

  function mostrar(mensajes) {
    var el = overlayEl();
    if (!el) return;
    document.body.style.overflow = "hidden";
    el.style.display = "flex";
    startRotate(mensajes);
  }

  function ocultar() {
    stopRotate();
    var el = overlayEl();
    if (el) el.style.display = "none";
    document.body.style.overflow = "";
  }

  global.HuenteBukLoading = { mostrar: mostrar, ocultar: ocultar };

  global.mostrarOverlay = function (mensaje) {
    mostrar(mensaje ? [mensaje] : ["Actualizando todos los datos, por favor espere…"]);
  };

  function debeMostrarAlNavegar(link, ev) {
    if (!link || link.target === "_blank") return false;
    if (ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey)) return false;
    var href = (link.getAttribute("href") || "").trim();
    return href && href.charAt(0) !== "#";
  }

  document.addEventListener(
    "click",
    function (ev) {
      var link = ev.target.closest("a[data-buk-loading]");
      if (!link || !debeMostrarAlNavegar(link, ev)) return;
      mostrar();
    },
    true
  );

  document.addEventListener("DOMContentLoaded", function () {
    ocultar();
  });
})(window);
