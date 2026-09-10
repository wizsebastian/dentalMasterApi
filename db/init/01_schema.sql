-- =====================================================================
-- SISTEMA DE REGISTRO ODONTOLÓGICO
-- 01_schema.sql  ·  PostgreSQL 14+
-- Módulos: sedes, doctores, pacientes, ficha médica, odontograma (FDI),
--          catálogo de servicios y precios, citas, planes de tratamiento,
--          procedimientos, implantes con trazabilidad, facturación.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------
-- TIPOS
-- ---------------------------------------------------------------------
CREATE TYPE sexo_t              AS ENUM ('M','F','O');
CREATE TYPE denticion_t         AS ENUM ('permanente','temporal');
CREATE TYPE arcada_t            AS ENUM ('superior','inferior');
CREATE TYPE lado_t              AS ENUM ('derecho','izquierdo');
CREATE TYPE grupo_dental_t      AS ENUM ('incisivo','canino','premolar','molar');
CREATE TYPE ambito_condicion_t  AS ENUM ('superficie','diente','raiz','periodontal','protesico');
CREATE TYPE estado_hallazgo_t   AS ENUM ('existente','planificado','en_proceso','completado','anulado');
CREATE TYPE estado_cita_t       AS ENUM ('agendada','confirmada','en_sala','atendida','cancelada','no_asistio');
CREATE TYPE estado_plan_t       AS ENUM ('borrador','presentado','aceptado','rechazado','en_ejecucion','finalizado');
CREATE TYPE estado_proc_t       AS ENUM ('pendiente','en_proceso','completado','anulado');
CREATE TYPE estado_implante_t   AS ENUM ('planificado','colocado','oseointegrado','cargado','fallido','explantado');
CREATE TYPE estado_factura_t    AS ENUM ('borrador','emitida','parcial','pagada','anulada');
CREATE TYPE rol_usuario_t       AS ENUM ('admin','doctor','asistente','recepcion','facturacion');

