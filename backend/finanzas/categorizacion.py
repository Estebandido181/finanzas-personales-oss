"""Categorización: categorías propias, reglas recordadas y asignación manual.

Todas las funciones reciben una conexión de SQLAlchemy (de ``db.conectar``)
y arman las consultas con expresiones de SQLAlchemy Core (los valores van
siempre como parámetros; nunca se arma SQL con texto del usuario). Las que
escriben lo hacen dentro de una transacción (``db.transaccion``): o se aplica
todo o nada.

Qué se categoriza
-----------------
Los gastos y, desde el ítem 15, los ingresos:

* ``compra`` (gasto): la regla se busca por ``comercio`` (la descripción del
  movimiento es el comercio, p. ej. ``MERPAGO*TIENDA``).
* ``transferencia`` (gasto): la regla se busca por ``cuenta_destino`` (la
  descripción es la cuenta destino, p. ej. ``*5678``, o, en las
  transferencias a llave Bre-B, el nombre de quien recibe, p. ej. ``NOMBRE
  DESTINO EJEMPLO``; la regla guarda ese nombre normalizado en el mismo campo
  ``cuenta_destino``).
* ``ingreso``: la regla se busca por ``quien_envia`` (la descripción es quien
  envía en los avisos "Recibiste", o el texto del dueño en los manuales).

``ajuste`` **no** se categoriza: no es gasto ni ingreso.

Cada categoría tiene una **clase** (``gasto`` | ``ingreso``): una compra o
transferencia solo acepta categorías de gasto y un ingreso solo de ingreso
(``clase_para_tipo``). Lo mismo vale para las reglas, porque toman la
categoría del movimiento desde el que se crean, y al borrar una categoría sus
movimientos y reglas solo pueden pasar a otra de la misma clase. Así un
ingreso nunca termina sumado en el gasto de una categoría.

Pendientes ("Sin categorizar"): los movimientos categorizables sin
categoría, gastos e ingresos. Cuentan juntos en el número de pendientes,
pero sus montos van siempre aparte (``resumen_sin_categorizar``): dinero que
sale y que entra no se suman en una sola cifra.

Cómo coincide una regla
-----------------------
Desde el ítem 17 (D21) una regla combina condiciones: el tipo de movimiento
(``campo``, siempre) + el texto exacto (opcional) + el monto exacto en
centavos (opcional), con al menos una además del tipo. Coincide si se cumplen
**todas** las que tiene; si coinciden varias, gana la más específica (texto +
monto > texto > monto; ver ``regla_que_coincide``). Una regla por monto solo
alcanza a su tipo: "transferencia + $3.200" nunca categoriza una compra.

La regla guarda el texto ya normalizado (``normalizar``) y coincide solo por
**igualdad exacta** con la descripción normalizada del movimiento, no por
"contiene". Por qué:

* es predecible: el dueño crea la regla desde la descripción exacta de un
  movimiento, y sabe que solo afectará a ese mismo comercio o cuenta;
* evita categorizar de más: con "contiene", una regla para ``D1`` capturaría
  ``D1 SAS`` o cualquier comercio que incluya "D1", y ``MERPAGO*TIENDA``
  capturaría ``MERPAGO*TIENDA2``, que puede ser otro negocio;
* no hace falta nada más: los avisos del banco repiten el nombre del
  comercio igual cada vez; la normalización absorbe las diferencias menores
  (mayúsculas, espacios repetidos y tildes compuestas o descompuestas).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from sqlalchemy import Connection

from finanzas.modulos.categorias.destinos import recortar_destino
from finanzas.infraestructura.persistencia.esquema import CLASE_GASTO, CLASE_INGRESO, CLASES_CATEGORIA

# Shim R1: consumidores históricos delegan a una sola política.
from finanzas.modulos.categorias.politica import (
    normalizar,
    campo_para_tipo,
    es_categorizable,
    clase_para_tipo,
    es_pendiente,
    _texto_para_tipo,
    regla_posible,
    CondicionesRegla,
    condiciones_de,
    condiciones_de_regla,
    motivo_sin_regla,
    reglas_posibles,
    especificidad,
    borrado_reversible,
    ReglaEvaluable,
    elegir_regla,
    CAMPO_POR_TIPO,
    TIPOS_CATEGORIZABLES,
    CLASE_POR_TIPO,
    TIPOS_PENDIENTES,
    CONDICION_TEXTO,
    CONDICION_MONTO,
    CONDICION_TEXTO_Y_MONTO,
    CONDICIONES,
    CONDICIONES_OFRECIDAS,
    MENSAJE_SIN_DESCRIPCION,
    MENSAJE_MONTO_INVALIDO,
    _INVISIBLES_EXTRA,
)

# Color e ícono de una categoría: claves, no valores sueltos. ``color`` es un
# token de ``frontend/diseno/tokens.css`` (``cat-mercado`` es la variable
# ``--cat-mercado``, que cambia en modo oscuro) e ``icono`` un ícono de Lucide.
# Son la paleta de época y los íconos de SISTEMA.md ("Categorías nuevas": se
# elige de esta misma paleta y de una lista corta). "Sin categorizar" no es
# una categoría: su color y su ícono no se pueden elegir.
from finanzas.modulos.categorias.contratos import (
    ErrorCategorizacion, CategoriaNoEncontrada, RestauracionNoPermitida,
    CopiaCategoria, CategoriaBorrada, ReglaNoEncontrada, CopiaRegla, MovimientoNoEncontrado, Asignacion, ResumenPendientes,
)
from finanzas.modulos.categorias.politica import (
    COLORES_CATEGORIA, ICONOS_CATEGORIA, MAXIMO_NOMBRE, SIN_CATEGORIZAR,
    SIN_CATEGORIA_NO_CATEGORIZABLE, limpiar_nombre, texto_clase,
)
from finanzas.bootstrap.categorias import componer_administracion_categorias, componer_administracion_reglas, componer_asignacion_categorias, componer_catalogo_categorias


def crear_categoria(conn: Connection, nombre: str, clase: str, color: str, icono: str) -> int:
    return componer_administracion_categorias(conn).crear(nombre, clase, color, icono)


def editar_categoria(conn: Connection, categoria_id: int, nombre: str | None = None,
                     color: str | None = None, icono: str | None = None) -> None:
    componer_administracion_categorias(conn).editar(categoria_id, nombre, color, icono)


def borrar_categoria(conn: Connection, categoria_id: int, destino_id: int | None) -> CategoriaBorrada:
    return componer_administracion_categorias(conn).borrar(categoria_id, destino_id)


def restaurar_categoria(conn: Connection, copia: CopiaCategoria) -> int:
    return componer_administracion_categorias(conn).restaurar(copia)


def regla_que_coincide(conn: Connection, tipo: str, descripcion: str, monto_centavos: int | None,
                       origen: str = "gmail", referencia: str | None = None) -> dict | None:
    ganadora = componer_asignacion_categorias(conn).regla_que_coincide(tipo, descripcion, monto_centavos, origen, referencia)
    if ganadora is None:
        return None
    return {clave: getattr(ganadora, clave) for clave in ("id", "categoria_id", "texto", "modo_texto", "origen_regla")}


def sin_categorizar(conn: Connection) -> list[dict]:
    return [asdict(f) for f in componer_catalogo_categorias(conn).pendientes()]


def contar_sin_categorizar(conn: Connection) -> int:
    return componer_catalogo_categorias(conn).resumen_pendientes().cuantos


def resumen_sin_categorizar(conn: Connection) -> ResumenPendientes:
    return componer_catalogo_categorias(conn).resumen_pendientes()


# --- Categorías (ítem 15) -------------------------------------------------------------

# "Otros" (la de gasto) va al final de su clase, como en el prototipo; las
# demás, en el orden en que se crearon. Sin columna de orden: no hace falta
# otra migración.
NOMBRE_AL_FINAL = "Otros"


def categorias(conn: Connection, clase: str | None = None) -> list[dict]:
    return [asdict(f) for f in componer_catalogo_categorias(conn).categorias(clase)]


def categorias_con_uso(
    conn: Connection, desde: datetime, hasta: datetime, clase: str | None = None
) -> list[dict]:
    """Shim R1: consulta histórica; HTTP ya consume el caso de uso del módulo."""
    from dataclasses import asdict
    from finanzas.bootstrap.categorias import componer_consulta_categorias
    return [asdict(fila.categoria) for fila in componer_consulta_categorias(conn).ejecutar(desde, hasta, clase)]


def buscar_categoria(conn: Connection, categoria_id: int) -> dict | None:
    fila = componer_catalogo_categorias(conn).categoria(categoria_id)
    return None if fila is None else asdict(fila)


# --- Asignar una categoría -------------------------------------------------------------


def asignar_categoria(conn: Connection, movimiento_id: int, categoria_id: int, recordar: bool) -> int:
    """Como ``asignar_con_detalle``, pero devuelve solo el total."""
    return asignar_con_detalle(conn, movimiento_id, categoria_id, recordar).total


def asignar_con_detalle(conn: Connection, movimiento_id: int, categoria_id: int,
                        recordar: bool, condiciones: str = CONDICION_TEXTO) -> Asignacion:
    return componer_asignacion_categorias(conn).asignar(movimiento_id, categoria_id, recordar, condiciones)


def _guardar_regla(conn: Connection, nueva: CondicionesRegla, categoria_id: int) -> int:
    # Participante: el llamador ya posee la transacción inmediata.
    return componer_asignacion_categorias(conn).guardar_regla(nueva, categoria_id)


def _aplicar_regla_a_pendientes(conn: Connection, tipo: str, regla_id: int, categoria_id: int) -> int:
    # Participante: el llamador ya posee la transacción inmediata.
    return componer_asignacion_categorias(conn).aplicar_a_pendientes(tipo, regla_id, categoria_id)


# --- Reglas ------------------------------------------------------------------------------

def listar_reglas(conn: Connection) -> list[dict]:
    return [asdict(f) for f in componer_catalogo_categorias(conn).reglas()]


# Cómo se lee cada tipo de regla: (artículo y tipo, conector del texto).
# ``cuenta_destino`` se lee "a «…»" porque también puede ser el nombre de quien
# recibe (transferencias a llave Bre-B, D25), no solo una cuenta.


def buscar_regla(conn: Connection, regla_id: int) -> dict | None:
    fila = componer_catalogo_categorias(conn).regla(regla_id)
    if fila is None:
        return None
    datos = asdict(fila)
    del datos["categoria_id"]
    return datos


def borrar_regla(conn: Connection, regla_id: int) -> None:
    """Borra la regla. Los movimientos que ya categorizó conservan su categoría.

    También conservan su origen ``regla``, pero dejan de apuntar a ella
    (``regla_id = NULL``): la clave foránea no deja borrarla antes, y así un
    id reutilizado nunca hace que un movimiento señale otra regla.

    Lanza ``ReglaNoEncontrada`` si no existe. Es ``borrar_regla_con_copia``
    sin la copia.
    """
    borrar_regla_con_copia(conn, regla_id)


# --- Categorizar en grupo (ítem 38) ----------------------------------------------------
#
# "Sin categorizar" junta los pendientes iguales para categorizarlos con un toque,
# con la regla incluida. "Iguales" es exactamente lo que alcanzaría la regla por
# texto que se ofrece (``regla_posible``): mismo tipo y misma descripción
# normalizada (``normalizar``). Por eso los gastos y los ingresos nunca se mezclan
# (el tipo es parte de la clave; tampoco se mezclan compras con transferencias,
# que se recuerdan por campos distintos), y lo que no tiene descripción no se
# agrupa (no admite regla por texto). Un movimiento solo no es un grupo. El ítem
# 30 lo reutiliza para lo importado del banco.

from finanzas.modulos.categorias.grupos import (
    SEPARADOR_CLAVE, MAXIMO_IDS_GRUPO, MENSAJE_CLAVE_INVALIDA,
    GrupoPendientes, clave_grupo, leer_clave_grupo, agrupar_pendientes,
)


def categorizar_grupo(conn: Connection, clave: str, ids, categoria_id: int, modo_regla: str = "exacta") -> Asignacion:
    return componer_asignacion_categorias(conn).categorizar_grupo(clave, ids, categoria_id, modo_regla)


# --- Deshacer: restaurar reglas y categorías borradas (ítem 38) ------------------------
#
# Borrar una regla o una categoría vacía se hace al tocar y se puede deshacer unos
# segundos. Lo borrado viaja en una "copia" que guarda el servidor en memoria
# (``finanzas.deshacer``); restaurar vuelve a crear exactamente esa fila, con el
# mismo id si sigue libre. Borrar una categoría con movimientos o reglas sigue
# pidiendo confirmación y no tiene deshacer (``borrado_reversible``).


def borrar_regla_con_copia(conn: Connection, regla_id: int) -> CopiaRegla:
    return componer_administracion_reglas(conn).borrar(regla_id)


def restaurar_regla(conn: Connection, copia: CopiaRegla) -> int:
    return componer_administracion_reglas(conn).restaurar(copia)

from finanzas.modulos.categorias.presentacion import pesos, frase_condiciones, frase_regla, _TIPO_EN_FRASE
