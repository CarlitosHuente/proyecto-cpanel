(function () {
    "use strict";

    const cfg = window.DW_RUTA || {};
    const lista = document.getElementById("listaRuta");
    const tbl = document.getElementById("tblOrdenes");
    const lblCount = document.getElementById("lblCount");
    const alertRuta = document.getElementById("alertRuta");
    const bloqueEnlaces = document.getElementById("bloqueEnlaces");
    const inpOrigen = document.getElementById("inpOrigen");
    const chkVolver = document.getElementById("chkVolverOrigen");

    let paradas = [];
    let dragSrc = null;

    function showAlert(msg, tipo) {
        alertRuta.textContent = msg;
        alertRuta.className = "alert alert-" + (tipo || "info") + " py-2 small";
        alertRuta.classList.remove("d-none");
    }

    function hideAlert() {
        alertRuta.classList.add("d-none");
    }

    function paradaFromRow(tr) {
        return {
            n_orden: tr.dataset.nOrden,
            cliente: tr.dataset.cliente || "",
            comuna: tr.dataset.comuna || "",
            direccion: tr.dataset.direccion || "",
        };
    }

    function syncCheckboxes() {
        if (!tbl) return;
        const nums = new Set(paradas.map((p) => p.n_orden));
        tbl.querySelectorAll("tr[data-n-orden]").forEach((tr) => {
            const chk = tr.querySelector(".chk-orden");
            if (chk) chk.checked = nums.has(tr.dataset.nOrden);
        });
    }

    function renderLista() {
        lista.innerHTML = "";
        paradas.forEach((p, idx) => {
            const li = document.createElement("li");
            li.className = "list-group-item d-flex justify-content-between align-items-start bg-black text-white border-secondary mb-1";
            li.draggable = true;
            li.dataset.idx = String(idx);
            li.innerHTML =
                '<div class="me-2"><span class="badge bg-secondary me-1">' + (idx + 1) + "</span>" +
                "<strong>" + escapeHtml(p.n_orden) + "</strong> — " + escapeHtml(p.cliente) +
                '<div class="small text-muted">' + escapeHtml(p.direccion) + "</div></div>" +
                '<button type="button" class="btn btn-sm btn-outline-danger py-0 btn-quitar" data-idx="' + idx + '">×</button>';
            lista.appendChild(li);
        });
        lblCount.textContent = "(" + paradas.length + ")";
        syncCheckboxes();
        bindDragDrop();
        bindQuitar();
    }

    function escapeHtml(s) {
        const d = document.createElement("div");
        d.textContent = s || "";
        return d.innerHTML;
    }

    function bindQuitar() {
        lista.querySelectorAll(".btn-quitar").forEach((btn) => {
            btn.onclick = function () {
                const i = parseInt(btn.dataset.idx, 10);
                paradas.splice(i, 1);
                renderLista();
                bloqueEnlaces.innerHTML = "";
            };
        });
    }

    function bindDragDrop() {
        lista.querySelectorAll("li[draggable]").forEach((li) => {
            li.addEventListener("dragstart", function (e) {
                dragSrc = li;
                e.dataTransfer.effectAllowed = "move";
            });
            li.addEventListener("dragover", function (e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
            });
            li.addEventListener("drop", function (e) {
                e.preventDefault();
                if (!dragSrc || dragSrc === li) return;
                const from = parseInt(dragSrc.dataset.idx, 10);
                const to = parseInt(li.dataset.idx, 10);
                const item = paradas.splice(from, 1)[0];
                paradas.splice(to, 0, item);
                renderLista();
            });
        });
    }

    function toggleOrden(tr, checked) {
        const p = paradaFromRow(tr);
        const idx = paradas.findIndex((x) => x.n_orden === p.n_orden);
        if (checked && idx < 0) {
            paradas.push(p);
        } else if (!checked && idx >= 0) {
            paradas.splice(idx, 1);
        }
        renderLista();
        bloqueEnlaces.innerHTML = "";
    }

    if (tbl) {
        tbl.querySelectorAll("tr[data-n-orden]").forEach((tr) => {
            const chk = tr.querySelector(".chk-orden");
            if (chk) {
                chk.addEventListener("change", function () {
                    toggleOrden(tr, chk.checked);
                });
            }
        });
    }

    document.getElementById("btnSelTodos")?.addEventListener("click", function () {
        if (!tbl) return;
        tbl.querySelectorAll("tr[data-n-orden]").forEach((tr) => {
            const p = paradaFromRow(tr);
            if (!paradas.find((x) => x.n_orden === p.n_orden)) {
                paradas.push(p);
            }
        });
        renderLista();
        bloqueEnlaces.innerHTML = "";
    });

    document.getElementById("btnOrdenComuna")?.addEventListener("click", function () {
        paradas.sort(function (a, b) {
            const ca = (a.comuna || "").localeCompare(b.comuna || "", "es");
            if (ca !== 0) return ca;
            return (a.n_orden || "").localeCompare(b.n_orden || "", "es");
        });
        renderLista();
        bloqueEnlaces.innerHTML = "";
        showAlert("Ordenado por comuna (heurística local, no optimiza distancia).", "info");
    });

    function payload() {
        return {
            origen: inpOrigen?.value || "",
            volver_origen: chkVolver?.checked || false,
            paradas: paradas.map(function (p, i) {
                return {
                    id: i + 1,
                    n_orden: p.n_orden,
                    cliente: p.cliente,
                    comuna: p.comuna,
                    direccion: p.direccion,
                };
            }),
        };
    }

    function renderEnlaces(enlaces) {
        bloqueEnlaces.innerHTML = "";
        if (!enlaces || !enlaces.length) return;
        enlaces.forEach(function (seg) {
            const div = document.createElement("div");
            div.className = "mb-2 p-2 border border-secondary rounded";
            const openA = document.createElement("a");
            openA.href = seg.url;
            openA.target = "_blank";
            openA.rel = "noopener";
            openA.className = "btn btn-sm btn-danger";
            openA.textContent = "Abrir Maps";
            const copyBtn = document.createElement("button");
            copyBtn.type = "button";
            copyBtn.className = "btn btn-sm btn-outline-light btn-copy";
            copyBtn.textContent = "Copiar link";
            copyBtn.dataset.url = seg.url;
            const row = document.createElement("div");
            row.className = "d-flex flex-wrap justify-content-between align-items-center gap-2";
            const title = document.createElement("strong");
            title.className = "text-white";
            title.textContent = seg.titulo;
            const btns = document.createElement("div");
            btns.className = "d-flex gap-1";
            btns.appendChild(openA);
            btns.appendChild(copyBtn);
            row.appendChild(title);
            row.appendChild(btns);
            div.appendChild(row);
            const sub = document.createElement("div");
            sub.className = "small text-muted mt-1";
            sub.textContent = (seg.paradas || []).length + " parada(s)";
            div.appendChild(sub);
            bloqueEnlaces.appendChild(div);
        });
        bloqueEnlaces.querySelectorAll(".btn-copy").forEach(function (btn) {
            btn.addEventListener("click", function () {
                navigator.clipboard.writeText(btn.dataset.url).then(function () {
                    showAlert("Enlace copiado al portapapeles.", "success");
                });
            });
        });
    }

    function postJson(url, body) {
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(function (r) {
            return r.json().then(function (j) {
                return { ok: r.ok, data: j };
            });
        });
    }

    document.getElementById("btnOptimizar")?.addEventListener("click", function () {
        if (!paradas.length) {
            showAlert("Seleccione al menos un pedido.", "warning");
            return;
        }
        hideAlert();
        const btn = document.getElementById("btnOptimizar");
        btn.disabled = true;
        btn.textContent = "Optimizando…";
        postJson(cfg.urls.optimizar, payload())
            .then(function (res) {
                if (!res.ok || !res.data.success) {
                    showAlert(res.data.error || "Error al optimizar.", "danger");
                    return;
                }
                paradas = (res.data.paradas || []).map(function (p) {
                    return {
                        n_orden: p.n_orden,
                        cliente: p.cliente,
                        comuna: p.comuna,
                        direccion: p.direccion,
                    };
                });
                renderLista();
                renderEnlaces(res.data.enlaces);
                let msg = "Ruta optimizada con OpenRouteService.";
                if (res.data.advertencias && res.data.advertencias.length) {
                    msg += " " + res.data.advertencias.join(" ");
                }
                showAlert(msg, "success");
            })
            .catch(function () {
                showAlert("Error de red al optimizar.", "danger");
            })
            .finally(function () {
                btn.disabled = !cfg.orsOk;
                btn.textContent = "Optimizar (ORS)";
            });
    });

    document.getElementById("btnAbrirMaps")?.addEventListener("click", function () {
        if (!paradas.length) {
            showAlert("Seleccione al menos un pedido.", "warning");
            return;
        }
        hideAlert();
        postJson(cfg.urls.enlaces, payload()).then(function (res) {
            if (!res.ok || !res.data.success) {
                showAlert(res.data.error || "No se pudo generar el enlace.", "danger");
                return;
            }
            renderEnlaces(res.data.enlaces);
            if (res.data.enlaces && res.data.enlaces[0]) {
                window.open(res.data.enlaces[0].url, "_blank", "noopener");
            }
        });
    });

    renderLista();
})();
