"""Ayudas compartidas extraídas de test_migraciones; datos inventados."""

from __future__ import annotations


import hashlib


import sqlite3


from pathlib import Path


import pytest


from alembic.autogenerate import compare_metadata


from alembic.runtime.migration import MigrationContext


from sqlalchemy import create_engine


from finanzas import db, migrar


from finanzas.migraciones import esquema_v1


TABLAS = ("categorias", "movimientos", "reglas", "configuracion_saldo", "correos_no_reconocidos")


TABLAS_POSTERIORES_A_V1 = ("estado_sincronizacion",)


def crear_base_v1(ruta: Path) -> None:
    """Base "de la v1": estructura de ESQUEMA_V1 y datos inventados en todas las tablas."""
    conn = sqlite3.connect(ruta)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            conn.executescript(esquema_v1.ESQUEMA_V1)
            conn.executemany(
                "INSERT OR IGNORE INTO categorias (nombre) VALUES (?)",
                [(nombre,) for nombre in db.CATEGORIAS_FIJAS],
            )
            conn.execute(
                "INSERT INTO configuracion_saldo VALUES (1, 123456789, '2026-08-01')"
            )
            conn.executemany(
                "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, "
                "categoria_id, origen, gmail_id, registrado_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("2026-08-02T10:15:00", 6863000, "compra", "COMERCIO INVENTADO ZXQ", 1,
                     "gmail", "id-inventado-1", "2026-08-02T15:16:00"),
                    ("2026-08-03T11:00:00", 600000, "transferencia", "*9999", None,
                     "gmail", "id-inventado-2", "2026-08-03T16:01:00"),
                    ("2026-08-04T09:00:00", 16000000, "ingreso", "PERSONA INVENTADA", None,
                     "gmail", "id-inventado-3", "2026-08-04T14:00:00"),
                    ("2026-08-05T08:30:00", 2500000, "ingreso", "Efectivo inventado", None,
                     "manual", None, "2026-08-05T13:30:00"),
                    ("2026-08-06T12:00:00", -45678, "ajuste", "Ajuste de saldo", None,
                     "manual", None, "2026-08-06T17:00:00"),
                ],
            )
            # Uno con la fecha de registro por defecto (strftime de SQLite).
            conn.execute(
                "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
                "VALUES ('2026-08-07T16:42:00', 1, 'compra', '', 'gmail', 'id-inventado-4')"
            )
            conn.execute(
                "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'comercio inventado zxq', 1)"
            )
            conn.execute(
                "INSERT INTO correos_no_reconocidos VALUES ('id-inventado-5', '2026-08-08T07:00:00', 'Asunto inventado')"
            )
    finally:
        conn.close()


COLUMNAS_V1 = {
    "movimientos": (
        "id, fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id, "
        "registrado_en"
    ),
    "categorias": "id, nombre",
    "reglas": "id, campo, texto, categoria_id",
}


CATEGORIAS_DE_LA_0005 = ("Antojos", "Sueldo", "Préstamos", "Otros ingresos")


CATEGORIAS_DE_LA_0006 = ("Retiro a efectivo", "Pago de tarjeta")


FILTRO_V1 = {
    "categorias": "WHERE nombre NOT IN ({})".format(
        ", ".join(f"'{n}'" for n in CATEGORIAS_DE_LA_0005 + CATEGORIAS_DE_LA_0006)
    ),
}


def volcado(ruta: Path) -> dict[str, list[tuple]]:
    """Todas las filas de las tablas de la app (con el id y las columnas de la v1), en orden."""
    conn = sqlite3.connect(ruta)
    try:
        return {
            t: conn.execute(
                f"SELECT {COLUMNAS_V1.get(t, '*')} FROM {t} {FILTRO_V1.get(t, '')} ORDER BY 1"
            ).fetchall()
            for t in TABLAS
        }
    finally:
        conn.close()


def huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def revision(ruta: Path) -> str | None:
    conn = db.conectar(str(ruta))
    try:
        return db.revision_actual(conn)
    finally:
        conn.close()


