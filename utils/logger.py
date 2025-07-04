
import requests
from datetime import datetime

WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzMOQm3zY75XAvw_WIZasnfGyfhh5Tz-iZ0G76S-ZlGyBxT5l31Msu9XrQa3gcPNKwf/exec"

def registrar_acceso(usuario, estado, mensaje):
    data = {
        "usuario": usuario,
        "estado": estado,
        "mensaje": mensaje,
        "fecha": datetime.now().isoformat()
    }
    try:
        requests.post(WEBHOOK_URL, json=data, timeout=5)
    except Exception as e:
        print("Error al enviar log:", e)
