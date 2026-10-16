"""Última sincronización correcta: migración 0003 y ``guardar_estado`` (ítem 13).

Datos inventados. La 0003 añade ``ultima_correcta_en`` a
``estado_sincronizacion`` y la rellena desde la fila existente si no es
``fallida``; ``guardar_estado`` la fija al terminar bien y la conserva al fallar.
"""

from __future__ import annotations
from finanzas.infraestructura import persistencia

from finanzas.modulos.sincronizacion import registro_sqlite

import shutil
import sqlite3
from datetime import datetime

import pytest
from alembic import command

from finanzas import db, migrar, sincronizacion
from finanzas.compartido import hora
from finanzas.migraciones import esquema_v1
from finanzas.sincronizacion import ResultadoSincronizacion

from tests.soporte.migracion_0005 import _subir_hasta
from tests.soporte.migraciones import crear_base_v1, huella, revision, volcado

FILA_OK = (
    "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, nuevos, duplicados, "
    "no_reconocidos, errores, rechazados_autenticacion) "
    "VALUES (1, '2026-09-20T06:00:00', ?, 'comando', 2, 0, 0, ?, 0)"
)
FILA_FALLIDA = (
    "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, codigo_error) "
    "VALUES (1, '2026-09-21T12:00:00', 'fallida', 'web', 'autorizacion_gmail')"
)


def _sql(ruta, texto, parametros=()):
    conn = sqlite3.connect(ruta)
    try:
        with conn:
            return conn.execute(texto, parametros).fetchall()
    finally:
        conn.close()


def _filas(ruta):
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(f) for f in conn.execute("SELECT * FROM estado_sincronizacion")]
    finally:
        conn.close()


def _columnas(ruta):
    return [f[1] for f in _sql(ruta, "PRAGMA table_xinfo(estado_sincronizacion)")]


def _estructura(ruta):
    """Descripción de todas las tablas (columnas, índices, claves y CHECK)."""
    conn = sqlite3.connect(ruta)
    try:
        return esquema_v1.describir(conn)
    finally:
        conn.close()


def _subir_hasta_0002(ruta):
    """Como ``migrar.aplicar`` pero parando en la 0002 (sin pasar nunca por la 0003)."""
    marcar_v1 = migrar.diagnosticar(str(ruta)).marcar_v1
    with migrar.conectar_para_migrar(str(ruta)) as conexion, conexion.begin():
        config = migrar._config(conexion)
        if marcar_v1:
            command.stamp(config, migrar.REVISION_V1)
        command.upgrade(config, "0002")


@pytest.fixture
def base_0002(tmp_path):
    """Base de la v1 con datos, subida solo hasta la 0002 (como la de producción hoy)."""
    ruta = tmp_path / "produccion-inventada.db"
    crear_base_v1(ruta)
    _subir_hasta_0002(ruta)
    assert revision(ruta) == "0002"
    return ruta


@pytest.fixture
def respaldos(tmp_path):
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    return carpeta


@pytest.fixture
def conn(tmp_path):
    ruta = tmp_path / "estado.db"
    db.preparar(str(ruta))
    conexion = db.conectar(str(ruta))
    yield conexion
    conexion.close()


def _a_las(monkeypatch, *momento):
    monkeypatch.setattr(hora, "ahora_colombia", lambda: datetime(*momento))


# --- Migración 0003 ---------------------------------------------------------------------

def test_0003_sigue_a_0002():
    # Desde el ítem 14 ya no es la última (le siguen la 0004, la 0005 y la 0006).
    assert migrar._scripts().get_revision("0003").down_revision == "0002"


def test_sin_fila_agrega_la_columna_y_no_cambia_nada_mas(base_0002):
    antes = volcado(base_0002)
    assert "ultima_correcta_en" not in _columnas(base_0002)
    assert migrar.aplicar(str(base_0002)).pendientes == ["0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010", "0011", "0012"]
    assert revision(base_0002) == migrar.revision_final()
    assert _columnas(base_0002)[-1] == "ultima_correcta_en"
    assert _filas(base_0002) == []
    assert volcado(base_0002) == antes


@pytest.mark.parametrize("estado, errores", [("ok", 0), ("con_errores", 3)])
def test_fila_correcta_se_rellena_con_su_terminada_en(base_0002, estado, errores):
    _sql(base_0002, FILA_OK, (estado, errores))
    migrar.aplicar(str(base_0002))
    [fila] = _filas(base_0002)
    assert fila["estado"] == estado
    assert fila["ultima_correcta_en"] == fila["terminada_en"] == "2026-09-20T06:00:00"
    assert (fila["nuevos"], fila["errores"], fila["origen"]) == (2, errores, "comando")


def test_fila_fallida_queda_en_null(base_0002):
    _sql(base_0002, FILA_FALLIDA)
    migrar.aplicar(str(base_0002))
    [fila] = _filas(base_0002)
    assert fila["ultima_correcta_en"] is None
    assert (fila["estado"], fila["codigo_error"], fila["terminada_en"]) == (
        "fallida", "autorizacion_gmail", "2026-09-21T12:00:00",
    )


