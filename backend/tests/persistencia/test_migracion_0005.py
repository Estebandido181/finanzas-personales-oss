"""Migración 0005 (ítem 15): categorías propias de gasto y de ingreso.

Datos inventados. La base "de producción" es la de la v1 (``crear_base_v1``)
subida hasta la 0004, como estará en el servidor antes de desplegar el ítem 15.
"""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.util import CommandError

from finanzas import db, migrar
from finanzas.migraciones import esquema_v1
from tests.soporte.migraciones import crear_base_v1, revision
from tests.soporte.migracion_0005 import _asignaciones, _categorias, _estructura, _sql, _subir_hasta  # ayudas compartidas

INICIALES = {
    1: ("Mercado", "gasto", "cat-mercado", "shopping-basket"),
    2: ("Restaurantes", "gasto", "cat-restaurantes", "utensils"),
    3: ("Transporte", "gasto", "cat-transporte", "bus"),
    4: ("Vivienda y servicios", "gasto", "cat-vivienda", "house"),
    5: ("Salud", "gasto", "cat-salud", "heart-pulse"),
    6: ("Entretenimiento", "gasto", "cat-entretenimiento", "ticket"),
    7: ("Compras", "gasto", "cat-compras", "shopping-bag"),
    8: ("Otros", "gasto", "cat-otros", "shapes"),
    9: ("Antojos", "gasto", "cat-antojos", "ice-cream-cone"),
    10: ("Sueldo", "ingreso", "cat-sueldo", "briefcase"),
    11: ("Préstamos", "ingreso", "cat-prestamos", "handshake"),
    12: ("Otros ingresos", "ingreso", "cat-otros-ingresos", "coins"),
}
# Las que añade después la 0006 (ítem 27, tests/persistencia/test_migracion_0006.py).
CON_LA_0006 = {
    **INICIALES,
    13: ("Retiro a efectivo", "gasto", "cat-vivienda", "coins"),
    14: ("Pago de tarjeta", "gasto", "cat-prestamos", "coins"),
}












@pytest.fixture
def base_0004(tmp_path):
    """Base de la v1 con datos, subida hasta la 0004, con un movimiento categorizado por regla."""
    ruta = tmp_path / "produccion-inventada.db"
    crear_base_v1(ruta)
    _subir_hasta(ruta, "0004")
    _sql(ruta, "UPDATE movimientos SET origen_categoria = 'regla', regla_id = 1 WHERE id = 1")
    # Un gasto categorizado a mano en cada una de las 8 categorías de la v1.
    for categoria_id in range(1, 9):
        _sql(
            ruta,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, "
            "origen, origen_categoria) VALUES (?, ?, 'compra', ?, ?, 'manual', 'manual')",
            (f"2026-08-1{categoria_id % 10}T10:00:00", 100 * categoria_id, f"COMPRA INVENTADA {categoria_id}",
             categoria_id),
        )
    assert revision(ruta) == "0004"
    return ruta


@pytest.fixture
def respaldos(tmp_path):
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    return carpeta


# --- Subir ------------------------------------------------------------------------------------

def test_0005_sigue_a_0004():
    assert migrar._scripts().get_revision("0005").down_revision == "0004"


def test_las_categorias_de_la_v1_pasan_sin_perder_ninguna_asignacion(base_0004):
    antes = _asignaciones(base_0004)
    _subir_hasta(base_0004, "0005")
    assert revision(base_0004) == "0005"
    # Cada movimiento y cada regla conserva su categoría (mismos ids) y cómo se categorizó.
    assert _asignaciones(base_0004) == antes
    assert sum(1 for *_, cat, _o, _r in antes["movimientos"] if cat is not None) == 9
    # Las 8 de la v1 con sus ids, de gasto, con color e ícono; más las 4 nuevas.
    assert _categorias(base_0004) == INICIALES


