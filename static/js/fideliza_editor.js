(function () {
  const ANCHOS = [30, 45, 60, 80, 100];

  function texto(valor) {
    return String(valor || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function estado(root, mensaje, error) {
    const caja = root.querySelector("[data-estado]");
    if (!caja) return;
    caja.textContent = mensaje || "";
    caja.classList.toggle("text-danger", !!error);
    caja.classList.toggle("text-success", !!mensaje && !error);
  }

  function areaActiva(root) {
    return root.querySelector("[data-area]");
  }

  function abrir(root) {
    root.classList.add("fid-abierto");
    const accion = root.querySelector(".fid-accion");
    if (accion) accion.textContent = "Contraer";
  }

  function resumenDe(root) {
    const area = areaActiva(root);
    const plano = (area.innerText || "").replace(/\s+/g, " ").trim();
    const fotos = area.querySelectorAll("img").length;
    if (!plano && !fotos) return "Sin texto. Pulsa Editar para escribir.";
    const extra = fotos ? (fotos === 1 ? " · 1 imagen" : " · " + fotos + " imágenes") : "";
    return (plano || "Imagen") .slice(0, 110) + extra;
  }

  function actualizarResumen(root) {
    const caja = root.querySelector("[data-resumen]");
    if (caja) caja.textContent = resumenDe(root);
  }

  function htmlActual(root) {
    if (root.classList.contains("fid-fuente-on")) {
      return root.querySelector("[data-source]").value;
    }
    const clon = areaActiva(root).cloneNode(true);
    clon.querySelectorAll(".fid-asa").forEach(function (nodo) { nodo.remove(); });
    clon.querySelectorAll(".fid-sel").forEach(function (nodo) { nodo.classList.remove("fid-sel"); });
    clon.querySelectorAll("[contenteditable]").forEach(function (nodo) { nodo.removeAttribute("contenteditable"); });
    clon.querySelectorAll("[draggable]").forEach(function (nodo) { nodo.removeAttribute("draggable"); });
    return clon.innerHTML;
  }

  function vestirImagenes(area) {
    area.querySelectorAll("img").forEach(function (img) {
      let figura = img.parentElement && img.parentElement.tagName === "FIGURE" ? img.parentElement : null;
      if (!figura) {
        figura = document.createElement("figure");
        img.replaceWith(figura);
        figura.appendChild(img);
        figura.style.width = "70%";
        figura.style.margin = "12px auto";
        figura.style.display = "block";
      }
      figura.classList.add("fid-img");
      figura.setAttribute("contenteditable", "false");
      figura.draggable = true;
      img.style.width = "100%";
      img.style.height = "auto";
      img.style.display = "block";
      if (!figura.querySelector(".fid-asa")) {
        const asa = document.createElement("span");
        asa.className = "fid-asa";
        asa.setAttribute("contenteditable", "false");
        figura.appendChild(asa);
      }
    });
  }

  function figuraHtml(src) {
    return (
      '<figure class="fid-img" contenteditable="false" draggable="true" style="width:70%;margin:12px auto;display:block;">' +
      '<img src="' + texto(src) + '" alt="" style="width:100%;height:auto;display:block;">' +
      '<span class="fid-asa" contenteditable="false"></span></figure><p></p>'
    );
  }

  function insertar(root, html) {
    abrir(root);
    const area = areaActiva(root);
    area.focus();
    const plantilla = document.createElement("template");
    plantilla.innerHTML = html;
    const nueva = plantilla.content.querySelector("figure.fid-img");
    const seleccion = window.getSelection();
    let puesto = false;
    if (seleccion && seleccion.rangeCount && area.contains(seleccion.anchorNode)) {
      const rango = seleccion.getRangeAt(0);
      rango.deleteContents();
      rango.insertNode(plantilla.content);
      puesto = true;
    }
    if (!puesto) area.appendChild(plantilla.content);
    vestirImagenes(area);
    if (nueva && area.contains(nueva)) {
      seleccionarImagen(root, nueva);
      nueva.scrollIntoView({ block: "nearest" });
    }
    actualizarResumen(root);
  }

  function bloque(tag) {
    if (!document.execCommand("formatBlock", false, tag)) {
      document.execCommand("formatBlock", false, "<" + tag + ">");
    }
  }

  function enlace(root) {
    const url = window.prompt("Dirección del enlace (https://, mailto: o tel:)");
    if (!url) return;
    const limpio = url.trim();
    if (!/^(https?:\/\/|mailto:|tel:|\/(?!\/))/i.test(limpio)) {
      estado(root, "Usa https://, mailto:, tel: o una ruta del sitio.", true);
      return;
    }
    const seleccion = window.getSelection();
    let visible = seleccion && !seleccion.isCollapsed ? seleccion.toString() : "";
    if (!visible) visible = window.prompt("Texto visible del enlace", limpio) || "";
    if (!visible.trim()) return;
    insertar(root, '<a href="' + texto(limpio) + '" target="_blank">' + texto(visible.trim()) + "</a>");
  }

  function imagenUrl(root) {
    const url = window.prompt("Dirección https de la imagen");
    if (!url) return;
    const limpio = url.trim();
    if (!/^https?:\/\//i.test(limpio)) {
      estado(root, "La imagen por enlace tiene que empezar con http:// o https://.", true);
      return;
    }
    insertar(root, figuraHtml(limpio));
    estado(root, "Imagen lista. Arrástrala, cambia el tamaño en la esquina o usa la barra verde.");
  }

  async function imagenArchivo(root, file) {
    if (!file) return;
    abrir(root);
    estado(root, "Subiendo imagen…");
    const datos = new FormData();
    datos.append("imagen", file);
    try {
      const respuesta = await fetch(root.dataset.upload, { method: "POST", body: datos });
      const cuerpo = await respuesta.json();
      if (!respuesta.ok || !cuerpo.ok) {
        estado(root, cuerpo.error || "No se pudo subir la imagen.", true);
        return;
      }
      insertar(root, figuraHtml(cuerpo.url));
      estado(root, "Imagen lista. Arrástrala, cambia el tamaño en la esquina o usa la barra verde.");
    } catch (error) {
      estado(root, "No se pudo subir la imagen.", true);
    }
  }

  function comando(root, boton) {
    const area = areaActiva(root);
    abrir(root);
    area.focus();
    const cmd = boton.dataset.cmd;
    if (cmd === "enlace") return enlace(root);
    if (cmd === "quitar-enlace") return document.execCommand("unlink");
    if (cmd === "imagen-url") return imagenUrl(root);
    if (cmd === "imagen-archivo") return root.querySelector("[data-file]").click();
    if (cmd === "fuente") return alternarFuente(root);
    if (cmd === "salto") {
      return insertar(
        root,
        '<div data-salto="1" style="page-break-before:always;border-top:2px dashed #94a3b8;margin:18px 0;padding-top:6px;color:#64748b;font-size:12px;text-align:center;clear:both;">— Salto de página —</div><p></p>'
      );
    }
    if (cmd === "linea") return document.execCommand("insertHorizontalRule");
    if (cmd === "boton") {
      const url = window.prompt("Dirección del botón", "https://");
      if (!url || !/^https?:\/\//i.test(url.trim())) return;
      const rotulo = window.prompt("Texto del botón", "Ver más");
      if (!rotulo) return;
      return insertar(
        root,
        '<table role="presentation" cellpadding="0" cellspacing="0"><tr><td bgcolor="#1b4332" style="background-color:#1b4332;border-radius:6px;">' +
          '<a href="' + texto(url.trim()) + '" target="_blank" style="display:inline-block;padding:12px 20px;color:#ffffff;text-decoration:none;font-family:Arial,sans-serif;">' +
          texto(rotulo.trim()) + "</a></td></tr></table><p></p>"
      );
    }
    if (cmd === "columnas") {
      return insertar(
        root,
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>' +
          '<td width="50%" valign="top" style="padding-right:8px;">Columna izquierda</td>' +
          '<td width="50%" valign="top" style="padding-left:8px;">Columna derecha</td>' +
          "</tr></table><p></p>"
      );
    }
    if (cmd === "tabla") {
      return insertar(
        root,
        '<table width="100%" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">' +
          '<tr><th style="border:1px solid #cbd5e1;">Título</th><th style="border:1px solid #cbd5e1;">Título</th></tr>' +
          '<tr><td style="border:1px solid #cbd5e1;">Dato</td><td style="border:1px solid #cbd5e1;">Dato</td></tr>' +
          "</table><p></p>"
      );
    }
    if (boton.dataset.block) return bloque(boton.dataset.block);
    if (boton.dataset.var) {
      return insertar(
        root,
        '<span data-var="' + boton.dataset.var + '" style="background-color:#d8f3dc;border-radius:4px;padding:0 4px;">{{' +
          boton.dataset.var + "}}</span>"
      );
    }
    if (cmd) document.execCommand(cmd, false, null);
    actualizarResumen(root);
  }

  function anchoDe(figura) {
    const valor = parseInt(figura.style.width, 10);
    return ANCHOS.indexOf(valor) >= 0 ? valor : 70;
  }

  function alinear(figura, lado) {
    const ancho = anchoDe(figura) + "%";
    figura.style.width = ancho;
    figura.style.display = "block";
    figura.style.clear = lado === "centro" ? "both" : "none";
    if (lado === "izq") {
      figura.style.float = "left";
      figura.style.margin = "4px 16px 12px 0";
    } else if (lado === "der") {
      figura.style.float = "right";
      figura.style.margin = "4px 0 12px 16px";
    } else {
      figura.style.float = "none";
      figura.style.margin = "12px auto";
    }
  }

  function ocultarBarras() {
    document.querySelectorAll(".fid-img-bar").forEach(function (barra) { barra.classList.remove("fid-on"); });
    document.querySelectorAll("figure.fid-sel").forEach(function (figura) { figura.classList.remove("fid-sel"); });
  }

  function seleccionarImagen(root, figura) {
    ocultarBarras();
    figura.classList.add("fid-sel");
    const barra = root.querySelector(".fid-img-bar");
    if (barra) {
      barra.classList.add("fid-on");
      barra._figura = figura;
    }
  }

  function moverFigura(figura, direccion) {
    const area = figura.parentElement;
    const hermanos = Array.prototype.filter.call(area.children, function (nodo) {
      return nodo.nodeType === 1 && !nodo.classList.contains("fid-img-bar");
    });
    const indice = hermanos.indexOf(figura);
    const destino = hermanos[indice + direccion];
    if (!destino) return;
    if (direccion < 0) area.insertBefore(figura, destino);
    else area.insertBefore(destino, figura);
  }

  function accionImagen(root, accion) {
    const figura = root.querySelector(".fid-img-bar")._figura;
    if (!figura || !figura.isConnected) return;
    if (accion === "izq" || accion === "centro" || accion === "der") alinear(figura, accion);
    if (accion === "chica") figura.style.width = "30%";
    if (accion === "media") figura.style.width = "60%";
    if (accion === "grande") figura.style.width = "100%";
    if (accion === "subir") moverFigura(figura, -1);
    if (accion === "bajar") moverFigura(figura, 1);
    if (accion === "quitar") {
      figura.remove();
      ocultarBarras();
    }
    actualizarResumen(root);
  }

  function alternarFuente(root) {
    const area = areaActiva(root);
    const fuente = root.querySelector("[data-source]");
    const activo = root.classList.toggle("fid-fuente-on");
    if (activo) {
      fuente.value = htmlActual(root);
      area.classList.add("d-none");
      fuente.classList.remove("d-none");
    } else {
      area.innerHTML = fuente.value;
      vestirImagenes(area);
      fuente.classList.add("d-none");
      area.classList.remove("d-none");
    }
  }

  function preparar(root) {
    const cuerpo = document.createElement("div");
    cuerpo.className = "fid-cuerpo";
    while (root.firstChild) cuerpo.appendChild(root.firstChild);
    const plego = document.createElement("button");
    plego.type = "button";
    plego.className = "fid-plegar";
    plego.innerHTML = '<span class="fid-resumen" data-resumen></span><span class="fid-accion">Editar</span>';
    const barra = document.createElement("div");
    barra.className = "fid-img-bar";
    barra.innerHTML =
      '<span>Imagen</span>' +
      '<button type="button" data-img="izq">Izquierda</button>' +
      '<button type="button" data-img="centro">Centro</button>' +
      '<button type="button" data-img="der">Derecha</button>' +
      '<button type="button" data-img="chica">Chica</button>' +
      '<button type="button" data-img="media">Media</button>' +
      '<button type="button" data-img="grande">Ancho completo</button>' +
      '<button type="button" data-img="subir">Subir</button>' +
      '<button type="button" data-img="bajar">Bajar</button>' +
      '<button type="button" data-img="quitar">Quitar</button>';
    cuerpo.insertBefore(barra, cuerpo.firstChild);
    root.appendChild(plego);
    root.appendChild(cuerpo);

    const area = areaActiva(root);
    const oculto = root.querySelector("[data-hidden]");
    area.setAttribute("contenteditable", "true");
    area.innerHTML = oculto.value;
    vestirImagenes(area);
    actualizarResumen(root);

    plego.addEventListener("click", function () {
      const abierto = root.classList.toggle("fid-abierto");
      plego.querySelector(".fid-accion").textContent = abierto ? "Contraer" : "Editar";
      if (abierto) {
        area.focus();
      } else {
        ocultarBarras();
        actualizarResumen(root);
      }
    });
    barra.querySelectorAll("button").forEach(function (boton) {
      boton.addEventListener("mousedown", function (evento) { evento.preventDefault(); });
      boton.addEventListener("click", function () { accionImagen(root, boton.dataset.img); });
    });
    root.querySelectorAll(".fid-tools button").forEach(function (boton) {
      boton.addEventListener("mousedown", function (evento) { evento.preventDefault(); });
      boton.addEventListener("click", function () { comando(root, boton); });
    });
    const familia = root.querySelector("[data-font]");
    if (familia) {
      familia.addEventListener("change", function () {
        area.focus();
        document.execCommand("fontName", false, familia.value);
      });
    }
    const tamano = root.querySelector("[data-size]");
    if (tamano) {
      tamano.addEventListener("change", function () {
        area.focus();
        document.execCommand("fontSize", false, tamano.value);
      });
    }
    root.querySelectorAll("[data-color]").forEach(function (input) {
      input.addEventListener("change", function () {
        area.focus();
        document.execCommand(input.dataset.color, false, input.value);
      });
    });
    const archivo = root.querySelector("[data-file]");
    archivo.addEventListener("change", function () {
      const file = archivo.files && archivo.files[0];
      archivo.value = "";
      imagenArchivo(root, file);
    });

    area.addEventListener("click", function (evento) {
      const figura = evento.target.closest("figure.fid-img");
      if (figura && area.contains(figura)) {
        seleccionarImagen(root, figura);
        return;
      }
      if (!evento.target.closest(".fid-asa")) ocultarBarras();
    });
    area.addEventListener("input", function () { actualizarResumen(root); });

    area.addEventListener("dragstart", function (evento) {
      const figura = evento.target.closest("figure.fid-img");
      if (!figura) return;
      area._arrastre = figura;
      evento.dataTransfer.effectAllowed = "move";
      evento.dataTransfer.setData("text/plain", "imagen");
    });
    area.addEventListener("dragover", function (evento) {
      if (!area._arrastre) return;
      evento.preventDefault();
      const destino = evento.target.closest("p, h1, h2, h3, h4, ul, ol, table, blockquote, figure");
      if (!destino || destino.parentElement !== area || destino === area._arrastre || area._arrastre.contains(destino)) return;
      const recta = destino.getBoundingClientRect();
      if (evento.clientY < recta.top + recta.height / 2) area.insertBefore(area._arrastre, destino);
      else area.insertBefore(area._arrastre, destino.nextSibling);
    });
    area.addEventListener("drop", function (evento) {
      evento.preventDefault();
      area._arrastre = null;
      actualizarResumen(root);
    });
    area.addEventListener("dragend", function () { area._arrastre = null; });

    area.addEventListener("mousedown", function (evento) {
      const asa = evento.target.closest(".fid-asa");
      if (!asa || !area.contains(asa)) return;
      evento.preventDefault();
      const figura = asa.closest("figure");
      seleccionarImagen(root, figura);
      const anchoPadre = area.getBoundingClientRect().width || 1;
      const inicioX = evento.clientX;
      const inicio = figura.getBoundingClientRect().width;
      function mover(ev) {
        const px = Math.max(90, inicio + (ev.clientX - inicioX));
        figura.style.width = Math.min(100, Math.max(20, Math.round((px / anchoPadre) * 100))) + "%";
      }
      function soltar() {
        document.removeEventListener("mousemove", mover);
        document.removeEventListener("mouseup", soltar);
      }
      document.addEventListener("mousemove", mover);
      document.addEventListener("mouseup", soltar);
    });

    const form = root.closest("form");
    if (form && !form.dataset.fidListo) {
      form.dataset.fidListo = "1";
      form.addEventListener("submit", function () {
        form.querySelectorAll("[data-fid-editor]").forEach(function (editor) {
          editor.querySelector("[data-hidden]").value = htmlActual(editor);
        });
      });
    }
  }

  document.querySelectorAll("[data-fid-editor]").forEach(preparar);

  const prueba = document.getElementById("fid-prueba");
  if (prueba) {
    prueba.addEventListener("click", async function () {
      const root = document.getElementById("editor-correo");
      const destino = document.getElementById("fid-destino").value.trim();
      const aviso = document.getElementById("fid-prueba-estado");
      const datos = new FormData();
      datos.append("destino", destino);
      datos.append("asunto", document.getElementById("fid-asunto").value);
      datos.append("html", htmlActual(root));
      prueba.disabled = true;
      aviso.textContent = "Enviando prueba…";
      aviso.className = "small text-secondary";
      try {
        const respuesta = await fetch(prueba.dataset.url, { method: "POST", body: datos });
        const cuerpo = await respuesta.json();
        if (!respuesta.ok || !cuerpo.ok) {
          aviso.textContent = cuerpo.error || "No se pudo enviar la prueba.";
          aviso.className = "small text-danger";
          return;
        }
        aviso.textContent = "Prueba enviada a " + destino + ".";
        aviso.className = "small text-success";
      } catch (error) {
        aviso.textContent = "No se pudo enviar la prueba.";
        aviso.className = "small text-danger";
      } finally {
        prueba.disabled = false;
      }
    });
  }

  const previa = document.getElementById("fid-previa");
  if (previa) {
    previa.addEventListener("click", function () {
      const root = document.getElementById("editor-correo");
      const muestra = htmlActual(root)
        .replaceAll("{{nombre}}", "Ana Pérez")
        .replaceAll("{{fecha}}", "19/10/2026 22:10")
        .replaceAll("{{sucursal}}", "Costanera")
        .replaceAll("{{movimiento}}", "Suma de puntos")
        .replaceAll("{{detalle}}", "Compra 12")
        .replaceAll("{{puntos}}", "+2")
        .replaceAll("{{saldo}}", "5")
        .replaceAll(
          "{{premios}}",
          "<p><strong>Premios</strong></p><ul><li><strong>Café</strong> (8 puntos): Te faltan 3 puntos</li></ul>"
        );
      const marco = document.getElementById("fid-marco");
      marco.classList.remove("d-none");
      marco.srcdoc = "<!DOCTYPE html><html><head><meta charset='utf-8'><style>body{margin:0;color:#1f2933;font-family:Arial,sans-serif}img{max-width:100%;height:auto}</style></head><body>" + muestra + "</body></html>";
    });
  }
})();
