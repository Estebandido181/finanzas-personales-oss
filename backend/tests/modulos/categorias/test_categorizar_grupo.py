"""Ítem 38: categorizar en grupo (agrupado en el servidor y ``categorizar_grupo``). Datos inventados."""

from __future__ import annotations

import pytest

from finanzas import categorizacion, db
from finanzas.categorizacion import (
    ErrorCategorizacion,
    agrupar_pendientes,
    categorizar_grupo,
    clave_grupo,
    leer_clave_grupo,
)

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import CONTRASENA, ClienteApi, ejecutar_sql, insertar_movimiento, insertar_regla
from tests.soporte.ayudas_db import sql

RUTA = "/api/movimientos/categorizar-grupo"


def _fila(id_, tipo, descripcion, monto=1000):
    return {"id": id_, "tipo": tipo, "descripcion": descripcion, "monto_centavos": monto}


# --- Agrupar (función pura) -------------------------------------------------------------------

def test_agrupa_con_la_misma_normalizacion_de_las_reglas():
    filas = [
        _fila(5, "compra", "TIENDA  INVENTADA", 1500),
        _fila(4, "compra", "tienda inventada​", 2500),
        _fila(3, "compra", "Tienda Inventada", 1000),
        _fila(2, "compra", "OTRA TIENDA", 700),
    ]
    [grupo] = agrupar_pendientes(filas)
    assert grupo.clave == "compra:tienda inventada"
    assert grupo.tipo == "compra"
    assert grupo.descripcion == "TIENDA  INVENTADA"  # la del más reciente, tal cual
    assert grupo.clase_categoria == "gasto"
    assert (grupo.cuantos, grupo.suma_centavos, grupo.ids) == (3, 5000, (5, 4, 3))
    assert grupo.regla == categorizacion.CondicionesRegla("comercio", "tienda inventada", None)
    # La regla ofrecida es la misma que "recordar" por texto con cualquiera de ellos.
    for fila in filas[:3]:
        assert categorizacion.regla_posible(fila["tipo"], fila["descripcion"]) == ("comercio", grupo.regla.texto)


def test_un_movimiento_solo_no_es_grupo():
    assert agrupar_pendientes([_fila(1, "compra", "UNICA"), _fila(2, "compra", "OTRA")]) == []
    assert agrupar_pendientes([]) == []


def test_nunca_mezcla_gastos_con_ingresos_ni_compras_con_transferencias():
    filas = [
        _fila(1, "compra", "NOMBRE EJEMPLO"),
        _fila(2, "transferencia", "NOMBRE EJEMPLO"),
        _fila(3, "ingreso", "NOMBRE EJEMPLO"),
        _fila(4, "ingreso", "nombre ejemplo"),
        _fila(5, "transferencia", "nombre  ejemplo"),
    ]
    grupos = {g.clave: g for g in agrupar_pendientes(filas)}
    assert set(grupos) == {"ingreso:nombre ejemplo", "transferencia:nombre ejemplo"}
    assert grupos["ingreso:nombre ejemplo"].ids == (3, 4)
    assert grupos["ingreso:nombre ejemplo"].clase_categoria == "ingreso"
    assert grupos["ingreso:nombre ejemplo"].regla.campo == "quien_envia"
    assert grupos["transferencia:nombre ejemplo"].regla.campo == "cuenta_destino"


def test_sin_descripcion_ni_ajustes_no_se_agrupan():
    filas = [
        _fila(1, "compra", ""), _fila(2, "compra", "   "),
        _fila(3, "ajuste", "Ajuste de saldo"), _fila(4, "ajuste", "Ajuste de saldo"),
    ]
    assert agrupar_pendientes(filas) == []


def test_orden_del_mas_numeroso_y_luego_el_mas_reciente():
    filas = [
        _fila(9, "compra", "B"), _fila(8, "compra", "A"), _fila(7, "compra", "C"),
        _fila(6, "compra", "C"), _fila(5, "compra", "A"), _fila(4, "compra", "C"), _fila(3, "compra", "B"),
    ]
    assert [g.clave for g in agrupar_pendientes(filas)] == ["compra:c", "compra:b", "compra:a"]


@pytest.mark.parametrize(
    "clave",
    ["", "compra", "compra:", ":texto", "ajuste:texto", "otro:texto", "compra:TEXTO", "compra: texto", 7],
)
def test_clave_invalida(clave):
    with pytest.raises(ErrorCategorizacion):
        leer_clave_grupo(clave)


def test_clave_ida_y_vuelta_con_dos_puntos_en_el_texto():
    clave = clave_grupo("transferencia", "Pago: NOMBRE")
    assert clave == "transferencia:pago: nombre"
    assert leer_clave_grupo(clave) == ("transferencia", "pago: nombre")
    assert clave_grupo("ajuste", "Ajuste") is None


