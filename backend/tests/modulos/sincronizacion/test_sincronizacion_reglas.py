"""Criterio de terminado del ítem 04: las reglas se aplican al sincronizar.

Crear una regla para un comercio (o una cuenta destino) hace que los
movimientos siguientes de ese comercio lleguen ya categorizados desde Gmail;
lo que no coincide queda en la bandeja "Sin categorizar". Correos inventados,
con los encabezados legítimos de ``tests/soporte/gmail_falso.py``.
"""

from __future__ import annotations

from finanzas.modulos.sincronizacion import registro_sqlite

from datetime import datetime

import pytest

from finanzas import categorizacion, db
from finanzas.gmail import ZONA_COLOMBIA, CorreoGmail
from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar
from tests.soporte.gmail_falso import LEGITIMO, ClienteFalso
from tests.soporte.ayudas_db import sql


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "reglas.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
            "VALUES (1, 100000000, '2026-08-01')"
        )
    yield conexion
    conexion.close()


def _correo(gmail_id: str, texto: str, dia: int = 15) -> CorreoGmail:
    return CorreoGmail(
        gmail_id, datetime(2026, 8, dia, 14, 40, tzinfo=ZONA_COLOMBIA), "Aviso (ejemplo)", texto, **LEGITIMO
    )


def _compra(comercio: str, dia: int = 15) -> str:
    return f"Bancolombia: Compraste $68.630,00 en {comercio} con tu T.Deb *1234, el {dia:02d}/08/2026 a las 14:32."


def _transferencia(destino: str) -> str:
    return f"Bancolombia: Transferiste $6,000.00 desde tu cuenta *1234 a la cuenta {destino} el 16/08/26 a las 09:15."


def _categoria(conn, gmail_id):
    return sql(conn, "SELECT categoria_id FROM movimientos WHERE gmail_id = ?", (gmail_id,)).fetchone()[0]


def _id_categoria(conn, nombre):
    return sql(conn, "SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]


def test_regla_creada_categoriza_los_siguientes_de_ese_comercio(conn):
    mercado = _id_categoria(conn, "Mercado")

    # 1. Llega la primera compra del comercio: sin regla, cae en la bandeja.
    assert sincronizar(conn, ClienteFalso({"c-1": _correo("c-1", _compra("MERPAGO*TIENDA", 15), 15)})) == \
        ResultadoSincronizacion(nuevos=1)
    assert _categoria(conn, "c-1") is None
    primero = categorizacion.sin_categorizar(conn)[0]["id"]

    # 2. El dueño la categoriza y marca "recordar".
    assert categorizacion.asignar_categoria(conn, primero, mercado, recordar=True) == 1

    # 3. Siguiente sincronización: el mismo comercio llega categorizado; otro
    #    comercio (incluido uno que solo lo contiene) queda en la bandeja.
    cliente = ClienteFalso({
        "c-2": _correo("c-2", _compra("MERPAGO*TIENDA", 16), 16),
        "c-3": _correo("c-3", _compra("PANADERIA EJEMPLO", 17), 17),
        "c-4": _correo("c-4", _compra("MERPAGO*TIENDA2", 18), 18),
    })
    assert sincronizar(conn, cliente) == ResultadoSincronizacion(nuevos=3)

    assert _categoria(conn, "c-2") == mercado
    assert _categoria(conn, "c-3") is None
    assert _categoria(conn, "c-4") is None
    bandeja = {fila["descripcion"] for fila in categorizacion.sin_categorizar(conn)}
    assert bandeja == {"PANADERIA EJEMPLO", "MERPAGO*TIENDA2"}


def test_regla_por_cuenta_destino_categoriza_transferencias(conn):
    vivienda = _id_categoria(conn, "Vivienda y servicios")
    sincronizar(conn, ClienteFalso({"t-1": _correo("t-1", _transferencia("*5678"))}))
    categorizacion.asignar_categoria(conn, categorizacion.sin_categorizar(conn)[0]["id"], vivienda, recordar=True)

    sincronizar(conn, ClienteFalso({
        "t-2": _correo("t-2", _transferencia("*5678"), 17),
        "t-3": _correo("t-3", _transferencia("*4321"), 17),
    }))

    assert _categoria(conn, "t-2") == vivienda
    assert _categoria(conn, "t-3") is None


def test_sin_reglas_todo_queda_en_la_bandeja(conn):
    sincronizar(conn, ClienteFalso({"c-1": _correo("c-1", _compra("TIENDA EJEMPLO"))}))
    assert [f["descripcion"] for f in categorizacion.sin_categorizar(conn)] == ["TIENDA EJEMPLO"]


# --- Carrera con "Recordar" (ronda 1 de revisión) ---------------------------------------------

def test_regla_guardada_justo_antes_del_insert_categoriza(conn, tmp_path, monkeypatch):
    """La web guarda la regla después de que la sincronización leyó el correo,
    pero antes del INSERT: el movimiento llega categorizado, porque la regla
    se consulta dentro de la misma transacción del INSERT."""
    from finanzas import sincronizacion

    mercado = _id_categoria(conn, "Mercado")
    with db.transaccion(conn):
        previo = sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen) "
            "VALUES ('2026-08-10T10:00:00', 5000, 'compra', 'TIENDA CARRERA', 'manual')"
        ).lastrowid
    guardar_original = registro_sqlite._guardar_movimiento
    regla_original = registro_sqlite._columnas_de_categoria
    dentro_de_transaccion: list[bool] = []

    def guardar_con_regla_de_la_web(c, gmail_id, movimiento, **kwargs):
        web = db.conectar(str(tmp_path / "reglas.db"))
        try:
            categorizacion.asignar_categoria(web, previo, mercado, recordar=True)
        finally:
            web.close()
        return guardar_original(c, gmail_id, movimiento, **kwargs)

    def regla_espiada(c, movimiento, **kwargs):
        dentro_de_transaccion.append(db.en_transaccion(c))
        return regla_original(c, movimiento, **kwargs)

    monkeypatch.setattr(registro_sqlite, "_guardar_movimiento", guardar_con_regla_de_la_web)
    monkeypatch.setattr(registro_sqlite, "_columnas_de_categoria", regla_espiada)

    assert sincronizar(conn, ClienteFalso({"c-1": _correo("c-1", _compra("TIENDA CARRERA"))})) == \
        ResultadoSincronizacion(nuevos=1)
    assert dentro_de_transaccion == [True]
    assert _categoria(conn, "c-1") == mercado


def test_la_consulta_de_reglas_reserva_la_escritura(conn, tmp_path, monkeypatch):
    """Mientras se consulta la regla, ninguna otra conexión puede escribir."""
    import sqlite3

    from finanzas import sincronizacion

    regla_original = registro_sqlite._columnas_de_categoria
    intentos: list[str] = []

    def regla_con_intruso(c, movimiento, **kwargs):
        otra = sqlite3.connect(str(tmp_path / "reglas.db"), timeout=0)
        try:
            otra.execute("INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'x', 1)")
        except sqlite3.OperationalError as error:
            intentos.append(str(error))
        finally:
            otra.close()
        return regla_original(c, movimiento, **kwargs)

    monkeypatch.setattr(registro_sqlite, "_columnas_de_categoria", regla_con_intruso)
    assert sincronizar(conn, ClienteFalso({"c-1": _correo("c-1", _compra("TIENDA EJEMPLO"))})) == \
        ResultadoSincronizacion(nuevos=1)
    assert intentos == ["database is locked"]
    assert categorizacion.listar_reglas(conn) == []
