let sucursalActiva = null;
let familiaActiva = null;
let semanaDefault = null;
let añoDefault = new Date().getFullYear();
let productosPorFamilia = {};  // clave: familia, valor: productos[]


function cargarSucursales() {
    const empresa = document.getElementById("empresa").value;
    fetch(`/api/sucursales?empresa=${empresa}`)
        .then(res => res.json())
        .then(data => {
            const cont = document.getElementById("sucursales");
            cont.innerHTML = "";

            // Botón "Todas"
            const btnTodas = document.createElement("button");
            btnTodas.className = "btn btn-outline-light m-1";
            btnTodas.innerText = "TODAS";
            btnTodas.onclick = () => {
                sucursalActiva = null;  // ← importante
                resaltarBoton(cont, btnTodas);
                actualizarDashboard();
            };
            cont.appendChild(btnTodas);

            // Botones por sucursal
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

            // Activar por defecto "Todas"
            btnTodas.click();
        });
}


function resaltarBoton(container, activo) {
    [...container.children].forEach(btn => btn.classList.remove("btn-activo", "btn-danger"));
    if (activo) {
        activo.classList.add("btn-activo", "btn-danger");
    }
}


function actualizarDashboard() {
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
            productosPorFamilia = data.detalle_por_familia || {};
            renderTorta(data.ventas_por_familia);
            
            animarContador("monto_neto", data.total_neto);

            // Seleccionamos la primera familia automáticamente para iniciar
            if (data.ventas_por_familia.length > 0) {
                const primera = data.ventas_por_familia[0].nombre;
                const productos = productosPorFamilia[primera] || [];
                renderBarrasNeto(primera, productos);
                renderBarrasCantidad(primera, productos);
            }
        });


}


function renderTorta(data) {
    const labels = data.map(d => d.nombre);
    const values = data.map(d => d.valor);

    const layout = {
        title: "Distribución por Familia", // o Detalle...
        height: 400,
        paper_bgcolor: "#111",     // Fondo general
        plot_bgcolor: "#111",      // Fondo de zona de gráfico
        font: {
            color: "#fff"          // Color del texto
        }
    };


    const trace = {
        labels: labels,
        values: values,
        type: "pie",
        textinfo: "label+percent",
        insidetextorientation: "radial"
    };

    Plotly.newPlot("grafico_torta", [trace], layout);

    // Capturar clic en un segmento de la torta
    const tortaDiv = document.getElementById("grafico_torta");
    tortaDiv.on('plotly_click', function(dataClick) {
        const punto = dataClick.points[0];
        const familiaSeleccionada = punto.label;
        familiaActiva = familiaSeleccionada;

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
        hovertemplate: "<b>%{x}</b><br>$%{y:,.0f}<extra></extra>"  // Tooltip fijo y claro
    };

    const layout = {
        title: `Detalle Neto: ${familia}`,
        height: 300,
        paper_bgcolor: "#111",
        plot_bgcolor: "#111",
        xaxis: {
            showticklabels: false // Oculta etiquetas del eje X
        },
        font: { color: "#fff" }
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
                xaxis: {
            showticklabels: false // Oculta etiquetas del eje X
        },
        font: { color: "#fff" }
    };

    Plotly.newPlot("grafico_barras_cantidad", [trace], layout);
}




function renderBarras(data) {
    const layout = {
        title: "Venta por Producto", // o Detalle...
        height: 400,
        paper_bgcolor: "#111",     // Fondo general
        plot_bgcolor: "#111",      // Fondo de zona de gráfico
        font: {
            color: "#fff"          // Color del texto
        }
    };

    const trace = {
        x: [],
        y: [],
        type: "bar"
    };

    Plotly.newPlot("grafico_barras", [trace], layout);
}

function detectarUltimaSemana() {
    const empresa = document.getElementById("empresa").value;
    fetch(`/api/dashboard-data?empresa=${empresa}`)
        .then(res => res.json())
        .then(data => {
            const today = new Date();
            const año = today.getFullYear();
            const semana = getCurrentWeek(today);
            document.getElementById("año").value = año;
            document.getElementById("semana").value = semana;
            actualizarDashboard();
        });
}

// Utilidad para obtener número de semana ISO
function getCurrentWeek(date) {
    const onejan = new Date(date.getFullYear(), 0, 1);
    const millis = date - onejan + ((onejan.getDay() + 6) % 7) * 86400000;
    return Math.floor(millis / 604800000) + 1;
}

document.addEventListener("DOMContentLoaded", () => {
    cargarSucursales();
    detectarUltimaSemana();

    // Auto-actualizar al cambiar fechas manualmente
    ["semana", "año", "desde", "hasta"].forEach(id => {
        document.getElementById(id).addEventListener("change", actualizarDashboard);
    });

    document.getElementById("empresa").addEventListener("change", () => {
        cargarSucursales();
        detectarUltimaSemana();
    });
});

function animarContador(idElemento, valorFinal) {
    const el = document.getElementById(idElemento);
    const valorInicial = parseInt(el.innerText.replace(/\D/g, "")) || 0;
    const duracion = 1000; // ms
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

