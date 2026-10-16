"""Migraciones (ítem 22): la base de la v1 migra sin pérdidas y todo es repetible.

Todos los datos son inventados. La "base de producción" se simula creando una
base con ``ESQUEMA_V1`` (el mismo texto que usaba ``db.inicializar`` en la v1,
sin tabla ``alembic_version``) y llenándola a mano.
"""

from __future__ import annotations
from finanzas.bootstrap.reporte import componer_reporte

import hashlib
import sqlite3
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from finanzas import db, migrar
from finanzas.migraciones import esquema_v1
from tests.soporte.migraciones import crear_base_v1, describir_0005, describir_0008, describir_0010, describir_0011, describir_0012, diferencias, huella, revision, volcado  # ayudas compartidas

TABLAS = ("categorias", "movimientos", "reglas", "configuracion_saldo", "correos_no_reconocidos")
# Tablas que crean migraciones posteriores a la 0001 (no existían en la v1).
# ``diferencias`` compara solo la parte de la v1; las nuevas tienen sus pruebas.
TABLAS_POSTERIORES_A_V1 = ("estado_sincronizacion",)
# Tablas de la conciliación (0008, ítem 29): se comparan con ``ESQUEMA_0008``.
TABLAS_0008 = ("importaciones", "cambios_importacion", "preguntas_conciliacion", "candidatos_pregunta")


# --- Ayudas ----------------------------------------------------------------------------



# Las columnas de la v1 de cada tabla (las que añaden migraciones posteriores,
# como ``origen_categoria`` y ``regla_id`` de la 0004, o ``clase``, ``color`` e
# ``icono`` de la 0005, tienen sus pruebas).
COLUMNAS_V1 = {
    "movimientos": (
        "id, fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id, "
        "registrado_en"
    ),
    "categorias": "id, nombre",
    "reglas": "id, campo, texto, categoria_id",
}
# Las categorías que añaden la 0005 (ítem 15) y la 0006 (ítem 27) no son de la
# v1: tienen sus pruebas en tests/persistencia/test_migracion_0005.py y
# tests/persistencia/test_migracion_0006.py (la 0007 no añade categorías).
CATEGORIAS_DE_LA_0005 = ("Antojos", "Sueldo", "Préstamos", "Otros ingresos")
CATEGORIAS_DE_LA_0006 = ("Retiro a efectivo", "Pago de tarjeta")
FILTRO_V1 = {
    "categorias": "WHERE nombre NOT IN ({})".format(
        ", ".join(f"'{n}'" for n in CATEGORIAS_DE_LA_0005 + CATEGORIAS_DE_LA_0006)
    ),
}








# ``categorias`` como la deja la 0005 (ítem 15) y ``reglas`` como la deja la
# 0006 (ítem 17), escritas a mano: clase, color e ícono; nombre único por
# clase; reglas de ingreso; reglas con texto y monto opcionales (al menos uno).
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


# ``movimientos`` como la deja la 0008 (ítem 29) y las tablas nuevas de la
# conciliación, escritas a mano: estados, destino de 4 dígitos, fecha del
# banco, marca "no está en el banco", origen ``extracto`` y ajustes en 0.
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






@pytest.fixture
def base_v1(tmp_path) -> Path:
    ruta = tmp_path / "produccion-inventada.db"
    crear_base_v1(ruta)
    return ruta


@pytest.fixture
def respaldos(tmp_path) -> Path:
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    return carpeta


# --- La migración inicial reproduce la v1 ------------------------------------------

def test_la_base_nueva_tiene_exactamente_la_estructura_de_la_v1(tmp_path):
    ruta = tmp_path / "nueva.db"
    migrar.aplicar(str(ruta))
    assert diferencias(ruta) == []
    assert revision(ruta) == migrar.revision_final() == "0012"


def test_la_base_nueva_trae_las_8_categorias_con_los_ids_de_la_v1(tmp_path, base_v1):
    ruta = tmp_path / "nueva.db"
    migrar.aplicar(str(ruta))
    assert volcado(ruta)["categorias"] == volcado(base_v1)["categorias"]
    assert [n for _, n in volcado(ruta)["categorias"]] == list(db.CATEGORIAS_FIJAS)
    # Más las 4 de la 0005 y las 2 de la 0006 (tests/persistencia/test_migracion_000{5,6}.py).
    conn = sqlite3.connect(ruta)
    assert conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 14
    conn.close()


def test_metadata_coincide_con_las_migraciones_sin_diferencias(tmp_path):
    # Lo mismo que "alembic check": columnas, tipos, NULL, índices, UNIQUE y FK.
    ruta = tmp_path / "nueva.db"
    migrar.aplicar(str(ruta))
    conn = db.conectar(str(ruta))
    try:
        contexto = MigrationContext.configure(conn)
        assert compare_metadata(contexto, db.metadata) == []
    finally:
        conn.close()


def test_metadata_crea_la_misma_estructura_que_la_v1_incluidos_los_check(tmp_path):
    # compare_metadata no mira los CHECK ni los DEFAULT: esto sí.
    ruta = tmp_path / "desde-metadata.db"
    db.metadata.create_all(create_engine(f"sqlite:///{ruta}"))
    assert diferencias(ruta) == []


