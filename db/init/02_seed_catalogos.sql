-- =====================================================================
-- 02_seed_catalogos.sql  ·  Datos maestros (no dependen del cliente)
-- =====================================================================

-- ---------------------------------------------------------------------
-- ESPECIALIDADES
-- ---------------------------------------------------------------------
INSERT INTO especialidad (codigo, nombre, descripcion) VALUES
 ('GEN','Odontología general','Diagnóstico y tratamiento integral'),
 ('ENDO','Endodoncia','Tratamiento de conductos radiculares'),
 ('PERIO','Periodoncia','Encías y tejidos de soporte'),
 ('CIR','Cirugía oral y maxilofacial','Exodoncias y cirugía'),
 ('IMPL','Implantología','Implantes dentales y rehabilitación'),
 ('PROT','Rehabilitación oral / Prótesis','Coronas, puentes y prótesis'),
 ('ORTO','Ortodoncia','Corrección de maloclusiones'),
 ('ODP','Odontopediatría','Atención odontológica infantil'),
 ('EST','Odontología estética','Blanqueamiento y carillas');

-- ---------------------------------------------------------------------
-- CONDICIONES MÉDICAS (ficha médica)
-- ---------------------------------------------------------------------
INSERT INTO condicion_medica (codigo, nombre, riesgo, alerta) VALUES
 ('HTA','Hipertensión arterial','alto','Controlar presión antes del procedimiento. Cuidado con anestesia con vasoconstrictor.'),
 ('DM','Diabetes mellitus','alto','Riesgo de infección y cicatrización lenta. Verificar glicemia.'),
 ('CARD','Cardiopatía / soplo','alto','Puede requerir profilaxis antibiótica.'),
 ('ANTICOAG','Terapia anticoagulante','alto','Riesgo de sangrado. Solicitar INR antes de cirugía.'),
 ('ASMA','Asma','medio','Paciente debe traer inhalador.'),
 ('EPIL','Epilepsia','alto','Evitar factores desencadenantes. Sesiones cortas.'),
 ('HEPB','Hepatitis B/C','alto','Reforzar bioseguridad.'),
 ('VIH','VIH','alto','Reforzar bioseguridad. Evaluar inmunosupresión.'),
 ('TIROID','Trastorno tiroideo','medio',NULL),
 ('RENAL','Insuficiencia renal','alto','Ajustar dosis de medicamentos.'),
 ('OSTEO','Osteoporosis / bifosfonatos','alto','Riesgo de osteonecrosis maxilar. Precaución con exodoncias e implantes.'),
 ('CANCER','Cáncer / quimio-radioterapia','alto','Coordinar con oncólogo antes de procedimientos invasivos.'),
 ('GAST','Gastritis / reflujo','bajo','Considerar erosión dental.'),
 ('EMB','Embarazo','medio','Evitar radiografías. Preferir 2do trimestre.');

-- ---------------------------------------------------------------------
-- ALERGIAS
-- ---------------------------------------------------------------------
INSERT INTO alergia (codigo, nombre, tipo) VALUES
 ('PENI','Penicilina','medicamento'),
 ('AINE','AINEs / Aspirina','medicamento'),
 ('SULF','Sulfamidas','medicamento'),
 ('LIDO','Lidocaína / anestésicos locales','medicamento'),
 ('LATEX','Látex','material'),
 ('NIQ','Níquel / metales','material'),
 ('YODO','Yodo / povidona','medicamento'),
 ('ACRIL','Acrílico','material');

-- ---------------------------------------------------------------------
-- ASEGURADORAS
-- ---------------------------------------------------------------------
INSERT INTO aseguradora (codigo, nombre, telefono) VALUES
 ('PARTIC','Particular / sin seguro', NULL),
 ('ARS01','ARS Humano','809-000-0001'),
 ('ARS02','ARS Universal','809-000-0002'),
 ('ARS03','ARS Palic Salud','809-000-0003'),
 ('ARS04','SeNaSa','809-000-0004');

-- ---------------------------------------------------------------------
-- DIENTES · Notación FDI/ISO 3950 (32 permanentes + 20 temporales)
-- ---------------------------------------------------------------------
DO $$
DECLARE
  q INT; p INT;
  nom_perm  TEXT[] := ARRAY['Incisivo central','Incisivo lateral','Canino','Primer premolar','Segundo premolar','Primer molar','Segundo molar','Tercer molar'];
  grp_perm  TEXT[] := ARRAY['incisivo','incisivo','canino','premolar','premolar','molar','molar','molar'];
  nom_temp  TEXT[] := ARRAY['Incisivo central','Incisivo lateral','Canino','Primer molar','Segundo molar'];
  grp_temp  TEXT[] := ARRAY['incisivo','incisivo','canino','molar','molar'];
  univ      INT;
