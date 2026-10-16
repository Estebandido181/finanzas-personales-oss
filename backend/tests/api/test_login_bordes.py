"""Casos borde del ítem 01: esquema de la base, hash de la contraseña y su CLI.

Lo del login (sesión, bloqueo, cookie manipulada, contraseñas raras) se
retiró con la v1 (ítem 20) y está portado a ``POST /api/sesion`` en
``test_api_sesion_bordes.py``; la protección de rutas, en ``test_web.py``.

Todos los datos son inventados.
"""

import sqlite3

import pytest

from finanzas import db
from finanzas.compartido.config import Config
from finanzas.seguridad import generar_hash
from finanzas.web.app import crear_app
from tests.soporte.ayudas_db import sql

CONTRASENA = "clave-inventada-para-bordes"
SECRETO = "secreto-inventado-para-bordes-de-mas-de-32-caracteres"


@pytest.fixture(scope="module")
def hash_prueba():
    return generar_hash(CONTRASENA)


@pytest.fixture
def config(tmp_path, hash_prueba):
    configuracion = Config(
        db_path=str(tmp_path / "bordes.db"),
        app_password_hash=hash_prueba,
        session_secret=SECRETO,
        cookie_secure=False,
        max_intentos=3,
        bloqueo_minutos=15,
    )
    db.preparar(configuracion.db_path)  # la app exige la base migrada (ítem 22)
    return configuracion


# --- Base de datos --------------------------------------------------------

def _mov(conn, **cambios):
    datos = {
        "fecha_hora": "2026-08-07T16:42:00",
        "monto_centavos": 600000,
        "tipo": "compra",
        "descripcion": "COMERCIO INVENTADO",
        "origen": "manual",
        "gmail_id": None,
    }
    datos.update(cambios)
    columnas = ", ".join(datos)
    marcas = ", ".join("?" for _ in datos)
    with db.transaccion(conn):
        sql(conn, f"INSERT INTO movimientos ({columnas}) VALUES ({marcas})", list(datos.values()))


@pytest.fixture
def conn(tmp_path):
    c = db.conectar(str(tmp_path / "esquema.db"))
    db.inicializar(c)
    yield c
    c.close()


def test_inicializar_sobre_base_con_datos_no_borra_nada(conn):
    mercado = sql(conn, "SELECT id FROM categorias WHERE nombre = 'Mercado'").fetchone()[0]
    _mov(conn, categoria_id=mercado)
    _mov(conn, tipo="ingreso", monto_centavos=123456)
    with db.transaccion(conn):
        sql(
            conn,
            "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'TIENDA X', ?)",
            (mercado,),
        )
        sql(
            conn,
            "INSERT INTO configuracion_saldo VALUES (1, 5000000, '2026-08-01')"
        )
        sql(
            conn,
            "INSERT INTO correos_no_reconocidos VALUES ('id-inventado', '2026-08-02', 'Asunto')"
        )
    ids_antes = [r[0] for r in sql(conn, "SELECT id FROM categorias ORDER BY id")]

    db.inicializar(conn)
    db.inicializar(conn)

    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 2
    assert sql(conn, "SELECT COUNT(*) FROM reglas").fetchone()[0] == 1
    assert sql(conn, "SELECT COUNT(*) FROM configuracion_saldo").fetchone()[0] == 1
    assert sql(conn, "SELECT COUNT(*) FROM correos_no_reconocidos").fetchone()[0] == 1
    assert [r[0] for r in sql(conn, "SELECT id FROM categorias ORDER BY id")] == ids_antes
    fila = sql(conn, "SELECT categoria_id FROM movimientos WHERE tipo='compra'").fetchone()
    assert fila[0] == mercado


