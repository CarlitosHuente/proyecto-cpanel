(function () {
    function overlay(texto) {
        var el = document.getElementById("loading-overlay");
        var msg = document.getElementById("loading-overlay-msg");
        if (msg && texto) msg.textContent = texto;
        if (el) el.style.display = "flex";
    }

    function ocultarOverlay() {
        var el = document.getElementById("loading-overlay");
        if (el) el.style.display = "none";
    }

    function mostrarError(texto) {
        var box = document.getElementById("form-error");
        if (!box) {
            window.alert(texto);
            return;
        }
        box.textContent = texto;
        box.classList.remove("d-none");
    }

    async function postJson(url, body) {
        var resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body || {})
        });
        var data = await resp.json().catch(function () { return {}; });
        if (!resp.ok || data.ok === false) {
            throw new Error(data.error || "No se pudo completar la acción.");
        }
        return data;
    }

    document.querySelectorAll(".btn-enviar").forEach(function (btn) {
        btn.addEventListener("click", async function () {
            var id = btn.getAttribute("data-id");
            var actuales = (btn.getAttribute("data-correos") || "").trim();
            var correos = actuales;
            if (!correos) {
                correos = window.prompt("Correos separados por coma", "");
                if (!correos) return;
            }
            overlay("Enviando informe…");
            try {
                var data = await postJson("/reporteria/" + id + "/enviar", { correos: correos });
                ocultarOverlay();
                window.alert("Enviado a " + (data.destinos || []).join(", "));
                if (!actuales) btn.setAttribute("data-correos", correos);
            } catch (err) {
                ocultarOverlay();
                window.alert(err.message || "No se pudo enviar.");
            }
        });
    });

    document.querySelectorAll(".btn-eliminar").forEach(function (btn) {
        btn.addEventListener("click", async function () {
            if (!window.confirm("¿Eliminar este reporte?")) return;
            overlay("Eliminando…");
            try {
                await postJson("/reporteria/" + btn.getAttribute("data-id") + "/eliminar", {});
                window.location.reload();
            } catch (err) {
                ocultarOverlay();
                window.alert(err.message || "No se pudo eliminar.");
            }
        });
    });

    var form = document.getElementById("form-reporte");
    if (!form || !window.REPORTERIA) return;

    var cfg = window.REPORTERIA;

    function corteActual() {
        var corte = document.querySelector("input[name=corte]:checked");
        return corte ? corte.value : "semanal";
    }

    function syncPeriodo() {
        var semanal = corteActual() === "semanal";
        var num = document.getElementById("periodo-num");
        var label = document.getElementById("label-periodo");
        if (num) {
            num.max = semanal ? "53" : "12";
            num.placeholder = semanal ? "Semana" : "Mes";
        }
        if (label) label.textContent = semanal ? "Semana base" : "Mes base";
    }

    document.querySelectorAll("input[name=corte]").forEach(function (el) {
        el.addEventListener("change", syncPeriodo);
    });
    syncPeriodo();

    function leer() {
        var num = document.getElementById("periodo-num").value.trim();
        var anio = document.getElementById("periodo-anio").value.trim();
        return {
            id: document.getElementById("reporte-id").value ? Number(document.getElementById("reporte-id").value) : null,
            nombre: document.getElementById("nombre").value.trim() || "Reporte Ventas",
            empresa: document.getElementById("empresa").value,
            corte: corteActual(),
            periodo_num: num || null,
            periodo_anio: anio || null,
            correos: document.getElementById("correos").value
        };
    }

    document.getElementById("btn-guardar").addEventListener("click", async function () {
        var box = document.getElementById("form-error");
        if (box) box.classList.add("d-none");
        try {
            var data = await postJson(cfg.guardarUrl, leer());
            document.getElementById("reporte-id").value = data.id;
            mostrarError("Filtros guardados. Genera el PDF cuando quieras.");
            box.classList.remove("alert-warning");
            box.classList.add("alert-success");
        } catch (err) {
            if (box) {
                box.classList.add("alert-warning");
                box.classList.remove("alert-success");
            }
            mostrarError(err.message);
        }
    });

    document.getElementById("btn-generar").addEventListener("click", async function () {
        var box = document.getElementById("form-error");
        if (box) box.classList.add("d-none");
        overlay("Generando informe, por favor espere…");
        try {
            var saved = await postJson(cfg.guardarUrl, leer());
            document.getElementById("reporte-id").value = saved.id;
            await postJson("/reporteria/" + saved.id + "/generar", {});
            window.location = cfg.listaUrl;
        } catch (err) {
            ocultarOverlay();
            if (box) {
                box.classList.add("alert-warning");
                box.classList.remove("alert-success");
            }
            mostrarError(err.message);
        }
    });
})();
