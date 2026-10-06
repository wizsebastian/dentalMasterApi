-- =====================================================================
-- 03_seed_demo.sql  ·  Datos de demostración / desarrollo
-- Requiere 01_schema.sql y 02_seed_catalogos.sql
-- =====================================================================

-- ---------------------------------------------------------------------
-- SEDE
-- ---------------------------------------------------------------------
INSERT INTO sede (id, nombre, direccion, ciudad, telefono, whatsapp, email, web, rnc) VALUES
 (1,'Clínica Dental Sonrisa','Av. Winston Churchill #45, Piantini','Santo Domingo','(809) 555-0100','(809) 555-0101','info@dentalsonrisa.do','www.dentalsonrisa.do','1-31-00000-1');

-- La demo ya está configurada: no arranca con la guía de primeros pasos.
UPDATE sede SET onboarding_cerrado_en = now(), catalogo_revisado_en = now();

INSERT INTO unidad_dental (id, sede_id, nombre, alquilada, orden) VALUES
 (1,1,'Unidad 1',FALSE,1),
 (2,1,'Unidad 2',TRUE,2);

-- ---------------------------------------------------------------------
-- DOCTORES
-- ---------------------------------------------------------------------
INSERT INTO doctor (id, sede_id, documento, nombres, apellidos, licencia, email, telefono, fecha_ingreso, porcentaje_comision) VALUES
 (1,1,'001-1234567-1','Laura','Fernández Cruz','EXQ-10245','laura.fernandez@dentalsonrisa.do','(809) 555-0111','2019-02-01',40.00),
 (2,1,'001-2345678-2','Miguel Antonio','Reyes Peralta','EXQ-11890','miguel.reyes@dentalsonrisa.do','(809) 555-0112','2020-06-15',45.00),
 (3,1,'001-3456789-3','Carolina','Batista Núñez','EXQ-12733','carolina.batista@dentalsonrisa.do','(809) 555-0113','2022-01-10',40.00);

INSERT INTO doctor_especialidad (doctor_id, especialidad_id, principal)
SELECT d.id, e.id, v.principal
FROM (VALUES (1,'GEN',TRUE),(1,'EST',FALSE),
             (2,'IMPL',TRUE),(2,'CIR',FALSE),(2,'PROT',FALSE),
             (3,'ODP',TRUE),(3,'ORTO',FALSE)) AS v(doc,esp,principal)
JOIN doctor d ON d.id = v.doc
JOIN especialidad e ON e.codigo = v.esp;

INSERT INTO usuario (id, doctor_id, email, password_hash, rol) VALUES
 (1,NULL,'admin@dentalsonrisa.do','$2b$12$CAMBIAR_ESTE_HASH_EN_PRODUCCION','admin'),
 (2,1,'laura.fernandez@dentalsonrisa.do','$2b$12$CAMBIAR_ESTE_HASH_EN_PRODUCCION','doctor'),
 (3,2,'miguel.reyes@dentalsonrisa.do','$2b$12$CAMBIAR_ESTE_HASH_EN_PRODUCCION','doctor'),
 (4,3,'carolina.batista@dentalsonrisa.do','$2b$12$CAMBIAR_ESTE_HASH_EN_PRODUCCION','doctor'),
 (5,NULL,'recepcion@dentalsonrisa.do','$2b$12$CAMBIAR_ESTE_HASH_EN_PRODUCCION','recepcion');

-- ---------------------------------------------------------------------
-- PACIENTES
-- ---------------------------------------------------------------------
INSERT INTO paciente (id, codigo, documento, nombres, apellidos, fecha_nacimiento, sexo, celular, email, direccion, ciudad, ocupacion, tipo_sangre, referido_por, sede_id) VALUES
 (1,'PAC-2026-0001','402-1112223-4','Juan Carlos','Peña Rosario','1985-03-12','M','(809) 777-0001','jc.pena@example.com','C/ Los Robles #12, Naco','Santo Domingo','Ingeniero civil','O+','Google',1),
 (2,'PAC-2026-0002','402-2223334-5','María Altagracia','Gómez Lantigua','1992-07-25','F','(809) 777-0002','maria.gomez@example.com','Av. Independencia #340','Santo Domingo','Contadora','A+','Paciente PAC-2026-0001',1),
 (3,'PAC-2026-0003',NULL,'Sofía Nicole','Martínez Gómez','2018-05-09','F','(809) 777-0003',NULL,'Av. Independencia #340','Santo Domingo',NULL,'A+','Madre: María Gómez',1),
 (4,'PAC-2026-0004','001-9998887-6','Rafael','Ureña Santos','1968-11-02','M','(809) 777-0004','r.urena@example.com','C/ Duarte #88, Villa Mella','Santo Domingo','Comerciante','B+','Referido médico',1);

