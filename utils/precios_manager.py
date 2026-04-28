import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRECIOS_FILE = os.path.join(BASE_DIR, 'precios.json')

def cargar_precios():
    """Carga la configuración actual de listas de precios."""
    if not os.path.exists(PRECIOS_FILE):
        return {
            "listas": [],
            "precios": {} # Formato: {"Producto A": {"Local": 1000, "Delivery": 1200}}
        }
    try:
        with open(PRECIOS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error leyendo precios.json: {e}")
        return {"listas": [], "precios": {}}

def guardar_precios(data):
    """Guarda la configuración de listas de precios."""
    with open(PRECIOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)