"""Deshacer unos segundos lo que se acaba de borrar (ítem 38).

Borrar un ingreso manual, una regla o una categoría sin movimientos ni reglas
se hace al tocar, sin confirmación, y la app muestra "Deshacer" unos
segundos. Restaurar es otra petición al servidor (``POST /api/deshacer``),
no un borrado retrasado en el cliente: el servidor sigue siendo la fuente de
verdad y lo borrado sale de la base en el momento.

Cómo sabe el cliente qué restaurar: el DELETE responde un ``token`` opaco
(``emitir``). La copia de lo borrado (``saldo.CopiaIngreso``,
``categorizacion.CopiaRegla`` o ``categorizacion.CopiaCategoria``) se queda
en la memoria del servidor; el cliente solo guarda el token, sin montos ni
datos del movimiento, y no puede pedir que se restaure algo distinto de lo
que se borró.

Cada token:

* vale ``SEGUNDOS_DESHACER`` segundos (reloj monotónico, no la hora del
  sistema) y una sola vez, salga bien o no la restauración: deshacer dos
  veces no duplica nada;
* queda ligado a la sesión que borró (se anota en la cookie de sesión, como
  ``tokens_ingreso``): otra sesión no puede usarlo;
* vive solo en la memoria del proceso (hay uno solo, ver
  ``deploy/systemd/finanzas.service``): si la app se reinicia, lo borrado
  ya no se puede deshacer, y la respuesta lo dice (410).

No se registra nada de las copias (montos, descripciones).
"""

from starlette.requests import Request
from finanzas.api.tokens_ingreso import agregar_a_sesion, lista_sesion
from finanzas.infraestructura.deshacer_ram import (
    RegistroDeshacer, _Pendiente, SEGUNDOS_DESHACER, MAXIMO_EN_MEMORIA,
)

CLAVE_TOKENS_DESHACER = "tokens_deshacer"
MAXIMO_TOKEN = 100

def emitir(request: Request, registro: RegistroDeshacer, copia: object) -> str:
    """Guarda la copia, anota el token en la sesión y lo devuelve."""
    token = registro.guardar(copia)
    agregar_a_sesion(request, CLAVE_TOKENS_DESHACER, token)
    return token


def tomar(request: Request, registro: RegistroDeshacer, token: str) -> _Pendiente | None:
    """La copia del token si es de esta sesión, sigue vigente y no se usó; si no, ``None``.

    El token sale de la sesión en cualquier caso: no sirve una segunda vez.
    """
    de_la_sesion = lista_sesion(request, CLAVE_TOKENS_DESHACER)
    if not token or token not in de_la_sesion:
        return None
    request.session[CLAVE_TOKENS_DESHACER] = [t for t in de_la_sesion if t != token]
    return registro.tomar(token)