INSERT INTO paciente_contacto (paciente_id, nombre, parentesco, telefono, es_emergencia, es_tutor) VALUES
 (1,'Ana Rosario','Esposa','(809) 777-1001',TRUE,FALSE),
 (2,'Pedro Gómez','Hermano','(809) 777-1002',TRUE,FALSE),
 (3,'María Altagracia Gómez','Madre','(809) 777-0002',TRUE,TRUE),
 (4,'Yolanda Santos','Hija','(809) 777-1004',TRUE,FALSE);

INSERT INTO paciente_seguro (paciente_id, aseguradora_id, poliza, plan, titular, vigente_desde, principal) VALUES
 (1,(SELECT id FROM aseguradora WHERE codigo='ARS01'),'HUM-884512','Plan Complementario','Juan Carlos Peña','2024-01-01',TRUE),
 (4,(SELECT id FROM aseguradora WHERE codigo='ARS04'),'SNS-220147','Régimen Contributivo','Rafael Ureña','2018-05-01',TRUE);

-- ---------------------------------------------------------------------
-- FICHAS MÉDICAS
-- ---------------------------------------------------------------------
INSERT INTO ficha_medica (id, paciente_id, motivo_consulta, enfermedad_actual, antecedentes_familiares,
                          fuma, cigarrillos_dia, consume_alcohol, bruxismo, ultima_visita_dental,
                          cepillados_dia, usa_hilo_dental, sangrado_encias, sensibilidad, dolor_atm,
                          embarazada, anticoagulantes, bifosfonatos, observaciones, actualizado_por) VALUES
 (1,1,'Ausencia de molar inferior izquierdo y sensibilidad al masticar',
    'Pieza 36 extraída hace 2 años. Refiere dificultad para masticar del lado izquierdo.',
    'Padre diabético tipo 2',
    FALSE,NULL,TRUE,TRUE,'2024-08-10',2,FALSE,TRUE,TRUE,FALSE,FALSE,FALSE,FALSE,
    'Diabético controlado con metformina. HbA1c 6.4% (feb 2026). Apto para cirugía de implante.',1),
 (2,2,'Limpieza y manchas en dientes anteriores',
    'Embarazo de 22 semanas. Sangrado gingival desde el segundo trimestre.',
    'Madre con enfermedad periodontal',
    FALSE,NULL,FALSE,FALSE,'2025-11-03',2,TRUE,TRUE,FALSE,FALSE,TRUE,FALSE,FALSE,
    'Gingivitis del embarazo. Evitar radiografías. Posponer tratamientos electivos al posparto.',1),
 (3,3,'Chequeo y dolor al comer dulces',
    'Madre refiere molestia en molares superiores derechos.',
    NULL,
    FALSE,NULL,FALSE,FALSE,'2025-06-20',1,FALSE,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE,
    'Paciente pediátrica, dentición mixta. Alta ingesta de azúcares. Requiere manejo de conducta.',3),
 (4,4,'Prótesis floja y encías sangrantes',
    'Usa prótesis parcial superior desde 2019. Refiere movilidad en piezas anteroinferiores.',
    'Hipertensión familiar',
    TRUE,10,TRUE,FALSE,'2023-02-15',1,FALSE,TRUE,FALSE,FALSE,FALSE,TRUE,FALSE,
    'ALERTA: warfarina 5mg. Solicitar INR (<3.0) 24h antes de cualquier exodoncia. PA de control 145/90.',2);

INSERT INTO ficha_condicion (ficha_id, condicion_medica_id, diagnosticado_en, controlado, detalle)
SELECT v.ficha, cm.id, v.dx::date, v.ctrl, v.detalle
FROM (VALUES
 (1,'DM','2018-04-01',TRUE,'Metformina 850mg 2 veces al día. HbA1c 6.4%'),
 (2,'EMB','2026-04-20',TRUE,'22 semanas de gestación'),
 (4,'HTA','2010-09-15',TRUE,'Losartán 50mg diario'),
 (4,'CARD','2019-03-08',TRUE,'Fibrilación auricular, en anticoagulación'),
 (4,'ANTICOAG','2019-03-08',TRUE,'Warfarina 5mg. Requiere INR previo a cirugía')
) AS v(ficha,cod,dx,ctrl,detalle)
JOIN condicion_medica cm ON cm.codigo = v.cod;

INSERT INTO ficha_alergia (ficha_id, alergia_id, severidad, reaccion)
SELECT v.ficha, a.id, v.sev, v.reaccion
FROM (VALUES
 (1,'PENI','severa','Urticaria y edema facial'),
 (2,'LATEX','moderada','Dermatitis de contacto'),
 (4,'AINE','moderada','Gastritis y broncoespasmo leve')
) AS v(ficha,cod,sev,reaccion)
JOIN alergia a ON a.codigo = v.cod;

