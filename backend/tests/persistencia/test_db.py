"""Pruebas del esquema SQLite (finanzas/db.py)."""

import sqlite3

import pytest

from finanzas import db
from tests.soporte.ayudas_db import sql

TABLAS = {"categorias", "movimientos", "reglas", "configuracion_saldo", "correos_no_reconocidos"}


@pytest.fixture
def conn(tmp_path):
    c = db.conectar(str(tmp_path / "prueba.db"))
    db.inicializar(c)
    yield c
    c.close()


def _movimiento(conn, **cambios):
    datos = {
        "fecha_hora": "2026-08-07T16:42:00",
        "monto_centavos": 600000,
        "tipo": "compra",
        "descripcion": "TIENDA EJEMPLO",
        "origen": "gmail",
        "gmail_id": "correo-1",
    }
    datos.update(cambios)
    columnas = ", ".join(datos)
    marcas = ", ".join("?" for _ in datos)
    with db.transaccion(conn):
        sql(conn, f"INSERT INTO movimientos ({columnas}) VALUES ({marcas})", list(datos.values()))


def test_crea_todas_las_tablas_y_el_indice(conn):
    nombres = {f["name"] for f in sql(conn, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert TABLAS <= nombres
    indices = {f["name"] for f in sql(conn, "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_movimientos_fecha_hora" in indices


def test_foreign_keys_activas(conn):
    assert sql(conn, "PRAGMA foreign_keys").fetchone()[0] == 1


def test_inicializar_es_idempotente_y_carga_las_12_categorias_iniciales(conn):
    db.inicializar(conn)
    db.inicializar(conn)
    filas = [tuple(f) for f in sql(conn, "SELECT nombre, clase, color, icono FROM categorias ORDER BY id")]
    assert sorted(filas) == sorted(db.CATEGORIAS_INICIALES)
    assert [n for n, *_ in filas[:8]] == list(db.CATEGORIAS_FIJAS)  # los ids de la v1


def test_gmail_id_es_unico(conn):
    _movimiento(conn, gmail_id="repetido")
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, gmail_id="repetido")


def test_varios_manuales_sin_gmail_id(conn):
    _movimiento(conn, tipo="ingreso", origen="manual", gmail_id=None)
    _movimiento(conn, tipo="ingreso", origen="manual", gmail_id=None)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 2


def test_check_tipo(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, tipo="retiro")


def test_check_origen(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, origen="nequi")


def test_manual_no_puede_tener_gmail_id(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, tipo="ingreso", origen="manual", gmail_id="x")


@pytest.mark.parametrize("tipo", ["compra", "transferencia", "ingreso"])
@pytest.mark.parametrize("monto", [0, -100])
def test_monto_no_positivo_rechazado_salvo_ajuste(conn, tipo, monto):
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, tipo=tipo, monto_centavos=monto)


def test_ajuste_admite_negativo_y_cero_desde_la_0008(conn):
    """D45: lo importado del banco puede reducir un ajuste hasta 0 sin borrarlo.

    ``saldo.ajustar_saldo`` sigue sin guardar un ajuste de 0 (tests/modulos/saldo/test_saldo.py).
    """
    _movimiento(conn, tipo="ajuste", origen="manual", gmail_id=None, monto_centavos=-450000)
    _movimiento(conn, tipo="ajuste", origen="manual", gmail_id=None, monto_centavos=1050)
    _movimiento(conn, tipo="ajuste", origen="manual", gmail_id=None, monto_centavos=0)
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, tipo="compra", monto_centavos=0)


@pytest.mark.parametrize("monto", [12.5, 1000.75, "abc", b"\x01"])
def test_monto_no_entero_rechazado(conn, monto):
    # La especificación exige enteros en centavos; sin el CHECK de typeof,
    # SQLite guardaría 12.5 o 'abc' tal cual.
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, monto_centavos=monto)
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, tipo="ajuste", origen="manual", gmail_id=None, monto_centavos=monto)


def test_monto_real_exacto_se_convierte_a_entero(conn):
    # Afinidad INTEGER: 1500.0 se guarda como 1500 (entero), no se pierde nada.
    _movimiento(conn, monto_centavos=1500.0)
    fila = sql(conn, "SELECT typeof(monto_centavos), monto_centavos FROM movimientos").fetchone()
    assert tuple(fila) == ("integer", 1500)


def test_gmail_sin_gmail_id_rechazado(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, origen="gmail", gmail_id=None)


@pytest.mark.parametrize("saldo", [12.5, "abc"])
def test_saldo_inicial_no_entero_rechazado(conn, saldo):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(
                conn,
                "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
                "VALUES (1, ?, '2026-09-01')",
                (saldo,),
            )


def test_saldo_inicial_negativo_permitido(conn):
    # Un saldo inicial en sobregiro no es imposible; solo se exige entero.
    with db.transaccion(conn):
        sql(
            conn,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
            "VALUES (1, -5000, '2026-09-01')"
        )


def test_regla_con_texto_vacio_rechazada(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', '', 1)")


def test_categoria_inexistente_rechazada(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _movimiento(conn, categoria_id=999)


def test_reglas_unicas_y_campo_valido(conn):
    with db.transaccion(conn):
        sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'TIENDA', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'TIENDA', 2)")
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('tarjeta', 'X', 1)")


def test_configuracion_saldo_una_sola_fila(conn):
    with db.transaccion(conn):
        sql(
            conn,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
            "VALUES (1, 100000, '2026-09-01')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(
                conn,
                "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
                "VALUES (2, 5, '2026-09-02')"
            )
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(
                conn,
                "INSERT INTO configuracion_saldo (saldo_inicial_centavos, fecha_inicio) "
                "VALUES (5, '2026-09-02')"
            )


def test_correos_no_reconocidos_sin_columna_de_cuerpo(conn):
    columnas = {f["name"] for f in sql(conn, "PRAGMA table_info(correos_no_reconocidos)")}
    assert columnas == {"gmail_id", "fecha", "asunto"}


# --- Ítem 22: los errores de la base no llevan valores a los registros ------------

MONTO_SECRETO = -987654321
TEXTO_SECRETO = "COMERCIO SECRETO INVENTADO ZXQ"


def test_error_de_check_no_muestra_los_valores(conn):
    import sqlalchemy.exc

    with pytest.raises(sqlalchemy.exc.IntegrityError) as error:
        with db.transaccion(conn):
            conn.execute(
                db.movimientos.insert().values(
                    fecha_hora="2026-08-07T16:42:00", monto_centavos=MONTO_SECRETO,
                    tipo="compra", descripcion=TEXTO_SECRETO, origen="gmail", gmail_id="id-secreto",
                )
            )
    texto = str(error.value)
    assert "CHECK constraint failed" in texto  # el error se sigue entendiendo
    assert str(MONTO_SECRETO) not in texto
    assert TEXTO_SECRETO not in texto
    assert "id-secreto" not in texto


def test_error_de_la_conexion_de_migrar_no_muestra_los_valores(tmp_path):
    import sqlalchemy.exc
    from sqlalchemy import text

    from finanzas import migrar

    ruta = str(tmp_path / "migrar.db")
    migrar.aplicar(ruta)
    with migrar.conectar_para_migrar(ruta) as conexion:
        with pytest.raises(sqlalchemy.exc.IntegrityError) as error:
            with conexion.begin():
                conexion.execute(
                    text("INSERT INTO reglas (campo, texto, categoria_id) VALUES ('tarjeta', :t, 1)"),
                    {"t": TEXTO_SECRETO},
                )
    assert "CHECK constraint failed" in str(error.value)
    assert TEXTO_SECRETO not in str(error.value)
