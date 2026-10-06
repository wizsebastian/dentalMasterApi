-- =====================================================================
-- 99_verify.sql  ·  Verificación automática del sistema odontológico
-- Uso:  psql -d odonto -f 99_verify.sql
-- Salida: tabla de checks con estado PASS/FAIL y un resumen final.
-- Este script es de solo lectura: no modifica datos.
-- Termina con error si alguna aserción falla o si no se evaluaron las 98.
-- =====================================================================
-- Cada bloque es un único INSERT: sin esto, una subconsulta rota se llevaría el
-- bloque entero y el resumen saldría en verde con menos filas.
\set ON_ERROR_STOP on
\pset border 2
\pset format aligned

CREATE TEMP TABLE _chk (
  id          TEXT PRIMARY KEY,
  bloque      TEXT,
  descripcion TEXT,
  esperado    TEXT,
  obtenido    TEXT
);

-- ---------------------------------------------------------------------
-- BLOQUE C · ESTRUCTURA DEL ESQUEMA
-- ---------------------------------------------------------------------
INSERT INTO _chk VALUES
('C-01','estructura','Tablas base del dominio en public','56',
 -- alembic_version queda fuera: es infraestructura de migraciones, no del
 -- modelo clínico, y sólo existe una vez que la API ancla el baseline.
 (SELECT count(*)::text FROM information_schema.tables
   WHERE table_schema='public' AND table_type='BASE TABLE'
     AND table_name <> 'alembic_version')),
('C-02','estructura','Vistas creadas','6',
 (SELECT count(*)::text FROM information_schema.views WHERE table_schema='public')),
('C-03','estructura','Tipos ENUM creados','13',
 (SELECT count(*)::text FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
   WHERE t.typtype='e' AND n.nspname='public')),
('C-04','estructura','Índice único parcial de odontograma vigente','1',
 (SELECT count(*)::text FROM pg_indexes
   WHERE schemaname='public' AND indexname='uq_odontograma_actual')),
('C-05','estructura','Claves foráneas declaradas (>= 60)',
 'true',
 (SELECT (count(*) >= 60)::text FROM information_schema.table_constraints
   WHERE constraint_schema='public' AND constraint_type='FOREIGN KEY')),
('C-06','estructura','Columna generada plan_item.total','ALWAYS',
 (SELECT COALESCE(MAX(is_generated),'NO') FROM information_schema.columns
   WHERE table_name='plan_item' AND column_name='total')),
('C-07','estructura','Columna generada procedimiento.total','ALWAYS',
 (SELECT COALESCE(MAX(is_generated),'NO') FROM information_schema.columns
   WHERE table_name='procedimiento' AND column_name='total')),
('C-08','estructura','Exclusiones de solape en cita (doctor y unidad)','2',
 (SELECT count(*)::text FROM pg_constraint
   WHERE conrelid='cita'::regclass AND contype='x'));

-- ---------------------------------------------------------------------
-- BLOQUE K · CATÁLOGOS MAESTROS
-- ---------------------------------------------------------------------
INSERT INTO _chk VALUES
('K-01','catalogos','Dientes cargados (FDI completo)','52',       (SELECT count(*)::text FROM diente)),
('K-02','catalogos','Dientes permanentes','32',                   (SELECT count(*)::text FROM diente WHERE denticion='permanente')),
('K-03','catalogos','Dientes temporales','20',                    (SELECT count(*)::text FROM diente WHERE denticion='temporal')),
('K-04','catalogos','Cuadrantes representados','8',               (SELECT count(DISTINCT cuadrante)::text FROM diente)),
('K-05','catalogos','Rango FDI permanentes 11-48','true',
 (SELECT (MIN(codigo_fdi)=11 AND MAX(codigo_fdi)=48)::text FROM diente WHERE denticion='permanente')),
('K-06','catalogos','Rango FDI temporales 51-85','true',
 (SELECT (MIN(codigo_fdi)=51 AND MAX(codigo_fdi)=85)::text FROM diente WHERE denticion='temporal')),
