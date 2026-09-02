"""OpenRouteService: geocoding + optimización de rutas (DespachoWeb)."""
from __future__ import annotations

import logging
from typing import Any, List, Optional

import requests

from utils.despacho_web_maps import normalizar_direccion_maps
from utils.env_config import ors_settings

logger = logging.getLogger(__name__)

ORS_BASE = "https://api.openrouteservice.org"
GEOCODE_PATH = "/geocode/search"
OPTIMIZATION_PATH = "/optimization"
TIMEOUT = 30


class OrsError(Exception):
    pass


class OrsGeocodeError(OrsError):
    def __init__(self, direccion: str, mensaje: str = ""):
        self.direccion = direccion
        super().__init__(mensaje or f"No se pudo geocodificar: {direccion}")


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": api_key,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }


def geocodificar_direccion(direccion: str, api_key: Optional[str] = None) -> tuple[float, float]:
    """Retorna (lon, lat) para una dirección en Chile."""
    cfg = ors_settings()
    key = (api_key or cfg.get("api_key") or "").strip()
    if not key:
        raise OrsError("ORS_API_KEY no configurada.")

    texto = normalizar_direccion_maps(direccion)
    params = {
        "text": texto,
        "boundary.country": "CHL",
        "size": 1,
    }
    try:
        resp = requests.get(
            f"{ORS_BASE}{GEOCODE_PATH}",
            params=params,
            headers=_headers(key),
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise OrsError(f"Error de red al geocodificar: {e}") from e

    if resp.status_code == 401:
        raise OrsError("API key ORS inválida o expirada.")
    if resp.status_code == 429:
        raise OrsError("Cuota diaria ORS agotada; intente mañana o reduzca paradas.")
    if not resp.ok:
        raise OrsGeocodeError(texto, f"Geocoding HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    features = data.get("features") or []
    if not features:
        raise OrsGeocodeError(texto)

    coords = features[0].get("geometry", {}).get("coordinates")
    if not coords or len(coords) < 2:
        raise OrsGeocodeError(texto)
    return float(coords[0]), float(coords[1])


def optimizar_paradas(
    origen: str,
    paradas: List[dict],
    *,
    volver_origen: bool = False,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    Optimiza orden de entrega con ORS/VROOM.

    paradas: lista de {id, direccion, n_orden?, cliente?}
    Retorna {orden_ids, paradas, advertencias, no_geocodificadas}.
    """
    cfg = ors_settings()
    key = (api_key or cfg.get("api_key") or "").strip()
    if not key:
        raise OrsError("ORS_API_KEY no configurada.")

    if not paradas:
        raise OrsError("Sin paradas para optimizar.")

    advertencias: list[str] = []
    jobs: list[dict] = []
    id_por_job: dict[int, dict] = {}

    try:
        lon_o, lat_o = geocodificar_direccion(origen, api_key=key)
    except OrsGeocodeError as e:
        raise OrsError(f"Origen no geocodificado: {e}") from e

    no_geo: list[dict] = []
    for i, p in enumerate(paradas):
        pid = int(p.get("id", i + 1))
        try:
            lon, lat = geocodificar_direccion(p["direccion"], api_key=key)
        except OrsGeocodeError:
            no_geo.append(p)
            continue
        jobs.append({"id": pid, "location": [lon, lat]})
        id_por_job[pid] = p

    if not jobs:
        raise OrsError("Ninguna parada pudo geocodificarse.")

    if no_geo:
        advertencias.append(
            f"{len(no_geo)} parada(s) sin geocodificar (quedaron fuera de la optimización)."
        )

    if volver_origen:
        vehicle_end = [lon_o, lat_o]
    elif len(jobs) == 1:
        vehicle_end = jobs[0]["location"]
    else:
        vehicle_end = jobs[-1]["location"]

    payload = {
        "jobs": jobs,
        "vehicles": [
            {
                "id": 1,
                "profile": "driving-car",
                "start": [lon_o, lat_o],
                "end": vehicle_end,
            }
        ],
    }

    try:
        resp = requests.post(
            f"{ORS_BASE}{OPTIMIZATION_PATH}",
            json=payload,
            headers=_headers(key),
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise OrsError(f"Error de red en optimización: {e}") from e

    if resp.status_code == 401:
        raise OrsError("API key ORS inválida o expirada.")
    if resp.status_code == 429:
        raise OrsError("Cuota ORS agotada; intente más tarde.")
    if not resp.ok:
        logger.warning("ORS optimization error: %s", resp.text[:500])
        raise OrsError(f"Optimización falló (HTTP {resp.status_code}).")

    data = resp.json()
    routes = data.get("routes") or []
    if not routes:
        raise OrsError("ORS no devolvió rutas.")

    steps = routes[0].get("steps") or []
    orden_ids: list[int] = []
    for step in steps:
        if step.get("type") == "job" and step.get("job") is not None:
            jid = int(step["job"])
            if jid not in orden_ids:
                orden_ids.append(jid)

    if not orden_ids:
        orden_ids = [j["id"] for j in jobs]

    orden_paradas = [id_por_job[jid] for jid in orden_ids if jid in id_por_job]

    return {
        "orden_ids": orden_ids,
        "paradas": orden_paradas,
        "advertencias": advertencias,
        "no_geocodificadas": no_geo,
        "origen_normalizado": normalizar_direccion_maps(origen),
    }


def geocodificar_paradas(
    paradas: List[dict],
    *,
    origen: Optional[str] = None,
    incluir_origen: bool = False,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Geocodifica paradas para mapa de puntos (sin optimizar ni trazar ruta)."""
    cfg = ors_settings()
    key = (api_key or cfg.get("api_key") or "").strip()
    if not key:
        raise OrsError("ORS_API_KEY no configurada.")

    if not paradas and not (incluir_origen and origen):
        raise OrsError("Sin paradas para geocodificar.")

    puntos: list[dict] = []
    no_geo: list[dict] = []

    if incluir_origen and origen:
        try:
            lon, lat = geocodificar_direccion(origen, api_key=key)
            puntos.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "n_orden": "",
                    "cliente": "Origen",
                    "direccion": normalizar_direccion_maps(origen),
                    "es_origen": True,
                }
            )
        except OrsGeocodeError:
            pass

    for i, p in enumerate(paradas):
        try:
            lon, lat = geocodificar_direccion(p["direccion"], api_key=key)
        except OrsGeocodeError:
            no_geo.append(p)
            continue
        puntos.append(
            {
                "lat": lat,
                "lon": lon,
                "n_orden": p.get("n_orden") or "",
                "cliente": p.get("cliente") or "",
                "direccion": p.get("direccion") or "",
                "orden": i + 1,
                "es_origen": False,
            }
        )

    if not puntos:
        raise OrsError("Ninguna parada pudo geocodificarse.")

    advertencias: list[str] = []
    if no_geo:
        advertencias.append(
            f"{len(no_geo)} parada(s) sin geocodificar (no aparecen en el mapa)."
        )

    return {"puntos": puntos, "no_geocodificadas": no_geo, "advertencias": advertencias}
