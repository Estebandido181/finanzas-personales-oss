"""Guardado de la conciliación con el banco (ítem 29): todo en una transacción.

``finanzas.conciliacion`` decide (lógica pura); este módulo lee de la base lo
que el motor necesita, aplica su ``Plan`` y deja constancia de cada cambio en
``importaciones`` y ``cambios_importacion`` (para el "deshacer" del ítem 30).
Nunca guarda el archivo del banco: solo los movimientos, y de ``Referencia``
solo ``*1234`` (D37; la base lo exige con un CHECK).

Funciones:

* ``importar(conn, movimientos_excel)``: concilia un reporte del banco.
  Todo ocurre en una sola transacción inmediata (``BEGIN IMMEDIATE``): una
  sincronización o un ajuste simultáneos quedan antes o después, nunca en
  medio. Importar dos veces el mismo reporte no cambia ningún movimiento.
* ``leer_estado(conn, filas)``: lo que el motor necesita, solo lectura. La
  conciliación en seco lo usa sobre una base abierta en solo lectura (y
  también sirve con una base de la 0007, sin las columnas nuevas).
* ``recibir_aviso(conn, gmail_id, movimiento)``: la sincronización lo llama
  antes de guardar un aviso. Si el movimiento ya entró del banco sin aviso,
  lo confirma en vez de crear otro; si hay duda, pregunta (D45).
* ``responder_pregunta(...)``: aplica la decisión del dueño.

Los registros (logs) nunca llevan montos, descripciones ni referencias.
"""

from __future__ import annotations

from finanzas.bootstrap.importaciones import componer_incorporacion_aviso, componer_operacion_avisos
from finanzas.modulos.importaciones.avisos_aplicacion import _ids
from finanzas.modulos.importaciones.avisos_sqlite import (_reservados, _sin_aviso_cercanos, _filas_que_esperan, _pregunta_de_correo, _reservar, _SQL_RESERVADOS)
import finanzas.modulos.importaciones.avisos_sqlite as _avisos_sqlite
from finanzas.bootstrap.importaciones import componer_reportes
from finanzas.modulos.importaciones.contratos import (
    ErrorConciliacion,
    SinConfiguracion,
    Conteos,
    ResumenImportacion,
    EstadoParaConciliar,
    MENSAJE_CANDIDATO_USADO,
)
from finanzas.modulos.importaciones.politica_planes import filas_desde_excel, conteos
from finanzas.modulos.importaciones.reportes_sqlite import (_fecha, _columnas, _elecciones_banco, _registrar_cambio, _crear_pregunta)
import finanzas.modulos.importaciones.reportes_sqlite as _reportes_sqlite

from finanzas.bootstrap.movimientos import componer_registro_normalizado
from finanzas.modulos.movimientos.publico import MovimientoNuevo

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from contextlib import nullcontext
from datetime import date, datetime, timedelta

from sqlalchemy import Connection, text

from finanzas.modulos.importaciones import motor as c
from finanzas.modulos.importaciones.publico import (MovimientoExcel, AVISO_NUEVO, AVISO_CONFIRMO, AVISO_PREGUNTA, AVISO_EN_PREGUNTA, AVISO_YA_ESTABA, AVISO_DESCARTADO)
from finanzas.bootstrap.categorias import componer_clasificacion_entrada
from dataclasses import asdict

logger = logging.getLogger(__name__)


# --- Lectura ---------------------------------------------------------------------------


def planear(conn: Connection, filas: Sequence[c.FilaBanco]) -> c.Plan:
    return componer_reportes(conn).planear(filas)

# --- Escritura ---------------------------------------------------------------------------


def importar(conn: Connection, movimientos_excel: Sequence[MovimientoExcel], *, transaccion_externa: bool = False,
             cobertura: Sequence[tuple[date, date]] | None = None,
             compensar_en_inicial_antes: date | None = None) -> ResumenImportacion:
    resultado = componer_reportes(conn).importar(movimientos_excel,
        transaccion_externa=transaccion_externa, cobertura=cobertura,
        compensar_en_inicial_antes=compensar_en_inicial_antes)
    logger.info("Importación %s guardada", resultado.importacion_id)
    return resultado

# --- Aviso que llega después de importar (D45) -----------------------------------------


def _preguntas_que_esperan_al_aviso(conn: Connection, aviso: c.AvisoNuevo) -> tuple[int, ...]:
    return componer_operacion_avisos(conn).preguntas_que_esperan_al_aviso(aviso)


def recibir_aviso(conn: Connection, gmail_id: str, movimiento) -> str:
    return componer_incorporacion_aviso(conn).incorporar_aviso(gmail_id, movimiento)

# --- Compatibilidad de respuestas: una única implementación ----------------------------
from finanzas.bootstrap.importaciones import componer_preguntas
from finanzas.modulos.importaciones.contratos import (
    MENSAJE_PREGUNTA_NO_EXISTE, MENSAJE_CANDIDATO, MENSAJE_FALTA_AJUSTE)
