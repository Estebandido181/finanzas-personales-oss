"""Prueba en seco ``--ayn`` (ítem 27): correos del segundo remitente, sin escribir nada.

Todo inventado.
"""

from __future__ import annotations
from finanzas.modulos.sincronizacion import registro_sqlite

import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from finanzas import db, prueba_en_seco
from finanzas.gmail import REMITENTE_AYN, CorreoGmail, ErrorAutorizacionGmail
from finanzas.compartido.hora import ZONA_COLOMBIA
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import ClienteFalso
from tests.soporte.sincronizacion_retiro_qr_pse import AYN, ENCABEZADO, PSE, _otro, _sin_dmarc_pass

DATOS_PRIVADOS = ["350,000", "35000000", "EMPRESA", "Asunto", "1234", "$", "Bancolombia"]


def _correo(gmail_id, texto=PSE, dia=4, mes=9, **origen):
    return CorreoGmail(gmail_id, datetime(2026, mes, dia, 8, 30, tzinfo=ZONA_COLOMBIA), "Asunto inventado",
                       ENCABEZADO + " " + texto, **(origen or AYN))


def _gmail():
    sin_dmarc = {"remitente": REMITENTE_AYN, "autenticacion": _sin_dmarc_pass(AYN["autenticacion"], "fail")}
    return {
        "p1": _correo("p1"),
        "p2": _correo("p2", dia=20),
        "registrado": _correo("registrado", dia=6),
        "otro": _correo("otro", texto="Texto inventado de ayn. sin aviso.", dia=7),
        "falla": _correo("falla", dia=8, **sin_dmarc),
        "tercero": _correo("tercero", dia=9, **_otro("pagos@pse-ejemplo.example")),
        "viejo": _correo("viejo", dia=20, mes=8),
    }


@pytest.fixture
def ruta_db(tmp_path):
    ruta = str(tmp_path / "seco-ayn.db")
    conn = db.conectar(ruta)
    db.inicializar(conn)
    with db.transaccion(conn):
        sql(conn, "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
                  "VALUES (1, 100000000, '2026-09-01')")
        sql(conn, "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
                  "VALUES ('2026-09-06T08:30:00', 100, 'compra', 'X', 'gmail', 'registrado')")
    conn.close()
    return ruta


@pytest.fixture
def entorno(monkeypatch, ruta_db):
    from finanzas.seguridad import generar_hash

    monkeypatch.setenv("APP_PASSWORD_HASH", generar_hash("clave-de-prueba-inventada"))
    monkeypatch.setenv("SESSION_SECRET", "secreto-de-prueba-inventado-de-mas-de-32-caracteres")
    monkeypatch.setenv("DB_PATH", ruta_db)
    monkeypatch.setenv("GMAIL_TOKEN", "/ruta/inventada/token.json")
    monkeypatch.delenv("GMAIL_REMITENTE", raising=False)


def _huella(ruta_db):
    carpeta = Path(ruta_db).parent
    return hashlib.sha256(Path(ruta_db).read_bytes()).hexdigest(), sorted(p.name for p in carpeta.iterdir())


def test_datos_de_la_base_en_solo_lectura(ruta_db):
    antes = _huella(ruta_db)
    fecha, registrados = prueba_en_seco.datos_de_la_base(ruta_db)
    assert fecha.isoformat() == "2026-09-01" and registrados == {"registrado"}
    assert _huella(ruta_db) == antes


def test_revisar_ayn_cuenta_por_resultado_motivo_y_tipo(ruta_db):
    fecha, registrados = prueba_en_seco.datos_de_la_base(ruta_db)
    cliente = ClienteFalso(_gmail())
    r = prueba_en_seco.revisar_ayn(cliente, fecha, registrados)
    c = r.conteos[prueba_en_seco.GRUPO_AYN]
    assert c[prueba_en_seco.RESULTADO_VALIDO] == 3
    assert c[prueba_en_seco.RESULTADO_NO_RECONOCIDO] == 1
    assert c[prueba_en_seco.RESULTADO_RECHAZADO] == 2
    assert c[prueba_en_seco.RESULTADO_ANTERIOR] == 1
    assert r.motivos_rechazo == {"remitente": 1, "sin_pass_alineado": 1}
    assert r.tipos == {"compra": 3}
    assert r.ya_registrados == 1
    assert cliente.llamadas_listar[0].isoformat() == "2026-09-01"


