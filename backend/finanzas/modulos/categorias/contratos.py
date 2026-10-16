"""Datos y puertos estrechos del piloto: no exponen SQL ni HTTP."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .condiciones import CondicionesRegla
from finanzas.modulos.movimientos.publico import RegistroCategorizable


@dataclass(frozen=True)
class CategoriaConUso:
    id: int
    nombre: str
    clase: str
    color: str
    icono: str
    movimientos_mes: int
    movimientos_total: int
    reglas: int


@dataclass(frozen=True)
class CategoriaConsultada:
    categoria: CategoriaConUso
    se_puede_deshacer_borrado: bool


class RepositorioCategorias(Protocol):
    def consultar_con_uso(self, desde: datetime, hasta: datetime, clase: str | None = None, *, uso: dict[int, tuple[int, int]]) -> list[CategoriaConUso]: ...


class UnidadDeTrabajoCategorias(Protocol):
    categorias: RepositorioCategorias
    movimientos: RegistroCategorizable
    def lectura(self) -> AbstractContextManager[None]: ...


class ConsultaCategorias(Protocol):
    def ejecutar(self, desde: datetime, hasta: datetime, clase: str | None = None) -> list[CategoriaConsultada]: ...


class ErrorCategorizacion(Exception):
    """La asignación no es válida (categoría inexistente, tipo no categorizable...).

    Los mensajes son para el dueño y no incluyen datos del movimiento.
    """

class CategoriaNoEncontrada(ErrorCategorizacion):
    """La categoría pedida no existe."""

class RestauracionNoPermitida(ErrorCategorizacion):
    """Lo borrado ya no se puede restaurar (algo cambió mientras tanto). El mensaje es para el dueño."""

@dataclass(frozen=True)
class CopiaCategoria:
    """Una categoría borrada sin movimientos ni reglas."""

    id: int
    nombre: str
    clase: str
    color: str
    icono: str

@dataclass(frozen=True)
class CategoriaBorrada:
    """Resultado de ``borrar_categoria``: cuántos movimientos y reglas pasaron a ``destino_id``.

    ``copia`` (ítem 38): lo necesario para restaurarla, solo si el borrado se
    puede deshacer (``borrado_reversible``); si no, ``None``.
    """

    movimientos: int
    reglas: int
    destino_id: int | None
    copia: CopiaCategoria | None = None


@dataclass(frozen=True)
class Categoria:
    id: int
    nombre: str
    clase: str
    color: str
    icono: str


class RepositorioAdministracionCategorias(Protocol):
    def buscar(self, categoria_id: int) -> Categoria | None: ...
    def otras(self, excepto: int | None) -> list[Categoria]: ...
    def insertar(self, nombre: str, clase: str, color: str, icono: str, id_preferido: int | None = None) -> int: ...
    def actualizar(self, categoria_id: int, nombre: str, color: str, icono: str) -> None: ...
    def contar_clase(self, clase: str) -> int: ...
    def contar_reglas(self, categoria_id: int) -> int: ...
    def mover_reglas(self, categoria_id: int, destino_id: int) -> None: ...
    def borrar(self, categoria_id: int) -> None: ...


class UnidadAdministracionCategorias(Protocol):
    categorias: RepositorioAdministracionCategorias
    movimientos: RegistroCategorizable
    def escritura(self, inmediata: bool = False) -> AbstractContextManager[None]: ...


class ReglaNoEncontrada(ErrorCategorizacion):
    """La regla pedida no existe."""


@dataclass(frozen=True)
class CopiaRegla:
    """Una regla borrada y los movimientos que había categorizado (que quedaron sin ``regla_id``)."""

    id: int
    campo: str
    texto: str | None
    monto_centavos: int | None
    categoria_id: int
    movimientos: tuple[int, ...]
    modo_texto: str = "exacta"
    origen_regla: str = "todos"
    texto_visible: str | None = None



@dataclass(frozen=True)
class ReglaGuardada:
    id: int
    campo: str
    texto: str | None
    monto_centavos: int | None
    categoria_id: int
    modo_texto: str
    origen_regla: str
    texto_visible: str | None


class RepositorioAdministracionReglas(Protocol):
    def buscar(self, regla_id: int) -> ReglaGuardada | None: ...
    def existe_equivalente(self, copia: CopiaRegla, texto: str | None) -> bool: ...
    def borrar(self, regla_id: int) -> None: ...
    def restaurar(self, copia: CopiaRegla, texto: str | None) -> int: ...


class UnidadAdministracionReglas(Protocol):
    categorias: RepositorioAdministracionCategorias
    reglas: RepositorioAdministracionReglas
    movimientos: RegistroCategorizable
    def escritura(self, inmediata: bool = False) -> AbstractContextManager[None]: ...


class MovimientoNoEncontrado(ErrorCategorizacion):
    """El movimiento pedido no existe."""


@dataclass(frozen=True)
class Asignacion:
    """Resultado de ``asignar_categoria``.

    ``total``: cuántos movimientos quedaron categorizados (el pedido más los
    que alcanzó la regla). ``regla_id``: la regla guardada, o ``None`` si no
    se pidió recordar.
    """

    total: int
    regla_id: int | None



class RepositorioReglasCategorizacion(RepositorioAdministracionReglas, Protocol):
    def candidatas(self, campo: str, monto_centavos: int | None) -> list[ReglaGuardada]: ...
    def guardar(self, nueva: CondicionesRegla, categoria_id: int) -> int: ...


class UnidadAsignacionCategorias(Protocol):
    categorias: RepositorioAdministracionCategorias
    reglas: RepositorioReglasCategorizacion
    movimientos: RegistroCategorizable
    def escritura(self, inmediata: bool = False) -> AbstractContextManager[None]: ...


@dataclass(frozen=True)
class CategoriaDeEntrada:
    categoria_id: int | None = None
    origen_categoria: str | None = None
    regla_id: int | None = None


class ClasificarEntrada(Protocol):
    def categoria_para_entrada(self, tipo: str, descripcion: str, monto_centavos: int,
                               categoria_al_leer: str | None = None) -> CategoriaDeEntrada: ...


@dataclass(frozen=True)
class ResumenPendientes:
    """La bandeja "Sin categorizar" de todos los meses.

    ``cuantos``: todos los pendientes, gastos e ingresos. Los montos van
    **aparte** y nunca se suman entre sí: ``gastos_centavos`` (compras y
    transferencias) e ``ingresos_centavos`` (ingresos).
    """

    cuantos: int
    gastos_centavos: int
    ingresos_centavos: int



@dataclass(frozen=True)
class ReglaConCategoria(ReglaGuardada):
    categoria: str
    categoria_clase: str
    categoria_color: str
    categoria_icono: str


class CatalogoCategorias(RepositorioAdministracionCategorias, Protocol):
    def listar(self, clase: str | None = None) -> list[Categoria]: ...


class CatalogoReglas(RepositorioAdministracionReglas, Protocol):
    def listar_con_categoria(self) -> list[ReglaConCategoria]: ...


class UnidadConsultaCatalogo(Protocol):
    categorias: CatalogoCategorias
    reglas: CatalogoReglas
    movimientos: RegistroCategorizable
    def lectura(self) -> AbstractContextManager[None]: ...