ESQUEMA_0005 = """
CREATE TABLE categorias (
    id INTEGER,
    nombre TEXT NOT NULL CHECK (nombre <> ''),
    clase TEXT NOT NULL CHECK (clase IN ('gasto', 'ingreso')),
    color TEXT NOT NULL CHECK (color <> ''),
    icono TEXT NOT NULL CHECK (icono <> ''),
    PRIMARY KEY (id),
    UNIQUE (nombre, clase)
);
CREATE TABLE reglas (
    id INTEGER,
    campo TEXT NOT NULL CHECK (campo IN ('comercio', 'cuenta_destino', 'quien_envia')),
    texto TEXT CHECK (texto IS NULL OR texto <> ''),
    categoria_id INTEGER NOT NULL,
    monto_centavos INTEGER CHECK (monto_centavos IS NULL OR monto_centavos > 0)
        CHECK (monto_centavos IS NULL OR typeof(monto_centavos) = 'integer'),
    PRIMARY KEY (id),
    CHECK (texto IS NOT NULL OR monto_centavos IS NOT NULL),
    FOREIGN KEY (categoria_id) REFERENCES categorias (id)
);
CREATE UNIQUE INDEX ux_reglas_condiciones ON reglas
    (campo, COALESCE(texto, ''), COALESCE(monto_centavos, 0));
"""


ESQUEMA_0008 = """
CREATE TABLE movimientos (
    id INTEGER,
    fecha_hora TEXT NOT NULL,
    monto_centavos INTEGER NOT NULL CHECK (typeof(monto_centavos) = 'integer'),
    tipo TEXT NOT NULL CHECK (tipo IN ('compra', 'transferencia', 'ingreso', 'ajuste')),
    descripcion TEXT DEFAULT '' NOT NULL,
    categoria_id INTEGER,
    origen TEXT NOT NULL CHECK (origen IN ('gmail', 'manual', 'extracto')),
    gmail_id TEXT,
    registrado_en TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')) NOT NULL,
    origen_categoria TEXT CHECK (origen_categoria IN ('manual', 'regla')),
    regla_id INTEGER,
    estado TEXT CHECK (estado IN ('confirmado', 'provisional', 'sin_aviso')),
    referencia TEXT CHECK (referencia IS NULL OR referencia GLOB '[*][0-9][0-9][0-9][0-9]'),
    fecha_banco TEXT CHECK (fecha_banco IS NULL OR fecha_banco GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    no_en_banco INTEGER DEFAULT '0' NOT NULL CHECK (no_en_banco IN (0, 1)),
    PRIMARY KEY (id),
    CHECK (tipo = 'ajuste' OR monto_centavos > 0),
    CHECK ((origen = 'gmail' AND gmail_id IS NOT NULL) OR (origen = 'manual' AND gmail_id IS NULL) OR origen = 'extracto'),
    CHECK (regla_id IS NULL OR COALESCE(origen_categoria, '') = 'regla'),
    CHECK (CASE origen WHEN 'extracto' THEN COALESCE(estado, '') IN ('confirmado', 'sin_aviso') WHEN 'manual' THEN (tipo = 'ajuste' AND estado IS NULL) OR (tipo <> 'ajuste' AND COALESCE(estado, 'provisional') IN ('provisional', 'confirmado')) ELSE estado IS NULL OR estado = 'confirmado' END),
    CHECK ((fecha_banco IS NOT NULL) = (COALESCE(estado, '') IN ('confirmado', 'sin_aviso'))),
    CHECK (no_en_banco = 0 OR (origen = 'gmail' AND estado IS NULL)),
    CHECK (referencia IS NULL OR fecha_banco IS NOT NULL),
    FOREIGN KEY (categoria_id) REFERENCES categorias (id),
    UNIQUE (gmail_id),
    FOREIGN KEY (regla_id) REFERENCES reglas (id)
);
CREATE INDEX idx_movimientos_fecha_hora ON movimientos (fecha_hora);
CREATE TABLE importaciones (
    id INTEGER,
    hecha_en TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')) NOT NULL,
    desde TEXT CHECK (desde IS NULL OR desde GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    hasta TEXT CHECK (hasta IS NULL OR hasta GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
""" + "".join(
    f"    {c} INTEGER DEFAULT '0' NOT NULL CHECK (typeof({c}) = 'integer') CHECK ({c} >= 0),\n"
    for c in ("filas", "ya_estaban", "agregados", "confirmados", "corregidos", "preguntas",
              "no_en_banco", "anteriores", "sin_formato")
) + """
    deshecha_en TEXT,
    PRIMARY KEY (id)
);
CREATE TABLE cambios_importacion (
    id INTEGER,
    importacion_id INTEGER NOT NULL,
    movimiento_id INTEGER NOT NULL,
    accion TEXT NOT NULL CHECK (accion IN ('agregado', 'confirmado', 'corregido', 'marcado', 'ajuste_reducido')),
    monto_anterior INTEGER,
    estado_anterior TEXT,
    no_en_banco_anterior INTEGER,
    fecha_banco_anterior TEXT,
    referencia_anterior TEXT CHECK (referencia_anterior IS NULL OR referencia_anterior GLOB '[*][0-9][0-9][0-9][0-9]'),
    PRIMARY KEY (id),
    UNIQUE (importacion_id, movimiento_id, accion),
    FOREIGN KEY (importacion_id) REFERENCES importaciones (id),
    FOREIGN KEY (movimiento_id) REFERENCES movimientos (id)
);
CREATE TABLE preguntas_conciliacion (
    id INTEGER,
    tipo TEXT NOT NULL CHECK (tipo IN ('es_el_mismo', 'ya_estaba_en_ajuste')),
    fuente TEXT NOT NULL CHECK (fuente IN ('banco', 'correo')),
    importacion_id INTEGER,
    creada_en TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')) NOT NULL,
    fecha TEXT NOT NULL,
    monto_centavos INTEGER NOT NULL CHECK (typeof(monto_centavos) = 'integer') CHECK (monto_centavos <> 0),
    descripcion TEXT DEFAULT '' NOT NULL,
    referencia TEXT CHECK (referencia IS NULL OR referencia GLOB '[*][0-9][0-9][0-9][0-9]'),
    gmail_id TEXT,
    tipo_movimiento TEXT CHECK (tipo_movimiento IN ('compra', 'transferencia', 'ingreso')),
    categoria_al_leer TEXT,
    ajuste_id INTEGER,
    respondida_en TEXT,
    respuesta TEXT CHECK (respuesta IN ('si', 'no')),
    PRIMARY KEY (id),
    CHECK ((fuente = 'correo') = (gmail_id IS NOT NULL)),
    CHECK ((fuente = 'correo') = (tipo_movimiento IS NOT NULL)),
    CHECK (fuente = 'banco' OR monto_centavos > 0),
    CHECK ((respuesta IS NULL) = (respondida_en IS NULL)),
    FOREIGN KEY (importacion_id) REFERENCES importaciones (id),
    UNIQUE (gmail_id),
    FOREIGN KEY (ajuste_id) REFERENCES movimientos (id)
);
CREATE TABLE candidatos_pregunta (
    pregunta_id INTEGER NOT NULL,
    movimiento_id INTEGER NOT NULL,
    de_aviso INTEGER DEFAULT '0' NOT NULL CHECK (de_aviso IN (0, 1)),
    PRIMARY KEY (pregunta_id, movimiento_id),
    FOREIGN KEY (pregunta_id) REFERENCES preguntas_conciliacion (id),
    FOREIGN KEY (movimiento_id) REFERENCES movimientos (id)
);
"""


def describir_0008() -> dict:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript("CREATE TABLE categorias (id INTEGER PRIMARY KEY);"
                           "CREATE TABLE reglas (id INTEGER PRIMARY KEY);" + ESQUEMA_0008)
        descripcion = esquema_v1.describir(conn)
        del descripcion["categorias"], descripcion["reglas"]
        return descripcion
    finally:
        conn.close()


ESQUEMA_0010 = """
ALTER TABLE movimientos ADD COLUMN borrado_en TEXT;
ALTER TABLE movimientos ADD COLUMN revisado_no_en_banco INTEGER DEFAULT '0' NOT NULL CHECK (revisado_no_en_banco IN (0, 1));
ALTER TABLE reglas ADD COLUMN modo_texto TEXT DEFAULT 'exacta' NOT NULL CHECK (modo_texto IN ('exacta', 'contiene', 'empieza_por'));
ALTER TABLE reglas ADD COLUMN origen_regla TEXT DEFAULT 'todos' NOT NULL CHECK (origen_regla IN ('todos', 'extracto'));
ALTER TABLE reglas ADD COLUMN texto_visible TEXT;
DROP INDEX ux_reglas_condiciones;
CREATE UNIQUE INDEX ux_reglas_condiciones ON reglas
    (campo, COALESCE(texto, ''), COALESCE(monto_centavos, 0), modo_texto, origen_regla);
CREATE TABLE reversiones_importacion (
    importacion_id INTEGER NOT NULL,
    diario TEXT NOT NULL,
    conteos TEXT NOT NULL,
    ultimo_movimiento_id INTEGER NOT NULL,
    PRIMARY KEY (importacion_id),
    FOREIGN KEY (importacion_id) REFERENCES importaciones (id)
);
"""


def describir_0010() -> dict:
    # Esquema escrito a mano: prueba independiente de Alembic y metadata,
    # incluidos CHECK, DEFAULT, índice de reglas y FK del diario.
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(ESQUEMA_0005 + ESQUEMA_0008 + ESQUEMA_0010)
        return esquema_v1.describir(conn)
    finally:
        conn.close()


