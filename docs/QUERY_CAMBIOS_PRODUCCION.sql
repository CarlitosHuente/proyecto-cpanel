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


-- [2026-05-14] [IA] [fabrica_produccion.queso_pizza_gr]
-- Motivo: Queso que no califica para empanada va a pizza; neto empanada = inicial − pizza − merma.
-- Entorno probado: local
-- SQL:

ALTER TABLE fabrica_produccion
ADD COLUMN queso_pizza_gr DECIMAL(10,2) NOT NULL DEFAULT 0
COMMENT 'Queso desviado a pizza (g), entre inicial y merma'
AFTER queso_inicial_gr;

-- Rollback:
-- ALTER TABLE fabrica_produccion DROP COLUMN queso_pizza_gr;


-- [2026-05-28] [IA] [despacho_web]
-- Motivo: Módulo DespachoWeb — carga PDF facturas tienda web, órdenes para AppSheet vía MySQL.
-- Tablas alineadas AppSheet: Orden, `Detalle O.C`, catálogo en Productos (ERP existente).
-- Entorno probado: producción datoshuente.com
-- SQL:

-- Prerrequisito FK detalle → Productos(nombre): nombre debe ser UNIQUE
-- (omitir si ya existe índice equivalente)
-- ALTER TABLE Productos ADD UNIQUE KEY uk_productos_nombre (nombre);

DROP TABLE IF EXISTS `Detalle O.C`;
DROP TABLE IF EXISTS dw_detalle_oc;
DROP TABLE IF EXISTS Orden;
DROP TABLE IF EXISTS dw_orden;

