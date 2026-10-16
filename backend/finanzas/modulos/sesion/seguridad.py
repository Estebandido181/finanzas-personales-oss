"""Hash de contraseñas y limitador de intentos del módulo Sesión.

La fachada finanzas.seguridad conserva los imports y el comando públicos.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
LARGO_SAL = 16
LARGO_HASH = 32
LARGO_MINIMO_CONTRASENA = 12
# Tope de memoria para scrypt: evita que un hash mal formado con n enorme
# consuma memoria sin control (scrypt lanza ValueError y se devuelve False).
_MAXMEM = 64 * 1024 * 1024


def _scrypt(contrasena: str, sal: bytes, n: int, r: int, p: int, largo: int) -> bytes:
    return hashlib.scrypt(
        contrasena.encode("utf-8"), salt=sal, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=largo
    )


def generar_hash(contrasena: str) -> str:
    """Devuelve el hash de ``contrasena`` en formato ``scrypt:n:r:p:sal:hash``."""
    sal = secrets.token_bytes(LARGO_SAL)
    derivada = _scrypt(contrasena, sal, SCRYPT_N, SCRYPT_R, SCRYPT_P, LARGO_HASH)
    return f"scrypt:{SCRYPT_N}:{SCRYPT_R}:{SCRYPT_P}:{sal.hex()}:{derivada.hex()}"


def _entero_positivo(texto: str) -> int | None:
    # Solo dígitos ASCII: int() aceptaría "+1", " 1" o dígitos Unicode.
    if not texto or not texto.isascii() or not texto.isdigit():
        return None
    valor = int(texto)
    return valor if valor > 0 else None


def _hex(texto: str) -> bytes | None:
    if not texto or not texto.isascii():
        return None
    try:
        return bytes.fromhex(texto) or None
    except ValueError:
        return None


def _parsear_hash(texto: str) -> tuple[int, int, int, bytes, bytes] | None:
    """Descompone ``scrypt:n:r:p:sal_hex:hash_hex``; ``None`` si el formato no es válido."""
    if not isinstance(texto, str):
        return None
    partes = texto.split(":")
    if len(partes) != 6 or partes[0] != "scrypt":
        return None
    n, r, p = (_entero_positivo(x) for x in partes[1:4])
    sal, derivada = _hex(partes[4]), _hex(partes[5])
    if n is None or r is None or p is None or sal is None or derivada is None:
        return None
    return n, r, p, sal, derivada


def hash_bien_formado(texto: str) -> bool:
    """True si ``texto`` tiene el formato de ``generar_hash`` (no comprueba la contraseña)."""
    return _parsear_hash(texto) is not None


def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    """True si ``contrasena`` corresponde a ``hash_guardado``.

    Nunca lanza excepción: un hash mal formado (o cualquier error) devuelve False.
    """
    try:
        partes = _parsear_hash(hash_guardado)
        if partes is None:
            return False
        n, r, p, sal, esperado = partes
        calculado = _scrypt(contrasena, sal, n, r, p, len(esperado))
        return hmac.compare_digest(calculado, esperado)
    except Exception:
        return False


class LimitadorIntentos:
    """Bloquea temporalmente una IP tras varios logins fallidos seguidos.

    - Si una IP acumula ``max_intentos`` fallos dentro de la ventana de
      ``bloqueo_minutos``, queda bloqueada ``bloqueo_minutos``.
    - Un login correcto reinicia el contador de esa IP.
    - Mientras dura el bloqueo, quien llama debe rechazar el intento sin
      comprobar la contraseña (ni siquiera la correcta entra).

    ``reloj`` devuelve segundos (por defecto ``time.monotonic``); las pruebas
    inyectan uno falso para simular el paso del tiempo.
    """

    def __init__(
        self,
        max_intentos: int,
        bloqueo_minutos: float,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_intentos <= 0 or bloqueo_minutos <= 0:
            raise ValueError("max_intentos y bloqueo_minutos deben ser mayores que 0")
        self.max_intentos = max_intentos
        self.bloqueo_segundos = bloqueo_minutos * 60
        self._reloj = reloj
        self._fallos: dict[str, list[float]] = {}
        self._bloqueada_hasta: dict[str, float] = {}

    def esta_bloqueada(self, ip: str) -> bool:
        ahora = self._reloj()
        hasta = self._bloqueada_hasta.get(ip)
        if hasta is None:
            return False
        if ahora < hasta:
            return True
        del self._bloqueada_hasta[ip]
        return False

    def registrar_fallo(self, ip: str) -> None:
        ahora = self._reloj()
        self._purgar(ahora)
        fallos = self._fallos.setdefault(ip, [])
        fallos.append(ahora)
        if len(fallos) >= self.max_intentos:
            self._bloqueada_hasta[ip] = ahora + self.bloqueo_segundos
            del self._fallos[ip]

    def registrar_exito(self, ip: str) -> None:
        self._fallos.pop(ip, None)

    def _purgar(self, ahora: float) -> None:
        """Olvida fallos fuera de la ventana y bloqueos vencidos (la memoria no crece sin límite)."""
        limite = ahora - self.bloqueo_segundos
        for ip in list(self._fallos):
            recientes = [t for t in self._fallos[ip] if t > limite]
            if recientes:
                self._fallos[ip] = recientes
            else:
                del self._fallos[ip]
        for ip in [ip for ip, hasta in self._bloqueada_hasta.items() if hasta <= ahora]:
            del self._bloqueada_hasta[ip]
