"""Casos borde del ítem 04: reglas y bandeja "Sin categorizar".

Complementa ``test_categorizacion.py``, ``test_sincronizacion_reglas.py`` y
``test_api_categorias.py``; las variantes de ``Origin`` están en
``test_api_sesion_bordes.py``. Todos los comercios, cuentas y montos son
inventados.
"""

from __future__ import annotations

from finanzas.modulos.sincronizacion import registro_sqlite

import threading
from datetime import datetime

import pytest
import sqlalchemy.exc

from finanzas import categorizacion, db, sincronizacion
from finanzas.categorizacion import (
    ErrorCategorizacion,
    asignar_categoria,
    borrar_regla,
    regla_que_coincide,
    contar_sin_categorizar,
    listar_reglas,
    normalizar,
    sin_categorizar,
)
from finanzas.gmail import ZONA_COLOMBIA, CorreoGmail
from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar
from tests.soporte.gmail_falso import LEGITIMO, ClienteFalso
from tests.soporte.ayudas_db import sql



def categoria_por_reglas(conn, tipo, descripcion):
    """Categoría de la regla que coincide (``regla_que_coincide``), o ``None``."""
    regla = regla_que_coincide(conn, tipo, descripcion, 100)
    return None if regla is None else regla["categoria_id"]


# --- Utilidades -------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "bordes.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
            "VALUES (1, 100000000, '2026-08-01')"
        )
    yield conexion
    conexion.close()


_contador = iter(range(1, 1_000_000))


def _mov(conn, tipo="compra", descripcion="TIENDA EJEMPLO", monto=100000, fecha="2026-08-15T10:00:00",
         categoria_id=None):
    origen, gmail_id = ("gmail", f"borde-{next(_contador)}") if tipo in ("compra", "transferencia") \
        else ("manual", None)
    with db.transaccion(conn):
        return sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fecha, monto, tipo, descripcion, categoria_id, origen, gmail_id),
        ).lastrowid


def _cat(conn, nombre):
    return sql(conn, "SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]


def _categoria_de(conn, mid):
    return sql(conn, "SELECT categoria_id FROM movimientos WHERE id = ?", (mid,)).fetchone()[0]


def _categoria_gmail(conn, gmail_id):
    return sql(conn, "SELECT categoria_id FROM movimientos WHERE gmail_id = ?", (gmail_id,)).fetchone()[0]


def _correo(gmail_id: str, texto: str, dia: int = 15) -> CorreoGmail:
    return CorreoGmail(
        gmail_id, datetime(2026, 8, dia, 14, 40, tzinfo=ZONA_COLOMBIA), "Aviso (ejemplo)", texto, **LEGITIMO
    )


def _compra(comercio: str, dia: int = 15) -> str:
    return f"Bancolombia: Compraste $12.500,00 en {comercio} con tu T.Deb *1234, el {dia:02d}/08/2026 a las 11:05."


def _transferencia(destino: str, dia: int = 16) -> str:
    return f"Bancolombia: Transferiste $6,000.00 desde tu cuenta *1234 a la cuenta {destino} el {dia:02d}/08/26 a las 09:15."


# --- Normalización: tildes, emojis, asteriscos, espacios y mayúsculas especiales -----------

@pytest.mark.parametrize(
    "a, b",
    [
        ("CAFÉ EJEMPLO", "café ejemplo"),              # compuesta vs descompuesta
        ("PANADERÍA ÑANDÚ", "panadería ñandú"),
        ("MERPAGO*TIENDA", "merpago*tienda"),
        ("  TIENDA\t\tEJEMPLO \n", "tienda ejemplo"),
        ("TIENDA EJEMPLO", "tienda ejemplo"),           # espacio duro
        ("TIENDA EJEMPLO", "tienda ejemplo"),           # espacio em
        ("HELADERÍA ☕ 🍦", "heladería ☕ 🍦"),
        ("STRASSE SHOP", "straße shop"),                     # casefold > lower
        ("İSTANBUL KEBAB", "i̇stanbul kebab"),          # İ turca -> i + punto combinante
    ],
)
def test_normalizar_equivalentes(a, b):
    assert normalizar(a) == normalizar(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("MERPAGO*TIENDA", "MERPAGO * TIENDA"),   # el asterisco y los espacios a su lado cuentan
        ("MERPAGO*TIENDA", "MERPAGOTIENDA"),
        ("ISTANBUL KEBAB", "ıstanbul kebab"),     # I latina vs ı turca sin punto: letras distintas
        ("CAFÉ EJEMPLO", "CAFE EJEMPLO"),         # la tilde no se quita
        ("HELADERÍA ☕", "HELADERÍA 🍦"),
    ],
)
def test_normalizar_distintos(a, b):
    assert normalizar(a) != normalizar(b)


