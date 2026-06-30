import pymysql

from utils.env_config import db_connection_params


def get_db_connection():
    cfg = db_connection_params()
    return pymysql.connect(
        host=cfg["host"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        cursorclass=pymysql.cursors.DictCursor,
    )
