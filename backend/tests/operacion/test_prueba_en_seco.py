"""Prueba en seco del lector (``python -m finanzas.prueba_en_seco``), con Gmail falso.

Todos los datos son inventados.
"""

from __future__ import annotations
from finanzas.modulos.sincronizacion import registro_sqlite

import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from finanzas import db, prueba_en_seco
from finanzas.gmail import CorreoGmail, ErrorAutorizacionGmail
from finanzas.compartido.hora import ZONA_COLOMBIA
from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import LEGITIMO, ClienteFalso

ENCABEZADO = "¡Listo! Todo salió bien con tus movimientos"
COMPRA = (
    "Bancolombia: Compraste $87.350,00 en SUPERMERCADO INVENTADO con tu T.Deb *4321, "
    "el 12/08/2026 a las 19:05. Si tienes dudas, encuentranos aqui."
)
INGRESO = (
    "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA INVENTADA en tu cuenta "
    "**1234, el 29/08/2026 a las 10:00. Si tienes dudas, hablemos."
)
LLAVE = (
    "Bancolombia: TITULAR INVENTADO, transferiste $6,200.00 a la llave 3000000000 desde tu "
    "cuenta *1234 a DESTINO INVENTADO el 29/08/26 a las 21:28. Con Bre-b es de una y gratis."
)
ASUNTO = "Asunto secreto inventado"
DATOS_PRIVADOS = [
    "87.350", "8735000", "160,000", "16000000", "6,200", "SUPERMERCADO", "PERSONA", "TITULAR",
    "DESTINO", "3000000000", "4321", "1234", ASUNTO, "Bancolombia", "$",
]


def _correo(gmail_id: str, texto: str, dia: int, **autenticacion) -> CorreoGmail:
    datos = autenticacion or LEGITIMO
    return CorreoGmail(gmail_id, datetime(2026, 8, dia, 9, 30, tzinfo=ZONA_COLOMBIA), ASUNTO, texto, **datos)


FALSO = {"remitente": "alertas@banco-inventado.example", "autenticacion": ""}


@pytest.fixture
def ruta_db(tmp_path):
    return str(tmp_path / "seco.db")