CREATE TABLE Orden (
    n_orden VARCHAR(50) NOT NULL PRIMARY KEY,
    fecha_oc DATE NOT NULL,
    cliente VARCHAR(255) NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
    transporte VARCHAR(50) NULL DEFAULT NULL,
    fecha_estado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    respaldo VARCHAR(500) NULL DEFAULT NULL,
    direccion VARCHAR(500) NOT NULL,
    comuna VARCHAR(120) NULL DEFAULT NULL,
    celular VARCHAR(20) NOT NULL,
    email VARCHAR(255) NULL DEFAULT NULL,
    url VARCHAR(500) NULL DEFAULT NULL,
    obs TEXT NULL,
    creado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_orden_estado (estado),
    KEY idx_orden_comuna (comuna),
    KEY idx_orden_fecha (fecha_oc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `Detalle O.C` (
    detalle_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    n_orden VARCHAR(50) NOT NULL,
    producto VARCHAR(255) NOT NULL,
    cantidad DECIMAL(10,2) NOT NULL DEFAULT 1,
    total INT NOT NULL DEFAULT 0,
    estado VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
    KEY idx_det_orden (n_orden),
    KEY idx_det_producto (producto),
    CONSTRAINT fk_det_orden FOREIGN KEY (n_orden) REFERENCES Orden (n_orden) ON DELETE CASCADE,
    CONSTRAINT fk_det_producto FOREIGN KEY (producto) REFERENCES `Productos` (`nombre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Rollback:
-- DROP TABLE IF EXISTS `Detalle O.C`;
-- DROP TABLE IF EXISTS Orden;


-- [2026-06-29] [IA] [fabrica_papaya]
-- Motivo: Módulo Fábrica Papaya — captura diaria vía AppSheet (MP, elaboración, transformación,
--         despacho), stock real semanal, catálogo de conceptos/productos y cierres de stock manual
--         (arranque histórico). Semana operativa lun–dom, semana_iso ISO (Chile).
--         Rendimiento elaboración = (kg_directa + kg_congelada) / kg_elaborados (calculado en app).
-- Entorno probado: pendiente local
-- SQL:

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
    tipo ENUM('inicial', 'ajuste') NOT NULL DEFAULT 'inicial',
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
    rendimiento_pct DECIMAL(8,4) NULL DEFAULT NULL COMMENT '(directa+congelada)/elaborados, calculado app/web',
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

CREATE TABLE IF NOT EXISTS papaya_despacho_guia (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fecha DATE NOT NULL,
    anio SMALLINT NOT NULL,
    semana_iso TINYINT UNSIGNED NOT NULL,
    numero_doc VARCHAR(64) NULL DEFAULT NULL COMMENT 'N° guía / documento (opcional)',
    destino VARCHAR(255) NULL DEFAULT NULL COMMENT 'Destino / cliente (opcional)',
    observaciones VARCHAR(500) NULL DEFAULT NULL,
    capturado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_papaya_guia_fecha (fecha),
    KEY idx_papaya_guia_semana (anio, semana_iso),
    KEY idx_papaya_guia_numero (numero_doc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS papaya_dia_despacho (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fecha DATE NOT NULL,
    anio SMALLINT NOT NULL,
    semana_iso TINYINT UNSIGNED NOT NULL,
    guia_id INT NULL DEFAULT NULL COMMENT 'FK guía; NULL = histórico / línea suelta',
    concepto_id INT NOT NULL COMMENT 'Terminado o intermedio (venta bulk directa/congelada)',
    cantidad DECIMAL(12,3) NOT NULL DEFAULT 0,
    numero_doc VARCHAR(64) NULL DEFAULT NULL COMMENT 'Legacy línea suelta',
    destino VARCHAR(255) NULL DEFAULT NULL COMMENT 'Legacy línea suelta',
    observaciones VARCHAR(500) NULL DEFAULT NULL,
    capturado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_papaya_despacho_fecha (fecha),
    KEY idx_papaya_despacho_semana (anio, semana_iso),
    KEY idx_papaya_despacho_guia (guia_id),
    KEY idx_papaya_despacho_concepto (concepto_id),
    CONSTRAINT fk_papaya_despacho_guia FOREIGN KEY (guia_id) REFERENCES papaya_despacho_guia (id) ON DELETE CASCADE,
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

-- Conceptos base (MP, intermedios). Productos terminados: alta vía web/import Excel.
INSERT INTO papaya_conceptos (codigo, nombre, tipo, unidad, orden) VALUES
    ('mp_huerto', 'Stock MP huerto', 'materia_prima', 'kg', 10),
    ('papaya_directa', 'Papaya directa', 'intermedio', 'kg', 20),
    ('papaya_congelada', 'Papaya congelada', 'intermedio', 'kg', 30),
    ('descarte', 'Descarte', 'movimiento', 'kg', 40),
    ('venta_calibre', 'Venta descarte por calibre', 'movimiento', 'kg', 50)
ON DUPLICATE KEY UPDATE
    nombre = VALUES(nombre),
    tipo = VALUES(tipo),
    unidad = VALUES(unidad),
    orden = VALUES(orden);

-- Rollback:
-- DROP TABLE IF EXISTS papaya_semana_stock_real;
-- DROP TABLE IF EXISTS papaya_dia_despacho;
-- DROP TABLE IF EXISTS papaya_dia_transformacion;
-- DROP TABLE IF EXISTS papaya_dia_elaboracion;
-- DROP TABLE IF EXISTS papaya_dia_mp;
-- DROP TABLE IF EXISTS papaya_cierre_stock;
-- DROP TABLE IF EXISTS papaya_conceptos;


-- [2026-06-30] [IA] [fabrica_papaya.cierre_stock.tipo]
-- Motivo: Diferenciar Stock Inicial vs Ajuste; snapshot concreto al cierre de la fecha indicada.
-- Entorno probado: local
-- SQL:

ALTER TABLE papaya_cierre_stock
ADD COLUMN tipo ENUM('inicial', 'ajuste') NOT NULL DEFAULT 'inicial'
COMMENT 'inicial=arranque; ajuste=corrección inventario'
AFTER fecha;

UPDATE papaya_cierre_stock SET tipo = 'inicial' WHERE es_manual = 1;

-- Rollback:
-- ALTER TABLE papaya_cierre_stock DROP COLUMN tipo;


-- [2026-06-30] [IA] [fabrica_papaya.despacho_doc_destino]
-- Motivo: Despachos — N° documento y destino opcionales (captura AppSheet; histórico sin backfill).
-- Entorno probado: local
-- SQL:

ALTER TABLE papaya_dia_despacho
ADD COLUMN numero_doc VARCHAR(64) NULL DEFAULT NULL COMMENT 'N° documento despacho (opcional)' AFTER cantidad,
ADD COLUMN destino VARCHAR(255) NULL DEFAULT NULL COMMENT 'Destino / cliente (opcional)' AFTER numero_doc;

-- Rollback:
-- ALTER TABLE papaya_dia_despacho DROP COLUMN destino, DROP COLUMN numero_doc;


-- [2026-06-30] [IA] [fabrica_papaya.despacho_guia]
-- Motivo: Guía de despacho (cabecera) + líneas en papaya_dia_despacho (AppSheet).
--         Histórico importado queda con guia_id NULL.
-- Entorno probado: local
-- SQL:

CREATE TABLE IF NOT EXISTS papaya_despacho_guia (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fecha DATE NOT NULL,
    anio SMALLINT NOT NULL,
    semana_iso TINYINT UNSIGNED NOT NULL,
    numero_doc VARCHAR(64) NULL DEFAULT NULL COMMENT 'N° guía / documento (opcional)',
    destino VARCHAR(255) NULL DEFAULT NULL COMMENT 'Destino / cliente (opcional)',
    observaciones VARCHAR(500) NULL DEFAULT NULL,
    capturado_por VARCHAR(120) NULL DEFAULT NULL,
    creado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_papaya_guia_fecha (fecha),
    KEY idx_papaya_guia_semana (anio, semana_iso),
    KEY idx_papaya_guia_numero (numero_doc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE papaya_dia_despacho
ADD COLUMN guia_id INT NULL DEFAULT NULL COMMENT 'FK guía; NULL = histórico / línea suelta' AFTER semana_iso,
ADD KEY idx_papaya_despacho_guia (guia_id),
ADD CONSTRAINT fk_papaya_despacho_guia FOREIGN KEY (guia_id) REFERENCES papaya_despacho_guia (id) ON DELETE CASCADE;

-- Rollback:
-- ALTER TABLE papaya_dia_despacho DROP FOREIGN KEY fk_papaya_despacho_guia, DROP COLUMN guia_id;
-- DROP TABLE IF EXISTS papaya_despacho_guia;


-- [2026-07-11] [IA] [mail_pdf_inbox — bandeja PDF IMAP Arqueo]
-- Motivo: Casilla admin@datoshuente.com → listar/ver/descargar PDF (arqueos/resúmenes).
--         Independiente de DespachoWeb. Primera instancia: solo visualización.
-- Entorno probado: local
-- SQL:

CREATE TABLE IF NOT EXISTS mail_pdf_inbox (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    message_id VARCHAR(255) NOT NULL,
    from_addr VARCHAR(255) NULL DEFAULT NULL,
    subject VARCHAR(500) NULL DEFAULT NULL,
    received_at DATETIME NULL DEFAULT NULL,
    filename VARCHAR(255) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    stored_path VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending|ignored',
    error VARCHAR(500) NULL DEFAULT NULL,
    imap_uid VARCHAR(32) NULL DEFAULT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_mail_pdf_msg_sha (message_id, sha256),
    KEY idx_mail_pdf_status (status),
    KEY idx_mail_pdf_received (received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Rollback:
-- DROP TABLE IF EXISTS mail_pdf_inbox;


-- [2026-08-11] [IA] [FxR — Fondos por Rendir]
-- Motivo: Módulo nuevo rendición de gastos (comprobantes, líneas globales, aprobación, PDF Drive).
-- Entorno probado: local
-- SQL: las tablas también se crean al entrar a /fxr (asegurar_esquema_fxr). Este bloque es para prod explícito.

CREATE TABLE IF NOT EXISTS fxr_centro_costo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(40) NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_fxr_cc_codigo (codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fxr_tipo_gasto (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(40) NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_fxr_tg_codigo (codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fxr_rendicion (
    id INT AUTO_INCREMENT PRIMARY KEY,
    correlativo INT NULL,
    usuario_email VARCHAR(190) NOT NULL,
    nombre_snapshot VARCHAR(190) NOT NULL DEFAULT '',
    area VARCHAR(120) NOT NULL DEFAULT '',
    fecha_rendicion DATE NULL,
    tipo VARCHAR(60) NOT NULL DEFAULT 'RENDICION_DE_FONDO',
    estado VARCHAR(20) NOT NULL DEFAULT 'borrador',
    total INT NOT NULL DEFAULT 0,
    motivo_rechazo TEXT NULL,
    pdf_drive_id VARCHAR(120) NULL,
    pdf_url VARCHAR(500) NULL,
    preparada_at DATETIME NULL,
    aprobada_at DATETIME NULL,
    aprobada_por VARCHAR(190) NULL,
    rechazada_at DATETIME NULL,
    rechazada_por VARCHAR(190) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_fxr_correlativo (correlativo),
    KEY idx_fxr_rend_usuario (usuario_email),
    KEY idx_fxr_rend_estado (estado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fxr_comprobante (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_email VARCHAR(190) NOT NULL,
    rendicion_id INT NULL,
    archivo_local VARCHAR(500) NOT NULL,
    mime VARCHAR(120) NOT NULL DEFAULT 'application/octet-stream',
    num_paginas INT NOT NULL DEFAULT 1,
    estado_archivo VARCHAR(30) NOT NULL DEFAULT 'staging',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_fxr_comp_usuario (usuario_email),
    KEY idx_fxr_comp_rend (rendicion_id),
    CONSTRAINT fk_fxr_comp_rend FOREIGN KEY (rendicion_id)
        REFERENCES fxr_rendicion(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fxr_linea (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rendicion_id INT NOT NULL,
    comprobante_id INT NOT NULL,
    orden INT NOT NULL DEFAULT 0,
    tipo_doc VARCHAR(20) NOT NULL DEFAULT 'otro',
    n_doc VARCHAR(80) NULL,
    n_doc_norm VARCHAR(80) NULL,
    fecha_comprobante DATE NULL,
    concepto VARCHAR(255) NOT NULL DEFAULT '',
    tipo_gasto_id INT NULL,
    centro_costo_id INT NULL,
    monto INT NOT NULL DEFAULT 0,
    observaciones TEXT NULL,
    duplicado_n_doc TINYINT(1) NOT NULL DEFAULT 0,
    duplicado_autorizado TINYINT(1) NOT NULL DEFAULT 0,
    duplicado_autorizado_por VARCHAR(190) NULL,
    duplicado_autorizado_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_fxr_linea_rend (rendicion_id),
    KEY idx_fxr_linea_ndoc (tipo_doc, n_doc_norm),
    KEY idx_fxr_linea_comp (comprobante_id),
    CONSTRAINT fk_fxr_linea_rend FOREIGN KEY (rendicion_id)
        REFERENCES fxr_rendicion(id) ON DELETE CASCADE,
    CONSTRAINT fk_fxr_linea_comp FOREIGN KEY (comprobante_id)
        REFERENCES fxr_comprobante(id) ON DELETE RESTRICT,
    CONSTRAINT fk_fxr_linea_tg FOREIGN KEY (tipo_gasto_id)
        REFERENCES fxr_tipo_gasto(id) ON DELETE SET NULL,
    CONSTRAINT fk_fxr_linea_cc FOREIGN KEY (centro_costo_id)
        REFERENCES fxr_centro_costo(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fxr_estado_hist (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rendicion_id INT NOT NULL,
    estado_desde VARCHAR(20) NULL,
    estado_hasta VARCHAR(20) NOT NULL,
    usuario_email VARCHAR(190) NOT NULL,
    nota VARCHAR(500) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_fxr_hist_rend (rendicion_id),
    CONSTRAINT fk_fxr_hist_rend FOREIGN KEY (rendicion_id)
        REFERENCES fxr_rendicion(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO fxr_tipo_gasto (codigo, nombre, activo) VALUES
 ('estacionamiento','Estacionamiento',1),
 ('peaje','Peaje',1),
 ('viatico','Viático',1),
 ('otro','Otro',1);

INSERT IGNORE INTO fxr_centro_costo (codigo, nombre, activo) VALUES
 ('ADM','Administración',1),
 ('OPE','Operaciones',1),
 ('COM','Comercial',1);

-- Rollback:
-- DROP TABLE IF EXISTS fxr_estado_hist;
-- DROP TABLE IF EXISTS fxr_linea;
-- DROP TABLE IF EXISTS fxr_comprobante;
-- DROP TABLE IF EXISTS fxr_rendicion;
-- DROP TABLE IF EXISTS fxr_tipo_gasto;
-- DROP TABLE IF EXISTS fxr_centro_costo;


-- [2026-08-11] [IA] [FxR — agrupar + layout collage]
-- Motivo: permite_agrupar en tipo_gasto; layout_json en rendicion para collage de imágenes.
-- Nota: sin IF NOT EXISTS (MySQL/MariaDB de cPanel no lo soporta). Si la columna ya existe, omitir esa línea.
-- SQL:
ALTER TABLE fxr_tipo_gasto ADD COLUMN permite_agrupar TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE fxr_rendicion ADD COLUMN layout_json MEDIUMTEXT NULL;
UPDATE fxr_tipo_gasto SET permite_agrupar=1 WHERE codigo IN ('peaje','estacionamiento');
-- Rollback:
-- ALTER TABLE fxr_tipo_gasto DROP COLUMN permite_agrupar;
-- ALTER TABLE fxr_rendicion DROP COLUMN layout_json;


-- [2026-08-11] [IA] [FxR — comentario/firma + perfil usuario]
-- Motivo: comentario bajo el total en PDF; nombre legible y CC por defecto en usuarios_huente.
-- Entorno probado: local
-- SQL: (MySQL sin IF NOT EXISTS en ADD COLUMN: omitir si la columna ya existe)

ALTER TABLE fxr_rendicion ADD COLUMN comentario_firma TEXT NULL;
ALTER TABLE usuarios_huente ADD COLUMN nombre VARCHAR(190) NULL;
ALTER TABLE usuarios_huente ADD COLUMN fxr_centro_costo_id INT NULL;

-- Opcional FK (solo si quieres integridad referencial):
-- ALTER TABLE usuarios_huente
--   ADD CONSTRAINT fk_usuarios_fxr_cc
--   FOREIGN KEY (fxr_centro_costo_id) REFERENCES fxr_centro_costo(id) ON DELETE SET NULL;

-- Rollback:
-- ALTER TABLE fxr_rendicion DROP COLUMN comentario_firma;
-- ALTER TABLE usuarios_huente DROP COLUMN fxr_centro_costo_id;
-- ALTER TABLE usuarios_huente DROP COLUMN nombre;

