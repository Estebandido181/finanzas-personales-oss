"""Tokens de un solo uso para registrar ingresos manuales (sin doble envío).

Cada vez que se pide la pantalla de saldo (``GET /api/saldo``) se emite un
token nuevo y se guarda en la sesión. Registrar el ingreso exige un token emitido y sin usar: así un
doble clic o un reenvío no registra el mismo ingreso dos veces. No es la
defensa contra CSRF (esa es ``SameSite``, ``Origin`` y, en la API, el
encabezado ``X-CSRF-Token``).

El registro vive en memoria, en ``app.state.tokens_ingreso``.
"""

from __future__ import annotations

import secrets
from enum import Enum

from starlette.requests import Request

CLAVE_TOKENS_INGRESO = "tokens_ingreso"  # emitidos y aún sin usar, en la sesión
CLAVE_TOKENS_INGRESO_USADOS = "tokens_ingreso_usados"  # ya usados, en la sesión
MAXIMO_TOKENS_SESION = 10  # uno por cada vez que se abre el formulario; se guardan los últimos


from finanzas.infraestructura.tokens_ingreso_ram import TokensIngreso, MAXIMO_TOKENS_MEMORIA


class Reserva(Enum):
    """Resultado de ``reservar``."""

    OK = "ok"  # el token era válido y queda marcado: registrar y luego ``confirmar``
    REPETIDO = "repetido"  # ya se usó (o el otro envío ganó la carrera)
    INVALIDO = "invalido"  # vacío o no emitido en esta sesión


def lista_sesion(request: Request, clave: str) -> list[str]:
    valor = request.session.get(clave)
    return [t for t in valor if isinstance(t, str)] if isinstance(valor, list) else []


def agregar_a_sesion(request: Request, clave: str, token: str) -> None:
    tokens = [t for t in lista_sesion(request, clave) if t != token] + [token]
    request.session[clave] = tokens[-MAXIMO_TOKENS_SESION:]


def emitir(request: Request) -> str:
    """Crea un token nuevo y lo guarda en la sesión."""
    token = secrets.token_urlsafe(16)
    agregar_a_sesion(request, CLAVE_TOKENS_INGRESO, token)
    return token


def reservar(request: Request, registro: TokensIngreso, token: str) -> Reserva:
    """Comprueba el token y, si vale, lo marca como usado (atómico).

    Si después el ingreso no se guarda, quien llama debe ``registro.liberar``.
    """
    if token and (token in lista_sesion(request, CLAVE_TOKENS_INGRESO_USADOS) or registro.usado(token)):
        return Reserva.REPETIDO
    if not token or token not in lista_sesion(request, CLAVE_TOKENS_INGRESO):
        return Reserva.INVALIDO
    if not registro.marcar(token):
        return Reserva.REPETIDO  # el otro envío ganó la carrera
    return Reserva.OK


def confirmar(request: Request, token: str) -> None:
    """El ingreso se guardó: el token pasa de "emitidos" a "usados" en la sesión."""
    request.session[CLAVE_TOKENS_INGRESO] = [
        t for t in lista_sesion(request, CLAVE_TOKENS_INGRESO) if t != token
    ]
    agregar_a_sesion(request, CLAVE_TOKENS_INGRESO_USADOS, token)
