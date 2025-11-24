import os
import pymysql

def get_db_connection():
    # Si existen variables de entorno, las usamos (producción)
    host = os.environ.get("DB_HOST")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")
    name = os.environ.get("DB_NAME")

    if host and user and name:
        # Modo producción (cPanel)
        return pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=name,
            cursorclass=pymysql.cursors.DictCursor,
        )

    # Si no hay variables → asumimos entorno local (lo que ya tienes)
    return pymysql.connect(
        host="localhost",
        user="root",
        password="6235834",
        database="huente_app",
        cursorclass=pymysql.cursors.DictCursor,
    )
