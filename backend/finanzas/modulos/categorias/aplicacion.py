"""Consulta del piloto; la transacción pertenece al caso de uso."""
from datetime import datetime

from finanzas.modulos.categorias.contratos import CategoriaConsultada, UnidadDeTrabajoCategorias
from finanzas.modulos.categorias.politica import borrado_reversible


class ConsultarCategorias:
    def __init__(self, unidad: UnidadDeTrabajoCategorias):
        self._unidad = unidad

    def ejecutar(self, desde: datetime, hasta: datetime, clase: str | None = None) -> list[CategoriaConsultada]:
        with self._unidad.lectura():
            uso = self._unidad.movimientos.uso_por_categoria(desde, hasta)
            filas = self._unidad.categorias.consultar_con_uso(desde, hasta, clase, uso=uso)
            return [CategoriaConsultada(fila, borrado_reversible(fila.movimientos_total, fila.reglas)) for fila in filas]
