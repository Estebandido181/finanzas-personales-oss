"""Estado de la última sincronización: migración 0002 y ``sincronizacion`` (ítem 10).

Datos inventados. La migración solo añade la tabla ``estado_sincronizacion``
(una fila): sube y baja sin tocar los demás datos, y es idempotente.
"""

from __future__ import annotations
from finanzas.infraestructura import persistencia

import sqlite3

import pytest

from finanzas import db, migrar, sincronizacion
from finanzas.gmail import ErrorAutorizacionGmail
from finanzas.sincronizacion import ResultadoSincronizacion

from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import ClienteFalso
from tests.soporte.migraciones import TABLAS, crear_base_v1, huella, revision, volcado


def _tablas(ruta):
    conn = sqlite3.connect(ruta)
    try:
        return {n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()


def _fila_estado(ruta):
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    try:
        filas = conn.execute("SELECT * FROM estado_sincronizacion").fetchall()
    finally:
        conn.close()
    return [dict(f) for f in filas]


@pytest.fixture
def base_v1(tmp_path):
    ruta = tmp_path / "produccion-inventada.db"
    crear_base_v1(ruta)
    return ruta


@pytest.fixture
def conn(tmp_path):
    ruta = tmp_path / "estado.db"
    db.preparar(str(ruta))
    conexion = db.conectar(str(ruta))
    yield conexion
    conexion.close()


# --- Migración 0002 ---------------------------------------------------------------------

def test_la_v1_migra_a_la_ultima_sin_perder_datos(base_v1):
    antes = volcado(base_v1)
    migrar.aplicar(str(base_v1))
    assert revision(base_v1) == migrar.revision_final()
    assert "estado_sincronizacion" in _tablas(base_v1)
    assert volcado(base_v1) == antes
    assert _fila_estado(base_v1) == []


def test_migrar_otra_vez_no_cambia_nada(base_v1):
    migrar.aplicar(str(base_v1))
    huella_antes = huella(base_v1)
    assert migrar.aplicar(str(base_v1)).al_dia
    assert huella(base_v1) == huella_antes


def test_bajar_a_0001_quita_solo_la_tabla_y_volver_a_subir(base_v1):
    from tests.soporte.migracion_0005 import _subir_hasta
    _subir_hasta(base_v1, "0008")
    conn = db.conectar(str(base_v1))
    try:
        sincronizacion.guardar_estado(conn, "web", resultado=ResultadoSincronizacion(nuevos=1))
    finally:
        conn.close()
    datos = volcado(base_v1)

    assert migrar.bajar_a(str(base_v1), "0001") == ["0008", "0007", "0006", "0005", "0004", "0003", "0002"]
    assert revision(base_v1) == "0001"
    assert "estado_sincronizacion" not in _tablas(base_v1)
    assert set(TABLAS) <= _tablas(base_v1)
    assert volcado(base_v1) == datos  # los datos de la v1, intactos

    _subir_hasta(base_v1, "0008")
    assert revision(base_v1) == "0008"
    assert volcado(base_v1) == datos
    assert _fila_estado(base_v1) == []  # el estado se pierde; la siguiente sincronización lo escribe


def test_comando_bajar_a_0001_hace_respaldo(base_v1, tmp_path, capsys):
    from tests.soporte.migracion_0005 import _subir_hasta
    _subir_hasta(base_v1, "0008")  # prueba histórica: 0009 exige restaurar respaldo
    respaldos = tmp_path / "respaldos"
    respaldos.mkdir()
    assert migrar.main(["--base", str(base_v1), "--respaldos", str(respaldos), "--bajar-a", "0001"]) == 0
    assert revision(base_v1) == "0001"
    assert any(p.name.startswith("finanzas-antes-de-migrar-0008-") for p in respaldos.iterdir())


def _sql_tabla(ruta, tabla):
    conn = sqlite3.connect(ruta)
    try:
        fila = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (tabla,)
        ).fetchone()
        return fila[0]
    finally:
        conn.close()


