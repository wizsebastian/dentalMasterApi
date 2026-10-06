-- =====================================================================
-- SISTEMA DE REGISTRO ODONTOLÓGICO
-- 01_schema.sql  ·  PostgreSQL 16+
-- Módulos: sedes, doctores, pacientes, ficha médica, odontograma (FDI),
--          catálogo de servicios y precios, citas, planes de tratamiento,
--          procedimientos, implantes con trazabilidad, documentos y firmas,
--          cuenta del paciente, comprobantes fiscales, gastos e inventario.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gist;   -- restricciones de exclusión de la agenda
CREATE EXTENSION IF NOT EXISTS unaccent;      -- búsquedas: «gomez» encuentra «Gómez»

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
CREATE TYPE estado_factura_t    AS ENUM ('borrador','emitida','anulada');
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
  whatsapp      TEXT,                       -- número al que escriben los pacientes
  email         TEXT,
  web           TEXT,
  rnc           TEXT,                       -- identificación fiscal del negocio
  logo_archivo_id BIGINT,                   -- FK a archivo, más abajo: `archivo` se crea después
  onboarding_cerrado_en TIMESTAMPTZ,        -- la guía de primeros pasos se terminó u omitió
  catalogo_revisado_en  TIMESTAMPTZ,        -- paso de la guía sin dato observable: «revisé mis precios»
  activo        BOOLEAN NOT NULL DEFAULT TRUE,
  creado_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE unidad_dental (                -- sillón: recurso que la agenda no puede duplicar
  id            BIGSERIAL PRIMARY KEY,
  sede_id       BIGINT NOT NULL REFERENCES sede(id),
  nombre        TEXT NOT NULL,
  alquilada     BOOLEAN NOT NULL DEFAULT FALSE,
  orden         INT NOT NULL DEFAULT 0,
  activo        BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (sede_id, nombre)
);

-- Numeración sin huecos ni carreras: expedientes, planes y recibos.
-- Se avanza con INSERT ... ON CONFLICT DO UPDATE dentro de la misma transacción
-- que consume el número, de modo que un rollback lo devuelve.
CREATE TABLE correlativo (
  clave         TEXT PRIMARY KEY,           -- 'paciente:2026', 'plan:2026', 'recibo'
  ultimo        BIGINT NOT NULL DEFAULT 0 CHECK (ultimo >= 0)
);

CREATE TABLE especialidad (
  id            BIGSERIAL PRIMARY KEY,
  codigo        TEXT NOT NULL UNIQUE,
  nombre        TEXT NOT NULL,
  descripcion   TEXT,
  activo        BOOLEAN NOT NULL DEFAULT TRUE
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
  fecha_nacimiento  DATE,                          -- opcional: el alta rápida sólo pide nombre
  sexo              sexo_t,
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
  doctor_tratante_id BIGINT REFERENCES doctor(id),
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
  tipo    TEXT CHECK (tipo IN ('medicamento','material','alimento','otro')) DEFAULT 'medicamento',
  -- Nombres que delatan la alergia en una receta: «amoxicilina» para la penicilina.
  palabras_clave TEXT[] NOT NULL DEFAULT '{}'
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
  unidad_id     BIGINT REFERENCES unidad_dental(id),
  servicio_id   BIGINT REFERENCES servicio(id),      -- motivo estructurado; da la duración
  motivo        TEXT,                                -- matiz en texto libre
  estado        estado_cita_t NOT NULL DEFAULT 'agendada',
  notas         TEXT,
  sobrecupo     BOOLEAN NOT NULL DEFAULT FALSE,      -- única vía para solapar a propósito
  sobrecupo_motivo TEXT,
  recordatorio_enviado_en TIMESTAMPTZ,
  creado_por    BIGINT REFERENCES usuario(id),
  creado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (fin > inicio),
  CHECK (NOT sobrecupo OR sobrecupo_motivo IS NOT NULL),
  -- Un doctor y un sillón no pueden estar en dos citas vivas a la vez. Lo impide la
  -- base y no el servicio porque dos recepcionistas agendando a la vez son una carrera.
  CONSTRAINT ex_cita_doctor EXCLUDE USING gist
    (doctor_id WITH =, tstzrange(inicio, fin, '[)') WITH &&)
    WHERE (estado NOT IN ('cancelada','no_asistio') AND NOT sobrecupo),
  CONSTRAINT ex_cita_unidad EXCLUDE USING gist
    (unidad_id WITH =, tstzrange(inicio, fin, '[)') WITH &&)
    WHERE (unidad_id IS NOT NULL AND estado NOT IN ('cancelada','no_asistio') AND NOT sobrecupo)
);
CREATE INDEX idx_cita_agenda ON cita (doctor_id, inicio);
CREATE INDEX idx_cita_paciente ON cita (paciente_id, inicio DESC);