def test_arrancar_la_app_sobre_base_con_datos_no_la_borra(config):
    crear_app(config)
    conn = db.conectar(config.db_path)
    try:
        _mov(conn)
    finally:
        conn.close()
    crear_app(config)
    conn = db.conectar(config.db_path)
    try:
        assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 1
        assert sql(conn, "SELECT COUNT(*) FROM categorias").fetchone()[0] == 14
    finally:
        conn.close()


def test_inicializar_reinserta_categoria_fija_borrada(conn):
    with db.transaccion(conn):
        sql(conn, "DELETE FROM categorias WHERE nombre = 'Otros'")
    db.inicializar(conn)
    assert sql(conn, "SELECT COUNT(*) FROM categorias").fetchone()[0] == 14


@pytest.mark.parametrize("monto", [-1, -450000, 1, 99])
def test_ajuste_negativo_o_positivo_permitido(conn, monto):
    _mov(conn, tipo="ajuste", monto_centavos=monto)
    assert sql(conn, "SELECT monto_centavos FROM movimientos").fetchone()[0] == monto


@pytest.mark.parametrize("monto", [0, -1, -600000])
def test_compra_con_cero_o_negativa_rechazada(conn, monto):
    with pytest.raises(sqlite3.IntegrityError):
        _mov(conn, tipo="compra", monto_centavos=monto)