BEGIN
  -- Permanentes: cuadrantes 1 (sup. der.), 2 (sup. izq.), 3 (inf. izq.), 4 (inf. der.)
  FOR q IN 1..4 LOOP
    FOR p IN 1..8 LOOP
      univ := CASE q WHEN 1 THEN 9 - p
                     WHEN 2 THEN 8 + p
                     WHEN 3 THEN 25 - p
                     ELSE 24 + p END;
      INSERT INTO diente (codigo_fdi, cuadrante, posicion, denticion, nombre, grupo, arcada, lado, universal)
      VALUES (q*10 + p, q, p, 'permanente', nom_perm[p], grp_perm[p]::grupo_dental_t,
              CASE WHEN q IN (1,2) THEN 'superior' ELSE 'inferior' END::arcada_t,
              CASE WHEN q IN (1,4) THEN 'derecho' ELSE 'izquierdo' END::lado_t,
              univ);
    END LOOP;
  END LOOP;

  -- Temporales: cuadrantes 5,6,7,8
  FOR q IN 5..8 LOOP
    FOR p IN 1..5 LOOP
      INSERT INTO diente (codigo_fdi, cuadrante, posicion, denticion, nombre, grupo, arcada, lado)
      VALUES (q*10 + p, q, p, 'temporal', nom_temp[p], grp_temp[p]::grupo_dental_t,
              CASE WHEN q IN (5,6) THEN 'superior' ELSE 'inferior' END::arcada_t,
              CASE WHEN q IN (5,8) THEN 'derecho' ELSE 'izquierdo' END::lado_t);
    END LOOP;
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- SUPERFICIES DENTALES
-- ---------------------------------------------------------------------
INSERT INTO superficie (codigo, nombre, aplica_a) VALUES
 ('M','Mesial','todos'),
 ('D','Distal','todos'),
 ('V','Vestibular / Bucal','todos'),
 ('L','Lingual / Palatino','todos'),
 ('O','Oclusal','posterior'),
 ('I','Incisal','anterior');

-- ---------------------------------------------------------------------
-- CONDICIONES DEL ODONTOGRAMA
-- patologico = TRUE  -> hallazgo a tratar (se pinta en rojo por convención)
-- patologico = FALSE -> tratamiento ya existente (azul)
-- ---------------------------------------------------------------------
INSERT INTO condicion_dental (codigo, nombre, ambito, color_hex, patologico, orden) VALUES
 ('CAR_INC','Mancha blanca / caries incipiente','superficie','#FB8C00', TRUE, 1),
 ('CAR','Caries','superficie','#E53935', TRUE, 2),
 ('FRA','Fractura','diente','#D81B60', TRUE, 3),
 ('DES','Desgaste / atrición','superficie','#8D6E63', TRUE, 4),
 ('REST_DEF','Restauración defectuosa / filtrada','superficie','#F4511E', TRUE, 5),
 ('AUS','Ausente congénito','diente','#616161', TRUE, 6),
 ('AUS_EXT','Ausente por extracción','diente','#424242', TRUE, 7),
 ('IND_EXT','Indicado para extracción','diente','#C62828', TRUE, 8),
 ('IMPACT','Retenido / impactado','diente','#6D4C41', TRUE, 9),
 ('SUPER','Supernumerario','diente','#7B1FA2', TRUE, 10),
 ('ERUP','En erupción','diente','#00897B', TRUE, 11),
 ('GIRO','Giroversión / malposición','diente','#5E35B1', TRUE, 12),
 ('DIAST','Diastema','diente','#3949AB', TRUE, 13),
 ('MOVIL','Movilidad','periodontal','#EF6C00', TRUE, 14),
 ('RECES','Recesión gingival','periodontal','#F06292', TRUE, 15),
 ('CALC','Cálculo / tártaro','periodontal','#9E9D24', TRUE, 16),
 ('BOLSA','Bolsa periodontal','periodontal','#AD1457', TRUE, 17),
 ('ABSC','Absceso / lesión periapical','raiz','#B71C1C', TRUE, 18),
 ('SELL','Sellante','superficie','#26A69A', FALSE, 20),
 ('RES','Restauración de resina','superficie','#1E88E5', FALSE, 21),
 ('AMAL','Amalgama','superficie','#455A64', FALSE, 22),
 ('TEMP','Restauración temporal','superficie','#00ACC1', FALSE, 23),
 ('ENDO','Tratamiento de conducto','raiz','#1565C0', FALSE, 24),
 ('PULPO','Pulpotomía','raiz','#0277BD', FALSE, 25),
 ('POSTE','Poste / muñón','raiz','#0D47A1', FALSE, 26),
 ('COR_PFM','Corona metal-porcelana','protesico','#3F51B5', FALSE, 27),
 ('COR_ZIR','Corona de zirconio / cerámica','protesico','#283593', FALSE, 28),
 ('COR_ACE','Corona de acero-cromo','protesico','#546E7A', FALSE, 29),
 ('PONT','Póntico de puente fijo','protesico','#5C6BC0', FALSE, 30),
 ('IMPL','Implante','protesico','#00695C', FALSE, 31),
 ('PILAR','Pilar / aditamento','protesico','#00838F', FALSE, 32),
 ('PPR','Prótesis parcial removible','protesico','#6A1B9A', FALSE, 33),
 ('PTOT','Prótesis total','protesico','#4A148C', FALSE, 34),
 ('ORTO','Aparatología de ortodoncia','protesico','#7E57C2', FALSE, 35),
 ('CARILLA','Carilla','protesico','#0097A7', FALSE, 36);

