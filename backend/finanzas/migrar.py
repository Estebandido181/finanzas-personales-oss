"""Entrada estable de migraciones; la implementación vive en ``operacion``.

La VM, Alembic y consumidores históricos mantienen ``finanzas.migrar``.
``ESPERA_BLOQUEO`` sigue ajustable aquí para las pruebas de concurrencia.
"""
from __future__ import annotations

from collections.abc import Sequence

from finanzas.operacion import migrar as _operacion
from finanzas.operacion.migrar import *  # noqa: F401,F403
from finanzas.operacion.migrar import (
    _argumentos, _comprobar, _migrar, _bajar, _diagnosticar,
    _modulo_respaldo, _config, _scripts, _revision_conocida, _pendientes,
)

ESPERA_BLOQUEO = _operacion.ESPERA_BLOQUEO


def _sincronizar_espera() -> None:
    # El valor público se puede modificar antes de invocar cualquiera de los
    # comandos o funciones que abren una conexión de migración.
    _operacion.ESPERA_BLOQUEO = ESPERA_BLOQUEO


def conectar_para_migrar(ruta: str):
    _sincronizar_espera()
    return _operacion.conectar_para_migrar(ruta)


def aplicar(ruta: str):
    _sincronizar_espera()
    return _operacion.aplicar(ruta)


def bajar_a(ruta: str, revision: str):
    _sincronizar_espera()
    return _operacion.bajar_a(ruta, revision)


def main(argv: Sequence[str] | None = None) -> int:
    _sincronizar_espera()
    return _operacion.main(argv)


if __name__ == "__main__":
    import sys

    sys.exit(main())
