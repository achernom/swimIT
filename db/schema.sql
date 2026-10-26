-- Esquema normalizado (compatible SQLite / PostgreSQL con cambios menores de tipos)
CREATE TABLE meet (
  meet_id      TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  city         TEXT,
  start_date   DATE NOT NULL,
  course       TEXT CHECK (course IN ('LCM','SCM','?')),   -- LCM = pileta 50 m, SCM = 25 m
  source_file  TEXT
);
CREATE TABLE team (
  team_id  INTEGER PRIMARY KEY,
  name     TEXT UNIQUE NOT NULL
);
CREATE TABLE swimmer (
  swimmer_id  INTEGER PRIMARY KEY,
  full_name   TEXT NOT NULL,
  gender      TEXT CHECK (gender IN ('M','F')),
  birth_year  INTEGER                 -- inferido: año del torneo - edad
);
CREATE TABLE event (
  event_id    INTEGER PRIMARY KEY,
  meet_id     TEXT REFERENCES meet(meet_id),
  event_num   INTEGER,
  gender      TEXT,                    -- M / F / X (mixto)
  age_group   TEXT,                    -- 18-24, 25-29 ... o suma de edades en relevos
  distance_m  INTEGER,
  stroke      TEXT,                    -- Libre, Espalda, Pecho, Mariposa, Combinado
  course      TEXT,
  division    TEXT,                    -- LIB (libres), FED (federados), OPEN, REL
  is_relay    INTEGER DEFAULT 0,
  is_special  INTEGER DEFAULT 0        -- golden race / finales open 20-100
);
CREATE TABLE result (
  result_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id    INTEGER REFERENCES event(event_id),
  swimmer_id  INTEGER REFERENCES swimmer(swimmer_id),
  team_id     INTEGER REFERENCES team(team_id),
  age         INTEGER,
  place       INTEGER,
  seed_s      REAL,
  time_s      REAL,
  status      TEXT,                    -- OK, DQ, NS, DNF
  points      REAL,
  fina_pts    INTEGER,                 -- puntos World Aquatics aproximados
  raw_name    TEXT                     -- nombre tal cual figura en el PDF (trazabilidad)
);
CREATE TABLE relay_result (
  relay_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id  INTEGER REFERENCES event(event_id),
  team_id   INTEGER REFERENCES team(team_id),
  letter    TEXT,
  place     INTEGER,
  time_s    REAL,
  status    TEXT
);
CREATE INDEX ix_result_swimmer ON result(swimmer_id);
CREATE INDEX ix_result_event   ON result(event_id);
CREATE INDEX ix_event_meet     ON event(meet_id, stroke, distance_m);