@pytest.mark.parametrize(
    "sentencia",
    [
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id) VALUES ('x', 12.5, 'compra', 'gmail', 'a')",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id) VALUES ('x', 0, 'compra', 'gmail', 'a')",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id) VALUES ('x', 1, 'retiro', 'gmail', 'a')",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id) VALUES ('x', 1, 'ingreso', 'manual', 'a')",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id, categoria_id) VALUES ('x', 1, 'compra', 'gmail', 'a', 99)",
        "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', '', 1)",
        "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('tarjeta', 'x', 1)",
        "INSERT INTO configuracion_saldo VALUES (2, 1, '2026-08-01')",
        "INSERT INTO configuracion_saldo VALUES (1, 'abc', '2026-08-01')",
        "INSERT INTO categorias (nombre) VALUES ('Mercado')",
    ],
)
def test_las_restricciones_rechazan_lo_mismo_que_en_la_v1(tmp_path, base_v1, sentencia):
    nueva = tmp_path / "nueva.db"
    migrar.aplicar(str(nueva))
    for ruta in (base_v1, nueva):
        conn = sqlite3.connect(ruta)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with pytest.raises(sqlite3.IntegrityError):
                with conn:
                    conn.execute(sentencia)
        finally:
            conn.close()


def test_un_ajuste_en_0_solo_lo_admite_la_0008(tmp_path, base_v1):
    """D45: lo importado del banco puede reducir un ajuste hasta 0 (la v1 no lo admitía)."""
    nueva = tmp_path / "nueva.db"
    migrar.aplicar(str(nueva))
    sentencia = ("INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id) "
                 "VALUES ('x', 0, 'ajuste', 'manual', NULL)")
    conn = sqlite3.connect(base_v1)
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(sentencia)
    conn.close()
    conn = sqlite3.connect(nueva)
    with conn:
        conn.execute(sentencia)
    conn.close()


def test_registrado_en_por_defecto_como_en_la_v1(tmp_path):
    ruta = tmp_path / "nueva.db"
    migrar.aplicar(str(ruta))
    conn = sqlite3.connect(ruta)
    try:
        with conn:
            conn.execute(
                "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id) "
                "VALUES ('2026-08-07T16:42:00', 1, 'compra', 'gmail', 'id-x')"
            )
        registrado, descripcion = conn.execute("SELECT registrado_en, descripcion FROM movimientos").fetchone()
    finally:
        conn.close()
    assert len(registrado) == 19 and registrado[10] == "T"
    assert descripcion == ""


# --- La base de la v1 (producción) ------------------------------------------------

def test_la_base_v1_se_reconoce_y_se_marca_sin_perder_nada(base_v1):
    antes = volcado(base_v1)
    assert migrar.diagnosticar(str(base_v1)) == migrar.Diagnostico(
        actual=None, pendientes=["0002", "0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010", "0011", "0012"], marcar_v1=True
    )

    hecho = migrar.aplicar(str(base_v1))

    assert hecho.marcar_v1
    assert revision(base_v1) == migrar.revision_final()
    assert volcado(base_v1) == antes  # mismos conteos y mismos valores, fila por fila
    assert sum(len(filas) for filas in antes.values()) == 8 + 6 + 1 + 1 + 1
    assert diferencias(base_v1) == []


def test_migrar_dos_veces_no_cambia_nada(base_v1):
    migrar.aplicar(str(base_v1))
    huella_antes = huella(base_v1)
    datos_antes = volcado(base_v1)

    hecho = migrar.aplicar(str(base_v1))

    assert hecho.al_dia
    assert huella(base_v1) == huella_antes  # ni un byte distinto
    assert volcado(base_v1) == datos_antes


def test_la_app_funciona_sobre_la_base_migrada(base_v1):
    from finanzas.bootstrap.saldo import componer_saldo

    migrar.aplicar(str(base_v1))
    db.exigir_al_dia(str(base_v1))
    conn = db.conectar(str(base_v1))
    try:
        # 1.234.567,89 + 160.000 + 25.000 − 68.630 − 6.000 − 456,78 − 0,01
        assert componer_saldo(conn).saldo_actual() == 123456789 + 16000000 + 2500000 - 6863000 - 600000 - 45678 - 1
        informe = componer_reporte(conn).reporte_mensual(2026, 8)
        assert informe.total_gasto_centavos == 6863000 + 600000 + 1
    finally:
        conn.close()


@pytest.mark.parametrize(
    "cambio",
    [
        "ALTER TABLE movimientos ADD COLUMN extra TEXT",
        "DROP INDEX idx_movimientos_fecha_hora",
        "CREATE TABLE tabla_inventada (id INTEGER)",
        "CREATE INDEX idx_inventado ON reglas (texto)",
        "CREATE VIEW vista_inventada AS SELECT id FROM categorias",
        "DROP TABLE correos_no_reconocidos",
    ],
)
def test_una_base_sin_version_distinta_de_la_v1_no_se_toca(base_v1, cambio):
    conn = sqlite3.connect(base_v1)
    with conn:
        conn.execute(cambio)
    conn.close()
    huella_antes = huella(base_v1)

    with pytest.raises(migrar.ErrorMigracion, match="No se cambió nada"):
        migrar.aplicar(str(base_v1))

    assert huella(base_v1) == huella_antes
    assert revision(base_v1) is None