INSERT INTO ficha_medicamento (ficha_id, nombre, dosis, frecuencia, motivo, desde) VALUES
 (1,'Metformina','850 mg','2 veces al día','Diabetes tipo 2','2018-04-01'),
 (2,'Ácido fólico','5 mg','1 vez al día','Embarazo','2026-01-15'),
 (4,'Warfarina','5 mg','1 vez al día','Fibrilación auricular','2019-03-08'),
 (4,'Losartán','50 mg','1 vez al día','Hipertensión','2010-09-15');

-- ---------------------------------------------------------------------
-- CITAS
-- ---------------------------------------------------------------------
INSERT INTO cita (id, paciente_id, doctor_id, sede_id, inicio, fin, motivo, estado) VALUES
 (1,1,1,1,'2026-03-02 09:00-04','2026-03-02 09:30-04','Evaluación inicial','atendida'),
 (2,1,2,1,'2026-04-15 10:00-04','2026-04-15 11:30-04','Colocación de implante 36','atendida'),
 (3,1,2,1,'2026-08-12 10:00-04','2026-08-12 10:30-04','Segunda fase quirúrgica','atendida'),
 (4,1,2,1,'2026-09-18 11:00-04','2026-09-18 12:00-04','Toma de impresión corona sobre implante','confirmada'),
 (5,2,1,1,'2026-05-06 15:00-04','2026-05-06 15:45-04','Profilaxis','cancelada'),
 (6,3,3,1,'2026-06-11 08:30-04','2026-06-11 09:10-04','Chequeo pediátrico','atendida'),
 (7,4,2,1,'2026-09-22 14:00-04','2026-09-22 15:00-04','Evaluación de prótesis','agendada');

-- Agenda de hoy y de mañana, relativa al día en que se carga el seed: así el
-- tablero «Hoy» no arranca vacío. El día se toma en la hora de la clínica, no en
-- la del servidor (UTC), que por la noche ya es el día siguiente.
INSERT INTO cita (id, paciente_id, doctor_id, sede_id, unidad_id, inicio, fin, motivo, estado)
SELECT v.id, v.pac, v.doc, 1, v.unidad,
       (hoy.dia + v.dias + v.desde::time) AT TIME ZONE 'America/Santo_Domingo',
       (hoy.dia + v.dias + v.hasta::time) AT TIME ZONE 'America/Santo_Domingo',
       v.motivo, v.estado::estado_cita_t
FROM (SELECT (now() AT TIME ZONE 'America/Santo_Domingo')::date AS dia) hoy,
     (VALUES
       ( 8,2,1,1,   0,'09:00','09:40','Profilaxis','atendida'),
       ( 9,3,3,2,   0,'10:00','10:30','Control pediátrico','en_sala'),
       (10,4,2,1,   0,'11:00','12:00','Evaluación de prótesis','confirmada'),
       (11,2,1,2,   0,'15:00','15:30','Revisión de encías','agendada'),
       (12,4,2,NULL,0,'16:00','16:30','Control','cancelada'),
       (13,3,3,1,   1,'09:30','10:00','Sellantes','agendada')
     ) AS v(id,pac,doc,unidad,dias,desde,hasta,motivo,estado);

-- ---------------------------------------------------------------------
-- CONSULTAS
-- ---------------------------------------------------------------------
INSERT INTO consulta (id, paciente_id, doctor_id, cita_id, fecha, motivo,
                      presion_sistolica, presion_diastolica, pulso,
                      subjetivo, objetivo, diagnostico, plan) VALUES
 (1,1,1,1,'2026-03-02 09:05-04','Evaluación inicial',124,80,72,
  'Refiere dificultad para masticar del lado izquierdo y sensibilidad en molar superior derecho.',
  'Ausencia de 36. Caries oclusal en 16. Caries mesial en 11. 46 con tratamiento de conducto previo y restauración amplia.',
  'K02.1 Caries de la dentina · Edentulismo parcial (36)',
  'Radiografía panorámica, resina en 16 y 11, evaluación para implante en 36.'),
 (2,1,2,2,'2026-04-15 10:05-04','Cirugía de implante 36',128,82,76,
  'Paciente asintomático, acude en ayunas parciales según indicación.',
  'Reborde alveolar 36 con altura ósea 13mm, ancho 7.2mm según CBCT. Encía queratinizada adecuada.',
  'Edentulismo parcial unitario 36, apto para implante inmediato diferido',
  'Colocación de implante Straumann BLX 4.0x10mm. Amoxicilina contraindicada por alergia: clindamicina 300mg.'),
 (3,3,3,6,'2026-06-11 08:35-04','Chequeo pediátrico',NULL,NULL,96,
  'Madre refiere molestia al comer dulces.',
  'Caries oclusal en 54 y 74. Pieza 85 con caries profunda, sin sintomatología pulpar espontánea. Dentición mixta, 16 y 26 en erupción.',
  'Caries de la infancia temprana',
  'Sellantes en 16 y 26, resinas en 54 y 74, pulpotomía + corona de acero en 85. Flúor y control de dieta.');

