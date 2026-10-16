"""Datos y condiciones compartidas de reglas, sin dependencia de los puertos."""
from dataclasses import dataclass

CONDICION_TEXTO = "texto"

CONDICION_MONTO = "monto"

CONDICION_TEXTO_Y_MONTO = "texto_y_monto"

CONDICIONES = (CONDICION_TEXTO, CONDICION_MONTO, CONDICION_TEXTO_Y_MONTO)

@dataclass(frozen=True)
class CondicionesRegla:
    """Las condiciones de una regla: tipo (``campo``) + ``texto`` y/o ``monto_centavos``.

    ``texto`` va normalizado; ``None`` si la regla no mira el texto. ``monto_centavos``:
    ``None`` si no mira el monto. Nunca los dos ``None``.
    """

    campo: str
    texto: str | None
    monto_centavos: int | None
    modo_texto: str = "exacta"
    origen_regla: str = "todos"
    texto_visible: str | None = None

    @property
    def condiciones(self) -> str:
        """``texto``, ``monto`` o ``texto_y_monto``."""
        return condiciones_de(self.texto, self.monto_centavos)

def condiciones_de(texto: str | None, monto_centavos: int | None) -> str:
    """Qué condiciones tiene una regla: ``texto``, ``monto`` o ``texto_y_monto``."""
    if texto is not None and monto_centavos is not None:
        return CONDICION_TEXTO_Y_MONTO
    return CONDICION_TEXTO if texto is not None else CONDICION_MONTO