-- Historial de la cita: reprogramar conserva la identidad de la cita y deja rastro,
-- en lugar de cancelar y crear otra.
CREATE TABLE cita_evento (
  id              BIGSERIAL PRIMARY KEY,
  cita_id         BIGINT NOT NULL REFERENCES cita(id) ON DELETE CASCADE,
  tipo            TEXT NOT NULL CHECK (tipo IN ('creada','reprogramada','estado','recordatorio')),
  inicio_anterior TIMESTAMPTZ,
  inicio_nuevo    TIMESTAMPTZ,
  estado_anterior estado_cita_t,
  estado_nuevo    estado_cita_t,
  motivo          TEXT,
  usuario_id      BIGINT REFERENCES usuario(id),
  ocurrido_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_cita_evento ON cita_evento (cita_id, ocurrido_en);

CREATE TABLE consulta (
  id                BIGSERIAL PRIMARY KEY,
  paciente_id       BIGINT NOT NULL REFERENCES paciente(id),
  doctor_id         BIGINT NOT NULL REFERENCES doctor(id),
  cita_id           BIGINT REFERENCES cita(id),
  plan_id           BIGINT,                        -- NULL = consulta suelta; FK compuesta en la sección 8
  unidad_id         BIGINT REFERENCES unidad_dental(id),
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
  notas             TEXT,
  creado_en         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (id, paciente_id)                         -- destino de las FK compuestas
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
  procedimiento_id    BIGINT,                      -- línea ejecutada que lo pintó; FK en la sección 8
  plan_item_id        BIGINT,                      -- ítem del plan que lo propuso; FK en la sección 8
  -- NULLS NOT DISTINCT: sin él, dos hallazgos de pieza completa (superficie NULL)
  -- idénticos no chocarían.
  UNIQUE NULLS NOT DISTINCT (odontograma_id, codigo_fdi, superficie, condicion_dental_id, estado)
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
  especialidad_id BIGINT REFERENCES especialidad(id), -- NULL = plan que cruza especialidades
  titulo          TEXT,
  codigo          TEXT NOT NULL UNIQUE,          -- PT-2026-0001
  fecha           DATE NOT NULL DEFAULT CURRENT_DATE,
  estado          estado_plan_t NOT NULL DEFAULT 'borrador',
  descuento_pct   NUMERIC(5,2) NOT NULL DEFAULT 0,
  notas           TEXT,
  cerrado_en      TIMESTAMPTZ,
  creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (id, paciente_id)                       -- destino de las FK compuestas
);

-- El plan es la carpeta clínica: agrupa consultas, se cotiza y se consiente.
-- La FK compuesta impide colgar una consulta del plan de otro paciente.
ALTER TABLE consulta
  ADD CONSTRAINT fk_consulta_plan FOREIGN KEY (plan_id, paciente_id)
      REFERENCES plan_tratamiento (id, paciente_id);
ALTER TABLE cita
  ADD COLUMN plan_id BIGINT REFERENCES plan_tratamiento(id);

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
  consulta_id     BIGINT NOT NULL,                -- toda línea ejecutada pertenece a una visita
  plan_item_id    BIGINT REFERENCES plan_item(id),
  codigo_fdi      SMALLINT REFERENCES diente(codigo_fdi),
  superficies     TEXT,
  fecha           DATE NOT NULL DEFAULT CURRENT_DATE,
  estado          estado_proc_t NOT NULL DEFAULT 'completado',
  anestesia       TEXT,
  materiales      TEXT,
  cantidad        INT NOT NULL DEFAULT 1 CHECK (cantidad > 0),
  precio          NUMERIC(12,2) NOT NULL DEFAULT 0,          -- unitario
  descuento_pct   NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (descuento_pct BETWEEN 0 AND 100),
  -- El cargo al paciente. Generada, como plan_item.total: nunca se inserta a mano.
  total           NUMERIC(12,2) GENERATED ALWAYS AS
                  (ROUND(cantidad * precio * (1 - descuento_pct/100), 2)) STORED,
  notas           TEXT,
  creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (consulta_id, paciente_id) REFERENCES consulta (id, paciente_id)
);
CREATE INDEX idx_proc_paciente ON procedimiento (paciente_id, fecha DESC);
CREATE INDEX idx_proc_consulta ON procedimiento (consulta_id);