def test_regla_con_tilde_descompuesta_y_emoji_categoriza_la_variante(conn):
    mercado = _cat(conn, "Mercado")
    a = _mov(conn, descripcion="CAFÉ ☕ EJEMPLO")
    b = _mov(conn, descripcion="café  ☕ ejemplo")
    c = _mov(conn, descripcion="CAFE ☕ EJEMPLO")  # sin tilde: otro texto
    assert asignar_categoria(conn, a, mercado, recordar=True) == 2
    assert _categoria_de(conn, b) == mercado
    assert _categoria_de(conn, c) is None
    assert categoria_por_reglas(conn, "compra", "Café ☕ Ejemplo") == mercado


def test_sincronizar_comercio_descompuesto_usa_la_regla_compuesta(conn):
    mercado = _cat(conn, "Mercado")
    sincronizar(conn, ClienteFalso({"c-1": _correo("c-1", _compra("CAFÉ EJEMPLO"))}))
    asignar_categoria(conn, sin_categorizar(conn)[0]["id"], mercado, recordar=True)
    sincronizar(conn, ClienteFalso({"c-2": _correo("c-2", _compra("CAFÉ EJEMPLO", 17), 17)}))
    assert _categoria_gmail(conn, "c-2") == mercado


def test_texto_solo_espacios_no_encuentra_regla(conn):
    assert categoria_por_reglas(conn, "compra", "   \t ") is None
    m = _mov(conn, descripcion="   ")
    with pytest.raises(ErrorCategorizacion):
        asignar_categoria(conn, m, _cat(conn, "Otros"), recordar=True)
    assert _categoria_de(conn, m) is None
    assert listar_reglas(conn) == []


# --- Separación comercio / cuenta destino ---------------------------------------------------

def test_regla_de_comercio_no_categoriza_transferencia_al_sincronizar(conn):
    with db.transaccion(conn):
        sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', '*5678', ?)",
                     (_cat(conn, "Mercado"),))
    sincronizar(conn, ClienteFalso({"t-1": _correo("t-1", _transferencia("*5678"))}))
    assert _categoria_gmail(conn, "t-1") is None


def test_recordar_transferencia_no_toca_compra_con_el_mismo_texto(conn):
    vivienda = _cat(conn, "Vivienda y servicios")
    t1 = _mov(conn, "transferencia", "*5678")
    t2 = _mov(conn, "transferencia", "*5678")
    compra = _mov(conn, "compra", "*5678")
    assert asignar_categoria(conn, t1, vivienda, recordar=True) == 2
    assert _categoria_de(conn, t2) == vivienda
    assert _categoria_de(conn, compra) is None
    assert [(r["campo"], r["texto"]) for r in listar_reglas(conn)] == [("cuenta_destino", "*5678")]
    assert categoria_por_reglas(conn, "compra", "*5678") is None


def test_recordar_compra_no_toca_transferencia_con_el_mismo_texto(conn):
    mercado = _cat(conn, "Mercado")
    compra = _mov(conn, "compra", "*5678")
    transferencia = _mov(conn, "transferencia", "*5678")
    assert asignar_categoria(conn, compra, mercado, recordar=True) == 1
    assert _categoria_de(conn, transferencia) is None