-- Visitas de los procedimientos 3 (resina en 16) y 6 (segunda fase del implante).
INSERT INTO consulta (id, paciente_id, doctor_id, cita_id, fecha, motivo) VALUES
 (4,1,1,NULL,'2026-03-20 16:00-04','Resina en 16'),
 (5,1,2,3,'2026-08-12 10:05-04','Segunda fase quirúrgica');

-- ---------------------------------------------------------------------
-- ODONTOGRAMAS
-- ---------------------------------------------------------------------
INSERT INTO odontograma (id, paciente_id, doctor_id, consulta_id, version, denticion, fecha, es_actual, observaciones) VALUES
 (1,1,1,1,1,'permanente','2026-03-02',TRUE,'Odontograma inicial. Higiene regular, cálculo supragingival leve.'),
 (2,3,3,3,1,'temporal','2026-06-11',TRUE,'Dentición mixta: presentes 16 y 26 en erupción.'),
 (3,4,2,NULL,1,'permanente','2026-09-01',TRUE,'Edentulismo parcial superior, prótesis parcial removible desde 2019.');

-- Estado global de piezas relevantes (paciente 1)
INSERT INTO odontograma_diente (odontograma_id, codigo_fdi, presente, movilidad, sondaje_mm, sangrado, notas) VALUES
 (1,36,FALSE,NULL,NULL,FALSE,'Extraída en 2024 por caries extensa'),
 (1,16,TRUE,0,2.5,FALSE,NULL),
 (1,11,TRUE,0,2.0,FALSE,NULL),
 (1,46,TRUE,0,3.0,TRUE,'Endodoncia previa (2021), restauración amplia'),
 (1,18,FALSE,NULL,NULL,FALSE,'Ausente congénito'),
 (1,28,FALSE,NULL,NULL,FALSE,'Ausente congénito');

-- Hallazgos paciente 1
INSERT INTO odontograma_hallazgo (odontograma_id, codigo_fdi, superficie, condicion_dental_id, estado, doctor_id, fecha, notas)
SELECT v.odo, v.fdi, v.sup, cd.id, v.estado::estado_hallazgo_t, v.doc, v.fecha::date, v.notas
FROM (VALUES
 (1,36,NULL,'AUS_EXT','existente',1,'2026-03-02','Extraída 2024'),
 (1,36,NULL,'IMPL','planificado',2,'2026-03-02','Plan: implante unitario'),
 (1,16,'O','CAR','existente',1,'2026-03-02','Caries dentinaria moderada'),
 (1,16,'O','RES','completado',1,'2026-03-20','Resina 1 superficie'),
 (1,11,'M','CAR','existente',1,'2026-03-02',NULL),
 (1,11,'M','RES','planificado',1,'2026-03-02','Resina 2 superficies (M-I)'),
 (1,26,'O','AMAL','existente',1,'2026-03-02','Amalgama antigua en buen estado'),
 (1,46,NULL,'ENDO','existente',1,'2026-03-02','Tratamiento de conducto 2021'),
 (1,46,NULL,'COR_PFM','planificado',1,'2026-03-02','Indicada corona por riesgo de fractura'),
 (1,18,NULL,'AUS','existente',1,'2026-03-02',NULL),
 (1,28,NULL,'AUS','existente',1,'2026-03-02',NULL),
 -- paciente pediátrico
 (2,54,'O','CAR','existente',3,'2026-06-11',NULL),
 (2,74,'O','CAR','existente',3,'2026-06-11',NULL),
 (2,85,'O','CAR','existente',3,'2026-06-11','Caries profunda'),
 (2,85,NULL,'PULPO','planificado',3,'2026-06-11',NULL),
 (2,85,NULL,'COR_ACE','planificado',3,'2026-06-11',NULL),
 (2,16,NULL,'ERUP','existente',3,'2026-06-11',NULL),
 (2,26,NULL,'ERUP','existente',3,'2026-06-11',NULL),
 (2,16,'O','SELL','planificado',3,'2026-06-11',NULL),
 (2,26,'O','SELL','planificado',3,'2026-06-11',NULL),
 -- paciente 4
 (3,14,NULL,'AUS_EXT','existente',2,'2026-09-01',NULL),
 (3,15,NULL,'AUS_EXT','existente',2,'2026-09-01',NULL),
 (3,24,NULL,'AUS_EXT','existente',2,'2026-09-01',NULL),
 (3,26,NULL,'AUS_EXT','existente',2,'2026-09-01',NULL),
 (3,31,NULL,'MOVIL','existente',2,'2026-09-01','Movilidad grado II'),
 (3,41,NULL,'MOVIL','existente',2,'2026-09-01','Movilidad grado II'),
 (3,13,NULL,'PPR','existente',2,'2026-09-01','Retenedor de prótesis parcial'),
 (3,23,NULL,'PPR','existente',2,'2026-09-01','Retenedor de prótesis parcial')
) AS v(odo,fdi,sup,cond,estado,doc,fecha,notas)
JOIN condicion_dental cd ON cd.codigo = v.cond;

