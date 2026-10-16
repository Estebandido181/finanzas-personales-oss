"""Contrato HTTP: comunes."""
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from finanzas.modulos.categorias import publico as categorizacion
from finanzas.modulos.saldo import publico as saldo
from finanzas.flujos import reporte


MAXIMO_CENTAVOS = saldo.MAXIMO_CENTAVOS


MAXIMO_ID = 10**18  # por encima no cabe en un entero de SQLite


TipoMovimiento = Literal["compra", "transferencia", "ingreso", "ajuste"]


OrigenMovimiento = Literal["gmail", "manual", "extracto"]


OrigenCategoria = Literal["manual", "regla", "desconocido"]


TipoFiltro = Literal[reporte.TIPOS_FILTRO]


ClaseCategoria = Literal["gasto", "ingreso"]


ColorCategoria = Literal[categorizacion.COLORES_CATEGORIA]


IconoCategoria = Literal[categorizacion.ICONOS_CATEGORIA]


TipoRegla = Literal["compra", "transferencia", "ingreso"]


CampoRegla = Literal["comercio", "cuenta_destino", "quien_envia"]


CondicionRegla = Literal[categorizacion.CONDICIONES]


CentavosNoNegativos = Annotated[StrictInt, Field(ge=0, le=MAXIMO_CENTAVOS)]


CentavosPositivos = Annotated[StrictInt, Field(ge=1, le=MAXIMO_CENTAVOS)]


IdEntrada = Annotated[StrictInt, Field(ge=1, le=MAXIMO_ID)]


Fecha = Annotated[str, Field(json_schema_extra={"format": "date"}, examples=["2026-09-01"])]


FechaHora = Annotated[str, Field(examples=["2026-09-15T14:32:00"])]


Mes = Annotated[str, Field(examples=["2026-09"])]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Error(BaseModel):
    """Cuerpo de todo error de la API. ``detalle`` es un texto para el dueño, sin datos internos."""

    detalle: str


class CampoInvalido(BaseModel):
    ubicacion: list[str | int]
    tipo: str
    mensaje: str


class ErrorValidacion(BaseModel):
    """422: la forma de la petición no es válida. Nunca repite los valores enviados."""

    detalle: str
    campos: list[CampoInvalido]


NombreCategoria = Annotated[StrictStr, Field(max_length=200, examples=["Mascotas"])]


TEXTO_SIN_CONDICION = (
    "Texto exacto (normalizado: minúsculas y espacios simples) del comercio, la cuenta destino "
    "o quien envía; ``null`` si la regla no mira el texto (``condiciones`` = ``monto``)."
)


MONTO_CONDICION = "Monto exacto en centavos; ``null`` si la regla no mira el monto."


MAXIMO_GMAIL_ID = 200