-- ---------------------------------------------------------------------
-- CATEGORÍAS DE SERVICIO
-- ---------------------------------------------------------------------
INSERT INTO categoria_servicio (codigo, nombre, orden) VALUES
 ('DX','Diagnóstico e imágenes',1),
 ('PREV','Preventiva',2),
 ('REST','Operatoria / Restauradora',3),
 ('ENDO','Endodoncia',4),
 ('PERIO','Periodoncia',5),
 ('CIR','Cirugía oral',6),
 ('IMPL','Implantología',7),
 ('PROT','Prótesis y rehabilitación',8),
 ('ORTO','Ortodoncia',9),
 ('ODP','Odontopediatría',10),
 ('EST','Estética',11);

-- ---------------------------------------------------------------------
-- SERVICIOS
-- ---------------------------------------------------------------------
INSERT INTO servicio (categoria_id, codigo, nombre, requiere_diente, requiere_superficie, es_implante, duracion_min, sesiones, condicion_resultante_id)
SELECT c.id, v.codigo, v.nombre, v.req_d, v.req_s, v.es_impl, v.dur, v.ses,
       (SELECT id FROM condicion_dental cd WHERE cd.codigo = v.cond)
FROM (VALUES
 ('DX','DX-001','Consulta y evaluación inicial',        FALSE,FALSE,FALSE, 30,1, NULL),
 ('DX','DX-002','Radiografía periapical',                TRUE, FALSE,FALSE, 10,1, NULL),
 ('DX','DX-003','Radiografía panorámica',                FALSE,FALSE,FALSE, 15,1, NULL),
 ('DX','DX-004','Tomografía CBCT',                       FALSE,FALSE,FALSE, 20,1, NULL),
 ('PREV','PREV-001','Profilaxis y fluorización',         FALSE,FALSE,FALSE, 40,1, NULL),
 ('PREV','PREV-002','Sellante de fosas y fisuras',       TRUE, TRUE, FALSE, 20,1, 'SELL'),
 ('PREV','PREV-003','Destartraje supragingival (arcada)',FALSE,FALSE,FALSE, 45,1, NULL),
 ('REST','REST-001','Resina · 1 superficie',             TRUE, TRUE, FALSE, 40,1, 'RES'),
 ('REST','REST-002','Resina · 2 superficies',            TRUE, TRUE, FALSE, 50,1, 'RES'),
 ('REST','REST-003','Resina · 3 o más superficies',      TRUE, TRUE, FALSE, 60,1, 'RES'),
 ('REST','REST-004','Amalgama',                          TRUE, TRUE, FALSE, 45,1, 'AMAL'),
 ('REST','REST-005','Restauración temporal',             TRUE, TRUE, FALSE, 20,1, 'TEMP'),
 ('REST','REST-006','Poste de fibra y reconstrucción',   TRUE, FALSE,FALSE, 60,1, 'POSTE'),
 ('ENDO','ENDO-001','Endodoncia unirradicular',          TRUE, FALSE,FALSE, 60,1, 'ENDO'),
 ('ENDO','ENDO-002','Endodoncia birradicular',           TRUE, FALSE,FALSE, 75,2, 'ENDO'),
 ('ENDO','ENDO-003','Endodoncia multirradicular (molar)',TRUE, FALSE,FALSE, 90,2, 'ENDO'),
 ('ENDO','ENDO-004','Retratamiento de conducto',         TRUE, FALSE,FALSE,100,2, 'ENDO'),
 ('ENDO','ENDO-005','Pulpotomía',                        TRUE, FALSE,FALSE, 45,1, 'PULPO'),
 ('PERIO','PERIO-001','Raspado y alisado radicular (cuadrante)',FALSE,FALSE,FALSE,60,1,NULL),
 ('PERIO','PERIO-002','Gingivectomía (sextante)',        FALSE,FALSE,FALSE, 60,1, NULL),
 ('PERIO','PERIO-003','Mantenimiento periodontal',       FALSE,FALSE,FALSE, 45,1, NULL),
 ('CIR','CIR-001','Extracción simple',                   TRUE, FALSE,FALSE, 30,1, 'AUS_EXT'),
 ('CIR','CIR-002','Extracción quirúrgica',               TRUE, FALSE,FALSE, 60,1, 'AUS_EXT'),
 ('CIR','CIR-003','Extracción de tercer molar retenido', TRUE, FALSE,FALSE, 90,1, 'AUS_EXT'),
 ('CIR','CIR-004','Frenectomía',                         FALSE,FALSE,FALSE, 45,1, NULL),
 ('CIR','CIR-005','Biopsia de tejido blando',            FALSE,FALSE,FALSE, 40,1, NULL),
 ('IMPL','IMPL-001','Implante dental unitario (cirugía)',TRUE, FALSE,TRUE, 90,1, 'IMPL'),
 ('IMPL','IMPL-002','Aditamento / pilar personalizado',  TRUE, FALSE,FALSE, 45,1, 'PILAR'),
 ('IMPL','IMPL-003','Corona sobre implante (zirconio)',  TRUE, FALSE,FALSE, 60,2, 'COR_ZIR'),
 ('IMPL','IMPL-004','Injerto óseo (por sitio)',          TRUE, FALSE,FALSE, 60,1, NULL),
 ('IMPL','IMPL-005','Elevación de seno maxilar',         TRUE, FALSE,FALSE,120,1, NULL),
 ('IMPL','IMPL-006','Segunda fase quirúrgica',           TRUE, FALSE,FALSE, 30,1, NULL),
 ('PROT','PROT-001','Corona metal-porcelana',            TRUE, FALSE,FALSE, 60,2, 'COR_PFM'),
 ('PROT','PROT-002','Corona de zirconio',                TRUE, FALSE,FALSE, 60,2, 'COR_ZIR'),
 ('PROT','PROT-003','Póntico de puente fijo',            TRUE, FALSE,FALSE, 45,2, 'PONT'),
 ('PROT','PROT-004','Prótesis parcial removible',        FALSE,FALSE,FALSE, 60,4, 'PPR'),
 ('PROT','PROT-005','Prótesis total (por arcada)',       FALSE,FALSE,FALSE, 60,5, 'PTOT'),
 ('ORTO','ORTO-001','Estudio y plan de ortodoncia',      FALSE,FALSE,FALSE, 60,1, NULL),
 ('ORTO','ORTO-002','Instalación de brackets (por arcada)',FALSE,FALSE,FALSE,90,1,'ORTO'),
 ('ORTO','ORTO-003','Control mensual de ortodoncia',     FALSE,FALSE,FALSE, 30,1, NULL),
 ('ORTO','ORTO-004','Retenedor',                         FALSE,FALSE,FALSE, 30,1, NULL),
 ('ODP','ODP-001','Corona de acero-cromo',               TRUE, FALSE,FALSE, 45,1, 'COR_ACE'),
 ('ODP','ODP-002','Aplicación tópica de flúor',          FALSE,FALSE,FALSE, 20,1, NULL),
 ('ODP','ODP-003','Mantenedor de espacio',               TRUE, FALSE,FALSE, 45,2, NULL),
 ('EST','EST-001','Blanqueamiento en consultorio',       FALSE,FALSE,FALSE, 75,1, NULL),
 ('EST','EST-002','Carilla de resina',                   TRUE, FALSE,FALSE, 60,1, 'CARILLA'),
 ('EST','EST-003','Carilla de porcelana',                TRUE, FALSE,FALSE, 60,2, 'CARILLA')
) AS v(cat,codigo,nombre,req_d,req_s,es_impl,dur,ses,cond)
JOIN categoria_servicio c ON c.codigo = v.cat;

