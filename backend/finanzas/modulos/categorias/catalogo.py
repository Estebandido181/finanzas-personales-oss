"""Consultas tipadas del catálogo y de los pendientes del registro."""
from finanzas.modulos.categorias.contratos import (
    Categoria, ReglaConCategoria, ReglaGuardada, ResumenPendientes, UnidadConsultaCatalogo,
)
from finanzas.modulos.movimientos.publico import MovimientoPendiente


class ConsultarCatalogo:
    def __init__(self, unidad: UnidadConsultaCatalogo):
        self._unidad = unidad

    def pendientes(self) -> list[MovimientoPendiente]:
        return self._unidad.movimientos.consultar_pendientes()

    def resumen_pendientes(self) -> ResumenPendientes:
        resumen = self._unidad.movimientos.resumir_pendientes()
        return ResumenPendientes(resumen.cuantos, resumen.gastos_centavos, resumen.ingresos_centavos)

    def categorias(self, clase: str | None = None) -> list[Categoria]:
        return self._unidad.categorias.listar(clase)

    def categoria(self, categoria_id: int) -> Categoria | None:
        return self._unidad.categorias.buscar(categoria_id)

    def reglas(self) -> list[ReglaConCategoria]:
        return self._unidad.reglas.listar_con_categoria()

    def regla(self, regla_id: int) -> ReglaGuardada | None:
        return self._unidad.reglas.buscar(regla_id)
