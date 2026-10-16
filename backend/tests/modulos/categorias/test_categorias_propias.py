"""Ítem 15: categorías propias (crear, editar, borrar) y reglas de ingresos.

Todos los nombres, comercios y cuentas son inventados.
"""

from __future__ import annotations
from finanzas.bootstrap.reporte import componer_reporte

from datetime import datetime

import pytest

from finanzas import categorizacion, db
from finanzas.flujos import reporte
from finanzas.categorizacion import (
    CategoriaNoEncontrada,
    ErrorCategorizacion,
    asignar_categoria,
    borrar_categoria,
    crear_categoria,
    editar_categoria,
)
from finanzas.gmail import ZONA_COLOMBIA, CorreoGmail
from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import LEGITIMO, ClienteFalso


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "categorias.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
            "VALUES (1, 100000000, '2026-08-01')",
        )
    yield conexion
    conexion.close()


def _cat(conn, nombre, clase=None):
    texto = "SELECT id FROM categorias WHERE nombre = ?" + (" AND clase = ?" if clase else "")
    return sql(conn, texto, (nombre, clase) if clase else (nombre,)).fetchone()[0]


_n = iter(range(1, 10_000))


def _mov(conn, tipo="compra", descripcion="TIENDA INVENTADA", monto=100000, categoria_id=None,
         fecha="2026-08-15T10:00:00", origen_categoria=None):
    gmail = tipo != "ajuste"
    with db.transaccion(conn):
        return sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, "
            "gmail_id, origen_categoria) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (fecha, monto, tipo, descripcion, categoria_id, "gmail" if gmail else "manual",
             f"inv-{next(_n)}" if gmail else None, origen_categoria),
        ).lastrowid


def _categoria_de(conn, movimiento_id):
    return sql(conn, "SELECT categoria_id FROM movimientos WHERE id = ?", (movimiento_id,)).fetchone()[0]


def _todo(conn):
    return (
        [tuple(f) for f in sql(conn, "SELECT * FROM categorias ORDER BY id")],
        [tuple(f) for f in sql(conn, "SELECT * FROM movimientos ORDER BY id")],
        [tuple(f) for f in sql(conn, "SELECT * FROM reglas ORDER BY id")],
    )


# --- Crear ---------------------------------------------------------------------------------

def test_crear_categoria_de_gasto_y_de_ingreso(conn):
    gasto = crear_categoria(conn, "  Mascotas   y  más ", "gasto", "cat-salud", "bus")
    ingreso = crear_categoria(conn, "Arriendos cobrados", "ingreso", "cat-sueldo", "house")
    assert dict(categorizacion.buscar_categoria(conn, gasto)) == {
        "id": gasto, "nombre": "Mascotas y más", "clase": "gasto", "color": "cat-salud", "icono": "bus"
    }
    assert categorizacion.buscar_categoria(conn, ingreso)["clase"] == "ingreso"
    assert [c["nombre"] for c in categorizacion.categorias(conn, clase="ingreso")] == [
        "Sueldo", "Préstamos", "Otros ingresos", "Arriendos cobrados"
    ]


@pytest.mark.parametrize(
    ("nombre", "clase", "mensaje"),
    [
        ("mercado", "gasto", "Ya hay una categoría de gasto"),  # sin importar mayúsculas
        (" MERCADO ", "gasto", "Ya hay una categoría de gasto"),
        ("sueldo", "ingreso", "Ya hay una categoría de ingreso"),
        ("", "gasto", "Escribe el nombre"),
        ("   ", "gasto", "Escribe el nombre"),
        ("x" * 41, "gasto", "hasta 40"),
        ("Sin categorizar", "gasto", "lo usa la app"),
        ("sin  CATEGORIZAR", "ingreso", "lo usa la app"),
        ("—", "gasto", "lo usa la app"),
        ("Nueva​", "gasto", "no válidos"),
        ("Nueva\x00", "gasto", "no válidos"),
        ("Nueva", "otra", "gasto o ingreso"),
    ],
)
def test_crear_rechaza_nombres_no_validos_sin_cambiar_nada(conn, nombre, clase, mensaje):
    antes = _todo(conn)
    with pytest.raises(ErrorCategorizacion, match=mensaje):
        crear_categoria(conn, nombre, clase, "cat-salud", "bus")
    assert _todo(conn) == antes


