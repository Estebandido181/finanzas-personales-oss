"""Migración 0006 (ítem 27): categorías "Retiro a efectivo" y "Pago de tarjeta".

Datos inventados. La base "de producción" es la de la v1 subida hasta la 0005.
"""

from __future__ import annotations

import pytest
from alembic.util import CommandError

from finanzas import categorizacion, migrar
from tests.soporte.migracion_0005 import CON_LA_0006, INICIALES, _asignaciones, _categorias, _estructura, _sql, _subir_hasta
from tests.soporte.migraciones import crear_base_v1, revision

NUEVAS = {13: CON_LA_0006[13], 14: CON_LA_0006[14]}


@pytest.fixture
def base_0005(tmp_path):
    ruta = tmp_path / "produccion-inventada.db"
    crear_base_v1(ruta)
    _subir_hasta(ruta, "0005")
    assert revision(ruta) == "0005"
    return ruta


@pytest.fixture
def respaldos(tmp_path):
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    return carpeta


def test_0006_sigue_a_0005():
    # La última es la 0008 (ítem 29, tests/persistencia/test_migracion_0008.py).
    assert migrar._scripts().get_revision("0006").down_revision == "0005"


def test_crea_las_dos_categorias_de_gasto_sin_tocar_nada_mas(base_0005):
    antes = (_asignaciones(base_0005), _estructura(base_0005))
    _subir_hasta(base_0005, "0006")  # la 0007 (ítem 17) sí cambia la tabla reglas
    assert revision(base_0005) == "0006"
    assert _categorias(base_0005) == CON_LA_0006
    assert (_asignaciones(base_0005), _estructura(base_0005)) == antes


def test_color_e_icono_validos_y_sin_repetir_un_par():
    pares = [(c, i) for _, _, c, i in CON_LA_0006.values()]
    assert len(set(pares)) == len(pares)
    for _, clase, color, icono in NUEVAS.values():
        assert clase == "gasto"
        assert color in categorizacion.COLORES_CATEGORIA and icono in categorizacion.ICONOS_CATEGORIA


def test_si_ya_existen_no_las_duplica_ni_las_cambia(base_0005):
    _sql(base_0005, "INSERT INTO categorias (nombre, clase, color, icono) "
                    "VALUES ('Pago de tarjeta', 'gasto', 'cat-otros', 'bus')")
    migrar.aplicar(str(base_0005))
    filas = _sql(base_0005, "SELECT nombre, color, icono FROM categorias WHERE nombre IN "
                            "('Pago de tarjeta', 'Retiro a efectivo') ORDER BY nombre")
    assert filas == [("Pago de tarjeta", "cat-otros", "bus"), ("Retiro a efectivo", "cat-vivienda", "coins")]


def test_con_el_mismo_nombre_de_ingreso_igual_crea_la_de_gasto(base_0005):
    _sql(base_0005, "INSERT INTO categorias (nombre, clase, color, icono) "
                    "VALUES ('Retiro a efectivo', 'ingreso', 'cat-sueldo', 'shapes')")
    migrar.aplicar(str(base_0005))
    assert _sql(base_0005, "SELECT clase FROM categorias WHERE nombre = 'Retiro a efectivo' ORDER BY clase") == [
        ("gasto",), ("ingreso",)
    ]


def test_ida_y_vuelta_sin_uso(base_0005):
    estructura = _estructura(base_0005)
    _subir_hasta(base_0005, "0008")
    assert migrar.bajar_a(str(base_0005), "0005") == ["0008", "0007", "0006"]
    assert revision(base_0005) == "0005"
    assert _categorias(base_0005) == INICIALES
    assert _estructura(base_0005) == estructura
    _subir_hasta(base_0005, "0008")
    assert _categorias(base_0005) == CON_LA_0006


def test_bajar_si_el_duenio_ya_borro_una(base_0005):
    _subir_hasta(base_0005, "0008")
    _sql(base_0005, "DELETE FROM categorias WHERE nombre = 'Pago de tarjeta'")
    assert migrar.bajar_a(str(base_0005), "0005") == ["0008", "0007", "0006"]
    assert _categorias(base_0005) == INICIALES


@pytest.mark.parametrize(
    ("cambio", "motivo"),
    [
        ("INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id) "
         "VALUES ('2026-09-05T10:15:00', 5000000, 'compra', 'CAJERO EJEMPLO', 13, 'gmail', 'id-inventado-27')",
         "hay movimientos o reglas"),
        ("INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'empresa ejemplo sas', 14)",
         "hay movimientos o reglas"),
    ],
)
def test_no_baja_si_estan_en_uso_y_no_toca_nada(base_0005, cambio, motivo):
    _subir_hasta(base_0005, "0008")
    _sql(base_0005, cambio)
    antes = (_asignaciones(base_0005), _categorias(base_0005), _estructura(base_0005))
    with pytest.raises(CommandError, match=motivo):
        migrar.bajar_a(str(base_0005), "0005")
    assert revision(base_0005) == "0008"
    assert (_asignaciones(base_0005), _categorias(base_0005), _estructura(base_0005)) == antes


