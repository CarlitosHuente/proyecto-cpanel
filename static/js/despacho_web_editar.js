(function () {
    const cfg = window.DW_EDIT;
    if (!cfg) return;

    const lineasEl = document.getElementById("lineasDetalle");
    const form = document.getElementById("formOrdenEdit");
    const alertOk = document.getElementById("alertOk");
    const alertErr = document.getElementById("alertErr");

    function escHtml(s) {
        return String(s || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/"/g, "&quot;");
    }

    function opcionesProducto(selected) {
        let html = '<option value="">— Seleccione —</option>';
        (cfg.productos || []).forEach(function (n) {
            html += '<option value="' + escHtml(n) + '"' + (n === selected ? " selected" : "") + ">" + escHtml(n) + "</option>";
        });
        if (selected && (cfg.productos || []).indexOf(selected) === -1) {
            html += '<option value="' + escHtml(selected) + '" selected>' + escHtml(selected) + "</option>";
        }
        return html;
    }

    function filaLinea(ln) {
        return (
            '<div class="row g-1 mb-2 linea-row">' +
            '<div class="col-5"><select class="form-select bg-black text-white border-secondary linea-prod" required>' +
            opcionesProducto(ln.producto || "") +
            "</select></div>" +
            '<div class="col-2"><input type="number" step="0.01" min="0" class="form-control bg-black text-white border-secondary linea-cant" value="' +
            (ln.cantidad != null ? ln.cantidad : 1) +
            '"></div>' +
            '<div class="col-3"><input type="number" step="1" min="0" class="form-control bg-black text-white border-secondary linea-total" value="' +
            (ln.total != null ? ln.total : 0) +
            '"></div>' +
            '<div class="col-2"><button type="button" class="btn btn-sm btn-outline-danger w-100 btn-del-linea">×</button></div>' +
            "</div>"
        );
    }

    function bindLineaEvents() {
        lineasEl.querySelectorAll(".btn-del-linea").forEach(function (btn) {
            btn.onclick = function () {
                btn.closest(".linea-row").remove();
            };
        });
    }

    function renderLineas(lineas) {
        lineasEl.innerHTML = "";
        (lineas || []).forEach(function (ln) {
            lineasEl.insertAdjacentHTML("beforeend", filaLinea(ln));
        });
        bindLineaEvents();
    }

    document.getElementById("btnAddLinea").addEventListener("click", function () {
        lineasEl.insertAdjacentHTML("beforeend", filaLinea({ producto: "", cantidad: 1, total: 0 }));
        bindLineaEvents();
    });

    renderLineas(
        (cfg.lineasIniciales || []).map(function (ln) {
            return { producto: ln.producto, cantidad: ln.cantidad, total: ln.total };
        })
    );

    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        alertOk.classList.add("d-none");
        alertErr.classList.add("d-none");

        const fd = new FormData(form);
        const orden = {};
        fd.forEach(function (v, k) {
            orden[k] = v;
        });

        const lineas = [];
        lineasEl.querySelectorAll(".linea-row").forEach(function (row) {
            const producto = row.querySelector(".linea-prod").value.trim();
            if (!producto) return;
            lineas.push({
                producto: producto,
                cantidad: parseFloat(row.querySelector(".linea-cant").value) || 0,
                total: parseInt(row.querySelector(".linea-total").value, 10) || 0,
            });
        });

        if (!lineas.length) {
            alertErr.textContent = "Agregue al menos una línea.";
            alertErr.classList.remove("d-none");
            return;
        }

        try {
            const res = await fetch(cfg.guardarUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ orden: orden, lineas: lineas }),
            });
            const data = await res.json();
            if (!data.success) {
                alertErr.textContent = data.error || "Error al guardar";
                alertErr.classList.remove("d-none");
                return;
            }
            alertOk.textContent = data.mensaje || "Guardado.";
            alertOk.classList.remove("d-none");
            window.scrollTo(0, 0);
        } catch (err) {
            alertErr.textContent = String(err);
            alertErr.classList.remove("d-none");
        }
    });

    document.getElementById("btnEliminar").addEventListener("click", function () {
        if (confirm("¿Eliminar esta orden y todo su detalle?")) {
            document.getElementById("formEliminar").submit();
        }
    });
})();