def test_el_mismo_nombre_si_se_puede_en_la_otra_clase(conn):
    nuevo = crear_categoria(conn, "Mercado", "ingreso", "cat-mercado", "coins")
    assert categorizacion.buscar_categoria(conn, nuevo)["clase"] == "ingreso"


def test_se_repite_el_color_pero_nunca_el_par_color_e_icono(conn):
    crear_categoria(conn, "Mascotas", "gasto", "cat-mercado", "bus")  # color repetido: sí
    with pytest.raises(ErrorCategorizacion, match="ese color con ese ícono"):
        crear_categoria(conn, "Otra", "ingreso", "cat-mercado", "shopping-basket")  # el de Mercado
    with pytest.raises(ErrorCategorizacion, match="color de la paleta"):
        crear_categoria(conn, "Otra", "gasto", "#5A6B1C", "bus")
    with pytest.raises(ErrorCategorizacion, match="ícono de la lista"):
        crear_categoria(conn, "Otra", "gasto", "cat-otros", "cohete")
    with pytest.raises(ErrorCategorizacion, match="color de la paleta"):
        crear_categoria(conn, "Otra", "gasto", "cat-sin-categorizar", "bus")


# --- Editar --------------------------------------------------------------------------------

def test_renombrar_y_cambiar_color_e_icono_conserva_sus_movimientos(conn):
    mercado = _cat(conn, "Mercado")
    mov = _mov(conn, categoria_id=mercado)
    editar_categoria(conn, mercado, nombre="Supermercado")
    editar_categoria(conn, mercado, color="cat-compras", icono="coins")
    assert dict(categorizacion.buscar_categoria(conn, mercado)) == {
        "id": mercado, "nombre": "Supermercado", "clase": "gasto", "color": "cat-compras", "icono": "coins"
    }
    assert _categoria_de(conn, mov) == mercado


def test_renombrar_a_su_mismo_nombre_con_otras_mayusculas_si_se_puede(conn):
    mercado = _cat(conn, "Mercado")
    editar_categoria(conn, mercado, nombre="MERCADO")
    assert categorizacion.buscar_categoria(conn, mercado)["nombre"] == "MERCADO"


@pytest.mark.parametrize(
    ("cambios", "mensaje"),
    [
        ({"nombre": "Salud"}, "Ya hay una categoría de gasto"),
        ({"icono": "heart-pulse", "color": "cat-salud"}, "ese color con ese ícono"),
        ({"color": "rojo"}, "color de la paleta"),
        ({"nombre": ""}, "Escribe el nombre"),
        ({}, "nada que cambiar"),
    ],
)
def test_editar_rechaza_sin_cambiar_nada(conn, cambios, mensaje):
    antes = _todo(conn)
    with pytest.raises(ErrorCategorizacion, match=mensaje):
        editar_categoria(conn, _cat(conn, "Mercado"), **cambios)
    assert _todo(conn) == antes


def test_editar_una_que_no_existe(conn):
    with pytest.raises(CategoriaNoEncontrada):
        editar_categoria(conn, 999, nombre="Nueva")


# --- Borrar ----------------------------------------------------------------------------------

def test_borrar_pasa_movimientos_y_reglas_a_la_destino_en_una_transaccion(conn):
    antojos, restaurantes = _cat(conn, "Antojos"), _cat(conn, "Restaurantes")
    a_mano = _mov(conn, descripcion="HELADERIA INVENTADA")
    asignar_categoria(conn, a_mano, antojos, recordar=False)
    primero = _mov(conn, descripcion="PANADERIA INVENTADA")
    por_regla = _mov(conn, descripcion="PANADERIA INVENTADA")
    asignar_categoria(conn, primero, antojos, recordar=True)
    otro = _mov(conn, descripcion="OTRA", categoria_id=_cat(conn, "Salud"))
    regla_id = categorizacion.listar_reglas(conn)[0]["id"]

    resultado = borrar_categoria(conn, antojos, restaurantes)

    assert resultado == categorizacion.CategoriaBorrada(movimientos=3, reglas=1, destino_id=restaurantes)
    assert categorizacion.buscar_categoria(conn, antojos) is None
    for mov in (a_mano, primero, por_regla):
        assert _categoria_de(conn, mov) == restaurantes
    assert _categoria_de(conn, otro) == _cat(conn, "Salud")
    # La regla pasa con ellos y los movimientos siguen diciendo cómo se categorizaron.
    assert [(r["id"], r["categoria_id"]) for r in categorizacion.listar_reglas(conn)] == [(regla_id, restaurantes)]
    origenes = dict(sql(conn, "SELECT id, origen_categoria FROM movimientos").fetchall())
    assert (origenes[a_mano], origenes[primero], origenes[por_regla]) == ("manual", "manual", "regla")
    assert sql(conn, "SELECT regla_id FROM movimientos WHERE id = ?", (por_regla,)).fetchone()[0] == regla_id
    # Ningún huérfano.
    assert sql(conn, "PRAGMA foreign_key_check").fetchall() == []
    # Y la regla movida sigue funcionando: ya categoriza en Restaurantes.
    assert categorizacion.regla_que_coincide(conn, "compra", "panaderia inventada", 100)["categoria_id"] == restaurantes


