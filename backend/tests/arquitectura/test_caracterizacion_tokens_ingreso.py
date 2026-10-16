"""Caracterización R0 del reinicio; sesiones y datos exclusivamente inventados.

El registro de tokens consumidos vive en memoria. La cookie previa conserva
el token emitido y permite reservarlo tras reiniciar; la posterior lo bloquea.
Esta limitación documentada se conserva durante la reorganización R1.
"""

from copy import deepcopy

import pytest
from starlette.requests import Request

from finanzas.api.tokens_ingreso import Reserva, TokensIngreso, confirmar, emitir, reservar


def _peticion(sesion):
    return Request({"type": "http", "session": deepcopy(sesion)})


@pytest.mark.parametrize(
    ("cookie_posterior", "resultado"),
    [(False, Reserva.OK), (True, Reserva.REPETIDO)],
    ids=["cookie-previa-permite-reservar-tras-reinicio", "cookie-posterior-bloquea-tras-reinicio"],
)
def test_reserva_tras_reinicio_con_cookie_previa_o_posterior(cookie_posterior, resultado):
    peticion = _peticion({})
    token = emitir(peticion)
    cookie_previa = deepcopy(peticion.session)
    registro = TokensIngreso()
    assert reservar(peticion, registro, token) is Reserva.OK
    confirmar(peticion, token)

    # Aun con la cookie previa, el proceso original rechaza un segundo envío.
    assert reservar(_peticion(cookie_previa), registro, token) is Reserva.REPETIDO

    cookie = peticion.session if cookie_posterior else cookie_previa
    registro_reiniciado = TokensIngreso()
    assert reservar(_peticion(cookie), registro_reiniciado, token) is resultado
