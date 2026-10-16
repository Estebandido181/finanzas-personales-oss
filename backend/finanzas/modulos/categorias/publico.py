"""Clasificación de entradas normalizadas: sin conocer correo ni SQL."""
from .contratos import CategoriaDeEntrada, ClasificarEntrada

from typing import Protocol
from .contratos import ReglaGuardada, ResumenPendientes


class AsignarPorReglas(ClasificarEntrada, Protocol):
    def regla_que_coincide(self, tipo: str, descripcion: str, monto_centavos: int | None,
                          origen: str = "gmail", referencia: str | None = None) -> ReglaGuardada | None: ...


class ConsultarPendientes(Protocol):
    def resumen_pendientes(self) -> ResumenPendientes: ...

from finanzas.modulos.categorias.politica import (
    CAMPO_POR_TIPO,
    COLORES_CATEGORIA,
    CONDICIONES,
    CONDICION_TEXTO,
    ICONOS_CATEGORIA,
    SIN_CATEGORIA_NO_CATEGORIZABLE,
    SIN_CATEGORIZAR,
    clase_para_tipo,
    condiciones_de,
    es_categorizable,
    es_pendiente,
    regla_posible,
    reglas_posibles,
)

from finanzas.modulos.categorias.contratos import (
    Asignacion,
    CategoriaNoEncontrada,
    ErrorCategorizacion,
    MovimientoNoEncontrado,
    ReglaNoEncontrada,
    RestauracionNoPermitida,
)

from finanzas.modulos.categorias.grupos import (
    GrupoPendientes,
    MAXIMO_IDS_GRUPO,
    agrupar_pendientes,
)

from finanzas.modulos.categorias.presentacion import (
    frase_condiciones,
    frase_regla,
)

from .politica import normalizar, campo_para_tipo
from .grupos import clave_grupo
from .presentacion import pesos
from .contratos import CopiaCategoria, CopiaRegla