def test_borrar_una_de_ingreso_pasa_sus_ingresos_a_otra_de_ingreso(conn):
    prestamos, otros_ingresos = _cat(conn, "Préstamos"), _cat(conn, "Otros ingresos")
    ingreso = _mov(conn, "ingreso", "PERSONA INVENTADA", monto=40000000)
    asignar_categoria(conn, ingreso, prestamos, recordar=True)
    assert borrar_categoria(conn, prestamos, otros_ingresos).movimientos == 1
    assert _categoria_de(conn, ingreso) == otros_ingresos
    assert categorizacion.regla_que_coincide(conn, "ingreso", "PERSONA INVENTADA", 100)["categoria_id"] == otros_ingresos


def test_borrar_una_vacia_no_necesita_destino(conn):
    nueva = crear_categoria(conn, "Mascotas", "gasto", "cat-otros", "bus")
    copia = categorizacion.CopiaCategoria(nueva, "Mascotas", "gasto", "cat-otros", "bus")
    assert borrar_categoria(conn, nueva, None) == categorizacion.CategoriaBorrada(0, 0, None, copia)
    assert categorizacion.buscar_categoria(conn, nueva) is None


@pytest.mark.parametrize(
    ("destino", "mensaje"),
    [
        (None, "Elige a qué categoría pasan"),
        ("Antojos", "Elige otra categoría"),
        (999, "no existe"),
        ("Sueldo", "solo pueden pasar a otra categoría de gasto"),
    ],
)
def test_borrar_con_destino_no_valido_no_cambia_nada(conn, destino, mensaje):
    antojos = _cat(conn, "Antojos")
    _mov(conn, categoria_id=antojos)
    destino_id = _cat(conn, destino) if isinstance(destino, str) else destino
    antes = _todo(conn)
    with pytest.raises(ErrorCategorizacion, match=mensaje) as error:
        borrar_categoria(conn, antojos, destino_id)
    assert not isinstance(error.value, CategoriaNoEncontrada)
    assert _todo(conn) == antes


def test_un_ingreso_nunca_pasa_a_una_categoria_de_gasto(conn):
    sueldo = _cat(conn, "Sueldo")
    ingreso = _mov(conn, "ingreso", "EMPRESA INVENTADA", categoria_id=sueldo)
    antes = _todo(conn)
    with pytest.raises(ErrorCategorizacion, match="solo pueden pasar a otra categoría de ingreso"):
        borrar_categoria(conn, sueldo, _cat(conn, "Otros"))
    assert _todo(conn) == antes
    assert _categoria_de(conn, ingreso) == sueldo


def test_no_se_borra_la_ultima_de_una_clase(conn):
    sueldo, prestamos, otros = _cat(conn, "Sueldo"), _cat(conn, "Préstamos"), _cat(conn, "Otros ingresos")
    borrar_categoria(conn, sueldo, None)
    borrar_categoria(conn, prestamos, None)
    antes = _todo(conn)
    with pytest.raises(ErrorCategorizacion, match="última categoría de ingreso"):
        borrar_categoria(conn, otros, None)
    assert _todo(conn) == antes
    # Las de gasto siguen pudiendo borrarse.
    borrar_categoria(conn, _cat(conn, "Antojos"), None)


def test_borrar_una_que_no_existe(conn):
    with pytest.raises(CategoriaNoEncontrada):
        borrar_categoria(conn, 999, 1)


