"""Contrato HTTP: importaciones."""
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StrictStr, model_validator
from .categorias import OpcionRegla
from .comunes import CentavosNoNegativos, ClaseCategoria, Entrada, Fecha, FechaHora, IdEntrada, OrigenMovimiento, TipoMovimiento, TipoRegla
from .deshacer import Deshacer
from .saldo import DesgloseSaldo


class ConteosImportacion(BaseModel):
    filas: int
    ya_estaban: int
    ya_preguntadas: int
    confirmados: int
    corregidos: int
    agregados: int
    preguntas_es_el_mismo: int
    preguntas_ajuste: int
    no_en_banco: int
    anteriores: int
    sin_formato: int
    ajuste_reducido: bool


class RangoImportacion(BaseModel):
    desde: Fecha | None
    hasta: Fecha | None
    dia_incompleto: bool


class CoberturaComprobacion(BaseModel):
    desde: Fecha | None
    hasta: Fecha | None
    archivos_de_120_filas: int | None
    proteccion_ausencias_conservadora: bool
    cobertura_verificada: Literal[False]
    cobertura_hasta_consulta_verificada: Literal[False]
    huecos: list[dict[str, str]]
    advertencia: str


class ContribucionesSaldo(BaseModel):
    agregados_centavos: int
    corregidos_centavos: int
    ajustes_centavos: int
    cambio_inicial_centavos: int
    otros_centavos: int


class PendientesComprobacion(BaseModel):
    preguntas: int
    no_en_banco: int
    sin_categoria: int


class ComprobacionSaldo(BaseModel):
    """Diferencia banco − app; coincidir no acredita cobertura ni consultas al banco."""
    estado: Literal["disponible", "sin_configuracion"]
    origen: Literal["actual", "importacion", "extension", "arranque"]
    saldo_real_centavos: int
    saldo_app_centavos: int | None
    diferencia_centavos: int | None
    coincide: bool | None
    recibido_en: FechaHora
    huella: str
    verificacion_independiente: bool
    diferencia_forzada_por_inicial: bool
    saldo_antes_centavos: int | None
    saldo_despues_centavos: int | None
    efecto_conciliacion_centavos: int | None
    resto_no_explicado_centavos: int | None
    desglose_antes: DesgloseSaldo | None
    desglose_despues: DesgloseSaldo | None
    contribuciones: ContribucionesSaldo | None
    pendientes: PendientesComprobacion
    cobertura: CoberturaComprobacion


class ComprobarSaldoEntrada(Entrada):
    saldo_real_centavos: CentavosNoNegativos
    token_analisis: Annotated[StrictStr, Field(min_length=1, max_length=100)] | None = None
    tipo_analisis: Literal["importacion", "arranque"] | None = None

    @model_validator(mode="after")
    def referencia_de_preview(self):
        if (self.token_analisis is None) != (self.tipo_analisis is None):
            raise ValueError("Indica el token y su tipo de análisis juntos.")
        return self


class CausaSaldoImportacion(BaseModel):
    codigo: str
    titulo: str
    texto: str
    accion: Literal["ajustar_saldo", "elegir_otro_archivo", "extender_historial"]


class VistaPreviaImportacion(BaseModel):
    causas_probables: list[CausaSaldoImportacion]
    diferencia_centavos: int
    entran_categorizados: int
    fecha_inicio: Fecha
    puede_extender_historial: bool = False
    token: str
    segundos: int
    resumen: ConteosImportacion
    reporte: RangoImportacion
    saldo_antes_centavos: int
    saldo_despues_centavos: int
    sin_categoria: int
    preguntas_pendientes: int
    sin_cambios: bool


class ConfirmarImportacionEntrada(Entrada):
    token: Annotated[StrictStr, Field(min_length=1, max_length=100)]


class PropuestaReglaBanco(BaseModel):
    modo: Literal["exacta", "contiene", "empieza_por"]
    texto: str
    frase: str


class GrupoImportacion(BaseModel):
    desde: Fecha
    hasta: Fecha
    es_gasto: bool
    regla: OpcionRegla | None
    clave: str
    tipo: TipoRegla
    descripcion: str
    clase_categoria: ClaseCategoria
    cuantos: int
    suma_centavos: int
    ids: list[int]
    reglas_propuestas: list[PropuestaReglaBanco]


class DetalleImportacion(BaseModel):
    todo_resuelto: bool
    puede_extender_historial: bool = False
    id: int
    hecha_en: FechaHora
    deshecha_en: FechaHora | None
    resumen: ConteosImportacion
    reporte: RangoImportacion
    saldo_centavos: int | None  # Deshacer primer arranque restaura ausencia de configuración.
    se_puede_deshacer: bool
    motivo_no_deshacer: str | None
    sin_categoria: int
    grupos: list[GrupoImportacion]
    preguntas_pendientes: int
    no_en_banco_pendientes: int
    siguiente: Literal["categorizar", "diferencias", "inicio"]


class UltimaImportacion(BaseModel):
    importacion: DetalleImportacion | None


class EstadoImportaciones(BaseModel):
    ultima_id: int | None
    mostrar_recordatorio: bool
    movimientos_desde_ultima: int
    semanas_desde_ultima: int
    preguntas_pendientes: int
    no_en_banco_pendientes: int
    sin_categoria: int
    importacion_pendiente: bool


class SugerenciaConciliacion(BaseModel):
    opcion: str | None
    motivo: str
    analisis: str


class DatoConciliacion(BaseModel):
    etiqueta: str | None = None  # Solo para distinguir candidatos con todos sus datos iguales.
    descartado: bool = False
    nota_descartado: str | None = None
    id: int | None
    descripcion: str
    tipo: TipoMovimiento
    origen: OrigenMovimiento
    monto_centavos: int
    fecha_hora: FechaHora
    destino_ultimos4: str | None


class OpcionConciliacion(BaseModel):
    id: str
    texto: str
    consecuencia: str


class PreguntaConciliacion(BaseModel):
    id: int
    tipo: Literal["monto_parecido", "varios_candidatos", "mismo_dia_ajuste"]
    fuente: Literal["banco", "correo"]
    movimiento: DatoConciliacion
    candidatos: list[DatoConciliacion]
    ajuste: DatoConciliacion | None
    diferencia_centavos: int | None
    opciones: list[OpcionConciliacion]
    sugerencia: SugerenciaConciliacion


class ListaPreguntasConciliacion(BaseModel):
    preguntas: list[PreguntaConciliacion]
    total: int
    con_sugerencia: int


class RespuestaConciliacionEntrada(Entrada):
    opcion: Annotated[StrictStr, Field(min_length=1, max_length=100)]


class RespuestaIndividualConciliacion(RespuestaConciliacionEntrada):
    pregunta_id: IdEntrada


class RespuestasConciliacionEntrada(Entrada):
    respuestas: Annotated[list[RespuestaIndividualConciliacion], Field(min_length=1, max_length=120)]


class ResultadoDecisionConciliacion(BaseModel):
    aplicadas: list[int]
    resumen: str
    efecto_saldo_centavos: int
    saldo_centavos: int
    deshacer: Deshacer


class NoEnBanco(BaseModel):
    id: int
    movimiento: DatoConciliacion
    sugerencia: SugerenciaConciliacion


class ListaNoEnBanco(BaseModel):
    movimientos: list[NoEnBanco]
    reporte: RangoImportacion | None


class RespuestaNoEnBancoEntrada(Entrada):
    opcion: Literal["borrar", "dejar"]


class DecisionDeshecha(BaseModel):
    saldo_centavos: int
    resumen: str