-- ---------------------------------------------------------------------
-- PLAN DE TRATAMIENTO (paciente 1)
-- ---------------------------------------------------------------------
INSERT INTO plan_tratamiento (id, paciente_id, doctor_id, lista_precio_id, codigo, fecha, estado, descuento_pct, notas) VALUES
 (1,1,2,1,'PT-2026-0001','2026-03-02','en_ejecucion',5.00,'Rehabilitación implantosoportada 36 + operatoria. Financiado en 3 pagos.');

INSERT INTO plan_item (id, plan_id, servicio_id, codigo_fdi, superficies, cantidad, precio_unit, descuento_pct, fase, prioridad, aprobado)
SELECT v.id, 1, s.id, v.fdi, v.sup, 1, ps.precio, 0, v.fase, v.prio, TRUE
FROM (VALUES
 (1,'REST-001',16,'O',1,1),
 (2,'REST-002',11,'MI',1,2),
 (3,'IMPL-001',36,NULL,2,1),
 (4,'IMPL-002',36,NULL,3,2),
 (5,'IMPL-003',36,NULL,3,2),
 (6,'PROT-001',46,NULL,3,3)
) AS v(id,cod,fdi,sup,fase,prio)
JOIN servicio s ON s.codigo = v.cod
JOIN precio_servicio ps ON ps.servicio_id = s.id AND ps.lista_precio_id = 1;

-- ---------------------------------------------------------------------
-- PROCEDIMIENTOS EJECUTADOS
-- ---------------------------------------------------------------------
INSERT INTO procedimiento (id, paciente_id, doctor_id, servicio_id, consulta_id, plan_item_id, codigo_fdi, superficies, fecha, estado, anestesia, materiales, precio, notas)
SELECT v.id, v.pac, v.doc, s.id, v.cons, v.item, v.fdi, v.sup, v.fecha::date, v.estado::estado_proc_t, v.anest, v.mat, v.precio, v.notas
FROM (VALUES
 (1,1,1,'DX-001',1,NULL,NULL,NULL,'2026-03-02','completado',NULL,NULL,1200,'Evaluación inicial y odontograma'),
 (2,1,1,'DX-003',1,NULL,NULL,NULL,'2026-03-02','completado',NULL,NULL,2500,'Panorámica de diagnóstico'),
 (3,1,1,'REST-001',4,1,16,'O','2026-03-20','completado','Lidocaína 2% c/epinefrina 1 carpule','Resina Z350 A2, adhesivo universal',2800,'Sin complicaciones'),
 (4,1,2,'DX-004',2,NULL,36,NULL,'2026-04-08','completado',NULL,NULL,6500,'CBCT sector 36 para planificación'),
 (5,1,2,'IMPL-001',2,3,36,NULL,'2026-04-15','completado','Lidocaína 2% c/epinefrina 2 carpules','Implante Straumann BLX 4.0x10, tornillo de cierre',45000,'Torque 35 Ncm, ISQ 72. Sutura 4-0. Profilaxis con clindamicina por alergia a penicilina.'),
 (6,1,2,'IMPL-006',5,NULL,36,NULL,'2026-08-12','completado','Lidocaína 2% 1 carpule','Tornillo de cicatrización 4.5mm',6000,'Segunda fase. ISQ 78. Cicatrización favorable.'),
 (7,3,3,'REST-001',3,NULL,54,'O','2026-06-11','completado','Anestesia tópica + infiltrativa','Ionómero de vidrio',2800,'Manejo de conducta con técnica decir-mostrar-hacer'),
 (8,3,3,'ODP-002',3,NULL,NULL,NULL,'2026-06-11','completado',NULL,'Barniz de flúor 5% NaF',1500,'Refuerzo de higiene con la madre')
) AS v(id,pac,doc,cod,cons,item,fdi,sup,fecha,estado,anest,mat,precio,notas)
JOIN servicio s ON s.codigo = v.cod;

-- El 5 % del plan PT-2026-0001 se copia a la línea al ejecutarla: así el cargo
-- no depende de un join al plan.
UPDATE procedimiento SET descuento_pct = 5 WHERE id IN (4,5);

-- El plan es la carpeta: las visitas del implante y la resina del plan cuelgan de él.
-- La consulta 1 (evaluación inicial) queda suelta a propósito.
UPDATE consulta SET plan_id = 1 WHERE id IN (2,4,5);

