"""Cómo se categorizó cada movimiento (ítem 14): migración 0004 y lógica.

Datos inventados. La 0004 añade ``origen_categoria`` ("manual", "regla" o
NULL) y ``regla_id`` a ``movimientos``, sin rellenar nada: lo categorizado
antes queda como "desconocido" (NULL). Al categorizar a mano el origen pasa
a ``manual`` (también si lo había puesto una regla); al aplicar una regla,
a ``regla`` con su id.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime

import pytest
from alembic import command

from finanzas import categorizacion, db, migrar
from finanzas.gmail import ZONA_COLOMBIA, CorreoGmail
from finanzas.migraciones import esquema_v1
from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import LEGITIMO, ClienteFalso
from tests.soporte.migracion_0005 import _subir_hasta
from tests.soporte.migraciones import crear_base_v1, revision, volcado


def _sql(ruta, texto, parametros=()):
    conn = sqlite3.connect(ruta)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            return conn.execute(texto, parametros).fetchall()
    finally:
        conn.close()


def _origenes(ruta):
    return _sql(ruta, "SELECT id, origen_categoria, regla_id FROM movimientos ORDER BY id")


def _estructura(ruta):
    conn = sqlite3.connect(ruta)
    try:
        return esquema_v1.describir(conn)
    finally:
        conn.close()


def _subir_hasta_0003(ruta):
    """Como ``migrar.aplicar`` pero parando en la 0003 (como la base de producción hoy)."""
    marcar_v1 = migrar.diagnosticar(str(ruta)).marcar_v1
    with migrar.conectar_para_migrar(str(ruta)) as conexion, conexion.begin():
        config = migrar._config(conexion)
        if marcar_v1:
            command.stamp(config, migrar.REVISION_V1)
        command.upgrade(config, "0003")


@pytest.fixture
def base_0003(tmp_path):
    """Base de la v1 con datos (un movimiento categorizado y una regla), subida hasta la 0003."""
    ruta = tmp_path / "produccion-inventada.db"
    crear_base_v1(ruta)
    _subir_hasta_0003(ruta)
    assert revision(ruta) == "0003"
    return ruta


@pytest.fixture
def respaldos(tmp_path):
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    return carpeta


# --- Migración 0004 ---------------------------------------------------------------------

def test_0004_sigue_a_0003():
    # La última es la0012; esta prueba conserva el enlace histórico0004→0003.
    assert migrar._scripts().get_revision("0004").down_revision == "0003"


def test_no_adivina_el_origen_de_lo_ya_categorizado(base_0003):
    datos = volcado(base_0003)
    assert migrar.aplicar(str(base_0003)).pendientes == ["0004", "0005", "0006", "0007", "0008", "0009", "0010", "0011", "0012"]
    assert revision(base_0003) == migrar.revision_final()
    assert volcado(base_0003) == datos  # nada de la v1 cambia
    # El movimiento 1 ya tenía categoría y hay una regla que coincide con él:
    # aun así queda "desconocido" (NULL), igual que todos los demás.
    assert _sql(base_0003, "SELECT categoria_id FROM movimientos WHERE id = 1") == [(1,)]
    assert _sql(base_0003, "SELECT texto FROM reglas") == [("comercio inventado zxq",)]
    assert {(o, r) for _, o, r in _origenes(base_0003)} == {(None, None)}


def test_migrar_otra_vez_no_cambia_nada(base_0003):
    migrar.aplicar(str(base_0003))
    assert migrar.aplicar(str(base_0003)).al_dia


@pytest.mark.parametrize(
    "sentencia",
    [
        # Origen fuera de la lista.
        "UPDATE movimientos SET origen_categoria = 'adivinado' WHERE id = 1",
        # Regla sin origen "regla".
        "UPDATE movimientos SET origen_categoria = 'manual', regla_id = 1 WHERE id = 1",
        "UPDATE movimientos SET regla_id = 1 WHERE id = 1",
        # Regla que no existe (clave foránea).
        "UPDATE movimientos SET origen_categoria = 'regla', regla_id = 99 WHERE id = 1",
    ],
)
def test_las_restricciones_nuevas_rechazan_datos_incoherentes(base_0003, sentencia):
    migrar.aplicar(str(base_0003))
    with pytest.raises(sqlite3.IntegrityError):
        _sql(base_0003, sentencia)


def test_la_clave_foranea_no_deja_borrar_una_regla_en_uso(base_0003):
    migrar.aplicar(str(base_0003))
    _sql(base_0003, "UPDATE movimientos SET origen_categoria = 'regla', regla_id = 1 WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        _sql(base_0003, "DELETE FROM reglas WHERE id = 1")


def test_los_check_anteriores_siguen_activos_tras_migrar(base_0003):
    migrar.aplicar(str(base_0003))
    with pytest.raises(sqlite3.IntegrityError):
        _sql(
            base_0003,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id) "
            "VALUES ('x', 0, 'compra', 'gmail', 'id-inventado-x')",
        )


def test_bajar_a_0003_deja_la_estructura_exacta_y_conserva_los_datos(base_0003, tmp_path):
    referencia = tmp_path / "nueva-0003.db"
    _subir_hasta_0003(referencia)
    estructura_0003 = _estructura(referencia)
    assert _estructura(base_0003) == estructura_0003

    # La 0009 recorta datos irreversiblemente; este caso prueba solo la
    # reversibilidad histórica de 0008 y anteriores.
    _subir_hasta(base_0003, "0008")
    _sql(base_0003, "UPDATE movimientos SET origen_categoria = 'regla', regla_id = 1 WHERE id = 1")
    _sql(base_0003, "UPDATE movimientos SET origen_categoria = 'manual' WHERE id = 2")
    datos = volcado(base_0003)

    assert migrar.bajar_a(str(base_0003), "0003") == ["0008", "0007", "0006", "0005", "0004"]
    assert revision(base_0003) == "0003"
    assert _estructura(base_0003) == estructura_0003  # mismas columnas, CHECK, UNIQUE e índice
    assert volcado(base_0003) == datos  # mismas filas, con sus ids
    with pytest.raises(sqlite3.IntegrityError):  # los CHECK de la 0001 siguen ahí
        _sql(
            base_0003,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id) "
            "VALUES ('x', 1, 'compra', 'manual', 'id-inventado-x')",
        )

    _subir_hasta(base_0003, "0008")  # y de vuelta: el dato se perdió, queda desconocido
    assert revision(base_0003) == "0008"
    assert {(o, r) for _, o, r in _origenes(base_0003)} == {(None, None)}
    assert volcado(base_0003) == datos


def test_comando_hace_respaldo_antes_de_la_0004_y_al_bajar(base_0003, respaldos, capsys):
    assert migrar.main(["--base", str(base_0003), "--respaldos", str(respaldos)]) == 0
    salida = capsys.readouterr().out
    assert "Migraciones aplicadas: 0004, 0005, 0006, 0007, 0008, 0009, 0010, 0011, 0012." in salida
    [previo] = respaldos.glob("finanzas-antes-de-migrar-0003-*.db")
    assert revision(previo) == "0003"
    assert "COMERCIO" not in salida.upper()  # no imprime datos

    # Restaurar el respaldo es la salida correcta de 0009. Después
    # comprobamos que las migraciones históricas sí pueden bajarse.
    shutil.copyfile(previo, base_0003)
    assert revision(base_0003) == "0003"
    _subir_hasta(base_0003, "0008")

    assert migrar.main(
        ["--base", str(base_0003), "--respaldos", str(respaldos), "--bajar-a", "0003"]
    ) == 0
    assert list(respaldos.glob("finanzas-antes-de-migrar-0008-*.db"))
    assert revision(base_0003) == "0003"


# --- Categorizar a mano y por regla ---------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "origen.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
            "VALUES (1, 100000000, '2026-08-01')",
        )
    yield conexion
    conexion.close()


def _mov(conn, descripcion="TIENDA INVENTADA", tipo="compra", categoria_id=None, dia=10):
    with db.transaccion(conn):
        return sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen) "
            "VALUES (?, 5000, ?, ?, ?, 'manual')",
            (f"2026-08-{dia:02d}T10:00:00", tipo, descripcion, categoria_id),
        ).lastrowid


def _estado(conn, movimiento_id):
    return tuple(
        sql(
            conn,
            "SELECT categoria_id, origen_categoria, regla_id FROM movimientos WHERE id = ?",
            (movimiento_id,),
        ).fetchone()
    )


def _regla_id(conn):
    return sql(conn, "SELECT id FROM reglas").fetchone()[0]


def test_a_mano_queda_manual_y_sin_regla(conn):
    uno = _mov(conn)
    resultado = categorizacion.asignar_con_detalle(conn, uno, 3, recordar=False)
    assert resultado == categorizacion.Asignacion(total=1, regla_id=None)
    assert _estado(conn, uno) == (3, "manual", None)


def test_recordar_el_pedido_queda_manual_y_los_demas_por_la_regla(conn):
    uno = _mov(conn, "Tienda  Inventada", dia=10)
    otro = _mov(conn, "TIENDA INVENTADA", dia=11)
    ya = _mov(conn, "TIENDA INVENTADA", categoria_id=5, dia=12)
    resultado = categorizacion.asignar_con_detalle(conn, uno, 1, recordar=True)
    regla = _regla_id(conn)
    assert resultado == categorizacion.Asignacion(total=2, regla_id=regla)
    assert _estado(conn, uno) == (1, "manual", None)
    assert _estado(conn, otro) == (1, "regla", regla)
    assert _estado(conn, ya) == (5, None, None)  # lo ya categorizado no se toca


def test_recordar_un_texto_que_ya_tenia_regla_devuelve_la_misma_regla(conn):
    uno = _mov(conn, dia=10)
    dos = _mov(conn, dia=11)
    primera = categorizacion.asignar_con_detalle(conn, uno, 1, recordar=True).regla_id
    segunda = categorizacion.asignar_con_detalle(conn, dos, 2, recordar=True).regla_id
    assert primera == segunda
    assert sql(conn, "SELECT categoria_id FROM reglas").fetchall() == [(2,)]


def test_corregir_uno_categorizado_por_regla_lo_marca_manual(conn):
    """Criterio de terminado del ítem 14."""
    uno = _mov(conn, dia=10)
    otro = _mov(conn, dia=11)
    categorizacion.asignar_categoria(conn, uno, 1, recordar=True)
    assert _estado(conn, otro)[1] == "regla"
    assert categorizacion.asignar_categoria(conn, otro, 4, recordar=False) == 1
    assert _estado(conn, otro) == (4, "manual", None)


def test_volver_a_poner_la_misma_categoria_tambien_queda_manual(conn):
    uno = _mov(conn, dia=10)
    otro = _mov(conn, dia=11)
    categorizacion.asignar_categoria(conn, uno, 1, recordar=True)
    categorizacion.asignar_categoria(conn, otro, 1, recordar=False)
    assert _estado(conn, otro) == (1, "manual", None)


def test_un_error_no_cambia_el_origen(conn):
    uno = _mov(conn, dia=10)
    otro = _mov(conn, dia=11)
    categorizacion.asignar_categoria(conn, uno, 1, recordar=True)
    antes = _estado(conn, otro)
    with pytest.raises(categorizacion.ErrorCategorizacion):
        categorizacion.asignar_categoria(conn, otro, 999, recordar=False)
    assert _estado(conn, otro) == antes


def test_borrar_la_regla_conserva_categoria_y_origen_pero_la_desliga(conn):
    uno = _mov(conn, dia=10)
    otro = _mov(conn, dia=11)
    categorizacion.asignar_categoria(conn, uno, 1, recordar=True)
    regla = _regla_id(conn)
    categorizacion.borrar_regla(conn, regla)
    assert _estado(conn, otro) == (1, "regla", None)
    assert _estado(conn, uno) == (1, "manual", None)
    # Una regla nueva puede reutilizar el id: el movimiento no pasa a señalarla.
    tercero = _mov(conn, "OTRA TIENDA", dia=12)
    categorizacion.asignar_categoria(conn, tercero, 2, recordar=True)
    assert _estado(conn, otro) == (1, "regla", None)


def test_buscar_regla(conn):
    uno = _mov(conn)
    categorizacion.asignar_categoria(conn, uno, 1, recordar=True)
    regla = _regla_id(conn)
    assert dict(categorizacion.buscar_regla(conn, regla)) == {
        "id": regla, "campo": "comercio", "texto": "tienda inventada", "monto_centavos": None,
        "modo_texto": "exacta", "origen_regla": "todos", "texto_visible": None,
    }
    assert categorizacion.buscar_regla(conn, regla + 1) is None


def test_regla_que_coincide(conn):
    uno = _mov(conn, "*5678", tipo="transferencia")
    categorizacion.asignar_categoria(conn, uno, 3, recordar=True)
    regla = dict(categorizacion.regla_que_coincide(conn, "transferencia", " *5678 ", 100))
    assert regla == {
        "id": _regla_id(conn), "categoria_id": 3, "texto": "*5678",
        "modo_texto": "exacta", "origen_regla": "todos",
    }
    assert categorizacion.regla_que_coincide(conn, "compra", "*5678", 100) is None
    assert categorizacion.regla_que_coincide(conn, "ingreso", "*5678", 100) is None


# --- Al sincronizar -----------------------------------------------------------------------

def _correo(gmail_id: str, comercio: str, dia: int) -> CorreoGmail:
    texto = (
        f"Bancolombia: Compraste $68.630,00 en {comercio} con tu T.Deb *1234, "
        f"el {dia:02d}/08/2026 a las 14:32."
    )
    return CorreoGmail(
        gmail_id, datetime(2026, 8, dia, 14, 40, tzinfo=ZONA_COLOMBIA), "Aviso (ejemplo)", texto, **LEGITIMO
    )


def _estado_gmail(conn, gmail_id):
    return tuple(
        sql(
            conn,
            "SELECT categoria_id, origen_categoria, regla_id FROM movimientos WHERE gmail_id = ?",
            (gmail_id,),
        ).fetchone()
    )


def test_al_sincronizar_la_regla_guarda_origen_y_su_id(conn):
    uno = _mov(conn, "MERPAGO*TIENDA", dia=10)
    categorizacion.asignar_categoria(conn, uno, 1, recordar=True)
    regla = _regla_id(conn)
    cliente = ClienteFalso({
        "c-1": _correo("c-1", "MERPAGO*TIENDA", 15),
        "c-2": _correo("c-2", "PANADERIA EJEMPLO", 16),
    })
    assert sincronizar(conn, cliente) == ResultadoSincronizacion(nuevos=2)
    assert _estado_gmail(conn, "c-1") == (1, "regla", regla)
    assert _estado_gmail(conn, "c-2") == (None, None, None)


# --- Una sola definición de pendiente, categorizable y regla posible -------------------------

@pytest.mark.parametrize(
    ("tipo", "categoria_id", "pendiente", "categorizable"),
    [
        ("compra", None, True, True),
        ("transferencia", None, True, True),
        ("compra", 1, False, True),
        ("ingreso", None, True, True),  # ítem 15
        ("ingreso", 10, False, True),
        ("ajuste", None, False, False),
    ],
)
def test_es_pendiente_y_es_categorizable(tipo, categoria_id, pendiente, categorizable):
    assert categorizacion.es_pendiente(tipo, categoria_id) is pendiente
    assert categorizacion.es_categorizable(tipo) is categorizable


def test_es_pendiente_coincide_con_la_consulta_de_la_bandeja(conn):
    ids = {
        _mov(conn, "UNO", tipo="compra", dia=1): ("compra", None),
        _mov(conn, "*5678", tipo="transferencia", dia=2): ("transferencia", None),
        _mov(conn, "DOS", tipo="compra", categoria_id=2, dia=3): ("compra", 2),
        _mov(conn, "PERSONA", tipo="ingreso", dia=4): ("ingreso", None),
    }
    esperados = {i for i, (tipo, cat) in ids.items() if categorizacion.es_pendiente(tipo, cat)}
    assert {f["id"] for f in categorizacion.sin_categorizar(conn)} == esperados
    assert categorizacion.contar_sin_categorizar(conn) == len(esperados) == 3


def test_regla_posible():
    assert categorizacion.regla_posible("compra", "  Tienda  INVENTADA ") == ("comercio", "tienda inventada")
    assert categorizacion.regla_posible("transferencia", "*5678") == ("cuenta_destino", "*5678")
    assert categorizacion.regla_posible("compra", " \t ") is None
    assert categorizacion.regla_posible("ingreso", " Persona  INVENTADA") == ("quien_envia", "persona inventada")
    assert categorizacion.regla_posible("ajuste", "Ajuste") is None
