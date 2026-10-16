"""Migración 0007 (ítem 17; era la 0006 antes de integrar el ítem 27): reglas con texto opcional y monto exacto opcional.

Datos inventados. La base "de producción" es la de la v1 (``crear_base_v1``)
subida hasta la 0006 (la del ítem 27, con las categorías de retiro y de pago de tarjeta), con reglas de compra, de transferencia y de ingreso y
movimientos que esas reglas categorizaron: como estará en el servidor antes
de desplegar el ítem 17.
"""

from __future__ import annotations

import sqlite3

import pytest
from alembic.util import CommandError

from finanzas import categorizacion, db, migrar
from tests.soporte.migracion_0005 import _estructura, _sql, _subir_hasta
from tests.soporte.migraciones import crear_base_v1, revision

INDICE = (
    "CREATE UNIQUE INDEX ux_reglas_condiciones ON reglas "
    "(campo, COALESCE(texto, ''), COALESCE(monto_centavos, 0))"
)


@pytest.fixture
def base_0006(tmp_path):
    """Base de la v1 subida hasta la 0006 (la del ítem 27, con las categorías de retiro y de pago de tarjeta), con reglas de los tres tipos y movimientos categorizados por ellas."""
    ruta = tmp_path / "produccion-inventada.db"
    crear_base_v1(ruta)  # trae la regla 1: comercio "comercio inventado zxq" -> Mercado
    _subir_hasta(ruta, "0006")
    _sql(ruta, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('cuenta_destino', '*5678', 4)")
    _sql(ruta, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('quien_envia', 'persona inventada', 10)")
    _sql(ruta, "UPDATE movimientos SET origen_categoria = 'regla', regla_id = 1 WHERE id = 1")
    _sql(
        ruta,
        "UPDATE movimientos SET categoria_id = 10, origen_categoria = 'regla', regla_id = 3 WHERE id = 3",
    )
    assert revision(ruta) == "0006"
    return ruta


def _reglas(ruta):
    return _sql(ruta, "SELECT id, campo, texto, categoria_id FROM reglas ORDER BY id")


def _movimientos(ruta):
    return _sql(ruta, "SELECT id, categoria_id, origen_categoria, regla_id FROM movimientos ORDER BY id")


@pytest.fixture
def respaldos(tmp_path):
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    return carpeta


# --- Subir ------------------------------------------------------------------------------------

def test_0007_sigue_a_0006():
    assert migrar._scripts().get_revision("0007").down_revision == "0006"


def test_las_reglas_existentes_se_conservan_intactas(base_0006):
    reglas, movimientos = _reglas(base_0006), _movimientos(base_0006)
    assert migrar.aplicar(str(base_0006)).pendientes == ["0007", "0008", "0009", "0010", "0011", "0012"]
    assert revision(base_0006) == migrar.revision_final()
    assert _reglas(base_0006) == reglas
    assert _sql(base_0006, "SELECT COUNT(*) FROM reglas WHERE monto_centavos IS NOT NULL") == [(0,)]
    # Los movimientos siguen apuntando a la regla que los categorizó.
    assert _movimientos(base_0006) == movimientos


def test_las_reglas_de_la_v1_siguen_funcionando_tras_migrar(base_0006):
    """Criterio de terminado: mismas coincidencias que antes, para cualquier monto."""
    migrar.aplicar(str(base_0006))
    conn = db.conectar(str(base_0006))
    try:
        for tipo, descripcion, regla_id in (
            ("compra", "Comercio  INVENTADO zxq", 1),
            ("transferencia", "*5678", 2),
            ("ingreso", "PERSONA INVENTADA", 3),
        ):
            for monto in (1, 320000, 6863000):
                regla = categorizacion.regla_que_coincide(conn, tipo, descripcion, monto)
                assert regla is not None and regla["id"] == regla_id
        assert categorizacion.regla_que_coincide(conn, "compra", "*5678", 320000) is None
    finally:
        conn.close()


def test_la_estructura_y_el_indice_unico(base_0006):
    _subir_hasta(base_0006, "0007")  # Prueba histórica de ese índice, anterior a los modos del0010.
    assert _sql(base_0006, "SELECT sql FROM sqlite_master WHERE name = 'ux_reglas_condiciones'") == [(INDICE,)]
    columnas = {fila[1]: fila for fila in _sql(base_0006, "PRAGMA table_info(reglas)")}
    assert columnas["texto"][3] == 0  # ya no es NOT NULL
    assert columnas["monto_centavos"][2] == "INTEGER" and columnas["monto_centavos"][3] == 0


@pytest.mark.parametrize(
    "sentencia",
    [
        # Al menos una condición además del tipo.
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('comercio', NULL, NULL, 1)",
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('comercio', '', NULL, 1)",
        # Monto: entero positivo en centavos (D8).
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('comercio', NULL, 0, 1)",
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('comercio', NULL, -320000, 1)",
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('comercio', NULL, 3200.5, 1)",
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('comercio', NULL, 'abc', 1)",
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('tarjeta', NULL, 320000, 1)",
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('comercio', NULL, 320000, 99)",
        # Duplicados (también con NULL): ya existe la regla 1 por texto.
        "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'comercio inventado zxq', 2)",
    ],
)
def test_las_restricciones_nuevas(base_0006, sentencia):
    migrar.aplicar(str(base_0006))
    with pytest.raises(sqlite3.IntegrityError):
        _sql(base_0006, sentencia)


def test_reglas_por_monto_duplicadas_se_rechazan(base_0006):
    migrar.aplicar(str(base_0006))
    _sql(base_0006, "INSERT INTO reglas (campo, monto_centavos, categoria_id) VALUES ('cuenta_destino', 320000, 3)")
    with pytest.raises(sqlite3.IntegrityError):
        _sql(base_0006, "INSERT INTO reglas (campo, monto_centavos, categoria_id) VALUES ('cuenta_destino', 320000, 8)")
    # Mismo monto en otro tipo, o con texto: son otras reglas.
    _sql(base_0006, "INSERT INTO reglas (campo, monto_centavos, categoria_id) VALUES ('comercio', 320000, 8)")
    _sql(
        base_0006,
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('cuenta_destino', '*5678', 320000, 3)",
    )


# --- Bajar y volver a subir ---------------------------------------------------------------------

def test_ida_y_vuelta_conserva_todos_los_datos(base_0006, tmp_path):
    referencia = tmp_path / "nueva-0006.db"
    _subir_hasta(referencia, "0006")
    estructura_0006 = _estructura(referencia)
    reglas, movimientos = _reglas(base_0006), _movimientos(base_0006)

    _subir_hasta(base_0006, "0008")
    estructura_0007 = _estructura(base_0006)
    assert migrar.bajar_a(str(base_0006), "0006") == ["0008", "0007"]
    assert revision(base_0006) == "0006"
    assert _estructura(base_0006) == estructura_0006  # la estructura exacta de la 0006
    assert _sql(base_0006, "SELECT name FROM sqlite_master WHERE name LIKE '%copia%'") == []
    assert (_reglas(base_0006), _movimientos(base_0006)) == (reglas, movimientos)

    _subir_hasta(base_0006, "0008")
    assert revision(base_0006) == "0008"
    assert _estructura(base_0006) == estructura_0007
    assert (_reglas(base_0006), _movimientos(base_0006)) == (reglas, movimientos)


@pytest.mark.parametrize(
    "regla",
    [
        "INSERT INTO reglas (campo, monto_centavos, categoria_id) VALUES ('cuenta_destino', 320000, 3)",
        "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES ('quien_envia', 'otra persona', 40000000, 11)",
    ],
)
def test_no_baja_si_perderia_reglas_nuevas(base_0006, regla):
    _subir_hasta(base_0006, "0008")
    _sql(base_0006, regla)
    antes = (_reglas(base_0006), _movimientos(base_0006), _estructura(base_0006))
    with pytest.raises(CommandError, match="reglas con monto o sin texto"):
        migrar.bajar_a(str(base_0006), "0006")
    assert revision(base_0006) == "0008"
    assert (_reglas(base_0006), _movimientos(base_0006), _estructura(base_0006)) == antes


def test_el_comando_hace_respaldo_y_explica_por_que_no_baja(base_0006, respaldos, capsys):
    assert migrar.main(["--base", str(base_0006), "--respaldos", str(respaldos)]) == 0
    assert "Migraciones aplicadas: 0007, 0008, 0009, 0010, 0011, 0012." in capsys.readouterr().out
    [previo] = respaldos.glob("finanzas-antes-de-migrar-0006-*.db")
    assert revision(previo) == "0006"

    _sql(base_0006, "INSERT INTO reglas (campo, monto_centavos, categoria_id) VALUES ('cuenta_destino', 320000, 3)")
    assert migrar.main(["--base", str(base_0006), "--respaldos", str(respaldos), "--bajar-a", "0006"]) == 1
    error = capsys.readouterr().err
    assert "respaldo previo" in error
    assert "320000" not in error and "3.200" not in error  # nunca montos en los mensajes
    assert revision(base_0006) == migrar.revision_final()


def test_bajar_encadenado_hasta_la_0005(base_0006, tmp_path):
    """0007 -> 0006 -> 0005: la 0007 devuelve ``reglas`` como la deja la 0006 y la 0006 quita sus
    categorías (sin usar). Las reglas y los movimientos siguen intactos."""
    referencia = tmp_path / "nueva-0005.db"
    _subir_hasta(referencia, "0005")
    reglas, movimientos = _reglas(base_0006), _movimientos(base_0006)
    _subir_hasta(base_0006, "0008")
    assert migrar.bajar_a(str(base_0006), "0005") == ["0008", "0007", "0006"]
    assert revision(base_0006) == "0005"
    assert _estructura(base_0006) == _estructura(referencia)
    assert (_reglas(base_0006), _movimientos(base_0006)) == (reglas, movimientos)
    nombres = {n for (n,) in _sql(base_0006, "SELECT nombre FROM categorias")}
    assert not nombres & {"Retiro a efectivo", "Pago de tarjeta"}
    _subir_hasta(base_0006, "0008")
    assert revision(base_0006) == "0008"
    assert (_reglas(base_0006), _movimientos(base_0006)) == (reglas, movimientos)