def test_migracion_0002_y_metadata_crean_la_misma_tabla_con_los_check(tmp_path):
    # compare_metadata (alembic check) no mira los CHECK: aquí se compara el
    # CREATE TABLE que guarda SQLite, creado por la migración y por db.metadata.
    from sqlalchemy import create_engine

    from finanzas.migraciones import esquema_v1

    migrada = tmp_path / "migrada.db"
    migrar.aplicar(str(migrada))
    desde_metadata = tmp_path / "metadata.db"
    motor = create_engine(f"sqlite:///{desde_metadata}")
    db.metadata.create_all(motor)
    motor.dispose()

    sql_migrada = _sql_tabla(migrada, "estado_sincronizacion")
    sql_metadata = _sql_tabla(desde_metadata, "estado_sincronizacion")
    # Los CHECK de una misma columna salen en orden variable (SQLAlchemy los
    # guarda en un conjunto), así que no se compara el texto tal cual: se
    # comparan las expresiones CHECK (ordenadas) y el SQL sin ellas.
    checks = esquema_v1._checks(sql_migrada)
    assert checks == esquema_v1._checks(sql_metadata)
    # id, estado, origen, 2 por cada uno de los 5 contadores, código y los 2 de la tabla.
    assert len(checks) == 16
    assert "codigo_error IS NULL OR codigo_error IN" in " ".join(checks)
    assert _sin_checks(sql_migrada) == _sin_checks(sql_metadata)
    # Y la descripción estructural completa: columnas, tipos, NULL, DEFAULT, claves y CHECK.
    descripciones = []
    for ruta in (migrada, desde_metadata):
        conn = sqlite3.connect(ruta)
        try:
            descripciones.append(esquema_v1.describir(conn)["estado_sincronizacion"])
        finally:
            conn.close()
    assert descripciones[0] == descripciones[1]
    assert descripciones[0]["checks"] == checks


def _sin_checks(sql_tabla):
    """El CREATE TABLE sin sus cláusulas CHECK (...) y con los espacios normalizados."""
    salida, i = [], 0
    while i < len(sql_tabla):
        if sql_tabla.startswith("CHECK (", i):
            profundidad, j = 0, i + len("CHECK ")
            while True:
                if sql_tabla[j] == "(":
                    profundidad += 1
                elif sql_tabla[j] == ")":
                    profundidad -= 1
                    if profundidad == 0:
                        break
                j += 1
            i = j + 1
            continue
        salida.append(sql_tabla[i])
        i += 1
    return " ".join("".join(salida).split())


@pytest.mark.parametrize(
    "sentencia",
    [
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, nuevos, duplicados, no_reconocidos, errores, rechazados_autenticacion) VALUES (2, 'x', 'ok', 'web', 0, 0, 0, 0, 0)",
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, nuevos, duplicados, no_reconocidos, errores, rechazados_autenticacion) VALUES (1, 'x', 'otro', 'web', 0, 0, 0, 0, 0)",
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, nuevos, duplicados, no_reconocidos, errores, rechazados_autenticacion) VALUES (1, 'x', 'ok', 'otro', 0, 0, 0, 0, 0)",
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, nuevos, duplicados, no_reconocidos, errores, rechazados_autenticacion) VALUES (1, 'x', 'ok', 'web', -1, 0, 0, 0, 0)",
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, nuevos, duplicados, no_reconocidos, errores, rechazados_autenticacion) VALUES (1, 'x', 'ok', 'web', 1.5, 0, 0, 0, 0)",
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, codigo_error) VALUES (1, 'x', 'fallida', 'web', 'texto libre con datos')",
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen) VALUES (1, 'x', 'fallida', 'web')",
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, codigo_error, nuevos, duplicados, no_reconocidos, errores, rechazados_autenticacion) VALUES (1, 'x', 'ok', 'web', 'error_inesperado', 0, 0, 0, 0, 0)",
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen) VALUES (1, 'x', 'ok', 'web')",
        "INSERT INTO estado_sincronizacion (id, estado, origen, codigo_error) VALUES (1, 'fallida', 'web', 'error_inesperado')",
    ],
)
def test_las_restricciones_de_la_tabla(conn, sentencia):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(conn, sentencia)


# --- Guardar y leer -------------------------------------------------------------------------

def test_sin_sincronizaciones_no_hay_estado(conn):
    assert sincronizacion.leer_estado(conn) is None


def test_guardar_y_leer_ok_y_con_errores(conn):
    sincronizacion.guardar_estado(conn, "web", resultado=ResultadoSincronizacion(nuevos=3, no_reconocidos=1))
    estado = sincronizacion.leer_estado(conn)
    assert (estado.estado, estado.origen, estado.codigo_error) == ("ok", "web", None)
    assert estado.resultado == ResultadoSincronizacion(nuevos=3, no_reconocidos=1)
    assert len(estado.terminada_en) == 19 and estado.terminada_en[10] == "T"

    sincronizacion.guardar_estado(conn, "comando", resultado=ResultadoSincronizacion(errores=2))
    estado = sincronizacion.leer_estado(conn)
    assert (estado.estado, estado.origen) == ("con_errores", "comando")
    assert sql(conn, "SELECT COUNT(*) FROM estado_sincronizacion").fetchone()[0] == 1  # una sola fila


def test_guardar_fallida(conn):
    guardado = sincronizacion.guardar_estado(conn, "comando", codigo_error="autorizacion_gmail")
    assert sincronizacion.leer_estado(conn) == guardado
    assert (guardado.estado, guardado.resultado, guardado.codigo_error) == ("fallida", None, "autorizacion_gmail")


