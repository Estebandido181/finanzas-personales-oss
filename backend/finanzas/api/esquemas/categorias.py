"""Contrato HTTP: categorias."""
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StrictBool, StrictStr
from finanzas.modulos.categorias import publico as categorizacion
from .comunes import CampoRegla, ClaseCategoria, ColorCategoria, CondicionRegla, Entrada, IconoCategoria, IdEntrada, MONTO_CONDICION, Mes, NombreCategoria, TEXTO_SIN_CONDICION, TipoRegla
from .deshacer import Deshacer


class Categoria(BaseModel):
    """Una categoría. ``color`` e ``icono`` son claves (token y ícono de Lucide), no valores."""

    id: int
    nombre: str
    clase: ClaseCategoria
    color: ColorCategoria
    icono: IconoCategoria


class CategoriaConUso(Categoria):
    """Una categoría con cuántos movimientos y reglas tiene.

    ``movimientos_mes``: los del mes pedido. ``movimientos_total``: los de
    todos los meses (son los que pasan a otra categoría si se borra).
    ``reglas``: sus reglas (también pasan).
    """

    movimientos_mes: int
    movimientos_total: int
    reglas: int
    se_puede_deshacer_borrado: bool = Field(
        description=(
            "Ítem 38: borrarla se hace al tocar y se puede deshacer (no tiene movimientos ni reglas). "
            "Si es ``false``, borrarla pide confirmación y a qué categoría pasan sus movimientos y reglas."
        )
    )


class ListaCategorias(BaseModel):
    """Primero las de gasto y luego las de ingreso; en cada clase, por orden de creación."""

    mes: Mes
    categorias: list[CategoriaConUso]


class CategoriaEntrada(Entrada):
    """Categoría nueva. Nombre único en su clase; el par ``color`` + ``icono``, único entre todas."""

    nombre: NombreCategoria
    clase: ClaseCategoria
    color: ColorCategoria
    icono: IconoCategoria


class EditarCategoriaEntrada(Entrada):
    """Lo que se cambia (al menos uno). La clase no se cambia."""

    nombre: NombreCategoria | None = None
    color: ColorCategoria | None = None
    icono: IconoCategoria | None = None


class CategoriaBorrada(BaseModel):
    """Cuántos movimientos y reglas pasaron a ``destino`` (``null`` si no había nada que pasar)."""

    movimientos_movidos: int
    reglas_movidas: int
    destino: Categoria | None
    deshacer: Deshacer | None = Field(
        description="Ítem 38: solo si no movió nada (no tenía movimientos ni reglas); si no, ``null``."
    )


class ReglaAplicada(BaseModel):
    modo_texto: Literal["exacta", "contiene", "empieza_por"] = "exacta"
    origen_regla: Literal["todos", "extracto"] = "todos"
    """Una regla (ítem 17): los movimientos de ``tipo_movimiento`` que cumplen todas sus condiciones.

    ``condiciones`` dice cuáles tiene además del tipo: ``texto`` (``campo``
    igual a ``texto``), ``monto`` (monto igual a ``monto_centavos``) o
    ``texto_y_monto`` (las dos). ``texto`` está normalizado: identifica la
    regla, no la descripción exacta del movimiento. ``frase``: las condiciones
    en palabras, p. ej. «transferencia de $3.200» o «compra en «tienda»».
    """

    id: int
    tipo_movimiento: TipoRegla
    campo: CampoRegla
    texto: str | None = Field(description=TEXTO_SIN_CONDICION)
    monto_centavos: int | None = Field(description=MONTO_CONDICION)
    condiciones: CondicionRegla
    frase: str


class ReglaPosible(BaseModel):
    """La regla por texto que guardaría ``recordar: true``: ``campo`` igual a ``texto`` (ya normalizado).

    Es la opción ``texto`` de ``reglas_posibles`` (se mantiene por compatibilidad).
    """

    campo: CampoRegla
    texto: str


class OpcionRegla(BaseModel):
    """Una regla que se ofrece crear al categorizar (ítem 17), para ``condiciones`` en el PUT.

    Mismos campos que ``ReglaAplicada`` (sin ``id``): ``texto`` ``null`` si no
    mira el texto y ``monto_centavos`` ``null`` si no mira el monto.
    """

    condiciones: CondicionRegla
    tipo_movimiento: TipoRegla
    campo: CampoRegla
    texto: str | None = Field(description=TEXTO_SIN_CONDICION)
    monto_centavos: int | None = Field(description=MONTO_CONDICION)
    frase: str


class CategorizarGrupoEntrada(Entrada):
    """Categorizar un grupo de ``grupos`` (ítem 38): su ``clave``, sus ``ids`` y la categoría."""

    clave: Annotated[StrictStr, Field(min_length=3, max_length=1000)]
    ids: Annotated[list[IdEntrada], Field(min_length=1, max_length=categorizacion.MAXIMO_IDS_GRUPO)]
    categoria_id: IdEntrada
    modo_regla: Literal["exacta", "contiene", "empieza_por"] = "exacta"


class CategorizarEntrada(Entrada):
    """``condiciones`` (ítem 17, solo con ``recordar: true``): qué regla crear.

    ``texto`` (por omisión, como en la v1), ``monto`` o ``texto_y_monto``. Se
    puede pedir cualquiera que el movimiento permita (por texto hace falta una
    descripción), aunque no esté en ``reglas_posibles``.
    """

    categoria_id: IdEntrada
    recordar: StrictBool = False
    condiciones: CondicionRegla | None = None


class Categorizado(BaseModel):
    """``categorizados``: el pedido más los que alcanzó la regla (si se recordó).

    El movimiento pedido queda con ``origen_categoria`` ``manual``; los que
    alcanzó la regla, con ``regla``. ``regla``: la regla guardada (nueva, o
    la que ya había para ese texto, ahora con esta categoría); ``null`` si
    no se pidió ``recordar``.
    """

    categorizados: int
    regla_guardada: bool
    regla: ReglaAplicada | None


class Regla(BaseModel):
    modo_texto: Literal["exacta", "contiene", "empieza_por"] = "exacta"
    origen_regla: Literal["todos", "extracto"] = "todos"
    """Regla recordada: los movimientos de ``tipo_movimiento`` que cumplen todas sus condiciones.

    Condiciones como en ``ReglaAplicada``. ``frase``: la regla en palabras,
    p. ej. «Si es una compra en «tienda ejemplo», va a Mercado», «Si es una
    transferencia de $3.200, va a Transporte» o «Si es un ingreso de «persona»
    por $400.000, va a Préstamos» (``texto`` tal como lo guarda la regla).
    Ordenadas por tipo y, dentro de cada tipo, en el orden en que ganan
    (texto y monto, luego texto, luego monto).
    """

    id: int
    tipo_movimiento: TipoRegla
    campo: CampoRegla
    texto: str | None = Field(description=TEXTO_SIN_CONDICION)
    monto_centavos: int | None = Field(description=MONTO_CONDICION)
    condiciones: CondicionRegla
    categoria: Categoria
    frase: str


class ListaReglas(BaseModel):
    reglas: list[Regla]


class ReglaBorrada(BaseModel):
    """Resultado de borrar una regla: su ``id`` y cómo deshacerlo (ítem 38)."""

    id: int
    deshacer: Deshacer
