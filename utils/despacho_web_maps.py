"""Enlaces Google Maps para rutas DespachoWeb (sin API key)."""
from __future__ import annotations

from typing import List, Optional
from urllib.parse import quote

# Google Maps URLs: máx. 9 waypoints intermedios (desktop).
MAX_WAYPOINTS_GOOGLE = 9
MAX_PARADAS_POR_ENLACE = MAX_WAYPOINTS_GOOGLE + 1  # waypoints + destino


def normalizar_direccion_maps(direccion: str, comuna: str = "") -> str:
    """Texto de dirección apto para geocoding / URLs."""
    direccion = (direccion or "").strip()
    comuna = (comuna or "").strip()
    if comuna and comuna.lower() not in direccion.lower():
        if direccion:
            direccion = f"{direccion}, {comuna}"
        else:
            direccion = comuna
    low = direccion.lower()
    if "chile" not in low and "santiago" not in low and "región" not in low:
        direccion = f"{direccion}, Chile"
    return direccion.strip(", ")


def url_buscar_direccion(direccion: str) -> str:
    q = quote(normalizar_direccion_maps(direccion))
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def armar_url_ruta_google(
    origen: str,
    paradas: List[str],
    *,
    destino: Optional[str] = None,
    travelmode: str = "driving",
) -> str:
    """
    Arma enlace directions. paradas = orden de entrega (texto).
    Si hay más de MAX_PARADAS_POR_ENLACE, usar partir_ruta_google().
    """
    origen = normalizar_direccion_maps(origen)
    paradas = [normalizar_direccion_maps(p) for p in paradas if (p or "").strip()]
    if not paradas:
        return url_buscar_direccion(origen)

    if len(paradas) == 1:
        return (
            f"https://www.google.com/maps/dir/?api=1"
            f"&origin={quote(origen)}"
            f"&destination={quote(paradas[0])}"
            f"&travelmode={travelmode}"
        )

    if destino:
        dest = normalizar_direccion_maps(destino)
        intermedias = [p for p in paradas if p != dest]
        if not intermedias:
            intermedias = paradas[:-1]
            dest = paradas[-1]
    else:
        intermedias = paradas[:-1]
        dest = paradas[-1]

    if len(intermedias) > MAX_WAYPOINTS_GOOGLE:
        raise ValueError(
            f"Máximo {MAX_PARADAS_POR_ENLACE} paradas por enlace Google Maps "
            f"({len(intermedias) + 1} indicadas)."
        )

    url = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={quote(origen)}"
        f"&destination={quote(dest)}"
        f"&travelmode={travelmode}"
    )
    if intermedias:
        wps = "|".join(quote(p, safe="") for p in intermedias)
        url += f"&waypoints={wps}"
    return url


def partir_ruta_google(
    origen: str,
    paradas: List[str],
    *,
    volver_origen: bool = False,
    travelmode: str = "driving",
) -> List[dict]:
    """
    Divide paradas en varios enlaces Google (máx. 10 paradas por tramo).
    Retorna lista de {titulo, url, paradas, origen, destino}.
    """
    origen = normalizar_direccion_maps(origen)
    paradas = [normalizar_direccion_maps(p) for p in paradas if (p or "").strip()]
    if not paradas:
        return []

    segmentos: List[dict] = []
    idx = 0
    tramo = 1
    start = origen

    while idx < len(paradas):
        restantes = len(paradas) - idx
        if restantes <= MAX_PARADAS_POR_ENLACE:
            chunk = paradas[idx:]
            idx = len(paradas)
        else:
            chunk = paradas[idx : idx + MAX_PARADAS_POR_ENLACE]
            idx += MAX_PARADAS_POR_ENLACE

        url = armar_url_ruta_google(start, chunk, travelmode=travelmode)
        dest = chunk[-1]

        segmentos.append(
            {
                "titulo": f"Ruta {tramo}",
                "url": url,
                "paradas": chunk,
                "origen": start,
                "destino": dest,
            }
        )
        tramo += 1
        start = dest

    if volver_origen and segmentos and segmentos[-1]["destino"] != origen:
        url = armar_url_ruta_google(segmentos[-1]["destino"], [origen], travelmode=travelmode)
        segmentos.append(
            {
                "titulo": f"Ruta {tramo} (vuelta)",
                "url": url,
                "paradas": [origen],
                "origen": segmentos[-1]["destino"],
                "destino": origen,
            }
        )

    return segmentos


def enlaces_busqueda_puntos(paradas: List[dict]) -> List[dict]:
    """
    Enlaces Google Maps de búsqueda (un pin por dirección, sin trazar ruta).
    paradas: {n_orden, cliente, direccion, comuna?}
    """
    enlaces: List[dict] = []
    for i, p in enumerate(paradas):
        direccion = (p.get("direccion") or "").strip()
        if not direccion:
            continue
        n_orden = (p.get("n_orden") or "").strip()
        titulo = f"Punto {i + 1}"
        if n_orden:
            titulo += f" — N° {n_orden}"
        enlaces.append(
            {
                "titulo": titulo,
                "url": url_buscar_direccion(direccion),
                "direccion": normalizar_direccion_maps(direccion, p.get("comuna") or ""),
                "n_orden": n_orden,
            }
        )
    return enlaces