UPDATE paciente SET doctor_tratante_id = v.doc
FROM (VALUES (1,2),(2,1),(3,3),(4,2)) AS v(pac,doc) WHERE paciente.id = v.pac;

-- ---------------------------------------------------------------------
-- IMPLANTE + SEGUIMIENTO
-- ---------------------------------------------------------------------
INSERT INTO implante (id, paciente_id, doctor_id, procedimiento_id, sistema_implante_id, codigo_fdi,
                      referencia, lote, serie, diametro_mm, longitud_mm, plataforma, torque_ncm, isq,
                      injerto_oseo, material_injerto, membrana, fecha_colocacion, fecha_carga, estado, garantia_hasta, notas)
VALUES (1,1,2,5,(SELECT id FROM sistema_implante WHERE marca='Straumann' AND linea='BLX'),36,
        'BLX-040-10-RB','LT-2026-A4179','SN-88213',4.0,10.0,'Regular Base',35,72,
        TRUE,'Xenoinjerto bovino 0.5cc',TRUE,'2026-04-15',NULL,'oseointegrado','2036-04-15',
        'Regeneración ósea guiada por dehiscencia vestibular de 2mm. Carga diferida prevista para septiembre 2026.');

INSERT INTO implante_evento (implante_id, fecha, tipo, doctor_id, isq, hallazgos, notas) VALUES
 (1,'2026-04-15','colocacion',2,72,'Estabilidad primaria adecuada','Torque 35 Ncm'),
 (1,'2026-04-22','control',2,NULL,'Retiro de sutura, cicatrización favorable',NULL),
 (1,'2026-06-10','control',2,NULL,'Sin signos de inflamación. Rx sin radiolucidez periimplantaria.',NULL),
 (1,'2026-08-12','segunda_fase',2,78,'Oseointegración confirmada','Colocado tornillo de cicatrización');

-- ---------------------------------------------------------------------
-- DOCUMENTOS CLÍNICOS
-- ---------------------------------------------------------------------
INSERT INTO documento_clinico (paciente_id, consulta_id, tipo, codigo_fdi, titulo, url, mime, tomado_en) VALUES
 (1,1,'panoramica',NULL,'Panorámica inicial','/storage/pac/1/rx/pano-2026-03-02.jpg','image/jpeg','2026-03-02'),
 (1,2,'cbct',36,'CBCT sector posteroinferior izquierdo','/storage/pac/1/rx/cbct-2026-04-08.zip','application/zip','2026-04-08'),
 (1,NULL,'radiografia_periapical',36,'Periapical control post-quirúrgico','/storage/pac/1/rx/peri-36-2026-04-15.jpg','image/jpeg','2026-04-15'),
 (1,NULL,'radiografia_periapical',36,'Periapical control 4 meses','/storage/pac/1/rx/peri-36-2026-08-12.jpg','image/jpeg','2026-08-12'),
 (3,3,'foto',NULL,'Fotografía intraoral inicial','/storage/pac/3/fotos/intra-2026-06-11.jpg','image/jpeg','2026-06-11');

-- ---------------------------------------------------------------------
-- PRESCRIPCIONES Y CONSENTIMIENTOS
-- ---------------------------------------------------------------------
INSERT INTO prescripcion (id, paciente_id, doctor_id, consulta_id, fecha, indicaciones) VALUES
 (1,1,2,2,'2026-04-15','Dieta blanda 7 días. Frío local las primeras 24h. No fumar. No enjuagar el primer día. Control en 7 días.');

INSERT INTO prescripcion_item (prescripcion_id, medicamento, presentacion, dosis, frecuencia, duracion) VALUES
 (1,'Clindamicina','Cápsulas 300 mg','1 cápsula','Cada 8 horas','7 días'),
 (1,'Ibuprofeno','Tabletas 600 mg','1 tableta','Cada 8 horas','3 días'),
 (1,'Clorhexidina 0.12%','Enjuague bucal','15 ml','2 veces al día','14 días');

-- El consentimiento del implante: un documento emitido con su firma.
INSERT INTO documento_emitido (id, paciente_id, tipo, plantilla_id, titulo, cuerpo, plan_id, doctor_id,
                               requiere_firma, sha256, emitido_por, emitido_en)
SELECT 1, 1, 'consentimiento', pl.id, pl.titulo, t.cuerpo, 1, 2, TRUE,
       encode(digest(t.cuerpo, 'sha256'), 'hex'), 3, '2026-04-15 09:30-04'
FROM plantilla_documento pl,
     LATERAL (SELECT 'Yo, Juan Carlos Peña Rosario, portador de la cédula 402-1112223-4, autorizo a Miguel Antonio Reyes Peralta a colocarme un implante dental en la pieza 36. He sido informado de sus riesgos y alternativas.' AS cuerpo) t
