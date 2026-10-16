"""Entrypoints web compatibles durante R1 (retirada interna prevista en R10)."""
from finanzas.bootstrap.app import (
    ENCABEZADOS_SEGURIDAD,
    crear_app,
    destino_inicio,
    origen_permitido,
    sitio_permitido,
)


def __getattr__(nombre: str):
    if nombre == "app":
        instancia = crear_app()
        globals()["app"] = instancia
        return instancia
    # Compatibilidad temporal para constantes y helpers históricos.
    from finanzas.bootstrap import app as composicion
    return getattr(composicion, nombre)
