"""Migración 0008 (ítem 29): conciliación con el banco.

Datos inventados. La base "de producción" es la de la v1 (``crear_base_v1``)
subida hasta la 0007, con movimientos del correo, un ingreso manual, un
ajuste y una regla con movimientos categorizados: como estará en el servidor
antes de desplegar el ítem 29.
"""

from __future__ import annotations

import sqlite3

import pytest
from alembic.util import CommandError

from finanzas import db, migrar
from tests.soporte.migracion_0005 import _estructura, _sql, _subir_hasta
from tests.soporte.migraciones import crear_base_v1, revision
from tests.soporte.migracion_0008 import _saldo  # ayudas compartidas

COLUMNAS_0007 = (
    "id, fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id, "
    "registrado_en, origen_categoria, regla_id"
)


@pytest.fixture
def base_0007(tmp_path):
    ruta = tmp_path / "produccion-inventada.db"
    crear_base_v1(ruta)
    _subir_hasta(ruta, "0007")
    _sql(ruta, "UPDATE movimientos SET origen_categoria = 'regla', regla_id = 1 WHERE id = 1")
    _sql(ruta, "INSERT INTO reglas (campo, monto_centavos, categoria_id) VALUES ('cuenta_destino', 620000, 3)")
    assert revision(ruta) == "0007"
    return ruta


@pytest.fixture
def respaldos(tmp_path):
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    return carpeta


def _movimientos(ruta):
    return _sql(ruta, f"SELECT {COLUMNAS_0007} FROM movimientos ORDER BY id")




# --- Subir ------------------------------------------------------------------------------------

def test_0008_sigue_a_0007():
    assert migrar._scripts().get_revision("0008").down_revision == "0007"


def test_subir_conserva_todo_y_el_saldo_no_cambia(base_0007):
    movimientos, saldo_antes = _movimientos(base_0007), _saldo(base_0007)
    _subir_hasta(base_0007, "0008")
    assert revision(base_0007) == "0008"
    assert _movimientos(base_0007) == movimientos
    assert _saldo(base_0007) == saldo_antes
    # Los ingresos manuales pasan a provisional (D39); lo demás queda sin estado (D45).
    estados = _sql(base_0007, "SELECT origen, tipo, estado, referencia, fecha_banco, no_en_banco FROM movimientos "
                              "ORDER BY id")
    assert estados == [
        ("gmail", "compra", None, None, None, 0),
        ("gmail", "transferencia", None, None, None, 0),
        ("gmail", "ingreso", None, None, None, 0),
        ("manual", "ingreso", "provisional", None, None, 0),
        ("manual", "ajuste", None, None, None, 0),
        ("gmail", "compra", None, None, None, 0),
    ]
    for tabla in ("importaciones", "cambios_importacion", "preguntas_conciliacion", "candidatos_pregunta"):
        assert _sql(base_0007, f"SELECT COUNT(*) FROM {tabla}") == [(0,)]
    assert _sql(base_0007, "SELECT name FROM sqlite_master WHERE name LIKE '%copia%'") == []
    assert _sql(base_0007, "PRAGMA foreign_key_check") == []


EXTRACTO = ("INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, estado, referencia, fecha_banco"
            "{extra_col}) VALUES ('2026-08-04T00:00:00', 620000, 'transferencia', 'extracto', {estado}, {ref}, "
            "{fecha}{extra_val})")


def _extracto(estado="'sin_aviso'", ref="'*0001'", fecha="'2026-08-04'", extra_col="", extra_val=""):
    return EXTRACTO.format(estado=estado, ref=ref, fecha=fecha, extra_col=extra_col, extra_val=extra_val)


