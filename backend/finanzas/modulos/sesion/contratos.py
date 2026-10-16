"""Identidad y puertos del acceso; la cookie pertenece al adaptador HTTP."""
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Protocol

CLAVE_AUTENTICADO = "autenticado"
CLAVE_CSRF = "csrf_token"
LARGO_TOKEN_CSRF = 32


@dataclass(frozen=True)
class UsuarioSesion:
    id: str
    nombre: str


DUENO = UsuarioSesion(id="dueno", nombre="Dueño")
EstadoSesion = MutableMapping[str, object]
GenerarToken = Callable[[int], str]
VerificarContrasena = Callable[[str, str], bool]
RevocarPreviews = Callable[[], None]


class LimitadorAcceso(Protocol):
    def esta_bloqueada(self, ip: str) -> bool: ...
    def registrar_exito(self, ip: str) -> None: ...
    def registrar_fallo(self, ip: str) -> None: ...


class SesionRequerida(Exception):
    pass


class AccesoBloqueado(Exception):
    pass


class ContrasenaIncorrecta(Exception):
    pass