-- ---------------------------------------------------------------------
-- 1. ORGANIZACIÓN Y PERSONAL
-- ---------------------------------------------------------------------
CREATE TABLE sede (
  id            BIGSERIAL PRIMARY KEY,
  nombre        TEXT NOT NULL,
  direccion     TEXT,
  ciudad        TEXT,
  telefono      TEXT,
  email         TEXT,
  rnc           TEXT,                       -- identificación fiscal del negocio
  activo        BOOLEAN NOT NULL DEFAULT TRUE,
  creado_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE especialidad (
  id            BIGSERIAL PRIMARY KEY,
  codigo        TEXT NOT NULL UNIQUE,
  nombre        TEXT NOT NULL,
  descripcion   TEXT
);

CREATE TABLE doctor (
  id                BIGSERIAL PRIMARY KEY,
  sede_id           BIGINT REFERENCES sede(id),
  documento         TEXT NOT NULL UNIQUE,   -- cédula / DNI
  nombres           TEXT NOT NULL,
  apellidos         TEXT NOT NULL,
  licencia          TEXT UNIQUE,            -- exequátur / colegiatura
  email             TEXT UNIQUE,
  telefono          TEXT,
  fecha_ingreso     DATE,
  porcentaje_comision NUMERIC(5,2) DEFAULT 0 CHECK (porcentaje_comision BETWEEN 0 AND 100),
  activo            BOOLEAN NOT NULL DEFAULT TRUE,
  creado_en         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE doctor_especialidad (
  doctor_id       BIGINT NOT NULL REFERENCES doctor(id) ON DELETE CASCADE,
  especialidad_id BIGINT NOT NULL REFERENCES especialidad(id),
  principal       BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (doctor_id, especialidad_id)
);

CREATE TABLE usuario (
  id            BIGSERIAL PRIMARY KEY,
  doctor_id     BIGINT REFERENCES doctor(id),
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  rol           rol_usuario_t NOT NULL,
  activo        BOOLEAN NOT NULL DEFAULT TRUE,
  creado_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 2. PACIENTES
-- ---------------------------------------------------------------------
CREATE TABLE paciente (
  id                BIGSERIAL PRIMARY KEY,
  codigo            TEXT NOT NULL UNIQUE,          -- expediente: PAC-2026-0001
  documento         TEXT UNIQUE,                   -- cédula / pasaporte
  nombres           TEXT NOT NULL,
  apellidos         TEXT NOT NULL,
  fecha_nacimiento  DATE NOT NULL,
  sexo              sexo_t NOT NULL,
  telefono          TEXT,
  celular           TEXT,
  email             TEXT,
  direccion         TEXT,
  ciudad            TEXT,
  ocupacion         TEXT,
  estado_civil      TEXT,
  tipo_sangre       TEXT,
  referido_por      TEXT,
  sede_id           BIGINT REFERENCES sede(id),
  notas             TEXT,
  activo            BOOLEAN NOT NULL DEFAULT TRUE,
  creado_en         TIMESTAMPTZ NOT NULL DEFAULT now(),
  actualizado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_paciente_nombre ON paciente (apellidos, nombres);

CREATE TABLE paciente_contacto (
  id            BIGSERIAL PRIMARY KEY,
  paciente_id   BIGINT NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
  nombre        TEXT NOT NULL,
  parentesco    TEXT,
  telefono      TEXT NOT NULL,
  es_emergencia BOOLEAN NOT NULL DEFAULT TRUE,
  es_tutor      BOOLEAN NOT NULL DEFAULT FALSE   -- responsable de menores
);

CREATE TABLE aseguradora (
  id        BIGSERIAL PRIMARY KEY,
  codigo    TEXT NOT NULL UNIQUE,
  nombre    TEXT NOT NULL,
  telefono  TEXT,
  activo    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE paciente_seguro (
  id              BIGSERIAL PRIMARY KEY,
  paciente_id     BIGINT NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
  aseguradora_id  BIGINT NOT NULL REFERENCES aseguradora(id),
  poliza          TEXT NOT NULL,
  plan            TEXT,
  titular         TEXT,
  vigente_desde   DATE,
  vigente_hasta   DATE,
  principal       BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------
-- 3. FICHA MÉDICA / HISTORIA CLÍNICA
-- ---------------------------------------------------------------------
CREATE TABLE ficha_medica (
  id                    BIGSERIAL PRIMARY KEY,
  paciente_id           BIGINT NOT NULL UNIQUE REFERENCES paciente(id) ON DELETE CASCADE,
  motivo_consulta       TEXT,
  enfermedad_actual     TEXT,
  antecedentes_familiares TEXT,
  -- hábitos
  fuma                  BOOLEAN DEFAULT FALSE,
  cigarrillos_dia       INT,
  consume_alcohol       BOOLEAN DEFAULT FALSE,
  bruxismo              BOOLEAN DEFAULT FALSE,
  onicofagia            BOOLEAN DEFAULT FALSE,
  respirador_bucal      BOOLEAN DEFAULT FALSE,
  -- antecedentes odontológicos
  ultima_visita_dental  DATE,
  cepillados_dia        INT,
  usa_hilo_dental       BOOLEAN DEFAULT FALSE,
  sangrado_encias       BOOLEAN DEFAULT FALSE,
  sensibilidad          BOOLEAN DEFAULT FALSE,
  dolor_atm             BOOLEAN DEFAULT FALSE,
  -- estado sistémico
  embarazada            BOOLEAN DEFAULT FALSE,
  semanas_gestacion     INT,
  anticoagulantes       BOOLEAN DEFAULT FALSE,
  bifosfonatos          BOOLEAN DEFAULT FALSE,   -- crítico para implantes/exodoncias
  observaciones         TEXT,
  actualizado_por       BIGINT REFERENCES doctor(id),
  creado_en             TIMESTAMPTZ NOT NULL DEFAULT now(),
  actualizado_en        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE condicion_medica (               -- catálogo
  id        BIGSERIAL PRIMARY KEY,
  codigo    TEXT NOT NULL UNIQUE,
  nombre    TEXT NOT NULL,
  riesgo    TEXT CHECK (riesgo IN ('bajo','medio','alto')) DEFAULT 'medio',
  alerta    TEXT                              -- advertencia clínica a mostrar
);

CREATE TABLE ficha_condicion (
  ficha_id            BIGINT NOT NULL REFERENCES ficha_medica(id) ON DELETE CASCADE,
  condicion_medica_id BIGINT NOT NULL REFERENCES condicion_medica(id),
  diagnosticado_en    DATE,
  controlado          BOOLEAN DEFAULT TRUE,
  detalle             TEXT,
  PRIMARY KEY (ficha_id, condicion_medica_id)
);

CREATE TABLE alergia (                        -- catálogo
  id      BIGSERIAL PRIMARY KEY,
  codigo  TEXT NOT NULL UNIQUE,
  nombre  TEXT NOT NULL,
  tipo    TEXT CHECK (tipo IN ('medicamento','material','alimento','otro')) DEFAULT 'medicamento'
);

CREATE TABLE ficha_alergia (
  ficha_id    BIGINT NOT NULL REFERENCES ficha_medica(id) ON DELETE CASCADE,
  alergia_id  BIGINT NOT NULL REFERENCES alergia(id),
  severidad   TEXT CHECK (severidad IN ('leve','moderada','severa')) DEFAULT 'moderada',
  reaccion    TEXT,
  PRIMARY KEY (ficha_id, alergia_id)
);

CREATE TABLE ficha_medicamento (
  id           BIGSERIAL PRIMARY KEY,
  ficha_id     BIGINT NOT NULL REFERENCES ficha_medica(id) ON DELETE CASCADE,
  nombre       TEXT NOT NULL,
  dosis        TEXT,
  frecuencia   TEXT,
  motivo       TEXT,
  desde        DATE,
  activo       BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------
-- 4. CATÁLOGO DENTAL (notación FDI / ISO 3950)
-- ---------------------------------------------------------------------
CREATE TABLE diente (
  codigo_fdi   SMALLINT PRIMARY KEY,          -- 11..48 permanentes, 51..85 temporales
  cuadrante    SMALLINT NOT NULL CHECK (cuadrante BETWEEN 1 AND 8),
  posicion     SMALLINT NOT NULL CHECK (posicion BETWEEN 1 AND 8),
  denticion    denticion_t NOT NULL,
  nombre       TEXT NOT NULL,
  grupo        grupo_dental_t NOT NULL,
  arcada       arcada_t NOT NULL,
  lado         lado_t NOT NULL,
  universal    SMALLINT,                      -- notación universal (1-32) para interoperar
  palmer       TEXT
);

CREATE TABLE superficie (
  codigo    CHAR(1) PRIMARY KEY,              -- M D V L O I
  nombre    TEXT NOT NULL,
  aplica_a  TEXT NOT NULL                     -- 'todos' | 'anterior' | 'posterior'
);

CREATE TABLE condicion_dental (               -- catálogo de hallazgos del odontograma
  id           BIGSERIAL PRIMARY KEY,
  codigo       TEXT NOT NULL UNIQUE,
  nombre       TEXT NOT NULL,
  ambito       ambito_condicion_t NOT NULL,
  color_hex    TEXT NOT NULL DEFAULT '#000000',
  patologico   BOOLEAN NOT NULL DEFAULT TRUE, -- TRUE = hallazgo, FALSE = tratamiento existente
  orden        INT DEFAULT 0
);

-- ---------------------------------------------------------------------
-- 5. SERVICIOS Y PRECIOS
-- ---------------------------------------------------------------------
CREATE TABLE categoria_servicio (
  id      BIGSERIAL PRIMARY KEY,
  codigo  TEXT NOT NULL UNIQUE,
  nombre  TEXT NOT NULL,
  orden   INT DEFAULT 0
);

CREATE TABLE servicio (
  id                  BIGSERIAL PRIMARY KEY,
  categoria_id        BIGINT NOT NULL REFERENCES categoria_servicio(id),
  codigo              TEXT NOT NULL UNIQUE,        -- código interno / CDT
  nombre              TEXT NOT NULL,
  descripcion         TEXT,
  requiere_diente     BOOLEAN NOT NULL DEFAULT FALSE,
  requiere_superficie BOOLEAN NOT NULL DEFAULT FALSE,
  es_implante         BOOLEAN NOT NULL DEFAULT FALSE,
  duracion_min        INT DEFAULT 30,
  sesiones            INT DEFAULT 1,
  condicion_resultante_id BIGINT REFERENCES condicion_dental(id), -- qué pinta en el odontograma al completarse
  activo              BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE lista_precio (
  id              BIGSERIAL PRIMARY KEY,
  codigo          TEXT NOT NULL UNIQUE,
  nombre          TEXT NOT NULL,
  moneda          CHAR(3) NOT NULL DEFAULT 'DOP',
  aseguradora_id  BIGINT REFERENCES aseguradora(id),   -- NULL = tarifa particular
  vigente_desde   DATE NOT NULL DEFAULT CURRENT_DATE,
  vigente_hasta   DATE,
  activo          BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE precio_servicio (
  id                BIGSERIAL PRIMARY KEY,
  lista_precio_id   BIGINT NOT NULL REFERENCES lista_precio(id) ON DELETE CASCADE,
  servicio_id       BIGINT NOT NULL REFERENCES servicio(id),
  precio            NUMERIC(12,2) NOT NULL CHECK (precio >= 0),
  costo             NUMERIC(12,2) DEFAULT 0,           -- costo directo (materiales/laboratorio)
  cobertura_pct     NUMERIC(5,2) DEFAULT 0 CHECK (cobertura_pct BETWEEN 0 AND 100),
  tasa_impuesto     NUMERIC(5,2) NOT NULL DEFAULT 0,   -- ITBIS/IVA si aplica
  UNIQUE (lista_precio_id, servicio_id)
);

-- ---------------------------------------------------------------------
-- 6. AGENDA Y CONSULTAS
-- ---------------------------------------------------------------------
CREATE TABLE cita (
  id            BIGSERIAL PRIMARY KEY,
  paciente_id   BIGINT NOT NULL REFERENCES paciente(id),
  doctor_id     BIGINT NOT NULL REFERENCES doctor(id),
  sede_id       BIGINT REFERENCES sede(id),
  inicio        TIMESTAMPTZ NOT NULL,
  fin           TIMESTAMPTZ NOT NULL,
  motivo        TEXT,
  estado        estado_cita_t NOT NULL DEFAULT 'agendada',
  notas         TEXT,
  creado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (fin > inicio)
);
CREATE INDEX idx_cita_agenda ON cita (doctor_id, inicio);

CREATE TABLE consulta (
  id                BIGSERIAL PRIMARY KEY,
  paciente_id       BIGINT NOT NULL REFERENCES paciente(id),
  doctor_id         BIGINT NOT NULL REFERENCES doctor(id),
  cita_id           BIGINT REFERENCES cita(id),
  fecha             TIMESTAMPTZ NOT NULL DEFAULT now(),
  motivo            TEXT,
  -- signos vitales
  presion_sistolica INT, presion_diastolica INT,
  pulso             INT, temperatura NUMERIC(4,1),
  -- SOAP
  subjetivo         TEXT,
  objetivo          TEXT,
  diagnostico       TEXT,
  plan              TEXT,
  creado_en         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_consulta_paciente ON consulta (paciente_id, fecha DESC);

-- ---------------------------------------------------------------------
-- 7. ODONTOGRAMA
--    Un odontograma = una versión fechada del estado bucal del paciente.
--    Los hallazgos se registran por diente y (opcionalmente) por superficie.
-- ---------------------------------------------------------------------
CREATE TABLE odontograma (
  id            BIGSERIAL PRIMARY KEY,
  paciente_id   BIGINT NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
  doctor_id     BIGINT REFERENCES doctor(id),
  consulta_id   BIGINT REFERENCES consulta(id),
  version       INT NOT NULL DEFAULT 1,
  denticion     denticion_t NOT NULL DEFAULT 'permanente',
  fecha         DATE NOT NULL DEFAULT CURRENT_DATE,
  es_actual     BOOLEAN NOT NULL DEFAULT TRUE,
  observaciones TEXT,
  creado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (paciente_id, version)
);
-- solo un odontograma vigente por paciente
CREATE UNIQUE INDEX uq_odontograma_actual
  ON odontograma (paciente_id) WHERE es_actual;

CREATE TABLE odontograma_diente (             -- estado global de la pieza
  id              BIGSERIAL PRIMARY KEY,
  odontograma_id  BIGINT NOT NULL REFERENCES odontograma(id) ON DELETE CASCADE,
  codigo_fdi      SMALLINT NOT NULL REFERENCES diente(codigo_fdi),
  presente        BOOLEAN NOT NULL DEFAULT TRUE,
  movilidad       SMALLINT CHECK (movilidad BETWEEN 0 AND 3),
  recesion_mm     NUMERIC(3,1),
  sondaje_mm      NUMERIC(3,1),
  sangrado        BOOLEAN DEFAULT FALSE,
  notas           TEXT,
  UNIQUE (odontograma_id, codigo_fdi)
);

CREATE TABLE odontograma_hallazgo (
  id                  BIGSERIAL PRIMARY KEY,
  odontograma_id      BIGINT NOT NULL REFERENCES odontograma(id) ON DELETE CASCADE,
  codigo_fdi          SMALLINT NOT NULL REFERENCES diente(codigo_fdi),
  superficie          CHAR(1) REFERENCES superficie(codigo),   -- NULL = aplica a toda la pieza
  condicion_dental_id BIGINT NOT NULL REFERENCES condicion_dental(id),
  estado              estado_hallazgo_t NOT NULL DEFAULT 'existente',
  doctor_id           BIGINT REFERENCES doctor(id),
  fecha               DATE NOT NULL DEFAULT CURRENT_DATE,
  notas               TEXT,
  UNIQUE (odontograma_id, codigo_fdi, superficie, condicion_dental_id, estado)
);
CREATE INDEX idx_hallazgo_diente ON odontograma_hallazgo (odontograma_id, codigo_fdi);

-- ---------------------------------------------------------------------
-- 8. PLANES DE TRATAMIENTO Y PROCEDIMIENTOS
-- ---------------------------------------------------------------------
CREATE TABLE plan_tratamiento (
  id              BIGSERIAL PRIMARY KEY,
  paciente_id     BIGINT NOT NULL REFERENCES paciente(id),
  doctor_id       BIGINT NOT NULL REFERENCES doctor(id),
  lista_precio_id BIGINT NOT NULL REFERENCES lista_precio(id),
  codigo          TEXT NOT NULL UNIQUE,          -- PT-2026-0001
  fecha           DATE NOT NULL DEFAULT CURRENT_DATE,
  estado          estado_plan_t NOT NULL DEFAULT 'borrador',
  descuento_pct   NUMERIC(5,2) NOT NULL DEFAULT 0,
  notas           TEXT,
  creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE plan_item (
  id            BIGSERIAL PRIMARY KEY,
  plan_id       BIGINT NOT NULL REFERENCES plan_tratamiento(id) ON DELETE CASCADE,
  servicio_id   BIGINT NOT NULL REFERENCES servicio(id),
  codigo_fdi    SMALLINT REFERENCES diente(codigo_fdi),
  superficies   TEXT,                            -- 'MOD', 'OV', etc.
  cantidad      INT NOT NULL DEFAULT 1 CHECK (cantidad > 0),
  precio_unit   NUMERIC(12,2) NOT NULL,
  descuento_pct NUMERIC(5,2) NOT NULL DEFAULT 0,
  fase          INT NOT NULL DEFAULT 1,          -- fase 1: urgencias, 2: rehabilitación...
  prioridad     SMALLINT NOT NULL DEFAULT 3 CHECK (prioridad BETWEEN 1 AND 5),
  aprobado      BOOLEAN NOT NULL DEFAULT FALSE,
  total         NUMERIC(12,2) GENERATED ALWAYS AS
                (cantidad * precio_unit * (1 - descuento_pct/100)) STORED
);

CREATE TABLE procedimiento (                    -- lo que realmente se ejecutó
  id              BIGSERIAL PRIMARY KEY,
  paciente_id     BIGINT NOT NULL REFERENCES paciente(id),
  doctor_id       BIGINT NOT NULL REFERENCES doctor(id),
  servicio_id     BIGINT NOT NULL REFERENCES servicio(id),
  consulta_id     BIGINT REFERENCES consulta(id),
  plan_item_id    BIGINT REFERENCES plan_item(id),
  codigo_fdi      SMALLINT REFERENCES diente(codigo_fdi),
  superficies     TEXT,
  fecha           DATE NOT NULL DEFAULT CURRENT_DATE,
  estado          estado_proc_t NOT NULL DEFAULT 'completado',
  anestesia       TEXT,
  materiales      TEXT,
  precio          NUMERIC(12,2) NOT NULL DEFAULT 0,
  notas           TEXT,
  creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_proc_paciente ON procedimiento (paciente_id, fecha DESC);

-- ---------------------------------------------------------------------
-- 9. IMPLANTES (trazabilidad de por vida)
-- ---------------------------------------------------------------------
CREATE TABLE sistema_implante (
  id            BIGSERIAL PRIMARY KEY,
  marca         TEXT NOT NULL,
  linea         TEXT NOT NULL,                 -- ej. 'BLX', 'NobelActive'
  conexion      TEXT,                          -- cono morse, hex interno...
  proveedor     TEXT,
  activo        BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (marca, linea)
);

CREATE TABLE implante (
  id                   BIGSERIAL PRIMARY KEY,
  paciente_id          BIGINT NOT NULL REFERENCES paciente(id),
  doctor_id            BIGINT NOT NULL REFERENCES doctor(id),
  procedimiento_id     BIGINT REFERENCES procedimiento(id),
  sistema_implante_id  BIGINT NOT NULL REFERENCES sistema_implante(id),
  codigo_fdi           SMALLINT NOT NULL REFERENCES diente(codigo_fdi),
  referencia           TEXT,                   -- SKU del fabricante
  lote                 TEXT NOT NULL,          -- obligatorio para trazabilidad
  serie                TEXT,
  diametro_mm          NUMERIC(3,1),
  longitud_mm          NUMERIC(3,1),
  plataforma           TEXT,
  torque_ncm           SMALLINT,
  isq                  SMALLINT,               -- estabilidad primaria
  injerto_oseo         BOOLEAN DEFAULT FALSE,
  material_injerto     TEXT,
  membrana             BOOLEAN DEFAULT FALSE,
  fecha_colocacion     DATE,
  fecha_carga          DATE,
  estado               estado_implante_t NOT NULL DEFAULT 'planificado',
  garantia_hasta       DATE,
  notas                TEXT,
  creado_en            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_implante_paciente ON implante (paciente_id);
CREATE INDEX idx_implante_lote ON implante (lote);

CREATE TABLE implante_evento (
  id            BIGSERIAL PRIMARY KEY,
  implante_id   BIGINT NOT NULL REFERENCES implante(id) ON DELETE CASCADE,
  fecha         DATE NOT NULL DEFAULT CURRENT_DATE,
  tipo          TEXT NOT NULL,                 -- colocacion, segunda_fase, control, carga, complicacion
  doctor_id     BIGINT REFERENCES doctor(id),
  isq           SMALLINT,
  hallazgos     TEXT,
  notas         TEXT
);

-- ---------------------------------------------------------------------
-- 10. DOCUMENTOS, RECETAS Y CONSENTIMIENTOS
-- ---------------------------------------------------------------------
CREATE TABLE documento_clinico (
  id            BIGSERIAL PRIMARY KEY,
  paciente_id   BIGINT NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
  consulta_id   BIGINT REFERENCES consulta(id),
  tipo          TEXT NOT NULL,                 -- radiografia_periapical, panoramica, cbct, foto, laboratorio
  codigo_fdi    SMALLINT REFERENCES diente(codigo_fdi),
  titulo        TEXT,
  url           TEXT NOT NULL,
  mime          TEXT,
  tomado_en     DATE,
  creado_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE prescripcion (
  id            BIGSERIAL PRIMARY KEY,
  paciente_id   BIGINT NOT NULL REFERENCES paciente(id),
  doctor_id     BIGINT NOT NULL REFERENCES doctor(id),
  consulta_id   BIGINT REFERENCES consulta(id),
  fecha         DATE NOT NULL DEFAULT CURRENT_DATE,
  indicaciones  TEXT
);

CREATE TABLE prescripcion_item (
  id                BIGSERIAL PRIMARY KEY,
  prescripcion_id   BIGINT NOT NULL REFERENCES prescripcion(id) ON DELETE CASCADE,
  medicamento       TEXT NOT NULL,
  presentacion      TEXT,
  dosis             TEXT NOT NULL,
  frecuencia        TEXT NOT NULL,
  duracion          TEXT
);

CREATE TABLE consentimiento (
  id            BIGSERIAL PRIMARY KEY,
  paciente_id   BIGINT NOT NULL REFERENCES paciente(id),
  plan_id       BIGINT REFERENCES plan_tratamiento(id),
  tipo          TEXT NOT NULL,                 -- implante, exodoncia, endodoncia, ortodoncia
  firmado_en    TIMESTAMPTZ,
  firmante      TEXT,
  url_documento TEXT
);

-- ---------------------------------------------------------------------
-- 11. FACTURACIÓN
-- ---------------------------------------------------------------------
CREATE TABLE factura (
  id              BIGSERIAL PRIMARY KEY,
  paciente_id     BIGINT NOT NULL REFERENCES paciente(id),
  sede_id         BIGINT REFERENCES sede(id),
  plan_id         BIGINT REFERENCES plan_tratamiento(id),
  numero          TEXT NOT NULL UNIQUE,        -- NCF / correlativo
  fecha           DATE NOT NULL DEFAULT CURRENT_DATE,
  moneda          CHAR(3) NOT NULL DEFAULT 'DOP',
  subtotal        NUMERIC(12,2) NOT NULL DEFAULT 0,
  descuento       NUMERIC(12,2) NOT NULL DEFAULT 0,
  impuesto        NUMERIC(12,2) NOT NULL DEFAULT 0,
  cubierto_seguro NUMERIC(12,2) NOT NULL DEFAULT 0,
  total           NUMERIC(12,2) NOT NULL DEFAULT 0,
  estado          estado_factura_t NOT NULL DEFAULT 'emitida',
  creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE factura_item (
  id                BIGSERIAL PRIMARY KEY,
  factura_id        BIGINT NOT NULL REFERENCES factura(id) ON DELETE CASCADE,
  procedimiento_id  BIGINT REFERENCES procedimiento(id),
  servicio_id       BIGINT NOT NULL REFERENCES servicio(id),
  descripcion       TEXT NOT NULL,
  cantidad          INT NOT NULL DEFAULT 1,
  precio_unit       NUMERIC(12,2) NOT NULL,
  descuento_pct     NUMERIC(5,2) NOT NULL DEFAULT 0,
  tasa_impuesto     NUMERIC(5,2) NOT NULL DEFAULT 0,
  total             NUMERIC(12,2) NOT NULL
);

CREATE TABLE pago (
  id            BIGSERIAL PRIMARY KEY,
  factura_id    BIGINT NOT NULL REFERENCES factura(id) ON DELETE CASCADE,
  fecha         DATE NOT NULL DEFAULT CURRENT_DATE,
  metodo        TEXT NOT NULL CHECK (metodo IN ('efectivo','tarjeta','transferencia','cheque','seguro','otro')),
  monto         NUMERIC(12,2) NOT NULL CHECK (monto > 0),
  referencia    TEXT,
  recibido_por  BIGINT REFERENCES usuario(id)
);

-- ---------------------------------------------------------------------
-- 12. VISTAS ÚTILES
-- ---------------------------------------------------------------------
CREATE VIEW v_odontograma_actual AS
SELECT p.id AS paciente_id, p.codigo AS expediente,
       d.codigo_fdi, d.nombre AS pieza, h.superficie,
       cd.codigo AS condicion, cd.nombre AS condicion_nombre,
       cd.color_hex, h.estado, h.fecha
FROM paciente p
JOIN odontograma o        ON o.paciente_id = p.id AND o.es_actual
JOIN odontograma_hallazgo h ON h.odontograma_id = o.id
JOIN diente d             ON d.codigo_fdi = h.codigo_fdi
JOIN condicion_dental cd  ON cd.id = h.condicion_dental_id;

CREATE VIEW v_estado_cuenta AS
SELECT f.paciente_id, f.id AS factura_id, f.numero, f.fecha, f.total,
       COALESCE(SUM(pg.monto),0) AS pagado,
       f.total - COALESCE(SUM(pg.monto),0) AS balance
FROM factura f
LEFT JOIN pago pg ON pg.factura_id = f.id
WHERE f.estado <> 'anulada'
GROUP BY f.id;

CREATE VIEW v_alertas_paciente AS
SELECT fm.paciente_id, 'condicion' AS tipo, cm.nombre AS detalle, cm.riesgo
FROM ficha_medica fm
JOIN ficha_condicion fc ON fc.ficha_id = fm.id
JOIN condicion_medica cm ON cm.id = fc.condicion_medica_id
WHERE cm.riesgo = 'alto'
UNION ALL
SELECT fm.paciente_id, 'alergia', a.nombre, fa.severidad
FROM ficha_medica fm
JOIN ficha_alergia fa ON fa.ficha_id = fm.id
JOIN alergia a ON a.id = fa.alergia_id;