def test_lo_que_si_admite(base_0007):
    _subir_hasta(base_0007, "0008")
    _sql(base_0007, _extracto())
    _sql(base_0007, _extracto(estado="'confirmado'", ref="NULL", extra_col=", gmail_id", extra_val=", 'id-tarde'"))
    _sql(base_0007, "UPDATE movimientos SET estado = 'confirmado', fecha_banco = '2026-08-03', "
                    "referencia = '*9999' WHERE id = 2")
    _sql(base_0007, "UPDATE movimientos SET no_en_banco = 1 WHERE id = 1")
    _sql(base_0007, "UPDATE movimientos SET monto_centavos = 0 WHERE tipo = 'ajuste'")  # D45


@pytest.mark.parametrize(
    "sentencia",
    [
        # D37: nunca un número completo ni otra forma que "*" + 4 dígitos.
        _extracto(ref="'3000000001'"),
        _extracto(ref="'*3000000001'"),
        _extracto(ref="'*123'"),
        _extracto(ref="'1234'"),
        _extracto(ref="'*12a4'"),
        # Estados amarrados a su origen.
        _extracto(estado="NULL", fecha="NULL"),
        _extracto(estado="'provisional'"),
        _extracto(fecha="NULL"),
        _extracto(fecha="'04/08/2026'"),
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id, estado, fecha_banco) "
        "VALUES ('x', 1, 'compra', 'gmail', 'id-x', 'sin_aviso', '2026-08-04')",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id, estado) "
        "VALUES ('x', 1, 'compra', 'gmail', 'id-x', 'confirmado')",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, estado) "
        "VALUES ('x', 1, 'ajuste', 'manual', 'provisional')",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, estado) "
        "VALUES ('x', 1, 'ingreso', 'otro', NULL)",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, gmail_id) "
        "VALUES ('x', 1, 'ingreso', 'manual', 'id-x')",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen) VALUES ('x', 0, 'compra', 'manual')",
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen) VALUES ('x', -5, 'ingreso', 'manual')",
        # "No está en el banco" solo para lo del correo sin conciliar.
        "UPDATE movimientos SET no_en_banco = 1 WHERE origen = 'manual'",
        "UPDATE movimientos SET no_en_banco = 2 WHERE id = 1",
        # Referencia solo con el respaldo del banco.
        "UPDATE movimientos SET referencia = '*0001' WHERE id = 1",
        # Tablas nuevas.
        "INSERT INTO preguntas_conciliacion (tipo, fuente, fecha, monto_centavos) VALUES ('otra', 'banco', 'x', 1)",
        "INSERT INTO preguntas_conciliacion (tipo, fuente, fecha, monto_centavos) VALUES ('es_el_mismo', 'banco', 'x', 0)",
        "INSERT INTO preguntas_conciliacion (tipo, fuente, fecha, monto_centavos, referencia) "
        "VALUES ('es_el_mismo', 'banco', 'x', 1, '3000000001')",
        "INSERT INTO preguntas_conciliacion (tipo, fuente, fecha, monto_centavos) VALUES ('es_el_mismo', 'correo', 'x', 1)",
        "INSERT INTO preguntas_conciliacion (tipo, fuente, fecha, monto_centavos, respuesta) "
        "VALUES ('es_el_mismo', 'banco', 'x', 1, 'si')",
        "INSERT INTO importaciones (filas) VALUES (-1)",
        "INSERT INTO importaciones (filas) VALUES (1.5)",
        "INSERT INTO cambios_importacion (importacion_id, movimiento_id, accion) VALUES (99, 1, 'agregado')",
        "INSERT INTO candidatos_pregunta (pregunta_id, movimiento_id) VALUES (99, 1)",
    ],
)
def test_las_restricciones_nuevas(base_0007, sentencia):
    _subir_hasta(base_0007, "0008")
    with pytest.raises(sqlite3.IntegrityError):
        _sql(base_0007, sentencia)


# --- Bajar ------------------------------------------------------------------------------------------

