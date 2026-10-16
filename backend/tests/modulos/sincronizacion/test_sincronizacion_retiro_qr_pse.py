"""Ítem 27 (D30): la sincronización con los avisos nuevos y los dos remitentes.

Todo inventado (cajeros, empresas, titulares, llaves, cuentas). Los
encabezados de autenticación son los de ``tests/soporte/gmail_falso.py`` (selector de
ejemplo, IP de documentación) con el subdominio cambiado cuando hace falta.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from finanzas import categorizacion, db, sincronizacion
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import DESCRIPCION_PAGO_QR
from finanzas.gmail import REMITENTE_AYN, REMITENTE_POR_DEFECTO, REMITENTES_OFICIALES, CorreoGmail
from finanzas.compartido.hora import ZONA_COLOMBIA
from finanzas.sincronizacion import ResultadoReproceso, ResultadoSincronizacion, reprocesar, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import AUTENTICACION_LEGITIMA, ClienteFalso
from tests.soporte.sincronizacion_retiro_qr_pse import _autenticacion_de, _otro, _sin_dmarc_pass  # ayudas compartidas

ENCABEZADO = "¡Listo! Todo salió bien con tus movimientos"
RETIRO = ("Bancolombia: Retiraste $50.000,00 en CAJERO EJEMPLO de tu T.Deb **1234 el 05/09/2026 "
          "a las 10:15. Si tienes dudas, llamanos al 000 000 0000.")
QR = ("Bancolombia: NOMBRE COMPLETO DE EJEMPLO pagaste $12,000.00 por codigo QR desde tu cuenta *1234 "
      "a la llave 3000000000 el 10/09/2026 a las 11:20. Si tienes dudas, llamanos al 000 000 0000.")
PSE = ("Bancolombia: Pagaste $350,000.00 a EMPRESA EJEMPLO SAS desde tu producto 1234 el 04/09/2026 "
       "08:30:15. Si tienes dudas, llamanos al 000 000 0000.")
COMPRA = ("Bancolombia: Compraste $87.350,00 en TIENDA EJEMPLO con tu T.Deb *1234, el 03/09/2026 "
          "a las 19:05. Si tienes dudas, llamanos al 000 000 0000.")




AN = {"remitente": REMITENTE_POR_DEFECTO, "autenticacion": _autenticacion_de(REMITENTE_POR_DEFECTO)}
AYN = {"remitente": REMITENTE_AYN, "autenticacion": _autenticacion_de(REMITENTE_AYN)}


def _correo(gmail_id: str, texto: str, dia: int = 5, **origen) -> CorreoGmail:
    return CorreoGmail(gmail_id, datetime(2026, 9, dia, 9, 0, tzinfo=ZONA_COLOMBIA), "Asunto inventado",
                       ENCABEZADO + " " + texto, **(origen or AN))


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "item27.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(conexion, "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
                      "VALUES (1, 100000000, '2026-09-01')")
    yield conexion
    conexion.close()


def _movimientos(conn):
    return [tuple(f) for f in sql(
        conn,
        "SELECT m.gmail_id, m.tipo, m.monto_centavos, m.descripcion, c.nombre, m.origen_categoria, m.regla_id "
        "FROM movimientos m LEFT JOIN categorias c ON c.id = m.categoria_id ORDER BY m.gmail_id",
    ).fetchall()]


def _cat(conn, nombre):
    return sql(conn, "SELECT id FROM categorias WHERE nombre = ? AND clase = 'gasto'", (nombre,)).fetchone()[0]


def _no_reconocidos(conn):
    return sorted(f[0] for f in sql(conn, "SELECT gmail_id FROM correos_no_reconocidos").fetchall())


# --- Los tres avisos llegan bien ----------------------------------------------------------------

def test_lee_los_tres_avisos_de_sus_remitentes(conn):
    cliente = ClienteFalso({
        "r": _correo("r", RETIRO, 5),
        "q": _correo("q", QR, 10),
        "p": _correo("p", PSE, 4, **AYN),
    })
    assert sincronizar(conn, cliente) == ResultadoSincronizacion(nuevos=3)
    assert _movimientos(conn) == [
        ("p", "compra", 35000000, "EMPRESA EJEMPLO SAS", None, None, None),
        ("q", "transferencia", 1200000, DESCRIPCION_PAGO_QR, None, None, None),
        ("r", "compra", 5000000, "CAJERO EJEMPLO", "Retiro a efectivo", None, None),
    ]


def test_un_aviso_del_otro_remitente_tambien_vale(conn):
    # D30: cualquiera de las dos direcciones, con su propio DMARC alineado.
    cliente = ClienteFalso({"r": _correo("r", RETIRO, **AYN), "p": _correo("p", PSE, 4, **AN)})
    assert sincronizar(conn, cliente) == ResultadoSincronizacion(nuevos=2)


def test_categoria_de_retiro_gana_a_una_regla_del_cajero(conn):
    with db.transaccion(conn):
        sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', ?, ?)",
            (categorizacion.normalizar("CAJERO EJEMPLO"), _cat(conn, "Otros")))
    sincronizar(conn, ClienteFalso({"r": _correo("r", RETIRO)}))
    assert _movimientos(conn)[0][4:] == ("Retiro a efectivo", None, None)


def test_sin_la_categoria_de_retiro_aplica_las_reglas(conn):
    with db.transaccion(conn):
        sql(conn, "DELETE FROM categorias WHERE nombre = 'Retiro a efectivo'")
        sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', ?, ?)",
            (categorizacion.normalizar("CAJERO EJEMPLO"), _cat(conn, "Otros")))
    sincronizar(conn, ClienteFalso({"r": _correo("r", RETIRO), "s": _correo("s", RETIRO.replace("CAJERO", "OTRO"))}))
    filas = {f[0]: f[4:6] for f in _movimientos(conn)}
    assert filas == {"r": ("Otros", "regla"), "s": (None, None)}


def test_una_categoria_de_ingreso_con_ese_nombre_no_se_usa(conn):
    with db.transaccion(conn):
        sql(conn, "UPDATE categorias SET nombre = 'Retiro viejo' WHERE nombre = 'Retiro a efectivo'")
        sql(conn, "INSERT INTO categorias (nombre, clase, color, icono) "
                  "VALUES ('Retiro a efectivo', 'ingreso', 'cat-sueldo', 'shapes')")
    sincronizar(conn, ClienteFalso({"r": _correo("r", RETIRO)}))
    assert _movimientos(conn)[0][4] is None


def test_pse_y_qr_usan_las_reglas_como_siempre(conn):
    with db.transaccion(conn):
        sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', ?, ?)",
            (categorizacion.normalizar("EMPRESA EJEMPLO SAS"), _cat(conn, "Pago de tarjeta")))
        sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('cuenta_destino', ?, ?)",
            (categorizacion.normalizar(DESCRIPCION_PAGO_QR), _cat(conn, "Mercado")))
    sincronizar(conn, ClienteFalso({"p": _correo("p", PSE, 4, **AYN), "q": _correo("q", QR, 10)}))
    assert {f[0]: (f[4], f[5]) for f in _movimientos(conn)} == {
        "p": ("Pago de tarjeta", "regla"), "q": ("Mercado", "regla"),
    }


# --- Remitentes y DMARC ----------------------------------------------------------------------



@pytest.mark.parametrize(
    "origen",
    [
        _otro(REMITENTE_AYN.replace("@ayn.", "@xyz.")),           # otro subdominio del banco
        _otro(REMITENTE_AYN.replace("@ayn.", "@")),                # el dominio sin subdominio
        _otro(REMITENTE_AYN.replace("alertasynotificaciones@", "alertas@")),  # otra dirección del subdominio
        _otro("pagos@pse-ejemplo.example"),                        # un tercero (como el aviso de PSE)
        {"remitente": "", "autenticacion": AYN["autenticacion"]},  # sin From o con varios
    ],
)
@pytest.mark.parametrize("texto", [RETIRO, QR, PSE])
def test_cualquier_otra_direccion_no_crea_movimientos(conn, origen, texto):
    resultado = sincronizar(conn, ClienteFalso({"x": _correo("x", texto, **origen)}))
    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert _movimientos(conn) == [] and _no_reconocidos(conn) == ["x"]




@pytest.mark.parametrize("cambio", ["fail", "sin_dmarc", "otro_dominio", "vacio"])
@pytest.mark.parametrize("remitente", REMITENTES_OFICIALES)
@pytest.mark.parametrize("texto", [RETIRO, QR, PSE, COMPRA])
def test_las_dos_direcciones_sin_dmarc_aprobado_no_crean_movimientos(conn, cambio, remitente, texto):
    origen = {"remitente": remitente, "autenticacion": _sin_dmarc_pass(_autenticacion_de(remitente), cambio)}
    resultado = sincronizar(conn, ClienteFalso({"x": _correo("x", texto, **origen)}))
    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert _movimientos(conn) == []


def test_sin_dmarc_aun_con_dkim_pass_no_crea_movimientos(conn):
    # D15: DKIM alineado por sí solo no basta, tampoco para ayn.
    sin_dmarc = _sin_dmarc_pass(AYN["autenticacion"], "sin_dmarc")
    assert "dkim=pass" in sin_dmarc
    resultado = sincronizar(conn, ClienteFalso({"p": _correo("p", PSE, remitente=REMITENTE_AYN, autenticacion=sin_dmarc)}))
    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)


def test_el_reproceso_tampoco_salta_la_verificacion(conn):
    falso = _otro(REMITENTE_AYN.replace("@ayn.", "@xyz."))
    cliente = ClienteFalso({"p": _correo("p", PSE, 4, **falso)})
    sincronizar(conn, cliente)
    assert reprocesar(conn, cliente) == ResultadoReproceso(revisados=1, siguen_sin_reconocerse=1)
    assert _movimientos(conn) == []


def test_los_registros_no_traen_datos_de_los_avisos(conn, caplog):
    caplog.set_level(logging.DEBUG)
    sincronizar(conn, ClienteFalso({
        "r": _correo("r", RETIRO), "q": _correo("q", QR), "p": _correo("p", PSE, 4, **AYN),
        "x": _correo("x", PSE, 4, **_otro("pagos@pse-ejemplo.example")),
    }))
    for dato in ["50.000", "5000000", "12,000", "350,000", "CAJERO", "EMPRESA", "NOMBRE", "3000000000",
                 "Asunto", "pse-ejemplo"]:
        assert dato not in caplog.text, dato


# --- Reprocesar y leer ayn. desde la fecha de inicio sin duplicar -------------------------------

def test_reprocesar_lee_los_retiros_y_qr_que_quedaron_no_reconocidos(conn, monkeypatch):
    correos = {"r": _correo("r", RETIRO), "q": _correo("q", QR, 10), "c": _correo("c", COMPRA, 3)}
    # Como antes del ítem 27: el lector no conocía estos avisos.
    from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor

    monkeypatch.setattr(extractor, "_EXTRACTORES", extractor._EXTRACTORES[:4])
    assert sincronizar(conn, ClienteFalso(correos)) == ResultadoSincronizacion(nuevos=1, no_reconocidos=2)
    monkeypatch.undo()

    assert reprocesar(conn, ClienteFalso(correos)) == ResultadoReproceso(revisados=2, movimientos_creados=2)
    assert [f[:2] + f[4:5] for f in _movimientos(conn)] == [
        ("c", "compra", None), ("q", "transferencia", None), ("r", "compra", "Retiro a efectivo"),
    ]
    assert _no_reconocidos(conn) == []
    # Reprocesar o sincronizar otra vez no duplica nada.
    assert reprocesar(conn, ClienteFalso(correos)) == ResultadoReproceso()
    assert sincronizar(conn, ClienteFalso(correos)) == ResultadoSincronizacion()
    assert len(_movimientos(conn)) == 3


class _GmailPorRemitente(ClienteFalso):
    """Gmail falso que, como el real, devuelve solo los correos de los remitentes que se le piden."""

    def __init__(self, correos, remitentes):
        super().__init__(correos)
        self.remitentes = remitentes

    def listar_ids(self, desde):
        self.llamadas_listar.append(desde)
        return [i for i, c in self.correos.items() if c.remitente in self.remitentes]


def test_tras_desplegar_lee_ayn_desde_la_fecha_de_inicio_una_sola_vez(conn):
    correos = {
        "c": _correo("c", COMPRA, 3),
        "p1": _correo("p1", PSE, 4, **AYN),
        "p2": _correo("p2", PSE.replace("04/09/2026", "20/09/2026"), 20, **AYN),
        "viejo": CorreoGmail("viejo", datetime(2026, 8, 20, 9, 0, tzinfo=ZONA_COLOMBIA), "Asunto inventado",
                             ENCABEZADO + " " + PSE.replace("04/09/2026", "20/08/2026"), **AYN),
    }
    # Antes del ítem 27 solo se consultaba an.: los PSE nunca se pidieron.
    antes = _GmailPorRemitente(correos, {REMITENTE_POR_DEFECTO})
    assert sincronizar(conn, antes, REMITENTE_POR_DEFECTO) == ResultadoSincronizacion(nuevos=1)

    # Con las dos direcciones, la siguiente sincronización normal trae ayn.
    # desde la fecha de inicio (el "viejo" es anterior y se descarta).
    despues = _GmailPorRemitente(correos, set(REMITENTES_OFICIALES))
    assert sincronizar(conn, despues) == ResultadoSincronizacion(nuevos=2)
    assert [f[0] for f in _movimientos(conn)] == ["c", "p1", "p2"]
    assert despues.llamadas_listar[0].isoformat() == "2026-09-01"
    # Y las siguientes no repiten nada ni vuelven a descargar lo registrado.
    otra = _GmailPorRemitente(correos, set(REMITENTES_OFICIALES))
    assert sincronizar(conn, otra) == ResultadoSincronizacion()
    assert otra.llamadas_obtener == ["viejo"]
    assert len(_movimientos(conn)) == 3


def test_el_mismo_correo_listado_por_las_dos_consultas_se_guarda_una_vez(conn):
    class Repetido(ClienteFalso):
        def listar_ids(self, desde):
            return ["p", "p"]

    assert sincronizar(conn, Repetido({"p": _correo("p", PSE, 4, **AYN)})) == ResultadoSincronizacion(nuevos=1)


# --- Revisión del ítem 27: cruce de dominios y mayúsculas --------------------------------------

def _con_header_from(remitente: str, dominio: str) -> dict:
    autenticacion = _autenticacion_de(remitente).replace(
        "header.from=notificacionesbancolombia.com", f"header.from={dominio}"
    )
    assert f"header.from={dominio}" in autenticacion
    return {"remitente": remitente, "autenticacion": autenticacion}


@pytest.mark.parametrize(
    ("remitente", "otro_subdominio"),
    [(REMITENTE_POR_DEFECTO, REMITENTE_AYN), (REMITENTE_AYN, REMITENTE_POR_DEFECTO)],
)
@pytest.mark.parametrize("texto", [RETIRO, PSE])
def test_dmarc_del_otro_subdominio_no_vale(conn, remitente, otro_subdominio, texto):
    # From an. con DMARC header.from=ayn. (y al revés): el DMARC debe estar
    # alineado con el dominio de la dirección que coincidió, no con el de la otra.
    origen = _con_header_from(remitente, otro_subdominio.split("@")[1])
    resultado = sincronizar(conn, ClienteFalso({"x": _correo("x", texto, **origen)}))
    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert _movimientos(conn) == []


@pytest.mark.parametrize("remitente", REMITENTES_OFICIALES)
def test_dmarc_de_su_propio_subdominio_si_vale(conn, remitente):
    origen = _con_header_from(remitente, remitente.split("@")[1])
    assert sincronizar(conn, ClienteFalso({"x": _correo("x", PSE, **origen)})) == ResultadoSincronizacion(nuevos=1)


@pytest.mark.parametrize("remitente", REMITENTES_OFICIALES)
@pytest.mark.parametrize("forma", [str.upper, str.title])
def test_from_en_mayusculas_vale_pero_sigue_exigiendo_dmarc(conn, remitente, forma):
    # Las direcciones no distinguen mayúsculas en el dominio (y el banco no
    # las usa en la parte local): se aceptan, pero con el mismo DMARC.
    bueno = {"remitente": forma(remitente), "autenticacion": _autenticacion_de(remitente)}
    malo = {"remitente": forma(remitente),
            "autenticacion": _sin_dmarc_pass(_autenticacion_de(remitente), "fail")}
    cliente = ClienteFalso({"a": _correo("a", PSE, **bueno), "b": _correo("b", RETIRO, **malo)})
    assert sincronizar(conn, cliente) == ResultadoSincronizacion(nuevos=1, rechazados_autenticacion=1)
    assert [f[0] for f in _movimientos(conn)] == ["a"]


def test_frase_del_banco_con_pagaste_no_crea_movimientos(conn):
    texto = QR.replace("NOMBRE COMPLETO DE EJEMPLO", "Te recordamos que")
    assert sincronizar(conn, ClienteFalso({"x": _correo("x", texto)})) == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == []
