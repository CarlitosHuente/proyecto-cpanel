/**
 * FxR — pulir imagen: jscanify (OpenCV.js) + 4 esquinas arrastrables + rotación 90° + Letter.
 */
(function () {
  const cfg = window.FXR_PULIR || {};
  const canvas = document.getElementById("fxr-pulir-canvas");
  if (!canvas || !cfg.imgUrl) return;
  const ctx = canvas.getContext("2d");
  const statusEl = document.getElementById("fxr-pulir-status");

  const work = document.createElement("canvas");
  const workCtx = work.getContext("2d");

  let corners = []; // [{x,y}] en coords del bitmap de trabajo
  let dragIdx = -1;
  let scale = 1;
  let offsetX = 0;
  let offsetY = 0;
  let outBlob = null;
  let scanner = null;
  let cvReady = false;
  let imgReady = false;

  const HANDLE = 14;
  const LETTER = 8.5 / 11;

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg;
  }

  function defaultCorners(w, h) {
    const m = 0.08;
    return [
      { x: w * m, y: h * m },
      { x: w * (1 - m), y: h * m },
      { x: w * (1 - m), y: h * (1 - m) },
      { x: w * m, y: h * (1 - m) },
    ];
  }

  function workW() {
    return work.width;
  }
  function workH() {
    return work.height;
  }

  function layout() {
    const maxW = canvas.parentElement.clientWidth - 8;
    const maxH = Math.min(window.innerHeight * 0.7, 720);
    scale = Math.min(maxW / workW(), maxH / workH(), 1);
    canvas.width = Math.round(workW() * scale);
    canvas.height = Math.round(workH() * scale);
    offsetX = 0;
    offsetY = 0;
  }

  function toCanvas(p) {
    return { x: p.x * scale + offsetX, y: p.y * scale + offsetY };
  }
  function toImg(cx, cy) {
    return {
      x: Math.max(0, Math.min(workW(), (cx - offsetX) / scale)),
      y: Math.max(0, Math.min(workH(), (cy - offsetY) / scale)),
    };
  }

  function draw() {
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(work, 0, 0, canvas.width, canvas.height);
    if (corners.length !== 4) return;
    ctx.beginPath();
    const c0 = toCanvas(corners[0]);
    ctx.moveTo(c0.x, c0.y);
    for (let i = 1; i < 4; i++) {
      const c = toCanvas(corners[i]);
      ctx.lineTo(c.x, c.y);
    }
    ctx.closePath();
    ctx.strokeStyle = "#00e5ff";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "rgba(0,229,255,0.12)";
    ctx.fill();
    corners.forEach((p, i) => {
      const c = toCanvas(p);
      ctx.beginPath();
      ctx.arc(c.x, c.y, HANDLE / 2, 0, Math.PI * 2);
      ctx.fillStyle = "#ffe566";
      ctx.fill();
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = "#111";
      ctx.font = "11px sans-serif";
      ctx.fillText(String(i + 1), c.x - 3, c.y + 4);
    });
  }

  function hitHandle(cx, cy) {
    for (let i = 0; i < corners.length; i++) {
      const c = toCanvas(corners[i]);
      const dx = c.x - cx;
      const dy = c.y - cy;
      if (dx * dx + dy * dy <= (HANDLE * 1.2) * (HANDLE * 1.2)) return i;
    }
    return -1;
  }

  function pointerPos(e) {
    const r = canvas.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return {
      x: ((t.clientX - r.left) / r.width) * canvas.width,
      y: ((t.clientY - r.top) / r.height) * canvas.height,
    };
  }

  canvas.addEventListener("mousedown", (e) => {
    const p = pointerPos(e);
    dragIdx = hitHandle(p.x, p.y);
  });
  window.addEventListener("mouseup", () => {
    dragIdx = -1;
  });
  canvas.addEventListener("mousemove", (e) => {
    if (dragIdx < 0) return;
    const p = pointerPos(e);
    corners[dragIdx] = toImg(p.x, p.y);
    draw();
  });
  canvas.addEventListener(
    "touchstart",
    (e) => {
      const p = pointerPos(e);
      dragIdx = hitHandle(p.x, p.y);
      if (dragIdx >= 0) e.preventDefault();
    },
    { passive: false }
  );
  canvas.addEventListener(
    "touchmove",
    (e) => {
      if (dragIdx < 0) return;
      e.preventDefault();
      const p = pointerPos(e);
      corners[dragIdx] = toImg(p.x, p.y);
      draw();
    },
    { passive: false }
  );
  canvas.addEventListener("touchend", () => {
    dragIdx = -1;
  });

  function cornersToJscanify(pts) {
    const ordered = orderCorners(pts);
    return {
      topLeftCorner: ordered[0],
      topRightCorner: ordered[1],
      bottomRightCorner: ordered[2],
      bottomLeftCorner: ordered[3],
    };
  }

  function jscanifyToCorners(cp) {
    if (
      !cp ||
      !cp.topLeftCorner ||
      !cp.topRightCorner ||
      !cp.bottomRightCorner ||
      !cp.bottomLeftCorner
    ) {
      return null;
    }
    return [
      { x: cp.topLeftCorner.x, y: cp.topLeftCorner.y },
      { x: cp.topRightCorner.x, y: cp.topRightCorner.y },
      { x: cp.bottomRightCorner.x, y: cp.bottomRightCorner.y },
      { x: cp.bottomLeftCorner.x, y: cp.bottomLeftCorner.y },
    ];
  }

  function orderCorners(pts) {
    const byX = pts.slice().sort((a, b) => a.x - b.x);
    const left = [byX[0], byX[1]].sort((a, b) => a.y - b.y);
    const right = [byX[2], byX[3]].sort((a, b) => a.y - b.y);
    return [left[0], right[0], right[1], left[1]]; // TL, TR, BR, BL
  }

  function letterSizeFromCorners(pts) {
    const o = orderCorners(pts);
    const sideTop = Math.hypot(o[1].x - o[0].x, o[1].y - o[0].y);
    const sideBot = Math.hypot(o[2].x - o[3].x, o[2].y - o[3].y);
    const sideL = Math.hypot(o[3].x - o[0].x, o[3].y - o[0].y);
    const sideR = Math.hypot(o[2].x - o[1].x, o[2].y - o[1].y);
    let outW = Math.max(sideTop, sideBot, 200);
    let outH = Math.max(sideL, sideR, 200);
    const cur = outW / outH;
    if (cur > LETTER) outH = outW / LETTER;
    else outW = outH * LETTER;
    outW = Math.round(Math.min(outW, 1700));
    outH = Math.round(outW / LETTER);
    return { outW, outH };
  }

  function contrastDocument(srcCanvas) {
    const w = srcCanvas.width;
    const h = srcCanvas.height;
    const out = document.createElement("canvas");
    out.width = w;
    out.height = h;
    const octx = out.getContext("2d");
    octx.drawImage(srcCanvas, 0, 0);
    const imgData = octx.getImageData(0, 0, w, h);
    const d = imgData.data;
    for (let i = 0; i < d.length; i += 4) {
      let g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      g = (g - 128) * 1.25 + 128;
      g = Math.max(0, Math.min(255, g));
      if (g > 210) g = 255;
      if (g < 35) g = 0;
      d[i] = d[i + 1] = d[i + 2] = g;
    }
    octx.putImageData(imgData, 0, 0);
    return out;
  }

  function warpDocument() {
    const { outW, outH } = letterSizeFromCorners(corners);
    const cornerPoints = cornersToJscanify(corners);

    if (cvReady && scanner) {
      try {
        const extracted = scanner.extractPaper(work, outW, outH, cornerPoints);
        if (extracted) return contrastDocument(extracted);
      } catch (e) {
        console.warn("jscanify extractPaper failed", e);
      }
    }
    return contrastDocument(warpFallback(outW, outH));
  }

  function warpFallback(outW, outH) {
    const ordered = orderCorners(corners);
    const dst = [
      { x: 0, y: 0 },
      { x: outW - 1, y: 0 },
      { x: outW - 1, y: outH - 1 },
      { x: 0, y: outH - 1 },
    ];
    const H = solveHomography(dst, ordered);
    const srcData = workCtx.getImageData(0, 0, workW(), workH()).data;
    const outCanvas = document.createElement("canvas");
    outCanvas.width = outW;
    outCanvas.height = outH;
    const octx = outCanvas.getContext("2d");
    const imgData = octx.createImageData(outW, outH);
    const d = imgData.data;
    for (let y = 0; y < outH; y++) {
      for (let x = 0; x < outW; x++) {
        const p = applyH(H, x, y);
        const rgb = sampleBilinear(srcData, workW(), workH(), p.x, p.y);
        const i = (y * outW + x) * 4;
        d[i] = rgb[0];
        d[i + 1] = rgb[1];
        d[i + 2] = rgb[2];
        d[i + 3] = 255;
      }
    }
    octx.putImageData(imgData, 0, 0);
    return outCanvas;
  }

  function solveHomography(src, dst) {
    const A = [];
    const b = [];
    for (let i = 0; i < 4; i++) {
      const x = src[i].x;
      const y = src[i].y;
      const u = dst[i].x;
      const v = dst[i].y;
      A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]);
      b.push(u);
      A.push([0, 0, 0, x, y, 1, -v * x, -v * y]);
      b.push(v);
    }
    const h = gaussianSolve(A, b);
    return [h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7], 1];
  }

  function gaussianSolve(A, b) {
    const n = b.length;
    const M = A.map((row, i) => row.concat([b[i]]));
    for (let col = 0; col < n; col++) {
      let piv = col;
      for (let r = col + 1; r < n; r++) {
        if (Math.abs(M[r][col]) > Math.abs(M[piv][col])) piv = r;
      }
      const tmp = M[col];
      M[col] = M[piv];
      M[piv] = tmp;
      const div = M[col][col] || 1e-12;
      for (let c = col; c <= n; c++) M[col][c] /= div;
      for (let r = 0; r < n; r++) {
        if (r === col) continue;
        const f = M[r][col];
        for (let c = col; c <= n; c++) M[r][c] -= f * M[col][c];
      }
    }
    return M.map((row) => row[n]);
  }

  function applyH(H, x, y) {
    const w = H[6] * x + H[7] * y + H[8];
    return {
      x: (H[0] * x + H[1] * y + H[2]) / w,
      y: (H[3] * x + H[4] * y + H[5]) / w,
    };
  }

  function sampleBilinear(data, w, h, x, y) {
    if (x < 0 || y < 0 || x >= w - 1 || y >= h - 1) return [255, 255, 255];
    const x0 = Math.floor(x);
    const y0 = Math.floor(y);
    const dx = x - x0;
    const dy = y - y0;
    const idx = (yy, xx) => (yy * w + xx) * 4;
    const p00 = idx(y0, x0);
    const p10 = idx(y0, x0 + 1);
    const p01 = idx(y0 + 1, x0);
    const p11 = idx(y0 + 1, x0 + 1);
    const out = [];
    for (let c = 0; c < 3; c++) {
      const v =
        data[p00 + c] * (1 - dx) * (1 - dy) +
        data[p10 + c] * dx * (1 - dy) +
        data[p01 + c] * (1 - dx) * dy +
        data[p11 + c] * dx * dy;
      out.push(v);
    }
    return out;
  }

  function showPreview(canvasOut) {
    canvasOut.toBlob(
      (blob) => {
        outBlob = blob;
        const url = URL.createObjectURL(blob);
        const el = document.getElementById("fxr-out-preview");
        const ph = document.getElementById("fxr-out-placeholder");
        el.src = url;
        el.style.display = "inline-block";
        if (ph) ph.style.display = "none";
      },
      "image/jpeg",
      0.82
    );
  }

  function autoDetect(silent) {
    if (!cvReady || !scanner) {
      if (!silent) setStatus("Detector aún cargando… espera un momento.");
      corners = defaultCorners(workW(), workH());
      draw();
      return false;
    }
    let mat = null;
    let contour = null;
    try {
      mat = cv.imread(work);
      contour = scanner.findPaperContour(mat);
      if (!contour) {
        if (!silent) setStatus("No se detectó el papel; ajusta las esquinas a mano.");
        corners = defaultCorners(workW(), workH());
        draw();
        return false;
      }
      const cp = scanner.getCornerPoints(contour);
      const pts = jscanifyToCorners(cp);
      if (!pts) {
        if (!silent) setStatus("Detección incompleta; ajusta las esquinas a mano.");
        corners = defaultCorners(workW(), workH());
        draw();
        return false;
      }
      // Validar área mínima
      const xs = pts.map((p) => p.x);
      const ys = pts.map((p) => p.y);
      const area =
        (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys));
      if (area < workW() * workH() * 0.05) {
        if (!silent) setStatus("Área detectada muy pequeña; ajusta a mano.");
        corners = defaultCorners(workW(), workH());
        draw();
        return false;
      }
      corners = pts;
      draw();
      setStatus("Arrastra las esquinas si hace falta. Usa Girar si la foto está ladeada.");
      return true;
    } catch (e) {
      console.warn("jscanify detect failed", e);
      if (!silent) setStatus("Error al detectar; ajusta las esquinas a mano.");
      corners = defaultCorners(workW(), workH());
      draw();
      return false;
    } finally {
      if (mat) mat.delete();
      if (contour) {
        try {
          contour.delete();
        } catch (_) {
          /* ignore */
        }
      }
    }
  }

  function rotateWork(dir) {
    // dir: 1 = CW 90°, -1 = CCW 90°
    const srcW = workW();
    const srcH = workH();
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
    autoDetect(true);
    if (corners.length !== 4) {
      corners = defaultCorners(workW(), workH());
      draw();
    }
  }

  document.getElementById("fxr-preview-btn").addEventListener("click", () => {
    showPreview(warpDocument());
  });

  document.getElementById("fxr-reset").addEventListener("click", () => {
    corners = defaultCorners(workW(), workH());
    draw();
    setStatus("Esquinas reiniciadas.");
  });

  document.getElementById("fxr-detect").addEventListener("click", () => {
    autoDetect(false);
  });

  document.getElementById("fxr-rotate-cw").addEventListener("click", () => {
    rotateWork(1);
  });
  document.getElementById("fxr-rotate-ccw").addEventListener("click", () => {
    rotateWork(-1);
  });

  document.getElementById("fxr-aplicar").addEventListener("click", () => {
    const c = warpDocument();
    c.toBlob(
      (blob) => {
        if (!blob) {
          alert("No se pudo generar la imagen");
          return;
        }
        const form = document.getElementById("fxr-pulir-form");
        const fileInput = document.getElementById("fxr-pulir-file");
        const dt = new DataTransfer();
        dt.items.add(new File([blob], "pulido.jpg", { type: "image/jpeg" }));
        fileInput.files = dt.files;
        form.submit();
      },
      "image/jpeg",
      0.82
    );
  });

  function onReady() {
    if (!imgReady || !cvReady) return;
    scanner = typeof jscanify === "function" ? new jscanify() : null;
    if (!scanner) {
      setStatus("jscanify no disponible; ajusta esquinas a mano.");
      corners = defaultCorners(workW(), workH());
      draw();
      return;
    }
    autoDetect(true);
  }

  function markCvReady() {
    cvReady = true;
    setStatus("Detector listo. Auto-detectando…");
    onReady();
  }

  function waitForCv() {
    if (typeof cv === "undefined") {
      setTimeout(waitForCv, 200);
      return;
    }
    if (cv.Mat) {
      markCvReady();
      return;
    }
    const prev = cv.onRuntimeInitialized;
    cv.onRuntimeInitialized = function () {
      if (typeof prev === "function") prev();
      markCvReady();
    };
    // timeout fallback
    setTimeout(() => {
      if (!cvReady && typeof cv !== "undefined" && cv.Mat) markCvReady();
    }, 8000);
  }

  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    work.width = img.naturalWidth;
    work.height = img.naturalHeight;
    workCtx.drawImage(img, 0, 0);
    layout();
    corners = defaultCorners(workW(), workH());
    draw();
    imgReady = true;
    onReady();
  };
  img.onerror = () => {
    alert("No se pudo cargar la imagen");
    setStatus("Error al cargar la imagen.");
  };
  img.src = cfg.imgUrl;

  waitForCv();

  window.addEventListener("resize", () => {
    if (!work.width) return;
    layout();
    draw();
  });
})();