def test_ida_y_vuelta_sin_conciliacion_conserva_todo(base_0007, tmp_path):
    estructura_0007, movimientos = _estructura(base_0007), _movimientos(base_0007)
    _subir_hasta(base_0007, "0008")
    estructura_0008 = _estructura(base_0007)
    assert migrar.bajar_a(str(base_0007), "0007") == ["0008"]
    assert revision(base_0007) == "0007"
    assert _estructura(base_0007) == estructura_0007  # la estructura exacta de la 0007
    assert _movimientos(base_0007) == movimientos
    _subir_hasta(base_0007, "0008")
    assert _estructura(base_0007) == estructura_0008 and _movimientos(base_0007) == movimientos


@pytest.mark.parametrize(
    "dato",
    [
        _extracto(),
        "UPDATE movimientos SET estado = 'confirmado', fecha_banco = '2026-08-03' WHERE id = 1",
        "UPDATE movimientos SET no_en_banco = 1 WHERE id = 1",
        "UPDATE movimientos SET monto_centavos = 0 WHERE tipo = 'ajuste'",
        "INSERT INTO importaciones (filas) VALUES (0)",
        "INSERT INTO preguntas_conciliacion (tipo, fuente, fecha, monto_centavos) "
        "VALUES ('es_el_mismo', 'banco', '2026-08-04', -620000)",
    ],
)
def test_no_baja_si_perderia_datos_de_la_conciliacion(base_0007, dato):
    _subir_hasta(base_0007, "0008")
    _sql(base_0007, dato)
    antes = (_sql(base_0007, "SELECT * FROM movimientos ORDER BY id"), _estructura(base_0007))
    with pytest.raises(CommandError, match="importados del banco"):
        migrar.bajar_a(str(base_0007), "0007")
    assert revision(base_0007) == "0008"
    assert (_sql(base_0007, "SELECT * FROM movimientos ORDER BY id"), _estructura(base_0007)) == antes


def test_el_comando_hace_respaldo_y_no_imprime_datos(base_0007, respaldos, capsys):
    assert migrar.main(["--base", str(base_0007), "--respaldos", str(respaldos)]) == 0
    assert "Migraciones aplicadas: 0008, 0009, 0010, 0011, 0012." in capsys.readouterr().out
    [previo] = respaldos.glob("finanzas-antes-de-migrar-0007-*.db")
    assert revision(previo) == "0007"
    _sql(base_0007, _extracto())
    assert migrar.main(["--base", str(base_0007), "--respaldos", str(respaldos), "--bajar-a", "0007"]) == 1
    error = capsys.readouterr().err
    assert "respaldo previo" in error and "620000" not in error and "*0001" not in error


# --- Claves foráneas al migrar ----------------------------------------------------------------------

def test_una_migracion_que_deja_claves_rotas_no_se_aplica(base_0007):
    """Las claves se apagan para reconstruir tablas, pero ``env.py`` rechaza las rotas nuevas.

    Un disparador inventado rompe una clave justo cuando Alembic anota la
    revisión nueva, dentro de la misma transacción.
    """
    _sql(base_0007, "CREATE TRIGGER rompe_clave AFTER UPDATE ON alembic_version BEGIN "
                    "UPDATE movimientos SET categoria_id = 999 WHERE id = 1; END")
    movimientos = _movimientos(base_0007)
    with pytest.raises(RuntimeError, match="claves foráneas rotas"):
        _subir_hasta(base_0007, "0008")
    assert revision(base_0007) == "0007" and _movimientos(base_0007) == movimientos


def test_las_claves_rotas_de_antes_no_impiden_migrar(base_0007):
    _sql(base_0007, "PRAGMA foreign_keys = OFF")
    conn = sqlite3.connect(base_0007)
    with conn:
        conn.execute("UPDATE movimientos SET categoria_id = 999 WHERE id = 2")
    conn.close()
    movimientos = _movimientos(base_0007)
    _subir_hasta(base_0007, "0008")
    assert revision(base_0007) == "0008" and _movimientos(base_0007) == movimientos
