/**
 * FxR revisión — recorte por arrastre + giro in-place (auto-guarda, sin ir a Pulir).
 */
(function () {
  const cfg = window.FXR_REV_IMG;
  if (!cfg || !cfg.imgUrl || !cfg.postUrl || !cfg.cid) return;

  const viewer = document.getElementById("fxr-rev-viewer");
  const canvas = document.getElementById("fxr-rev-canvas");
  const statusEl = document.getElementById("fxr-rev-img-status");
  if (!viewer || !canvas) return;

  const ctx = canvas.getContext("2d");
  const work = document.createElement("canvas");
  const workCtx = work.getContext("2d");

  let scale = 1;
  let rectDrag = null;
  let saving = false;
  let dirtyLocal = false;

  const MIN_SEL = 20;

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg;
  }

  function layout() {
    const maxW = Math.max(120, viewer.clientWidth - 16);
    const maxH = Math.max(120, viewer.clientHeight - 48);
    scale = Math.min(maxW / work.width, maxH / work.height, 1);
    canvas.width = Math.round(work.width * scale);
    canvas.height = Math.round(work.height * scale);
  }

  function toImg(cx, cy) {
    return {
      x: Math.max(0, Math.min(work.width, cx / scale)),
      y: Math.max(0, Math.min(work.height, cy / scale)),
    };
  }

  function pointerPos(e) {
    const r = canvas.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return {
      x: ((t.clientX - r.left) / r.width) * canvas.width,
      y: ((t.clientY - r.top) / r.height) * canvas.height,
    };
  }

  function draw() {
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(work, 0, 0, canvas.width, canvas.height);
    if (!rectDrag) return;
    const x0 = Math.min(rectDrag.x0, rectDrag.x1) * scale;
    const y0 = Math.min(rectDrag.y0, rectDrag.y1) * scale;
    const x1 = Math.max(rectDrag.x0, rectDrag.x1) * scale;
    const y1 = Math.max(rectDrag.y0, rectDrag.y1) * scale;
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.clearRect(x0, y0, x1 - x0, y1 - y0);
    ctx.drawImage(
      work,
      Math.min(rectDrag.x0, rectDrag.x1),
      Math.min(rectDrag.y0, rectDrag.y1),
      Math.abs(rectDrag.x1 - rectDrag.x0),
      Math.abs(rectDrag.y1 - rectDrag.y0),
      x0,
      y0,
      x1 - x0,
      y1 - y0
    );
    ctx.strokeStyle = "#ffe566";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
    ctx.setLineDash([]);
  }

  function rotate(dir) {
    if (saving) return;
    const srcW = work.width;
    const srcH = work.height;
    const tmp = document.createElement("canvas");
    tmp.width = srcH;
    tmp.height = srcW;
    const tctx = tmp.getContext("2d");
    tctx.translate(tmp.width / 2, tmp.height / 2);
    tctx.rotate((dir * Math.PI) / 2);
    tctx.drawImage(work, -srcW / 2, -srcH / 2);
    work.width = tmp.width;
    work.height = tmp.height;
    workCtx.drawImage(tmp, 0, 0);
    layout();
    draw();
    dirtyLocal = true;
    setStatus("Girado… guardando");
    saveBlob("giro");
  }

  function applyCrop(x0, y0, x1, y1) {
    const left = Math.max(0, Math.floor(Math.min(x0, x1)));
    const top = Math.max(0, Math.floor(Math.min(y0, y1)));
    const right = Math.min(work.width, Math.ceil(Math.max(x0, x1)));
    const bottom = Math.min(work.height, Math.ceil(Math.max(y0, y1)));
    const w = right - left;
    const h = bottom - top;
    if (w < MIN_SEL || h < MIN_SEL) {
      setStatus("Selección muy pequeña; arrastra un área mayor.");
      return false;
    }
    const tmp = document.createElement("canvas");
    tmp.width = w;
    tmp.height = h;
    tmp.getContext("2d").drawImage(work, left, top, w, h, 0, 0, w, h);
    work.width = w;
    work.height = h;
    workCtx.drawImage(tmp, 0, 0);
    layout();
    draw();
    dirtyLocal = true;
    setStatus("Recortado… guardando");
    saveBlob("recorte");
    return true;
  }

  function saveBlob(accion) {
    if (saving) return;
    saving = true;
    work.toBlob(
      (blob) => {
        if (!blob) {
          saving = false;
          setStatus("No se pudo generar la imagen");
          return;
        }
        const fd = new FormData();
        fd.append("archivo", blob, "revision.jpg");
        fd.append("accion", accion || "ajuste");
        fetch(cfg.postUrl, { method: "POST", body: fd, credentials: "same-origin" })
          .then((r) => r.json().then((j) => ({ okHttp: r.ok, j })))
          .then(({ okHttp, j }) => {
            saving = false;
            if (!okHttp || !j || !j.ok) {
              setStatus((j && j.error) || "Error al guardar");
              return;
            }
            dirtyLocal = false;
            setStatus("Guardado");
            if (j.url) {
              // refresca bitmap desde servidor (cache-bust)
              const img = new Image();
              img.crossOrigin = "anonymous";
              img.onload = () => {
                work.width = img.naturalWidth;
                work.height = img.naturalHeight;
                workCtx.drawImage(img, 0, 0);
                layout();
                draw();
              };
              img.src = j.url;
            }
          })
          .catch(() => {
            saving = false;
            setStatus("Error de red al guardar");
          });
      },
      "image/jpeg",
      0.85
    );
  }

  canvas.addEventListener("mousedown", (e) => {
    if (saving) return;
    const p = pointerPos(e);
    const imgP = toImg(p.x, p.y);
    rectDrag = { x0: imgP.x, y0: imgP.y, x1: imgP.x, y1: imgP.y };
    draw();
  });
  window.addEventListener("mousemove", (e) => {
    if (!rectDrag) return;
    const p = pointerPos(e);
    const imgP = toImg(p.x, p.y);
    rectDrag.x1 = imgP.x;
    rectDrag.y1 = imgP.y;
    draw();
  });
  window.addEventListener("mouseup", () => {
    if (!rectDrag) return;
    const r = rectDrag;
    rectDrag = null;
    if (!applyCrop(r.x0, r.y0, r.x1, r.y1)) draw();
  });

  canvas.addEventListener(
    "touchstart",
    (e) => {
      if (saving) return;
      e.preventDefault();
      const p = pointerPos(e);
      const imgP = toImg(p.x, p.y);
      rectDrag = { x0: imgP.x, y0: imgP.y, x1: imgP.x, y1: imgP.y };
      draw();
    },
    { passive: false }
  );
  canvas.addEventListener(
    "touchmove",
    (e) => {
      if (!rectDrag) return;
      e.preventDefault();
      const p = pointerPos(e);
      const imgP = toImg(p.x, p.y);
      rectDrag.x1 = imgP.x;
      rectDrag.y1 = imgP.y;
      draw();
    },
    { passive: false }
  );
  canvas.addEventListener("touchend", () => {
    if (!rectDrag) return;
    const r = rectDrag;
    rectDrag = null;
    if (!applyCrop(r.x0, r.y0, r.x1, r.y1)) draw();
  });

  const btnCcw = document.getElementById("fxr-rev-rotate-ccw");
  const btnCw = document.getElementById("fxr-rev-rotate-cw");
  if (btnCcw) btnCcw.addEventListener("click", () => rotate(-1));
  if (btnCw) btnCw.addEventListener("click", () => rotate(1));

  // Teclado: [ ] giran (sin interferir con ← → ni inputs)
  document.addEventListener("keydown", (e) => {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT"))
      return;
    if (e.key === "[") {
      e.preventDefault();
      rotate(-1);
    } else if (e.key === "]") {
      e.preventDefault();
      rotate(1);
    }
  });

  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    work.width = img.naturalWidth;
    work.height = img.naturalHeight;
    workCtx.drawImage(img, 0, 0);
    layout();
    draw();
    setStatus("Arrastra para recortar · [ ] o botones para girar (se guarda solo)");
  };
  img.onerror = () => setStatus("No se pudo cargar la imagen");
  img.src = cfg.imgUrl;

  window.addEventListener("resize", () => {
    if (!work.width) return;
    layout();
    draw();
  });
})();
