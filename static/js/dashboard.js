let sucursalActiva = null;
let carruselInterval = null; // Variable global para limpiar el carrusel

let dataHistoricoGlobal = null;
let tendenciaAnualGlobal = null;
let tendenciaSemanalGlobal = null;
let vistaTendenciaActiva = 'anual';

// --- CACHÉ EN MEMORIA DEL NAVEGADOR ---
let cacheConsultas = {};
let cacheProductos = {};

// --- INICIO CALENDARIO ---
const feriadosChile = {
    "2026": {
        "1-1": "Año Nuevo",
        "4-3": "Viernes Santo",
        "4-4": "Sábado Santo",
        "5-1": "Día del Trabajador",
        "5-21": "Día de las Glorias Navales",
        "6-22": "Día Nacional de los Pueblos Indígenas",
        "6-29": "San Pedro y San Pablo",
        "7-16": "Virgen del Carmen",
        "8-15": "Asunción de la Virgen",
        "9-18": "Independencia Nacional",
        "9-19": "Día de las Glorias del Ejército",
        "10-12": "Encuentro de Dos Mundos",
        "10-31": "Día de las Iglesias Evangélicas",
        "11-1": "Día de Todos los Santos",
        "12-8": "Inmaculada Concepción",
        "12-25": "Navidad"
    }
};

function getWeekNumber(d) {
    d = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
    var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    var weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return weekNo;
}