@pytest.fixture
def base(ruta_db):
    """Base con 3 movimientos de Gmail, 1 manual y 2 no reconocidos (uno falsificado)."""
    conn = db.conectar(ruta_db)
    db.inicializar(conn)
    with db.transaccion(conn):
        sql(conn, "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (100000000, "2026-08-01"))
        sql(conn, "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen) "
                  "VALUES ('2026-08-20T08:00:00', 5000, 'ajuste', 'Ajuste inventado', 'manual')")
    correos = {
        "m-compra": _correo("m-compra", ENCABEZADO + "\n\n" + COMPRA, 12),
        "m-ingreso": _correo("m-ingreso", INGRESO, 29),
        "m-llave": _correo("m-llave", ENCABEZADO + " " + LLAVE, 29),
        "n-otro": _correo("n-otro", "Texto inventado sin aviso.", 15),
        "n-falso": _correo("n-falso", COMPRA, 16, **FALSO),
    }
    resultado = sincronizar(conn, ClienteFalso(correos))
    assert resultado == ResultadoSincronizacion(nuevos=3, no_reconocidos=1, rechazados_autenticacion=1)
    conn.close()
    return correos


def _huella(ruta_db: str) -> tuple[str, list[str]]:
    carpeta = Path(ruta_db).parent
    return hashlib.sha256(Path(ruta_db).read_bytes()).hexdigest(), sorted(p.name for p in carpeta.iterdir())


@pytest.fixture
def entorno(monkeypatch, ruta_db):
    from finanzas.seguridad import generar_hash

    monkeypatch.setenv("APP_PASSWORD_HASH", generar_hash("clave-de-prueba-inventada"))
    monkeypatch.setenv("SESSION_SECRET", "secreto-de-prueba-inventado-de-mas-de-32-caracteres")
    monkeypatch.setenv("DB_PATH", ruta_db)
    monkeypatch.setenv("GMAIL_TOKEN", "/ruta/inventada/token.json")
    monkeypatch.delenv("GMAIL_REMITENTE", raising=False)


def _gmail_de_hoy(base: dict[str, CorreoGmail]) -> dict[str, CorreoGmail]:
    """Lo que "devuelve Gmail" en la prueba en seco: con el lector nuevo, la
    compra se lee igual, el ingreso vuelve citado y la llave sin aviso."""
    return {
        **base,
        "m-ingreso": _correo("m-ingreso", "Reversamos la siguiente transacción: " + INGRESO, 29),
        "m-llave": _correo("m-llave", "Texto inventado sin aviso.", 29),
    }


def test_ids_a_revisar_solo_movimientos_de_gmail(base, ruta_db):
    assert prueba_en_seco.ids_a_revisar(ruta_db, False) == [
        ("m-compra", prueba_en_seco.GRUPO_MOVIMIENTOS),
        ("m-ingreso", prueba_en_seco.GRUPO_MOVIMIENTOS),
        ("m-llave", prueba_en_seco.GRUPO_MOVIMIENTOS),
    ]
    con_no_reconocidos = prueba_en_seco.ids_a_revisar(ruta_db, True)
    assert [i for i, _ in con_no_reconocidos] == ["m-compra", "m-ingreso", "m-llave", "n-otro", "n-falso"]


def test_conteos_correctos(base, ruta_db):
    ids = prueba_en_seco.ids_a_revisar(ruta_db, True)
    cliente = ClienteFalso(_gmail_de_hoy(base), fallan={})
    resultado = prueba_en_seco.revisar(ids, cliente)
    m = resultado.conteos[prueba_en_seco.GRUPO_MOVIMIENTOS]
    n = resultado.conteos[prueba_en_seco.GRUPO_NO_RECONOCIDOS]
    assert (m[prueba_en_seco.RESULTADO_VALIDO], m[prueba_en_seco.RESULTADO_CITADO],
            m[prueba_en_seco.RESULTADO_NO_RECONOCIDO]) == (1, 1, 1)
    assert (n[prueba_en_seco.RESULTADO_NO_RECONOCIDO], n[prueba_en_seco.RESULTADO_RECHAZADO]) == (1, 1)
    assert resultado.detalle == [
        ("2026-08-29 09:30", prueba_en_seco.GRUPO_MOVIMIENTOS, prueba_en_seco.RESULTADO_CITADO),
        ("2026-08-29 09:30", prueba_en_seco.GRUPO_MOVIMIENTOS, prueba_en_seco.RESULTADO_NO_RECONOCIDO),
        ("2026-08-15 09:30", prueba_en_seco.GRUPO_NO_RECONOCIDOS, prueba_en_seco.RESULTADO_NO_RECONOCIDO),
        ("2026-08-16 09:30", prueba_en_seco.GRUPO_NO_RECONOCIDOS, prueba_en_seco.RESULTADO_RECHAZADO),
    ]


def test_comando_no_escribe_y_no_muestra_datos(base, ruta_db, entorno, capsys):
    antes = _huella(ruta_db)
    codigo = prueba_en_seco.main(
        ["--incluir-no-reconocidos"], fabrica_cliente=lambda config: ClienteFalso(_gmail_de_hoy(base))
    )
    assert codigo == 0
    assert _huella(ruta_db) == antes  # mismo contenido y ningún archivo nuevo (journal, wal)

    captura = capsys.readouterr()
    salida = captura.out + captura.err
    assert "Correos revisados: 5." in salida
    assert "movimiento guardado (3): aviso válido 1, citado 1, no reconocido 1, " in salida
    assert "rechazado por remitente o autenticación 1" in salida
    assert "2026-08-29 09:30  movimiento guardado -> citado" in salida
    for dato in DATOS_PRIVADOS:
        assert dato not in salida, dato


def test_sin_la_opcion_solo_revisa_movimientos(base, ruta_db, entorno, capsys):
    assert prueba_en_seco.main([], fabrica_cliente=lambda config: ClienteFalso(base)) == 0
    salida = capsys.readouterr().out
    assert "Correos revisados: 3." in salida
    assert "Todos los correos revisados quedarían como aviso válido." in salida
    assert prueba_en_seco.GRUPO_NO_RECONOCIDOS not in salida


def test_error_al_descargar_codigo_1_y_sin_escribir(base, ruta_db, entorno, capsys):
    antes = _huella(ruta_db)
    correos = {k: v for k, v in base.items() if k != "m-compra"}
    cliente = ClienteFalso(correos, fallan={"m-compra": TimeoutError("detalle con datos inventados $1")})
    assert prueba_en_seco.main([], fabrica_cliente=lambda config: cliente) == 1
    assert _huella(ruta_db) == antes
    salida = capsys.readouterr().out
    assert "sin fecha  movimiento guardado -> error al descargar" in salida
    assert "$" not in salida


def test_autorizacion_revocada_codigo_2(base, ruta_db, entorno):
    class Revocado(ClienteFalso):
        def obtener(self, gmail_id):
            raise ErrorAutorizacionGmail("Token revocado (inventado).")

    antes = _huella(ruta_db)
    assert prueba_en_seco.main([], fabrica_cliente=lambda config: Revocado(base)) == 2
    assert _huella(ruta_db) == antes


def test_base_inexistente_codigo_2_y_no_la_crea(ruta_db, entorno):
    assert prueba_en_seco.main([], fabrica_cliente=lambda config: ClienteFalso({})) == 2
    assert not Path(ruta_db).exists()


def test_falta_configuracion_codigo_2(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    assert prueba_en_seco.main([], fabrica_cliente=lambda config: ClienteFalso({})) == 2


def test_no_llama_a_listar_ni_a_funciones_que_guardan(base, ruta_db, monkeypatch):
    from finanzas import sincronizacion

    def prohibido(*args, **kwargs):
        raise AssertionError("la prueba en seco no debe guardar")

    monkeypatch.setattr(registro_sqlite, "_guardar_movimiento", prohibido)
    monkeypatch.setattr(registro_sqlite, "_guardar_no_reconocido", prohibido)
    cliente = ClienteFalso(_gmail_de_hoy(base))
    prueba_en_seco.revisar(prueba_en_seco.ids_a_revisar(ruta_db, True), cliente)
    assert cliente.llamadas_listar == []
    assert sorted(cliente.llamadas_obtener) == sorted(base)


def test_unidad_systemd_endurecida_y_sin_escritura():
    unidad = (Path(__file__).resolve().parents[3] / "deploy" / "systemd" / "finanzas-prueba-en-seco.service").read_text(
        encoding="utf-8"
    )
    lineas = {linea.strip() for linea in unidad.splitlines()}
    assert "Type=oneshot" in lineas
    assert "EnvironmentFile=/etc/finanzas/finanzas.env" in lineas
    assert "ReadOnlyPaths=/var/lib/finanzas" in lineas
    assert "ProtectSystem=strict" in lineas
    assert "NoNewPrivileges=true" in lineas
    assert "ExecStart=/opt/finanzas/.venv/bin/python -m finanzas.prueba_en_seco --incluir-no-reconocidos" in lineas
    assert not any(linea.startswith("ReadWritePaths") for linea in lineas)
    # El resto del endurecimiento, igual que finanzas-sync.
    sync = (Path(__file__).resolve().parents[3] / "deploy" / "systemd" / "finanzas-sync.service").read_text(encoding="utf-8")
    endurecimiento = sync.split("# --- Endurecimiento", 1)[1].splitlines()[1:]
    for linea in endurecimiento:
        linea = linea.strip()
        if linea and not linea.startswith("#") and not linea.startswith("ReadWritePaths"):
            assert linea in lineas, linea