def describir_0011() -> dict:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(ESQUEMA_0005 + ESQUEMA_0008 + ESQUEMA_0010 +
            "ALTER TABLE reversiones_importacion ADD COLUMN arranque TEXT;")
        return esquema_v1.describir(conn)
    finally:
        conn.close()


def describir_0012() -> dict:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(ESQUEMA_0005 + ESQUEMA_0008 + ESQUEMA_0010 +
            "ALTER TABLE reversiones_importacion ADD COLUMN arranque TEXT;" + ESQUEMA_0012)
        return esquema_v1.describir(conn)
    finally:
        conn.close()


ESQUEMA_0012 = """
ALTER TABLE preguntas_conciliacion ADD COLUMN ocurrencia_banco INTEGER
 CHECK(ocurrencia_banco IS NULL OR ocurrencia_banco > 0)
 CHECK(ocurrencia_banco IS NULL OR typeof(ocurrencia_banco) = 'integer');
ALTER TABLE preguntas_conciliacion ADD COLUMN movimiento_elegido_id INTEGER
 CONSTRAINT fk_pregunta_movimiento_elegido REFERENCES movimientos(id)
 CHECK(movimiento_elegido_id IS NULL OR (fuente = 'banco' AND respuesta IS NOT NULL AND ocurrencia_banco IS NOT NULL));
CREATE TABLE descartes_movimientos (
 id INTEGER PRIMARY KEY, movimiento_id INTEGER NOT NULL REFERENCES movimientos(id),
 descartado_en TEXT NOT NULL, restaurado_en TEXT, fecha TEXT NOT NULL,
 monto_centavos INTEGER NOT NULL, referencia TEXT, fecha_banco TEXT,
 monto_banco_centavos INTEGER, referencia_banco TEXT,
 huella_movimiento TEXT NOT NULL, huella_contexto TEXT NOT NULL,
 CHECK(referencia IS NULL OR referencia GLOB '[*][0-9][0-9][0-9][0-9]'),
 CHECK(referencia_banco IS NULL OR referencia_banco GLOB '[*][0-9][0-9][0-9][0-9]'),
 CHECK(typeof(monto_centavos) = 'integer'),
 CHECK(monto_centavos <> 0),
 CHECK(monto_banco_centavos IS NULL OR typeof(monto_banco_centavos) = 'integer'),
 CHECK(monto_banco_centavos IS NULL OR monto_banco_centavos <> 0),
 CHECK((fecha_banco IS NULL) = (monto_banco_centavos IS NULL)),
 CHECK(fecha_banco IS NOT NULL OR referencia_banco IS NULL)
);
CREATE UNIQUE INDEX un_descarte_activo_por_movimiento ON descartes_movimientos(movimiento_id)
 WHERE restaurado_en IS NULL;
"""


def describir_0005() -> dict:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(ESQUEMA_0005)
        return esquema_v1.describir(conn)
    finally:
        conn.close()


def diferencias(ruta: Path, ultima: bool = True, *, revision_esperada: str = "0012") -> list[str]:
    """Diferencias con la estructura esperada.

    ``ultima``: la de la última revisión (la v1, más lo que añadieron las
    migraciones posteriores, y nada más). Si no, la de la v1 tal cual.
    """
    conn = sqlite3.connect(ruta)
    try:
        actual = esquema_v1.describir(conn)
        disparadores = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('view', 'trigger')"
        ).fetchall()
    finally:
        conn.close()
    esperado = esquema_v1.describir_v1()
    if ultima:
        if revision_esperada == "0012":
            esperado.update(describir_0012())
        elif revision_esperada == "0011":
            esperado.update(describir_0011())
        elif revision_esperada == "0010":
            esperado.update(describir_0010())
        else:
            assert revision_esperada == "0008"
            esperado.update(describir_0005())
            esperado.update(describir_0008())
    salida = []
    for nombre in sorted(set(actual) | set(esperado)):
        if nombre not in actual:
            salida.append(f"falta la tabla {nombre}")
        elif nombre not in esperado:
            if nombre not in TABLAS_POSTERIORES_A_V1:
                salida.append(f"tabla inesperada {nombre}")
        elif actual[nombre] != esperado[nombre]:
            partes = [k for k in esperado[nombre] if actual[nombre][k] != esperado[nombre][k]]
            salida.append(f"tabla {nombre}: difiere en {', '.join(partes)}")
    salida += [f"inesperado {n}" for (n,) in disparadores]
    return salida