def test_la_base_v1_sin_version_tambien_pasa_entera(tmp_path):
    ruta = tmp_path / "v1.db"
    crear_base_v1(ruta)
    antes = _sql(ruta, "SELECT id, categoria_id FROM movimientos ORDER BY id")
    assert migrar.aplicar(str(ruta)).pendientes == ["0002", "0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010", "0011", "0012"]
    assert _sql(ruta, "SELECT id, categoria_id FROM movimientos ORDER BY id") == antes
    assert _categorias(ruta) == CON_LA_0006


def test_la_base_nueva_trae_las_14_categorias_iniciales(tmp_path):
    ruta = tmp_path / "nueva.db"
    migrar.aplicar(str(ruta))
    assert _categorias(ruta) == CON_LA_0006
    assert sorted(CON_LA_0006.values()) == sorted(db.CATEGORIAS_INICIALES)


def test_las_claves_de_color_e_icono_son_las_del_sistema_de_diseno():
    from pathlib import Path

    from finanzas import categorizacion

    raiz = Path(__file__).resolve().parents[3] / "frontend" / "diseno"
    tokens = (raiz / "tokens.css").read_text(encoding="utf-8")
    iconos = (raiz / "iconos" / "iconos.svg").read_text(encoding="utf-8")
    for color in categorizacion.COLORES_CATEGORIA:
        assert f"--{color}:" in tokens, color
    for icono in categorizacion.ICONOS_CATEGORIA:
        assert f'id="i-{icono}"' in iconos, icono
    assert {c for _, _, c, _ in db.CATEGORIAS_INICIALES} == set(categorizacion.COLORES_CATEGORIA)
    assert {i for _, _, _, i in db.CATEGORIAS_INICIALES} == set(categorizacion.ICONOS_CATEGORIA)


@pytest.mark.parametrize(
    "sentencia",
    [
        "INSERT INTO categorias (nombre, clase, color, icono) VALUES ('Mercado', 'gasto', 'cat-otros', 'bus')",
        "INSERT INTO categorias (nombre, clase, color, icono) VALUES ('Nueva', 'otra', 'cat-otros', 'bus')",
        "INSERT INTO categorias (nombre, clase, color, icono) VALUES ('', 'gasto', 'cat-otros', 'bus')",
        "INSERT INTO categorias (nombre, clase, color, icono) VALUES ('Nueva', 'gasto', '', 'bus')",
        "INSERT INTO categorias (nombre, clase, color) VALUES ('Nueva', 'gasto', 'cat-otros')",
        "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('tarjeta', 'x', 10)",
        "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('quien_envia', 'x', 99)",
        "DELETE FROM categorias WHERE id = 1",  # tiene movimientos y una regla
    ],
)
def test_las_restricciones_nuevas(base_0004, sentencia):
    migrar.aplicar(str(base_0004))
    with pytest.raises(sqlite3.IntegrityError):
        _sql(base_0004, sentencia)


