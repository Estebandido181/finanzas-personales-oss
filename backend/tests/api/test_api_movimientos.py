"""API de movimientos del ítem 14: filtros, origen de la categoría y categorizar en un paso.

Datos inventados.
"""

from __future__ import annotations

import pytest

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import ejecutar_sql, insertar_movimiento

MES = {"mes": "2026-08"}


@pytest.fixture
def mes(config):
    """Un mes con de todo: pendiente, categorizado a mano, por regla, desconocido, ingreso y ajuste."""
    ids = {
        "pendiente": insertar_movimiento(config, "2026-08-02T10:00:00", 850000, "compra", "PANADERIA INVENTADA"),
        "desconocido": insertar_movimiento(
            config, "2026-08-03T10:00:00", 1200000, "compra", "HELADERIA INVENTADA", categoria_id=7
        ),
        "a_mano": insertar_movimiento(config, "2026-08-04T10:00:00", 620000, "transferencia", "*3000000009"),
        "por_regla_1": insertar_movimiento(config, "2026-08-05T10:00:00", 320000, "transferencia", "*3000000001"),
        "por_regla_2": insertar_movimiento(config, "2026-08-06T10:00:00", 320000, "transferencia", "*3000000001"),
        "ingreso": insertar_movimiento(config, "2026-08-07T10:00:00", 480000000, "ingreso", "EMPRESA INVENTADA"),
        "ajuste": insertar_movimiento(
            config, "2026-08-08T10:00:00", -4500, "ajuste", "Ajuste de saldo", origen="manual"
        ),
        "otro_mes": insertar_movimiento(config, "2026-09-01T10:00:00", 100, "compra", "OTRO MES"),
    }
    return ids