def test_migrar_otra_vez_no_cambia_nada(base_0002):
    _sql(base_0002, FILA_OK, ("ok", 0))
    migrar.aplicar(str(base_0002))
    huella_antes = huella(base_0002)
    assert migrar.aplicar(str(base_0002)).al_dia
    assert huella(base_0002) == huella_antes


def test_bajar_a_0002_quita_solo_la_columna_y_conserva_los_check(base_0002, tmp_path):
    # Referencia: una base nueva subida solo hasta la 0002.
    nueva_0002 = tmp_path / "nueva-0002.db"
    _subir_hasta_0002(nueva_0002)
    estructura_0002 = _estructura(nueva_0002)
    assert _estructura(base_0002) == estructura_0002
    _sql(base_0002, FILA_OK, ("con_errores", 1))
    fila_0002 = _filas(base_0002)
    # La 0009 recorta datos irreversiblemente; este caso prueba solo la
    # reversibilidad histórica de 0008 y anteriores.
    _subir_hasta(base_0002, "0008")
    datos = volcado(base_0002)

    assert migrar.bajar_a(str(base_0002), "0002") == ["0008", "0007", "0006", "0005", "0004", "0003"]
    assert revision(base_0002) == "0002"
    assert "ultima_correcta_en" not in _columnas(base_0002)
    assert _estructura(base_0002) == estructura_0002  # mismos CHECK que creó la 0002
    assert _filas(base_0002) == fila_0002
    assert volcado(base_0002) == datos

    _subir_hasta(base_0002, "0008")  # y de vuelta: se vuelve a rellenar
    assert _filas(base_0002)[0]["ultima_correcta_en"] == "2026-09-20T06:00:00"


def test_los_check_de_la_0002_siguen_activos_tras_migrar(base_0002):
    migrar.aplicar(str(base_0002))
    with pytest.raises(sqlite3.IntegrityError):
        _sql(
            base_0002,
            "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, codigo_error, "
            "ultima_correcta_en) VALUES (1, 'x', 'fallida', 'web', 'texto libre', 'x')",
        )


def test_comando_hace_respaldo_antes_de_la_0003_y_al_bajar(base_0002, respaldos, capsys):
    _sql(base_0002, FILA_OK, ("ok", 0))
    assert migrar.main(["--base", str(base_0002), "--respaldos", str(respaldos)]) == 0
    salida = capsys.readouterr().out
    assert "Migraciones aplicadas: 0003, 0004, 0005, 0006, 0007, 0008, 0009, 0010, 0011, 0012." in salida
    [previo] = respaldos.glob("finanzas-antes-de-migrar-0002-*.db")
    assert revision(previo) == "0002" and "ultima_correcta_en" not in _columnas(previo)
    assert "2026-09-20" not in salida  # no imprime datos

    # Restaurar el respaldo es la salida correcta de 0009. Después
    # comprobamos que las migraciones históricas sí pueden bajarse.
    shutil.copyfile(previo, base_0002)
    assert revision(base_0002) == "0002"
    _subir_hasta(base_0002, "0008")

    assert migrar.main(
        ["--base", str(base_0002), "--respaldos", str(respaldos), "--bajar-a", "0002"]
    ) == 0
    assert list(respaldos.glob("finanzas-antes-de-migrar-0008-*.db"))
    assert revision(base_0002) == "0002"


def test_comprobar_ve_la_0003_pendiente(base_0002, capsys):
    assert migrar.main(["--base", str(base_0002), "--comprobar"]) == 1
    assert "Migraciones pendientes: 0003, 0004, 0005, 0006, 0007, 0008, 0009, 0010, 0011, 0012." in capsys.readouterr().out


# --- guardar_estado ---------------------------------------------------------------------

def test_primera_vez_correcta_fija_la_fecha(conn, monkeypatch):
    _a_las(monkeypatch, 2026, 9, 1, 6, 0, 0)
    guardado = sincronizacion.guardar_estado(conn, "comando", resultado=ResultadoSincronizacion(nuevos=1))
    assert guardado.ultima_correcta_en == guardado.terminada_en == "2026-09-01T06:00:00"
    assert sincronizacion.leer_estado(conn) == guardado


def test_primera_vez_fallida_queda_en_none(conn):
    guardado = sincronizacion.guardar_estado(conn, "web", codigo_error="autorizacion_gmail")
    assert guardado.ultima_correcta_en is None
    assert sincronizacion.leer_estado(conn).ultima_correcta_en is None


