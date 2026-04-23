import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configuración de credenciales reutilizando el JSON de tu raíz
SCOPES = ['https://www.googleapis.com/auth/drive']
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
SERVICE_ACCOUNT_FILE = os.path.join(ROOT_DIR, 'credenciales_google.json')

def obtener_servicio_drive():
    """Crea la conexión autorizada con Google Drive."""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def crear_o_obtener_carpeta(nombre_carpeta, parent_id=None):
    """Busca una carpeta por nombre. Si no existe, la crea dinámicamente."""
    servicio = obtener_servicio_drive()
    query = f"name='{nombre_carpeta}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
        
    resultados = servicio.files().list(q=query, fields="files(id, name)").execute()
    archivos = resultados.get('files', [])
    
    if archivos:
        return archivos[0]['id'] # La carpeta ya existe, retornamos su ID
    else:
        # La carpeta no existe, procedemos a crearla
        file_metadata = {
            'name': nombre_carpeta,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
            
        carpeta = servicio.files().create(body=file_metadata, fields='id').execute()
        return carpeta.get('id')

def subir_respaldo_pago(archivo_path, nombre_archivo, mimetype, carpeta_id):
    """Sube un archivo (Ej: PDF o JPG) a Drive, le da permisos de vista y retorna la URL."""
    servicio = obtener_servicio_drive()
    file_metadata = {'name': nombre_archivo, 'parents': [carpeta_id]}
    media = MediaFileUpload(archivo_path, mimetype=mimetype, resumable=True)
    
    # Subimos el archivo y le pedimos a Drive que nos devuelva el webViewLink
    archivo = servicio.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    file_id = archivo.get('id')
    
    # Le damos permiso de lectura "cualquiera con el enlace" para que el iframe de tu ERP no pida login de Google
    servicio.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()

    return file_id, archivo.get('webViewLink')