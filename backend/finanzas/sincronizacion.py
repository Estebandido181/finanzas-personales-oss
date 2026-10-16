"""Entrypoint conservado; casos y registro pertenecen a Sincronización."""
from __future__ import annotations
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime
from sqlalchemy import Connection
from finanzas.compartido.config import Config
from finanzas.modulos.sincronizacion.publico import *
from finanzas.modulos.sincronizacion.contratos import SincronizacionNoConfigurada, ResultadoReproceso, REMITENTE_POR_DEFECTO
from finanzas.modulos.sincronizacion.adaptadores.gmail.autenticidad import (
    MOTIVO_REMITENTE, remitente_reconocido, motivo_autenticacion_invalida,
)
from finanzas.modulos.sincronizacion.adaptadores.gmail.cliente import ClienteGmailReal
from finanzas.modulos.sincronizacion.politica import (
    debe_sincronizar_al_abrir, ANTIGUEDAD_PARA_SINCRONIZAR, CODIGOS_QUE_NO_SE_ARREGLAN_SOLOS,
)
from finanzas.modulos.sincronizacion.adaptadores.avisos.evaluacion import evaluar_correo, _motivo_rechazo
from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor
from finanzas.modulos.sincronizacion.adaptadores.avisos.lector import *
from finanzas.modulos.sincronizacion.adaptadores.avisos.lector import (
    _IMAGEN_PLANTILLA, _INICIO_AVISO, _RELLENOS_INVISIBLES, _OTRO_AVISO, _clave_encabezado,
    _CLAVES_ENCABEZADOS, _sin_imagenes_plantilla, _encabezado_permitido, _analizar, _buscar_aviso,
)
from finanzas.bootstrap.sincronizacion import (
    componer_sincronizacion, componer_registro_sincronizacion, componer_colaboradores_sincronizacion,
    gmail_configurado, cliente_desde_config,
)
from finanzas.modulos.sincronizacion import registro_sqlite
from finanzas.operacion.sincronizar import main

def _ejecutar(conn: Connection, fabrica_cliente: Callable[[], ClienteGmail], remitentes_oficiales: str | Sequence[str], origen: str) -> tuple[EstadoSincronizacion, Exception | None]:
    return componer_sincronizacion(conn)._ejecutar(fabrica_cliente, remitentes_oficiales, origen)

def ejecutar(conn: Connection, fabrica_cliente: Callable[[], ClienteGmail], remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES, origen: str='comando') -> ResultadoSincronizacion:
    return componer_sincronizacion(conn).ejecutar(fabrica_cliente, remitentes_oficiales, origen)

def ejecutar_con_estado(conn: Connection, fabrica_cliente: Callable[[], ClienteGmail], remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES, origen: str='web') -> EstadoSincronizacion:
    return componer_sincronizacion(conn).ejecutar_con_estado(fabrica_cliente, remitentes_oficiales, origen)

def ejecutar_reproceso(conn: Connection, fabrica_cliente: Callable[[], ClienteGmail], remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES, gmail_id: str | None=None) -> tuple[ResultadoReproceso | None, str | None]:
    return componer_sincronizacion(conn).ejecutar_reproceso(fabrica_cliente, remitentes_oficiales, gmail_id)

def reprocesar(conn: Connection, cliente: ClienteGmail, remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES, gmail_id: str | None=None) -> ResultadoReproceso:
    return componer_sincronizacion(conn).reprocesar(cliente, remitentes_oficiales, gmail_id)

def sincronizar(conn: Connection, cliente: ClienteGmail, remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES) -> ResultadoSincronizacion:
    return componer_sincronizacion(conn).sincronizar(cliente, remitentes_oficiales)

def es_no_reconocido(conn: Connection, gmail_id: str) -> bool:
    return componer_registro_sincronizacion(conn).es_no_reconocido(gmail_id)

def fecha_configurada(conn: Connection) -> bool:
    return componer_registro_sincronizacion(conn).fecha_configurada()

def leer_fecha_inicio(conn: Connection) -> date:
    return componer_registro_sincronizacion(conn).leer_fecha_inicio()

def listar_no_reconocidos(conn: Connection) -> list[RowMapping]:
    return componer_registro_sincronizacion(conn).listar_no_reconocidos()

guardar_estado = registro_sqlite.guardar_estado
leer_estado = registro_sqlite.leer_estado
contar_no_reconocidos = registro_sqlite.contar_no_reconocidos
_ids_registrados = registro_sqlite._ids_registrados
_leer_ultima_correcta = registro_sqlite._leer_ultima_correcta
_guardar_no_reconocido = registro_sqlite._guardar_no_reconocido
def _guardar_movimiento(conn: Connection, gmail_id: str, movimiento: extractor.MovimientoExtraido, quitar_no_reconocido: bool=False, *, transaccion_externa: bool=False) -> bool:
    return registro_sqlite._guardar_movimiento(conn, gmail_id, movimiento, quitar_no_reconocido, transaccion_externa=transaccion_externa, colaboradores=componer_colaboradores_sincronizacion(conn))

def _columnas_de_categoria(conn: Connection, movimiento: extractor.MovimientoExtraido) -> dict:
    return registro_sqlite._columnas_de_categoria(conn, movimiento, colaboradores=componer_colaboradores_sincronizacion(conn))

if __name__ == "__main__":
    sys.exit(main())
