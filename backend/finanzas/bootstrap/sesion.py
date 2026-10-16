"""Presta la sesión HTTP y los servicios de seguridad al caso de acceso."""
import secrets

from finanzas.modulos.sesion.publico import (
    Acceder, EstadoSesion, LimitadorAcceso, RevocarPreviews, SesionActual,
)
from finanzas.modulos.sesion.publico import verificar_contrasena


def componer_sesion(estado: EstadoSesion) -> SesionActual:
    return SesionActual(estado, secrets.token_urlsafe)


def componer_acceso(estado: EstadoSesion, limitador: LimitadorAcceso,
                    revocar: RevocarPreviews) -> Acceder:
    return Acceder(componer_sesion(estado), limitador, verificar_contrasena, revocar)