from finanzas.modulos.importaciones.preguntas_aplicacion import _Efecto, _elegir
from finanzas.modulos.importaciones.preguntas_sqlite import (preguntas_pendientes, _ajuste, _SQL_AJUSTES)
import finanzas.modulos.importaciones.preguntas_sqlite as _preguntas_sqlite
from finanzas.modulos.importaciones import preguntas_aplicacion as _politicas_preguntas


def responder_pregunta(conn: Connection, pregunta_id: int, si: bool, movimiento_id: int | None = None,
                       ya_estaba_en_ajuste: bool | None = None, *, ninguno: bool = False,
                       transaccion_externa: bool = False) -> None:
    componer_preguntas(conn).responder_pregunta(pregunta_id, si, movimiento_id, ya_estaba_en_ajuste,
        ninguno=ninguno, transaccion_externa=transaccion_externa)

def _efecto_con_ajuste(conn: Connection, importacion_id: int | None, fila: c.FilaBanco, efecto: _Efecto,
                       ya_estaba: bool | None) -> None:
    return _politicas_preguntas._efecto_con_ajuste(PreguntasSQLite(conn, colaboradores=componer_colaboradores_importacion(conn)), importacion_id, fila, efecto, ya_estaba)


def _efecto_ya_estaba(conn: Connection, importacion_id: int | None, fila: c.FilaBanco, efecto: _Efecto,
                      ya_estaba: bool, ajuste_id: int | None) -> None:
    return _politicas_preguntas._efecto_ya_estaba(PreguntasSQLite(conn, colaboradores=componer_colaboradores_importacion(conn)), importacion_id, fila, efecto, ya_estaba, ajuste_id)


def _candidato_automatico(conn: Connection, fila: c.FilaBanco, candidatos: Sequence[int]) -> int | None:
    return _politicas_preguntas._candidato_automatico(PreguntasSQLite(conn, colaboradores=componer_colaboradores_importacion(conn)), fila, candidatos)


def _validar_ocurrencia_elegida(conn: Connection, pregunta, movimiento_id: int | None) -> None:
    return _politicas_preguntas._validar_ocurrencia_elegida(PreguntasSQLite(conn, colaboradores=componer_colaboradores_importacion(conn)), pregunta, movimiento_id)


def _actualizar_preguntas_sin_candidatos(conn: Connection, pregunta) -> None:
    return _politicas_preguntas._actualizar_preguntas_sin_candidatos(PreguntasSQLite(conn, colaboradores=componer_colaboradores_importacion(conn)), pregunta)

from finanzas.modulos.movimientos.bancario_sqlite import _SQL_FILA_ACTUAL

from finanzas.bootstrap.importaciones import componer_colaboradores_importacion

def _vincular_aviso_descartado(conn: Connection, ident: int, gmail_id: str) -> None:
    return _avisos_sqlite._vincular_aviso_descartado(conn, ident, gmail_id, colaboradores=componer_colaboradores_importacion(conn))

def _guardar_aviso(conn: Connection, gmail_id: str, movimiento) -> int:
    return _avisos_sqlite._guardar_aviso(conn, gmail_id, movimiento, colaboradores=componer_colaboradores_importacion(conn))

def _reservas_descartes(conn: Connection, reservados: set[int]) -> list[c.ReservaDescarte]:
    return _reportes_sqlite._reservas_descartes(conn, reservados, colaboradores=componer_colaboradores_importacion(conn))

def leer_estado(conn: Connection, filas: Sequence[c.FilaBanco]) -> EstadoParaConciliar:
    return _reportes_sqlite.leer_estado(conn, filas, colaboradores=componer_colaboradores_importacion(conn))

def _confirmar(conn: Connection, importacion_id: int | None, fila: c.FilaBanco, movimiento_id: int, corregir: bool) -> None:
    return _reportes_sqlite._confirmar(conn, importacion_id, fila, movimiento_id, corregir, colaboradores=componer_colaboradores_importacion(conn))

def _confirmar_descarte(conn: Connection, fila: c.FilaBanco, ident: int, importacion_id: int | None=None) -> None:
    return _reportes_sqlite._confirmar_descarte(conn, fila, ident, importacion_id, colaboradores=componer_colaboradores_importacion(conn))

def _agregar(conn: Connection, importacion_id: int | None, fila: c.FilaBanco) -> int:
    return _reportes_sqlite._agregar(conn, importacion_id, fila, colaboradores=componer_colaboradores_importacion(conn))

def _reducir_ajuste(conn: Connection, importacion_id: int | None, ajuste_id: int, efecto: int) -> None:
    return _reportes_sqlite._reducir_ajuste(conn, importacion_id, ajuste_id, efecto, colaboradores=componer_colaboradores_importacion(conn))

def _aplicar_fila(conn: Connection, importacion_id, fila, movimiento_id, de_aviso=False):
    return _preguntas_sqlite._aplicar_fila(conn, importacion_id, fila, movimiento_id, de_aviso, colaboradores=componer_colaboradores_importacion(conn))

def _responder_correo(conn: Connection, pregunta, elegido):
    return _preguntas_sqlite._responder_correo(conn, pregunta, elegido, colaboradores=componer_colaboradores_importacion(conn))

from finanzas.modulos.importaciones.preguntas_sqlite import PreguntasSQLite
