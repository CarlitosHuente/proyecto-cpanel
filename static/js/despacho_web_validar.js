(function () {
    const cfg = window.DW_VALIDAR;
    if (!cfg) return;

    const lineasEl = document.getElementById("lineasDetalle");
    const form = document.getElementById("formOrden");
    const alertDup = document.getElementById("alertDuplicado");
    const alertErr = document.getElementById("alertError");
    const btnGuardar = document.getElementById("btnGuardar");

    function escHtml(s) {
        return String(s || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/"/g, "&quot;");
    }

    function actualizarDireccionCompleta() {
        const dirEl = document.getElementById("direccion");
        if (dirEl.dataset.manual === "1") return;
        const calle = document.getElementById("calle").value.trim();
        const comuna = document.getElementById("comuna").value.trim();
        let full = calle;
        if (comuna && !calle.toLowerCase().includes(comuna.toLowerCase())) {
            full = calle ? calle + ", " + comuna : comuna;
        }
        dirEl.value = full;
    }

    document.getElementById("direccion").addEventListener("input", function () {
        this.dataset.manual = "1";
    });

    function normalizarCelularVisual(raw) {
        const d = String(raw || "").replace(/\D/g, "");
        if (!d) return { ok: false, msg: "Ingrese celular (9 dígitos o +569…)" };
        let n = d;
        if (n.startsWith("56")) n = n.slice(2);
        if (n.length === 9 && n.startsWith("9")) return { ok: true, fmt: "+56" + n };
        if (n.length === 8) return { ok: true, fmt: "+569" + n };
        if (n.length > 9 && n.slice(-9).startsWith("9")) return { ok: true, fmt: "+56" + n.slice(-9) };
        return { ok: false, msg: "Formato no válido; use 9XXXXXXXX o +569XXXXXXXX" };
    }

    const celularInp = document.getElementById("celular");
    const celularHint = document.getElementById("celularHint");

    function refreshCelularHint() {
        const r = normalizarCelularVisual(celularInp.value);
        if (r.ok) {
            celularHint.textContent = "Se guardará como: " + r.fmt;
            celularHint.className = "form-text text-success";
        } else {
            celularHint.textContent = r.msg;
            celularHint.className = "form-text text-warning";
        }
    }

    celularInp.addEventListener("input", refreshCelularHint);
    celularInp.addEventListener("blur", function () {
        const r = normalizarCelularVisual(this.value);
        if (r.ok) this.value = r.fmt;
        refreshCelularHint();
    });
    refreshCelularHint();

    document.getElementById("calle").addEventListener("input", actualizarDireccionCompleta);
    document.getElementById("comuna").addEventListener("input", actualizarDireccionCompleta);
    actualizarDireccionCompleta();

    function opcionesProducto(selected) {
        const names = cfg.productos || [];
        let html = '<option value="">— Seleccione —</option>';
        names.forEach(function (n) {
            const sel = n === selected ? " selected" : "";
            html += '<option value="' + escHtml(n) + '"' + sel + ">" + escHtml(n) + "</option>";
        });
        if (selected && names.indexOf(selected) === -1) {
            html += '<option value="' + escHtml(selected) + '" selected>' + escHtml(selected) + " (PDF)</option>";
        }
        return html;
    }

    const autoCreados = new Set(cfg.productosAutoCreados || []);

    function filaLinea(ln, idx) {
        const prod = ln.producto || "";
        const cant = ln.cantidad != null ? ln.cantidad : 1;
        const total = ln.total != null ? ln.total : 0;
        const badge =
            prod && autoCreados.has(prod)
                ? '<span class="badge bg-info text-dark ms-1 linea-badge-nuevo" title="Creado automático desde PDF">Nuevo</span>'
                : "";
        return (
            '<div class="row g-1 mb-2 linea-row align-items-center" data-idx="' +
            idx +
            '">' +
            '<div class="col-5"><div class="d-flex align-items-center gap-1">' +
            '<select class="form-select bg-black text-white border-secondary linea-prod flex-grow-1" required>' +
            opcionesProducto(prod) +
            "</select>" +
            badge +
            "</div></div>" +
            '<div class="col-2"><input type="number" step="0.01" min="0" class="form-control bg-black text-white border-secondary linea-cant" value="' +
            cant +
            '"></div>' +
            '<div class="col-3"><input type="number" step="1" min="0" class="form-control bg-black text-white border-secondary linea-total" value="' +
            total +
            '"></div>' +
            '<div class="col-2"><button type="button" class="btn btn-sm btn-outline-danger w-100 btn-del-linea">×</button></div>' +
            "</div>"
        );
    }

    function renderLineas(lineas) {
        lineasEl.innerHTML = "";
        (lineas || []).forEach(function (ln, i) {
            lineasEl.insertAdjacentHTML("beforeend", filaLinea(ln, i));
        });
        bindLineaEvents();
    }

    function bindLineaEvents() {
        lineasEl.querySelectorAll(".btn-del-linea").forEach(function (btn) {
            btn.onclick = function () {
                btn.closest(".linea-row").remove();
            };
        });
    }

    document.getElementById("btnAddLinea").addEventListener("click", function () {
        lineasEl.insertAdjacentHTML("beforeend", filaLinea({ producto: "", cantidad: 1, total: 0 }, Date.now()));
        bindLineaEvents();
    });

    renderLineas(cfg.lineasIniciales || []);

    function recolectarLineas() {
        const out = [];
        lineasEl.querySelectorAll(".linea-row").forEach(function (row) {
            const producto = row.querySelector(".linea-prod").value.trim();
            if (!producto) return;
            out.push({
                producto: producto,
                cantidad: parseFloat(row.querySelector(".linea-cant").value) || 0,
                total: parseInt(row.querySelector(".linea-total").value, 10) || 0,
            });
        });
        return out;
    }

    function recolectarOrden() {
        const fd = new FormData(form);
        const o = {};
        fd.forEach(function (v, k) {
            o[k] = v;
        });
        return o;
    }

    async function checkDuplicado(nOrden) {
        const res = await fetch(cfg.urls.duplicado + "?n_orden=" + encodeURIComponent(nOrden));
        const data = await res.json();
        return data.existe;
    }

    document.getElementById("n_orden").addEventListener("blur", async function () {
        const n = this.value.trim();
        alertDup.classList.add("d-none");
        if (!n) return;
        if (await checkDuplicado(n)) {
            alertDup.textContent = "La Orden N° " + n + " ya existe en el sistema";
            alertDup.classList.remove("d-none");
        }
    });

    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        alertErr.classList.add("d-none");
        alertDup.classList.add("d-none");

        const orden = recolectarOrden();
        const lineas = recolectarLineas();
        const celCheck = normalizarCelularVisual(orden.celular);
        if (!celCheck.ok) {
            alertErr.textContent = celCheck.msg;
            alertErr.classList.remove("d-none");
            return;
        }
        orden.celular = celCheck.fmt;
        if (!lineas.length) {
            alertErr.textContent = "Agregue al menos una línea de detalle.";
            alertErr.classList.remove("d-none");
            return;
        }

        if (await checkDuplicado(orden.n_orden)) {
            alertDup.textContent = "La Orden N° " + orden.n_orden + " ya existe en el sistema";
            alertDup.classList.remove("d-none");
            return;
        }

        btnGuardar.disabled = true;
        btnGuardar.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Guardando…';

        try {
            const res = await fetch(cfg.urls.guardar, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    batch_id: cfg.batchId,
                    idx: cfg.idx,
                    orden: orden,
                    lineas: lineas,
                }),
            });
            const data = await res.json();
            if (!data.success) {
                if (res.status === 409) {
                    alertDup.textContent = data.error || "Orden duplicada";
                    alertDup.classList.remove("d-none");
                } else {
                    alertErr.textContent = data.error || "Error al guardar";
                    alertErr.classList.remove("d-none");
                }
                return;
            }
            window.location.href = data.redirect;
        } catch (err) {
            alertErr.textContent = String(err);
            alertErr.classList.remove("d-none");
        } finally {
            btnGuardar.disabled = false;
            btnGuardar.innerHTML = '<i class="bi bi-check2-circle me-2"></i>Guardar y continuar';
        }
    });

    document.getElementById("btnOmitir").addEventListener("click", async function () {
        if (!confirm("¿Omitir esta factura sin guardar?")) return;
        const res = await fetch(cfg.urls.omitir, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ batch_id: cfg.batchId, idx: cfg.idx }),
        });
        const data = await res.json();
        if (data.success) window.location.href = data.redirect;
    });
})();
