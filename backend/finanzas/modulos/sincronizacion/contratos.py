"""Correo y movimientos normalizados; puerto de recuperación de solo lectura."""
from __future__ import annotations
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

ALCANCES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Remitentes públicos de las alertas de Bancolombia (D30): exactamente estas
# dos direcciones, ni otra dirección ni otro subdominio. La primera envía
# Compraste, Transferiste, Recibiste, Retiraste y los pagos QR; la segunda,
# los pagos por PSE. No se pueden cambiar por configuración.
REMITENTE_POR_DEFECTO = "alertasynotificaciones@an.notificacionesbancolombia.com"
REMITENTE_AYN = "alertasynotificaciones@ayn.notificacionesbancolombia.com"
REMITENTES_OFICIALES: tuple[str, ...] = (REMITENTE_POR_DEFECTO, REMITENTE_AYN)


def como_remitentes(remitentes: str | Sequence[str]) -> tuple[str, ...]:
    """Una dirección suelta o varias, siempre como tupla (una cadena es una
    sola dirección, nunca una secuencia de letras)."""
    if isinstance(remitentes, str):
        return (remitentes,)
    return tuple(remitentes)

class ErrorGmail(Exception):
    """Fallo al hablar con Gmail."""


class ErrorAutorizacionGmail(ErrorGmail):
    """Falta el token de Gmail, se revocó o no sirve.

    El mensaje es para el dueño y nunca incluye el contenido del token.
    """


@dataclass(frozen=True)
class CorreoGmail:
    """Un correo ya descargado.

    - ``gmail_id``: id del mensaje en Gmail.
    - ``fecha``: fecha de recepción (``internalDate``), con zona horaria de
      Colombia.
    - ``asunto``: encabezado ``Subject`` (vacío si no tiene).
    - ``texto``: cuerpo en texto plano (la parte ``text/plain`` si existe; si
      no, la HTML convertida).
    - ``alternativos``: otras versiones del cuerpo (la HTML convertida cuando
      también hay ``text/plain``). Algunos correos traen un texto plano de
      relleno y el aviso real solo en el HTML.

    - ``remitente``: la única dirección del encabezado ``From`` (analizada con
      ``email.utils.getaddresses``), o ``""`` si no hay exactamente una.
    - ``autenticacion``: valor del PRIMER encabezado ``Authentication-Results``
      (el de más arriba, que añade Gmail al recibir el correo), o ``""``.

    El cuerpo, el remitente y la autenticación solo viven en memoria: nunca se
    guardan ni se registran. Los valores por defecto (vacíos) hacen que un
    correo construido sin ellos se rechace.
    """

    gmail_id: str
    fecha: datetime
    asunto: str = field(repr=False)
    texto: str = field(repr=False)
    alternativos: tuple[str, ...] = field(default=(), repr=False)
    remitente: str = field(default="", repr=False)
    autenticacion: str = field(default="", repr=False)

    @property
    def textos(self) -> tuple[str, ...]:
        """Todas las versiones del cuerpo, en orden de preferencia."""
        return (self.texto, *self.alternativos)


class ClienteGmail(Protocol):
    """Lo que la sincronización necesita de Gmail."""

    def listar_ids(self, desde: date) -> list[str]:
        """Ids de los correos de los remitentes de alertas recibidos desde ``desde``."""
        ...

    def obtener(self, gmail_id: str) -> CorreoGmail:
        """Descarga un correo completo."""
        ...



@dataclass(frozen=True)
class MovimientoExtraido:
    """Movimiento leído de un aviso.

    - ``tipo``: ``"compra"``, ``"transferencia"`` o ``"ingreso"``.
    - ``monto_centavos``: monto exacto en centavos (siempre > 0);
      ``$68.630,00`` -> 6863000.
    - ``fecha_hora``: fecha y hora sin zona horaria, hora local de Colombia.
    - ``descripcion``: comercio (compras), cajero (retiros), empresa (pagos
      PSE), cuenta destino solo con los últimos cuatro dígitos, como ``*5678``
      (transferencias a cuenta), nombre de quien recibe (transferencias a
      llave Bre-B), ``DESCRIPCION_PAGO_QR`` (pagos QR) o quien envía
      (ingresos).
    - ``categoria_al_leer``: nombre de la categoría de gasto que el aviso
      implica por sí mismo (D30). Solo "Retiraste" la trae ("Retiro a
      efectivo"); en los demás es ``None`` y decide una regla o el dueño.
    """

    tipo: str
    monto_centavos: int
    fecha_hora: datetime
    descripcion: str
    categoria_al_leer: str | None = None


