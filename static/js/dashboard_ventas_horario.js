(function () {
    let sucursalActiva = null;
    let empresaActiva = "comercial";
    let datosCache = null;
    let modoVista = "comparar"; // comparar | detalle
    let diaIdx = null; // null = todos (solo en detalle)

    const COLORES_DIA = ["#d80000", "#0dcaf0", "#ffc107", "#28a745", "#e83e8c", "#6f42c1", "#fd7e14"];
    const HORAS_LABEL = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, "0")}:00`);

    const $ = (id) => document.getElementById(id);

    function mostrarLoading(on) {
        const el = $("loading-overlay");
        el.classList.toggle("d-none", !on);
        el.classList.toggle("d-flex", on);
    }

    function paramsConsulta() {
        return {
            empresa: empresaActiva,
            sucursal: sucursalActiva,
            semana: $("semana").value,
            año: $("año").value,
            desde: $("desde").value,
            hasta: $("hasta").value,
        };
    }

    function qs(obj) {
        return Object.entries(obj)
            .filter(([, v]) => v !== null && v !== undefined && v !== "")
            .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
            .join("&");
    }

    async function cargarSucursales() {
        const res = await fetch(`/api/sucursales-horario?empresa=${empresaActiva}`);
        const lista = await res.json();
        const cont = $("sucursales");
        cont.innerHTML = "";

        if (empresaActiva === "agricola") {
            lista.forEach((s) => {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "btn btn-outline-light btn-sm";
                btn.textContent = s === "TODAS" ? "Todas" : s;
                btn.dataset.sucursal = s;
                btn.addEventListener("click", () => seleccionarSucursal(s, btn));
                cont.appendChild(btn);
            });
            seleccionarSucursal("TODAS", cont.querySelector("button"));
            return;
        }

        if (!lista.length) {
            cont.innerHTML = '<span class="text-muted small">Sin sucursales en BD</span>';
            sucursalActiva = null;
            return;
        }

        lista.forEach((s) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn btn-outline-light btn-sm";
            btn.textContent = s;
            btn.dataset.sucursal = s;
            btn.addEventListener("click", () => seleccionarSucursal(s, btn));
            cont.appendChild(btn);
        });
        seleccionarSucursal(lista[0], cont.querySelector("button"));
    }

    function seleccionarSucursal(s, btn) {
        sucursalActiva = s;
        document.querySelectorAll("#sucursales .btn").forEach((b) => {
            b.classList.remove("btn-danger");
            b.classList.add("btn-outline-light");
        });
        if (btn) {
            btn.classList.remove("btn-outline-light");
            btn.classList.add("btn-danger");
        }
    }

    async function initFechas() {
        const res = await fetch(`/api/latest-date-info?empresa=${empresaActiva}`);
        const data = await res.json();
        if (data.semana) $("semana").value = data.semana;
        if (data.año) $("año").value = data.año;
    }

    function pintarKpis(kpis, meta, extraLabel) {
        $("kpi-neto").textContent = HuenteFmt.pesoConSigno(kpis.neto_total);
        $("kpi-hora-pico").textContent = kpis.hora_pico_label || "—";
        $("kpi-neto-pico").textContent = kpis.neto_hora_pico
            ? HuenteFmt.pesoConSigno(kpis.neto_hora_pico) + " en esa hora"
            : "";
        $("kpi-ticket").textContent = HuenteFmt.pesoConSigno(kpis.ticket_promedio);
        $("kpi-boletas").textContent = HuenteFmt.entero(kpis.total_boletas);
        $("kpi-cantidad").textContent = HuenteFmt.metrico(kpis.total_cantidad);
        let metaTxt = `${meta.filas} líneas · ${meta.empresa} · ${meta.sucursal}`;
        if (extraLabel) metaTxt += " · " + extraLabel;
        $("kpi-meta").textContent = metaTxt;
    }

    function pintarTabla(filas, sinHora) {
        const tbody = $("tabla-horas");
        tbody.innerHTML = "";
        filas.forEach((r) => {
            if (r.neto === 0 && r.boletas === 0) return;
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${r.label}</td>
                <td>${HuenteFmt.pesoConSigno(r.neto)}</td>
                <td>${HuenteFmt.entero(r.boletas)}</td>
                <td>${HuenteFmt.pesoConSigno(r.ticket)}</td>
                <td>${HuenteFmt.metrico(r.cantidad)}</td>
                <td>${r.pct_neto.toFixed(1)}%</td>
            `;
            tbody.appendChild(tr);
        });
        const info = $("sin-hora-info");
        if (sinHora && sinHora.neto > 0) {
            info.textContent = `Sin hora válida: ${HuenteFmt.pesoConSigno(sinHora.neto)} (${HuenteFmt.entero(sinHora.boletas)} boletas)`;
        } else {
            info.textContent = "";
        }
    }

    function pintarTablaDias(porDia) {
        const tbody = $("tabla-dias");
        tbody.innerHTML = "";
        porDia.forEach((d, i) => {
            const tr = document.createElement("tr");
            tr.style.cursor = "pointer";
            tr.title = "Clic para ver detalle de " + d.label;
            tr.innerHTML = `
                <td><span class="badge" style="background:${COLORES_DIA[i]}">${d.label_corto}</span> ${d.label}</td>
                <td>${HuenteFmt.pesoConSigno(d.neto_total)}</td>
                <td>${d.hora_pico_label}</td>
                <td>${HuenteFmt.pesoConSigno(d.neto_hora_pico)}</td>
                <td>${HuenteFmt.entero(d.total_boletas)}</td>
            `;
            tr.addEventListener("click", () => {
                setModoVista("detalle");
                seleccionarDia(i);
            });
            tbody.appendChild(tr);
        });
    }

    function construirChipsDias(porDia) {
        const cont = $("dias-chips");
        cont.innerHTML = "";

        const btnTodos = document.createElement("button");
        btnTodos.type = "button";
        btnTodos.className = "btn btn-sm btn-danger";
        btnTodos.textContent = "Todos";
        btnTodos.dataset.idx = "";
        btnTodos.addEventListener("click", () => seleccionarDia(null));
        cont.appendChild(btnTodos);

        porDia.forEach((d, i) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn btn-sm btn-outline-light";
            btn.textContent = d.label_corto;
            btn.dataset.idx = String(i);
            btn.title = d.label;
            btn.addEventListener("click", () => seleccionarDia(i));
            cont.appendChild(btn);
        });
    }

    function seleccionarDia(idx) {
        diaIdx = idx;
        document.querySelectorAll("#dias-chips .btn").forEach((b) => {
            const active = (idx === null && b.dataset.idx === "") || (idx !== null && b.dataset.idx === String(idx));
            b.classList.toggle("btn-danger", active);
            b.classList.toggle("btn-outline-light", !active);
        });
        if (datosCache) renderVista();
    }

    function setModoVista(modo) {
        modoVista = modo;
        $("btn-vista-comparar").classList.toggle("btn-danger", modo === "comparar");
        $("btn-vista-comparar").classList.toggle("btn-outline-light", modo !== "comparar");
        $("btn-vista-detalle").classList.toggle("btn-danger", modo === "detalle");
        $("btn-vista-detalle").classList.toggle("btn-outline-light", modo !== "detalle");
        $("panel-dias-chips").classList.toggle("d-none", modo !== "detalle");
        $("card-resumen-dias").classList.toggle("d-none", modo !== "comparar");

        if (modo === "comparar") {
            $("titulo-grafico-principal").textContent = "Comparar semana — neto por hora";
            $("subtitulo-grafico").textContent =
                "Cada línea suma todos los lunes, martes, etc. del período filtrado.";
            diaIdx = null;
        } else {
            $("titulo-grafico-principal").textContent = "Detalle por hora";
            $("subtitulo-grafico").textContent =
                "Elige un día o «Todos» para ver el total del período por hora.";
        }
        if (datosCache) renderVista();
    }

    async function chartCompararSemana(porDia) {
        const traces = porDia.map((d, i) => ({
            x: HORAS_LABEL,
            y: d.por_hora.map((r) => r.neto),
            name: d.label_corto,
            type: "scatter",
            mode: "lines+markers",
            line: { color: COLORES_DIA[i], width: 2 },
            marker: { size: 4 },
            customdata: d.por_hora.map((r) => HuenteFmt.peso(r.neto)),
            hovertemplate: `<b>${d.label}</b><br>%{x}<br>Neto: %{customdata}<extra></extra>`,
        }));

        await Plotly.newPlot(
            "chart-barras",
            traces,
            {
                paper_bgcolor: "#111",
                plot_bgcolor: "#111",
                font: { color: "#fff" },
                margin: { t: 40, r: 20, b: 50, l: 60 },
                xaxis: { tickangle: -45, type: "category", title: "Hora del pedido" },
                yaxis: { title: "Neto ($)", tickformat: ",.0f" },
                legend: { orientation: "h", y: 1.15 },
            },
            { responsive: true, displayModeBar: false }
        );
    }

    async function chartBarrasDetalle(filas) {
        const horas = filas.map((r) => r.label);
        const neto = filas.map((r) => r.neto);
        const boletas = filas.map((r) => r.boletas);
        const netoFmt = neto.map((n) => HuenteFmt.peso(n));

        await Plotly.newPlot(
            "chart-barras",
            [
                {
                    x: horas,
                    y: neto,
                    type: "bar",
                    name: "Neto",
                    marker: { color: "#d80000" },
                    customdata: netoFmt,
                    hovertemplate: "%{x}<br>Neto: %{customdata}<extra></extra>",
                },
                {
                    x: horas,
                    y: boletas,
                    type: "scatter",
                    mode: "lines+markers",
                    name: "Boletas",
                    yaxis: "y2",
                    line: { color: "#0dcaf0" },
                    hovertemplate: "%{x}<br>Boletas: %{y}<extra></extra>",
                },
            ],
            {
                paper_bgcolor: "#111",
                plot_bgcolor: "#111",
                font: { color: "#fff" },
                margin: { t: 30, r: 50, b: 50, l: 60 },
                xaxis: { tickangle: -45, type: "category" },
                yaxis: { title: "Neto ($)", tickformat: ",.0f" },
                yaxis2: {
                    title: "Boletas",
                    overlaying: "y",
                    side: "right",
                    tickformat: ",.0f",
                },
                legend: { orientation: "h", y: 1.12 },
            },
            { responsive: true, displayModeBar: false }
        );
    }

    async function chartHeatmap(hm, highlightIdx) {
        const horasLabel = hm.horas.map((h) => `${String(h).padStart(2, "0")}:00`);
        const zText = hm.valores.map((fila) =>
            fila.map((v) => (v > 0 ? HuenteFmt.peso(v) : ""))
        );

        const shapes = [];
        if (highlightIdx !== null && highlightIdx >= 0 && highlightIdx < hm.dias.length) {
            shapes.push({
                type: "rect",
                xref: "paper",
                yref: "y",
                x0: 0,
                x1: 1,
                y0: hm.dias[highlightIdx],
                y1: hm.dias[highlightIdx],
                line: { color: "#0dcaf0", width: 3 },
                fillcolor: "rgba(13,202,240,0.08)",
            });
        }

        await Plotly.newPlot(
            "chart-heatmap",
            [
                {
                    z: hm.valores,
                    x: horasLabel,
                    y: hm.dias,
                    text: zText,
                    type: "heatmap",
                    colorscale: [
                        [0, "#111"],
                        [0.2, "#4a0010"],
                        [0.5, "#d80000"],
                        [1, "#ff6b6b"],
                    ],
                    hoverongaps: false,
                    hovertemplate: "%{y} · %{x}<br>Neto: %{text}<extra></extra>",
                },
            ],
            {
                paper_bgcolor: "#111",
                plot_bgcolor: "#111",
                font: { color: "#fff" },
                margin: { t: 30, l: 90, r: 20, b: 60 },
                xaxis: { tickangle: -45, type: "category" },
                shapes,
            },
            { responsive: true, displayModeBar: false }
        );
    }

    async function renderVista() {
        if (!datosCache || typeof Plotly === "undefined") return;

        const { por_dia, por_hora, heatmap, sin_hora, kpis, meta } = datosCache;

        if (modoVista === "comparar") {
            pintarKpis(kpis, meta, "vista comparar semana");
            pintarTabla(por_hora, sin_hora);
            await chartCompararSemana(por_dia);
            await chartHeatmap(heatmap, null);
            return;
        }

        let filas = por_hora;
        let kpiView = kpis;
        let labelExtra = "todos los días";
        let highlight = null;

        if (diaIdx !== null && por_dia[diaIdx]) {
            const d = por_dia[diaIdx];
            filas = d.por_hora;
            kpiView = {
                neto_total: d.neto_total,
                hora_pico_label: d.hora_pico_label,
                neto_hora_pico: d.neto_hora_pico,
                ticket_promedio: _ticketFromDia(d),
                total_boletas: d.total_boletas,
                total_cantidad: filas.reduce((s, r) => s + r.cantidad, 0),
            };
            labelExtra = d.label;
            highlight = diaIdx;
        }

        pintarKpis(kpiView, meta, labelExtra);
        pintarTabla(filas, diaIdx === null ? sin_hora : { neto: 0, boletas: 0 });
        await chartBarrasDetalle(filas);
        await chartHeatmap(heatmap, highlight);
    }

    function _ticketFromDia(d) {
        if (!d.total_boletas) return 0;
        return Math.round(d.neto_total / d.total_boletas);
    }

    async function consultar() {
        const alert = $("alert-filtros");
        alert.classList.add("d-none");

        if (empresaActiva === "comercial" && !sucursalActiva) {
            alert.textContent = "Selecciona una sucursal.";
            alert.classList.remove("d-none");
            return;
        }

        const p = paramsConsulta();
        const tieneFechas = p.desde && p.hasta;
        const tieneSemana = p.semana && p.año;
        if (!tieneFechas && !tieneSemana) {
            alert.textContent = "Indica Semana+Año o rango Desde/Hasta.";
            alert.classList.remove("d-none");
            return;
        }

        mostrarLoading(true);
        try {
            const res = await fetch(`/api/dashboard-ventas-horario?${qs(p)}`);
            const data = await res.json();
            if (!res.ok) {
                alert.textContent = data.error || "Error al consultar";
                alert.classList.remove("d-none");
                return;
            }
            datosCache = data;
            construirChipsDias(data.por_dia);
            pintarTablaDias(data.por_dia);
            try {
                await renderVista();
            } catch (chartErr) {
                console.error("Error gráficos horario:", chartErr);
                alert.textContent = "Datos OK, pero falló el gráfico. Recarga la página (F5).";
                alert.classList.remove("d-none");
            }
        } catch (e) {
            console.error("Error consulta horario:", e);
            alert.textContent = "Error de conexión o al leer datos.";
            alert.classList.remove("d-none");
        } finally {
            mostrarLoading(false);
        }
    }

    document.addEventListener("DOMContentLoaded", async function () {
        $("btn-vista-comparar").addEventListener("click", () => setModoVista("comparar"));
        $("btn-vista-detalle").addEventListener("click", () => setModoVista("detalle"));

        $("empresa").addEventListener("change", async function () {
            empresaActiva = this.value;
            $("desde").value = "";
            $("hasta").value = "";
            await initFechas();
            await cargarSucursales();
        });

        ["semana", "año"].forEach((id) => {
            $(id).addEventListener("change", () => {
                $("desde").value = "";
                $("hasta").value = "";
            });
        });
        ["desde", "hasta"].forEach((id) => {
            $(id).addEventListener("change", () => {
                $("semana").value = "";
                $("año").value = "";
            });
        });

        $("btn-consultar").addEventListener("click", consultar);

        setModoVista("comparar");
        await initFechas();
        await cargarSucursales();
        await consultar();
    });
})();