def test_el_comando_hace_respaldo_y_explica_por_que_no_baja(base_0005, respaldos, capsys):
    assert migrar.main(["--base", str(base_0005), "--respaldos", str(respaldos)]) == 0
    assert "Migraciones aplicadas: 0006, 0007, 0008, 0009, 0010, 0011, 0012." in capsys.readouterr().out
    assert list(respaldos.glob("finanzas-antes-de-migrar-0005-*.db"))
    _sql(base_0005, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'cajero ejemplo', 13)")
    assert migrar.main(["--base", str(base_0005), "--respaldos", str(respaldos), "--bajar-a", "0005"]) == 1
    error = capsys.readouterr().err
    assert "0009" in error and "respaldo previo" in error
    assert "CAJERO" not in error.upper()
    assert revision(base_0005) == migrar.revision_final()


def test_baja_aunque_el_duenio_las_haya_recoloreado_si_no_se_usan(base_0005):
    _subir_hasta(base_0005, "0008")
    _sql(base_0005, "UPDATE categorias SET color = 'cat-salud', icono = 'bus' WHERE id = 14")
    assert migrar.bajar_a(str(base_0005), "0005") == ["0008", "0007", "0006"]
    assert _categorias(base_0005) == INICIALES


@pytest.mark.parametrize(
    "existente",
    ["retiro a efectivo", "RETIRO A EFECTIVO", "  Retiro   a efectivo ", "Retiro a\u200b efectivo",
     "Retiro\ta efectivo"],
)
def test_nombre_equivalente_como_en_la_app_no_se_duplica(base_0005, existente):
    _sql(base_0005, "INSERT INTO categorias (nombre, clase, color, icono) VALUES (?, 'gasto', 'cat-otros', 'bus')",
         (existente,))
    migrar.aplicar(str(base_0005))
    gasto = [n for (n,) in _sql(base_0005, "SELECT nombre FROM categorias WHERE clase = 'gasto'")]
    assert sum(1 for n in gasto if categorizacion.normalizar(n) == "retiro a efectivo") == 1
    assert "Pago de tarjeta" in gasto


def test_la_sincronizacion_encuentra_la_equivalente(base_0005):
    from finanzas import db, sincronizacion
    from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import extraer

    _sql(base_0005, "INSERT INTO categorias (nombre, clase, color, icono) "
                    "VALUES ('RETIRO A EFECTIVO', 'gasto', 'cat-otros', 'bus')")
    migrar.aplicar(str(base_0005))
    conn = db.conectar(str(base_0005))
    try:
        movimiento = extraer("Bancolombia: Retiraste $50.000,00 en CAJERO EJEMPLO de tu T.Deb **1234 "
                             "el 05/09/2026 a las 10:15.")
        columnas = sincronizacion._columnas_de_categoria(conn, movimiento)
        conn.rollback()
    finally:
        conn.close()
    [(esperado,)] = _sql(base_0005, "SELECT id FROM categorias WHERE nombre = 'RETIRO A EFECTIVO'")
    assert columnas == {"categoria_id": esperado, "origen_categoria": None, "regla_id": None}


def test_no_repite_un_par_color_icono_en_uso(base_0005):
    # El dueño ya usa los dos pares preferidos (y el primer respaldo).
    for nombre, color in [("Uno inventado", "cat-vivienda"), ("Dos inventado", "cat-prestamos"),
                          ("Tres inventado", "cat-mercado")]:
        _sql(base_0005, "INSERT INTO categorias (nombre, clase, color, icono) VALUES (?, 'gasto', ?, 'coins')",
             (nombre, color))
    migrar.aplicar(str(base_0005))
    pares = _sql(base_0005, "SELECT color, icono FROM categorias")
    assert len(set(pares)) == len(pares)  # ningún par repetido
    nuevas = dict((n, (c, i)) for n, c, i in _sql(
        base_0005, "SELECT nombre, color, icono FROM categorias WHERE nombre IN ('Retiro a efectivo', 'Pago de tarjeta')"
    ))
    assert nuevas == {"Retiro a efectivo": ("cat-restaurantes", "coins"),
                      "Pago de tarjeta": ("cat-transporte", "coins")}
    for color, icono in nuevas.values():
        assert color in categorizacion.COLORES_CATEGORIA and icono in categorizacion.ICONOS_CATEGORIA


def test_los_candidatos_son_la_paleta_y_los_iconos_de_la_app():
    import importlib

    modulo = importlib.import_module("finanzas.migraciones.versions.0006_categorias_retiro_y_pago_tarjeta")
    assert modulo._COLORES == categorizacion.COLORES_CATEGORIA
    assert modulo._ICONOS == categorizacion.ICONOS_CATEGORIA
    for texto in ["Retiro A  EFECTIVO", "x\u200by", "É"]:
        assert modulo._clave_nombre(texto) == categorizacion.normalizar(texto)


def test_migrar_dos_veces_no_cambia_nada(base_0005):
    migrar.aplicar(str(base_0005))
    antes = _categorias(base_0005)
    assert migrar.aplicar(str(base_0005)).pendientes == []
    assert _categorias(base_0005) == antes
