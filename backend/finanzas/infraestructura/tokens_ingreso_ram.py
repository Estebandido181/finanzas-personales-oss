"""Registro RAM de uso único, independiente de la cookie y del ingreso."""
import threading
from collections import OrderedDict

MAXIMO_TOKENS_MEMORIA = 1000

class TokensIngreso:
    """Tokens de ingreso ya usados, en memoria del proceso y con un candado.

    Por qué además de la sesión: la sesión viaja en la cookie, así que dos
    envíos casi simultáneos del mismo formulario (doble clic) llegan con la
    misma cookie y los dos verían el token "sin usar". Este registro, con su
    candado, hace atómico el "comprobar y marcar": solo uno de los dos pasa.
    La lista de la sesión cubre un reinicio de la app entre los dos envíos
    solo si el segundo trae la cookie posterior al primero; con la cookie
    anterior (doble clic justo durante un reinicio) el token podría usarse
    otra vez. Se guardan los últimos ``MAXIMO_TOKENS_MEMORIA``.
    """

    def __init__(self) -> None:
        self._usados: OrderedDict[str, None] = OrderedDict()
        self._candado = threading.Lock()

    def marcar(self, token: str) -> bool:
        """Marca el token como usado; ``False`` si ya lo estaba."""
        with self._candado:
            if token in self._usados:
                return False
            self._usados[token] = None
            while len(self._usados) > MAXIMO_TOKENS_MEMORIA:
                self._usados.popitem(last=False)
            return True

    def liberar(self, token: str) -> None:
        """Deshace ``marcar`` (el ingreso no se guardó: se puede corregir y reenviar)."""
        with self._candado:
            self._usados.pop(token, None)

    def usado(self, token: str) -> bool:
        with self._candado:
            return token in self._usados
