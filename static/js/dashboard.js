let sucursalActiva = null;
let carruselInterval = null; // Variable global para limpiar el carrusel

// --- INICIO DE CAMBIOS ---

// Función para mostrar/ocultar el overlay de carga de los gráficos
function toggleChartsOverlay(show) {
    const overlay = document.getElementById("charts-loading-overlay");
    if (overlay) {
        overlay.style.display = show ? "flex" : "none";
    }
}

// Función para limpiar filtros de fecha/semana
function limpiarFiltrosFecha() {
    document.getElementById("desde").value = "";
    document.getElementById("hasta").value = "";
}

function limpiarFiltrosSemana() {
    document.getElementById("semana").value = "";
    document.getElementById("año").value = "";
}

// Función para cargar los datos del dashboard
function actualizarDashboard() {
    toggleChartsOverlay(true); // Mostrar overlay al iniciar la carga

    const empresa = document.getElementById("empresa").value;
    const semana = document.getElementById("semana").value;
    const año = document.getElementById("año").value;
    const desde = document.getElementById("desde").value;
    const hasta = document.getElementById("hasta").value;

    const params = new URLSearchParams({
        empresa,
        semana,
        año,
        desde,
        hasta,
        sucursal: sucursalActiva || "",
    });

    fetch(`/api/dashboard-data?${params.toString()}`)
        .then(res => res.json())
        .then(data => {
            renderTorta(data.ventas_por_familia);
            
            // Render KPIs Enriquecidos
            if (data.kpis) {
                renderKPI("kpi_neto", "kpi_neto_var", data.kpis.neto_actual, data.kpis.neto_anterior, true);
                renderKPI("kpi_cantidad", "kpi_cantidad_var", data.kpis.cantidad_actual, data.kpis.cantidad_anterior, false);
                
                iniciarCarruselProductos(data.kpis.top_productos_cantidad);
            }

            // Render Análisis Avanzado
            if (data.analisis_avanzado) {
                renderRankingSucursales(data.analisis_avanzado.ranking_sucursales);
                renderListaTop("lista_estrellas", data.analisis_avanzado.estrellas, false);
                renderListaTop("lista_alertas", data.analisis_avanzado.alertas, true);
            }

            // --- NUEVOS GRÁFICOS ---
            // Condicionados a que el backend envíe esta información
            if (data.tendencia) {
                renderTendenciaVentas(data.tendencia);
            }
            if (data.comparativo_periodo) {
                renderComparativoPeriodo(data.comparativo_periodo);
            }

            // Si hay datos, renderizar los gráficos de barras con la primera familia
            if (data.ventas_por_familia && data.ventas_por_familia.length > 0) {
                const primeraFamilia = data.ventas_por_familia[0].nombre;
                actualizarGraficosBarras(primeraFamilia);
            } else {
                // Si no hay datos, limpiar los gráficos de barras
                Plotly.newPlot("grafico_barras_neto", [], {title: "Sin datos de Neto"});
                Plotly.newPlot("grafico_barras_cantidad", [], {title: "Sin datos de Cantidad"});
            }
        })
        .catch(error => {
            console.error("Error al cargar datos del dashboard:", error);
        })
        .finally(() => {
            toggleChartsOverlay(false); // Ocultar overlay al finalizar
        });
}

// Función para actualizar los gráficos de barras al hacer clic en la torta
function actualizarGraficosBarras(familiaSeleccionada) {
    const empresa = document.getElementById("empresa").value;
    const semana = document.getElementById("semana").value;
    const año = document.getElementById("año").value;
    const desde = document.getElementById("desde").value;
    const hasta = document.getElementById("hasta").value;
    const sucursal = sucursalActiva || "";

    const params = new URLSearchParams({
        empresa,
        semana,
        año,
        desde,
        hasta,
        sucursal,
        familia: familiaSeleccionada
    });

    fetch(`/api/dashboard-productos?${params.toString()}`)
        .then(res => res.json())
        .then(productos => {
            renderBarrasNeto(familiaSeleccionada, productos);
            renderBarrasCantidad(familiaSeleccionada, productos);
        });
}