function generarCalendario(año, mes) {
    const container = document.getElementById("calendar-container");
    const meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
    const hoy = new Date();
    
    const primerDia = new Date(año, mes, 1);
    
    let html = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <button class="btn btn-outline-light" id="prev-month">&lt;</button>
            <h4 class="mb-0">${meses[mes]} ${año}</h4>
            <button class="btn btn-outline-light" id="next-month">&gt;</button>
        </div>
        <table class="table table-bordered table-dark calendar-table">
            <thead>
                <tr>
                    <th class="week-number-header">Sem</th>
                    <th>Lun</th>
                    <th>Mar</th>
                    <th>Mié</th>
                    <th>Jue</th>
                    <th>Vie</th>
                    <th>Sáb</th>
                    <th>Dom</th>
                </tr>
            </thead>
            <tbody>
    `;

    let fecha = new Date(primerDia);
    let diaSemana = fecha.getDay();
    if (diaSemana === 0) diaSemana = 7; // Sunday is 7
    fecha.setDate(fecha.getDate() - (diaSemana - 1));

    let done = false;
    while (!done) {
        const weekNum = getWeekNumber(fecha);
        html += `<tr><td class="week-number">${weekNum}</td>`;
        for (let i = 0; i < 7; i++) {
            const diaActual = fecha.getDate();
            const mesActual = fecha.getMonth();
            const añoActual = fecha.getFullYear();
            
            let classes = "day-cell";
            let title = "";
            
            if (mesActual !== mes) {
                classes += " other-month";
            }

            const feriadoKey = `${mesActual + 1}-${diaActual}`;
            const feriado = feriadosChile[String(añoActual)] ? feriadosChile[String(añoActual)][feriadoKey] : null;

            if (feriado) {
                classes += " holiday";
                title = feriado;
            }

            if (diaActual === hoy.getDate() && mesActual === hoy.getMonth() && añoActual === hoy.getFullYear()) {
                classes += " today";
            }

            html += `<td class="${classes}" title="${title}">${diaActual}</td>`;
            fecha.setDate(fecha.getDate() + 1);
        }
        html += `</tr>`;
        if (fecha.getFullYear() > año || (fecha.getFullYear() === año && fecha.getMonth() > mes)) {
            done = true;
        }
    }

    html += `</tbody></table>`;
    container.innerHTML = html;

    document.getElementById("prev-month").onclick = () => {
        const nuevaFecha = new Date(año, mes - 1, 1);
        generarCalendario(nuevaFecha.getFullYear(), nuevaFecha.getMonth());
    };
    document.getElementById("next-month").onclick = () => {
        const nuevaFecha = new Date(año, mes + 1, 1);
        generarCalendario(nuevaFecha.getFullYear(), nuevaFecha.getMonth());
    };
}

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
    const empresa = document.getElementById("empresa").value;
    const semana = document.getElementById("semana").value;
    const año = document.getElementById("año").value;
    const desde = document.getElementById("desde").value;
    const hasta = document.getElementById("hasta").value;

    // PREVENCIÓN: Si no hay ningún filtro seleccionado, forzamos recargar la última fecha disponible
    if (!semana && !año && !desde && !hasta) {
        toggleChartsOverlay(true);
        fetch(`/api/latest-date-info?empresa=${empresa}`)
            .then(res => res.json())
            .then(data => {
                document.getElementById("año").value = data.año;
                document.getElementById("semana").value = data.semana;
                actualizarDashboard(); 
            });
        return;
    }

    // Omitimos enviar parámetros vacíos en la URL para evitar que el backend anule la semana
    const queryObj = { empresa };
    if (semana) queryObj.semana = semana;
    if (año) queryObj.año = año;
    if (desde) queryObj.desde = desde;
    if (hasta) queryObj.hasta = hasta;
    if (sucursalActiva) queryObj.sucursal = sucursalActiva;

    const params = new URLSearchParams(queryObj);
    const queryKey = params.toString();

    // 1. REVISAR SI LA CONSULTA YA ESTÁ EN MEMORIA (¡CARGA INSTANTÁNEA!)
    if (cacheConsultas[queryKey]) {
        renderizarDatosDashboard(cacheConsultas[queryKey], empresa);
        return; // Salimos sin hacer la petición al servidor
    }

    // 2. SI NO ESTÁ EN MEMORIA, BUSCAMOS EN EL SERVIDOR
    toggleChartsOverlay(true); 

    fetch(`/api/dashboard-data?${queryKey}`)
        .then(res => res.json())
        .then(data => {
            cacheConsultas[queryKey] = data; // GUARDAMOS EN MEMORIA PARA LA PRÓXIMA VEZ
            renderizarDatosDashboard(data, empresa);
        })
        .catch(error => {
            console.error("Error al cargar datos del dashboard:", error);
        })
        .finally(() => {
            toggleChartsOverlay(false); // Ocultar overlay al finalizar
        });
}

// Separamos el renderizado para poder llamarlo desde la caché o desde el fetch
function renderizarDatosDashboard(data, empresa) {
    renderTorta(data.ventas_por_familia);
    
    // Render KPIs Enriquecidos
    if (data.kpis) {
        renderKPI("kpi_neto", "kpi_neto_var", data.kpis.neto_actual, data.kpis.neto_anterior, true);
        
        // Cantidad ahora es Empanadas
        renderKPI("kpi_cantidad", "kpi_cantidad_var", data.kpis.empanadas_actual || 0, data.kpis.empanadas_anterior || 0, false);
        
        // Tercera Tarjeta Dinámica
        if (empresa === "agricola") {
            if (carruselInterval) clearInterval(carruselInterval);
            document.getElementById("kpi_carrusel_nombre").innerText = "Ticket Promedio";
            document.getElementById("kpi_carrusel_nombre").style.color = "#ffc107"; // Amarillo
            renderKPI("kpi_carrusel_cantidad", "kpi_carrusel_var", data.kpis.ticket_promedio_actual || 0, data.kpis.ticket_promedio_anterior || 0, true);
        } else {
            document.getElementById("kpi_carrusel_nombre").style.color = "#0dcaf0";
            iniciarCarruselProductos(data.kpis.top_productos_cantidad);
        }
    }

    dataHistoricoGlobal = data.historico_semanal;
    tendenciaAnualGlobal = data.tendencia;
    tendenciaSemanalGlobal = data.tendencia_semanal;

    // Render Análisis Avanzado
    if (data.analisis_avanzado) {
        renderRankingSucursales(data.analisis_avanzado.ranking_sucursales);
        renderListaTop("lista_estrellas", data.analisis_avanzado.estrellas, false);
        renderListaTop("lista_alertas", data.analisis_avanzado.alertas, true);
    }

    // --- NUEVOS GRÁFICOS ---
    cambiarVistaTendencia(vistaTendenciaActiva); // Renderiza anual o semanal según el botón activo

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
}

// --- FUNCIONES NUEVAS PARA MODAL Y TENDENCIA ---
function abrirModalHistorico() {
    if (!dataHistoricoGlobal || !dataHistoricoGlobal.años) {
        alert("No hay datos históricos disponibles para esta vista.");
        return;
    }
    
    const thead = document.getElementById("head-historico-neto");
    const tbody = document.getElementById("body-historico-neto");
    const semanaConsultada = parseInt(document.getElementById("semana").value) || 0;
    
    let htmlHead = `<th>Semana</th>`;
    dataHistoricoGlobal.años.forEach(año => htmlHead += `<th>${año}</th>`);
    thead.innerHTML = htmlHead;
    
    let htmlBody = "";
    dataHistoricoGlobal.datos.forEach(fila => {
        const isActiva = (fila.semana === semanaConsultada) ? "fila-semana-activa" : "";
        htmlBody += `<tr class="${isActiva}" id="fila-hist-${fila.semana}">
            <td class="fw-bold ${isActiva ? 'text-info' : ''}">Sem ${fila.semana}</td>`;
        
        dataHistoricoGlobal.años.forEach(año => {
            const val = fila[año] || 0;
            htmlBody += `<td>$${val.toLocaleString('es-CL')}</td>`;
        });
        htmlBody += `</tr>`;
    });
    tbody.innerHTML = htmlBody;
    
    const modal = new bootstrap.Modal(document.getElementById('modalHistoricoNeto'));
    modal.show();
    
    // Scrollear a la semana activa después de abrir
    setTimeout(() => {
        const trActiva = document.getElementById(`fila-hist-${semanaConsultada}`);
        if (trActiva) {
            trActiva.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }, 300);
}

function cambiarVistaTendencia(tipo) {
    vistaTendenciaActiva = tipo;
    const dataRender = tipo === 'anual' ? tendenciaAnualGlobal : tendenciaSemanalGlobal;
    if (dataRender) renderTendenciaVentas(dataRender);
}
// --- FIN NUEVAS FUNCIONES ---

// Función para actualizar los gráficos de barras al hacer clic en la torta
function actualizarGraficosBarras(familiaSeleccionada) {
    const empresa = document.getElementById("empresa").value;
    const semana = document.getElementById("semana").value;
    const año = document.getElementById("año").value;
    const desde = document.getElementById("desde").value;
    const hasta = document.getElementById("hasta").value;
    const sucursal = sucursalActiva || "";

    const queryObj = { empresa, familia: familiaSeleccionada };
    if (semana) queryObj.semana = semana;
    if (año) queryObj.año = año;
    if (desde) queryObj.desde = desde;
    if (hasta) queryObj.hasta = hasta;
    if (sucursal) queryObj.sucursal = sucursal;

    const params = new URLSearchParams(queryObj);
    const queryKey = params.toString();

    // Verificamos si los productos de esta familia ya están en memoria
    if (cacheProductos[queryKey]) {
        renderBarrasNeto(familiaSeleccionada, cacheProductos[queryKey]);
        renderBarrasCantidad(familiaSeleccionada, cacheProductos[queryKey]);
        return;
    }

    fetch(`/api/dashboard-productos?${queryKey}`)
        .then(res => res.json())
        .then(productos => {
            cacheProductos[queryKey] = productos; // Guardamos en memoria
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

    // Listener para el calendario
    const calendarIcon = document.getElementById("calendar-icon");
    const calendarModalEl = document.getElementById('calendarModal');
    if (calendarIcon && calendarModalEl) {
        const calendarModal = new bootstrap.Modal(calendarModalEl);
        calendarIcon.addEventListener("click", () => {
            const ahora = new Date();
            generarCalendario(ahora.getFullYear(), ahora.getMonth());
            calendarModal.show();
        });
    }


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
    if (!datos) return;
    
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
        margin: { t: 20 }, // Reducimos margen superior porque el título ahora está en HTML
        height: 350,
        paper_bgcolor: "#111",
        plot_bgcolor: "#111",
        font: { color: "#fff" },
        hovermode: "x unified",
        xaxis: { showgrid: false },
        yaxis: { gridcolor: "#333", tickformat: "$,.0f" },
        legend: { orientation: "h", y: -0.2 }
    };

    // Usamos Plotly.react en lugar de newPlot para que la actualización sea ultra rápida sin recargar el DOM
    Plotly.react("grafico_tendencia", [traceActual, traceAnterior], layout);
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
