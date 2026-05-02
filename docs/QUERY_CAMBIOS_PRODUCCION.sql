-- =========================================================
-- PROYECTO HUENTE - QUERY CAMBIOS PRODUCCION
-- =========================================================
-- Regla: todo cambio SQL aplicado en local debe registrarse aqui
-- antes de pasar a produccion.
--
-- Formato sugerido:
-- [FECHA] [AUTOR] [MODULO]
-- Motivo:
-- Entorno probado:
-- SQL:
-- Rollback:
-- =========================================================


-- [2026-05-02] [pendiente] [modulo-pendiente]
-- Motivo:
-- Entorno probado: local
-- SQL:
-- ALTER TABLE ejemplo ADD COLUMN nueva_columna VARCHAR(100) NULL;
-- Rollback:
-- ALTER TABLE ejemplo DROP COLUMN nueva_columna;


-- [2026-05-02] [codex] [ventas comercial en DB]
-- Motivo: Comercial deja de usar CSV publicado; misma forma de filas que agricola + columna sucursal. Eliminar tablas de prueba V2.
-- Entorno probado: local
-- SQL:

DROP TABLE IF EXISTS ventas_fuente_v2;
DROP TABLE IF EXISTS cargas_fuente_v2;

CREATE TABLE IF NOT EXISTS cargas_comercial (
    carga_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fecha_carga TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    nombre_archivo VARCHAR(255) NOT NULL,
    registros_insertados INT DEFAULT 0,
    usuario VARCHAR(120) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ventas_comercial (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    carga_id INT NOT NULL,
    id_comanda VARCHAR(50) NULL,
    estado VARCHAR(60) NULL,
    estado_stk VARCHAR(60) NULL,
    fecha DATE NULL,
    apertura VARCHAR(20) NULL,
    hora_pedid VARCHAR(20) NULL,
    hora_entre VARCHAR(20) NULL,
    hora_acord VARCHAR(20) NULL,
    cierre VARCHAR(20) NULL,
    cod_horari VARCHAR(50) NULL,
    des_horari VARCHAR(120) NULL,
    cod_repart VARCHAR(50) NULL,
    des_repart VARCHAR(120) NULL,
    cod_zona VARCHAR(50) NULL,
    des_zona VARCHAR(120) NULL,
    cod_client VARCHAR(50) NULL,
    des_client VARCHAR(180) NULL,
    propina DECIMAL(18,2) NULL,
    impresion VARCHAR(50) NULL,
    subtotal DECIMAL(18,2) NULL,
    total DECIMAL(18,2) NULL,
    t_comp VARCHAR(20) NULL,
    n_comp VARCHAR(50) NULL,
    cod_articu VARCHAR(50) NULL,
    des_articu VARCHAR(255) NULL,
    tipo VARCHAR(80) NULL,
    rubro VARCHAR(120) NULL,
    cod_bodega VARCHAR(50) NULL,
    des_bodega VARCHAR(120) NULL,
    cantidad DECIMAL(18,3) NULL,
    precio DECIMAL(18,2) NULL,
    precio_lis DECIMAL(18,2) NULL,
    sub_rengl DECIMAL(18,2) NULL,
    tot_rengl DECIMAL(18,2) NULL,
    hora_coci VARCHAR(20) NULL,
    envio_coci VARCHAR(20) NULL,
    modificado VARCHAR(120) NULL,
    motivo VARCHAR(255) NULL,
    autoriza VARCHAR(120) NULL,
    usuario VARCHAR(120) NULL,
    fecha_anu VARCHAR(50) NULL,
    hora_anu VARCHAR(50) NULL,
    sucursal VARCHAR(120) NOT NULL,
    KEY idx_vc_carga (carga_id),
    KEY idx_vc_fecha (fecha),
    CONSTRAINT fk_ventas_comercial_carga FOREIGN KEY (carga_id) REFERENCES cargas_comercial(carga_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Rollback (quitar comercial y opcionalmente restaurar V2):
-- DROP TABLE IF EXISTS ventas_comercial;
-- DROP TABLE IF EXISTS cargas_comercial;


-- [2026-05-02] [mantenimiento] [ventas_comercial.sucursal]
-- Motivo: Filas insertadas antes del parseo Sem./alias seguian mostrando nombre de archivo en dashboard.
-- No requiere ALTER: es correccion de DATOS. Ver script:
--   python scripts/fix_sucursal_ventas_comercial.py --dry-run
--   python scripts/fix_sucursal_ventas_comercial.py
-- Luego refrescar cache dashboard (/refresh).

