"""Seguridad del login: hash de la contraseña y limitador de intentos.

Hash
----
Se usa ``hashlib.scrypt`` (librería estándar, sin dependencias) con sal
aleatoria de 16 bytes y parámetros n=2**14, r=8, p=1. El texto guardado en
``APP_PASSWORD_HASH`` tiene el formato::

    scrypt:<n>:<r>:<p>:<sal_hex>:<hash_hex>

Se usa ``:`` como separador y no ``$`` a propósito: bash (``source .env``)
y el ``EnvironmentFile`` de systemd expanden ``$``, y el hash llegaría roto a
la app. ``Config.desde_entorno`` valida el formato al arrancar.

Para generarlo::

    python -m finanzas.seguridad

Limitador de intentos
---------------------
``LimitadorIntentos`` vive en memoria (un solo proceso de uvicorn; se
reinicia al reiniciar la app). Cuenta los fallos por IP del cliente.

En producción la app corre detrás de Caddy, así que la conexión que ve
uvicorn viene de 127.0.0.1. uvicorn 0.54 ya trae ``proxy_headers`` activado
por defecto y confía en ``X-Forwarded-For`` solo si la conexión viene de
127.0.0.1 o ::1 (``FORWARDED_ALLOW_IPS``), así que el limitador ve la IP real
del cliente sin opciones extra. Pendiente para el ítem 07: comprobar que
Caddy reemplaza ``X-Forwarded-For`` con la IP real en lugar de encadenar el
valor que envía el cliente; si lo encadenara, un atacante podría inventar su
IP y saltarse el bloqueo. Si la app se expusiera sin proxy, todo sigue
funcionando con la IP de la conexión.
"""

from __future__ import annotations

import getpass
import sys

from finanzas.modulos.sesion.seguridad import (
    SCRYPT_N, SCRYPT_R, SCRYPT_P, LARGO_SAL, LARGO_HASH,
    LARGO_MINIMO_CONTRASENA, LimitadorIntentos, generar_hash,
    hash_bien_formado, verificar_contrasena,
)
from finanzas.modulos.sesion.seguridad import _scrypt


def main() -> int:
    """CLI: pide la contraseña dos veces e imprime el hash para ``APP_PASSWORD_HASH``."""
    contrasena = getpass.getpass("Contraseña nueva: ")
    if len(contrasena) < LARGO_MINIMO_CONTRASENA:
        print(
            f"La contraseña debe tener al menos {LARGO_MINIMO_CONTRASENA} caracteres.",
            file=sys.stderr,
        )
        return 1
    if getpass.getpass("Repite la contraseña: ") != contrasena:
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1
    print(generar_hash(contrasena))
    return 0


if __name__ == "__main__":
    sys.exit(main())