# --- categorizar_grupo (con base) -------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "grupo.db"))
    db.inicializar(conexion)
    yield conexion
    conexion.close()


def _cat(conn, nombre):
    return sql(conn, "SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]


def _mov(conn, tipo="compra", descripcion="TIENDA INVENTADA", monto=1000, categoria_id=None, origen="gmail"):
    with db.transaccion(conn):
        n = sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0]
        return sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"2026-09-{n + 1:02d}T10:00:00", monto, tipo, descripcion, categoria_id, origen,
             f"id-inventado-{n}" if origen == "gmail" else None),
        ).lastrowid


def _estado(conn, id_):
    return tuple(
        sql(conn, "SELECT categoria_id, origen_categoria, regla_id FROM movimientos WHERE id = ?", (id_,)).fetchone()
    )


def test_categoriza_todos_y_crea_la_regla(conn):
    mercado = _cat(conn, "Mercado")
    ids = [_mov(conn, descripcion=d) for d in ("TIENDA INVENTADA", "tienda inventada", "Tienda  Inventada")]
    otro = _mov(conn, descripcion="OTRA TIENDA")
    asignacion = categorizar_grupo(conn, "compra:tienda inventada", ids, mercado)
    assert asignacion.total == 3
    regla = sql(conn, "SELECT campo, texto, monto_centavos, categoria_id FROM reglas WHERE id = ?",
                (asignacion.regla_id,)).fetchone()
    assert tuple(regla) == ("comercio", "tienda inventada", None, mercado)
    for id_ in ids:
        assert _estado(conn, id_) == (mercado, "manual", None)
    assert _estado(conn, otro) == (None, None, None)


def test_el_que_ya_no_esta_pendiente_no_se_toca_y_no_cuenta(conn):
    mercado, compras = _cat(conn, "Mercado"), _cat(conn, "Compras")
    a, b, c = (_mov(conn) for _ in range(3))
    with db.transaccion(conn):
        sql(conn, "UPDATE movimientos SET categoria_id = ?, origen_categoria = 'manual' WHERE id = ?", (compras, b))
    asignacion = categorizar_grupo(conn, "compra:tienda inventada", [a, b, c, 999], mercado)
    assert asignacion.total == 2
    assert _estado(conn, b) == (compras, "manual", None)
    assert _estado(conn, a)[0] == _estado(conn, c)[0] == mercado


def test_ids_de_otro_grupo_no_se_tocan(conn):
    mercado = _cat(conn, "Mercado")
    a, b = _mov(conn), _mov(conn)
    otro = _mov(conn, descripcion="OTRA TIENDA")
    transferencia = _mov(conn, tipo="transferencia", descripcion="TIENDA INVENTADA")
    asignacion = categorizar_grupo(conn, "compra:tienda inventada", [a, b, otro, transferencia], mercado)
    assert asignacion.total == 2
    assert _estado(conn, otro)[0] is None
    assert _estado(conn, transferencia)[0] is None


def test_alcanza_a_los_iguales_que_llegaron_despues_por_regla(conn):
    mercado = _cat(conn, "Mercado")
    a, b = _mov(conn), _mov(conn)
    nuevo = _mov(conn)  # llegó después de abrir la bandeja: no viene en ids
    asignacion = categorizar_grupo(conn, "compra:tienda inventada", [a, b], mercado)
    assert asignacion.total == 3
    assert _estado(conn, nuevo) == (mercado, "regla", asignacion.regla_id)


def test_si_ninguno_sigue_pendiente_no_cambia_nada(conn):
    mercado, compras = _cat(conn, "Mercado"), _cat(conn, "Compras")
    a = _mov(conn, categoria_id=compras)
    asignacion = categorizar_grupo(conn, "compra:tienda inventada", [a, 12345], mercado)
    assert (asignacion.total, asignacion.regla_id) == (0, None)
    assert sql(conn, "SELECT COUNT(*) FROM reglas").fetchone()[0] == 0


def test_regla_existente_pasa_a_la_nueva_categoria(conn):
    mercado, compras = _cat(conn, "Mercado"), _cat(conn, "Compras")
    with db.transaccion(conn):
        vieja = sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'tienda inventada', ?)",
                    (compras,)).lastrowid
    a, b = _mov(conn), _mov(conn)
    asignacion = categorizar_grupo(conn, "compra:tienda inventada", [a, b], mercado)
    assert asignacion.regla_id == vieja
    assert sql(conn, "SELECT categoria_id FROM reglas WHERE id = ?", (vieja,)).fetchone()[0] == mercado
    assert sql(conn, "SELECT COUNT(*) FROM reglas").fetchone()[0] == 1