-- ---------------------------------------------------------------------
-- LISTAS DE PRECIO
-- Moneda DOP. Los servicios de salud van exentos de ITBIS (tasa = 0);
-- ajusta `tasa_impuesto` si tu jurisdicción grava estos servicios.
-- ---------------------------------------------------------------------
INSERT INTO lista_precio (id, codigo, nombre, moneda, aseguradora_id, vigente_desde) VALUES
 (1,'PART-2026','Tarifa particular 2026','DOP', NULL, '2026-01-01'),
 (2,'ARS01-2026','Tarifa ARS Humano 2026','DOP',(SELECT id FROM aseguradora WHERE codigo='ARS01'),'2026-01-01');
SELECT setval(pg_get_serial_sequence('lista_precio','id'), 2);

-- Precios particulares
INSERT INTO precio_servicio (lista_precio_id, servicio_id, precio, costo, tasa_impuesto)
SELECT 1, s.id, v.precio, v.costo, 0
FROM (VALUES
 ('DX-001',1200,0),('DX-002',700,80),('DX-003',2500,300),('DX-004',6500,1500),
 ('PREV-001',2500,250),('PREV-002',1500,180),('PREV-003',3000,300),
 ('REST-001',2800,350),('REST-002',3600,480),('REST-003',4500,600),
 ('REST-004',2500,300),('REST-005',1200,120),('REST-006',6500,1200),
 ('ENDO-001',9000,1200),('ENDO-002',11000,1500),('ENDO-003',14000,1900),
 ('ENDO-004',16000,2200),('ENDO-005',4500,600),
 ('PERIO-001',5000,500),('PERIO-002',7000,800),('PERIO-003',3500,350),
 ('CIR-001',3000,400),('CIR-002',6000,900),('CIR-003',12000,1800),
 ('CIR-004',8000,1000),('CIR-005',7000,1200),
 ('IMPL-001',45000,14000),('IMPL-002',12000,4500),('IMPL-003',28000,9000),
 ('IMPL-004',18000,7000),('IMPL-005',45000,15000),('IMPL-006',6000,800),
 ('PROT-001',18000,6000),('PROT-002',25000,9000),('PROT-003',16000,5500),
 ('PROT-004',22000,7500),('PROT-005',35000,12000),
 ('ORTO-001',5000,600),('ORTO-002',30000,9000),('ORTO-003',2500,300),('ORTO-004',6000,2000),
 ('ODP-001',5000,900),('ODP-002',1500,150),('ODP-003',6000,1800),
 ('EST-001',12000,3500),('EST-002',8000,1200),('EST-003',30000,11000)
) AS v(codigo,precio,costo)
JOIN servicio s ON s.codigo = v.codigo;