WHERE pl.codigo = 'CONS-IMPLANTE';

INSERT INTO firma (documento_emitido_id, firmante_nombre, firmante_rol, firmante_documento, trazo,
                   hash_documento, firmado_en)
SELECT 1, 'Juan Carlos Peña Rosario', 'paciente', '402-1112223-4',
       '[[[12,40],[30,18],[46,44],[62,20],[80,42],[120,30]]]'::jsonb, d.sha256, '2026-04-15 09:40-04'
FROM documento_emitido d WHERE d.id = 1;

-- ---------------------------------------------------------------------
-- COMPROBANTES FISCALES, PAGOS Y APLICACIONES
-- ---------------------------------------------------------------------
INSERT INTO factura (id, paciente_id, sede_id, plan_id, numero, fecha, moneda, subtotal, descuento, impuesto, cubierto_seguro, total, estado) VALUES
 (1,1,1,1,'B0200000001','2026-03-20','DOP', 6500.00, 0.00, 0.00, 0.00, 6500.00,'emitida'),
 (2,1,1,1,'B0200000002','2026-04-15','DOP',51500.00,2575.00, 0.00, 0.00,48925.00,'emitida'),
 (3,3,1,NULL,'B0200000003','2026-06-11','DOP', 4300.00, 0.00, 0.00, 0.00, 4300.00,'emitida');

UPDATE factura SET tipo_ncf = 'B02';

-- Rangos de NCF de la demo: el de consumo ya gastó los tres de arriba.
INSERT INTO secuencia_ncf (tipo, desde, hasta, siguiente, vence) VALUES
 ('B02', 1, 500, 4, '2027-12-31'),
 ('B01', 1, 100, 1, '2027-12-31');

INSERT INTO factura_item (factura_id, procedimiento_id, servicio_id, descripcion, cantidad, precio_unit, descuento_pct, tasa_impuesto, total)
SELECT v.fac, v.proc, s.id, v.desc_, 1, v.precio, v.desc_pct, 0, ROUND(v.precio * (1 - v.desc_pct/100),2)
FROM (VALUES
 (1,1,'DX-001','Consulta y evaluación inicial',1200.00,0.00),
 (1,2,'DX-003','Radiografía panorámica',2500.00,0.00),
 (1,3,'REST-001','Resina 1 superficie · pieza 16 (O)',2800.00,0.00),
 (2,4,'DX-004','Tomografía CBCT · sector 36',6500.00,5.00),
 (2,5,'IMPL-001','Implante dental unitario · pieza 36',45000.00,5.00),
 (3,7,'REST-001','Resina 1 superficie · pieza 54 (O)',2800.00,0.00),
 (3,8,'ODP-002','Aplicación tópica de flúor',1500.00,0.00)
) AS v(fac,proc,cod,desc_,precio,desc_pct)
JOIN servicio s ON s.codigo = v.cod;

-- Los pagos son del paciente y llevan recibo correlativo. El 5 está anulado:
-- conserva su número y queda fuera de todo balance.
INSERT INTO pago (id, paciente_id, numero_recibo, fecha, metodo, monto, concepto, referencia, recibido_por,
                  anulado_en, anulado_por, motivo_anulacion) VALUES
 (1,1,1,'2026-03-20','tarjeta', 6500.00,'Evaluación, panorámica y resina','AUTH-448120',5,NULL,NULL,NULL),
 (2,1,2,'2026-04-15','transferencia',25000.00,'Abono implante 36','TRF-99120',5,NULL,NULL,NULL),
 (3,1,3,'2026-06-10','efectivo',15000.00,'Abono implante 36',NULL,5,NULL,NULL,NULL),
 (4,3,4,'2026-06-11','tarjeta', 4300.00,'Resina y flúor','AUTH-551903',5,NULL,NULL,NULL),
 (5,2,5,'2026-05-06','efectivo',  500.00,'Abono profilaxis',NULL,5,'2026-05-06 15:20-04',5,'Cita cancelada: se devolvió el abono');

-- A qué consulta se imputa cada pago. La consulta 2 queda con saldo 8 925,00 y la 5
-- (segunda fase, 6 000,00) sin abonar: el paciente 1 debe 14 925,00.
INSERT INTO pago_aplicacion (pago_id, consulta_id, paciente_id, monto) VALUES
 (1,1,1, 3700.00),
 (1,4,1, 2800.00),
 (2,2,1,25000.00),
 (3,2,1,15000.00),
 (4,3,3, 4300.00);

INSERT INTO correlativo (clave, ultimo) VALUES
 ('paciente:2026',4),
 ('plan:2026',1),
 ('recibo',5);

