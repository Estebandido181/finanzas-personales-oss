"""API: categorías, bandeja "Sin categorizar", categorizar y reglas (ítem 10). Datos inventados."""

from __future__ import annotations

import pytest

from finanzas import db

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import ejecutar_sql, insertar_movimiento, insertar_regla


def _categoria_de(config, movimiento_id):
    return ejecutar_sql(config, "SELECT categoria_id FROM movimientos WHERE id = ?", (movimiento_id,)).fetchone()[0]


def _reglas(config):
    return [tuple(f) for f in ejecutar_sql(config, "SELECT campo, texto, categoria_id FROM reglas ORDER BY id").fetchall()]


def test_categorias(api):
    r = api.get("/api/categorias")
    assert r.status_code == 200
    categorias = r.json()["categorias"]
    # Las de gasto (las 8 de la v1 con sus ids, Antojos y las 2 de la 0006),
    # con «Otros» al final como en el prototipo, y luego las de ingreso.
    assert [c["nombre"] for c in categorias] == [
        *db.CATEGORIAS_FIJAS[:7], "Antojos", "Retiro a efectivo", "Pago de tarjeta", "Otros",
        "Sueldo", "Préstamos", "Otros ingresos",
    ]
    assert [c["id"] for c in categorias] == [1, 2, 3, 4, 5, 6, 7, 9, 13, 14, 8, 10, 11, 12]
    assert [c["clase"] for c in categorias] == ["gasto"] * 11 + ["ingreso"] * 3


def test_sin_categorizar(api, config):
    uno = insertar_movimiento(config, "2026-08-02T10:00:00", 6863000, "compra", "TIENDA INVENTADA")
    dos = insertar_movimiento(config, "2026-08-03T10:00:00", 600000, "transferencia", "*9999")
    insertar_movimiento(config, "2026-08-04T10:00:00", 100, "compra", "YA TIENE", categoria_id=2)
    insertar_movimiento(config, "2026-08-05T10:00:00", 100, "ajuste", "Ajuste", origen="manual")
    r = api.get("/api/movimientos/sin-categorizar")
    assert r.status_code == 200
    datos = r.json()
    assert datos["total"] == 2
    # Mismo esquema ``Movimiento`` que la lista del mes (ítem 14).
    comun = {
        "es_gasto": True, "categoria": None, "origen": "gmail", "origen_categoria": None,
        "regla": None, "pendiente": True, "categorizable": True, "clase_categoria": "gasto",
        "descartado": False, "puede_descartar": False,
        "motivo_no_descartar": "Configura el saldo y la fecha de inicio antes de revisar este movimiento.",
        "puede_restaurar": False,
        "motivo_no_restaurar": "Configura el saldo y la fecha de inicio antes de revisar este movimiento.",
    }
    assert datos["movimientos"] == [
        {"id": dos, "fecha_hora": "2026-08-03T10:00:00", "tipo": "transferencia", "descripcion": "*9999",
         "monto_centavos": 600000, **comun, "regla_posible": {"campo": "cuenta_destino", "texto": "*9999"},
         # Ítem 17: una transferencia ofrece por texto, por monto y las dos cosas juntas.
         "reglas_posibles": [
             {"condiciones": "texto", "tipo_movimiento": "transferencia", "campo": "cuenta_destino",
              "texto": "*9999", "monto_centavos": None, "frase": "transferencia a «*9999»"},
             {"condiciones": "monto", "tipo_movimiento": "transferencia", "campo": "cuenta_destino",
              "texto": None, "monto_centavos": 600000, "frase": "transferencia de $6.000"},
             {"condiciones": "texto_y_monto", "tipo_movimiento": "transferencia", "campo": "cuenta_destino",
              "texto": "*9999", "monto_centavos": 600000, "frase": "transferencia a «*9999» por $6.000"},
         ]},
        {"id": uno, "fecha_hora": "2026-08-02T10:00:00", "tipo": "compra", "descripcion": "TIENDA INVENTADA",
         "monto_centavos": 6863000, **comun, "regla_posible": {"campo": "comercio", "texto": "tienda inventada"},
         # Una compra ofrece solo por texto.
         "reglas_posibles": [
             {"condiciones": "texto", "tipo_movimiento": "compra", "campo": "comercio",
              "texto": "tienda inventada", "monto_centavos": None, "frase": "compra en «tienda inventada»"},
         ]},
    ]


def test_la_bandeja_es_de_todos_los_meses_con_el_mismo_esquema_que_el_mes(api, config):
    agosto = insertar_movimiento(config, "2026-08-02T10:00:00", 100, "compra", "TIENDA AGOSTO", origen="manual")
    julio = insertar_movimiento(config, "2026-07-15T10:00:00", 200, "compra", "TIENDA JULIO")
    bandeja = api.get("/api/movimientos/sin-categorizar").json()["movimientos"]
    assert [m["id"] for m in bandeja] == [agosto, julio]
    del_mes = api.get("/api/movimientos", params={"mes": "2026-08"}).json()["movimientos"]
    assert bandeja[0] == del_mes[0]
    assert bandeja[0]["origen"] == "manual"


def test_categorizar_sin_recordar(api, config):
    uno = insertar_movimiento(config, "2026-08-02T10:00:00", 100, "compra", "TIENDA INVENTADA")
    otro = insertar_movimiento(config, "2026-08-03T10:00:00", 200, "compra", "TIENDA INVENTADA")
    r = api.put(f"/api/movimientos/{uno}/categoria", json={"categoria_id": 3})
    assert r.status_code == 200
    assert r.json() == {"categorizados": 1, "regla_guardada": False, "regla": None}
    assert _categoria_de(config, uno) == 3
    assert _categoria_de(config, otro) is None
    assert _reglas(config) == []