# --- Recordar dos veces, borrar y volver a sincronizar -------------------------------------

def test_recordar_dos_veces_con_categorias_distintas(conn):
    mercado, restaurantes = _cat(conn, "Mercado"), _cat(conn, "Restaurantes")
    a = _mov(conn, descripcion="TIENDA DOBLE")
    b = _mov(conn, descripcion="tienda doble")
    assert asignar_categoria(conn, a, mercado, recordar=True) == 2

    c = _mov(conn, descripcion="TIENDA DOBLE")
    assert asignar_categoria(conn, c, restaurantes, recordar=True) == 1

    reglas = listar_reglas(conn)
    assert len(reglas) == 1 and reglas[0]["categoria_id"] == restaurantes
    # Lo ya categorizado con la regla anterior se respeta.
    assert _categoria_de(conn, a) == _categoria_de(conn, b) == mercado
    assert _categoria_de(conn, c) == restaurantes
    assert categoria_por_reglas(conn, "compra", "Tienda Doble") == restaurantes


def test_recordar_dos_veces_y_sincronizar_usa_la_ultima(conn):
    mercado, restaurantes = _cat(conn, "Mercado"), _cat(conn, "Restaurantes")
    sincronizar(conn, ClienteFalso({"c-1": _correo("c-1", _compra("TIENDA DOBLE"))}))
    m = sin_categorizar(conn)[0]["id"]
    asignar_categoria(conn, m, mercado, recordar=True)
    asignar_categoria(conn, m, restaurantes, recordar=True)  # cambia de idea sobre el mismo movimiento
    sincronizar(conn, ClienteFalso({"c-2": _correo("c-2", _compra("TIENDA DOBLE", 18), 18)}))
    assert _categoria_de(conn, m) == restaurantes
    assert _categoria_gmail(conn, "c-2") == restaurantes


def test_borrar_regla_y_volver_a_sincronizar(conn):
    mercado = _cat(conn, "Mercado")
    sincronizar(conn, ClienteFalso({"c-1": _correo("c-1", _compra("TIENDA BORRADA"))}))
    asignar_categoria(conn, sin_categorizar(conn)[0]["id"], mercado, recordar=True)
    sincronizar(conn, ClienteFalso({"c-2": _correo("c-2", _compra("TIENDA BORRADA", 16), 16)}))
    assert _categoria_gmail(conn, "c-2") == mercado

    borrar_regla(conn, listar_reglas(conn)[0]["id"])

    cliente = ClienteFalso({
        "c-1": _correo("c-1", _compra("TIENDA BORRADA")),          # ya registrado
        "c-2": _correo("c-2", _compra("TIENDA BORRADA", 16), 16),  # ya registrado
        "c-3": _correo("c-3", _compra("TIENDA BORRADA", 17), 17),  # nuevo
    })
    assert sincronizar(conn, cliente) == ResultadoSincronizacion(nuevos=1)
    assert _categoria_gmail(conn, "c-1") == mercado
    assert _categoria_gmail(conn, "c-2") == mercado
    assert _categoria_gmail(conn, "c-3") is None
    assert [f["descripcion"] for f in sin_categorizar(conn)] == ["TIENDA BORRADA"]


def test_borrar_regla_dos_veces(conn):
    m = _mov(conn)
    asignar_categoria(conn, m, _cat(conn, "Otros"), recordar=True)
    rid = listar_reglas(conn)[0]["id"]
    borrar_regla(conn, rid)
    with pytest.raises(categorizacion.ReglaNoEncontrada):
        borrar_regla(conn, rid)


def test_regla_borrada_y_recreada_vuelve_a_aplicar(conn):
    otros = _cat(conn, "Otros")
    m = _mov(conn, descripcion="TIENDA CICLO")
    asignar_categoria(conn, m, otros, recordar=True)
    borrar_regla(conn, listar_reglas(conn)[0]["id"])
    n = _mov(conn, descripcion="TIENDA CICLO")
    assert asignar_categoria(conn, n, otros, recordar=True) == 1
    assert categoria_por_reglas(conn, "compra", "TIENDA CICLO") == otros


