import os
from utils.db import get_db_connection

# --- CÓDIGO SQL ---
sql_commands = [
    """
    CREATE TABLE IF NOT EXISTS flujo_categorias (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(100) NOT NULL,
        tipo ENUM('ingreso', 'egreso') NOT NULL,
        activo BOOLEAN DEFAULT TRUE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS flujo_entidades (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(100) NOT NULL,
        tipo ENUM('interno', 'cliente', 'proveedor', 'banco') DEFAULT 'proveedor',
        activo BOOLEAN DEFAULT TRUE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS flujo_contratos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(100),
        entidad_id INT,
        categoria_id INT,
        dia_vencimiento INT NOT NULL,
        monto_estimado DECIMAL(15, 2),
        activo BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (entidad_id) REFERENCES flujo_entidades(id),
        FOREIGN KEY (categoria_id) REFERENCES flujo_categorias(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS flujo_movimientos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        fecha DATE NOT NULL,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tipo ENUM('ingreso', 'egreso') NOT NULL,
        monto DECIMAL(15, 2) NOT NULL,
        categoria_id INT,
        entidad_id INT,
        descripcion VARCHAR(255),
        estado ENUM('proyectado', 'real', 'anulado') DEFAULT 'real',
        es_automato BOOLEAN DEFAULT FALSE,
        usuario_responsable VARCHAR(100),
        FOREIGN KEY (categoria_id) REFERENCES flujo_categorias(id),
        FOREIGN KEY (entidad_id) REFERENCES flujo_entidades(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS flujo_auditoria (
        id INT AUTO_INCREMENT PRIMARY KEY,
        usuario_email VARCHAR(100),
        accion VARCHAR(50), 
        detalle TEXT, 
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    # --- DATOS SEMILLA (Solo se insertan si las tablas están vacías) ---
    """
    INSERT IGNORE INTO flujo_categorias (id, nombre, tipo) VALUES 
    (1, 'Venta Local', 'ingreso'), 
    (2, 'Venta Delivery App', 'ingreso'), 
    (3, 'Transbank', 'ingreso'),
    (4, 'Arriendo', 'egreso'), 
    (5, 'Servicios Básicos', 'egreso'), 
    (6, 'Proveedores MP', 'egreso'), 
    (7, 'Fondo por Rendir', 'egreso');
    """,
    """
    INSERT IGNORE INTO flujo_entidades (id, nombre, tipo) VALUES 
    (1, 'Uber Eats', 'cliente'), 
    (2, 'Pedidos Ya', 'cliente'), 
    (3, 'Transbank', 'banco'), 
    (4, 'Local Principal', 'interno');
    """
]

def ejecutar_migracion():
    print("🔄 Conectando a la base de datos...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print("🛠 Creando tablas para el módulo de Flujo...")
        for command in sql_commands:
            cursor.execute(command)
        
        conn.commit()
        print("✅ Tablas creadas y datos iniciales insertados correctamente.")
        
    except Exception as e:
        print(f"❌ Error al ejecutar SQL: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
        print("🔌 Conexión cerrada.")

if __name__ == "__main__":
    ejecutar_migracion()