def test_tras_borrar_el_reporte_suma_todo_en_la_destino(conn):
    antojos, restaurantes = _cat(conn, "Antojos"), _cat(conn, "Restaurantes")
    _mov(conn, monto=1200000, categoria_id=antojos)
    _mov(conn, monto=3890000, categoria_id=restaurantes)
    antes = componer_reporte(conn).reporte_mensual(2026, 8)
    borrar_categoria(conn, antojos, restaurantes)
    despues = componer_reporte(conn).reporte_mensual(2026, 8)
    assert despues.total_gasto_centavos == antes.total_gasto_centavos == 5090000
    assert [(g.nombre, g.centavos) for g in despues.por_categoria] == [("Restaurantes", 5090000)]


def test_categorias_con_uso_cuenta_movimientos_del_mes_de_siempre_y_reglas(conn):
    mercado, sueldo = _cat(conn, "Mercado"), _cat(conn, "Sueldo")
    _mov(conn, categoria_id=mercado, fecha="2026-08-31T23:59:59")
    _mov(conn, categoria_id=mercado, fecha="2026-09-01T00:00:00")
    _mov(conn, "ingreso", "EMPRESA INVENTADA", categoria_id=sueldo, fecha="2026-08-02T08:00:00")
    asignar_categoria(conn, _mov(conn, descripcion="SUPER INVENTADO"), mercado, recordar=True)
    filas = {
        f["nombre"]: (f["movimientos_mes"], f["movimientos_total"], f["reglas"])
        for f in categorizacion.categorias_con_uso(conn, datetime(2026, 8, 1), datetime(2026, 9, 1))
    }
    assert filas["Mercado"] == (2, 3, 1)
    assert filas["Sueldo"] == (1, 1, 0)
    assert filas["Antojos"] == (0, 0, 0)
    solo_ingreso = categorizacion.categorias_con_uso(
        conn, datetime(2026, 8, 1), datetime(2026, 9, 1), clase="ingreso"
    )
    assert [f["nombre"] for f in solo_ingreso] == ["Sueldo", "Préstamos", "Otros ingresos"]


# --- Reglas de ingresos (criterio de terminado) ----------------------------------------------

def test_recordar_un_ingreso_crea_la_regla_por_quien_envia_y_categoriza_los_iguales(conn):
    sueldo = _cat(conn, "Sueldo")
    primero = _mov(conn, "ingreso", "Empresa  Inventada S.A.S.", monto=480000000)
    igual = _mov(conn, "ingreso", "EMPRESA INVENTADA S.A.S.", monto=480000000, fecha="2026-09-15T08:00:00")
    otro = _mov(conn, "ingreso", "OTRA PERSONA INVENTADA", monto=100)
    compra_igual = _mov(conn, "compra", "EMPRESA INVENTADA S.A.S.")
    ya = _mov(conn, "ingreso", "EMPRESA INVENTADA S.A.S.", categoria_id=_cat(conn, "Préstamos"))

    assert asignar_categoria(conn, primero, sueldo, recordar=True) == 2

    assert _categoria_de(conn, primero) == _categoria_de(conn, igual) == sueldo
    assert _categoria_de(conn, otro) is None
    assert _categoria_de(conn, compra_igual) is None  # otro campo: las de gasto no se tocan
    assert _categoria_de(conn, ya) == _cat(conn, "Préstamos")  # no se pisa
    [regla] = categorizacion.listar_reglas(conn)
    assert (regla["campo"], regla["texto"], regla["categoria"], regla["categoria_clase"]) == (
        "quien_envia", "empresa inventada s.a.s.", "Sueldo", "ingreso"
    )
    assert categorizacion.frase_regla(regla["campo"], regla["texto"], regla["categoria"]) == (
        "Si es un ingreso de «empresa inventada s.a.s.», va a Sueldo"
    )


def test_una_regla_de_ingreso_no_categoriza_gastos(conn):
    sueldo = _cat(conn, "Sueldo")
    asignar_categoria(conn, _mov(conn, "ingreso", "*5678"), sueldo, recordar=True)
    assert categorizacion.regla_que_coincide(conn, "ingreso", "*5678", 100)["categoria_id"] == sueldo
    assert categorizacion.regla_que_coincide(conn, "transferencia", "*5678", 100) is None
    assert categorizacion.regla_que_coincide(conn, "compra", "*5678", 100) is None


