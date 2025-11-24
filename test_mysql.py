from utils.db import get_db_connection

conn = get_db_connection()
print("Conexion OK")
conn.close()