@dataclass
class ResultadoSincronizacion:
    """Contadores de una sincronización.

    - ``nuevos``: movimientos guardados.
    - ``duplicados``: correos que otro proceso guardó mientras tanto.
    - ``no_reconocidos``: correos guardados para revisión (solo id, fecha y asunto).
    - ``errores``: correos que no se pudieron descargar o procesar; se
      reintentan en la siguiente sincronización.
    - ``rechazados_autenticacion``: correos cuyo remitente no es uno de los oficiales o
      que Gmail no autenticó (posibles falsificaciones). Se guardan como no
      reconocidos (solo id, fecha y asunto) y nunca pasan por el extractor.

    Los correos ya registrados en sincronizaciones anteriores no se descargan
    y no cuentan en ningún contador.
    """

    nuevos: int = 0
    duplicados: int = 0
    no_reconocidos: int = 0
    errores: int = 0
    rechazados_autenticacion: int = 0

    def resumen(self) -> str:
        return (
            f"{self.nuevos} nuevos, {self.duplicados} duplicados, "
            f"{self.no_reconocidos} no reconocidos, {self.errores} errores, "
            f"{self.rechazados_autenticacion} rechazados por remitente o autenticación"
        )


@dataclass(frozen=True)
class EstadoSincronizacion:
    """La última sincronización terminada (tabla ``estado_sincronizacion``).

    ``terminada_en`` va en hora de Colombia sin zona, como las fechas de los
    movimientos. Si ``estado`` es ``"fallida"``, ``codigo_error`` dice por qué
    y ``resultado`` es ``None``; si no, ``resultado`` trae los contadores.

    ``ultima_correcta_en`` (migración 0003, ítem 13): ``terminada_en`` de la
    última sincronización que no quedó ``"fallida"`` (``ok`` o
    ``con_errores``), en el mismo formato; ``None`` si no se sabe (nunca
    hubo una, o la base se migró con una fallida guardada). Si esta terminó
    bien, es igual a ``terminada_en``.
    """

    terminada_en: str
    estado: str
    origen: str
    resultado: ResultadoSincronizacion | None
    codigo_error: str | None
    ultima_correcta_en: str | None = None



class RegistroAvisos(Protocol):
    def ids_registrados(self) -> set[str]: ...
    def guardar_movimiento(self, gmail_id: str, movimiento: MovimientoExtraido) -> bool: ...
    def guardar_no_reconocido(self, aviso) -> int: ...
    def guardar_estado(self, resultado: ResultadoSincronizacion) -> EstadoSincronizacion: ...


class SincronizacionNoConfigurada(Exception):
    """Falta algo para poder sincronizar (fecha de inicio o token de Gmail)."""

@dataclass
class ResultadoReproceso:
    """Contadores de un reproceso de los correos no reconocidos.

    - ``revisados``: correos de la lista que se intentaron reprocesar.
    - ``movimientos_creados``: ahora sí eran un aviso válido; salen de la lista.
    - ``siguen_sin_reconocerse``: siguen sin aviso válido, no pasan la
      verificación de remitente y DMARC (D15) o son anteriores a la fecha de
      inicio; se quedan en la lista.
    - ``ya_registrados``: el movimiento ya existía con ese ``gmail_id`` (una
      fila sobrante); salen de la lista sin crear nada.
    - ``errores``: no se pudieron descargar o procesar; se quedan en la lista.

    ``revisados`` es siempre la suma de los otros cuatro.
    """

    revisados: int = 0
    movimientos_creados: int = 0
    siguen_sin_reconocerse: int = 0
    ya_registrados: int = 0
    errores: int = 0

    def resumen(self) -> str:
        return (
            f"{self.revisados} revisados, {self.movimientos_creados} movimientos creados, "
            f"{self.siguen_sin_reconocerse} siguen sin reconocerse, "
            f"{self.ya_registrados} ya registrados, {self.errores} errores"
        )


class RegistroSincronizacion(RegistroAvisos, Protocol):
    def leer_fecha_inicio(self) -> date: ...
    def fecha_configurada(self) -> bool: ...
    def listar_no_reconocidos(self) -> list[dict]: ...
    def es_no_reconocido(self, gmail_id: str) -> bool: ...
    def guardar_correo_no_reconocido(self, correo: CorreoGmail) -> bool: ...
    def guardar_movimiento(self, gmail_id: str, movimiento: MovimientoExtraido,
                          quitar_no_reconocido: bool = False) -> bool: ...
    def guardar_estado_sincronizacion(self, origen: str, resultado: ResultadoSincronizacion | None = None,
                                     codigo_error: str | None = None) -> EstadoSincronizacion: ...
    def en_transaccion(self) -> bool: ...
    def cerrar_lectura(self) -> None: ...