('K-07','catalogos','Notación universal 1-32 sin duplicados','32',
 (SELECT count(DISTINCT universal)::text FROM diente WHERE universal IS NOT NULL)),
('K-08','catalogos','Superficies dentales','6',                   (SELECT count(*)::text FROM superficie)),
('K-09','catalogos','Condiciones del odontograma','35',           (SELECT count(*)::text FROM condicion_dental)),
('K-10','catalogos','Condiciones patológicas','18',               (SELECT count(*)::text FROM condicion_dental WHERE patologico)),
('K-11','catalogos','Condiciones no patológicas (tratamientos)','17',
                                                                  (SELECT count(*)::text FROM condicion_dental WHERE NOT patologico)),
('K-12','catalogos','Categorías de servicio','11',                (SELECT count(*)::text FROM categoria_servicio)),
('K-13','catalogos','Servicios','47',                             (SELECT count(*)::text FROM servicio)),
('K-14','catalogos','Servicios que requieren diente','29',        (SELECT count(*)::text FROM servicio WHERE requiere_diente)),
('K-15','catalogos','Servicios que requieren superficie','6',     (SELECT count(*)::text FROM servicio WHERE requiere_superficie)),
('K-16','catalogos','Servicios marcados como implante','1',       (SELECT count(*)::text FROM servicio WHERE es_implante)),
('K-17','catalogos','Listas de precio','2',                       (SELECT count(*)::text FROM lista_precio)),
('K-18','catalogos','Precios cargados (47 x 2 listas)','94',      (SELECT count(*)::text FROM precio_servicio)),
('K-19','catalogos','Servicios sin precio en tarifa particular','0',
 (SELECT count(*)::text FROM servicio s
   WHERE NOT EXISTS (SELECT 1 FROM precio_servicio ps WHERE ps.servicio_id=s.id AND ps.lista_precio_id=1))),
('K-20','catalogos','Precios negativos','0',                      (SELECT count(*)::text FROM precio_servicio WHERE precio < 0)),
('K-21','catalogos','Especialidades','9',                         (SELECT count(*)::text FROM especialidad)),
('K-22','catalogos','Condiciones médicas','14',                   (SELECT count(*)::text FROM condicion_medica)),
('K-23','catalogos','Alergias','8',                               (SELECT count(*)::text FROM alergia)),
('K-24','catalogos','Aseguradoras','5',                           (SELECT count(*)::text FROM aseguradora)),
('K-25','catalogos','Sistemas de implante','6',                   (SELECT count(*)::text FROM sistema_implante)),
('K-26','catalogos','Plantillas de documento','6',                (SELECT count(*)::text FROM plantilla_documento)),
('K-27','catalogos','Plantillas con variables sin cerrar','0',
 (SELECT count(*)::text FROM plantilla_documento
   WHERE (length(cuerpo) - length(replace(cuerpo,'{{',''))) <> (length(cuerpo) - length(replace(cuerpo,'}}',''))))),
('K-28','catalogos','Categorías de gasto / de insumo','8/6',
 (SELECT (SELECT count(*) FROM categoria_gasto)::text || '/' || (SELECT count(*) FROM categoria_insumo)::text)),
('K-29','catalogos','Alergias a medicamentos sin palabras clave','0',
 (SELECT count(*)::text FROM alergia WHERE tipo='medicamento' AND cardinality(palabras_clave)=0));

