"""Ayudas compartidas extraídas de test_avisos_citados_bordes; datos inventados."""

from __future__ import annotations


import base64


from datetime import date


import pytest


from finanzas import db


from finanzas.gmail import CorreoGmail, correo_desde_mensaje


from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar


from tests.soporte.ayudas_db import sql


from tests.soporte.gmail_falso import ENCABEZADOS_LEGITIMOS


AVISOS = {
    "compraste": "Bancolombia: Compraste $87.350,00 en SUPERMERCADO EJEMPLO con tu T.Deb *4321, "
    "el 12/08/2026 a las&nbsp;19:05. Si tienes dudas, encuentranos aqui: 018000000000.",
    "transferiste": "Bancolombia: Transferiste $6,000.00 desde tu cuenta *1234 a la cuenta *3000000000 "
    "el 14/08/26 a las 7:05 p. m. ¿Dudas? Llamanos al 018000000000.",
    "recibiste": "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta "
    "**1234, el 29/08/2026 a las&nbsp;10:00. Si tienes dudas, hablemos: 018000000000.",
    "transferiste_llave": "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 "
    "desde tu cuenta *1234 a NOMBRE DESTINO EJEMPLO el 29/08/26 a las&nbsp;21:28. Con Bre-b es de "
    "una y gratis. Dudas al 018000000000.",
}


FORMATOS = list(AVISOS)


H1 = "<h1>&iexcl;Listo! Todo sali&oacute; bien con tus movimientos</h1>"


ENCABEZADO = "¡Listo! Todo salió bien con tus movimientos"


def _plano(aviso: str) -> str:
    return aviso.replace("&nbsp;", " ")


def _b64(texto: str) -> str:
    return base64.urlsafe_b64encode(texto.encode("utf-8")).decode("ascii").rstrip("=")


def _parte(tipo: str, cuerpo: str) -> dict:
    return {
        "mimeType": tipo,
        "filename": "",
        "headers": [{"name": "Content-Type", "value": f"{tipo}; charset=UTF-8"}],
        "body": {"data": _b64(cuerpo)},
    }


def _mensaje(gmail_id: str, html: str | None = None, plano: str | None = None) -> dict:
    if html is not None and plano is not None:
        payload = {
            "mimeType": "multipart/alternative",
            "filename": "",
            "headers": ENCABEZADOS_LEGITIMOS
            + [{"name": "Content-Type", "value": 'multipart/alternative; boundary="limite"'}],
            "body": {"size": 0},
            "parts": [_parte("text/plain", plano), _parte("text/html", html)],
        }
    else:
        payload = _parte("text/html", html) if html is not None else _parte("text/plain", plano or "")
        payload["headers"] = ENCABEZADOS_LEGITIMOS + payload["headers"]
    return {
        "id": gmail_id,
        "threadId": "hilo-" + gmail_id,
        "labelIds": ["INBOX"],
        "snippet": "",
        "internalDate": "1788102000000",
        "payload": payload,
    }


def _plantilla(cabecera: str, aviso: str, antes: str = "") -> str:
    """HTML con la estructura de los correos reales anonimizados."""
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Alertas y Notificaciones</title>'
        "<style>td { font-family: Arial; }</style></head><body>\n"
        f'{antes}<table width="600" cellpadding="0" cellspacing="0">\n'
        '  <tr><td><img src="https://example.com/logo.png" alt="Bancolombia"></td></tr>\n'
        f"  <tr><td>{cabecera}</td></tr>\n"
        f'  <tr><td><p style="font-size:14px">{aviso}</p></td></tr>\n'
        '  <tr><td style="font-size:11px;color:#777"><p>Pie de página inventado.</p></td></tr>\n'
        "</table></body></html>"
    )


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "citados_bordes.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (100000000, "2026-08-01"),
        )
    yield conexion
    conexion.close()


class _Cliente:
    def __init__(self, correo: CorreoGmail):
        self.correo = correo

    def listar_ids(self, desde: date) -> list[str]:
        return [self.correo.gmail_id]

    def obtener(self, gmail_id: str) -> CorreoGmail:
        return self.correo


def _sincronizar(conn, **cuerpo) -> ResultadoSincronizacion:
    return sincronizar(conn, _Cliente(correo_desde_mensaje(_mensaje("borde-0001", **cuerpo))))


def _movimientos(conn) -> int:
    return sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0]