-- ---------------------------------------------------------------------
-- GASTOS E INVENTARIO
-- ---------------------------------------------------------------------
INSERT INTO proveedor (id, nombre, rnc, telefono) VALUES
 (1,'Depósito Dental del Caribe','1-01-55555-5','(809) 555-0300');

INSERT INTO insumo (id, nombre, categoria_id, marca, modelo, unidad, controla_stock, stock_minimo, costo, notas)
SELECT v.id, v.nombre, c.id, v.marca, v.modelo, v.unidad, v.stock, v.minimo, v.costo, v.notas
FROM (VALUES
 (1,'Resina compuesta A2','Restauración','3M','Filtek Z350 XT','jeringa 4g',TRUE,3,2200.00,NULL),
 (2,'Adhesivo universal','Restauración','3M','Single Bond Universal','frasco 5ml',TRUE,1,3200.00,NULL),
 (3,'Lidocaína 2% con epinefrina','Anestesia','Septodont','Lignospan','cartucho 1.8ml',TRUE,50,45.00,NULL),
 (4,'Guantes de nitrilo M','Descartables','Kimberly-Clark','Purple','caja 100',TRUE,3,550.00,NULL),
 (5,'Corona de zirconio (laboratorio)','Laboratorio externo',NULL,NULL,'servicio',FALSE,0,8500.00,'No lleva existencia: se paga por caso')
) AS v(id,nombre,cat,marca,modelo,unidad,stock,minimo,costo,notas)
JOIN categoria_insumo c ON c.nombre = v.cat;

-- Kárdex: existencia inicial, una compra y lo consumido. La resina queda en 3: justo en su mínimo.
INSERT INTO gasto (id, fecha, monto, itbis, categoria_id, descripcion, tipo, doctor_id, metodo, proveedor_id, tipo_ncf, ncf, registrado_por)
SELECT v.id, v.fecha::date, v.monto, v.itbis, c.id, v.descripcion, v.tipo, v.doc, v.metodo, v.prov, v.tipo_ncf, v.ncf, 1
FROM (VALUES
 (1,'2026-09-01',45000.00,   0.00,'Alquiler','Alquiler del local · septiembre','consultorio',NULL,'transferencia',NULL,NULL,NULL),
 (2,'2026-09-05', 7080.00,1080.00,'Materiales e insumos','Resina y adhesivo','consultorio',NULL,'tarjeta',1,'B01','B0100004512'),
 (3,'2026-09-30',20570.00,   0.00,'Sueldos y honorarios','Honorarios de abril · implante 36','doctor',2,'transferencia',NULL,NULL,NULL)
) AS v(id,fecha,monto,itbis,cat,descripcion,tipo,doc,metodo,prov,tipo_ncf,ncf)
JOIN categoria_gasto c ON c.nombre = v.cat;

INSERT INTO movimiento_insumo (insumo_id, cantidad, motivo, costo_unit, gasto_id, usuario_id, ocurrido_en) VALUES
 (1,  2, 'inicial',  2200.00, NULL, 1, '2026-01-02 08:00-04'),
 (1,  2, 'compra',   2200.00, 2,    1, '2026-09-05 10:00-04'),
 (1, -1, 'consumo',  NULL,    NULL, 1, '2026-09-20 16:00-04'),
 (2,  1, 'inicial',  3200.00, NULL, 1, '2026-01-02 08:00-04'),
 (2,  1, 'compra',   3200.00, 2,    1, '2026-09-05 10:00-04'),
 (3,120, 'inicial',    45.00, NULL, 1, '2026-01-02 08:00-04'),
 (3,-14, 'consumo',  NULL,    NULL, 1, '2026-09-20 16:00-04'),
 (4,  6, 'inicial',   550.00, NULL, 1, '2026-01-02 08:00-04');

-- Receta de la resina de una superficie: un décimo de jeringa, una gota de adhesivo y un cartucho.
INSERT INTO servicio_insumo (servicio_id, insumo_id, cantidad)
SELECT s.id, v.insumo, v.cantidad
FROM servicio s, (VALUES (1, 0.1), (2, 0.05), (3, 1)) AS v(insumo, cantidad)
WHERE s.codigo = 'REST-001';

-- ---------------------------------------------------------------------
-- SINCRONIZAR SECUENCIAS (por los IDs explícitos usados arriba)
-- ---------------------------------------------------------------------
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT unnest(ARRAY['sede','doctor','usuario','paciente','ficha_medica','cita','consulta',
                               'odontograma','plan_tratamiento','plan_item','procedimiento','implante',
                               'prescripcion','factura','pago','unidad_dental','documento_emitido',
                               'proveedor','insumo','gasto']) AS t
  LOOP
    EXECUTE format('SELECT setval(pg_get_serial_sequence(%L,''id''), COALESCE((SELECT MAX(id) FROM %I),1))', r.t, r.t);
  END LOOP;
END $$;
