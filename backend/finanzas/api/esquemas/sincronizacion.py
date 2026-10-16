"""Contrato HTTP: sincronizacion."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from .comunes import FechaHora


class Contadores(BaseModel):
    nuevos: int
    duplicados: int
    no_reconocidos: int
    errores: int
    rechazados_autenticacion: int


class ResultadoSincronizacion(BaseModel):
    """Una sincronización terminada.

    ``estado``: ``ok``; ``con_errores`` (algunos correos fallaron y se
    reintentan en la siguiente); ``fallida`` (no se completó: ``codigo_error``
    dice por qué y ``contadores`` es ``null``). ``origen``: ``web`` (botón) o
    ``comando`` (temporizador). ``mensaje`` es un texto para el dueño.
    """

    terminada_en: FechaHora
    estado: Literal["ok", "con_errores", "fallida"]
    origen: Literal["web", "comando"]
    contadores: Contadores | None
    codigo_error: (
        Literal["sin_fecha_inicio", "gmail_no_configurado", "autorizacion_gmail", "error_inesperado"]
        | None
    )
    mensaje: str


class EstadoSincronizacion(BaseModel):
    """``en_curso`` solo ve las lanzadas desde la web (el botón).

    ``ultima_correcta_en``: cuándo terminó la última sincronización que no
    quedó ``fallida`` (``ok`` o ``con_errores``), aunque la más reciente haya
    fallado. Igual a ``ultima.terminada_en`` si la última fue correcta;
    ``null`` si nunca hubo una correcta o no se sabe (la base se migró con
    una fallida guardada).
    """

    en_curso: bool
    ultima: ResultadoSincronizacion | None
    ultima_correcta_en: FechaHora | None
    debe_sincronizar_al_abrir: bool = Field(
        description=(
            "Ítem 38: la app debe lanzar «Sincronizar» sola al abrirse. Lo decide el servidor "
            "(``sincronizacion.debe_sincronizar_al_abrir``): Gmail configurado, hay fecha de inicio, "
            "ninguna en curso, la última terminó hace más de una hora (o nunca hubo) y no falló por "
            "un error que no se arregla solo (Gmail sin configurar o sin permiso)."
        )
    )


class CorreoNoReconocido(BaseModel):
    gmail_id: str
    fecha: FechaHora | None
    asunto: str | None


class ListaNoReconocidos(BaseModel):
    correos: list[CorreoNoReconocido]


class ContadoresReproceso(BaseModel):
    """``revisados`` = ``movimientos_creados`` + ``siguen_sin_reconocerse`` +
    ``ya_registrados`` + ``errores``. Los creados y los ya registrados salen de
    la lista; los demás se quedan.

    ``siguen_sin_reconocerse`` incluye tres casos: sin aviso válido (el lector
    aún no lo reconoce), rechazados por remitente o DMARC (D15) y anteriores a
    la fecha de inicio (nunca crean movimientos, aunque el aviso sea válido)."""

    revisados: int
    movimientos_creados: int
    siguen_sin_reconocerse: int
    ya_registrados: int
    errores: int


class ResultadoReproceso(BaseModel):
    """Un reproceso de los no reconocidos (ítem 19).

    ``estado``: ``ok``; ``con_errores`` (algunos correos no se pudieron
    descargar o procesar y siguen en la lista); ``fallida`` (no se pudo
    empezar o se cortó: ``codigo_error``, con los mismos códigos que la
    sincronización, dice por qué y ``contadores`` es ``null``; lo que alcanzó
    a crearse antes del corte se conserva). ``mensaje`` es un texto para el
    dueño.
    """

    estado: Literal["ok", "con_errores", "fallida"]
    contadores: ContadoresReproceso | None
    codigo_error: (
        Literal["sin_fecha_inicio", "gmail_no_configurado", "autorizacion_gmail", "error_inesperado"]
        | None
    )
    mensaje: str
