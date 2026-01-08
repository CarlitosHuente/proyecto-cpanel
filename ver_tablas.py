from utils.db import get_db_connection

conn = get_db_connection()
with conn.cursor() as cursor:
    cursor.execute("SHOW TABLES;")
    tablas = cursor.fetchall()
    
    print("\n--- TABLAS EN TU BASE DE DATOS ---")
    for tabla in tablas:
        # Dependiendo de tu conector, esto puede venir como tupla o diccionario
        print(tabla)
    print("----------------------------------\n")

conn.close()