"""API de categorías propias y reglas (ítem 15). Datos inventados.

Ids de las categorías iniciales: 1 a 8 las de la v1 (8 = Otros), 9 Antojos,
10 Sueldo, 11 Préstamos y 12 Otros ingresos.
"""

from __future__ import annotations

import pytest

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import ejecutar_sql, insertar_movimiento

ANTOJOS, SUELDO, PRESTAMOS, OTROS_INGRESOS = 9, 10, 11, 12


def _todo(config):
    return [
        ejecutar_sql(config, f"SELECT * FROM {t} ORDER BY id").fetchall()
        for t in ("categorias", "movimientos", "reglas")
    ]


def _crear(api, **datos):
    cuerpo = {"nombre": "Mascotas", "clase": "gasto", "color": "cat-otros", "icono": "bus", **datos}
    return api.post("/api/categorias", json=cuerpo)


# --- Listar ---------------------------------------------------------------------------------

def test_listar_con_clase_color_icono_y_uso(api, config):
    insertar_movimiento(config, "2026-08-02T10:00:00", 100, "compra", "HELADERIA INVENTADA", categoria_id=ANTOJOS)
    insertar_movimiento(config, "2026-07-02T10:00:00", 100, "compra", "HELADERIA INVENTADA", categoria_id=ANTOJOS)
    insertar_movimiento(config, "2026-08-03T10:00:00", 4800000, "ingreso", "EMPRESA INVENTADA", categoria_id=SUELDO)
    ejecutar_sql(config, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('quien_envia', 'empresa inventada', 10)")
    r = api.get("/api/categorias", params={"mes": "2026-08"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["mes"] == "2026-08"
    por_id = {c["id"]: c for c in datos["categorias"]}
    assert por_id[ANTOJOS] == {
        "id": ANTOJOS, "nombre": "Antojos", "clase": "gasto", "color": "cat-antojos", "icono": "ice-cream-cone",
        "movimientos_mes": 1, "movimientos_total": 2, "reglas": 0, "se_puede_deshacer_borrado": False,
    }
    assert por_id[SUELDO] == {
        "id": SUELDO, "nombre": "Sueldo", "clase": "ingreso", "color": "cat-sueldo", "icono": "briefcase",
        "movimientos_mes": 1, "movimientos_total": 1, "reglas": 1, "se_puede_deshacer_borrado": False,
    }
    # Sin movimientos ni reglas: borrarla se puede deshacer (ítem 38).
    assert por_id[2]["se_puede_deshacer_borrado"] is True
    assert [c["clase"] for c in datos["categorias"]] == ["gasto"] * 11 + ["ingreso"] * 3


@pytest.mark.parametrize(("clase", "cuantas"), [("gasto", 11), ("ingreso", 3)])
def test_listar_por_clase(api, clase, cuantas):
    categorias = api.get("/api/categorias", params={"clase": clase}).json()["categorias"]
    assert len(categorias) == cuantas and {c["clase"] for c in categorias} == {clase}


@pytest.mark.parametrize("params", [{"clase": "otra"}, {"mes": "2026-13"}, {"mes": "x" * 8}])
def test_listar_con_parametros_no_validos(api, params):
    assert api.get("/api/categorias", params=params).status_code in (400, 422)


# --- Crear ---------------------------------------------------------------------------------

def test_crear(api):
    r = _crear(api, nombre="  Mascotas  ", clase="ingreso", color="cat-salud", icono="coins")
    assert r.status_code == 201
    nueva = r.json()
    assert nueva == {"id": nueva["id"], "nombre": "Mascotas", "clase": "ingreso", "color": "cat-salud",
                     "icono": "coins"}
    ids = [c["id"] for c in api.get("/api/categorias", params={"clase": "ingreso"}).json()["categorias"]]
    assert ids[-1] == nueva["id"]


@pytest.mark.parametrize(
    ("datos", "estado", "detalle"),
    [
        ({"nombre": "mercado"}, 400, "Ya hay una categoría de gasto con ese nombre."),
        ({"nombre": "Sin categorizar"}, 400, "Ese nombre lo usa la app; elige otro."),
        ({"nombre": "   "}, 400, "Escribe el nombre de la categoría."),
        ({"color": "cat-mercado", "icono": "shopping-basket"}, 400,
         "Otra categoría ya tiene ese color con ese ícono; cambia uno de los dos."),
        ({"color": "#5A6B1C"}, 422, None),
        ({"icono": "cohete"}, 422, None),
        ({"clase": "ahorro"}, 422, None),
        ({"nombre": 5}, 422, None),
        ({"nombre": "x" * 201}, 422, None),
        ({"extra": True}, 422, None),
    ],
)
def test_crear_no_valida_no_cambia_nada(api, config, datos, estado, detalle):
    antes = _todo(config)
    r = _crear(api, **datos)
    assert r.status_code == estado
    if detalle:
        assert r.json() == {"detalle": detalle}
    assert _todo(config) == antes


# --- Editar --------------------------------------------------------------------------------

def test_renombrar_y_cambiar_color_e_icono(api, config):
    mov = insertar_movimiento(config, categoria_id=ANTOJOS)
    r = api.patch(f"/api/categorias/{ANTOJOS}", json={"nombre": "Dulces"})
    assert r.status_code == 200
    assert r.json() == {"id": ANTOJOS, "nombre": "Dulces", "clase": "gasto", "color": "cat-antojos",
                        "icono": "ice-cream-cone"}
    r = api.patch(f"/api/categorias/{ANTOJOS}", json={"color": "cat-salud", "icono": "coins"})
    assert (r.json()["color"], r.json()["icono"], r.json()["nombre"]) == ("cat-salud", "coins", "Dulces")
    movimiento = api.get("/api/movimientos", params={"mes": "2026-08"}).json()["movimientos"][0]
    assert movimiento["id"] == mov
    assert movimiento["categoria"] == {"id": ANTOJOS, "nombre": "Dulces", "clase": "gasto", "color": "cat-salud",
                                       "icono": "coins"}


@pytest.mark.parametrize(
    ("ruta", "datos", "estado"),
    [
        (f"/api/categorias/{ANTOJOS}", {"nombre": "Mercado"}, 400),
        (f"/api/categorias/{ANTOJOS}", {}, 400),
        (f"/api/categorias/{ANTOJOS}", {"clase": "ingreso"}, 422),  # la clase no se cambia
        (f"/api/categorias/{ANTOJOS}", {"color": "rojo"}, 422),
        ("/api/categorias/999", {"nombre": "Nueva"}, 404),
        ("/api/categorias/0", {"nombre": "Nueva"}, 422),
    ],
)
def test_editar_no_valido_no_cambia_nada(api, config, ruta, datos, estado):
    antes = _todo(config)
    assert api.patch(ruta, json=datos).status_code == estado
    assert _todo(config) == antes


# --- Borrar ----------------------------------------------------------------------------------

def test_borrar_pasa_movimientos_y_reglas(api, config):
    a = insertar_movimiento(config, "2026-08-02T10:00:00", 100, "compra", "HELADERIA INVENTADA")
    b = insertar_movimiento(config, "2026-08-03T10:00:00", 200, "compra", "HELADERIA INVENTADA")
    assert api.put(f"/api/movimientos/{a}/categoria", json={"categoria_id": ANTOJOS, "recordar": True}).status_code == 200
    r = api.delete(f"/api/categorias/{ANTOJOS}", params={"mover_a": 2})
    assert r.status_code == 200
    assert r.json() == {
        "movimientos_movidos": 2,
        "reglas_movidas": 1,
        "destino": {"id": 2, "nombre": "Restaurantes", "clase": "gasto", "color": "cat-restaurantes",
                    "icono": "utensils"},
        "deshacer": None,  # movió movimientos y reglas: sin deshacer (ítem 38)
    }
    movimientos = {m["id"]: m for m in api.get("/api/movimientos", params={"mes": "2026-08"}).json()["movimientos"]}
    assert movimientos[a]["categoria"]["id"] == movimientos[b]["categoria"]["id"] == 2
    assert movimientos[b]["origen_categoria"] == "regla" and movimientos[b]["regla"] is not None
    [regla] = api.get("/api/reglas").json()["reglas"]
    assert regla["categoria"]["id"] == 2
    assert ANTOJOS not in [c["id"] for c in api.get("/api/categorias").json()["categorias"]]
    assert ejecutar_sql(config, "PRAGMA foreign_key_check").fetchall() == []


def test_borrar_una_vacia_sin_destino(api):
    nueva = _crear(api).json()["id"]
    r = api.delete(f"/api/categorias/{nueva}")
    assert r.status_code == 200
    datos = r.json()
    assert set(datos.pop("deshacer")) == {"token", "segundos"}  # vacía: se puede deshacer (ítem 38)
    assert datos == {"movimientos_movidos": 0, "reglas_movidas": 0, "destino": None}


@pytest.mark.parametrize(
    ("categoria", "params", "estado", "detalle"),
    [
        (ANTOJOS, {}, 400, "Elige a qué categoría pasan sus movimientos y reglas."),
        (ANTOJOS, {"mover_a": SUELDO}, 400,
         "Los movimientos y reglas de una categoría de gasto solo pueden pasar a otra categoría de gasto."),
        (SUELDO, {"mover_a": 8}, 400,
         "Los movimientos y reglas de una categoría de ingreso solo pueden pasar a otra categoría de ingreso."),
        (ANTOJOS, {"mover_a": ANTOJOS}, 400, "Elige otra categoría para pasar sus movimientos y reglas."),
        (ANTOJOS, {"mover_a": 999}, 400, "La categoría a la que pasan no existe."),
        (999, {"mover_a": 1}, 404, "La categoría no existe."),
        (ANTOJOS, {"mover_a": 0}, 422, None),
        (ANTOJOS, {"mover_a": "uno"}, 422, None),
    ],
)
def test_borrar_no_valido_no_cambia_nada(api, config, categoria, params, estado, detalle):
    insertar_movimiento(config, categoria_id=ANTOJOS)
    insertar_movimiento(config, tipo="ingreso", descripcion="EMPRESA INVENTADA", categoria_id=SUELDO)
    antes = _todo(config)
    r = api.delete(f"/api/categorias/{categoria}", params=params)
    assert r.status_code == estado
    if detalle:
        assert r.json() == {"detalle": detalle}
    assert _todo(config) == antes


def test_no_se_borra_la_ultima_de_una_clase(api, config):
    assert api.delete(f"/api/categorias/{SUELDO}").status_code == 200
    assert api.delete(f"/api/categorias/{PRESTAMOS}").status_code == 200
    antes = _todo(config)
    r = api.delete(f"/api/categorias/{OTROS_INGRESOS}")
    assert r.status_code == 400
    assert r.json() == {"detalle": "No se puede borrar la última categoría de ingreso: crea otra antes."}
    assert _todo(config) == antes


# --- Ingresos categorizables y reglas -------------------------------------------------------

def test_categorizar_un_ingreso_con_regla_y_verla_en_la_lista_de_reglas(api, config):
    uno = insertar_movimiento(config, "2026-08-02T08:00:00", 480000000, "ingreso", "EMPRESA INVENTADA S.A.S.")
    dos = insertar_movimiento(config, "2026-08-30T08:00:00", 480000000, "ingreso", "Empresa Inventada S.A.S.")
    bandeja = {m["id"]: m for m in api.get("/api/movimientos/sin-categorizar").json()["movimientos"]}
    assert bandeja[uno]["clase_categoria"] == "ingreso"
    assert bandeja[uno]["es_gasto"] is False
    assert bandeja[uno]["regla_posible"] == {"campo": "quien_envia", "texto": "empresa inventada s.a.s."}

    r = api.put(f"/api/movimientos/{uno}/categoria", json={"categoria_id": SUELDO, "recordar": True})
    assert r.status_code == 200
    respuesta = r.json()
    assert respuesta["categorizados"] == 2
    assert respuesta["regla"]["tipo_movimiento"] == "ingreso"
    assert respuesta["regla"]["campo"] == "quien_envia"

    movimiento = {m["id"]: m for m in api.get("/api/movimientos", params={"mes": "2026-08"}).json()["movimientos"]}
    assert movimiento[dos]["origen_categoria"] == "regla"
    assert movimiento[dos]["categoria"]["clase"] == "ingreso"
    assert api.get("/api/movimientos/sin-categorizar").json()["total"] == 0

    [regla] = api.get("/api/reglas").json()["reglas"]
    assert regla == {
        "modo_texto": "exacta", "origen_regla": "todos",
        "id": respuesta["regla"]["id"],
        "tipo_movimiento": "ingreso",
        "campo": "quien_envia",
        "texto": "empresa inventada s.a.s.",
        "monto_centavos": None,
        "condiciones": "texto",
        "categoria": {"id": SUELDO, "nombre": "Sueldo", "clase": "ingreso", "color": "cat-sueldo",
                      "icono": "briefcase"},
        "frase": "Si es un ingreso de «empresa inventada s.a.s.», va a Sueldo",
    }
    assert api.delete(f"/api/reglas/{regla['id']}").status_code == 200
    assert api.get("/api/reglas").json()["reglas"] == []


def test_el_reporte_no_mezcla_ingresos_en_el_gasto_por_categoria(api, config):
    insertar_movimiento(config, "2026-08-02T08:00:00", 480000000, "ingreso", "EMPRESA INVENTADA", categoria_id=SUELDO)
    insertar_movimiento(config, "2026-08-03T08:00:00", 1200000, "compra", "HELADERIA INVENTADA", categoria_id=ANTOJOS)
    datos = api.get("/api/reporte", params={"mes": "2026-08"}).json()
    assert datos["total_gasto_centavos"] == 1200000
    assert [(g["nombre"], g["centavos"]) for g in datos["por_categoria"]] == [("Antojos", 1200000)]
    assert datos["por_categoria"][0]["categoria"]["color"] == "cat-antojos"
    assert datos["total_ingresos_centavos"] == 480000000
    assert (datos["pendientes"], datos["pendientes_centavos"], datos["pendientes_ingresos_centavos"]) == (0, 0, 0)
