"""Fixtures y ayudas compartidas por las pruebas de la API (ítem 10).

Todos los datos son inventados. Uso en un archivo de pruebas::

    from tests.soporte.ayudas_api import *  # noqa: F401,F403  (fixtures: config, fabrica, app, cliente, api)

``api`` es un cliente con sesión iniciada por ``POST /api/sesion`` que añade
solo el encabezado ``X-CSRF-Token`` a lo que cambia datos (``api.post``,
``api.put``, ``api.delete``).
"""

from __future__ import annotations

import secrets
import shutil

import pytest
from fastapi.testclient import TestClient

from finanzas import db
from finanzas.compartido.config import Config
from finanzas import seguridad
from finanzas.web.app import crear_app

from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import ClienteFalso

__all__ = [
    "CONTRASENA",
    "SECRETO",
    "hash_prueba",
    "base_plantilla",
    "hash_barato",
    "config",
    "fabrica",
    "app",
    "cliente",
    "api",
    "Fabrica",
    "ClienteApi",
    "configurar_saldo",
    "insertar_movimiento",
    "insertar_regla",
    "ejecutar_sql",
]

CONTRASENA = "clave-de-prueba-inventada"
SECRETO = "secreto-de-prueba-inventado-de-mas-de-32-caracteres"


class Fabrica:
    """Fábrica de clientes de Gmail falsos que cuenta cuántas veces se usó."""

    def __init__(self, cliente=None, error=None):
        self.cliente = cliente or ClienteFalso()
        self.error = error
        self.llamadas = 0

    def __call__(self):
        self.llamadas += 1
        if self.error:
            raise self.error
        return self.cliente


# Velocidad (ítem 10): cientos de pruebas hacen login. Con los parámetros de
# producción (n=2**14) cada login cuesta decenas de milisegundos, así que
# aquí se usa un hash con n=2**4 **solo para estas pruebas**. Tiene el mismo
# formato y pasa por el mismo ``verificar_contrasena`` (que lee n, r y p del
# propio hash); los parámetros de producción y sus pruebas
# (``tests/modulos/sesion/test_seguridad.py``) no cambian.
N_BARATO = 2**4


def hash_barato(contrasena: str) -> str:
    sal = secrets.token_bytes(seguridad.LARGO_SAL)
    derivada = seguridad._scrypt(contrasena, sal, N_BARATO, 1, 1, seguridad.LARGO_HASH)
    return f"scrypt:{N_BARATO}:1:1:{sal.hex()}:{derivada.hex()}"


@pytest.fixture(scope="session")
def hash_prueba():
    return hash_barato(CONTRASENA)


@pytest.fixture(scope="session")
def base_plantilla(tmp_path_factory):
    """Base migrada una sola vez por sesión; cada prueba trabaja sobre una copia."""
    ruta = tmp_path_factory.mktemp("plantilla-api") / "plantilla.db"
    db.preparar(str(ruta))
    return ruta


@pytest.fixture
def config(tmp_path, hash_prueba, base_plantilla):
    configuracion = Config(
        db_path=str(tmp_path / "api.db"),
        app_password_hash=hash_prueba,
        session_secret=SECRETO,
        cookie_secure=False,
        max_intentos=3,
        bloqueo_minutos=15,
    )
    shutil.copyfile(base_plantilla, configuracion.db_path)
    return configuracion


@pytest.fixture
def fabrica():
    return Fabrica()


@pytest.fixture
def app(config, fabrica):
    return crear_app(config, fabrica_cliente_gmail=fabrica)


@pytest.fixture
def cliente(app):
    with TestClient(app, follow_redirects=False) as c:
        yield c


class ClienteApi:
    """Envoltorio del ``TestClient`` con sesión: añade el token CSRF a lo que cambia datos."""

    def __init__(self, cliente: TestClient, csrf: str) -> None:
        self.cliente = cliente
        self.csrf = csrf

    def _con_csrf(self, kwargs):
        encabezados = dict(kwargs.pop("headers", None) or {})
        encabezados.setdefault("X-CSRF-Token", self.csrf)
        kwargs["headers"] = encabezados
        return kwargs

    def get(self, url, **kwargs):
        return self.cliente.get(url, **kwargs)

    def post(self, url, **kwargs):
        kwargs.setdefault("json", {})
        return self.cliente.post(url, **self._con_csrf(kwargs))

    def put(self, url, **kwargs):
        kwargs.setdefault("json", {})
        return self.cliente.put(url, **self._con_csrf(kwargs))

    def patch(self, url, **kwargs):
        kwargs.setdefault("json", {})
        return self.cliente.patch(url, **self._con_csrf(kwargs))

    def delete(self, url, **kwargs):
        return self.cliente.delete(url, **self._con_csrf(kwargs))


@pytest.fixture
def api(cliente):
    r = cliente.post("/api/sesion", json={"contrasena": CONTRASENA})
    assert r.status_code == 200, r.text
    return ClienteApi(cliente, r.json()["csrf_token"])


def ejecutar_sql(config, texto, parametros=()):
    conn = db.conectar(config.db_path)
    try:
        with db.transaccion(conn):
            resultado = sql(conn, texto, parametros)
        return resultado
    finally:
        conn.close()


def configurar_saldo(config, centavos=100000000, fecha="2026-08-01"):
    ejecutar_sql(
        config,
        "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
        (centavos, fecha),
    )


def insertar_movimiento(
    config,
    fecha_hora="2026-08-10T10:00:00",
    monto=6863000,
    tipo="compra",
    descripcion="COMERCIO INVENTADO",
    categoria_id=None,
    origen="gmail",
    gmail_id=None,
):
    if origen == "gmail" and gmail_id is None:
        gmail_id = f"id-inventado-{fecha_hora}-{monto}-{descripcion}"
    resultado = ejecutar_sql(
        config,
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (fecha_hora, monto, tipo, descripcion, categoria_id, origen, gmail_id if origen == "gmail" else None),
    )
    return resultado.lastrowid


def insertar_regla(config, campo="comercio", texto="comercio inventado", categoria_id=1):
    return ejecutar_sql(
        config,
        "INSERT INTO reglas (campo, texto, categoria_id) VALUES (?, ?, ?)",
        (campo, texto, categoria_id),
    ).lastrowid