def test_ingresos_con_categoria_de_ingreso(conn):
    sueldo = _cat(conn, "Sueldo")
    a = _mov(conn, tipo="ingreso", descripcion="EMPRESA EJEMPLO")
    b = _mov(conn, tipo="ingreso", descripcion="empresa ejemplo", origen="manual")
    asignacion = categorizar_grupo(conn, "ingreso:empresa ejemplo", [a, b], sueldo)
    assert asignacion.total == 2
    assert sql(conn, "SELECT campo FROM reglas").fetchone()[0] == "quien_envia"


@pytest.mark.parametrize(
    "clave, nombre",
    [("compra:tienda inventada", "Sueldo"), ("ingreso:empresa ejemplo", "Mercado")],
)
def test_categoria_de_otra_clase_no_cambia_nada(conn, clave, nombre):
    a = _mov(conn, tipo=clave.split(":")[0], descripcion=clave.split(":")[1])
    antes = sql(conn, "SELECT * FROM movimientos").fetchall()
    with pytest.raises(ErrorCategorizacion):
        categorizar_grupo(conn, clave, [a], _cat(conn, nombre))
    assert sql(conn, "SELECT * FROM movimientos").fetchall() == antes
    assert sql(conn, "SELECT COUNT(*) FROM reglas").fetchone()[0] == 0


def test_errores_de_entrada(conn):
    mercado = _cat(conn, "Mercado")
    with pytest.raises(ErrorCategorizacion, match="no existe"):
        categorizar_grupo(conn, "compra:tienda inventada", [1], 99999)
    with pytest.raises(ErrorCategorizacion):
        categorizar_grupo(conn, "compra:tienda inventada", [], mercado)
    with pytest.raises(ErrorCategorizacion):
        categorizar_grupo(conn, "compra:TIENDA", [1], mercado)
    with pytest.raises(ErrorCategorizacion):
        categorizar_grupo(conn, "compra:x", list(range(1, categorizacion.MAXIMO_IDS_GRUPO + 2)), mercado)


def test_todo_o_nada_si_falla_a_mitad(conn, monkeypatch):
    mercado = _cat(conn, "Mercado")
    a, b = _mov(conn), _mov(conn)

    def falla(*_args, **_kwargs):
        raise RuntimeError("fallo inventado")

    from finanzas.modulos.categorias.asignacion import AsignarCategorias
    monkeypatch.setattr(AsignarCategorias, "aplicar_a_pendientes", falla)
    with pytest.raises(RuntimeError):
        categorizar_grupo(conn, "compra:tienda inventada", [a, b], mercado)
    assert _estado(conn, a) == _estado(conn, b) == (None, None, None)
    assert sql(conn, "SELECT COUNT(*) FROM reglas").fetchone()[0] == 0


# --- API ---------------------------------------------------------------------------------------

