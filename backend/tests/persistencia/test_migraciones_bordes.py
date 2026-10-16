"""Casos borde de las migraciones y del comando ``python -m finanzas.migrar`` (ítem 22).

Complementa ``test_migraciones.py`` y ``test_migrar.py``. Todos los datos son
inventados: la base "de la v1" la crea ``crear_base_v1`` con centinelas que
nunca deben aparecer en la salida del comando.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from finanzas import db, migrar
from finanzas.migraciones import esquema_v1
from tests.soporte.migraciones import crear_base_v1, huella, revision, volcado
from tests.soporte.migrar import CENTINELAS


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


def _correr(capsys, *argv) -> tuple[int, str]:
    codigo = migrar.main(list(argv))
    salida = capsys.readouterr()
    return codigo, salida.out + salida.err


def _previos(carpeta: Path) -> list[Path]:
    return sorted(carpeta.glob("finanzas-antes-de-migrar-*.db"))


def _sin_datos(texto: str) -> None:
    for centinela in CENTINELAS:
        assert centinela not in texto, centinela


def _ejecutar(ruta: Path, *sentencias: str) -> None:
    conn = sqlite3.connect(ruta)
    try:
        with conn:
            for sentencia in sentencias:
                conn.execute(sentencia)
    finally:
        conn.close()


# --- Archivos raros -----------------------------------------------------------------

def test_archivo_vacio_se_trata_como_base_nueva(capsys, tmp_path, respaldos):
    # Un archivo de 0 bytes (p. ej. creado con touch) es una base SQLite vacía.
    ruta = tmp_path / "vacia.db"
    ruta.touch()

    codigo, salida = _correr(capsys, "--base", str(ruta), "--comprobar")
    assert codigo == 1
    assert "0001" in salida

    codigo, salida = _correr(capsys, "--base", str(ruta), "--respaldos", str(respaldos))
    assert codigo == 0, salida
    assert _previos(respaldos) == []  # no había nada que respaldar
    assert revision(ruta) == migrar.revision_final()
    assert len(volcado(ruta)["categorias"]) == len(db.CATEGORIAS_FIJAS)


def test_archivo_que_no_es_sqlite_se_rechaza_sin_tocarlo(capsys, tmp_path, respaldos):
    ruta = tmp_path / "no-es-base.db"
    ruta.write_bytes(b"COMERCIO INVENTADO 6863000 " * 200)
    huella_antes = huella(ruta)

    codigo, salida = _correr(capsys, "--base", str(ruta), "--respaldos", str(respaldos))
    assert codigo == 1
    assert "No se migró" in salida
    assert "Traceback" not in salida
    _sin_datos(salida)
    assert huella(ruta) == huella_antes
    assert _previos(respaldos) == []

    codigo, salida = _correr(capsys, "--base", str(ruta), "--comprobar")
    assert codigo == 1
    _sin_datos(salida)
    assert huella(ruta) == huella_antes


# --- Estados de la base -------------------------------------------------------------

def test_revision_desconocida_por_comando_no_respalda_ni_cambia(capsys, tmp_path, respaldos):
    ruta = tmp_path / "futura.db"
    migrar.aplicar(str(ruta))
    _ejecutar(ruta, "UPDATE alembic_version SET version_num = '9999'")
    huella_antes = huella(ruta)

    codigo, salida = _correr(capsys, "--base", str(ruta), "--respaldos", str(respaldos))
    assert codigo == 1
    assert "9999" in salida
    assert _previos(respaldos) == []
    assert huella(ruta) == huella_antes

    codigo, salida = _correr(capsys, "--base", str(ruta), "--comprobar")
    assert codigo == 1
    assert huella(ruta) == huella_antes


def test_tabla_alembic_version_vacia_con_estructura_v1_se_marca(base_v1, respaldos, capsys):
    # Una tabla de versiones sin fila equivale a "sin versión".
    _ejecutar(base_v1, "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
    antes = volcado(base_v1)

    codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    assert codigo == 0, salida
    assert revision(base_v1) == migrar.revision_final()
    assert volcado(base_v1) == antes
    conn = sqlite3.connect(base_v1)
    try:
        assert conn.execute("SELECT count(*) FROM alembic_version").fetchone()[0] == 1
    finally:
        conn.close()


def test_base_v1_con_estadisticas_de_analyze_se_reconoce(base_v1, respaldos, capsys):
    # ANALYZE crea sqlite_stat1: es interna de SQLite y no cambia la estructura de la app.
    _ejecutar(base_v1, "ANALYZE")
    antes = volcado(base_v1)

    codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    assert codigo == 0, salida
    assert revision(base_v1) == migrar.revision_final()
    assert volcado(base_v1) == antes


def test_base_v1_en_modo_wal_migra_sin_perdidas(base_v1, respaldos, capsys):
    conn = sqlite3.connect(base_v1)
    try:
        assert conn.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    finally:
        conn.close()
    antes = volcado(base_v1)

    codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    assert codigo == 0, salida
    assert revision(base_v1) == migrar.revision_final()
    assert volcado(base_v1) == antes
    [copia] = _previos(respaldos)
    assert volcado(copia) == antes


def test_base_v1_con_datos_huerfanos_se_marca_sin_tocarlos(base_v1, respaldos, capsys):
    # Si alguna vez se escribió con las claves foráneas apagadas, la marca no
    # debe fallar ni "arreglar" nada: los datos quedan tal cual.
    conn = sqlite3.connect(base_v1)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        with conn:
            conn.execute("UPDATE movimientos SET categoria_id = 999 WHERE gmail_id = 'id-inventado-2'")
    finally:
        conn.close()
    antes = volcado(base_v1)

    codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    assert codigo == 0, salida
    assert revision(base_v1) == migrar.revision_final()
    assert volcado(base_v1) == antes


def test_preparar_sobre_base_v1_la_marca_sin_duplicar_categorias(base_v1):
    antes = volcado(base_v1)
    db.preparar(str(base_v1))
    db.preparar(str(base_v1))
    assert revision(base_v1) == migrar.revision_final()
    assert volcado(base_v1) == antes


# --- Concurrencia -------------------------------------------------------------------

def test_base_bloqueada_por_otro_proceso_no_se_migra(base_v1, respaldos, capsys, monkeypatch):
    # Si la app o la sincronización tienen la escritura reservada más allá de
    # la espera, el comando falla sin dejar nada a medias.
    monkeypatch.setattr(migrar, "ESPERA_BLOQUEO", 0.2)
    antes = volcado(base_v1)
    otro = sqlite3.connect(base_v1, isolation_level=None)
    try:
        otro.execute("BEGIN IMMEDIATE")
        codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    finally:
        otro.execute("ROLLBACK")
        otro.close()

    assert codigo == 1
    assert "La base quedó como estaba" in salida
    _sin_datos(salida)
    assert revision(base_v1) is None
    assert volcado(base_v1) == antes

    # Liberada la base, la siguiente ejecución migra con normalidad.
    codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    assert codigo == 0, salida
    assert revision(base_v1) == migrar.revision_final()


# --- Comando ------------------------------------------------------------------------

def test_bajar_a_en_base_sin_version_no_respalda_ni_cambia(capsys, base_v1, respaldos):
    huella_antes = huella(base_v1)
    codigo, salida = _correr(
        capsys, "--base", str(base_v1), "--respaldos", str(respaldos), "--bajar-a", "0001"
    )
    assert codigo == 1
    assert "no tiene versión" in salida
    assert _previos(respaldos) == []
    assert huella(base_v1) == huella_antes


def test_comprobar_y_bajar_a_juntos_son_argumentos_invalidos(capsys, base_v1):
    huella_antes = huella(base_v1)
    codigo, _ = _correr(capsys, "--base", str(base_v1), "--comprobar", "--bajar-a", "0001")
    assert codigo == 2
    assert huella(base_v1) == huella_antes


@pytest.mark.parametrize("exito", [True, False])
def test_el_comando_restaura_la_umask(capsys, tmp_path, respaldos, exito):
    ruta = tmp_path / "nueva.db"
    if not exito:
        ruta.write_bytes(b"no es una base")
    anterior = os.umask(0o022)
    try:
        codigo, _ = _correr(capsys, "--base", str(ruta), "--respaldos", str(respaldos))
        assert codigo == (0 if exito else 1)
        assert os.umask(0o022) == 0o022
    finally:
        os.umask(anterior)


def test_base_nueva_por_comando_queda_al_dia_para_la_app(capsys, tmp_path, respaldos):
    ruta = tmp_path / "nueva.db"
    with pytest.raises(db.BaseNoMigrada):
        db.exigir_al_dia(str(ruta))
    assert not ruta.exists()

    codigo, salida = _correr(capsys, "--base", str(ruta), "--respaldos", str(respaldos))
    assert codigo == 0, salida
    db.exigir_al_dia(str(ruta))  # no lanza


def test_exigir_al_dia_rechaza_revision_desconocida(tmp_path):
    ruta = tmp_path / "futura.db"
    migrar.aplicar(str(ruta))
    _ejecutar(ruta, "UPDATE alembic_version SET version_num = '9999'")
    with pytest.raises(db.BaseNoMigrada):
        db.exigir_al_dia(str(ruta))


# --- Comparación de estructura ------------------------------------------------------

def test_checks_respeta_parentesis_dentro_de_textos():
    sql = "CREATE TABLE t (x TEXT CHECK (x IN ('a)b', 'c(')), y INTEGER)"
    assert esquema_v1._checks(sql) == ["x IN ('a)b', 'c(')"]


def test_checks_ignora_los_comentarios():
    sql = "CREATE TABLE t (\n  x TEXT -- CHECK (x <> 'nada')\n  CHECK (x <> '')\n)"
    assert esquema_v1._checks(sql) == ["x <> ''"]


def test_checks_sin_sql():
    assert esquema_v1._checks(None) == []


def test_default_con_y_sin_parentesis_es_el_mismo():
    assert esquema_v1._default("(strftime('%s', 'now'))") == esquema_v1._default("strftime('%s', 'now')")
    assert esquema_v1._default("''") == "''"
    assert esquema_v1._default(None) is None


@pytest.mark.parametrize(
    "original, cambiado, tabla",
    [
        # Un DEFAULT distinto.
        ("descripcion    TEXT NOT NULL DEFAULT ''", "descripcion    TEXT NOT NULL DEFAULT 'x'", "movimientos"),
        # Quitar NOT NULL.
        ("fecha_hora     TEXT NOT NULL,", "fecha_hora     TEXT,", "movimientos"),
        # Clave foránea que apunta a otro sitio.
        ("categoria_id INTEGER NOT NULL REFERENCES categorias(id)",
         "categoria_id INTEGER NOT NULL", "reglas"),
        # UNIQUE de más.
        ("fecha    TEXT,", "fecha    TEXT UNIQUE,", "correos_no_reconocidos"),
        # UNIQUE de menos.
        ("gmail_id       TEXT UNIQUE,", "gmail_id       TEXT,", "movimientos"),
    ],
)
def test_cambios_sutiles_de_estructura_se_detectan(tmp_path, original, cambiado, tabla):
    assert original in esquema_v1.ESQUEMA_V1
    ruta = tmp_path / "sutil.db"
    conn = sqlite3.connect(ruta)
    try:
        conn.executescript(esquema_v1.ESQUEMA_V1.replace(original, cambiado))
        diferencias = esquema_v1.diferencias_con_v1(conn)
    finally:
        conn.close()
    assert len(diferencias) == 1 and tabla in diferencias[0], diferencias
    huella_antes = huella(ruta)
    with pytest.raises(migrar.ErrorMigracion):
        migrar.aplicar(str(ruta))
    assert huella(ruta) == huella_antes


def test_disparador_inesperado_se_detecta(base_v1):
    _ejecutar(
        base_v1,
        "CREATE TRIGGER disparador_inventado AFTER INSERT ON reglas BEGIN SELECT 1; END",
    )
    huella_antes = huella(base_v1)
    with pytest.raises(migrar.ErrorMigracion, match="disparador"):
        migrar.aplicar(str(base_v1))
    assert huella(base_v1) == huella_antes


# --- Comando alembic directo (desarrollo) -------------------------------------------

def test_alembic_directo_usa_db_path_y_no_detecta_diferencias(tmp_path, monkeypatch):
    # Sin conexión recibida, env.py abre la base de DB_PATH (``alembic upgrade``,
    # ``alembic check`` en desarrollo). ``check`` falla si metadata y
    # migraciones no coinciden.
    from alembic import command
    from alembic.config import Config as ConfigAlembic

    ruta = tmp_path / "desarrollo.db"
    monkeypatch.setenv("DB_PATH", str(ruta))
    config = ConfigAlembic(str(Path(__file__).resolve().parents[3] / "alembic.ini"))

    command.upgrade(config, "head")
    assert revision(ruta) == migrar.revision_final()
    command.check(config)  # no lanza
    assert migrar.diagnosticar(str(ruta)).al_dia