-- ---------------------------------------------------------------------
-- BLOQUE D · DATOS DEMO
-- ---------------------------------------------------------------------
INSERT INTO _chk VALUES
('D-01','demo','Sedes','1',                        (SELECT count(*)::text FROM sede)),
('D-02','demo','Doctores','3',                     (SELECT count(*)::text FROM doctor)),
('D-03','demo','Relaciones doctor-especialidad','7',(SELECT count(*)::text FROM doctor_especialidad)),
('D-04','demo','Usuarios','5',                     (SELECT count(*)::text FROM usuario)),
('D-05','demo','Pacientes','4',                    (SELECT count(*)::text FROM paciente)),
('D-06','demo','Contactos de emergencia','4',      (SELECT count(*)::text FROM paciente_contacto)),
('D-07','demo','Seguros de paciente','2',          (SELECT count(*)::text FROM paciente_seguro)),
('D-08','demo','Fichas médicas','4',               (SELECT count(*)::text FROM ficha_medica)),
('D-09','demo','Pacientes sin ficha médica','0',
 (SELECT count(*)::text FROM paciente p WHERE NOT EXISTS (SELECT 1 FROM ficha_medica f WHERE f.paciente_id=p.id))),
('D-10','demo','Condiciones médicas asignadas','5',(SELECT count(*)::text FROM ficha_condicion)),
('D-11','demo','Alergias asignadas','3',           (SELECT count(*)::text FROM ficha_alergia)),
('D-12','demo','Medicamentos en uso','4',          (SELECT count(*)::text FROM ficha_medicamento)),
('D-13','demo','Citas','13',                       (SELECT count(*)::text FROM cita)),
('D-14','demo','Consultas','5',                    (SELECT count(*)::text FROM consulta)),
('D-15','demo','Odontogramas','3',                 (SELECT count(*)::text FROM odontograma)),
('D-16','demo','Odontogramas vigentes','3',        (SELECT count(*)::text FROM odontograma WHERE es_actual)),
('D-17','demo','Estados de pieza registrados','6', (SELECT count(*)::text FROM odontograma_diente)),
('D-18','demo','Hallazgos del odontograma','28',   (SELECT count(*)::text FROM odontograma_hallazgo)),
('D-19','demo','Planes de tratamiento','1',        (SELECT count(*)::text FROM plan_tratamiento)),
('D-20','demo','Ítems del plan','6',               (SELECT count(*)::text FROM plan_item)),
('D-21','demo','Procedimientos ejecutados','8',    (SELECT count(*)::text FROM procedimiento)),
('D-22','demo','Implantes','1',                    (SELECT count(*)::text FROM implante)),
('D-23','demo','Eventos de seguimiento de implante','4',(SELECT count(*)::text FROM implante_evento)),
('D-24','demo','Documentos clínicos','5',          (SELECT count(*)::text FROM documento_clinico)),
('D-25','demo','Prescripciones / ítems','1/3',
 (SELECT (SELECT count(*) FROM prescripcion)::text || '/' || (SELECT count(*) FROM prescripcion_item)::text)),
('D-26','demo','Consentimientos firmados','1',
 (SELECT count(*)::text FROM documento_emitido d
   WHERE d.tipo='consentimiento' AND EXISTS (SELECT 1 FROM firma f WHERE f.documento_emitido_id=d.id))),
('D-27','demo','Facturas / ítems / pagos / aplicaciones','3/7/5/5',
 (SELECT (SELECT count(*) FROM factura)::text || '/' || (SELECT count(*) FROM factura_item)::text || '/'
      || (SELECT count(*) FROM pago)::text || '/' || (SELECT count(*) FROM pago_aplicacion)::text)),
('D-28','demo','Unidades dentales','2',            (SELECT count(*)::text FROM unidad_dental)),
('D-29','demo','Insumos / movimientos de kárdex','5/8',
 (SELECT (SELECT count(*) FROM insumo)::text || '/' || (SELECT count(*) FROM movimiento_insumo)::text)),
('D-30','demo','Gastos / proveedores','3/1',
 (SELECT (SELECT count(*) FROM gasto)::text || '/' || (SELECT count(*) FROM proveedor)::text));

-- ---------------------------------------------------------------------
-- BLOQUE R · REGLAS DE NEGOCIO Y CONSISTENCIA
-- ---------------------------------------------------------------------
INSERT INTO _chk VALUES
('R-01','reglas','Pacientes con más de un odontograma vigente','0',
 (SELECT count(*)::text FROM (SELECT paciente_id FROM odontograma WHERE es_actual GROUP BY 1 HAVING count(*)>1) q)),