# --- Muchos pendientes --------------------------------------------------------------------

def test_muchos_pendientes_del_mismo_comercio(conn):
    mercado, otros = _cat(conn, "Mercado"), _cat(conn, "Otros")
    variantes = ["TIENDA MASIVA", "tienda masiva", " Tienda  Masiva ", "TIENDA MASIVA"]
    ids = [_mov(conn, descripcion=variantes[i % len(variantes)], fecha=f"2026-08-{1 + i % 28:02d}T10:00:00")
           for i in range(400)]
    ya_hecho = _mov(conn, descripcion="TIENDA MASIVA", categoria_id=otros)
    otra_tienda = _mov(conn, descripcion="TIENDA MASIVA 2")
    transferencia = _mov(conn, "transferencia", "TIENDA MASIVA")

    assert contar_sin_categorizar(conn) == 402
    assert asignar_categoria(conn, ids[123], mercado, recordar=True) == 400
    assert contar_sin_categorizar(conn) == 2
    assert {f["id"] for f in sin_categorizar(conn)} == {otra_tienda, transferencia}
    assert _categoria_de(conn, ya_hecho) == otros
    assert sql(conn, "SELECT COUNT(*) FROM movimientos WHERE categoria_id = ?", (mercado,)).fetchone()[0] == 400


# --- Concurrencia -------------------------------------------------------------------------

def test_asignar_durante_una_sincronizacion_no_pierde_ni_equivoca(conn, tmp_path, monkeypatch):
    """Alguien intenta guardar una regla mientras la sincronización consulta las reglas.

    Ajustada en la ronda 1 de revisión: la consulta ahora ocurre dentro de la
    transacción ``BEGIN IMMEDIATE`` del INSERT, así que la otra conexión no
    puede escribir en medio (en la web esperaría unos milisegundos; aquí, en
    el mismo hilo y sin espera, falla con "database is locked"). El
    movimiento nuevo no se pierde ni queda con otra categoría: llega a la
    bandeja y "Recordar" lo categoriza después.
    """
    mercado = _cat(conn, "Mercado")
    previo = _mov(conn, descripcion="TIENDA CARRERA")
    original = registro_sqlite._columnas_de_categoria
    bloqueos: list[str] = []

    def con_carrera(c, movimiento, **kwargs):
        resultado = original(c, movimiento, **kwargs)
        otra = db.conectar(str(tmp_path / "bordes.db"), espera=0)
        try:
            asignar_categoria(otra, previo, mercado, recordar=True)
        except sqlalchemy.exc.OperationalError as error:
            bloqueos.append(str(error.orig))  # el error del driver, sin el envoltorio
        finally:
            otra.close()
        return resultado

    monkeypatch.setattr(registro_sqlite, "_columnas_de_categoria", con_carrera)
    assert sincronizar(conn, ClienteFalso({"c-1": _correo("c-1", _compra("TIENDA CARRERA"))})) == \
        ResultadoSincronizacion(nuevos=1)
    assert bloqueos == ["database is locked"]
    assert _categoria_de(conn, previo) is None
    assert _categoria_gmail(conn, "c-1") is None
    assert listar_reglas(conn) == []
    # Nada se perdió: al recordar ahora, se categorizan los dos.
    assert asignar_categoria(conn, previo, mercado, recordar=True) == 2
    assert _categoria_gmail(conn, "c-1") == mercado
    assert sin_categorizar(conn) == []


