"""Registro RAM de copias opacas; no conoce datos financieros ni HTTP."""
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

SEGUNDOS_DESHACER = 30
MAXIMO_EN_MEMORIA = 100

@dataclass(frozen=True)
class _Pendiente:
    copia: object
    vence: float


class RegistroDeshacer:
    """Copias de lo borrado, por token, en memoria y con un candado.

    El candado hace atómico "tomar": dos "Deshacer" casi simultáneos con el
    mismo token restauran una sola vez. Se guardan las ``MAXIMO_EN_MEMORIA``
    más recientes; las vencidas se descartan al guardar o tomar.
    """

    def __init__(
        self, segundos: int = SEGUNDOS_DESHACER, reloj: Callable[[], float] = time.monotonic
    ) -> None:
        self.segundos = segundos
        self._reloj = reloj
        self._pendientes: OrderedDict[str, _Pendiente] = OrderedDict()
        self._candado = threading.Lock()

    def _limpiar(self, ahora: float) -> None:
        vencidos = [t for t, p in self._pendientes.items() if p.vence <= ahora]
        for token in vencidos:
            del self._pendientes[token]
        while len(self._pendientes) > MAXIMO_EN_MEMORIA:
            self._pendientes.popitem(last=False)

    def guardar(self, copia: object) -> str:
        """Guarda la copia y devuelve un token nuevo para restaurarla."""
        token = secrets.token_urlsafe(16)
        with self._candado:
            ahora = self._reloj()
            self._pendientes[token] = _Pendiente(copia, ahora + self.segundos)
            self._limpiar(ahora)
        return token

    def tomar(self, token: str) -> _Pendiente | None:
        """Saca la copia del token (una sola vez); ``None`` si no existe o venció."""
        with self._candado:
            ahora = self._reloj()
            self._limpiar(ahora)
            return self._pendientes.pop(token, None)
