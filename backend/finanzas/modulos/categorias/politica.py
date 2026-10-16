"""Política única de categorías y reglas, sin SQL, HTTP ni lectores de fuentes."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from finanzas.modulos.categorias.destinos import recortar_destino
from finanzas.modulos.categorias.contratos import Categoria, ErrorCategorizacion
from .condiciones import (CONDICION_TEXTO, CONDICION_MONTO, CONDICION_TEXTO_Y_MONTO,
    CONDICIONES, CondicionesRegla, condiciones_de)

CAMPO_POR_TIPO = {"compra": "comercio", "transferencia": "cuenta_destino", "ingreso": "quien_envia"}
TIPOS_CATEGORIZABLES = tuple(CAMPO_POR_TIPO)
CLASE_POR_TIPO = {"compra": "gasto", "transferencia": "gasto", "ingreso": "ingreso"}
_INVISIBLES_EXTRA = frozenset("\u034f\u180e")

def normalizar(texto: str) -> str:
    """Forma canónica para comparar descripciones.

    1. Sin caracteres de formato invisibles (categoría Unicode ``Cf``, como
       U+200B, y U+034F y U+180E), igual que el extractor: un correo puede
       traerlos pegados al comercio sin que se vean.
    2. Unicode NFC: "é" compuesta (U+00E9) y "e" + tilde combinante (U+0301)
       quedan iguales.
    3. ``casefold()``: ignora mayúsculas (más completo que ``lower()``).
    4. Espacios colapsados: sin espacios al inicio o al final y uno solo
       entre palabras (también tabulaciones y saltos de línea).
    """
    visible = "".join(
        c for c in texto if unicodedata.category(c) != "Cf" and c not in _INVISIBLES_EXTRA
    )
    return " ".join(unicodedata.normalize("NFC", visible).casefold().split())


def campo_para_tipo(tipo: str) -> str | None:
    """Campo de regla que corresponde al tipo, o ``None`` si no se categoriza."""
    return CAMPO_POR_TIPO.get(tipo)


def es_categorizable(tipo: str) -> bool:
    """``True`` si a un movimiento de este tipo se le puede asignar categoría."""
    return campo_para_tipo(tipo) is not None


def clase_para_tipo(tipo: str) -> str | None:
    """Clase de categoría que acepta el tipo (``gasto`` o ``ingreso``), o ``None`` si no se categoriza."""
    return CLASE_POR_TIPO.get(tipo)


# Qué va a la bandeja "Sin categorizar" y cuenta como pendiente: los tipos de
# ``TIPOS_PENDIENTES`` sin categoría. Es la **única** definición: la usan
# ``es_pendiente`` (un movimiento suelto, para la API) y la consulta de la
# bandeja y del conteo (``_pendientes_de_categorizar``). Son los gastos
# (compras y transferencias) y, desde el ítem 15, los ingresos.
TIPOS_PENDIENTES = TIPOS_CATEGORIZABLES


def es_pendiente(tipo: str, categoria_id: int | None) -> bool:
    """``True`` si el movimiento va en la bandeja "Sin categorizar"."""
    return tipo in TIPOS_PENDIENTES and categoria_id is None


def _texto_para_tipo(tipo: str, descripcion: str) -> str:
    texto = normalizar(descripcion)
    return recortar_destino(texto) if tipo == "transferencia" else texto


def regla_posible(tipo: str, descripcion: str) -> tuple[str, str] | None:
    """``(campo, texto)`` de la regla por texto que crearía "recordar", o ``None`` si no se puede.

    No se puede si el tipo no se categoriza o la descripción normalizada
    queda vacía. ``texto`` es el normalizado (``normalizar``): lo que guarda
    la regla y con lo que coincide. Es la opción ``texto`` de
    ``condiciones_de_regla``.
    """
    campo = campo_para_tipo(tipo)
    texto = _texto_para_tipo(tipo, descripcion)
    if campo is None or not texto:
        return None
    return campo, texto


# --- Condiciones de una regla (ítem 17) ------------------------------------------------
#
# Una regla siempre dice el tipo de movimiento (``campo``) y además una o dos
# condiciones: el texto exacto (``texto``) y el monto exacto
# (``monto_centavos``). Al categorizar se elige cuál crear:
# Las que se **ofrecen** al categorizar cada tipo (``reglas_posibles``), según el
# prototipo aprobado y TEXTOS.md: las transferencias ofrecen las tres ("Transferencias
# a LAURA GÓMEZ EJEMPLO", "Transferencias de $6.200", "Las dos cosas juntas") y, por
# decisión del dueño, también los ingresos ("ingreso de «…» por $400.000" del
# prototipo de Categorías); las compras, solo por texto. Crear las demás se puede igual si se
# piden (``asignar_con_detalle``): una regla por monto nunca alcanza a otro tipo.
CONDICIONES_OFRECIDAS = {
    "compra": (CONDICION_TEXTO,),
    "transferencia": (CONDICION_TEXTO, CONDICION_MONTO, CONDICION_TEXTO_Y_MONTO),
    "ingreso": (CONDICION_TEXTO, CONDICION_MONTO, CONDICION_TEXTO_Y_MONTO),
}
assert set(CONDICIONES_OFRECIDAS) == set(TIPOS_CATEGORIZABLES)






def condiciones_de_regla(
    tipo: str, descripcion: str, monto_centavos: int, condiciones: str = CONDICION_TEXTO
) -> CondicionesRegla | None:
    """La regla que crearía "recordar" con esas ``condiciones``, o ``None`` si no se puede.

    No se puede si el tipo no se categoriza, si hace falta el texto y la
    descripción normalizada queda vacía, o si hace falta el monto y no es un
    entero positivo.
    """
    if condiciones not in CONDICIONES:
        return None
    campo = campo_para_tipo(tipo)
    if campo is None:
        return None
    texto = monto = None
    if condiciones in (CONDICION_TEXTO, CONDICION_TEXTO_Y_MONTO):
        texto = _texto_para_tipo(tipo, descripcion)
        if not texto:
            return None
    if condiciones in (CONDICION_MONTO, CONDICION_TEXTO_Y_MONTO):
        if not isinstance(monto_centavos, int) or isinstance(monto_centavos, bool) or monto_centavos <= 0:
            return None
        monto = monto_centavos
    return CondicionesRegla(campo=campo, texto=texto, monto_centavos=monto)


MENSAJE_SIN_DESCRIPCION = "Este movimiento no tiene descripción: no se puede recordar la regla por texto."
MENSAJE_MONTO_INVALIDO = "El monto de este movimiento no es válido: no se puede recordar la regla por monto."


def motivo_sin_regla(descripcion: str, monto_centavos: int, condiciones: str) -> str:
    """Por qué ``condiciones_de_regla`` no puede crear la regla (para el dueño, sin datos).

    Para un tipo categorizable y ``condiciones`` válidas, la causa es que falta
    la descripción (si la regla mira el texto) o que el monto no es un entero
    positivo (si mira el monto). Si fallan las dos, se dice primero la descripción.
    """
    if condiciones in (CONDICION_TEXTO, CONDICION_TEXTO_Y_MONTO) and not normalizar(descripcion):
        return MENSAJE_SIN_DESCRIPCION
    return MENSAJE_MONTO_INVALIDO


def reglas_posibles(tipo: str, descripcion: str, monto_centavos: int) -> list[CondicionesRegla]:
    """Las reglas que se ofrecen al categorizar el movimiento (``CONDICIONES_OFRECIDAS``), en ese orden.

    Solo las que se pueden crear: sin descripción no hay opciones por texto.
    """
    posibles = (
        condiciones_de_regla(tipo, descripcion, monto_centavos, condiciones)
        for condiciones in CONDICIONES_OFRECIDAS.get(tipo, ())
    )
    return [posible for posible in posibles if posible is not None]


# Cómo coincide y cuál gana
# -------------------------
# Una regla coincide con un movimiento si es de su tipo (``campo``) y **todas**
# sus condiciones se cumplen: el texto, si lo tiene, es igual a la descripción
# normalizada; el monto, si lo tiene, es igual al monto exacto en centavos.
#
# Si coinciden varias, gana la más específica (``especificidad``):
#     texto + monto (3)  >  solo texto (2)  >  solo monto (1)
# El texto va antes que el monto porque identifica a quién se paga (un comercio
# o una cuenta), mientras que un mismo monto lo comparten pagos sin relación.
# Desempate: la más reciente (``id`` mayor). Con el índice único
# ``ux_reglas_condiciones`` no puede haber dos reglas del mismo tipo con la
# misma especificidad que coincidan con un mismo movimiento (tendrían las mismas
# condiciones), pero el desempate deja el resultado determinista pase lo que pase.

def especificidad(texto: str | None, monto_centavos: int | None) -> int:
    """3 si la regla tiene texto y monto, 2 si solo texto, 1 si solo monto."""
    return (2 if texto is not None else 0) + (1 if monto_centavos is not None else 0)


def borrado_reversible(movimientos: int, reglas: int) -> bool:
    """¿Borrar una categoría con estos movimientos y reglas se puede deshacer?

    Solo si no tiene ninguno: entonces no hay nada que mover y basta volver a
    crearla. Es la única regla: ``borrar_categoria`` la usa para dar la copia y
    la API la expone en cada categoría (``se_puede_deshacer_borrado``).
    """
    return movimientos == 0 and reglas == 0


@dataclass(frozen=True)
class ReglaEvaluable:
    id: int
    categoria_id: int
    campo: str
    texto: str | None
    monto_centavos: int | None
    modo_texto: str
    origen_regla: str


def elegir_regla(reglas: list[ReglaEvaluable], tipo: str, descripcion: str,
                 monto_centavos: int | None, origen: str = "gmail",
                 referencia: str | None = None) -> ReglaEvaluable | None:
    """Coincidencia y prioridad únicas, sobre datos normalizados por persistencia."""
    campo = campo_para_tipo(tipo)
    if campo is None:
        return None
    texto = _texto_para_tipo(tipo, descripcion) or None
    for regla in sorted(reglas, key=lambda r: (especificidad(r.texto, r.monto_centavos), r.id), reverse=True):
        if regla.campo != campo or (regla.monto_centavos is not None and regla.monto_centavos != monto_centavos):
            continue
        if regla.origen_regla == "extracto" and origen != "extracto":
            continue
        patron = regla.texto
        valor = normalizar(referencia) if origen == "extracto" and campo == "cuenta_destino" and regla.modo_texto == "exacta" and patron and patron.startswith("*") and referencia else texto
        if patron is None or (valor is not None and (
            (regla.modo_texto == "exacta" and valor == patron)
            or (regla.modo_texto == "contiene" and patron in valor)
            or (regla.modo_texto == "empieza_por" and valor.startswith(patron))
        )):
            return regla
    return None


COLORES_CATEGORIA = (
    "cat-mercado",
    "cat-restaurantes",
    "cat-transporte",
    "cat-vivienda",
    "cat-salud",
    "cat-entretenimiento",
    "cat-compras",
    "cat-antojos",
    "cat-otros",
    "cat-sueldo",
    "cat-prestamos",
    "cat-otros-ingresos",
)
ICONOS_CATEGORIA = (
    "shopping-basket",
    "utensils",
    "bus",
    "house",
    "heart-pulse",
    "ticket",
    "shopping-bag",
    "ice-cream-cone",
    "shapes",
    "briefcase",
    "handshake",
    "coins",
)
MAXIMO_NOMBRE = 40
# Lo que la app muestra en lugar de una categoría: una categoría con ese
# nombre confundiría (``reporte`` los usa con estos mismos textos).
SIN_CATEGORIZAR = "Sin categorizar"
SIN_CATEGORIA_NO_CATEGORIZABLE = "—"


def texto_clase(clase: str) -> str:
    """``gasto`` o ``ingreso``, para los mensajes."""
    return "ingreso" if clase == "ingreso" else "gasto"


def limpiar_nombre(nombre: str) -> str:
    """El nombre como se guarda: NFC y sin espacios de más. Lanza ``ErrorCategorizacion`` si no sirve.

    No sirve si queda vacío, pasa de ``MAXIMO_NOMBRE`` caracteres, trae
    caracteres de control o invisibles, o es lo que la app muestra en lugar
    de una categoría ("Sin categorizar", "—").
    """
    if not isinstance(nombre, str):
        raise ErrorCategorizacion("Escribe el nombre de la categoría.")
    limpio = " ".join(unicodedata.normalize("NFC", nombre).split())
    if not limpio:
        raise ErrorCategorizacion("Escribe el nombre de la categoría.")
    if len(limpio) > MAXIMO_NOMBRE:
        raise ErrorCategorizacion(f"El nombre puede tener hasta {MAXIMO_NOMBRE} caracteres.")
    if any(unicodedata.category(c).startswith("C") or c in _INVISIBLES_EXTRA for c in limpio):
        raise ErrorCategorizacion("El nombre tiene caracteres no válidos.")
    if normalizar(limpio) in (normalizar(SIN_CATEGORIZAR), normalizar(SIN_CATEGORIA_NO_CATEGORIZABLE)):
        raise ErrorCategorizacion("Ese nombre lo usa la app; elige otro.")
    return limpio


def validar_color_e_icono(color: str, icono: str) -> None:
    if color not in COLORES_CATEGORIA:
        raise ErrorCategorizacion("Elige un color de la paleta.")
    if icono not in ICONOS_CATEGORIA:
        raise ErrorCategorizacion("Elige un ícono de la lista.")



def comprobar_unicidad(otras: list[Categoria], nombre: str, clase: str, color: str, icono: str) -> None:
    clave = normalizar(nombre)
    if any(o.clase == clase and normalizar(o.nombre) == clave for o in otras):
        raise ErrorCategorizacion(f"Ya hay una categoría de {texto_clase(clase)} con ese nombre.")
    if any(o.color == color and o.icono == icono for o in otras):
        raise ErrorCategorizacion("Otra categoría ya tiene ese color con ese ícono; cambia uno de los dos.")
