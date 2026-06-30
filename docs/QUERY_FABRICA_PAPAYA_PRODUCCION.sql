-- =============================================================================
-- Fábrica Papaya — despliegue PRODUCCIÓN (DDL)
-- Ejecutar UNA vez en MySQL antes de desplegar el código web.
-- Datos históricos: docs/DATA_FABRICA_PAPAYA_IMPORT.sql (segundo paso).
-- Generado: 2026-06-29
-- =============================================================================

-- [2026-06-29] [fabrica_papaya]
-- Módulo Fábrica Papaya: captura diaria (MP, elaboración, transformación, despacho),
-- stock real semanal, catálogo de conceptos y cierres de stock (inicial / ajuste).
-- Semana operativa lun–dom, semana_iso ISO (Chile).

CREATE TABLE IF NOT EXISTS papaya_conceptos (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(64) NOT NULL COMMENT 'Slug estable p. ej. nectar_300cc, papaya_congelada',
    nombre VARCHAR(255) NOT NULL,
    tipo ENUM('materia_prima', 'intermedio', 'terminado', 'movimiento') NOT NULL,
    unidad ENUM('kg', 'und', 'lt') NOT NULL DEFAULT 'kg',
    producto_erp VARCHAR(255) NULL DEFAULT NULL COMMENT 'Nombre en Productos ERP, sin FK forzada',
    activo TINYINT(1) NOT NULL DEFAULT 1,
    orden INT NOT NULL DEFAULT 0,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_papaya_concepto_codigo (codigo),
    KEY idx_papaya_concepto_tipo (tipo, activo, orden)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS papaya_cierre_stock (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fecha DATE NOT NULL COMMENT 'Fecha del snapshot (stock concreto al cierre de este día)',
    tipo ENUM('inicial', 'ajuste') NOT NULL DEFAULT 'inicial' COMMENT 'inicial=arranque; ajuste=corrección inventario',
    concepto_id INT NOT NULL,
    cantidad DECIMAL(12,3) NOT NULL DEFAULT 0,
    es_manual TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Legacy; siempre 1 en captura web',
    notas VARCHAR(500) NULL DEFAULT NULL,
    capturado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_papaya_cierre_fecha_concepto (fecha, concepto_id),
    KEY idx_papaya_cierre_concepto (concepto_id),
    CONSTRAINT fk_papaya_cierre_concepto FOREIGN KEY (concepto_id) REFERENCES papaya_conceptos (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS papaya_dia_mp (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fecha DATE NOT NULL,
    anio SMALLINT NOT NULL,
    semana_iso TINYINT UNSIGNED NOT NULL COMMENT 'Semana ISO lun–dom (1–53)',
    entrada_huerto_kg DECIMAL(12,3) NOT NULL DEFAULT 0,
    entrada_externa_kg DECIMAL(12,3) NOT NULL DEFAULT 0,
    kg_a_elaboracion DECIMAL(12,3) NOT NULL DEFAULT 0 COMMENT 'Kg MP enviados a elaboración',
    kg_descarte DECIMAL(12,3) NOT NULL DEFAULT 0,
    comentario_descarte TEXT NULL DEFAULT NULL,
    kg_venta_calibre DECIMAL(12,3) NOT NULL DEFAULT 0,
    observaciones TEXT NULL DEFAULT NULL,
    capturado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_papaya_dia_mp_fecha (fecha),
    KEY idx_papaya_dia_mp_semana (anio, semana_iso)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS papaya_dia_elaboracion (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fecha DATE NOT NULL,
    anio SMALLINT NOT NULL,
    semana_iso TINYINT UNSIGNED NOT NULL,
    kg_elaborados DECIMAL(12,3) NOT NULL DEFAULT 0,
    kg_directa DECIMAL(12,3) NOT NULL DEFAULT 0 COMMENT 'Salida elaboración → papaya directa',
    kg_congelada DECIMAL(12,3) NOT NULL DEFAULT 0 COMMENT 'Salida elaboración → a congelar',
    rendimiento_pct DECIMAL(8,4) NULL DEFAULT NULL COMMENT 'Pelador; calculado app/web',
    observaciones TEXT NULL DEFAULT NULL,
    capturado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_papaya_dia_elab_fecha (fecha),
    KEY idx_papaya_dia_elab_semana (anio, semana_iso)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS papaya_dia_transformacion (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fecha DATE NOT NULL,
    anio SMALLINT NOT NULL,
    semana_iso TINYINT UNSIGNED NOT NULL,
    concepto_id INT NOT NULL COMMENT 'Producto terminado (papaya_conceptos.terminado)',
    fuente ENUM('directa', 'congelada') NOT NULL,
    kg_fuente DECIMAL(12,3) NOT NULL DEFAULT 0 COMMENT 'Kg consumidos de la fuente intermedia',
    cantidad_producida DECIMAL(12,3) NOT NULL DEFAULT 0 COMMENT 'Und o kg según unidad del concepto',
    observaciones VARCHAR(500) NULL DEFAULT NULL,
    capturado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_papaya_transf_fecha (fecha),
    KEY idx_papaya_transf_semana (anio, semana_iso),
    KEY idx_papaya_transf_concepto (concepto_id),
    CONSTRAINT fk_papaya_transf_concepto FOREIGN KEY (concepto_id) REFERENCES papaya_conceptos (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS papaya_dia_despacho (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fecha DATE NOT NULL,
    anio SMALLINT NOT NULL,
    semana_iso TINYINT UNSIGNED NOT NULL,
    concepto_id INT NOT NULL COMMENT 'Terminado o intermedio (venta bulk directa/congelada)',
    cantidad DECIMAL(12,3) NOT NULL DEFAULT 0,
    observaciones VARCHAR(500) NULL DEFAULT NULL,
    capturado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_papaya_despacho_fecha (fecha),
    KEY idx_papaya_despacho_semana (anio, semana_iso),
    KEY idx_papaya_despacho_concepto (concepto_id),
    CONSTRAINT fk_papaya_despacho_concepto FOREIGN KEY (concepto_id) REFERENCES papaya_conceptos (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS papaya_semana_stock_real (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    anio SMALLINT NOT NULL,
    semana_iso TINYINT UNSIGNED NOT NULL,
    concepto_id INT NOT NULL,
    cantidad DECIMAL(12,3) NOT NULL DEFAULT 0,
    observaciones VARCHAR(500) NULL DEFAULT NULL,
    capturado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_papaya_stock_real_semana (anio, semana_iso, concepto_id),
    KEY idx_papaya_stock_real_concepto (concepto_id),
    CONSTRAINT fk_papaya_stock_real_concepto FOREIGN KEY (concepto_id) REFERENCES papaya_conceptos (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Catálogo completo (MP, intermedios, terminados): ver DATA_FABRICA_PAPAYA_IMPORT.sql

-- =============================================================================
-- Si ya ejecutaste una versión anterior SIN columna tipo en papaya_cierre_stock:
--
-- ALTER TABLE papaya_cierre_stock
-- ADD COLUMN tipo ENUM('inicial', 'ajuste') NOT NULL DEFAULT 'inicial'
-- COMMENT 'inicial=arranque; ajuste=corrección inventario'
-- AFTER fecha;
-- UPDATE papaya_cierre_stock SET tipo = 'inicial' WHERE es_manual = 1;
-- =============================================================================

-- Rollback completo (solo emergencia):
-- DROP TABLE IF EXISTS papaya_semana_stock_real;
-- DROP TABLE IF EXISTS papaya_dia_despacho;
-- DROP TABLE IF EXISTS papaya_dia_transformacion;
-- DROP TABLE IF EXISTS papaya_dia_elaboracion;
-- DROP TABLE IF EXISTS papaya_dia_mp;
-- DROP TABLE IF EXISTS papaya_cierre_stock;
-- DROP TABLE IF EXISTS papaya_conceptos;
