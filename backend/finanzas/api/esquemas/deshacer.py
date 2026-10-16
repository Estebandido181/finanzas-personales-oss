"""Contrato HTTP: deshacer."""
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StrictStr
from finanzas.api import deshacer
from .comunes import Entrada


class Deshacer(BaseModel):
    """Para deshacer un borrado: se envía ``token`` a ``POST /api/deshacer``.

    ``token`` es opaco: lo borrado se queda en el servidor, el cliente no
    guarda montos ni datos. Vale una sola vez, solo en esta sesión y durante
    ``segundos`` (la app muestra "Deshacer" como mucho ese tiempo).
    """

    token: str
    segundos: int


class DeshacerEntrada(Entrada):
    token: Annotated[StrictStr, Field(min_length=1, max_length=deshacer.MAXIMO_TOKEN)]


class Deshecho(BaseModel):
    """Lo restaurado: ``que`` (``ingreso``, ``regla`` o ``categoria``) y su ``id``.

    El ``id`` es el mismo de antes si seguía libre. ``saldo_centavos``: solo
    al restaurar un ingreso, el saldo justo después (subió exactamente su
    monto); ``null`` en los demás.
    """

    que: Literal["ingreso", "regla", "categoria"]
    id: int
    saldo_centavos: int | None