def test_sincronizacion_y_asignacion_en_hilos(tmp_path):
    ruta = str(tmp_path / "hilos.db")
    base = db.conectar(ruta)
    db.inicializar(base)
    with db.transaccion(base):
        sql(base, "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
                     "VALUES (1, 100000000, '2026-08-01')")
    mercado = _cat(base, "Mercado")
    previos = [_mov(base, descripcion="TIENDA HILOS") for _ in range(50)]
    correos = {f"h-{i}": _correo(f"h-{i}", _compra("TIENDA HILOS" if i % 2 else "OTRA TIENDA", 1 + i % 28),
                                 1 + i % 28) for i in range(200)}
    errores: list[BaseException] = []

    def sync():
        c = db.conectar(ruta)
        try:
            sincronizar(c, ClienteFalso(correos))
        except BaseException as e:  # noqa: BLE001
            errores.append(e)
        finally:
            c.close()

    def asignar():
        c = db.conectar(ruta)
        try:
            for mid in previos[:5]:
                asignar_categoria(c, mid, mercado, recordar=True)
        except BaseException as e:  # noqa: BLE001
            errores.append(e)
        finally:
            c.close()

    hilos = [threading.Thread(target=sync), threading.Thread(target=asignar)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    assert errores == []
    total = sql(base, "SELECT COUNT(*) FROM movimientos").fetchone()[0]
    assert total == 250
    # Nada de "TIENDA HILOS" con otra categoría, y OTRA TIENDA sigue sin categoría.
    malas = sql(
        base,
        "SELECT COUNT(*) FROM movimientos WHERE categoria_id IS NOT NULL AND categoria_id <> ?", (mercado,)
    ).fetchone()[0]
    assert malas == 0
    assert sql(
        base,
        "SELECT COUNT(*) FROM movimientos WHERE descripcion = 'OTRA TIENDA' AND categoria_id IS NOT NULL"
    ).fetchone()[0] == 0
    assert all(_categoria_de(base, mid) == mercado for mid in previos)
    base.close()


# --- Ingresos y ajustes -------------------------------------------------------------------

@pytest.mark.parametrize("tipo, monto", [("ajuste", -150050), ("ajuste", 250000)])
def test_ajuste_nunca_en_bandeja_ni_categorizable(conn, tipo, monto):
    m = _mov(conn, tipo, "TIENDA EJEMPLO", monto=monto)
    compra = _mov(conn, "compra", "TIENDA EJEMPLO")
    assert [f["id"] for f in sin_categorizar(conn)] == [compra]
    assert contar_sin_categorizar(conn) == 1
    for recordar in (False, True):
        with pytest.raises(ErrorCategorizacion):
            asignar_categoria(conn, m, _cat(conn, "Otros"), recordar=recordar)
    assert _categoria_de(conn, m) is None
    # Recordar la compra con el mismo texto no alcanza al ingreso/ajuste.
    asignar_categoria(conn, compra, _cat(conn, "Otros"), recordar=True)
    assert _categoria_de(conn, m) is None
    assert categoria_por_reglas(conn, tipo, "TIENDA EJEMPLO") is None


def test_ingreso_en_bandeja_solo_con_categorias_de_ingreso(conn):
    # Ítem 15: un ingreso sin categoría es pendiente y solo acepta categorías de ingreso.
    ingreso = _mov(conn, "ingreso", "TIENDA EJEMPLO", monto=350000000)
    compra = _mov(conn, "compra", "TIENDA EJEMPLO")
    assert {f["id"] for f in sin_categorizar(conn)} == {ingreso, compra}
    assert contar_sin_categorizar(conn) == 2
    for recordar in (False, True):
        with pytest.raises(ErrorCategorizacion, match="categorías de ingreso"):
            asignar_categoria(conn, ingreso, _cat(conn, "Otros"), recordar=recordar)
        with pytest.raises(ErrorCategorizacion, match="categorías de gasto"):
            asignar_categoria(conn, compra, _cat(conn, "Sueldo"), recordar=recordar)
    assert _categoria_de(conn, ingreso) is None
    # Recordar la compra con el mismo texto no alcanza al ingreso (otro campo).
    asignar_categoria(conn, compra, _cat(conn, "Otros"), recordar=True)
    assert _categoria_de(conn, ingreso) is None
    assert categoria_por_reglas(conn, "ingreso", "TIENDA EJEMPLO") is None
