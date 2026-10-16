"""Cliente de Gmail falso y fixtures compartidas por las pruebas (sin red)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from finanzas.gmail import CorreoGmail, correo_desde_mensaje

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "gmail"
ARCHIVOS = {
    "msg-0001": "compraste_html.json",
    "msg-0002": "transferiste_multipart.json",
    # D12 / ítem 09: su aviso es "Recibiste un pago de NOMBRE por $100.000,00 en tu
    # cuenta *1234 ...", una redacción distinta de "Recibiste una transferencia por
    # ...", así que sigue siendo "no reconocido" a propósito.
    "msg-0003": "otro_tipo_no_reconocido.json",
    "msg-0004": "compraste_html_anidado.json",
}


def correo_fixture(gmail_id: str) -> CorreoGmail:
    """``CorreoGmail`` construido desde la respuesta simulada de la API."""
    return correo_desde_mensaje(json.loads((FIXTURES / ARCHIVOS[gmail_id]).read_text(encoding="utf-8")))


class ClienteFalso:
    """``ClienteGmail`` en memoria que registra las llamadas.

    ``fallan`` asocia ids con la excepción que lanza ``obtener`` para ellos.
    """

    def __init__(self, correos: dict[str, CorreoGmail] | None = None, fallan: dict | None = None):
        self.correos = correos if correos is not None else {i: correo_fixture(i) for i in ARCHIVOS}
        self.fallan = fallan or {}
        self.llamadas_listar: list[date] = []
        self.llamadas_obtener: list[str] = []

    def listar_ids(self, desde: date) -> list[str]:
        self.llamadas_listar.append(desde)
        return list(self.correos) + list(self.fallan)

    def obtener(self, gmail_id: str) -> CorreoGmail:
        self.llamadas_obtener.append(gmail_id)
        if gmail_id in self.fallan:
            raise self.fallan[gmail_id]
        return self.correos[gmail_id]


# Encabezados de un correo legítimo (inventados: selector de ejemplo e IP de
# documentación 192.0.2.x), iguales a los de los fixtures.
REMITENTE_OFICIAL = "alertasynotificaciones@an.notificacionesbancolombia.com"
AUTENTICACION_LEGITIMA = (
    "mx.google.com;\r\n       dkim=pass header.i=@notificacionesbancolombia.com header.s=selector-ejemplo "
    "header.b=AbCdEf12;\r\n       spf=pass (google.com: domain of "
    "alertasynotificaciones@an.notificacionesbancolombia.com designates 192.0.2.10 as permitted sender) "
    "smtp.mailfrom=alertasynotificaciones@an.notificacionesbancolombia.com;\r\n       dmarc=pass "
    "(p=REJECT sp=REJECT dis=NONE) header.from=notificacionesbancolombia.com"
)
# Para construir un CorreoGmail legítimo: CorreoGmail(..., **LEGITIMO).
LEGITIMO = {"remitente": REMITENTE_OFICIAL, "autenticacion": AUTENTICACION_LEGITIMA}
# Encabezados para respuestas simuladas de la API (payload["headers"]).
ENCABEZADOS_LEGITIMOS = [
    {"name": "Authentication-Results", "value": AUTENTICACION_LEGITIMA},
    {"name": "From", "value": f"Bancolombia (ejemplo) <{REMITENTE_OFICIAL}>"},
]