def test_un_check_distinto_se_detecta(tmp_path):
    # Misma tabla, pero sin el CHECK de "texto <> ''" en reglas.
    ruta = tmp_path / "otra.db"
    conn = sqlite3.connect(ruta)
    conn.executescript(esquema_v1.ESQUEMA_V1.replace("texto        TEXT NOT NULL CHECK (texto <> ''),", "texto        TEXT NOT NULL,"))
    conn.close()
    assert diferencias(ruta, ultima=False) == ["tabla reglas: difiere en checks"]
    with pytest.raises(migrar.ErrorMigracion, match="reglas"):
        migrar.aplicar(str(ruta))


def test_revision_desconocida_se_rechaza(tmp_path):
    ruta = tmp_path / "nueva.db"
    migrar.aplicar(str(ruta))
    conn = sqlite3.connect(ruta)
    with conn:
        conn.execute("UPDATE alembic_version SET version_num = '9999'")
    conn.close()
    with pytest.raises(migrar.ErrorMigracion, match="9999"):
        migrar.aplicar(str(ruta))


def test_si_algo_falla_a_mitad_no_queda_nada_a_medias(base_v1, monkeypatch):
    # La marca (stamp) y las migraciones van en una sola transacción.
    huella_antes = huella(base_v1)

    def falla(*args, **kwargs):
        raise RuntimeError("fallo inventado")

    monkeypatch.setattr(migrar.command, "upgrade", falla)
    with pytest.raises(RuntimeError):
        migrar.aplicar(str(base_v1))
    assert revision(base_v1) is None
    assert huella(base_v1) == huella_antes


# --- Ida y vuelta -------------------------------------------------------------------

def test_downgrade_y_upgrade_de_ida_y_vuelta(tmp_path):
    ruta = tmp_path / "ida-y-vuelta.db"
    from tests.soporte.migracion_0005 import _subir_hasta
    _subir_hasta(ruta, "0008")
    estructura = diferencias(ruta, revision_esperada="0008")

    assert migrar.bajar_a(str(ruta), "base") == ["0008", "0007", "0006", "0005", "0004", "0003", "0002", "0001"]
    conn = sqlite3.connect(ruta)
    restantes = {n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert restantes & set(TABLAS + TABLAS_POSTERIORES_A_V1) == set()
    assert revision(ruta) is None

    _subir_hasta(ruta, "0008")
    assert diferencias(ruta, revision_esperada="0008") == estructura == []
    assert revision(ruta) == "0008"
    assert len(volcado(ruta)["categorias"]) == 8  # las de la v1 (más las 4 de la 0005 y las 2 de la 0006)


# --- La app exige la base al día -------------------------------------------------------

def test_exigir_al_dia(tmp_path, base_v1):
    with pytest.raises(db.BaseNoMigrada):
        db.exigir_al_dia(str(tmp_path / "no-existe.db"))
    assert not (tmp_path / "no-existe.db").exists()
    with pytest.raises(db.BaseNoMigrada, match="python -m finanzas.migrar"):
        db.exigir_al_dia(str(base_v1))  # la de la v1, sin marcar
    migrar.aplicar(str(base_v1))
    db.exigir_al_dia(str(base_v1))


def test_la_sincronizacion_no_arranca_sin_migrar(base_v1, monkeypatch, capsys):
    from finanzas import sincronizacion

    monkeypatch.setenv("DB_PATH", str(base_v1))
    from finanzas.seguridad import generar_hash

    monkeypatch.setenv("APP_PASSWORD_HASH", generar_hash("clave-inventada"))
    monkeypatch.setenv("SESSION_SECRET", "secreto-inventado-de-mas-de-32-caracteres-xx")

    def sin_gmail(config):
        raise AssertionError("no debe llegar a Gmail")

    huella_antes = huella(base_v1)
    assert sincronizacion.main([], fabrica_cliente=sin_gmail) == 2
    assert "python -m finanzas.migrar" in capsys.readouterr().err
    assert huella(base_v1) == huella_antes


def test_preparar_vuelve_a_cargar_una_categoria_fija_borrada(tmp_path):
    # Comportamiento de la v1 que conserva db.inicializar (para pruebas y desarrollo).
    ruta = tmp_path / "nueva.db"
    db.preparar(str(ruta))
    conn = sqlite3.connect(ruta)
    with conn:
        conn.execute("DELETE FROM categorias WHERE nombre = 'Otros'")
    conn.close()
    db.preparar(str(ruta))
    assert len(volcado(ruta)["categorias"]) == 8  # las de la v1, sin contar las de la 0005 y la 0006
