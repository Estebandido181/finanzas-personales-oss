"""Compatibilidad de persistencia; cuerpos únicos fuera del ejecutor operativo."""
from finanzas.infraestructura.persistencia.esquema import *
from finanzas.infraestructura.persistencia.esquema import (
    _ahora_iso_sqlite, _ahora_iso_postgresql, _solo_sqlite, _fecha_valida,
    _entero_no_negativo, _contador,
)
from finanzas.infraestructura.persistencia.conexion import (
    crear_motor, conectar, ruta_de, _al_conectar_sqlite, ESPERA_POR_DEFECTO,
)
from finanzas.infraestructura.persistencia.transacciones import (
    en_transaccion, _es_sqlite, _cerrar_transaccion_vacia, transaccion,
    lectura_consistente, insertar,
)
from finanzas.infraestructura.persistencia.revision import BaseNoMigrada, revision_actual


def exigir_al_dia(ruta: str) -> None:
    from finanzas.bootstrap.persistencia import exigir_al_dia as verificar
    verificar(ruta)


def preparar(ruta: str) -> None:
    from finanzas.operacion.desarrollo import preparar as preparar_desarrollo
    preparar_desarrollo(ruta)


def inicializar(conn) -> None:
    from finanzas.operacion.desarrollo import inicializar as inicializar_desarrollo
    inicializar_desarrollo(conn)
