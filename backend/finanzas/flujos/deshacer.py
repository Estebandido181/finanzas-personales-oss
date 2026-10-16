"""Restauración por el módulo propietario; no consume tokens ni conoce HTTP."""
from typing import Protocol
from finanzas.modulos.saldo.publico import CopiaIngreso, ServicioSaldo
from finanzas.modulos.categorias.publico import CopiaCategoria, CopiaRegla


class RestaurarCategorias(Protocol):
    def restaurar(self, copia: CopiaCategoria) -> int: ...


class RestaurarReglas(Protocol):
    def restaurar(self, copia: CopiaRegla) -> int: ...


def restaurar(copia, saldo: ServicioSaldo, categorias: RestaurarCategorias, reglas: RestaurarReglas):
    if isinstance(copia, CopiaIngreso):
        nuevo_id, saldo_despues = saldo.restaurar_ingreso(copia)
        return dict(que="ingreso", id=nuevo_id, saldo_centavos=saldo_despues)
    if isinstance(copia, CopiaRegla):
        return dict(que="regla", id=reglas.restaurar(copia), saldo_centavos=None)
    if isinstance(copia, CopiaCategoria):
        return dict(que="categoria", id=categorias.restaurar(copia), saldo_centavos=None)
    return None
