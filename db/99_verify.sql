-- =====================================================================
-- 99_verify.sql  ·  Verificación automática del sistema odontológico
-- Uso:  psql -d odonto -f 99_verify.sql
-- Salida: tabla de checks con estado PASS/FAIL y un resumen final.
-- Este script es de solo lectura: no modifica datos.
-- =====================================================================
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
('C-01','estructura','Tablas base del dominio en public','40',
 -- alembic_version queda fuera: es infraestructura de migraciones, no del
 -- modelo clínico, y sólo existe una vez que la API ancla el baseline.
 (SELECT count(*)::text FROM information_schema.tables
   WHERE table_schema='public' AND table_type='BASE TABLE'
     AND table_name <> 'alembic_version')),
('C-02','estructura','Vistas creadas','3',
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
   WHERE table_name='plan_item' AND column_name='total'));

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
('K-25','catalogos','Sistemas de implante','6',                   (SELECT count(*)::text FROM sistema_implante));

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
('D-13','demo','Citas','7',                        (SELECT count(*)::text FROM cita)),
('D-14','demo','Consultas','3',                    (SELECT count(*)::text FROM consulta)),
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
('D-26','demo','Consentimientos firmados','1',     (SELECT count(*)::text FROM consentimiento WHERE firmado_en IS NOT NULL)),
('D-27','demo','Facturas / ítems / pagos','3/7/4',
 (SELECT (SELECT count(*) FROM factura)::text || '/' || (SELECT count(*) FROM factura_item)::text || '/' || (SELECT count(*) FROM pago)::text));

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
('R-07','reglas','Balance pendiente del paciente 1','8925.00',
 (SELECT SUM(balance)::numeric(12,2)::text FROM v_estado_cuenta WHERE paciente_id=1)),
('R-08','reglas','Facturas con pagos que exceden el total','0',
 (SELECT count(*)::text FROM v_estado_cuenta WHERE balance < 0)),
('R-09','reglas','Factura marcada pagada con balance distinto de cero','0',
 (SELECT count(*)::text FROM v_estado_cuenta ec JOIN factura f ON f.id=ec.factura_id
   WHERE f.estado='pagada' AND ec.balance <> 0)),
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
    UNION ALL SELECT 1 FROM factura WHERE id > (SELECT last_value FROM factura_id_seq)) q));

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