ALTER TABLE odontograma_hallazgo
  ADD CONSTRAINT fk_hallazgo_procedimiento FOREIGN KEY (procedimiento_id)
      REFERENCES procedimiento(id) ON DELETE SET NULL,
  -- SET NULL y no CASCADE: quitar un ítem no reescribe los odontogramas históricos.
  ADD CONSTRAINT fk_hallazgo_plan_item FOREIGN KEY (plan_item_id)
      REFERENCES plan_item(id) ON DELETE SET NULL;
CREATE INDEX idx_hallazgo_plan_item ON odontograma_hallazgo (plan_item_id) WHERE plan_item_id IS NOT NULL;

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
-- Un archivo guardado en el almacén. La ruta en disco se deriva del sha256
-- (direccionado por contenido): la base no guarda rutas, y dos subidas del
-- mismo archivo comparten los mismos bytes.
CREATE TABLE archivo (
  id              BIGSERIAL PRIMARY KEY,
  sha256          CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  nombre_original TEXT NOT NULL,
  mime            TEXT NOT NULL,
  bytes           BIGINT NOT NULL CHECK (bytes > 0),
  subido_por      BIGINT REFERENCES usuario(id),
  creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_archivo_sha256 ON archivo (sha256);

-- El logo de la clínica es un archivo más del almacén; lo usan todos los impresos.
ALTER TABLE sede
  ADD CONSTRAINT fk_sede_logo FOREIGN KEY (logo_archivo_id) REFERENCES archivo(id) ON DELETE SET NULL;

-- Fotos, radiografías y exámenes del paciente. Con `consulta_id` es una foto
-- de esa visita; sin él, un examen suelto del expediente.
CREATE TABLE documento_clinico (
  id            BIGSERIAL PRIMARY KEY,
  paciente_id   BIGINT NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
  consulta_id   BIGINT REFERENCES consulta(id),
  tipo          TEXT NOT NULL,                 -- radiografia_periapical, panoramica, cbct, foto, laboratorio
  codigo_fdi    SMALLINT REFERENCES diente(codigo_fdi),
  titulo        TEXT,
  archivo_id    BIGINT REFERENCES archivo(id),
  url           TEXT,                          -- referencia externa: el archivo vive fuera del almacén
  mime          TEXT,
  tomado_en     DATE,
  creado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (archivo_id IS NOT NULL OR url IS NOT NULL)
);
CREATE INDEX idx_documento_clinico_paciente ON documento_clinico (paciente_id, creado_en DESC);

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

-- Plantillas de los documentos que se entregan o se firman. El cuerpo lleva
-- variables como {{paciente.nombre}}, que se combinan al emitir.
CREATE TABLE plantilla_documento (
  id              BIGSERIAL PRIMARY KEY,
  codigo          TEXT NOT NULL UNIQUE,
  tipo            TEXT NOT NULL CHECK (tipo IN ('constancia','licencia','postoperatorio',
                                                'consentimiento','consentimiento_datos')),
  titulo          TEXT NOT NULL,
  cuerpo          TEXT NOT NULL,
  especialidad_id BIGINT REFERENCES especialidad(id),
  requiere_firma  BOOLEAN NOT NULL DEFAULT FALSE,
  activo          BOOLEAN NOT NULL DEFAULT TRUE
);

-- Un documento ya emitido es inmutable: guarda el texto final, no la plantilla.
-- Corregirlo es anularlo y emitir otro. El hash permite comprobar que lo firmado
-- es lo que se guardó.
CREATE TABLE documento_emitido (
  id              BIGSERIAL PRIMARY KEY,
  paciente_id     BIGINT NOT NULL REFERENCES paciente(id),
  tipo            TEXT NOT NULL CHECK (tipo IN ('constancia','licencia','postoperatorio',
                                                'consentimiento','consentimiento_datos')),
  plantilla_id    BIGINT REFERENCES plantilla_documento(id),
  titulo          TEXT NOT NULL,
  cuerpo          TEXT NOT NULL,
  consulta_id     BIGINT REFERENCES consulta(id),
  plan_id         BIGINT REFERENCES plan_tratamiento(id),
  doctor_id       BIGINT REFERENCES doctor(id),
  requiere_firma  BOOLEAN NOT NULL DEFAULT FALSE,
  sha256          CHAR(64) NOT NULL,
  emitido_por     BIGINT REFERENCES usuario(id),
  emitido_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
  anulado_en      TIMESTAMPTZ,
  motivo_anulacion TEXT,
  CHECK ((anulado_en IS NULL) = (motivo_anulacion IS NULL))
);
CREATE INDEX idx_documento_paciente ON documento_emitido (paciente_id, emitido_en DESC);

-- La firma manuscrita: el trazo, quién firmó y el hash de lo que firmó.
CREATE TABLE firma (
  id                   BIGSERIAL PRIMARY KEY,
  documento_emitido_id BIGINT NOT NULL REFERENCES documento_emitido(id) ON DELETE CASCADE,
  firmante_nombre      TEXT NOT NULL,
  firmante_rol         TEXT NOT NULL CHECK (firmante_rol IN ('paciente','tutor','doctor','testigo')),
  firmante_documento   TEXT,
  trazo                JSONB NOT NULL,          -- lista de trazos; cada uno, lista de puntos [x, y]
  hash_documento       CHAR(64) NOT NULL,
  firmado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
  dispositivo          TEXT,
  ip                   INET
);

-- ---------------------------------------------------------------------
-- 11. CUENTA DEL PACIENTE Y COMPROBANTES FISCALES
--     Lo que el paciente debe son sus procedimientos ejecutados; lo que ha
--     entrado son sus pagos. La factura es el comprobante fiscal (NCF) que se
--     emite sólo a petición: no genera deuda ni recibe pagos.
-- ---------------------------------------------------------------------
CREATE TABLE factura (
  id              BIGSERIAL PRIMARY KEY,
  paciente_id     BIGINT NOT NULL REFERENCES paciente(id),
  sede_id         BIGINT REFERENCES sede(id),
  plan_id         BIGINT REFERENCES plan_tratamiento(id),
  numero          TEXT NOT NULL UNIQUE,        -- NCF
  tipo_ncf        TEXT,                        -- B01 crédito fiscal, B02 consumo…
  ncf_vence       DATE,                        -- «válido hasta» de la secuencia, impreso en el comprobante
  rnc_cliente     TEXT,
  razon_social    TEXT,
  fecha           DATE NOT NULL DEFAULT CURRENT_DATE,
  moneda          CHAR(3) NOT NULL DEFAULT 'DOP',
  subtotal        NUMERIC(12,2) NOT NULL DEFAULT 0,
  descuento       NUMERIC(12,2) NOT NULL DEFAULT 0,
  impuesto        NUMERIC(12,2) NOT NULL DEFAULT 0,
  cubierto_seguro NUMERIC(12,2) NOT NULL DEFAULT 0,
  total           NUMERIC(12,2) NOT NULL DEFAULT 0,
  estado          estado_factura_t NOT NULL DEFAULT 'emitida',
  emitida_por     BIGINT REFERENCES usuario(id),
  creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Un NCF emitido no se borra ni se reutiliza: la factura se anula.
  anulada_en      TIMESTAMPTZ,
  anulada_por     BIGINT REFERENCES usuario(id),
  motivo_anulacion TEXT,
  CHECK (numero ~ '^(B[0-9]{10}|E[0-9]{12})$'),
  CHECK ((estado = 'anulada') = (anulada_en IS NOT NULL)),
  CHECK ((anulada_en IS NULL) = (motivo_anulacion IS NULL))
);
CREATE INDEX idx_factura_paciente ON factura (paciente_id, fecha DESC);

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
CREATE INDEX idx_factura_item_procedimiento ON factura_item (procedimiento_id);

-- Rangos de NCF autorizados por la DGII. Cada factura toma el siguiente número
-- de la secuencia activa de su tipo; al agotarse o vencer se carga otra.
CREATE TABLE secuencia_ncf (
  id          BIGSERIAL PRIMARY KEY,
  tipo        TEXT NOT NULL CHECK (tipo ~ '^[BE][0-9]{2}$'),   -- B01 crédito fiscal, B02 consumo, B14, B15; E31, E32 = e-CF
  desde       BIGINT NOT NULL CHECK (desde > 0),
  hasta       BIGINT NOT NULL,
  siguiente   BIGINT NOT NULL,
  vence       DATE,
  activo      BOOLEAN NOT NULL DEFAULT TRUE,
  creado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (hasta >= desde),
  CHECK (siguiente BETWEEN desde AND hasta + 1)                -- hasta + 1 = agotada
);
CREATE UNIQUE INDEX uq_secuencia_ncf_activa ON secuencia_ncf (tipo) WHERE activo;

CREATE TABLE pago (
  id            BIGSERIAL PRIMARY KEY,
  paciente_id   BIGINT NOT NULL REFERENCES paciente(id),   -- el pago es del paciente; admite anticipos
  numero_recibo BIGINT NOT NULL UNIQUE,                    -- correlativo 'recibo'
  fecha         DATE NOT NULL DEFAULT CURRENT_DATE,
  metodo        TEXT NOT NULL CHECK (metodo IN ('efectivo','tarjeta','transferencia','cheque','seguro','otro')),
  monto         NUMERIC(12,2) NOT NULL CHECK (monto > 0),
  concepto      TEXT,
  referencia    TEXT,
  comprobante_id BIGINT REFERENCES archivo(id),            -- voucher o captura de la transferencia
  recibido_por  BIGINT REFERENCES usuario(id),
  registrado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Un pago nunca se borra ni cambia de monto: se anula y conserva su número.
  anulado_en    TIMESTAMPTZ,
  anulado_por   BIGINT REFERENCES usuario(id),
  motivo_anulacion TEXT,
  CHECK ((anulado_en IS NULL) = (motivo_anulacion IS NULL)),
  UNIQUE (id, paciente_id)
);
CREATE INDEX idx_pago_paciente ON pago (paciente_id, fecha DESC);

-- A qué consultas se imputa cada pago. Lo que un pago no tiene aplicado es
-- crédito a favor del paciente. Persistir la aplicación hace estable la
-- atribución: lo cobrado por una consulta no cambia al registrar otra.
CREATE TABLE pago_aplicacion (
  id            BIGSERIAL PRIMARY KEY,
  pago_id       BIGINT NOT NULL,
  consulta_id   BIGINT NOT NULL,
  paciente_id   BIGINT NOT NULL,
  monto         NUMERIC(12,2) NOT NULL CHECK (monto > 0),
  creado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (pago_id, consulta_id),
  FOREIGN KEY (pago_id, paciente_id)     REFERENCES pago (id, paciente_id) ON DELETE CASCADE,
  FOREIGN KEY (consulta_id, paciente_id) REFERENCES consulta (id, paciente_id)
);
CREATE INDEX idx_aplicacion_consulta ON pago_aplicacion (consulta_id);

-- Cierre de caja: la foto del día. No cambia aunque después se anule un pago;
-- lo que se mueva tras el cierre se ve como diferencia contra la caja viva.
CREATE TABLE cierre_caja (
  id                BIGSERIAL PRIMARY KEY,
  fecha             DATE NOT NULL UNIQUE,
  cobrado           NUMERIC(12,2) NOT NULL,                    -- todos los métodos, sin anulados
  efectivo_esperado NUMERIC(12,2) NOT NULL,                    -- cobros en efectivo − gastos en efectivo
  efectivo_contado  NUMERIC(12,2) NOT NULL CHECK (efectivo_contado >= 0),
  diferencia        NUMERIC(12,2) GENERATED ALWAYS AS (efectivo_contado - efectivo_esperado) STORED,
  desglose          JSONB NOT NULL,                            -- totales por método al cerrar
  notas             TEXT,
  cerrado_por       BIGINT REFERENCES usuario(id),
  cerrado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (efectivo_contado = efectivo_esperado OR notas IS NOT NULL)   -- un descuadre se explica
);

-- ---------------------------------------------------------------------
-- 12. GASTOS E INVENTARIO
--     Un solo catálogo de insumos. La existencia no es una columna: es la suma
--     de un kárdex de sólo inserción, igual que el saldo es la suma de los pagos.
-- ---------------------------------------------------------------------
CREATE TABLE categoria_gasto (
  id      BIGSERIAL PRIMARY KEY,
  nombre  TEXT NOT NULL,
  activo  BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX uq_categoria_gasto ON categoria_gasto (lower(nombre));

CREATE TABLE proveedor (
  id        BIGSERIAL PRIMARY KEY,
  nombre    TEXT NOT NULL,
  rnc       TEXT UNIQUE,
  telefono  TEXT,
  activo    BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX uq_proveedor_nombre ON proveedor (lower(nombre));

CREATE TABLE gasto (
  id             BIGSERIAL PRIMARY KEY,
  fecha          DATE NOT NULL DEFAULT CURRENT_DATE,
  monto          NUMERIC(12,2) NOT NULL CHECK (monto > 0),      -- total pagado, ITBIS incluido
  itbis          NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (itbis >= 0),
  categoria_id   BIGINT NOT NULL REFERENCES categoria_gasto(id),
  descripcion    TEXT NOT NULL,
  tipo           TEXT NOT NULL CHECK (tipo IN ('consultorio','doctor','personal')),
  doctor_id      BIGINT REFERENCES doctor(id),
  paciente_id    BIGINT REFERENCES paciente(id),                -- costo de un caso (laboratorio)
  metodo         TEXT NOT NULL CHECK (metodo IN ('efectivo','tarjeta','transferencia','cheque','seguro','otro')),
  proveedor_id   BIGINT REFERENCES proveedor(id),
  tipo_ncf       TEXT,
  ncf            TEXT CHECK (ncf IS NULL OR ncf ~ '^(B[0-9]{10}|E[0-9]{12})$'),
  comprobante_id BIGINT REFERENCES archivo(id),                 -- foto o PDF de la factura del proveedor
  notas          TEXT,
  registrado_por BIGINT REFERENCES usuario(id),
  registrado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
  anulado_en     TIMESTAMPTZ,
  anulado_por    BIGINT REFERENCES usuario(id),
  motivo_anulacion TEXT,
  CHECK ((tipo = 'doctor') = (doctor_id IS NOT NULL)),          -- el honorario dice de quién es
  CHECK ((anulado_en IS NULL) = (motivo_anulacion IS NULL)),
  CHECK (itbis <= monto),
  UNIQUE (proveedor_id, ncf)                                    -- un comprobante no se registra dos veces
);
CREATE INDEX idx_gasto_fecha ON gasto (fecha DESC);

CREATE TABLE categoria_insumo (
  id      BIGSERIAL PRIMARY KEY,
  nombre  TEXT NOT NULL
);
CREATE UNIQUE INDEX uq_categoria_insumo ON categoria_insumo (lower(nombre));

CREATE TABLE insumo (
  id             BIGSERIAL PRIMARY KEY,
  nombre         TEXT NOT NULL,
  categoria_id   BIGINT REFERENCES categoria_insumo(id),
  marca          TEXT,
  modelo         TEXT,
  unidad         TEXT NOT NULL DEFAULT 'unidad',
  controla_stock BOOLEAN NOT NULL DEFAULT TRUE,                 -- FALSE: servicios de laboratorio externo
  stock_minimo   NUMERIC(12,3) NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
  costo          NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (costo >= 0),   -- último costo por unidad
  notas          TEXT,
  activo         BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX uq_insumo_nombre ON insumo (lower(nombre));

-- Kárdex. Con signo: positivo entra, negativo sale. No se actualiza ni se borra:
-- un error se corrige con otro movimiento.
CREATE TABLE movimiento_insumo (
  id               BIGSERIAL PRIMARY KEY,
  insumo_id        BIGINT NOT NULL REFERENCES insumo(id),
  cantidad         NUMERIC(12,3) NOT NULL CHECK (cantidad <> 0),
  motivo           TEXT NOT NULL CHECK (motivo IN ('inicial','compra','consumo','merma','conteo','devolucion')),
  costo_unit       NUMERIC(12,2),
  gasto_id         BIGINT REFERENCES gasto(id),                 -- la compra que lo trajo
  procedimiento_id BIGINT REFERENCES procedimiento(id) ON DELETE SET NULL, -- la línea que lo consumió
  nota             TEXT,
  usuario_id       BIGINT REFERENCES usuario(id),
  ocurrido_en      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_movimiento_insumo ON movimiento_insumo (insumo_id, ocurrido_en DESC);

-- Receta: qué insumos gasta un servicio. Da su costo y descuenta existencia al ejecutarlo.
CREATE TABLE servicio_insumo (
  servicio_id BIGINT NOT NULL REFERENCES servicio(id) ON DELETE CASCADE,
  insumo_id   BIGINT NOT NULL REFERENCES insumo(id),
  cantidad    NUMERIC(12,3) NOT NULL CHECK (cantidad > 0),
  PRIMARY KEY (servicio_id, insumo_id)
);

-- ---------------------------------------------------------------------
-- 13. VISTAS ÚTILES
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

-- Cargos y aplicaciones se agregan en subconsultas separadas: unirlos antes de
-- sumar multiplicaría filas.
CREATE VIEW v_saldo_consulta AS
SELECT c.id AS consulta_id, c.paciente_id, c.plan_id, c.doctor_id, c.fecha,
       COALESCE(cg.total, 0)                            AS total,
       COALESCE(ap.aplicado, 0)                         AS aplicado,
       COALESCE(cg.total, 0) - COALESCE(ap.aplicado, 0) AS saldo
FROM consulta c
LEFT JOIN (SELECT consulta_id, SUM(total) AS total
             FROM procedimiento
            WHERE estado IN ('en_proceso','completado')
            GROUP BY consulta_id) cg ON cg.consulta_id = c.id
LEFT JOIN (SELECT a.consulta_id, SUM(a.monto) AS aplicado
             FROM pago_aplicacion a
             JOIN pago pg ON pg.id = a.pago_id AND pg.anulado_en IS NULL
            GROUP BY a.consulta_id) ap ON ap.consulta_id = c.id;

-- Estado de cuenta por paciente. balance > 0 = debe; balance < 0 = crédito a favor.
CREATE VIEW v_estado_cuenta AS
SELECT p.id AS paciente_id,
       COALESCE(cg.cargos, 0)                             AS cargos,
       COALESCE(pg.pagado, 0)                             AS pagado,
       COALESCE(pg.pagado, 0) - COALESCE(ap.aplicado, 0)  AS credito_sin_aplicar,
       COALESCE(cg.cargos, 0) - COALESCE(pg.pagado, 0)    AS balance
FROM paciente p
LEFT JOIN (SELECT paciente_id, SUM(total) AS cargos
             FROM procedimiento
            WHERE estado IN ('en_proceso','completado')
            GROUP BY paciente_id) cg ON cg.paciente_id = p.id
LEFT JOIN (SELECT paciente_id, SUM(monto) AS pagado
             FROM pago
            WHERE anulado_en IS NULL
            GROUP BY paciente_id) pg ON pg.paciente_id = p.id
LEFT JOIN (SELECT a.paciente_id, SUM(a.monto) AS aplicado
             FROM pago_aplicacion a
             JOIN pago pg2 ON pg2.id = a.pago_id AND pg2.anulado_en IS NULL
            GROUP BY a.paciente_id) ap ON ap.paciente_id = p.id;

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

-- Existencia de cada insumo = suma de su kárdex. La alerta salta con existencia <= mínimo.
CREATE VIEW v_existencia_insumo AS
SELECT i.id AS insumo_id,
       COALESCE(m.existencia, 0)                AS existencia,
       (COALESCE(m.existencia, 0) * i.costo)::numeric(14,2) AS valor,
       (i.controla_stock AND COALESCE(m.existencia, 0) <= i.stock_minimo) AS bajo_minimo
FROM insumo i
LEFT JOIN (SELECT insumo_id, SUM(cantidad) AS existencia
             FROM movimiento_insumo GROUP BY insumo_id) m ON m.insumo_id = i.id;

-- Lo que cuesta en insumos ejecutar un servicio una vez, según su receta.
CREATE VIEW v_costo_servicio AS
SELECT si.servicio_id, SUM(si.cantidad * i.costo)::numeric(12,2) AS costo_insumos
FROM servicio_insumo si
JOIN insumo i ON i.id = si.insumo_id
GROUP BY si.servicio_id;