def test_comando_ayn_consulta_solo_ayn_no_escribe_y_no_muestra_datos(ruta_db, entorno, capsys):
    pedidos = []

    def fabrica(config):
        pedidos.append(config.gmail_remitentes)
        return ClienteFalso(_gmail())

    antes = _huella(ruta_db)
    assert prueba_en_seco.main(["--ayn"], fabrica_cliente=fabrica) == 0
    assert _huella(ruta_db) == antes
    assert pedidos == [(REMITENTE_AYN,)]
    salida = capsys.readouterr()
    texto = salida.out + salida.err
    assert "Correos de ayn. en Gmail desde la fecha de inicio: 7 (1 ya registrados en la base)." in texto
    assert "- pasan remitente y DMARC: 4" in texto
    assert "- rechazados por remitente o autenticación: 2 (remitente 1, sin_pass_alineado 1)" in texto
    assert "- se leerían como aviso: 3 (compra 3)" in texto
    assert "2026-09-08 08:30 -> rechazado por remitente o autenticación" in texto
    assert "OJO: hay correos de ayn. rechazados" in texto
    for dato in DATOS_PRIVADOS:
        assert dato not in texto, dato


def test_solo_cuenta_como_pasa_un_correo_de_ayn(ruta_db):
    # Revisión del ítem 27: un correo de la otra dirección oficial (an.), aun
    # con DMARC bien, no prueba nada sobre ayn.: cuenta como rechazado.
    from tests.soporte.sincronizacion_retiro_qr_pse import AN

    fecha, registrados = prueba_en_seco.datos_de_la_base(ruta_db)
    correos = {"de-ayn": _correo("de-ayn"), "de-an": _correo("de-an", dia=5, **AN)}
    r = prueba_en_seco.revisar_ayn(ClienteFalso(correos), fecha, registrados)
    c = r.conteos[prueba_en_seco.GRUPO_AYN]
    assert (c[prueba_en_seco.RESULTADO_VALIDO], c[prueba_en_seco.RESULTADO_RECHAZADO]) == (1, 1)
    assert r.motivos_rechazo == {"remitente": 1}


def test_comando_ayn_todo_bien(ruta_db, entorno, capsys):
    correos = {"p1": _correo("p1"), "p2": _correo("p2", dia=20)}
    assert prueba_en_seco.main(["--ayn"], fabrica_cliente=lambda config: ClienteFalso(correos)) == 0
    assert "Todos los correos de ayn. pasan remitente y DMARC." in capsys.readouterr().out


def test_no_llama_a_funciones_que_guardan(ruta_db, monkeypatch):
    from finanzas import sincronizacion

    def prohibido(*args, **kwargs):
        raise AssertionError("la prueba en seco no debe guardar")

    monkeypatch.setattr(registro_sqlite, "_guardar_movimiento", prohibido)
    monkeypatch.setattr(registro_sqlite, "_guardar_no_reconocido", prohibido)
    fecha, registrados = prueba_en_seco.datos_de_la_base(ruta_db)
    prueba_en_seco.revisar_ayn(ClienteFalso(_gmail()), fecha, registrados)


def test_errores_y_autorizacion(ruta_db, entorno, capsys):
    cliente = ClienteFalso({"p1": _correo("p1")}, fallan={"x": TimeoutError("detalle inventado $1")})
    assert prueba_en_seco.main(["--ayn"], fabrica_cliente=lambda config: cliente) == 1
    assert "$" not in capsys.readouterr().out

    class Revocado(ClienteFalso):
        def listar_ids(self, desde):
            raise ErrorAutorizacionGmail("Token revocado (inventado).")

    assert prueba_en_seco.main(["--ayn"], fabrica_cliente=lambda config: Revocado({})) == 2


def test_sin_fecha_de_inicio_o_sin_base_codigo_2(tmp_path, entorno, monkeypatch, ruta_db):
    conn = db.conectar(ruta_db)
    with db.transaccion(conn):
        sql(conn, "DELETE FROM configuracion_saldo")
    conn.close()
    assert prueba_en_seco.main(["--ayn"], fabrica_cliente=lambda config: ClienteFalso({})) == 2
    monkeypatch.setenv("DB_PATH", str(tmp_path / "no-existe.db"))
    assert prueba_en_seco.main(["--ayn"], fabrica_cliente=lambda config: ClienteFalso({})) == 2
    assert not (tmp_path / "no-existe.db").exists()


def test_ayn_no_se_combina_con_las_otras_opciones(entorno):
    with pytest.raises(SystemExit):
        prueba_en_seco.main(["--ayn", "--mostrar-previo"], fabrica_cliente=lambda config: ClienteFalso({}))
