(function () {
    const $ = id => document.getElementById(id);
    const cacheResumen = {};
    const cacheProducto = {};

    const plotlyLayout = {
        paper_bgcolor: "transparent", plot_bgcolor: "transparent",
        font: { color: "#ccc" }, margin: { t: 30, b: 50, l: 70, r: 20 },
        xaxis: { showgrid: false, tickcolor: "#555" },
        yaxis: { showgrid: true, gridcolor: "#333", tickformat: "$,.0f" },
        legend: { orientation: "h", y: 1.12, font: { size: 12 } }
    };
    const plotlyConfig = { displayModeBar: false, responsive: true };

    let productoActual = null;

    function fmt(n) {
        return HuenteFmt.peso(n);
    }
    function fmtN(n) {
        return HuenteFmt.entero(n);
    }

    function cargarResumen() {
        const empresa = $("fil-empresa").value;
        const sucursal = $("fil-sucursal").value;
        const familia = $("fil-familia").value;
        const params = new URLSearchParams({ empresa });
        if (sucursal) params.set("sucursal", sucursal);
        if (familia) params.set("familia", familia);

        $("detalle-producto").style.display = "none";
        productoActual = null;

        const cacheKey = params.toString();
        if (cacheResumen[cacheKey]) {
            renderResumen(cacheResumen[cacheKey], sucursal, familia);
            return;
        }

        $("loading-hist").style.display = "block";
        $("cards-container").style.display = "none";

        fetch("/api/historico-resumen?" + params)
            .then(r => r.json())
            .then(data => {
                cacheResumen[cacheKey] = data;
                renderResumen(data, sucursal, familia);
            })
            .catch(() => { $("loading-hist").style.display = "none"; });
    }

    function renderResumen(data, sucursal, familia) {
        $("loading-hist").style.display = "none";
        $("cards-container").style.display = "block";

        poblarSelect($("fil-sucursal"), data.sucursales, sucursal);
        poblarSelect($("fil-familia"), data.familias, familia);
        poblarSelect($("sel-producto"), data.productos || [], "");

        const periodoTxt = data.semana_limite
            ? ` <span class="text-muted small fw-normal">(Sem 1-${data.semana_limite} — ${data.año_actual} vs ${data.año_anterior})</span>`
            : "";
        $("lbl-top-neto").innerHTML = "Top Ventas (Neto)" + periodoTxt;
        $("lbl-top-crec").innerHTML = "Mayor Crecimiento" + periodoTxt;
        $("lbl-top-caida").innerHTML = "Mayor Ca\u00edda" + periodoTxt;

        renderCards("cards-top-neto", data.top_neto, "danger", "neto");
        renderCards("cards-top-crec", data.top_crecimiento, "success", "delta");
        renderCards("cards-top-caida", data.top_caida, "warning", "delta");
    }

    function poblarSelect(sel, opciones, valorActual) {
        const primera = sel.options[0].text;
        sel.innerHTML = "";
        const opt0 = document.createElement("option");
        opt0.value = "";
        opt0.textContent = primera;
        sel.appendChild(opt0);
        opciones.forEach(v => {
            const o = document.createElement("option");
            o.value = v;
            o.textContent = v;
            if (v === valorActual) o.selected = true;
            sel.appendChild(o);
        });
    }

    function renderCards(containerId, cards, color, modoMonto) {
        const container = $(containerId);
        if (!cards || cards.length === 0) {
            container.innerHTML = '<div class="col"><p class="text-muted small">Sin datos</p></div>';
            return;
        }
        container.innerHTML = cards.map(c => {
            const varClass = c.var_pct >= 0 ? "text-success" : "text-danger";
            const arrow = c.var_pct >= 0 ? "&#9650;" : "&#9660;";
            const sparkId = "spark_" + Math.random().toString(36).substr(2, 6);
            const lineaMonto = modoMonto === "delta"
                ? `<div class="mt-1">
                        <span class="text-${color} fw-bold fs-6">${HuenteFmt.pesoConSigno(c.variacion)}</span>
                        <div class="text-muted small">Neto act. ${fmt(c.neto_actual)} · ant. ${fmt(c.neto_anterior)}</div>
                   </div>`
                : `<div class="mt-1">
                        <span class="text-${color} fw-bold">${fmt(c.neto_actual)}</span>
                        <span class="text-muted small ms-1">cant: ${fmtN(c.cantidad_actual)}</span>
                   </div>`;
            return `
            <div class="col">
                <div class="card card-producto bg-dark text-white h-100 p-2"
                     data-producto="${c.producto.replace(/"/g, '&quot;')}"
                     onclick="window._selProducto(this)">
                    <div class="d-flex justify-content-between align-items-start">
                        <span class="small fw-bold text-truncate" style="max-width:75%;" title="${c.producto}">${c.producto}</span>
                        <span class="${varClass} small fw-bold">${arrow} ${Math.abs(c.var_pct)}%</span>
                    </div>
                    ${lineaMonto}
                    <canvas id="${sparkId}" class="spark-canvas mt-1"></canvas>
                </div>
            </div>`;
        }).join("");

        cards.forEach((c, i) => {
            const canvasId = container.querySelectorAll("canvas")[i]?.id;
            if (canvasId && c.sparkline && c.sparkline.length > 1) {
                drawSparkline(canvasId, c.sparkline, color);
            }
        });
    }

    function drawSparkline(canvasId, data, color) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const w = canvas.width = canvas.offsetWidth;
        const h = canvas.height = canvas.offsetHeight;
        const max = Math.max(...data);
        const min = Math.min(...data);
        const range = max - min || 1;
        const step = w / (data.length - 1);

        const colorMap = { danger: "#d80000", success: "#198754", warning: "#ffc107" };
        ctx.strokeStyle = colorMap[color] || "#d80000";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        data.forEach((v, i) => {
            const x = i * step;
            const y = h - ((v - min) / range) * (h - 4) - 2;
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
    }

    window._selProducto = function (el) {
        document.querySelectorAll(".card-producto").forEach(c => c.classList.remove("selected"));
        el.classList.add("selected");
        const prod = el.dataset.producto;
        $("sel-producto").value = prod;
        cargarDetalle(prod);
    };

    function cargarDetalle(producto) {
        if (!producto) {
            $("detalle-producto").style.display = "none";
            return;
        }
        productoActual = producto;
        $("detalle-producto").style.display = "block";
        $("label-producto-sel").textContent = producto;

        const empresa = $("fil-empresa").value;
        const sucursal = $("fil-sucursal").value;
        const familia = $("fil-familia").value;
        const params = new URLSearchParams({ empresa, producto });
        if (sucursal) params.set("sucursal", sucursal);
        if (familia) params.set("familia", familia);

        const cacheKey = params.toString();
        if (cacheProducto[cacheKey]) {
            renderDetalle(cacheProducto[cacheKey]);
            return;
        }

        $("detalle-loading").style.display = "block";
        fetch("/api/historico-producto?" + params)
            .then(r => r.json())
            .then(data => {
                cacheProducto[cacheKey] = data;
                renderDetalle(data);
            })
            .catch(() => { $("detalle-loading").style.display = "none"; });
    }

    function renderDetalle(data) {
        $("detalle-loading").style.display = "none";
        renderKPIs(data);
        renderCharts(data);
        renderTabla(data);
    }

    function renderKPIs(data) {
        const t = data.totales;
        const varNeto = t.neto_anterior ? (((t.neto_actual - t.neto_anterior) / Math.abs(t.neto_anterior)) * 100).toFixed(1) : 0;
        const varCant = t.cantidad_anterior ? (((t.cantidad_actual - t.cantidad_anterior) / Math.abs(t.cantidad_anterior)) * 100).toFixed(1) : 0;
        const kpis = [
            { label: "Neto " + data.año_actual, value: fmt(t.neto_actual), color: "info",
              sub: `<span class="${varNeto >= 0 ? "text-success" : "text-danger"}">${varNeto >= 0 ? "&#9650;" : "&#9660;"} ${Math.abs(varNeto)}% vs ${data.año_anterior}</span>` },
            { label: "Neto " + data.año_anterior, value: fmt(t.neto_anterior), color: "secondary", sub: "" },
            { label: "Cantidad " + data.año_actual, value: fmtN(t.cantidad_actual), color: "info",
              sub: `<span class="${varCant >= 0 ? "text-success" : "text-danger"}">${varCant >= 0 ? "&#9650;" : "&#9660;"} ${Math.abs(varCant)}%</span>` },
            { label: "Precio Prom. " + data.año_actual, value: fmt(t.precio_actual), color: "warning",
              sub: `Anterior: ${fmt(t.precio_anterior)}` },
        ];
        $("producto-kpis").innerHTML = kpis.map(k => `
            <div class="col">
                <div class="card bg-dark text-white border-secondary h-100 p-3 text-center shadow">
                    <h6 class="text-uppercase small opacity-75 mb-1">${k.label}</h6>
                    <h3 class="fw-bold text-${k.color} m-0">${k.value}</h3>
                    <small class="mt-1">${k.sub}</small>
                </div>
            </div>`).join("");
    }

    function renderCharts(data) {
        const sems = data.semanas.map(s => "Sem " + s);
        const hoverClp = "%{x}<br><b>%{fullData.name}</b><br>%{customdata}<extra></extra>";
        const hoverQty = "%{x}<br><b>%{fullData.name}</b><br>%{customdata} unidades<extra></extra>";

        Plotly.newPlot("chart-neto", [
            { x: sems, y: data.neto_actual, name: data.año_actual, type: "scatter", mode: "lines+markers",
              line: { color: "#d80000", width: 3 }, marker: { size: 4 },
              customdata: data.neto_actual.map(v => HuenteFmt.peso(v)), hovertemplate: hoverClp },
            { x: sems, y: data.neto_anterior, name: data.año_anterior, type: "scatter", mode: "lines",
              line: { color: "#888", width: 2, dash: "dot" },
              customdata: data.neto_anterior.map(v => HuenteFmt.peso(v)), hovertemplate: hoverClp }
        ], { ...plotlyLayout }, plotlyConfig);

        const lyQty = { ...plotlyLayout, yaxis: { ...plotlyLayout.yaxis, tickformat: ",.0f" } };
        Plotly.newPlot("chart-cantidad", [
            { x: sems, y: data.cant_actual, name: data.año_actual, type: "bar", marker: { color: "#0dcaf0" },
              customdata: data.cant_actual.map(v => HuenteFmt.entero(v)), hovertemplate: hoverQty },
            { x: sems, y: data.cant_anterior, name: data.año_anterior, type: "bar", marker: { color: "#555" },
              customdata: data.cant_anterior.map(v => HuenteFmt.entero(v)), hovertemplate: hoverQty }
        ], { ...lyQty, barmode: "group" }, plotlyConfig);

        Plotly.newPlot("chart-precio", [
            { x: sems, y: data.precio_actual, name: data.año_actual, type: "scatter", mode: "lines+markers",
              line: { color: "#ffc107", width: 2 }, marker: { size: 4 },
              customdata: data.precio_actual.map(v => HuenteFmt.peso(v)), hovertemplate: hoverClp },
            { x: sems, y: data.precio_anterior, name: data.año_anterior, type: "scatter", mode: "lines",
              line: { color: "#888", width: 2, dash: "dot" },
              customdata: data.precio_anterior.map(v => HuenteFmt.peso(v)), hovertemplate: hoverClp }
        ], { ...plotlyLayout }, plotlyConfig);
    }

    function renderTabla(data) {
        $("th-año-act").textContent = data.año_actual;
        $("th-año-ant").textContent = data.año_anterior;
        $("th-año-act2").textContent = data.año_actual;
        $("th-año-ant2").textContent = data.año_anterior;
        $("th-año-act3").textContent = data.año_actual;
        $("th-año-ant3").textContent = data.año_anterior;

        $("tabla-resumen-body").innerHTML = data.resumen_mensual.map(r => {
            const clsNeto = r.neto_actual > r.neto_anterior ? "text-success" : r.neto_actual < r.neto_anterior ? "text-danger" : "";
            return `<tr>
                <td class="text-start ps-3 fw-bold">${r.mes}</td>
                <td class="${clsNeto}">${fmt(r.neto_actual)}</td>
                <td class="text-secondary">${fmt(r.neto_anterior)}</td>
                <td>${fmtN(r.cantidad_actual)}</td>
                <td class="text-secondary">${fmtN(r.cantidad_anterior)}</td>
                <td>${fmt(r.precio_actual)}</td>
                <td class="text-secondary">${fmt(r.precio_anterior)}</td>
            </tr>`;
        }).join("");

        const t = data.totales;
        $("tabla-resumen-foot").innerHTML = `<tr class="fw-bold">
            <td class="text-start ps-3">TOTAL</td>
            <td class="text-info">${fmt(t.neto_actual)}</td>
            <td class="text-secondary">${fmt(t.neto_anterior)}</td>
            <td class="text-info">${fmtN(t.cantidad_actual)}</td>
            <td class="text-secondary">${fmtN(t.cantidad_anterior)}</td>
            <td class="text-info">${fmt(t.precio_actual)}</td>
            <td class="text-secondary">${fmt(t.precio_anterior)}</td>
        </tr>`;
    }

    // Event listeners
    $("fil-empresa").addEventListener("change", () => {
        $("fil-sucursal").value = "";
        $("fil-familia").value = "";
        cargarResumen();
    });
    $("fil-sucursal").addEventListener("change", cargarResumen);
    $("fil-familia").addEventListener("change", cargarResumen);
    $("sel-producto").addEventListener("change", function () {
        document.querySelectorAll(".card-producto").forEach(c => c.classList.remove("selected"));
        if (this.value) {
            document.querySelectorAll(".card-producto").forEach(c => {
                if (c.dataset.producto === this.value) c.classList.add("selected");
            });
            cargarDetalle(this.value);
        }
    });

    // Init
    cargarResumen();
})();
