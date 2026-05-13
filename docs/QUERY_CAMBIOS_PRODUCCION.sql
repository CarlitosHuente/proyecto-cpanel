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


-- [2026-05-10] [IA] [arqueo_caja]
-- Motivo: Módulo cuadratura diaria caja sucursal — import Excel (FEC_COMPR, N_COMP, DESC_CTA, DEBE, HABER opcional)
--         y captura terreno por día/canal; revertir por carga_id.
-- Entorno probado: local (aplicar en prod antes de usar rutas /arqueo-caja).
-- SQL:

CREATE TABLE IF NOT EXISTS arqueo_caja_cargas (
    carga_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sucursal_id INT NOT NULL,
    fecha_carga TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    nombre_archivo VARCHAR(255) NOT NULL,
    registros_insertados INT DEFAULT 0,
    usuario VARCHAR(120) DEFAULT NULL,
    KEY idx_ac_carga_suc (sucursal_id),
    CONSTRAINT fk_arqueo_caja_carga_sucursal FOREIGN KEY (sucursal_id) REFERENCES Sucursales(sucursal_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS arqueo_caja_lineas (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    carga_id INT NOT NULL,
    sucursal_id INT NOT NULL,
    fec_compr DATE NOT NULL,
    n_comp VARCHAR(120) NOT NULL,
    cod_comp VARCHAR(30) NULL DEFAULT NULL COMMENT 'Tipo doc / COD_COMP (ej. FAC)',
    desc_cta VARCHAR(255) NOT NULL,
    debe DECIMAL(18,2) NOT NULL DEFAULT 0,
    haber DECIMAL(18,2) NOT NULL DEFAULT 0,
    KEY idx_ac_linea_suc_fecha (sucursal_id, fec_compr),
    KEY idx_ac_linea_carga (carga_id),
    CONSTRAINT fk_arqueo_linea_carga FOREIGN KEY (carga_id) REFERENCES arqueo_caja_cargas(carga_id) ON DELETE CASCADE,
    CONSTRAINT fk_arqueo_linea_sucursal FOREIGN KEY (sucursal_id) REFERENCES Sucursales(sucursal_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS arqueo_caja_terreno (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sucursal_id INT NOT NULL,
    fecha DATE NOT NULL,
    caja TINYINT NOT NULL DEFAULT 1 COMMENT '1=Caja 1, 2=Caja 2',
    canal_raw VARCHAR(255) NOT NULL,
    canal_norm VARCHAR(255) NOT NULL,
    monto DECIMAL(18,2) NOT NULL,
    propina DECIMAL(18,2) NULL DEFAULT NULL COMMENT 'Solo informativo',
    notas VARCHAR(500) DEFAULT NULL,
    usuario VARCHAR(120) DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_arqueo_terreno (sucursal_id, fecha, canal_norm, caja),
    KEY idx_ac_terreno_suc_fecha (sucursal_id, fecha),
    KEY idx_ac_terreno_caja (sucursal_id, fecha, caja),
    CONSTRAINT fk_arqueo_terreno_sucursal FOREIGN KEY (sucursal_id) REFERENCES Sucursales(sucursal_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Rollback:
-- DROP TABLE IF EXISTS arqueo_caja_lineas;
-- DROP TABLE IF EXISTS arqueo_caja_terreno;
-- DROP TABLE IF EXISTS arqueo_caja_cargas;


-- [2026-05-11] [IA] [arqueo_caja terreno: caja, propina, unique por caja]
-- Motivo: Dos cajas por sucursal; propina informativa; no pisar silenciosamente mismo canal/caja/día.
-- Ejecutar SOLO si la tabla arqueo_caja_terreno ya existía sin columnas caja/propina (error si ya aplicado):
-- SQL:
-- ALTER TABLE arqueo_caja_terreno ADD COLUMN caja TINYINT NOT NULL DEFAULT 1 AFTER fecha;
-- ALTER TABLE arqueo_caja_terreno ADD COLUMN propina DECIMAL(18,2) NULL DEFAULT NULL AFTER monto;
-- ALTER TABLE arqueo_caja_terreno DROP INDEX uk_arqueo_terreno;
-- ALTER TABLE arqueo_caja_terreno ADD UNIQUE KEY uk_arqueo_terreno (sucursal_id, fecha, canal_norm, caja);
-- ALTER TABLE arqueo_caja_terreno ADD KEY idx_ac_terreno_caja (sucursal_id, fecha, caja);
-- Rollback (manual): revertir UNIQUE y columnas según necesidad.


-- [2026-05-10] [IA] [arqueo_caja_lineas.cod_comp]
-- Motivo: Import tipo PruebaSemana / contable: columna G (COD_COMP, tipo documento).
-- Ejecutar si la tabla ya existía sin cod_comp:
-- ALTER TABLE arqueo_caja_lineas ADD COLUMN cod_comp VARCHAR(30) NULL DEFAULT NULL COMMENT 'Tipo doc' AFTER n_comp;


-- [2026-05-02] [mantenimiento] [ventas_comercial.sucursal]
-- Motivo: Filas insertadas antes del parseo Sem./alias seguian mostrando nombre de archivo en dashboard.
-- No requiere ALTER: es correccion de DATOS. Ver script:
--   python scripts/fix_sucursal_ventas_comercial.py --dry-run
--   python scripts/fix_sucursal_ventas_comercial.py
-- Luego refrescar cache dashboard (/refresh).