def test_monto_nulo_rechazado(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _mov(conn, monto_centavos=None)


def test_fk_categoria_inexistente_en_movimiento(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _mov(conn, categoria_id=12345)


def test_fk_categoria_inexistente_en_regla(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(
                conn,
                "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'X', 12345)"
            )


def test_no_se_puede_borrar_categoria_en_uso(conn):
    mercado = sql(conn, "SELECT id FROM categorias WHERE nombre = 'Mercado'").fetchone()[0]
    _mov(conn, categoria_id=mercado)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(conn, "DELETE FROM categorias WHERE id = ?", (mercado,))


def test_movimiento_sin_categoria_permitido(conn):
    _mov(conn, categoria_id=None)
    assert sql(conn, "SELECT categoria_id FROM movimientos").fetchone()[0] is None


def test_gmail_id_duplicado_rechazado(conn):
    _mov(conn, origen="gmail", gmail_id="id-correo-inventado")
    with pytest.raises(sqlite3.IntegrityError):
        _mov(conn, origen="gmail", gmail_id="id-correo-inventado")


def test_monto_como_texto_numerico_se_guarda_como_entero(conn):
    # Afinidad INTEGER de SQLite: '100' se convierte a 100.
    _mov(conn, monto_centavos="100")
    tipo = sql(conn, "SELECT typeof(monto_centavos) FROM movimientos").fetchone()[0]
    assert tipo == "integer"


# --- Ronda 2: montos enteros, gmail_id, hash con ":" y Cache-Control -------

@pytest.mark.parametrize("monto", ["abc", 12.5, "12.5", b"\x01", "1e3x"])
def test_monto_no_entero_rechazado(conn, monto):
    with pytest.raises(sqlite3.IntegrityError):
        _mov(conn, monto_centavos=monto)


def test_monto_float_exacto_se_convierte_a_entero(conn):
    # Afinidad INTEGER: 12.0 se guarda como 12 (documentado en db.py).
    _mov(conn, monto_centavos=12.0)
    assert sql(conn, "SELECT typeof(monto_centavos) FROM movimientos").fetchone()[0] == "integer"


def test_monto_booleano_se_guarda_como_entero(conn):
    """DOCUMENTA: sqlite3 envía True como 1; el esquema no puede distinguirlo."""
    _mov(conn, monto_centavos=True)
    assert sql(conn, "SELECT monto_centavos FROM movimientos").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        _mov(conn, monto_centavos=False)  # 0 en una compra


def test_monto_entero_maximo_de_sqlite_aceptado(conn):
    _mov(conn, monto_centavos=2**63 - 1)
    _mov(conn, tipo="ajuste", monto_centavos=-(2**63))
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 2


def test_monto_fuera_de_rango_no_se_guarda(conn):
    with pytest.raises(OverflowError):
        _mov(conn, monto_centavos=2**63)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0


@pytest.mark.parametrize("saldo", ["abc", 10.5])
def test_saldo_inicial_no_entero_rechazado(conn, saldo):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(conn, "INSERT INTO configuracion_saldo VALUES (1, ?, '2026-08-01')", (saldo,))


def test_saldo_inicial_negativo_permitido(conn):
    with db.transaccion(conn):
        sql(conn, "INSERT INTO configuracion_saldo VALUES (1, -250000, '2026-08-01')")


def test_movimiento_gmail_sin_gmail_id_rechazado(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _mov(conn, origen="gmail", gmail_id=None)


def test_regla_con_texto_vacio_rechazada(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', '', 1)")


def _partes_hash(clave=CONTRASENA):
    return generar_hash(clave).split(":")


def test_hash_con_hex_en_mayusculas_sigue_funcionando():
    from finanzas.seguridad import hash_bien_formado, verificar_contrasena

    p = _partes_hash()
    mayus = ":".join(p[:4] + [p[4].upper(), p[5].upper()])
    assert hash_bien_formado(mayus)
    assert verificar_contrasena(CONTRASENA, mayus)
    assert not verificar_contrasena("otra-clave-inventada", mayus)


def test_hash_con_espacios_alrededor_se_acepta_en_config(hash_prueba):
    # Config.desde_entorno hace strip() de la variable: un espacio o salto de
    # línea al pegar el hash no rompe el arranque.
    c = Config.desde_entorno(
        {"APP_PASSWORD_HASH": f"  {hash_prueba}\n", "SESSION_SECRET": SECRETO}
    )
    from finanzas.seguridad import verificar_contrasena

    assert verificar_contrasena(CONTRASENA, c.app_password_hash)


@pytest.mark.parametrize(
    "malo",
    [
        "scrypt$16384$8$1$00$00",  # formato viejo con $
        "SCRYPT:16384:8:1:00:00",
        "scrypt:16384:8:1:00",
        "scrypt:16384:8:1:00:00:00",
        "scrypt:0:8:1:00:00",
        "scrypt:-16384:8:1:00:00",
        "scrypt:+16384:8:1:00:00",
        "scrypt: 16384:8:1:00:00",
        "scrypt:16384:8:1::00",
        "scrypt:16384:8:1:0g:00",
        "scrypt:16384:8:1:abc:00",  # hex de largo impar
        "scrypt:١٦٣٨٤:8:1:00:00",  # dígitos no ASCII
    ],
)
def test_hash_mal_formado_rechazado_al_arrancar(malo):
    from finanzas.compartido.config import ErrorConfiguracion

    with pytest.raises(ErrorConfiguracion, match="APP_PASSWORD_HASH"):
        Config.desde_entorno({"APP_PASSWORD_HASH": malo, "SESSION_SECRET": SECRETO})


def test_error_de_hash_no_muestra_el_valor():
    from finanzas.compartido.config import ErrorConfiguracion

    malo = "scrypt:16384:8:1:deadbeefvalorinventado:00"
    with pytest.raises(ErrorConfiguracion) as error:
        Config.desde_entorno({"APP_PASSWORD_HASH": malo, "SESSION_SECRET": SECRETO})
    assert "deadbeefvalorinventado" not in str(error.value)


def test_cli_rechaza_contrasena_de_11_y_acepta_de_12(monkeypatch, capsys):
    from finanzas import seguridad

    monkeypatch.setattr(seguridad.getpass, "getpass", lambda _="": "a" * 11)
    assert seguridad.main() == 1
    assert "12" in capsys.readouterr().err
    monkeypatch.setattr(seguridad.getpass, "getpass", lambda _="": "a" * 12)
    assert seguridad.main() == 0
    salida = capsys.readouterr().out.strip()
    assert seguridad.verificar_contrasena("a" * 12, salida)
