"""Adaptador de recuperación Gmail; nunca solicita permisos de escritura."""
from __future__ import annotations
from collections.abc import Sequence
from datetime import date, datetime, time
from typing import Any
from finanzas.compartido.hora import ZONA_COLOMBIA
from finanzas.modulos.sincronizacion.contratos import (CorreoGmail, ErrorAutorizacionGmail, REMITENTES_OFICIALES, como_remitentes)
from .mime import correo_desde_mensaje
from .oauth import cargar_credenciales, _MENSAJE_REVOCADO

_REINTENTOS = 3

# --- Cliente real -------------------------------------------------------------

def consulta_gmail(remitente: str, desde: date) -> str:
    """Consulta de búsqueda de Gmail para UN remitente: ``from:<remitente> after:<segundos>``.

    Con dos remitentes se hace una consulta por cada uno (``listar_ids``), en
    vez de combinarlos con ``OR`` o ``{}``: así ningún detalle de la sintaxis
    de búsqueda de Gmail puede dejar fuera los correos de uno de ellos.

    ``after:`` recibe los segundos Unix de la medianoche de ``desde`` en hora
    de Colombia. Con una fecha ``aaaa/mm/dd``, Gmail la interpretaría en la hora
    del Pacífico y podría perder los correos de las primeras horas del día.
    """
    medianoche = datetime.combine(desde, time(0, 0), tzinfo=ZONA_COLOMBIA)
    return f"from:{remitente} after:{int(medianoche.timestamp())}"


def _es_error_de_autorizacion(error: Exception) -> bool:
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError

    if isinstance(error, RefreshError):
        return True
    return isinstance(error, HttpError) and getattr(error.resp, "status", None) == 401


class ClienteGmailReal:
    """``ClienteGmail`` sobre la API oficial de Gmail.

    ``service`` es el objeto de ``googleapiclient.discovery.build("gmail", "v1")``;
    las pruebas pasan uno falso. En la app se crea con ``desde_token``.
    """

    def __init__(
        self, service: Any, remitentes: str | Sequence[str] = REMITENTES_OFICIALES
    ) -> None:
        self._service = service
        self._remitentes = como_remitentes(remitentes)

    @classmethod
    def desde_token(
        cls, ruta_token: str, remitentes: str | Sequence[str] = REMITENTES_OFICIALES
    ) -> "ClienteGmailReal":
        from googleapiclient.discovery import build

        credenciales = cargar_credenciales(ruta_token)
        service = build("gmail", "v1", credentials=credenciales, cache_discovery=False)
        return cls(service, remitentes)

    def listar_ids(self, desde: date) -> list[str]:
        """Ids de todos los remitentes, una consulta por remitente, en ese
        orden y sin repetidos."""
        ids: list[str] = []
        for remitente in self._remitentes:
            ids.extend(self._listar_ids_de(consulta_gmail(remitente, desde)))
        return list(dict.fromkeys(ids))

    def _listar_ids_de(self, consulta: str) -> list[str]:
        ids: list[str] = []
        pagina: str | None = None
        while True:
            try:
                respuesta = (
                    self._service.users()
                    .messages()
                    .list(userId="me", q=consulta, pageToken=pagina)
                    .execute(num_retries=_REINTENTOS)
                )
            except Exception as error:
                if _es_error_de_autorizacion(error):
                    raise ErrorAutorizacionGmail(_MENSAJE_REVOCADO) from None
                raise
            ids.extend(str(m["id"]) for m in respuesta.get("messages") or ())
            pagina = respuesta.get("nextPageToken")
            if not pagina:
                return ids

    def obtener(self, gmail_id: str) -> CorreoGmail:
        try:
            mensaje = (
                self._service.users()
                .messages()
                .get(userId="me", id=gmail_id, format="full")
                .execute(num_retries=_REINTENTOS)
            )
        except Exception as error:
            if _es_error_de_autorizacion(error):
                raise ErrorAutorizacionGmail(_MENSAJE_REVOCADO) from None
            raise
        return correo_desde_mensaje(mensaje)