@pytest.mark.parametrize(
    "argumentos",
    [
        {"origen": "otro", "codigo_error": "error_inesperado"},
        {"origen": "web"},
        {"origen": "web", "codigo_error": "texto libre"},
        {"origen": "web", "codigo_error": "error_inesperado", "resultado": ResultadoSincronizacion()},
    ],
)
def test_guardar_rechaza_lo_que_no_es_de_la_lista(conn, argumentos):
    with pytest.raises(ValueError):
        sincronizacion.guardar_estado(conn, **argumentos)
    assert sincronizacion.leer_estado(conn) is None


def test_si_no_se_puede_guardar_no_falla(conn, monkeypatch, caplog):
    def falla(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(persistencia, "transaccion", falla)
    estado = sincronizacion.guardar_estado(conn, "web", resultado=ResultadoSincronizacion(nuevos=1))
    assert estado.estado == "ok"
    assert "No se pudo guardar el estado" in caplog.text


# --- ejecutar guarda el estado -------------------------------------------------------------------

def _configurar(conn):
    with db.transaccion(conn):
        sql(conn, "INSERT INTO configuracion_saldo VALUES (1, 100, '2026-08-01')")


def test_ejecutar_guarda_ok(conn):
    _configurar(conn)
    resultado = sincronizacion.ejecutar(conn, ClienteFalso, origen="web")
    estado = sincronizacion.leer_estado(conn)
    assert estado.resultado == resultado and estado.origen == "web" and estado.estado == "ok"


def test_ejecutar_sin_fecha_guarda_y_relanza(conn):
    with pytest.raises(sincronizacion.SincronizacionNoConfigurada):
        sincronizacion.ejecutar(conn, ClienteFalso)
    estado = sincronizacion.leer_estado(conn)
    assert (estado.estado, estado.codigo_error, estado.origen) == ("fallida", "sin_fecha_inicio", "comando")


@pytest.mark.parametrize(
    "error, codigo",
    [
        (sincronizacion.SincronizacionNoConfigurada("falta GMAIL_TOKEN"), "gmail_no_configurado"),
        (ErrorAutorizacionGmail("token revocado inventado"), "autorizacion_gmail"),
        (RuntimeError("error con datos inventados $6.000"), "error_inesperado"),
    ],
)
def test_ejecutar_con_error_guarda_el_codigo_y_relanza_la_misma_excepcion(conn, error, codigo):
    _configurar(conn)

    def fabrica():
        raise error

    with pytest.raises(type(error)) as capturada:
        sincronizacion.ejecutar(conn, fabrica)
    assert capturada.value is error
    estado = sincronizacion.leer_estado(conn)
    assert (estado.estado, estado.codigo_error, estado.resultado) == ("fallida", codigo, None)
    assert "inventad" not in repr(sql(conn, "SELECT * FROM estado_sincronizacion").fetchall())


def test_error_de_autorizacion_a_mitad_de_la_descarga(conn):
    _configurar(conn)
    cliente = ClienteFalso(fallan={"msg-9999": ErrorAutorizacionGmail("revocado")})
    with pytest.raises(ErrorAutorizacionGmail):
        sincronizacion.ejecutar(conn, lambda: cliente)
    assert sincronizacion.leer_estado(conn).codigo_error == "autorizacion_gmail"


def test_ejecutar_con_estado_no_lanza(conn, caplog):
    _configurar(conn)

    def fabrica():
        raise RuntimeError("datos inventados $6.000")

    estado = sincronizacion.ejecutar_con_estado(conn, fabrica)
    assert (estado.estado, estado.codigo_error, estado.origen) == ("fallida", "error_inesperado", "web")
    assert "RuntimeError" in caplog.text
    assert "$6.000" not in caplog.text


def test_el_comando_guarda_el_estado(tmp_path, monkeypatch, capsys):
    from finanzas.seguridad import generar_hash

    ruta = tmp_path / "comando.db"
    db.preparar(str(ruta))
    monkeypatch.setenv("DB_PATH", str(ruta))
    monkeypatch.setenv("APP_PASSWORD_HASH", generar_hash("clave-de-prueba-inventada"))
    monkeypatch.setenv("SESSION_SECRET", "secreto-de-prueba-inventado-de-mas-de-32-caracteres")
    # Sin configurar el saldo: código 2 y estado fallida.
    assert sincronizacion.main([], fabrica_cliente=lambda _c: ClienteFalso()) == 2
    [fila] = _fila_estado(ruta)
    assert (fila["estado"], fila["codigo_error"], fila["origen"]) == ("fallida", "sin_fecha_inicio", "comando")
