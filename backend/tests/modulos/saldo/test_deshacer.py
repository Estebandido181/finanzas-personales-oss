"""Ítem 38: deshacer el borrado de un ingreso manual, una regla o una categoría vacía. Datos inventados."""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.modulos.saldo import politica as saldo_politica

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from finanzas import categorizacion
from finanzas.compartido import hora
from finanzas.api import deshacer

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import CONTRASENA, ClienteApi, configurar_saldo, ejecutar_sql, insertar_movimiento

AHORA = datetime(2026, 9, 15, 12, 0, 0)
RUTA = "/api/deshacer"


# --- El registro en memoria -------------------------------------------------------------------

class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_registro_una_sola_vez_y_vence():
    reloj = Reloj()
    registro = deshacer.RegistroDeshacer(segundos=30, reloj=reloj)
    token = registro.guardar("copia inventada")
    assert registro.tomar(token).copia == "copia inventada"
    assert registro.tomar(token) is None  # una sola vez
    otro = registro.guardar("otra")
    reloj.t += 30
    assert registro.tomar(otro) is None  # vencido
    assert registro.tomar("desconocido") is None


def test_registro_tiene_tope():
    registro = deshacer.RegistroDeshacer()
    tokens = [registro.guardar(i) for i in range(deshacer.MAXIMO_EN_MEMORIA + 5)]
    assert registro.tomar(tokens[0]) is None
    assert registro.tomar(tokens[-1]).copia == deshacer.MAXIMO_EN_MEMORIA + 4


# --- API: ayudas -------------------------------------------------------------------------------

@pytest.fixture
def reloj(monkeypatch):
    class R:
        actual = AHORA

    r = R()
    monkeypatch.setattr(hora, "ahora_colombia", lambda: r.actual)
    return r


@pytest.fixture
def con_saldo(config, reloj):
    configurar_saldo(config, centavos=1_250_000_00, fecha="2026-09-01")
    return config


