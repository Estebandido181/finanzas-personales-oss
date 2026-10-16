"""Contrato HTTP: arranque."""
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StrictStr
from .comunes import CentavosNoNegativos, Entrada, Fecha
from .importaciones import ComprobacionSaldo, ConteosImportacion, DetalleImportacion
from .sincronizacion import Contadores, ResultadoSincronizacion


class EstadoArranque(BaseModel):
    mostrar_arranque_inicial: bool
    puede_iniciar_arranque: bool
    puede_extender_historial: bool


class ArchivoHistorial(BaseModel):
    id: int
    estado: Literal["leido"]
    filas: int
    desde: Fecha | None
    hasta: Fecha | None
    truncado: bool


class ArchivosHistorial(BaseModel):
    token: str
    segundos: int
    archivos: list[ArchivoHistorial]
    puede_calcular: bool
    limite_archivos: int
    limite_filas: int


class CalcularArranqueEntrada(Entrada):
    token: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    modo: Literal["arranque", "extension"]
    saldo_actual_centavos: CentavosNoNegativos = 0
    saldo_real_centavos: CentavosNoNegativos | None = None


class HuecoHistorial(BaseModel):
    desde: Fecha
    hasta: Fecha


class CalculoArranque(BaseModel):
    comprobacion_saldo: ComprobacionSaldo | None = None
    modo: Literal["arranque", "extension"]
    saldo_actual_centavos: int
    saldo_inicial_centavos: int
    ingresos_centavos: int
    gastos_centavos: int
    otros_movimientos_netos_centavos: int
    explicacion_otros_movimientos: str
    fecha_inicio_propuesta: Fecha
    fecha_inicio_anterior: Fecha | None
    saldo_inicial_anterior_centavos: int | None
    desde: Fecha
    hasta: Fecha
    archivos: int
    filas: int
    filas_solapadas: int
    archivos_truncados: int
    cobertura_verificada: bool
    huecos: list[HuecoHistorial]
    advertencia_cobertura: str
    correos_leidos: int
    no_reconocidos: int
    contadores_gmail: Contadores
    resumen: ConteosImportacion
    sin_categoria: int
    preguntas_pendientes: int
    saldo_despues_centavos: int


class VistaPreviaArranque(CalculoArranque):
    token: str
    segundos: int


class ResultadoArranque(BaseModel):
    fase: Literal["categorizar", "diferencias", "listo", "deshecho"]
    calculo: CalculoArranque
    importacion: DetalleImportacion
    fecha_inicio: Fecha | None
    saldo_inicial_centavos: int | None
    sincronizacion: ResultadoSincronizacion | None
