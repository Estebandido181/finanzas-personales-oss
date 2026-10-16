"""Agrupación pura de pendientes; conserva claves y orden de la bandeja."""
from dataclasses import dataclass
from finanzas.modulos.categorias.contratos import ErrorCategorizacion
from finanzas.modulos.categorias.politica import (
    CondicionesRegla, CAMPO_POR_TIPO, CLASE_POR_TIPO, TIPOS_PENDIENTES, normalizar, regla_posible,
)

SEPARADOR_CLAVE = ":"
MAXIMO_IDS_GRUPO = 5000
MENSAJE_CLAVE_INVALIDA = "Ese grupo no es válido. Recarga la bandeja e inténtalo de nuevo."


@dataclass(frozen=True)
class GrupoPendientes:
    """Pendientes iguales (``agrupar_pendientes``).

    ``clave``: ``tipo:texto`` (``texto`` normalizado), lo que se envía para
    categorizarlos. ``descripcion``: la del más reciente, tal cual. ``ids``:
    en el orden recibido (del más reciente al más antiguo en la bandeja).
    ``regla``: la regla por texto que se crea al categorizar el grupo.
    """

    clave: str
    tipo: str
    descripcion: str
    clase_categoria: str
    cuantos: int
    suma_centavos: int
    ids: tuple[int, ...]
    regla: CondicionesRegla


def clave_grupo(tipo: str, descripcion: str) -> str | None:
    """La clave del grupo al que va un pendiente, o ``None`` si no se agrupa (sin regla por texto)."""
    posible = regla_posible(tipo, descripcion)
    if posible is None or tipo not in TIPOS_PENDIENTES:
        return None
    return f"{tipo}{SEPARADOR_CLAVE}{posible[1]}"


def leer_clave_grupo(clave: str) -> tuple[str, str]:
    """``(tipo, texto)`` de una clave de ``clave_grupo``. ``ErrorCategorizacion`` si no es una.

    Solo acepta claves que ``clave_grupo`` podría haber dado: tipo
    categorizable y texto ya normalizado y no vacío.
    """
    if not isinstance(clave, str):
        raise ErrorCategorizacion(MENSAJE_CLAVE_INVALIDA)
    tipo, separador, texto = clave.partition(SEPARADOR_CLAVE)
    if not separador or tipo not in TIPOS_PENDIENTES or not texto or normalizar(texto) != texto:
        raise ErrorCategorizacion(MENSAJE_CLAVE_INVALIDA)
    return tipo, texto


def agrupar_pendientes(filas) -> list[GrupoPendientes]:
    """Los grupos de pendientes iguales entre ``filas`` (de 2 o más movimientos).

    ``filas``: mapeos con ``id``, ``tipo``, ``descripcion`` y ``monto_centavos``
    (como los de ``sin_categorizar``), del más reciente al más antiguo. Es
    función pura: no lee la base, así la usa también lo importado (ítem 30).
    Los grupos van del más numeroso al menos; a igual número, primero el
    que tiene el movimiento más reciente.
    """
    por_clave: dict[str, list] = {}
    for fila in filas:
        clave = clave_grupo(str(fila["tipo"]), str(fila["descripcion"]))
        if clave is not None:
            por_clave.setdefault(clave, []).append(fila)
    grupos = []
    for orden, (clave, miembros) in enumerate(por_clave.items()):
        if len(miembros) < 2:
            continue
        tipo, texto = leer_clave_grupo(clave)
        grupo = GrupoPendientes(
            clave=clave,
            tipo=tipo,
            descripcion=str(miembros[0]["descripcion"]),
            clase_categoria=CLASE_POR_TIPO[tipo],
            cuantos=len(miembros),
            suma_centavos=sum(int(f["monto_centavos"]) for f in miembros),
            ids=tuple(int(f["id"]) for f in miembros),
            regla=CondicionesRegla(campo=CAMPO_POR_TIPO[tipo], texto=texto, monto_centavos=None),
        )
        grupos.append((-len(miembros), orden, grupo))
    grupos.sort(key=lambda g: (g[0], g[1]))
    return [grupo for _, _, grupo in grupos]