def _categorizar(api, movimiento_id, categoria_id, recordar=False):
    r = api.put(
        f"/api/movimientos/{movimiento_id}/categoria",
        json={"categoria_id": categoria_id, "recordar": recordar},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _por_id(api, **params):
    r = api.get("/api/movimientos", params={**MES, **params})
    assert r.status_code == 200, r.text
    return {m["id"]: m for m in r.json()["movimientos"]}


def _preparado(api, mes):
    _categorizar(api, mes["a_mano"], 6)
    # "Recordar" sobre por_regla_1: él queda a mano y la regla alcanza a por_regla_2.
    _categorizar(api, mes["por_regla_1"], 3, recordar=True)
    return _por_id(api)


# --- Origen de la categoría ---------------------------------------------------------------

def test_cada_movimiento_dice_como_se_categorizo(api, mes, config):
    movimientos = _preparado(api, mes)
    regla_id = ejecutar_sql(config, "SELECT id FROM reglas").fetchone()[0]
    regla = {"id": regla_id, "tipo_movimiento": "transferencia", "campo": "cuenta_destino", "texto": "*0001",
             "monto_centavos": None, "condiciones": "texto", "frase": "transferencia a «*0001»",
             "modo_texto": "exacta", "origen_regla": "todos"}

    assert movimientos[mes["pendiente"]]["origen_categoria"] is None
    assert movimientos[mes["pendiente"]]["regla"] is None
    assert movimientos[mes["desconocido"]]["origen_categoria"] == "desconocido"
    assert movimientos[mes["desconocido"]]["regla"] is None
    assert movimientos[mes["a_mano"]]["origen_categoria"] == "manual"
    assert movimientos[mes["por_regla_1"]]["origen_categoria"] == "manual"
    assert movimientos[mes["por_regla_2"]] == {
        "id": mes["por_regla_2"],
        "fecha_hora": "2026-08-06T10:00:00",
        "tipo": "transferencia",
        "descripcion": "*3000000001",
        "monto_centavos": 320000,
        "es_gasto": True,
        "categoria": {"id": 3, "nombre": "Transporte", "clase": "gasto", "color": "cat-transporte", "icono": "bus"},
        "origen": "gmail",
        "origen_categoria": "regla",
        "regla": regla,
        "pendiente": False,
        "descartado": False,
        "puede_descartar": False,
        "motivo_no_descartar": "Configura el saldo y la fecha de inicio antes de revisar este movimiento.",
        "puede_restaurar": False,
        "motivo_no_restaurar": "Configura el saldo y la fecha de inicio antes de revisar este movimiento.",
        "categorizable": True,
        "clase_categoria": "gasto",
        "regla_posible": {"campo": "cuenta_destino", "texto": "*0001"},
        "reglas_posibles": [
            {"condiciones": c, "tipo_movimiento": "transferencia", "campo": "cuenta_destino",
             "texto": t, "monto_centavos": mo, "frase": f}
            for c, t, mo, f in (
                ("texto", "*0001", None, "transferencia a «*0001»"),
                ("monto", None, 320000, "transferencia de $3.200"),
                ("texto_y_monto", "*0001", 320000, "transferencia a «*0001» por $3.200"),
            )
        ],
    }
    for clave in ("ingreso", "ajuste"):
        assert movimientos[mes[clave]]["origen_categoria"] is None
        assert movimientos[mes[clave]]["regla"] is None


def test_corregir_uno_de_regla_lo_marca_manual(api, mes):
    """Criterio de terminado del ítem 14: al corregir queda marcado como manual."""
    _preparado(api, mes)
    respuesta = _categorizar(api, mes["por_regla_2"], 4)
    assert respuesta == {"categorizados": 1, "regla_guardada": False, "regla": None}
    movimiento = _por_id(api)[mes["por_regla_2"]]
    assert movimiento["categoria"]["id"] == 4
    assert movimiento["categoria"]["nombre"] == "Vivienda y servicios"
    assert movimiento["origen_categoria"] == "manual"
    assert movimiento["regla"] is None


def test_borrar_la_regla_deja_origen_regla_sin_regla(api, mes):
    _preparado(api, mes)
    regla_id = _por_id(api)[mes["por_regla_2"]]["regla"]["id"]
    assert api.delete(f"/api/reglas/{regla_id}").status_code == 200
    movimiento = _por_id(api)[mes["por_regla_2"]]
    assert movimiento["categoria"]["id"] == 3
    assert movimiento["origen_categoria"] == "regla"
    assert movimiento["regla"] is None


# --- Categorizar en un paso, con la regla --------------------------------------------------

def test_categorizar_y_crear_la_regla_en_una_llamada(api, mes, config):
    respuesta = _categorizar(api, mes["por_regla_1"], 3, recordar=True)
    regla_id = ejecutar_sql(config, "SELECT id FROM reglas").fetchone()[0]
    assert respuesta == {
        "categorizados": 2,
        "regla_guardada": True,
        "regla": {"id": regla_id, "tipo_movimiento": "transferencia", "campo": "cuenta_destino", "texto": "*0001",
                  "monto_centavos": None, "condiciones": "texto", "frase": "transferencia a «*0001»",
                  "modo_texto": "exacta", "origen_regla": "todos"},
    }
    # Quedan la panadería, la transferencia a *0009, el ingreso y la del otro mes.
    assert api.get("/api/movimientos/sin-categorizar").json()["total"] == 4


def test_crear_la_regla_despues_de_categorizar(api, mes):
    # Primer toque: la categoría. Segundo: la regla (misma llamada con recordar).
    assert _categorizar(api, mes["por_regla_1"], 3)["regla"] is None
    respuesta = _categorizar(api, mes["por_regla_1"], 3, recordar=True)
    assert respuesta["categorizados"] == 2 and respuesta["regla"]["texto"] == "*0001"
    movimientos = _por_id(api)
    assert movimientos[mes["por_regla_1"]]["origen_categoria"] == "manual"
    assert movimientos[mes["por_regla_2"]]["origen_categoria"] == "regla"


def test_categorizar_sin_token_csrf_se_rechaza_sin_cambiar_nada(api, cliente, mes):
    r = cliente.put(f"/api/movimientos/{mes['pendiente']}/categoria", json={"categoria_id": 1, "recordar": True})
    assert r.status_code == 403
    assert _por_id(api)[mes["pendiente"]]["categoria"] is None


def test_categorizar_desde_otro_origen_se_rechaza(api, mes):
    r = api.put(
        f"/api/movimientos/{mes['pendiente']}/categoria",
        json={"categoria_id": 1},
        headers={"Origin": "https://sitio-ajeno.example"},
    )
    assert r.status_code == 403
    assert _por_id(api)[mes["pendiente"]]["categoria"] is None


def test_un_ingreso_solo_acepta_categorias_de_ingreso(api, mes):
    # Ítem 15: 1 es Mercado (gasto): 400 sin cambiar nada; 10 es Sueldo (ingreso).
    r = api.put(f"/api/movimientos/{mes['ingreso']}/categoria", json={"categoria_id": 1})
    assert r.status_code == 400
    assert r.json() == {"detalle": "Un ingreso solo acepta categorías de ingreso."}
    assert _por_id(api)[mes["ingreso"]]["categoria"] is None
    assert _categorizar(api, mes["ingreso"], 10)["categorizados"] == 1
    assert _por_id(api)[mes["ingreso"]]["categoria"]["nombre"] == "Sueldo"


def test_un_gasto_solo_acepta_categorias_de_gasto(api, mes):
    r = api.put(f"/api/movimientos/{mes['pendiente']}/categoria", json={"categoria_id": 10, "recordar": True})
    assert r.status_code == 400
    assert r.json() == {"detalle": "Un gasto solo acepta categorías de gasto."}
    assert _por_id(api)[mes["pendiente"]]["categoria"] is None


def test_un_ajuste_no_se_categoriza(api, mes):
    for categoria_id in (1, 10):
        r = api.put(f"/api/movimientos/{mes['ajuste']}/categoria", json={"categoria_id": categoria_id})
        assert r.status_code == 400


# --- Filtros --------------------------------------------------------------------------------

def test_sin_filtros_trae_todo_el_mes(api, mes):
    assert set(_por_id(api)) == {v for k, v in mes.items() if k != "otro_mes"}


@pytest.mark.parametrize(
    ("tipo", "esperados"),
    [
        ("gasto", {"pendiente", "desconocido", "a_mano", "por_regla_1", "por_regla_2"}),
        ("compra", {"pendiente", "desconocido"}),
        ("transferencia", {"a_mano", "por_regla_1", "por_regla_2"}),
        ("ingreso", {"ingreso"}),
        ("ajuste", {"ajuste"}),
    ],
)
def test_filtro_por_tipo(api, mes, tipo, esperados):
    assert set(_por_id(api, tipo=tipo)) == {mes[k] for k in esperados}


def test_filtro_por_categoria(api, mes):
    _preparado(api, mes)
    assert set(_por_id(api, categoria_id=3)) == {mes["por_regla_1"], mes["por_regla_2"]}
    assert set(_por_id(api, categoria_id=7)) == {mes["desconocido"]}
    assert _por_id(api, categoria_id=8) == {}


def test_filtro_sin_categoria_son_los_pendientes_del_mes(api, mes):
    assert set(_por_id(api, sin_categoria=True)) == {
        mes["pendiente"], mes["a_mano"], mes["por_regla_1"], mes["por_regla_2"], mes["ingreso"],
    }
    _preparado(api, mes)
    assert set(_por_id(api, sin_categoria=True)) == {mes["pendiente"], mes["ingreso"]}
    assert set(_por_id(api, sin_categoria=False)) == {v for k, v in mes.items() if k != "otro_mes"}


def test_filtros_combinados(api, mes):
    _preparado(api, mes)
    assert set(_por_id(api, tipo="transferencia", categoria_id=6)) == {mes["a_mano"]}
    assert _por_id(api, tipo="compra", categoria_id=6) == {}
    assert set(_por_id(api, tipo="compra", sin_categoria=True)) == {mes["pendiente"]}
    assert set(_por_id(api, tipo="ingreso", sin_categoria=True)) == {mes["ingreso"]}
    assert _por_id(api, tipo="ajuste", sin_categoria=True) == {}
    _categorizar(api, mes["ingreso"], 10)
    assert set(_por_id(api, tipo="ingreso", categoria_id=10)) == {mes["ingreso"]}


def test_filtro_conserva_el_orden(api, mes):
    r = api.get("/api/movimientos", params={**MES, "tipo": "gasto"}).json()["movimientos"]
    fechas = [m["fecha_hora"] for m in r]
    assert fechas == sorted(fechas, reverse=True)


def test_categoria_y_sin_categoria_juntos_400(api, mes):
    r = api.get("/api/movimientos", params={**MES, "categoria_id": 1, "sin_categoria": True})
    assert r.status_code == 400
    assert r.json() == {"detalle": "No se puede filtrar a la vez por una categoría y por sin categoría."}


@pytest.mark.parametrize(
    "params",
    [
        {"tipo": "retiro"},
        {"tipo": "GASTO"},
        {"categoria_id": 0},
        {"categoria_id": -1},
        {"categoria_id": "uno"},
        {"categoria_id": 10**18 + 1},
        {"sin_categoria": "quizas"},
    ],
)
def test_filtros_invalidos_422(api, params):
    assert api.get("/api/movimientos", params={**MES, **params}).status_code == 422


def test_filtros_exigen_sesion(cliente):
    assert cliente.get("/api/movimientos", params={**MES, "tipo": "gasto"}).status_code == 401


# --- Bandeja y pendientes (criterio del ítem 15) ----------------------------------------------

def test_la_bandeja_y_los_pendientes_incluyen_el_ingreso_con_su_monto_aparte(api, mes):
    bandeja = api.get("/api/movimientos/sin-categorizar").json()
    assert {m["id"] for m in bandeja["movimientos"]} == {
        mes["pendiente"], mes["a_mano"], mes["por_regla_1"], mes["por_regla_2"], mes["ingreso"],
        mes["otro_mes"],
    }
    reporte = api.get("/api/reporte", params=MES).json()
    assert reporte["pendientes"] == 6
    assert reporte["pendientes_centavos"] == 850000 + 620000 + 320000 + 320000 + 100
    assert reporte["pendientes_ingresos_centavos"] == 480000000


def test_filtrar_movimientos_valida_el_tipo_tambien_fuera_de_la_api():
    from finanzas.flujos import reporte

    with pytest.raises(reporte.ErrorReporte):
        reporte.filtrar_movimientos([], tipo="retiro")
    assert reporte.filtrar_movimientos([], tipo="gasto") == []


# --- Reglas de negocio que decide el backend (pendiente, categorizable, regla_posible) ----

def test_pendiente_categorizable_y_regla_posible(api, mes):
    movimientos = _preparado(api, mes)
    esperado = {
        "pendiente": (True, True, {"campo": "comercio", "texto": "panaderia inventada"}),
        "desconocido": (False, True, {"campo": "comercio", "texto": "heladeria inventada"}),
        "a_mano": (False, True, {"campo": "cuenta_destino", "texto": "*0009"}),
        "por_regla_2": (False, True, {"campo": "cuenta_destino", "texto": "*0001"}),
        "ingreso": (True, True, {"campo": "quien_envia", "texto": "empresa inventada"}),
        "ajuste": (False, False, None),
    }
    for clave, (pendiente, categorizable, regla_posible) in esperado.items():
        mov = movimientos[mes[clave]]
        assert (mov["pendiente"], mov["categorizable"], mov["regla_posible"]) == (
            pendiente, categorizable, regla_posible,
        ), clave
    clases = {clave: movimientos[mes[clave]]["clase_categoria"] for clave in esperado}
    assert clases == {
        "pendiente": "gasto", "desconocido": "gasto", "a_mano": "gasto", "por_regla_2": "gasto",
        "ingreso": "ingreso", "ajuste": None,
    }


def test_regla_posible_usa_la_misma_normalizacion_que_recordar(api, config):
    uno = insertar_movimiento(config, "2026-08-02T10:00:00", 100, "compra", "  Café\u200b  ÉJEMPLO\t Tienda ")
    posible = _por_id(api)[uno]["regla_posible"]
    regla = _categorizar(api, uno, 1, recordar=True)["regla"]
    assert posible == {"campo": regla["campo"], "texto": regla["texto"]}
    assert posible["texto"] == "café éjemplo tienda"


def test_sin_descripcion_no_hay_regla_posible(api, config):
    uno = insertar_movimiento(config, "2026-08-02T10:00:00", 100, "compra", "   ")
    mov = _por_id(api)[uno]
    assert (mov["pendiente"], mov["categorizable"], mov["regla_posible"]) == (True, True, None)
    r = api.put(f"/api/movimientos/{uno}/categoria", json={"categoria_id": 1, "recordar": True})
    assert r.status_code == 400


def test_pendiente_coincide_con_la_bandeja(api, mes):
    _categorizar(api, mes["a_mano"], 6)
    pendientes_del_mes = {i for i, m in _por_id(api).items() if m["pendiente"]}
    bandeja = {m["id"] for m in api.get("/api/movimientos/sin-categorizar").json()["movimientos"]}
    assert pendientes_del_mes == bandeja - {mes["otro_mes"]}
    assert set(_por_id(api, sin_categoria=True)) == pendientes_del_mes


def test_la_app_no_expone_rutas_e2e(app):
    rutas = [getattr(r, "path", "") for r in app.routes]
    assert rutas  # la app sí tiene rutas
    assert not [r for r in rutas if r == "/e2e" or r.startswith("/e2e/")]