def _ingreso(api, monto=150_000_37, fecha_hora="2026-09-12T10:00", descripcion="Venta inventada"):
    token = api.get("/api/saldo").json()["token_ingreso"]
    r = api.post("/api/ingresos", json={
        "monto_centavos": monto, "fecha_hora": fecha_hora, "descripcion": descripcion, "token": token,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _huella(config):
    return [tuple(f) for f in ejecutar_sql(config, "SELECT * FROM movimientos ORDER BY id").fetchall()]


def _tabla(config, tabla):
    return [tuple(f) for f in ejecutar_sql(config, f"SELECT * FROM {tabla} ORDER BY id").fetchall()]


def _saldo(api):
    return api.get("/api/saldo").json()["saldo_centavos"]


def _cat(config, nombre):
    return ejecutar_sql(config, "SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]


def _deshacer(api, token):
    return api.post(RUTA, json={"token": token})


# --- Ingreso manual ----------------------------------------------------------------------------

def test_restaurar_ingreso_deja_todo_como_antes(api, con_saldo):
    insertar_movimiento(con_saldo, "2026-09-02T08:00:00", 12_345_67, "compra")
    id_ingreso = _ingreso(api)
    otros = _cat(con_saldo, "Otros ingresos")
    assert api.put(f"/api/movimientos/{id_ingreso}/categoria", json={"categoria_id": otros}).status_code == 200
    antes, saldo_antes = _huella(con_saldo), _saldo(api)

    borrado = api.delete(f"/api/ingresos/{id_ingreso}").json()
    assert borrado["saldo_centavos"] == saldo_antes - 150_000_37
    assert borrado["deshacer"]["segundos"] == deshacer.SEGUNDOS_DESHACER

    r = _deshacer(api, borrado["deshacer"]["token"])
    assert r.status_code == 200, r.text
    assert r.json() == {"que": "ingreso", "id": id_ingreso, "saldo_centavos": saldo_antes}
    assert _huella(con_saldo) == antes  # misma fila: id, fecha, categoría, fecha de registro
    assert _saldo(api) == saldo_antes
    # Sigue siendo borrable, como antes.
    assert api.delete(f"/api/ingresos/{id_ingreso}").status_code == 200


def test_restaurar_dos_veces_no_duplica(api, con_saldo):
    token = api.delete(f"/api/ingresos/{_ingreso(api)}").json()["deshacer"]["token"]
    assert _deshacer(api, token).status_code == 200
    despues = _huella(con_saldo)
    r = _deshacer(api, token)
    assert r.status_code == 410
    assert "Ya no se puede deshacer" in r.json()["detalle"]
    assert _huella(con_saldo) == despues


def test_ajuste_despues_del_borrado_409_y_saldo_sigue_cuadrado(api, con_saldo, reloj):
    token = api.delete(f"/api/ingresos/{_ingreso(api)}").json()["deshacer"]["token"]
    reloj.actual = datetime(2026, 9, 15, 12, 0, 5)
    assert api.post("/api/ajustes", json={"saldo_real_centavos": 1_000_000_00}).json()["registrado"]
    antes = _huella(con_saldo)
    r = _deshacer(api, token)
    assert r.status_code == 409
    assert r.json()["detalle"] == saldo_politica.MENSAJE_RESTAURAR_TRAS_AJUSTE
    assert _huella(con_saldo) == antes
    assert _saldo(api) == 1_000_000_00


def test_importar_despues_del_borrado_409_y_no_se_cuenta_dos_veces(api, con_saldo):
    """Ítem 29: el reporte importado tras borrar trae el depósito sin aviso; restaurar lo duplicaría."""
    from datetime import date

    from finanzas import db, importacion
    from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel

    token = api.delete(f"/api/ingresos/{_ingreso(api)}").json()["deshacer"]["token"]
    conn = db.conectar(con_saldo.db_path)
    try:
        importacion.importar(conn, [MovimientoExcel(date(2026, 9, 12), 150_000_37, "ABONO EJEMPLO")])
    finally:
        conn.close()
    # El saldo se lee de la base: hasta el ítem 30 la API no lista el origen "extracto".
    def saldo_en_base():
        conexion = db.conectar(con_saldo.db_path)
        try:
            return componer_saldo(conexion).saldo_actual()
        finally:
            conexion.close()

    antes, saldo_antes = _huella(con_saldo), saldo_en_base()
    r = _deshacer(api, token)
    assert r.status_code == 409
    assert r.json()["detalle"] == saldo_politica.MENSAJE_RESTAURAR_TRAS_IMPORTAR
    assert _huella(con_saldo) == antes and saldo_en_base() == saldo_antes


def test_ajuste_que_reutiliza_el_id_tambien_409(api, con_saldo, reloj):
    # El ingreso es el último movimiento: SQLite da su id al ajuste siguiente.
    id_ingreso = _ingreso(api, fecha_hora="2026-09-15T12:03")
    token = api.delete(f"/api/ingresos/{id_ingreso}").json()["deshacer"]["token"]
    api.post("/api/ajustes", json={"saldo_real_centavos": 999_00})
    assert ejecutar_sql(con_saldo, "SELECT tipo FROM movimientos WHERE id = ?", (id_ingreso,)).fetchone()[0] == "ajuste"
    assert _deshacer(api, token).status_code == 409


def test_id_ocupado_por_otro_movimiento_restaura_con_id_nuevo(api, con_saldo):
    id_ingreso = _ingreso(api)
    borrado = api.delete(f"/api/ingresos/{id_ingreso}").json()
    compra = insertar_movimiento(con_saldo, "2026-09-13T08:00:00", 5_000_00, "compra")
    assert compra == id_ingreso
    saldo_antes = _saldo(api)
    r = _deshacer(api, borrado["deshacer"]["token"]).json()
    assert r["id"] != id_ingreso
    assert r["saldo_centavos"] == saldo_antes + 150_000_37 == _saldo(api)


def test_fecha_de_inicio_cambiada_409(api, con_saldo):
    token = api.delete(f"/api/ingresos/{_ingreso(api)}").json()["deshacer"]["token"]
    # Sin movimientos, la configuración se puede cambiar.
    assert api.put("/api/saldo/configuracion", json={
        "saldo_inicial_centavos": 1_250_000_00, "fecha_inicio": "2026-09-14",
    }).status_code == 200
    r = _deshacer(api, token)
    assert r.status_code == 409
    assert _huella(con_saldo) == []


def test_categoria_borrada_mientras_tanto_vuelve_sin_categoria(api, con_saldo):
    id_ingreso = _ingreso(api)
    nueva = api.post("/api/categorias", json={
        "nombre": "Ventas inventadas", "clase": "ingreso", "color": "cat-otros", "icono": "coins",
    }).json()["id"]
    api.put(f"/api/movimientos/{id_ingreso}/categoria", json={"categoria_id": nueva})
    token = api.delete(f"/api/ingresos/{id_ingreso}").json()["deshacer"]["token"]
    assert api.delete(f"/api/categorias/{nueva}").status_code == 200
    assert _deshacer(api, token).status_code == 200
    fila = ejecutar_sql(con_saldo, "SELECT categoria_id, origen_categoria, regla_id FROM movimientos").fetchone()
    assert tuple(fila) == (None, None, None)


def test_id_de_categoria_reutilizado_por_otra_409(api, con_saldo):
    id_ingreso = _ingreso(api)
    nueva = api.post("/api/categorias", json={
        "nombre": "Ventas inventadas", "clase": "ingreso", "color": "cat-otros", "icono": "coins",
    }).json()["id"]
    api.put(f"/api/movimientos/{id_ingreso}/categoria", json={"categoria_id": nueva})
    token = api.delete(f"/api/ingresos/{id_ingreso}").json()["deshacer"]["token"]
    assert api.delete(f"/api/categorias/{nueva}").status_code == 200
    otra = api.post("/api/categorias", json={
        "nombre": "Regalos inventados", "clase": "ingreso", "color": "cat-salud", "icono": "coins",
    }).json()["id"]
    assert otra == nueva  # SQLite reutilizó el id de la última
    r = _deshacer(api, token)
    assert r.status_code == 409
    assert r.json()["detalle"] == saldo_politica.MENSAJE_RESTAURAR_CATEGORIA_CAMBIO
    assert _huella(con_saldo) == []


def test_restaura_tambien_columnas_que_la_copia_no_conoce(tmp_path, reloj):
    """Una columna agregada después (como ``estado`` del ítem 29) vuelve igual."""
    from finanzas import db

    conn = db.conectar(str(tmp_path / "columnas.db"))
    db.inicializar(conn)
    try:
        with db.transaccion(conn):
            conn.exec_driver_sql(
                "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, 0, '2026-09-01')"
            )
            conn.exec_driver_sql("ALTER TABLE movimientos ADD COLUMN estado_inventado TEXT")
        id_ingreso = componer_saldo(conn).registrar_ingreso(12_345, datetime(2026, 9, 10, 9, 30), "Venta inventada")
        with db.transaccion(conn):
            conn.exec_driver_sql("UPDATE movimientos SET estado_inventado = 'provisional' WHERE id = ?", (id_ingreso,))
        conn.rollback()
        antes = conn.exec_driver_sql("SELECT * FROM movimientos").fetchall()
        conn.rollback()
        copia, saldo_borrado = componer_saldo(conn).borrar_ingreso_con_copia(id_ingreso)
        assert copia.fila["estado_inventado"] == "provisional"
        assert saldo_borrado == 0
        assert componer_saldo(conn).restaurar_ingreso(copia) == (id_ingreso, 12_345)
        assert conn.exec_driver_sql("SELECT * FROM movimientos").fetchall() == antes
    finally:
        conn.close()


# --- Regla -------------------------------------------------------------------------------------

def test_restaurar_regla_mismos_campos_y_movimientos_vuelven_a_apuntarle(api, config):
    a = insertar_movimiento(config, "2026-08-02T10:00:00", 100, "transferencia", "*5678")
    b = insertar_movimiento(config, "2026-08-03T10:00:00", 100, "transferencia", "*5678")
    transporte = _cat(config, "Transporte")
    r = api.put(f"/api/movimientos/{a}/categoria",
                json={"categoria_id": transporte, "recordar": True, "condiciones": "texto_y_monto"})
    regla_id = r.json()["regla"]["id"]
    reglas_antes, movs_antes = _tabla(config, "reglas"), _huella(config)
    assert ejecutar_sql(config, "SELECT regla_id FROM movimientos WHERE id = ?", (b,)).fetchone()[0] == regla_id

    borrado = api.delete(f"/api/reglas/{regla_id}").json()
    assert borrado["id"] == regla_id
    assert api.get("/api/reglas").json()["reglas"] == []

    r = _deshacer(api, borrado["deshacer"]["token"])
    assert r.json() == {"que": "regla", "id": regla_id, "saldo_centavos": None}
    assert _tabla(config, "reglas") == reglas_antes
    assert _huella(config) == movs_antes


def test_regla_igual_creada_mientras_tanto_409(api, config):
    a = insertar_movimiento(config, "2026-08-02T10:00:00", 100, "compra", "TIENDA INVENTADA")
    regla_id = api.put(f"/api/movimientos/{a}/categoria",
                       json={"categoria_id": 1, "recordar": True}).json()["regla"]["id"]
    token = api.delete(f"/api/reglas/{regla_id}").json()["deshacer"]["token"]
    api.put(f"/api/movimientos/{a}/categoria", json={"categoria_id": 2, "recordar": True})
    antes = _tabla(config, "reglas")
    r = _deshacer(api, token)
    assert r.status_code == 409
    assert "misma" in r.json()["detalle"]
    assert _tabla(config, "reglas") == antes


def test_restaurar_regla_categoria_ya_no_existe(tmp_path):
    from finanzas import db

    conn = db.conectar(str(tmp_path / "r.db"))
    db.inicializar(conn)
    try:
        copia = categorizacion.CopiaRegla(id=1, campo="comercio", texto="tienda", monto_centavos=None,
                                          categoria_id=99999, movimientos=())
        with pytest.raises(categorizacion.RestauracionNoPermitida):
            categorizacion.restaurar_regla(conn, copia)
        # Categoría de otra clase (Sueldo es de ingreso; la regla es de compra).
        sueldo = conn.exec_driver_sql("SELECT id FROM categorias WHERE nombre = 'Sueldo'").scalar()
        with pytest.raises(categorizacion.RestauracionNoPermitida):
            categorizacion.restaurar_regla(conn, copia.__class__(**{**copia.__dict__, "categoria_id": sueldo}))
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM reglas").scalar() == 0
    finally:
        conn.close()


# --- Categoría vacía ---------------------------------------------------------------------------

def _crear_categoria(api, nombre="Mascotas inventadas", color="cat-otros", icono="bus"):
    r = api.post("/api/categorias", json={"nombre": nombre, "clase": "gasto", "color": color, "icono": icono})
    assert r.status_code == 201
    return r.json()["id"]


def test_restaurar_categoria_vacia(api, config):
    nueva = _crear_categoria(api)
    antes = _tabla(config, "categorias")
    [cat] = [c for c in api.get("/api/categorias").json()["categorias"] if c["id"] == nueva]
    assert cat["se_puede_deshacer_borrado"] is True
    token = api.delete(f"/api/categorias/{nueva}").json()["deshacer"]["token"]
    r = _deshacer(api, token)
    assert r.json() == {"que": "categoria", "id": nueva, "saldo_centavos": None}
    assert _tabla(config, "categorias") == antes


def test_categoria_con_movimientos_no_tiene_deshacer(api, config):
    nueva = _crear_categoria(api)
    insertar_movimiento(config, categoria_id=nueva)
    [cat] = [c for c in api.get("/api/categorias").json()["categorias"] if c["id"] == nueva]
    assert cat["se_puede_deshacer_borrado"] is False
    r = api.delete(f"/api/categorias/{nueva}", params={"mover_a": 1})
    assert r.json()["deshacer"] is None


def test_categoria_con_el_mismo_nombre_creada_mientras_tanto_409(api, config):
    nueva = _crear_categoria(api)
    token = api.delete(f"/api/categorias/{nueva}").json()["deshacer"]["token"]
    _crear_categoria(api, color="cat-salud", icono="ticket")
    antes = _tabla(config, "categorias")
    r = _deshacer(api, token)
    assert r.status_code == 409
    assert r.json()["detalle"].startswith("No se puede deshacer: ya hay una categoría")
    assert _tabla(config, "categorias") == antes


# --- Token y seguridad -------------------------------------------------------------------------

@pytest.mark.parametrize("cuerpo, estado", [
    ({"token": "desconocido"}, 410),
    ({"token": ""}, 422),
    ({"token": "x" * (deshacer.MAXIMO_TOKEN + 1)}, 422),
    ({}, 422),
    ({"token": 5}, 422),
    ({"token": "a", "otro": 1}, 422),
])
def test_entradas_invalidas(api, cuerpo, estado):
    assert api.post(RUTA, json=cuerpo).status_code == estado


def test_token_vencido_410(api, config, monkeypatch):
    registro = api.cliente.app.state.deshacer
    reloj = Reloj()
    monkeypatch.setattr(registro, "_reloj", reloj)
    token = api.delete(f"/api/categorias/{_crear_categoria(api)}").json()["deshacer"]["token"]
    reloj.t += deshacer.SEGUNDOS_DESHACER
    assert _deshacer(api, token).status_code == 410


def test_token_de_otra_sesion_410(api, app, config):
    token = api.delete(f"/api/categorias/{_crear_categoria(api)}").json()["deshacer"]["token"]
    with TestClient(app, follow_redirects=False) as otro:
        csrf = otro.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
        assert ClienteApi(otro, csrf).post(RUTA, json={"token": token}).status_code == 410
    # La sesión que borró lo sigue pudiendo usar.
    assert _deshacer(api, token).status_code == 200


def test_exige_sesion_y_csrf(api, config):
    token = api.delete(f"/api/categorias/{_crear_categoria(api)}").json()["deshacer"]["token"]
    antes = _tabla(config, "categorias")
    assert api.post(RUTA, json={"token": token}, headers={"X-CSRF-Token": "inventado"}).status_code == 403
    assert api.cliente.post(RUTA, json={"token": token}).status_code == 403
    api.delete("/api/sesion")
    assert api.cliente.post(RUTA, json={"token": token}, headers={"X-CSRF-Token": api.csrf}).status_code == 401
    assert _tabla(config, "categorias") == antes