('R-02','reglas','Hallazgos en piezas marcadas como ausentes con tratamiento activo','0',
 (SELECT count(*)::text FROM odontograma_hallazgo h
   JOIN odontograma_diente od ON od.odontograma_id=h.odontograma_id AND od.codigo_fdi=h.codigo_fdi
   JOIN condicion_dental cd ON cd.id=h.condicion_dental_id
   WHERE od.presente=FALSE AND h.estado='completado' AND cd.codigo IN ('RES','AMAL','SELL'))),
('R-03','reglas','Total del plan PT-2026-0001','109400.00',
 (SELECT SUM(total)::numeric(12,2)::text FROM plan_item WHERE plan_id=1)),
('R-04','reglas','Total del plan con 5% de descuento','103930.00',
 (SELECT (SUM(pi.total)*(1-pt.descuento_pct/100))::numeric(12,2)::text
    FROM plan_item pi JOIN plan_tratamiento pt ON pt.id=pi.plan_id
   WHERE pt.codigo='PT-2026-0001' GROUP BY pt.descuento_pct)),
('R-05','reglas','Total fase 1 del plan','6400.00',
 (SELECT SUM(total)::numeric(12,2)::text FROM plan_item WHERE plan_id=1 AND fase=1)),
('R-06','reglas','Facturas cuyo total no cuadra con sus ítems','0',
 (SELECT count(*)::text FROM (
    SELECT f.id FROM factura f JOIN factura_item fi ON fi.factura_id=f.id
    GROUP BY f.id, f.total HAVING SUM(fi.total)::numeric(12,2) <> f.total) q)),
('R-07','reglas','Balance pendiente del paciente 1','14925.00',
 (SELECT balance::numeric(12,2)::text FROM v_estado_cuenta WHERE paciente_id=1)),
('R-08','reglas','Aplicaciones que exceden su pago o su consulta','0',
 (SELECT ((SELECT count(*) FROM (SELECT pg.id FROM pago pg JOIN pago_aplicacion a ON a.pago_id=pg.id
                                  GROUP BY pg.id, pg.monto HAVING SUM(a.monto) > pg.monto) q)
        + (SELECT count(*) FROM v_saldo_consulta WHERE saldo < 0))::text)),
('R-09','reglas','Pacientes cuyo saldo por consulta no concilia con el balance','0',
 (SELECT count(*)::text FROM v_estado_cuenta ec
   WHERE ec.balance <> COALESCE((SELECT SUM(sc.saldo) FROM v_saldo_consulta sc
                                  WHERE sc.paciente_id=ec.paciente_id),0) - ec.credito_sin_aplicar)),
('R-10','reglas','Alertas clínicas activas (alto riesgo + alergias)','7',
 (SELECT count(*)::text FROM v_alertas_paciente)),
('R-11','reglas','Alertas del paciente 4 (anticoagulado)','4',
 (SELECT count(*)::text FROM v_alertas_paciente WHERE paciente_id=4)),
('R-12','reglas','Alergia a penicilina registrada en paciente 1','1',
 (SELECT count(*)::text FROM ficha_medica fm
    JOIN ficha_alergia fa ON fa.ficha_id=fm.id JOIN alergia a ON a.id=fa.alergia_id
   WHERE fm.paciente_id=1 AND a.codigo='PENI')),
('R-13','reglas','Trazabilidad: pacientes con implante del lote LT-2026-A4179','1',
 (SELECT count(DISTINCT paciente_id)::text FROM implante WHERE lote='LT-2026-A4179')),
('R-14','reglas','Implantes sin lote registrado','0',
 (SELECT count(*)::text FROM implante WHERE lote IS NULL OR lote='')),
('R-15','reglas','Implante 36 del paciente 1 oseointegrado','oseointegrado',
 (SELECT estado::text FROM implante WHERE paciente_id=1 AND codigo_fdi=36)),
