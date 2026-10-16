"""API: reporte mensual y movimientos del mes (ítem 10). Datos inventados."""

from __future__ import annotations

import pytest

from finanzas.flujos import reporte

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import configurar_saldo, insertar_movimiento


@pytest.fixture
def con_datos(config):
    configurar_saldo(config, centavos=123456789)
    insertar_movimiento(config, "2026-08-02T10:15:00", 6863000, "compra", "COMERCIO INVENTADO ZXQ", categoria_id=1)
    insertar_movimiento(config, "2026-08-03T11:00:00", 600000, "transferencia", "*9999")
    insertar_movimiento(config, "2026-08-04T09:00:00", 16000000, "ingreso", "PERSONA INVENTADA")
    insertar_movimiento(config, "2026-08-05T08:30:00", 2500001, "ingreso", "Efectivo", origen="manual")
    insertar_movimiento(config, "2026-08-06T12:00:00", -45678, "ajuste", "Ajuste de saldo", origen="manual")
    insertar_movimiento(config, "2026-08-31T23:59:59", 1, "compra", "UN CENTAVO", categoria_id=2)
    insertar_movimiento(config, "2026-09-01T00:00:00", 777, "compra", "OTRO MES")
    return config


def test_reporte_del_mes_con_montos_exactos_en_centavos(api, con_datos):
    r = api.get("/api/reporte", params={"mes": "2026-08"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["mes"] == "2026-08"
    assert datos["nombre_mes"] == "agosto de 2026"
    assert datos["mes_anterior"] == "2026-07" and datos["mes_siguiente"] == "2026-09"
    assert datos["es_mes_actual"] is False
    assert datos["total_gasto_centavos"] == 6863000 + 600000 + 1
    assert datos["por_categoria"] == [
        {"nombre": "Mercado", "centavos": 6863000, "porcentaje": 92.0,
         "categoria": {"id": 1, "nombre": "Mercado", "clase": "gasto", "color": "cat-mercado",
                       "icono": "shopping-basket"}},
        {"nombre": "Sin categorizar", "centavos": 600000, "porcentaje": 8.0, "categoria": None},
        {"nombre": "Restaurantes", "centavos": 1, "porcentaje": 0.0,
         "categoria": {"id": 2, "nombre": "Restaurantes", "clase": "gasto", "color": "cat-restaurantes",
                       "icono": "utensils"}},
    ]
    assert sum(g["centavos"] for g in datos["por_categoria"]) == datos["total_gasto_centavos"]
    # La transferencia de agosto y la compra de septiembre, más los dos ingresos
    # de agosto (ítem 15): sin categoría también son pendientes.
    assert datos["pendientes"] == 4
    # Los montos nunca se mezclan: gastos por un lado, ingresos por otro.
    assert datos["pendientes_centavos"] == 600000 + 777
    assert datos["pendientes_ingresos_centavos"] == 16000000 + 2500001
    # Ingresos de Gmail y manuales; el ajuste no cuenta.
    assert datos["total_ingresos_centavos"] == 16000000 + 2500001
    assert datos["saldo_centavos"] == (
        123456789 + 16000000 + 2500001 - 6863000 - 600000 - 45678 - 1 - 777
    )
    for valor in (datos["total_gasto_centavos"], datos["saldo_centavos"],
                  datos["total_ingresos_centavos"], datos["pendientes_centavos"],
                  datos["pendientes_ingresos_centavos"]):
        assert isinstance(valor, int)


def test_reporte_sin_mes_es_el_actual(api):
    datos = api.get("/api/reporte").json()
    assert datos["mes"] == reporte.texto_mes(*reporte.mes_actual())
    assert datos["es_mes_actual"] is True
    assert datos["saldo_centavos"] is None  # sin configurar
    assert datos["por_categoria"] == [] and datos["total_gasto_centavos"] == 0
    assert datos["total_ingresos_centavos"] == 0
    assert (datos["pendientes"], datos["pendientes_centavos"], datos["pendientes_ingresos_centavos"]) == (0, 0, 0)


def test_ingresos_y_pendientes_en_otro_mes(api, con_datos):
    datos = api.get("/api/reporte", params={"mes": "2026-09"}).json()
    assert datos["total_gasto_centavos"] == 777
    assert datos["total_ingresos_centavos"] == 0  # los ingresos son de agosto
    # Los pendientes no dependen del mes pedido.
    assert (datos["pendientes"], datos["pendientes_centavos"], datos["pendientes_ingresos_centavos"]) == (
        4, 600000 + 777, 16000000 + 2500001
    )


def test_pendientes_centavos_coincide_con_la_bandeja(api, con_datos):
    bandeja = api.get("/api/movimientos/sin-categorizar").json()
    datos = api.get("/api/reporte", params={"mes": "2026-08"}).json()
    assert datos["pendientes"] == bandeja["total"] == len(bandeja["movimientos"])
    gastos = [m for m in bandeja["movimientos"] if m["es_gasto"]]
    ingresos = [m for m in bandeja["movimientos"] if m["tipo"] == "ingreso"]
    assert len(gastos) + len(ingresos) == bandeja["total"]
    assert datos["pendientes_centavos"] == sum(m["monto_centavos"] for m in gastos)
    assert datos["pendientes_ingresos_centavos"] == sum(m["monto_centavos"] for m in ingresos)


def test_categorizar_un_ingreso_lo_saca_de_pendientes_sin_tocar_el_gasto(api, con_datos):
    antes = api.get("/api/reporte", params={"mes": "2026-08"}).json()
    bandeja = api.get("/api/movimientos/sin-categorizar").json()["movimientos"]
    ingreso = next(m for m in bandeja if m["descripcion"] == "PERSONA INVENTADA")
    r = api.put(f"/api/movimientos/{ingreso['id']}/categoria", json={"categoria_id": 10})
    assert r.status_code == 200
    despues = api.get("/api/reporte", params={"mes": "2026-08"}).json()
    assert despues["pendientes"] == antes["pendientes"] - 1
    assert despues["pendientes_centavos"] == antes["pendientes_centavos"]
    assert despues["pendientes_ingresos_centavos"] == 2500001
    # El gasto y su reparto por categoría no cambian: un ingreso nunca es gasto.
    assert despues["total_gasto_centavos"] == antes["total_gasto_centavos"]
    assert despues["por_categoria"] == antes["por_categoria"]
    assert despues["total_ingresos_centavos"] == antes["total_ingresos_centavos"]


def test_reporte_sin_sesion_401(cliente):
    r = cliente.get("/api/reporte", params={"mes": "2026-08"})
    assert r.status_code == 401
    assert "total_ingresos_centavos" not in r.text


@pytest.mark.parametrize("mes", ["2026-13", "2026-8", "26-08", "1999-12", "2100-01", "2026-08 ", "２０２６-08", "x"])
def test_mes_invalido_400(api, mes):
    r = api.get("/api/reporte", params={"mes": mes})
    assert r.status_code in (400, 422)
    assert "detalle" in r.json()
    assert api.get("/api/movimientos", params={"mes": mes}).status_code in (400, 422)


def test_limites_del_rango(api):
    assert api.get("/api/reporte", params={"mes": "2000-01"}).json()["mes_anterior"] is None
    assert api.get("/api/reporte", params={"mes": "2099-12"}).json()["mes_siguiente"] is None


def test_movimientos_del_mes(api, con_datos):
    r = api.get("/api/movimientos", params={"mes": "2026-08"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["mes"] == "2026-08"
    movimientos = datos["movimientos"]
    assert [m["fecha_hora"] for m in movimientos] == sorted((m["fecha_hora"] for m in movimientos), reverse=True)
    assert len(movimientos) == 6
    por_descripcion = {m["descripcion"]: m for m in movimientos}
    compra = por_descripcion["COMERCIO INVENTADO ZXQ"]
    assert compra == {
        "id": compra["id"],
        "fecha_hora": "2026-08-02T10:15:00",
        "tipo": "compra",
        "descripcion": "COMERCIO INVENTADO ZXQ",
        "monto_centavos": 6863000,
        "es_gasto": True,
        "categoria": {"id": 1, "nombre": "Mercado", "clase": "gasto", "color": "cat-mercado", "icono": "shopping-basket"},
        "origen": "gmail",
        # Ya categorizado al migrar a la 0004: no se sabe cómo (no se adivina).
        "origen_categoria": "desconocido",
        "regla": None,
        "pendiente": False,
        "descartado": False,
        "puede_descartar": False,
        "motivo_no_descartar": "Hay un ajuste posterior que protege este movimiento.",
        "puede_restaurar": False,
        "motivo_no_restaurar": "Hay un ajuste posterior que protege este movimiento.",
        "categorizable": True,
        "clase_categoria": "gasto",
        "regla_posible": {"campo": "comercio", "texto": "comercio inventado zxq"},
        "reglas_posibles": [
            {"condiciones": "texto", "tipo_movimiento": "compra", "campo": "comercio",
             "texto": "comercio inventado zxq", "monto_centavos": None,
             "frase": "compra en «comercio inventado zxq»"},
        ],
    }
    assert por_descripcion["*9999"]["categoria"] is None
    assert por_descripcion["*9999"]["es_gasto"] is True
    ajuste = por_descripcion["Ajuste de saldo"]
    assert ajuste["monto_centavos"] == -45678 and ajuste["es_gasto"] is False and ajuste["categoria"] is None
    assert por_descripcion["Efectivo"]["origen"] == "manual"
    assert "OTRO MES" not in por_descripcion


def test_movimientos_sin_mes_es_el_actual(api):
    datos = api.get("/api/movimientos").json()
    assert datos == {"mes": reporte.texto_mes(*reporte.mes_actual()), "movimientos": []}


def test_descripcion_con_html_sale_tal_cual_en_json(api, config):
    # La API no escapa HTML (es JSON): el frontend nunca debe insertarlo como HTML.
    insertar_movimiento(config, "2026-08-02T10:00:00", 100, "compra", "<b>COMERCIO</b>")
    r = api.get("/api/movimientos", params={"mes": "2026-08"})
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["movimientos"][0]["descripcion"] == "<b>COMERCIO</b>"