def _correo(gmail_id, texto, dia=15):
    return CorreoGmail(gmail_id, datetime(2026, 8, dia, 9, 0, tzinfo=ZONA_COLOMBIA), "Alerta (ejemplo)", texto,
                       **LEGITIMO)


def _recibiste(nombre, dia=15, monto="$160,000"):
    return (f"Bancolombia: Recibiste una transferencia por {monto} de {nombre} en tu cuenta **1234, "
            f"el {dia:02d}/08/2026 a las 10:00. Si tienes dudas, hablemos: 018000000000.")


def _categoria_gmail(conn, gmail_id):
    return sql(
        conn, "SELECT categoria_id, origen_categoria, regla_id FROM movimientos WHERE gmail_id = ?", (gmail_id,)
    ).fetchone()


def test_las_reglas_de_ingreso_se_aplican_al_sincronizar(conn):
    sueldo = _cat(conn, "Sueldo")
    # 1. Llega el primer ingreso: sin regla, queda pendiente con su monto aparte.
    assert sincronizar(conn, ClienteFalso({"r-1": _correo("r-1", _recibiste("EMPRESA INVENTADA S.A.S.", 15))})) \
        == ResultadoSincronizacion(nuevos=1)
    assert tuple(_categoria_gmail(conn, "r-1")) == (None, None, None)
    assert categorizacion.resumen_sin_categorizar(conn) == categorizacion.ResumenPendientes(1, 0, 16000000)

    # 2. El dueño lo categoriza y recuerda la regla.
    primero = categorizacion.sin_categorizar(conn)[0]["id"]
    asignar_categoria(conn, primero, sueldo, recordar=True)
    regla_id = categorizacion.listar_reglas(conn)[0]["id"]

    # 3. Siguiente sincronización: el mismo remitente llega categorizado por la
    #    regla; otro remitente queda pendiente.
    cliente = ClienteFalso({
        "r-2": _correo("r-2", _recibiste("Empresa Inventada S.A.S.", 16), 16),
        "r-3": _correo("r-3", _recibiste("OTRA PERSONA INVENTADA", 17), 17),
    })
    assert sincronizar(conn, cliente) == ResultadoSincronizacion(nuevos=2)
    assert tuple(_categoria_gmail(conn, "r-2")) == (sueldo, "regla", regla_id)
    assert tuple(_categoria_gmail(conn, "r-3")) == (None, None, None)
    assert categorizacion.resumen_sin_categorizar(conn) == categorizacion.ResumenPendientes(1, 0, 16000000)


def test_una_regla_de_gasto_con_el_mismo_texto_no_categoriza_un_ingreso_al_sincronizar(conn):
    otros = _cat(conn, "Otros")
    asignar_categoria(conn, _mov(conn, "transferencia", "PERSONA INVENTADA"), otros, recordar=True)
    sincronizar(conn, ClienteFalso({"r-1": _correo("r-1", _recibiste("PERSONA INVENTADA"))}))
    assert tuple(_categoria_gmail(conn, "r-1")) == (None, None, None)


# --- Pendientes: el monto de los ingresos nunca se suma al de los gastos ----------------------

def test_resumen_de_pendientes_separa_gastos_e_ingresos(conn):
    _mov(conn, "compra", monto=6863000)
    _mov(conn, "transferencia", "*5678", monto=600000)
    _mov(conn, "ingreso", "PERSONA INVENTADA", monto=16000000)
    _mov(conn, "ingreso", "EFECTIVO INVENTADO", monto=2500001)
    _mov(conn, "ajuste", "Ajuste", monto=-45678)
    _mov(conn, "compra", monto=999, categoria_id=_cat(conn, "Otros"))
    resumen = categorizacion.resumen_sin_categorizar(conn)
    assert resumen == categorizacion.ResumenPendientes(
        cuantos=4, gastos_centavos=6863000 + 600000, ingresos_centavos=16000000 + 2500001
    )
    assert resumen.cuantos == categorizacion.contar_sin_categorizar(conn) == len(categorizacion.sin_categorizar(conn))


def test_resumen_vacio(conn):
    assert categorizacion.resumen_sin_categorizar(conn) == categorizacion.ResumenPendientes(0, 0, 0)