def test_una_fallida_conserva_la_ultima_correcta(conn, monkeypatch):
    _a_las(monkeypatch, 2026, 9, 1, 6, 0, 0)
    sincronizacion.guardar_estado(conn, "comando", resultado=ResultadoSincronizacion(nuevos=1))
    for hora_fallo in (12, 18):  # dos fallos seguidos no la pierden
        _a_las(monkeypatch, 2026, 9, 1, hora_fallo, 0, 0)
        guardado = sincronizacion.guardar_estado(conn, "comando", codigo_error="error_inesperado")
        assert guardado.ultima_correcta_en == "2026-09-01T06:00:00"
    estado = sincronizacion.leer_estado(conn)
    assert estado == guardado
    assert (estado.estado, estado.terminada_en) == ("fallida", "2026-09-01T18:00:00")
    assert estado.ultima_correcta_en == "2026-09-01T06:00:00"


def test_con_errores_cuenta_como_correcta(conn, monkeypatch):
    _a_las(monkeypatch, 2026, 9, 1, 6, 0, 0)
    sincronizacion.guardar_estado(conn, "web", codigo_error="gmail_no_configurado")
    _a_las(monkeypatch, 2026, 9, 1, 7, 30, 0)
    guardado = sincronizacion.guardar_estado(conn, "web", resultado=ResultadoSincronizacion(errores=2))
    assert guardado.estado == "con_errores"
    assert sincronizacion.leer_estado(conn).ultima_correcta_en == "2026-09-01T07:30:00"


def test_una_correcta_despues_de_fallar_la_actualiza(conn, monkeypatch):
    _a_las(monkeypatch, 2026, 9, 1, 6, 0, 0)
    sincronizacion.guardar_estado(conn, "comando", resultado=ResultadoSincronizacion())
    _a_las(monkeypatch, 2026, 9, 1, 12, 0, 0)
    sincronizacion.guardar_estado(conn, "comando", codigo_error="autorizacion_gmail")
    _a_las(monkeypatch, 2026, 9, 2, 6, 0, 0)
    sincronizacion.guardar_estado(conn, "web", resultado=ResultadoSincronizacion(nuevos=4))
    estado = sincronizacion.leer_estado(conn)
    assert estado.ultima_correcta_en == estado.terminada_en == "2026-09-02T06:00:00"


def test_ejecutar_con_error_conserva_la_ultima_correcta(conn, monkeypatch):
    from finanzas.gmail import ErrorAutorizacionGmail
    from tests.soporte.gmail_falso import ClienteFalso

    with db.transaccion(conn):
        conn.exec_driver_sql("INSERT INTO configuracion_saldo VALUES (1, 100, '2026-08-01')")
    _a_las(monkeypatch, 2026, 9, 1, 6, 0, 0)
    sincronizacion.ejecutar(conn, ClienteFalso)

    def fabrica():
        raise ErrorAutorizacionGmail("token revocado inventado")

    _a_las(monkeypatch, 2026, 9, 1, 12, 0, 0)
    estado = sincronizacion.ejecutar_con_estado(conn, fabrica)
    assert estado.codigo_error == "autorizacion_gmail"
    assert estado.ultima_correcta_en == "2026-09-01T06:00:00"


def test_si_no_se_puede_guardar_una_correcta_devuelve_la_que_quedo(conn, monkeypatch, caplog):
    _a_las(monkeypatch, 2026, 9, 1, 6, 0, 0)
    sincronizacion.guardar_estado(conn, "comando", resultado=ResultadoSincronizacion(nuevos=1))

    def falla(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    _a_las(monkeypatch, 2026, 9, 1, 12, 0, 0)
    with monkeypatch.context() as parche:
        parche.setattr(persistencia, "transaccion", falla)
        estado = sincronizacion.guardar_estado(conn, "web", resultado=ResultadoSincronizacion(nuevos=2))
    assert (estado.estado, estado.terminada_en) == ("ok", "2026-09-01T12:00:00")
    assert estado.ultima_correcta_en == "2026-09-01T06:00:00"  # la guardada, no la de esta
    assert not conn.in_transaction()  # la lectura de respaldo no deja la conexión abierta
    assert sincronizacion.leer_estado(conn).ultima_correcta_en == "2026-09-01T06:00:00"
    assert "No se pudo guardar el estado" in caplog.text


def test_si_no_se_puede_guardar_ni_leer_devuelve_none(conn, monkeypatch):
    def falla(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(persistencia, "transaccion", falla)
    monkeypatch.setattr(registro_sqlite, "_leer_ultima_correcta", falla)
    estado = sincronizacion.guardar_estado(conn, "web", resultado=ResultadoSincronizacion(nuevos=1))
    assert (estado.estado, estado.ultima_correcta_en) == ("ok", None)


def test_si_no_se_puede_guardar_una_fallida_no_falla(conn, monkeypatch, caplog):
    def falla(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(persistencia, "transaccion", falla)
    estado = sincronizacion.guardar_estado(conn, "web", codigo_error="error_inesperado")
    assert (estado.estado, estado.ultima_correcta_en) == ("fallida", None)
    assert "No se pudo guardar el estado" in caplog.text