def _cat_api(config, nombre):
    return ejecutar_sql(config, "SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]


def test_bandeja_trae_grupos(api, config):
    a = insertar_movimiento(config, fecha_hora="2026-08-10T10:00:00", monto=1000, descripcion="TIENDA INVENTADA")
    b = insertar_movimiento(config, fecha_hora="2026-08-11T10:00:00", monto=2050, descripcion="tienda inventada")
    insertar_movimiento(config, fecha_hora="2026-08-12T10:00:00", monto=300, descripcion="UNICA INVENTADA")
    c = insertar_movimiento(config, fecha_hora="2026-08-13T10:00:00", monto=40000, tipo="ingreso",
                            descripcion="PERSONA EJEMPLO")
    d = insertar_movimiento(config, fecha_hora="2026-08-14T10:00:00", monto=50000, tipo="ingreso",
                            descripcion="Persona Ejemplo")
    datos = api.get("/api/movimientos/sin-categorizar").json()
    assert datos["total"] == 5
    grupos = {g["clave"]: g for g in datos["grupos"]}
    assert set(grupos) == {"compra:tienda inventada", "ingreso:persona ejemplo"}
    compra = grupos["compra:tienda inventada"]
    assert compra == {
        "clave": "compra:tienda inventada",
        "tipo": "compra",
        "descripcion": "tienda inventada",
        "clase_categoria": "gasto",
        "es_gasto": True,
        "cuantos": 2,
        "suma_centavos": 3050,
        "ids": [b, a],
        "regla": {
            "condiciones": "texto",
            "tipo_movimiento": "compra",
            "campo": "comercio",
            "texto": "tienda inventada",
            "monto_centavos": None,
            "frase": "compra en «tienda inventada»",
        },
    }
    ingreso = grupos["ingreso:persona ejemplo"]
    assert (ingreso["es_gasto"], ingreso["clase_categoria"], ingreso["suma_centavos"], ingreso["ids"]) == (
        False, "ingreso", 90000, [d, c],
    )


def test_bandeja_vacia_sin_grupos(api):
    assert api.get("/api/movimientos/sin-categorizar").json()["grupos"] == []


def test_api_categorizar_grupo(api, config):
    ids = [insertar_movimiento(config, fecha_hora=f"2026-08-1{i}T10:00:00", descripcion="TIENDA INVENTADA")
           for i in range(3)]
    grupo = api.get("/api/movimientos/sin-categorizar").json()["grupos"][0]
    mercado = _cat_api(config, "Mercado")
    r = api.post(RUTA, json={"clave": grupo["clave"], "ids": grupo["ids"], "categoria_id": mercado})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["categorizados"] == 3
    assert datos["regla_guardada"] is True
    assert datos["regla"]["texto"] == "tienda inventada"
    assert datos["regla"]["frase"] == "compra en «tienda inventada»"
    bandeja = api.get("/api/movimientos/sin-categorizar").json()
    assert bandeja["total"] == 0 and bandeja["grupos"] == []
    filas = ejecutar_sql(config, "SELECT categoria_id, origen_categoria FROM movimientos ORDER BY id").fetchall()
    assert [tuple(f) for f in filas] == [(mercado, "manual")] * len(ids)
    reporte = api.get("/api/reporte?mes=2026-08").json()
    assert reporte["pendientes"] == 0


def test_api_dos_veces_la_segunda_no_cambia_nada(api, config):
    ids = [insertar_movimiento(config, fecha_hora=f"2026-08-1{i}T10:00:00") for i in range(2)]
    cuerpo = {"clave": "compra:comercio inventado", "ids": ids, "categoria_id": _cat_api(config, "Mercado")}
    assert api.post(RUTA, json=cuerpo).json()["categorizados"] == 2
    assert api.post(RUTA, json=cuerpo).json() == {"categorizados": 0, "regla_guardada": False, "regla": None}


@pytest.mark.parametrize(
    "cuerpo, estado",
    [
        ({"clave": "compra:TIENDA", "ids": [1], "categoria_id": 1}, 400),
        ({"clave": "ajuste:ajuste de saldo", "ids": [1], "categoria_id": 1}, 400),
        ({"clave": "compra:tienda", "ids": [1], "categoria_id": 999999}, 400),
        ({"clave": "compra:tienda", "ids": [], "categoria_id": 1}, 422),
        ({"clave": "compra:tienda", "ids": [0], "categoria_id": 1}, 422),
        ({"clave": "compra:tienda", "ids": ["1"], "categoria_id": 1}, 422),
        ({"clave": "compra:tienda", "ids": [1]}, 422),
        ({"clave": "compra:tienda", "ids": [1], "categoria_id": 1, "otro": 1}, 422),
        ({"clave": "c" * 1001, "ids": [1], "categoria_id": 1}, 422),
    ],
)
def test_api_errores(api, cuerpo, estado):
    assert api.post(RUTA, json=cuerpo).status_code == estado


def test_api_categoria_de_otra_clase_400(api, config):
    ids = [insertar_movimiento(config, fecha_hora=f"2026-08-1{i}T10:00:00") for i in range(2)]
    r = api.post(RUTA, json={"clave": "compra:comercio inventado", "ids": ids,
                             "categoria_id": _cat_api(config, "Sueldo")})
    assert r.status_code == 400
    assert "gasto" in r.json()["detalle"]


def test_api_exige_sesion_y_csrf(cliente, api, config):
    ids = [insertar_movimiento(config, fecha_hora=f"2026-08-1{i}T10:00:00") for i in range(2)]
    cuerpo = {"clave": "compra:comercio inventado", "ids": ids, "categoria_id": _cat_api(config, "Mercado")}
    assert api.post(RUTA, json=cuerpo, headers={"X-CSRF-Token": "token-inventado"}).status_code == 403
    assert api.cliente.post(RUTA, json=cuerpo).status_code == 403  # sin encabezado
    api.delete("/api/sesion")
    assert api.cliente.post(RUTA, json=cuerpo, headers={"X-CSRF-Token": api.csrf}).status_code == 401
    pendientes = ejecutar_sql(config, "SELECT COUNT(*) FROM movimientos WHERE categoria_id IS NULL").fetchone()[0]
    assert pendientes == 2


def test_api_regla_existente_para_otro_texto_no_interfiere(api, config):
    insertar_regla(config, texto="otra tienda", categoria_id=_cat_api(config, "Compras"))
    ids = [insertar_movimiento(config, fecha_hora=f"2026-08-1{i}T10:00:00") for i in range(2)]
    r = api.post(RUTA, json={"clave": "compra:comercio inventado", "ids": ids,
                             "categoria_id": _cat_api(config, "Mercado")})
    assert r.json()["categorizados"] == 2
    assert ejecutar_sql(config, "SELECT COUNT(*) FROM reglas").fetchone()[0] == 2
