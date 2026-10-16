"""Barrera única de autenticidad y lectura; nunca escribe ni consulta la base."""
from collections.abc import Sequence
from finanzas.modulos.sincronizacion.publico import CorreoGmail
from finanzas.modulos.sincronizacion.adaptadores.gmail.autenticidad import (
    MOTIVO_REMITENTE, remitente_reconocido, motivo_autenticacion_invalida,
)
from . import extractor
from .lector import clasificar_correo

def _motivo_rechazo(correo: CorreoGmail, remitentes_oficiales: str | Sequence[str]) -> str | None:
    """Categoría genérica del rechazo, o ``None`` si el correo es confiable.

    ``"remitente"`` (From no es exactamente uno de los oficiales), ``"encabezado_invalido"`` (el
    ``Authentication-Results`` falta, no es de Gmail o se sale de la
    gramática) o ``"sin_pass_alineado"`` (se entiende, pero no trae
    ``dmarc=pass`` alineado con el dominio de la dirección oficial que
    coincidió; DMARC es obligatorio, D15). Nunca lleva valores del
    correo: sirve para diagnosticar, p. ej., si el banco cambia de proveedor.
    """
    remitente = remitente_reconocido(correo, remitentes_oficiales)
    if remitente is None:
        return MOTIVO_REMITENTE
    return motivo_autenticacion_invalida(correo, remitente)

def evaluar_correo(
    correo: CorreoGmail, remitentes_oficiales: str | Sequence[str]
) -> tuple[str | None, extractor.MovimientoExtraido | None]:
    """(motivo de rechazo, movimiento) de un correo ya descargado.

    Único camino de decisión, compartido por ``sincronizar`` y ``reprocesar``
    para que el reproceso nunca se salte la verificación (D15):

    1. el filtro ``from:`` de la consulta se puede falsificar: antes de leer
       el aviso se exige uno de los dos remitentes oficiales autenticado por
       Gmail (DMARC alineado con el dominio de esa dirección). Si falla, devuelve ``(motivo, None)`` y el cuerpo ni se mira;
    2. si pasa, revisa todas las versiones del cuerpo (``clasificar_correo``):
       si alguna cita el aviso, queda no reconocido; si no, vale la primera
       con aviso (algunos correos traen un texto plano de relleno). Devuelve
       ``(None, movimiento)`` o ``(None, None)`` si no hay aviso válido.
    """
    motivo = _motivo_rechazo(correo, remitentes_oficiales)
    if motivo is not None:
        return motivo, None
    _, movimiento = clasificar_correo(correo.textos)
    return None, movimiento