def test_mismo_nombre_en_otra_clase_y_reglas_de_ingreso_si_se_admiten(base_0004):
    migrar.aplicar(str(base_0004))
    _sql(base_0004, "INSERT INTO categorias (nombre, clase, color, icono) VALUES ('Mercado', 'ingreso', 'cat-otros', 'bus')")
    _sql(base_0004, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('quien_envia', 'persona inventada', 10)")


def test_no_sube_si_un_movimiento_tiene_una_categoria_de_otra_clase(base_0004):
    # Solo puede pasar tras bajar a la 0004 y usar la versión anterior de la app.
    _sql(base_0004, "INSERT INTO categorias (id, nombre) VALUES (10, 'Sueldo')")
    _sql(base_0004, "UPDATE movimientos SET categoria_id = 10 WHERE id = 1")  # una compra con Sueldo
    antes = _asignaciones(base_0004)
    with pytest.raises(CommandError, match="otra clase"):
        migrar.aplicar(str(base_0004))
    assert revision(base_0004) == "0004"  # nada a medias
    assert _asignaciones(base_0004) == antes


def test_el_comando_hace_respaldo_y_explica_si_no_puede_subir(base_0004, respaldos, capsys):
    _sql(base_0004, "INSERT INTO categorias (id, nombre) VALUES (10, 'Sueldo')")
    _sql(base_0004, "UPDATE movimientos SET categoria_id = 10 WHERE id = 1")
    assert migrar.main(["--base", str(base_0004), "--respaldos", str(respaldos)]) == 1
    error = capsys.readouterr().err
    assert "otra clase" in error and "No se cambió nada" in error
    assert "COMERCIO" not in error.upper()  # sin datos
    assert revision(base_0004) == "0004"


# --- Bajar y volver a subir ---------------------------------------------------------------------

def test_ida_y_vuelta_conserva_todos_los_datos(base_0004, tmp_path):
    referencia = tmp_path / "nueva-0004.db"
    _subir_hasta(referencia, "0004")
    estructura_0004 = _estructura(referencia)

    _subir_hasta(base_0004, "0008")
    # Uso de la v2 que la 0004 sí puede guardar: un ingreso con categoría de ingreso.
    _sql(base_0004, "UPDATE movimientos SET categoria_id = 10, origen_categoria = 'manual' WHERE id = 3")
    datos = _asignaciones(base_0004)
    categorias = _categorias(base_0004)

    assert migrar.bajar_a(str(base_0004), "0004") == ["0008", "0007", "0006", "0005"]
    assert revision(base_0004) == "0004"
    assert _estructura(base_0004) == estructura_0004  # la estructura exacta de la 0004
    assert _asignaciones(base_0004) == datos  # ningún movimiento ni regla huérfano
    assert _sql(base_0004, "SELECT id, nombre FROM categorias ORDER BY id") == [
        (i, n) for i, (n, *_) in INICIALES.items()
    ]

    _subir_hasta(base_0004, "0008")
    assert revision(base_0004) == "0008"
    assert _asignaciones(base_0004) == datos
    assert _categorias(base_0004) == categorias  # ni duplicadas ni con otra clase


@pytest.mark.parametrize(
    ("cambio", "motivo"),
    [
        ("INSERT INTO reglas (campo, texto, categoria_id) VALUES ('quien_envia', 'persona inventada', 10)",
         "reglas de ingreso"),
        ("INSERT INTO categorias (nombre, clase, color, icono) VALUES ('Mascotas', 'gasto', 'cat-otros', 'bus')",
         "categorías creadas o cambiadas"),
        ("UPDATE categorias SET nombre = 'Supermercado' WHERE id = 1", "categorías creadas o cambiadas"),
        ("UPDATE categorias SET color = 'cat-salud' WHERE id = 1", "categorías creadas o cambiadas"),
    ],
)
def test_no_baja_si_perderia_datos(base_0004, cambio, motivo):
    _subir_hasta(base_0004, "0005")
    _sql(base_0004, cambio)
    antes = (_asignaciones(base_0004), _categorias(base_0004), _estructura(base_0004))
    with pytest.raises(CommandError, match=motivo):
        migrar.bajar_a(str(base_0004), "0004")
    assert revision(base_0004) == "0005"
    assert (_asignaciones(base_0004), _categorias(base_0004), _estructura(base_0004)) == antes


def test_el_comando_explica_por_que_no_baja(base_0004, respaldos, capsys):
    _subir_hasta(base_0004, "0005")
    _sql(base_0004, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('quien_envia', 'persona inventada', 10)")
    assert migrar.main(["--base", str(base_0004), "--respaldos", str(respaldos), "--bajar-a", "0004"]) == 1
    error = capsys.readouterr().err
    assert "reglas de ingreso" in error and "respaldo previo" in error
    assert "PERSONA" not in error.upper()
    assert revision(base_0004) == "0005"


def test_el_comando_hace_respaldo_antes_de_la_0005(base_0004, respaldos, capsys):
    assert migrar.main(["--base", str(base_0004), "--respaldos", str(respaldos)]) == 0
    assert "Migraciones aplicadas: 0005, 0006, 0007, 0008, 0009, 0010, 0011, 0012." in capsys.readouterr().out
    [previo] = respaldos.glob("finanzas-antes-de-migrar-0004-*.db")
    assert revision(previo) == "0004"
