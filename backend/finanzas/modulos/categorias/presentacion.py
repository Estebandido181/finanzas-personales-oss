"""Frases y montos para presentar, aritmética entera sin infraestructura."""
from .politica import normalizar, clase_para_tipo, campo_para_tipo
from .grupos import clave_grupo

_TIPO_EN_FRASE = {
    "comercio": ("una compra", "compra", "en"),
    "cuenta_destino": ("una transferencia", "transferencia", "a"),
    "quien_envia": ("un ingreso", "ingreso", "de"),
}

def pesos(centavos: int) -> str:
    """Monto para leer en una frase, como en el prototipo: ``320000`` -> ``$3.200``.

    Punto para los miles; los centavos solo si los hay (``$132.449,50``). Solo
    aritmética entera.
    """
    enteros, resto = divmod(int(centavos), 100)
    texto = f"${enteros:,}".replace(",", ".")
    return texto if resto == 0 else f"{texto},{resto:02d}"


def frase_condiciones(campo: str, texto: str | None, monto_centavos: int | None = None, modo_texto: str = "exacta") -> str:
    """Las condiciones en palabras, sin artículo: ``compra en «tienda»``,
    ``transferencia de $3.200`` o ``ingreso de «persona» por $400.000``.

    Es lo que la app muestra junto a un movimiento ("por regla: transferencia de
    $3.200"). Quien presenta una regla bancaria usa su texto original visible.
    """
    _, tipo, conector = _TIPO_EN_FRASE[campo]
    partes = [tipo]
    if texto is not None:
        partes.append(f"{conector} «{texto}»" if modo_texto == "exacta" else
            f'del banco cuya descripción {"contiene" if modo_texto == "contiene" else "empieza por"} «{texto}»')
    if monto_centavos is not None:
        partes.append(("por " if texto is not None else "de ") + pesos(monto_centavos))
    return " ".join(partes)


def frase_regla(campo: str, texto: str | None, categoria: str, monto_centavos: int | None = None, modo_texto: str = "exacta") -> str:
    """La regla en palabras, como en el prototipo de Categorías y reglas.

    * ``Si es una compra en «tienda», va a Mercado``
    * ``Si es una transferencia de $3.200, va a Transporte``
    * ``Si es un ingreso de «persona» por $400.000, va a Préstamos``
    """
    articulo = _TIPO_EN_FRASE[campo][0].split(" ")[0]
    return f"Si es {articulo} {frase_condiciones(campo, texto, monto_centavos, modo_texto)}, va a {categoria}"