('R-16','reglas','Filas del odontograma vigente del paciente 1','11',
 (SELECT count(*)::text FROM v_odontograma_actual WHERE paciente_id=1)),
('R-17','reglas','Tratamientos planificados pendientes en todos los pacientes','7',
 (SELECT count(*)::text FROM odontograma_hallazgo h
    JOIN odontograma o ON o.id=h.odontograma_id AND o.es_actual
   WHERE h.estado='planificado')),
('R-18','reglas','Procedimientos sin precio','0',
 (SELECT count(*)::text FROM procedimiento WHERE precio IS NULL OR precio <= 0)),
('R-19','reglas','Producción del doctor 2 en abril 2026','51500.00',
 (SELECT COALESCE(SUM(precio),0)::numeric(12,2)::text FROM procedimiento
   WHERE doctor_id=2 AND estado='completado' AND fecha BETWEEN '2026-04-01' AND '2026-04-30')),
('R-20','reglas','Citas con hora fin anterior al inicio','0',
 (SELECT count(*)::text FROM cita WHERE fin <= inicio)),
('R-21','reglas','Secuencias desincronizadas (id máximo > nextval)','0',
 (SELECT count(*)::text FROM (
    SELECT 1 FROM paciente WHERE id > (SELECT last_value FROM paciente_id_seq)
    UNION ALL SELECT 1 FROM doctor WHERE id > (SELECT last_value FROM doctor_id_seq)
    UNION ALL SELECT 1 FROM factura WHERE id > (SELECT last_value FROM factura_id_seq)
    UNION ALL SELECT 1 FROM pago WHERE id > (SELECT last_value FROM pago_id_seq)) q)),
('R-22','reglas','Correlativos por detrás de lo ya emitido','0',
 (SELECT count(*)::text FROM (
    SELECT 1 WHERE COALESCE((SELECT ultimo FROM correlativo WHERE clave='recibo'),0)
                 < COALESCE((SELECT MAX(numero_recibo) FROM pago),0)
    UNION ALL
    SELECT 1 WHERE COALESCE((SELECT ultimo FROM correlativo WHERE clave='paciente:2026'),0)
                 < COALESCE((SELECT MAX(split_part(codigo,'-',3)::int) FROM paciente WHERE codigo LIKE 'PAC-2026-%'),0)
    UNION ALL
    SELECT 1 WHERE COALESCE((SELECT ultimo FROM correlativo WHERE clave='plan:2026'),0)
                 < COALESCE((SELECT MAX(split_part(codigo,'-',3)::int) FROM plan_tratamiento WHERE codigo LIKE 'PT-2026-%'),0)) q)),
('R-23','reglas','Huecos en la numeración de recibos','0',
 (SELECT (COALESCE(MAX(numero_recibo),0) - count(*))::text FROM pago)),
('R-24','reglas','Saldo de la consulta 2 (implante, abonada)','8925.00',
 (SELECT saldo::numeric(12,2)::text FROM v_saldo_consulta WHERE consulta_id=2)),
('R-25','reglas','Balance del paciente 2 (su único pago está anulado)','0.00',
 (SELECT balance::numeric(12,2)::text FROM v_estado_cuenta WHERE paciente_id=2)),
('R-26','reglas','Citas vivas solapadas por doctor sin sobrecupo','0',
 (SELECT count(*)::text FROM cita a JOIN cita b
     ON a.id < b.id AND a.doctor_id = b.doctor_id
    AND tstzrange(a.inicio,a.fin,'[)') && tstzrange(b.inicio,b.fin,'[)')
  WHERE a.estado NOT IN ('cancelada','no_asistio') AND b.estado NOT IN ('cancelada','no_asistio')
    AND NOT a.sobrecupo AND NOT b.sobrecupo)),
('R-27','reglas','Firmas cuyo hash no es el del documento que firman','0',
 (SELECT count(*)::text FROM firma f JOIN documento_emitido d ON d.id=f.documento_emitido_id
   WHERE f.hash_documento <> d.sha256 OR d.sha256 <> encode(digest(d.cuerpo,'sha256'),'hex'))),