// Carga inicial al cargar la página
document.addEventListener("DOMContentLoaded", () => {
    // 1. Cargar sucursales
    cargarSucursales();

    // 2. Obtener la última semana y año del backend
    const empresa = document.getElementById("empresa").value;
    fetch(`/api/latest-date-info?empresa=${empresa}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById("año").value = data.año;
            document.getElementById("semana").value = data.semana;
            // 3. Cargar el dashboard con estos datos iniciales
            actualizarDashboard();
        });

    // 4. Configurar listeners para filtros
    // Filtros de fecha limpian semana/año
    document.getElementById("desde").addEventListener("input", limpiarFiltrosSemana);
    document.getElementById("hasta").addEventListener("input", limpiarFiltrosSemana);

    // Filtros de semana/año limpian fecha
    document.getElementById("semana").addEventListener("input", limpiarFiltrosFecha);
    document.getElementById("año").addEventListener("input", limpiarFiltrosFecha);

    // Listener para el botón de empresa
    document.getElementById("empresa").addEventListener("change", () => {
        cargarSucursales();
        actualizarDashboard();
    });
    
    // Listener para los filtros principales que actualizan todo
     ["semana", "año", "desde", "hasta"].forEach(id => {
        document.getElementById(id).addEventListener("change", actualizarDashboard);
    });
});

// --- FIN DE CAMBIOS ---


// El resto de las funciones (cargarSucursales, renderTorta, etc.)
// pueden tener pequeñas modificaciones para adaptarse a la nueva lógica.
// Aquí está la versión completa y funcional de todo el archivo.

function cargarSucursales() {
    const empresa = document.getElementById("empresa").value;
    fetch(`/api/sucursales?empresa=${empresa}`)
        .then(res => res.json())
        .then(data => {
            const cont = document.getElementById("sucursales");
            cont.innerHTML = "";

            const btnTodas = document.createElement("button");
            btnTodas.className = "btn btn-outline-light m-1";
            btnTodas.innerText = "TODAS";
            btnTodas.onclick = () => {
                sucursalActiva = null;
                resaltarBoton(cont, btnTodas);
                actualizarDashboard();
            };
            cont.appendChild(btnTodas);

            data.forEach((suc) => {
                const btn = document.createElement("button");
                btn.className = "btn btn-outline-light m-1";
                btn.innerText = suc;
                btn.onclick = () => {
                    sucursalActiva = suc;
                    resaltarBoton(cont, btn);
                    actualizarDashboard();
                };
                cont.appendChild(btn);
            });

            btnTodas.click();
        });
}

function resaltarBoton(container, activo) {
    [...container.children].forEach(btn => btn.classList.remove("btn-activo", "btn-danger"));
    if (activo) {
        activo.classList.add("btn-activo", "btn-danger");
    }
}

function renderTorta(data) {
    const labels = data.map(d => d.nombre);
    const values = data.map(d => d.valor);

    const layout = {
        title: "Distribución por Familia",
        height: 400,
        paper_bgcolor: "#111",
        plot_bgcolor: "#111",
        font: { color: "#fff" }
    };

    const trace = {
        labels: labels,
        values: values,
        type: "pie",
        textinfo: "label+percent",
        insidetextorientation: "radial"
    };

    Plotly.newPlot("grafico_torta", [trace], layout);

    document.getElementById('grafico_torta').on('plotly_click', function(dataClick) {
        if (dataClick.points && dataClick.points.length > 0) {
            const familiaSeleccionada = dataClick.points[0].label;
            actualizarGraficosBarras(familiaSeleccionada);
        }
    });
}

function renderBarrasNeto(familia, productos) {
    const nombres = productos.map(p => p.descripcion);
    const valores = productos.map(p => p.neto);

    const trace = {
        x: nombres,
        y: valores,
        type: "bar",
        marker: { color: "#e60000" },
        hovertemplate: "<b>%{x}</b><br>$%{y:,.0f}<extra></extra>"
    };

    const layout = {
        title: `Detalle Neto: ${familia}`,
        height: 300,
        paper_bgcolor: "#111",
        plot_bgcolor: "#111",
        xaxis: { showticklabels: false },
        font: { color: "#fff" },
        hovermode: 'closest'
    };

    Plotly.newPlot("grafico_barras_neto", [trace], layout);
}

function renderBarrasCantidad(familia, productos) {
    const nombres = productos.map(p => p.descripcion);
    const cantidades = productos.map(p => p.cantidad);

    const trace = {
        x: nombres,
        y: cantidades,
        type: "bar",
        marker: { color: "#17a2b8" },
        hovertemplate: "<b>%{x}</b><br>%{y:,.0f} unidades<extra></extra>"
    };

    const layout = {
        title: `Detalle Cantidad: ${familia}`,
        height: 300,
        paper_bgcolor: "#111",
        plot_bgcolor: "#111",
        xaxis: { showticklabels: false },
        font: { color: "#fff" },
        hovermode: 'closest'
    };

    Plotly.newPlot("grafico_barras_cantidad", [trace], layout);
}

function animarContador(idElemento, valorFinal, isCurrency = true) {
    const el = document.getElementById(idElemento);
    const valorInicial = parseInt(el.innerText.replace(/\D/g, "")) || 0;
    const duracion = 1000;
    const pasos = 30;
    const incremento = (valorFinal - valorInicial) / pasos;
    let contador = 0;
    
    const formatNumber = (num) => isCurrency ? `$${Math.round(num).toLocaleString("es-CL")}` : Math.round(num).toLocaleString("es-CL");

    const intervalo = setInterval(() => {
        contador++;
        const valorActual = valorInicial + incremento * contador;
        el.innerText = formatNumber(valorActual);
        if (contador >= pasos) {
            clearInterval(intervalo);
            el.innerText = formatNumber(valorFinal);
        }
    }, duracion / pasos);
}

// --- FUNCIONES PARA KPIs Y ANÁLISIS ---

function renderKPI(idValor, idVar, actual, anterior, isCurrency) {
    animarContador(idValor, actual, isCurrency);
    const elVar = document.getElementById(idVar);
    if (anterior > 0) {
        const pct = ((actual - anterior) / anterior) * 100;
        const sign = pct >= 0 ? "▲" : "▼";
        const color = pct >= 0 ? "#198754" : "#dc3545"; // Bootstrap success/danger
        elVar.innerHTML = `<span style="color: ${color}">${sign} ${Math.abs(pct).toFixed(1)}% vs anterior</span>`;
    } else {
        elVar.innerHTML = `<span style="color: #6c757d">Sin data previa</span>`;
    }
}

function iniciarCarruselProductos(productos) {
    if (carruselInterval) clearInterval(carruselInterval);
    
    const elNombre = document.getElementById("kpi_carrusel_nombre");
    const elCant = document.getElementById("kpi_carrusel_cantidad");
    const elVar = document.getElementById("kpi_carrusel_var");
    
    if (!productos || productos.length === 0) {
        elNombre.innerText = "Sin ventas";
        elCant.innerText = "0";
        elVar.innerHTML = "-";
        return;
    }

    let index = 0;
    
    function actualizarCard() {
        const prod = productos[index];
        elNombre.innerText = prod.DESCRIPCION;
        animarContador("kpi_carrusel_cantidad", prod.cantidad_actual, false);
        
        if (prod.cantidad_anterior > 0) {
            const pct = ((prod.cantidad_actual - prod.cantidad_anterior) / prod.cantidad_anterior) * 100;
            const sign = pct >= 0 ? "▲" : "▼";
            const color = pct >= 0 ? "#198754" : "#dc3545"; 
            elVar.innerHTML = `<span style="color: ${color}">${sign} ${Math.abs(pct).toFixed(1)}% vs ant.</span>`;
        } else {
            elVar.innerHTML = `<span style="color: #6c757d">Sin data previa</span>`;
        }
        index = (index + 1) % productos.length;
    }

    actualizarCard(); // Primera llamada inmediata
    if (productos.length > 1) {
        carruselInterval = setInterval(actualizarCard, 3500); // Rota cada 3.5 segundos
    }
}

function renderRankingSucursales(datos) {
    if (!datos || datos.length === 0) {
        document.getElementById("contenedor_ranking").style.display = "none";
        document.getElementById("contenedor_estrellas").className = "col-lg-6 mb-3";
        document.getElementById("contenedor_alertas").className = "col-lg-6 mb-3";
        return;
    }

    document.getElementById("contenedor_ranking").style.display = "block";
    document.getElementById("contenedor_estrellas").className = "col-lg-4 mb-3";
    document.getElementById("contenedor_alertas").className = "col-lg-4 mb-3";

    const trace = {
        x: datos.map(d => d.neto),
        y: datos.map(d => d.sucursal),
        type: "bar",
        orientation: "h",
        marker: { color: "#0dcaf0" },
        text: datos.map(d => "$" + d.neto.toLocaleString("es-CL")),
        textposition: "auto",
        hovertemplate: "<b>%{y}</b><br>$%{x:,.0f}<extra></extra>"
    };

    const layout = {
        margin: { l: 80, r: 10, t: 10, b: 30 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: "#fff" },
        xaxis: { showgrid: false, showticklabels: false },
        yaxis: { showgrid: false }
    };

    Plotly.newPlot("grafico_ranking", [trace], layout, {displayModeBar: false});
}

function renderListaTop(idContenedor, datos, isAlerta) {
    const cont = document.getElementById(idContenedor);
    if (!datos || datos.length === 0) {
        cont.innerHTML = "<p class='text-muted mt-2'>Sin datos / Sin caídas detectadas.</p>";
        return;
    }

    let html = "<ul class='list-group list-group-flush bg-transparent'>";
    datos.forEach(d => {
        const varAbs = Math.abs(d.variacion);
        // Si la variación es 0 (porque no hay data previa), solo mostramos el texto.
        const textVar = varAbs > 0 ? "$" + varAbs.toLocaleString("es-CL") : "-";
        const colorClass = isAlerta ? "text-danger" : "text-success";
        const sign = isAlerta && varAbs > 0 ? "-" : (varAbs > 0 ? "+" : "");

        html += `
            <li class="list-group-item bg-transparent border-secondary text-white d-flex justify-content-between align-items-center px-0 py-1" style="border-bottom: 1px solid #333 !important;">
                <span class="text-truncate text-white" style="max-width: 65%; font-size:0.85rem;" title="${d.DESCRIPCION}">${d.DESCRIPCION}</span>
                <span class="${colorClass} fw-bold" style="font-size:0.85rem;">${sign}${textVar}</span>
            </li>
        `;
    });
    html += "</ul>";
    cont.innerHTML = html;
}

// --- NUEVAS FUNCIONES DE RENDERIZADO ---

function renderTendenciaVentas(datos) {
    // datos debe ser un objeto: { etiquetas: ['Ene', 'Feb', ...], actual: [100, 200...], anterior: [90, 180...] }
    const traceActual = {
        x: datos.etiquetas,
        y: datos.actual,
        type: "scatter",
        mode: "lines+markers",
        name: "Año Actual",
        line: { color: "#e60000", width: 3 }, // Rojo corporativo
        hovertemplate: "<b>%{x}</b><br>Actual: $%{y:,.0f}<extra></extra>"
    };

    const traceAnterior = {
        x: datos.etiquetas,
        y: datos.anterior,
        type: "scatter",
        mode: "lines",
        name: "Año Anterior",
        line: { color: "#6c757d", width: 2, dash: "dot" }, // Gris punteado
        hovertemplate: "<b>%{x}</b><br>Anterior: $%{y:,.0f}<extra></extra>"
    };

    const layout = {
        title: "Tendencia de Ventas (Actual vs Anterior)",
        height: 350,
        paper_bgcolor: "#111",
        plot_bgcolor: "#111",
        font: { color: "#fff" },
        hovermode: "x unified",
        xaxis: { showgrid: false },
        yaxis: { gridcolor: "#333", tickformat: "$,.0f" },
        legend: { orientation: "h", y: -0.2 }
    };

    Plotly.newPlot("grafico_tendencia", [traceActual, traceAnterior], layout);
}

function renderComparativoPeriodo(datos) {
    // datos debe ser un objeto: { etiquetas: ['Año Anterior', 'Año Actual'], valores: [45000, 50000] }
    const trace = {
        x: datos.etiquetas,
        y: datos.valores,
        type: "bar",
        marker: { color: ["#6c757d", "#e60000"] }, // Gris vs Rojo
        text: datos.valores.map(v => "$" + v.toLocaleString("es-CL")),
        textposition: "auto",
        hovertemplate: "<b>%{x}</b><br>$%{y:,.0f}<extra></extra>"
    };

    const layout = {
        title: "Comparativo del Periodo",
        height: 350,
        paper_bgcolor: "#111",
        plot_bgcolor: "#111",
        font: { color: "#fff" },
        yaxis: { showticklabels: false, gridcolor: "#333" }
    };

    Plotly.newPlot("grafico_comparativo", [trace], layout);
}
