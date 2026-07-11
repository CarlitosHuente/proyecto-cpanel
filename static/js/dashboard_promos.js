(function () {
    let sucursalActiva = null;
    let datosCache = null;

    const $ = (id) => document.getElementById(id);

    function mostrarLoading(on) {
        const el = $("loading-overlay");
        el.classList.toggle("d-none", !on);
        el.classList.toggle("d-flex", on);
    }

    function paramsConsulta() {
        return {
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

    function mostrarAlerta(msg) {
        const el = $("alert-filtros");
        if (!msg) {
            el.classList.add("d-none");
            el.textContent = "";
            return;
        }
        el.textContent = msg;
        el.classList.remove("d-none");
    }

    async function cargarSucursales() {
        const res = await fetch("/api/sucursales-horario?empresa=comercial");
        const lista = await res.json();
        const cont = $("sucursales");
        cont.innerHTML = "";

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
        const res = await fetch("/api/latest-date-info?empresa=comercial");
        const data = await res.json();
        if (data.semana) $("semana").value = data.semana;
        if (data.año) $("año").value = data.año;
    }

    function pintarKpis(kpis, meta) {
        $("kpi-packs").textContent = HuenteFmt.metrico(kpis.packs_promo);
        $("kpi-packs-dia").textContent = kpis.dias_con_venta
            ? `${HuenteFmt.metrico(kpis.packs_por_dia)} packs/día · ${HuenteFmt.entero(kpis.dias_con_venta)} días`
            : "";
        $("kpi-neto-promo").textContent = HuenteFmt.peso(kpis.neto_promo);
        $("kpi-pct-boletas").textContent =
            kpis.pct_boletas_con_promo != null
                ? Number(kpis.pct_boletas_con_promo).toFixed(1) + "%"
                : "—";
        $("kpi-boletas-detalle").textContent =
            kpis.total_boletas
                ? `${HuenteFmt.entero(kpis.boletas_con_promo)} / ${HuenteFmt.entero(kpis.total_boletas)} boletas`
                : "";
        $("kpi-pct-emp").textContent =
            kpis.pct_empanadas_promo != null
                ? Number(kpis.pct_empanadas_promo).toFixed(1) + "%"
                : "—";
        $("kpi-meta").textContent = `${meta.filas || 0} líneas · ${meta.sucursal}`;
        $("kpi-ticket-con").textContent = HuenteFmt.peso(kpis.ticket_con_promo);
        $("kpi-ticket-sin").textContent = HuenteFmt.peso(kpis.ticket_sin_promo);
        $("kpi-pe-emp-promo").textContent = HuenteFmt.peso(kpis.precio_efectivo_emp_promo);
        $("kpi-pe-emp-indiv").textContent = HuenteFmt.peso(kpis.precio_efectivo_emp_indiv);
        $("kpi-acompanamiento").textContent =
            `Acomp. néctar ${HuenteFmt.metrico(kpis.packs_con_nectar)} · bebida ${HuenteFmt.metrico(kpis.packs_con_bebida)} packs`;
    }

    function pintarTablaCategorias(filas) {
        const tbody = $("tabla-categorias");
        tbody.innerHTML = "";
        (filas || []).forEach((r) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td class="text-start">${r.categoria}</td>
                <td>${HuenteFmt.metrico(r.total)}</td>
                <td>${HuenteFmt.metrico(r.promo)}</td>
                <td>${HuenteFmt.metrico(r.individual)}</td>
                <td>${Number(r.pct_promo).toFixed(1)}%</td>
                <td>${HuenteFmt.peso(r.precio_efectivo_promo)}</td>
                <td>${HuenteFmt.peso(r.precio_efectivo_indiv)}</td>
                <td>${HuenteFmt.metrico(r.unidades_dia)}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    function pintarTablaCombos(ranking, sinReceta) {
        const tbody = $("tabla-combos");
        tbody.innerHTML = "";
        (ranking || []).forEach((r) => {
            const u = r.unidades || {};
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td class="text-start">${r.descripcion}</td>
                <td>${HuenteFmt.metrico(r.packs)}</td>
                <td>${Number(r.pct_mix || 0).toFixed(1)}%</td>
                <td>${HuenteFmt.peso(r.neto)}</td>
                <td>${HuenteFmt.peso(r.precio_bruto_prom)}</td>
                <td>${HuenteFmt.metrico(u.Empanadas || 0)}</td>
                <td>${HuenteFmt.metrico(u.Nectar || 0)}</td>
                <td>${HuenteFmt.metrico(u.Bebidas || 0)}</td>
                <td>${HuenteFmt.metrico(u.Helados || 0)}</td>
                <td>${r.con_receta ? "Sí" : '<span class="text-warning">Sin receta</span>'}</td>
            `;
            tbody.appendChild(tr);
        });
        const info = $("sin-receta-info");
        const n = (sinReceta || []).length;
        info.textContent = n
            ? `${n} combo(s) sin receta configurada (no aportan unidades derivadas)`
            : "";
    }

    function pintarChartCategorias(filas) {
        const cats = (filas || []).map((r) => r.categoria);
        const promo = (filas || []).map((r) => r.promo);
        const indiv = (filas || []).map((r) => r.individual);
        Plotly.newPlot(
            "chart-categorias",
            [
                {
                    type: "bar",
                    name: "En promoción",
                    x: cats,
                    y: promo,
                    marker: { color: "#d80000" },
                    hovertemplate: "%{x}<br>Promo: %{y}<extra></extra>",
                },
                {
                    type: "bar",
                    name: "Individual",
                    x: cats,
                    y: indiv,
                    marker: { color: "#0dcaf0" },
                    hovertemplate: "%{x}<br>Individual: %{y}<extra></extra>",
                },
            ],
            {
                barmode: "stack",
                paper_bgcolor: "rgba(0,0,0,0)",
                plot_bgcolor: "rgba(0,0,0,0)",
                font: { color: "#ccc" },
                margin: { t: 20, r: 20, b: 40, l: 50 },
                legend: { orientation: "h", y: 1.12 },
                yaxis: { title: "Unidades", gridcolor: "#333" },
                xaxis: { gridcolor: "#333" },
            },
            { responsive: true, displayModeBar: false }
        );
    }

    function pintarChartCombos(ranking) {
        const top = (ranking || []).slice(0, 10);
        const labels = top.map((r) => r.descripcion);
        const packs = top.map((r) => r.packs);
        Plotly.newPlot(
            "chart-combos",
            [
                {
                    type: "bar",
                    orientation: "h",
                    y: labels.slice().reverse(),
                    x: packs.slice().reverse(),
                    marker: { color: "#ffc107" },
                    hovertemplate: "%{y}<br>Packs: %{x}<extra></extra>",
                },
            ],
            {
                paper_bgcolor: "rgba(0,0,0,0)",
                plot_bgcolor: "rgba(0,0,0,0)",
                font: { color: "#ccc" },
                margin: { t: 20, r: 20, b: 40, l: 160 },
                xaxis: { title: "Packs", gridcolor: "#333" },
                yaxis: { automargin: true },
            },
            { responsive: true, displayModeBar: false }
        );
    }

    function pintarChartPrecioEfectivo(filas) {
        const cats = (filas || []).map((r) => r.categoria);
        const promo = (filas || []).map((r) => r.precio_efectivo_promo || 0);
        const indiv = (filas || []).map((r) => r.precio_efectivo_indiv || 0);
        Plotly.newPlot(
            "chart-precio-efectivo",
            [
                {
                    type: "bar",
                    name: "En promo",
                    x: cats,
                    y: promo,
                    marker: { color: "#d80000" },
                    customdata: promo,
                    hovertemplate: "%{x}<br>Promo: %{customdata:$,.0f}<extra></extra>",
                },
                {
                    type: "bar",
                    name: "Individual",
                    x: cats,
                    y: indiv,
                    marker: { color: "#0dcaf0" },
                    customdata: indiv,
                    hovertemplate: "%{x}<br>Individual: %{customdata:$,.0f}<extra></extra>",
                },
            ],
            {
                barmode: "group",
                paper_bgcolor: "rgba(0,0,0,0)",
                plot_bgcolor: "rgba(0,0,0,0)",
                font: { color: "#ccc" },
                margin: { t: 20, r: 20, b: 40, l: 50 },
                legend: { orientation: "h", y: 1.12 },
                yaxis: { title: "Neto $ / unidad", gridcolor: "#333" },
                xaxis: { gridcolor: "#333" },
            },
            { responsive: true, displayModeBar: false }
        );
    }

    function itemSeleccionado() {
        const tipo = $("sim-tipo").value;
        const key = $("sim-item").value;
        if (!datosCache || !datosCache.precios_base) return null;
        if (tipo === "combo") {
            return (datosCache.precios_base.combos || []).find(
                (c) => c.descripcion === key
            );
        }
        return (datosCache.precios_base.categorias || []).find(
            (c) => c.categoria === key
        );
    }

    function poblarSimuladorItems() {
        const sel = $("sim-item");
        sel.innerHTML = "";
        if (!datosCache || !datosCache.precios_base) return;
        const tipo = $("sim-tipo").value;
        if (tipo === "combo") {
            (datosCache.precios_base.combos || []).forEach((c) => {
                const opt = document.createElement("option");
                opt.value = c.descripcion;
                opt.textContent = c.descripcion;
                sel.appendChild(opt);
            });
        } else {
            (datosCache.precios_base.categorias || []).forEach((c) => {
                const opt = document.createElement("option");
                opt.value = c.categoria;
                opt.textContent = c.categoria + " (venta suelta)";
                sel.appendChild(opt);
            });
        }
        sincronizarSimulador();
    }

    function sincronizarSimulador() {
        const item = itemSeleccionado();
        const tipo = $("sim-tipo").value;
        if (!item) {
            $("sim-precio-actual").value = "";
            $("sim-precio-nuevo").value = "";
            $("sim-volumen").textContent = "—";
            $("sim-neto-actual").textContent = "—";
            $("sim-neto-nuevo").textContent = "—";
            $("sim-delta").textContent = "—";
            $("sim-delta-pct").textContent = "—";
            return;
        }
        const precio = Number(item.precio_bruto_actual) || 0;
        $("sim-precio-actual").value = HuenteFmt.peso(precio);
        if (!$("sim-precio-nuevo").dataset.touched) {
            $("sim-precio-nuevo").value = String(Math.round(precio));
        }
        if (tipo === "combo") {
            $("sim-volumen").textContent = HuenteFmt.metrico(item.packs) + " packs";
        } else {
            $("sim-volumen").textContent =
                HuenteFmt.metrico(item.unidades_individual) + " unidades";
        }
        calcularSimulador();
    }

    function calcularSimulador() {
        const item = itemSeleccionado();
        const tipo = $("sim-tipo").value;
        if (!item) return;

        const precioNuevo = Math.round(Number($("sim-precio-nuevo").value) || 0);
        const sens = Number($("sim-sens").value) || 0;
        $("sim-sens-label").textContent = (sens >= 0 ? "+" : "") + sens + "%";
        const factorVol = 1 + sens / 100;

        let netoActual;
        let netoNuevo;
        if (tipo === "combo") {
            const packs = Number(item.packs) || 0;
            netoActual = Math.round(Number(item.neto_actual) || 0);
            const packsAdj = packs * factorVol;
            netoNuevo = Math.round((packsAdj * precioNuevo) / 1.19);
        } else {
            const unidades = Number(item.unidades_individual) || 0;
            netoActual = Math.round(Number(item.neto_individual_actual) || 0);
            const uAdj = unidades * factorVol;
            netoNuevo = Math.round((uAdj * precioNuevo) / 1.19);
        }

        const delta = netoNuevo - netoActual;
        const deltaPct = netoActual ? (100.0 * delta) / netoActual : 0;

        $("sim-neto-actual").textContent = HuenteFmt.peso(netoActual);
        $("sim-neto-nuevo").textContent = HuenteFmt.peso(netoNuevo);
        const deltaEl = $("sim-delta");
        deltaEl.textContent = HuenteFmt.pesoConSigno(delta);
        deltaEl.className = "kpi-valor " + (delta >= 0 ? "sim-delta-pos" : "sim-delta-neg");
        const pctEl = $("sim-delta-pct");
        pctEl.textContent = (deltaPct >= 0 ? "+" : "") + deltaPct.toFixed(1) + "%";
        pctEl.className = "kpi-valor " + (deltaPct >= 0 ? "sim-delta-pos" : "sim-delta-neg");
    }

    async function consultar() {
        mostrarAlerta("");
        if (!sucursalActiva) {
            mostrarAlerta("Selecciona una sucursal.");
            return;
        }
        const p = paramsConsulta();
        const tieneRango = p.desde && p.hasta;
        const tieneSemana = p.semana && p.año;
        if (!tieneRango && !tieneSemana) {
            mostrarAlerta("Indica Semana+Año o un rango Desde/Hasta.");
            return;
        }

        mostrarLoading(true);
        try {
            const res = await fetch("/api/dashboard-promos?" + qs(p));
            const data = await res.json();
            if (!res.ok) {
                mostrarAlerta(data.error || "Error al consultar");
                return;
            }
            datosCache = data;
            $("sim-precio-nuevo").dataset.touched = "";
            pintarKpis(data.kpis || {}, data.meta || {});
            pintarTablaCategorias(data.por_categoria);
            pintarTablaCombos(data.ranking_combos, data.sin_receta);
            pintarChartCategorias(data.por_categoria);
            pintarChartCombos(data.ranking_combos);
            pintarChartPrecioEfectivo(data.por_categoria);
            poblarSimuladorItems();
        } catch (e) {
            console.error(e);
            mostrarAlerta("No se pudo cargar el análisis.");
        } finally {
            mostrarLoading(false);
        }
    }

    async function init() {
        await cargarSucursales();
        await initFechas();
        $("btn-consultar").addEventListener("click", consultar);
        $("sim-tipo").addEventListener("change", () => {
            $("sim-precio-nuevo").dataset.touched = "";
            poblarSimuladorItems();
        });
        $("sim-item").addEventListener("change", () => {
            $("sim-precio-nuevo").dataset.touched = "";
            sincronizarSimulador();
        });
        $("sim-precio-nuevo").addEventListener("input", () => {
            $("sim-precio-nuevo").dataset.touched = "1";
            calcularSimulador();
        });
        $("sim-sens").addEventListener("input", calcularSimulador);
        if (sucursalActiva) consultar();
    }

    init();
})();