-- Tarifa de seguro: 15% menos que particular, con cobertura por categoría
INSERT INTO precio_servicio (lista_precio_id, servicio_id, precio, costo, cobertura_pct, tasa_impuesto)
SELECT 2, ps.servicio_id, ROUND(ps.precio * 0.85, 2), ps.costo,
       CASE cs.codigo
         WHEN 'DX'    THEN 100
         WHEN 'PREV'  THEN 100
         WHEN 'REST'  THEN 70
         WHEN 'ENDO'  THEN 60
         WHEN 'PERIO' THEN 60
         WHEN 'CIR'   THEN 70
         WHEN 'ODP'   THEN 80
         WHEN 'PROT'  THEN 40
         WHEN 'IMPL'  THEN 20
         WHEN 'ORTO'  THEN 20
         ELSE 0
       END,
       0
FROM precio_servicio ps
JOIN servicio s          ON s.id = ps.servicio_id
JOIN categoria_servicio cs ON cs.id = s.categoria_id
WHERE ps.lista_precio_id = 1;

-- ---------------------------------------------------------------------
-- SISTEMAS DE IMPLANTE
-- ---------------------------------------------------------------------
INSERT INTO sistema_implante (marca, linea, conexion, proveedor) VALUES
 ('Straumann','BLX','TorcFit','Distribuidor local'),
 ('Straumann','Bone Level Tapered','CrossFit','Distribuidor local'),
 ('Nobel Biocare','NobelActive','Conexión cónica','Distribuidor local'),
 ('Neodent','Grand Morse','Cono morse','Distribuidor local'),
 ('MIS','C1','Hexágono interno','Distribuidor local'),
 ('BioHorizons','Tapered Pro','Hexágono interno','Distribuidor local');
