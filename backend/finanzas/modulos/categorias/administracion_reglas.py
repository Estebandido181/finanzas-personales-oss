"""Borrado y restauración de reglas dentro de la transacción del caso de uso."""
from dataclasses import asdict

from finanzas.modulos.categorias.contratos import (
    CopiaRegla, ReglaNoEncontrada, RestauracionNoPermitida, UnidadAdministracionReglas,
)
from finanzas.modulos.categorias.politica import CAMPO_POR_TIPO, CLASE_POR_TIPO, _texto_para_tipo


class AdministrarReglas:
    def __init__(self, unidad: UnidadAdministracionReglas):
        self._unidad = unidad

    def borrar(self, regla_id: int) -> CopiaRegla:
        with self._unidad.escritura(inmediata=True):
            regla = self._unidad.reglas.buscar(regla_id)
            if regla is None:
                raise ReglaNoEncontrada("La regla no existe.")
            movimientos = self._unidad.movimientos.ids_por_regla(regla_id)
            self._unidad.movimientos.desvincular_regla(regla_id)
            self._unidad.reglas.borrar(regla_id)
        return CopiaRegla(**asdict(regla), movimientos=movimientos)

    def restaurar(self, copia: CopiaRegla) -> int:
        tipo = {campo: tipo for tipo, campo in CAMPO_POR_TIPO.items()}[copia.campo]
        # Una copia anterior al recorte nunca reintroduce la cuenta completa.
        texto = None if copia.texto is None else _texto_para_tipo(tipo, copia.texto)
        with self._unidad.escritura(inmediata=True):
            categoria = self._unidad.categorias.buscar(copia.categoria_id)
            if categoria is None or categoria.clase != CLASE_POR_TIPO[tipo]:
                raise RestauracionNoPermitida("No se puede deshacer: la categoría de la regla ya no existe.")
            if self._unidad.reglas.existe_equivalente(copia, texto):
                raise RestauracionNoPermitida("No se puede deshacer: ya hay una regla con esas mismas condiciones.")
            nuevo_id = self._unidad.reglas.restaurar(copia, texto)
            self._unidad.movimientos.revincular_regla_si_compatible(copia.movimientos, copia.categoria_id, nuevo_id)
            return nuevo_id