('R-28','reglas','Existencia de resina A2 (suma del kárdex)','3.000',
 (SELECT existencia::text FROM v_existencia_insumo WHERE insumo_id=1)),
('R-29','reglas','Insumos en su mínimo o por debajo','1',
 (SELECT count(*)::text FROM v_existencia_insumo WHERE bajo_minimo)),
('R-30','reglas','Costo en insumos de REST-001, según su receta','425.00',
 (SELECT cs.costo_insumos::text FROM v_costo_servicio cs JOIN servicio s ON s.id=cs.servicio_id
   WHERE s.codigo='REST-001')),
('R-31','reglas','Gastos de septiembre 2026, sin anulados','72650.00',
 (SELECT COALESCE(SUM(monto),0)::numeric(12,2)::text FROM gasto
   WHERE anulado_en IS NULL AND fecha BETWEEN '2026-09-01' AND '2026-09-30')),
('R-32','reglas','Líneas facturadas en más de un comprobante vivo','0',
 (SELECT count(*)::text FROM (
    SELECT fi.procedimiento_id FROM factura_item fi JOIN factura f ON f.id=fi.factura_id
     WHERE f.estado <> 'anulada' AND fi.procedimiento_id IS NOT NULL
     GROUP BY fi.procedimiento_id HAVING count(*) > 1) q)),
('R-33','reglas','Secuencias de NCF por detrás de lo ya emitido','0',
 (SELECT count(*)::text FROM secuencia_ncf s
   WHERE s.activo AND s.siguiente <= COALESCE(
     (SELECT MAX(substr(f.numero,4)::bigint) FROM factura f WHERE left(f.numero,3) = s.tipo), 0))),
('R-34','reglas','La sede de la demo tiene cerrada la guía de primeros pasos','1',
 (SELECT count(*)::text FROM sede
   WHERE onboarding_cerrado_en IS NOT NULL AND catalogo_revisado_en IS NOT NULL));

-- ---------------------------------------------------------------------
-- REPORTE
-- ---------------------------------------------------------------------
\echo '=================== RESULTADO DE LA VERIFICACIÓN ==================='
SELECT id, descripcion, esperado, COALESCE(obtenido,'(null)') AS obtenido,
       CASE WHEN esperado IS NOT DISTINCT FROM obtenido THEN 'PASS' ELSE '>>> FAIL' END AS estado
FROM _chk ORDER BY id;

\echo '=========================== RESUMEN ==============================='
SELECT bloque,
       count(*) FILTER (WHERE esperado IS NOT DISTINCT FROM obtenido) AS pass,
       count(*) FILTER (WHERE esperado IS DISTINCT FROM obtenido)     AS fail,
       count(*) AS total
FROM _chk GROUP BY bloque
UNION ALL
SELECT 'TOTAL',
       count(*) FILTER (WHERE esperado IS NOT DISTINCT FROM obtenido),
       count(*) FILTER (WHERE esperado IS DISTINCT FROM obtenido),
       count(*)
FROM _chk;

\echo '--- Fallos detectados (vacío = verificación 100% correcta) ---'
SELECT id, descripcion, esperado, obtenido FROM _chk
WHERE esperado IS DISTINCT FROM obtenido ORDER BY id;

-- El script falla (código de salida distinto de cero) si algo no pasó o si
-- faltan aserciones: quien lo invoque no necesita leer la tabla.
DO $$
DECLARE fallos INT; total INT;
BEGIN
  SELECT count(*) FILTER (WHERE esperado IS DISTINCT FROM obtenido), count(*)
    INTO fallos, total FROM _chk;
  IF fallos > 0 OR total <> 101 THEN
    RAISE EXCEPTION 'Verificación fallida: % FAIL de % aserciones (se esperaban 101)', fallos, total;
  END IF;
END $$;
