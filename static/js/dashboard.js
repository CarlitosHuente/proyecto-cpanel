let sucursalActiva = null;

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
            animarContador("monto_neto", data.total_neto);

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

function animarContador(idElemento, valorFinal) {
    const el = document.getElementById(idElemento);
    const valorInicial = parseInt(el.innerText.replace(/\D/g, "")) || 0;
    const duracion = 1000;
    const pasos = 30;
    const incremento = (valorFinal - valorInicial) / pasos;
    let contador = 0;

    const intervalo = setInterval(() => {
        contador++;
        const valorActual = valorInicial + incremento * contador;
        el.innerText = `$${Math.round(valorActual).toLocaleString("es-CL")}`;
        if (contador >= pasos) {
            clearInterval(intervalo);
            el.innerText = `$${valorFinal.toLocaleString("es-CL")}`;
        }
    }, duracion / pasos);
}