def test_categorizar_recordando_aplica_a_los_iguales(api, config):
    uno = insertar_movimiento(config, "2026-08-02T10:00:00", 100, "compra", "Tienda  Inventada")
    otro = insertar_movimiento(config, "2026-08-03T10:00:00", 200, "compra", "TIENDA INVENTADA")
    ya = insertar_movimiento(config, "2026-08-04T10:00:00", 300, "compra", "TIENDA INVENTADA", categoria_id=5)
    r = api.put(f"/api/movimientos/{uno}/categoria", json={"categoria_id": 1, "recordar": True})
    assert r.status_code == 200
    regla_id = ejecutar_sql(config, "SELECT id FROM reglas").fetchone()[0]
    assert r.json() == {
        "categorizados": 2,
        "regla_guardada": True,
        "regla": {"id": regla_id, "tipo_movimiento": "compra", "campo": "comercio", "texto": "tienda inventada",
                  "monto_centavos": None, "condiciones": "texto", "frase": "compra en «tienda inventada»",
                  "modo_texto": "exacta", "origen_regla": "todos"},
    }
    assert (_categoria_de(config, uno), _categoria_de(config, otro), _categoria_de(config, ya)) == (1, 1, 5)
    assert _reglas(config) == [("comercio", "tienda inventada", 1)]
    assert api.get("/api/movimientos/sin-categorizar").json()["total"] == 0


def test_categorizar_movimiento_inexistente_404(api):
    r = api.put("/api/movimientos/999/categoria", json={"categoria_id": 1})
    assert r.status_code == 404
    assert r.json() == {"detalle": "El movimiento no existe."}


def test_categorizar_con_categoria_inexistente_400(api, config):
    uno = insertar_movimiento(config)
    r = api.put(f"/api/movimientos/{uno}/categoria", json={"categoria_id": 99})
    assert r.status_code == 400
    assert r.json() == {"detalle": "La categoría no existe."}
    assert _categoria_de(config, uno) is None


def test_categorizar_un_ingreso_400(api, config):
    uno = insertar_movimiento(config, tipo="ingreso", descripcion="PERSONA INVENTADA")
    r = api.put(f"/api/movimientos/{uno}/categoria", json={"categoria_id": 1})
    assert r.status_code == 400
    assert _categoria_de(config, uno) is None


def test_recordar_sin_descripcion_400(api, config):
    uno = insertar_movimiento(config, descripcion="")
    r = api.put(f"/api/movimientos/{uno}/categoria", json={"categoria_id": 1, "recordar": True})
    assert r.status_code == 400
    assert _categoria_de(config, uno) is None


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"categoria_id": "1"},
        {"categoria_id": 1.0},
        {"categoria_id": True},
        {"categoria_id": 0},
        {"categoria_id": -1},
        {"categoria_id": 10**19},
        {"categoria_id": 1, "recordar": "1"},
        {"categoria_id": 1, "recordar": 1},
        {"categoria_id": 1, "otro": 1},
    ],
)
def test_categorizar_valida_la_forma(api, config, cuerpo):
    uno = insertar_movimiento(config)
    r = api.put(f"/api/movimientos/{uno}/categoria", json=cuerpo)
    assert r.status_code == 422
    assert _categoria_de(config, uno) is None


@pytest.mark.parametrize("ruta", ["abc", "0", "-1", "1.5", "99999999999999999999"])
def test_id_de_movimiento_invalido(api, ruta):
    assert api.put(f"/api/movimientos/{ruta}/categoria", json={"categoria_id": 1}).status_code == 422


def test_listar_reglas(api, config):
    insertar_regla(config, "comercio", "tienda inventada", 1)
    insertar_regla(config, "cuenta_destino", "*9999", 3)
    r = api.get("/api/reglas")
    assert r.status_code == 200
    reglas = r.json()["reglas"]
    assert [(g["tipo_movimiento"], g["campo"], g["texto"], g["categoria"]) for g in reglas] == [
        ("compra", "comercio", "tienda inventada",
         {"id": 1, "nombre": "Mercado", "clase": "gasto", "color": "cat-mercado", "icono": "shopping-basket"}),
        ("transferencia", "cuenta_destino", "*9999",
         {"id": 3, "nombre": "Transporte", "clase": "gasto", "color": "cat-transporte", "icono": "bus"}),
    ]
    assert [g["frase"] for g in reglas] == [
        "Si es una compra en «tienda inventada», va a Mercado",
        "Si es una transferencia a «*9999», va a Transporte",
    ]
    assert all(isinstance(g["id"], int) for g in reglas)


def test_borrar_regla_conserva_las_categorias(api, config):
    uno = insertar_movimiento(config, descripcion="TIENDA INVENTADA", categoria_id=1)
    regla = insertar_regla(config, "comercio", "tienda inventada", 1)
    r = api.delete(f"/api/reglas/{regla}")
    assert r.status_code == 200  # desde el ítem 38, con el token para deshacer
    assert r.json()["id"] == regla
    assert set(r.json()["deshacer"]) == {"token", "segundos"}
    assert _reglas(config) == []
    assert _categoria_de(config, uno) == 1
    assert api.delete(f"/api/reglas/{regla}").status_code == 404


def test_borrar_regla_inexistente(api):
    r = api.delete("/api/reglas/12345")
    assert r.status_code == 404
    assert r.json() == {"detalle": "La regla no existe."}
    assert api.delete("/api/reglas/abc").status_code == 422
