/**
 * FxR — pulir imagen: 4 esquinas, warp perspectiva, contraste documento, Letter.
 * Sin dependencias obligatorias; OpenCV.js opcional vía CDN si está disponible.
 */
(function () {
  const cfg = window.FXR_PULIR || {};
  const canvas = document.getElementById("fxr-pulir-canvas");
  if (!canvas || !cfg.imgUrl) return;
  const ctx = canvas.getContext("2d");
  const img = new Image();
  img.crossOrigin = "anonymous";

  let corners = []; // [{x,y}] en coords de imagen natural
  let dragIdx = -1;
  let scale = 1;
  let offsetX = 0;
  let offsetY = 0;
  let outBlob = null;

  const HANDLE = 14;

  function defaultCorners(w, h) {
    const m = 0.08;
    return [
      { x: w * m, y: h * m },
      { x: w * (1 - m), y: h * m },
      { x: w * (1 - m), y: h * (1 - m) },
      { x: w * m, y: h * (1 - m) },
    ];
  }

  function layout() {
    const maxW = canvas.parentElement.clientWidth - 8;
    const maxH = Math.min(window.innerHeight * 0.7, 720);
    scale = Math.min(maxW / img.naturalWidth, maxH / img.naturalHeight, 1);
    canvas.width = Math.round(img.naturalWidth * scale);
    canvas.height = Math.round(img.naturalHeight * scale);
    offsetX = 0;
    offsetY = 0;
  }

  function toCanvas(p) {
    return { x: p.x * scale + offsetX, y: p.y * scale + offsetY };
  }
  function toImg(cx, cy) {
    return {
      x: Math.max(0, Math.min(img.naturalWidth, (cx - offsetX) / scale)),
      y: Math.max(0, Math.min(img.naturalHeight, (cy - offsetY) / scale)),
    };
  }

  function draw() {
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
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

  // --- Perspective (pure JS) ---
  function solveHomography(src, dst) {
    // src/dst: 4 points {x,y}
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

  function orderCorners(pts) {
    // TL, TR, BR, BL by sum/diff
    const sorted = pts.slice();
    sorted.sort((a, b) => a.x + a.y - (b.x + b.y));
    const tl = sorted[0];
    const br = sorted[3];
    const rest = [sorted[1], sorted[2]];
    rest.sort((a, b) => a.y - b.y);
    let tr, bl;
    if (rest[0].x > rest[1].x) {
      tr = rest[0];
      bl = rest[1];
    } else {
      // one of them may be TR
      const byX = pts.slice().sort((a, b) => a.x - b.x);
      const left = [byX[0], byX[1]].sort((a, b) => a.y - b.y);
      const right = [byX[2], byX[3]].sort((a, b) => a.y - b.y);
      return [left[0], right[0], right[1], left[1]];
    }
    return [tl, tr, br, bl];
  }

  function warpDocument() {
    const ordered = orderCorners(corners);
    const wSrc = img.naturalWidth;
    const hSrc = img.naturalHeight;
    const sideTop = Math.hypot(ordered[1].x - ordered[0].x, ordered[1].y - ordered[0].y);
    const sideBot = Math.hypot(ordered[2].x - ordered[3].x, ordered[2].y - ordered[3].y);
    const sideL = Math.hypot(ordered[3].x - ordered[0].x, ordered[3].y - ordered[0].y);
    const sideR = Math.hypot(ordered[2].x - ordered[1].x, ordered[2].y - ordered[1].y);
    let outW = Math.max(sideTop, sideBot, 200);
    let outH = Math.max(sideL, sideR, 200);
    // Letter aspect 8.5 x 11
    const letter = 8.5 / 11;
    const cur = outW / outH;
    if (cur > letter) outH = outW / letter;
    else outW = outH * letter;
    outW = Math.round(Math.min(outW, 1700));
    outH = Math.round(outW / letter);

    const dst = [
      { x: 0, y: 0 },
      { x: outW - 1, y: 0 },
      { x: outW - 1, y: outH - 1 },
      { x: 0, y: outH - 1 },
    ];
    // Map from dest -> source
    const H = solveHomography(dst, ordered);

    const srcCanvas = document.createElement("canvas");
    srcCanvas.width = wSrc;
    srcCanvas.height = hSrc;
    const sctx = srcCanvas.getContext("2d");
    sctx.drawImage(img, 0, 0);
    const srcData = sctx.getImageData(0, 0, wSrc, hSrc).data;

    const outCanvas = document.createElement("canvas");
    outCanvas.width = outW;
    outCanvas.height = outH;
    const octx = outCanvas.getContext("2d");
    const imgData = octx.createImageData(outW, outH);
    const d = imgData.data;
    for (let y = 0; y < outH; y++) {
      for (let x = 0; x < outW; x++) {
        const p = applyH(H, x, y);
        let rgb = sampleBilinear(srcData, wSrc, hSrc, p.x, p.y);
        // document mode: grayscale + contrast
        let g = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2];
        g = (g - 128) * 1.35 + 128;
        g = Math.max(0, Math.min(255, g));
        // mild threshold boost
        if (g > 200) g = 255;
        if (g < 40) g = 0;
        const i = (y * outW + x) * 4;
        d[i] = d[i + 1] = d[i + 2] = g;
        d[i + 3] = 255;
      }
    }
    octx.putImageData(imgData, 0, 0);
    return outCanvas;
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

  document.getElementById("fxr-preview-btn").addEventListener("click", () => {
    showPreview(warpDocument());
  });

  document.getElementById("fxr-reset").addEventListener("click", () => {
    corners = defaultCorners(img.naturalWidth, img.naturalHeight);
    draw();
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

  // Detección mejorada: bordes Sobel + escaneo desde el marco + blob claro
  function autoDetectSimple() {
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    const c = document.createElement("canvas");
    const maxSide = 480;
    const s = Math.min(1, maxSide / Math.max(w, h));
    const sw = Math.round(w * s);
    const sh = Math.round(h * s);
    c.width = sw;
    c.height = sh;
    const cx = c.getContext("2d", { willReadFrequently: true });
    cx.drawImage(img, 0, 0, sw, sh);
    const data = cx.getImageData(0, 0, sw, sh).data;
    const gray = new Float32Array(sw * sh);
    for (let i = 0; i < sw * sh; i++) {
      const o = i * 4;
      gray[i] = 0.299 * data[o] + 0.587 * data[o + 1] + 0.114 * data[o + 2];
    }

    // Soft blur 3x3
    const blur = new Float32Array(sw * sh);
    for (let y = 1; y < sh - 1; y++) {
      for (let x = 1; x < sw - 1; x++) {
        let sum = 0;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) sum += gray[(y + dy) * sw + (x + dx)];
        }
        blur[y * sw + x] = sum / 9;
      }
    }

    // Sobel magnitude
    const mag = new Float32Array(sw * sh);
    let magMax = 1;
    for (let y = 1; y < sh - 1; y++) {
      for (let x = 1; x < sw - 1; x++) {
        const gx =
          -blur[(y - 1) * sw + (x - 1)] +
          blur[(y - 1) * sw + (x + 1)] -
          2 * blur[y * sw + (x - 1)] +
          2 * blur[y * sw + (x + 1)] -
          blur[(y + 1) * sw + (x - 1)] +
          blur[(y + 1) * sw + (x + 1)];
        const gy =
          -blur[(y - 1) * sw + (x - 1)] -
          2 * blur[(y - 1) * sw + x] -
          blur[(y - 1) * sw + (x + 1)] +
          blur[(y + 1) * sw + (x - 1)] +
          2 * blur[(y + 1) * sw + x] +
          blur[(y + 1) * sw + (x + 1)];
        const m = Math.sqrt(gx * gx + gy * gy);
        mag[y * sw + x] = m;
        if (m > magMax) magMax = m;
      }
    }
    const edgeThr = magMax * 0.18;

    // Desde cada borde, encontrar la primera línea con muchos bordes (marco del papel)
    function scanEdge(horizontal, fromStart) {
      const limit = horizontal ? sh : sw;
      const other = horizontal ? sw : sh;
      const start = fromStart ? 2 : limit - 3;
      const end = fromStart ? Math.floor(limit * 0.45) : Math.floor(limit * 0.55);
      const step = fromStart ? 1 : -1;
      let best = fromStart ? Math.floor(limit * 0.08) : Math.floor(limit * 0.92);
      let bestScore = -1;
      for (let i = start; fromStart ? i < end : i > end; i += step) {
        let score = 0;
        for (let j = Math.floor(other * 0.1); j < Math.floor(other * 0.9); j++) {
          const x = horizontal ? j : i;
          const y = horizontal ? i : j;
          if (mag[y * sw + x] >= edgeThr) score++;
        }
        if (score > bestScore) {
          bestScore = score;
          best = i;
        }
        // early stop if strong continuous edge after leaving border noise
        if (score > other * 0.25 && (fromStart ? i > 8 : i < limit - 8)) break;
      }
      return best;
    }

    let top = scanEdge(true, true);
    let bottom = scanEdge(true, false);
    let left = scanEdge(false, true);
    let right = scanEdge(false, false);

    // Refinar con blob claro (papel) si el marco es dudoso
    const sorted = Array.from(blur).filter((_, i) => {
      const x = i % sw;
      const y = (i / sw) | 0;
      return x > 2 && y > 2 && x < sw - 2 && y < sh - 2;
    });
    sorted.sort((a, b) => a - b);
    const candidates = [];
    for (const pct of [0.45, 0.55, 0.65]) {
      const thr = sorted[Math.floor(sorted.length * pct)] || 128;
      let minX = sw,
        minY = sh,
        maxX = 0,
        maxY = 0,
        count = 0;
      for (let y = 0; y < sh; y++) {
        for (let x = 0; x < sw; x++) {
          if (blur[y * sw + x] >= thr) {
            count++;
            if (x < minX) minX = x;
            if (y < minY) minY = y;
            if (x > maxX) maxX = x;
            if (y > maxY) maxY = y;
          }
        }
      }
      const area = (maxX - minX) * (maxY - minY);
      if (count > sw * sh * 0.08 && area > sw * sh * 0.12) {
        candidates.push({ minX, minY, maxX, maxY, area, count });
      }
    }
    if (candidates.length) {
      candidates.sort((a, b) => b.area - a.area);
      const best = candidates[0];
      // Mezcla: preferir blob si el scan de bordes quedó muy al margen
      const frameArea = Math.max(1, (right - left) * (bottom - top));
      if (best.area > frameArea * 0.7 || frameArea > sw * sh * 0.95) {
        left = best.minX;
        top = best.minY;
        right = best.maxX;
        bottom = best.maxY;
      }
    }

    // Asegurar orden y margen mínimo
    if (right - left < sw * 0.25 || bottom - top < sh * 0.25) {
      corners = defaultCorners(w, h);
      draw();
      return;
    }
    const pad = 3;
    left = Math.max(0, left - pad);
    top = Math.max(0, top - pad);
    right = Math.min(sw - 1, right + pad);
    bottom = Math.min(sh - 1, bottom + pad);

    // Esquinas: extremos del rectángulo (usuario puede arrastrar si hay perspectiva)
    // Intento de esquinas “reales” buscando máximo borde cerca de cada esquina del bbox
    function refineCorner(cx0, cy0, dx, dy) {
      let bestX = cx0,
        bestY = cy0,
        best = -1;
      for (let t = 0; t < 18; t++) {
        for (let u = 0; u < 18; u++) {
          const x = Math.round(cx0 + dx * t);
          const y = Math.round(cy0 + dy * u);
          if (x < 1 || y < 1 || x >= sw - 1 || y >= sh - 1) continue;
          const m = mag[y * sw + x];
          if (m > best) {
            best = m;
            bestX = x;
            bestY = y;
          }
        }
      }
      return { x: bestX / s, y: bestY / s };
    }

    corners = [
      refineCorner(left, top, 1, 1),
      refineCorner(right, top, -1, 1),
      refineCorner(right, bottom, -1, -1),
      refineCorner(left, bottom, 1, -1),
    ];
    draw();
  }

  document.getElementById("fxr-detect").addEventListener("click", () => {
    if (window.cv && typeof cv.Mat === "function" && cv.Mat) {
      try {
        detectOpenCV();
        return;
      } catch (e) {
        console.warn("OpenCV detect failed", e);
      }
    }
    autoDetectSimple();
  });

  function detectOpenCV() {
    const src = cv.imread(img);
    const gray = new cv.Mat();
    const blur = new cv.Mat();
    const edges = new cv.Mat();
    const contours = new cv.MatVector();
    const hierarchy = new cv.Mat();
    try {
      cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY, 0);
      cv.GaussianBlur(gray, blur, new cv.Size(5, 5), 0);
      cv.Canny(blur, edges, 40, 120);
      cv.findContours(edges, contours, hierarchy, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE);
      let bestPts = null;
      let bestArea = 0;
      const minArea = img.naturalWidth * img.naturalHeight * 0.08;
      for (let i = 0; i < contours.size(); i++) {
        const cnt = contours.get(i);
        const peri = cv.arcLength(cnt, true);
        for (const eps of [0.02, 0.03, 0.04, 0.015]) {
          const approx = new cv.Mat();
          cv.approxPolyDP(cnt, approx, eps * peri, true);
          if (approx.rows === 4 && cv.isContourConvex(approx)) {
            const area = Math.abs(cv.contourArea(approx));
            if (area > bestArea && area > minArea) {
              bestArea = area;
              const pts = [];
              for (let k = 0; k < 4; k++) {
                pts.push({ x: approx.intPtr(k, 0)[0], y: approx.intPtr(k, 0)[1] });
              }
              bestPts = pts;
            }
          }
          approx.delete();
        }
      }
      if (bestPts) {
        corners = orderCorners(bestPts);
        draw();
      } else {
        autoDetectSimple();
      }
    } finally {
      src.delete();
      gray.delete();
      blur.delete();
      edges.delete();
      contours.delete();
      hierarchy.delete();
    }
  }

  function tryLoadOpenCV() {
    if (window.cv && cv.Mat) return;
    const s = document.createElement("script");
    s.src = "https://docs.opencv.org/4.8.0/opencv.js";
    s.async = true;
    s.onload = () => {
      const boot = () => {
        /* listo para botón Auto detectar */
      };
      if (typeof cv !== "undefined" && cv["onRuntimeInitialized"]) {
        cv["onRuntimeInitialized"] = boot;
      } else {
        setTimeout(boot, 800);
      }
    };
    document.head.appendChild(s);
  }

  img.onload = () => {
    layout();
    corners = defaultCorners(img.naturalWidth, img.naturalHeight);
    draw();
    autoDetectSimple();
    tryLoadOpenCV();
  };
  img.onerror = () => {
    alert("No se pudo cargar la imagen");
  };
  img.src = cfg.imgUrl;

  window.addEventListener("resize", () => {
    if (!img.naturalWidth) return;
    layout();
    draw();
  });
})();
