"""Privacidad de destinos numéricos (D37/D45), sin modificar nombres Bre-B."""

import re


def recortar_destino(texto: str) -> str:
    """Conserva solo cuatro dígitos de una cuenta; otros textos quedan intactos.

    Solo se llama sobre el destino de una transferencia, nunca sobre un
    comercio o el nombre de quien envía. No interpreta formatos desconocidos.
    """
    if re.fullmatch(r"\*?[0-9]{4,}", texto):
        return "*" + texto[-4:]
    return texto
