"""Políticas y lectura de entradas en centavos enteros."""
import re
from datetime import date, datetime, timedelta
from finanzas.compartido import hora
from finanzas.modulos.saldo.contratos import ErrorSaldo
TIPO_COMPRA = "compra"
TIPO_TRANSFERENCIA = "transferencia"
TIPO_INGRESO = "ingreso"

MAXIMO_CENTAVOS = 10**12

TOLERANCIA_FUTURO = timedelta(minutes=5)

MAXIMO_DESCRIPCION = 200

DESCRIPCION_INGRESO = "Ingreso"

DESCRIPCION_AJUSTE = "Ajuste de saldo"

ULTIMOS_POR_DEFECTO = 20

TIPOS_GASTO = (TIPO_COMPRA, TIPO_TRANSFERENCIA)

TIPO_AJUSTE = "ajuste"

ORIGEN_MANUAL = "manual"

MENSAJE_INGRESO_NO_EXISTE = "Ese ingreso ya no existe. Recarga la pantalla de saldo."

MENSAJE_NO_SE_BORRA_AJUSTE = "Los ajustes no se borran. Si el saldo no cuadra, haz un ajuste nuevo."

MENSAJE_NO_SE_BORRA_GMAIL = "Lo que llega de Gmail no se borra: solo los ingresos registrados a mano."

MENSAJE_NO_SE_BORRA_GASTO = "Solo se pueden borrar ingresos registrados a mano."

MENSAJE_NO_SE_PUDO_BORRAR = "No se pudo borrar el ingreso. Recarga la pantalla de saldo e inténtalo de nuevo."

MENSAJE_CONCILIADO = (
    "Este ingreso ya lo confirmó el reporte del banco, o está en una pregunta de la "
    "conciliación: no se puede borrar."
)

MENSAJE_ANTERIOR_AL_AJUSTE = (
    "Este ingreso es anterior al último ajuste: borrarlo descuadraría un saldo que ya cuadraste. "
    "Si hace falta, corrige el saldo con un ajuste."
)

MENSAJE_RESTAURAR_TRAS_AJUSTE = (
    "No se puede deshacer: ajustaste el saldo después de borrar este ingreso, "
    "y restaurarlo descuadraría el saldo que cuadraste."
)

MENSAJE_RESTAURAR_ANTES_DEL_INICIO = (
    "No se puede deshacer: el ingreso quedaría antes de la fecha de inicio, que cambió."
)

MENSAJE_RESTAURAR_SIN_CONFIGURACION = (
    "No se puede deshacer: el saldo inicial y la fecha de inicio ya no están configurados."
)

MENSAJE_RESTAURAR_TRAS_IMPORTAR = (
    "No se puede deshacer: importaste un reporte del banco después de borrar este ingreso, "
    "y restaurarlo podría contarlo dos veces. Regístralo otra vez si hace falta."
)

MENSAJE_RESTAURAR_CATEGORIA_CAMBIO = (
    "No se puede deshacer: la categoría de este ingreso cambió mientras tanto. Regístralo otra vez."
)

_PESOS = re.compile(r"(?P<entero>[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:,(?P<decimales>[0-9]{1,2}))?")

_PUNTO_DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]{3})*\.[0-9]{1,2}")

_MUCHOS_DECIMALES = re.compile(r"[0-9.]+,[0-9]{3,}")

_LARGO_MAXIMO_TEXTO = 40

MENSAJE_MONTO_INVALIDO = (
    "Monto no válido. Escríbelo en pesos con punto para los miles y coma para los "
    "decimales, por ejemplo 1.234.567,89."
)

_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

_FECHA_HORA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2})?")


def _es_entero(valor: object) -> bool:
    # bool es subclase de int: True no es un monto.
    return isinstance(valor, int) and not isinstance(valor, bool)


def _validar_no_negativo(valor: object, nombre: str) -> int:
    if not _es_entero(valor):
        raise ErrorSaldo(f"El {nombre} debe ser un número entero de centavos.")
    if valor < 0:
        raise ErrorSaldo(f"El {nombre} no puede ser negativo.")
    if valor > MAXIMO_CENTAVOS:
        raise ErrorSaldo(f"El {nombre} es demasiado grande.")
    return valor


def _limite_iso(momento: datetime) -> str:
    """Límite de un rango en el formato guardado (hora de Colombia, sin zona).

    Lo guardado tiene precisión de segundos. Si el límite trae microsegundos
    se redondea **hacia arriba** al segundo siguiente: así ``desde <= x`` y
    ``x < hasta`` dan lo mismo con el límite exacto que con el redondeado
    (recortar hacia abajo incluiría un segundo de más en ambos extremos).
    """
    momento = hora.a_hora_colombia(momento)
    if momento.microsecond:
        momento = momento.replace(microsecond=0) + timedelta(seconds=1)
    return momento.isoformat(timespec="seconds")


def leer_pesos(texto: str) -> int:
    """Convierte lo que escribe el dueño, en pesos colombianos, a centavos.

    Acepta ``1234567``, ``1.234.567`` (miles con punto bien agrupados),
    ``1.234.567,89``, ``1234567,89`` y ``0,50``, con ``$`` y espacios
    opcionales al inicio y al final. Rechaza con ``ErrorSaldo`` lo vacío,
    los negativos, los miles mal agrupados, más de 2 decimales, el punto
    como decimal (``1234.56`` es ambiguo), las cifras no ASCII y los montos
    por encima de 10¹² centavos. Solo aritmética entera: nunca pasa por
    ``float``.
    """
    if not isinstance(texto, str):
        raise ErrorSaldo("Escribe un monto.")
    limpio = texto.strip()
    if limpio.startswith("$"):
        limpio = limpio[1:].strip()
    if not limpio:
        raise ErrorSaldo("Escribe un monto.")
    if len(limpio) > _LARGO_MAXIMO_TEXTO:
        raise ErrorSaldo("El monto es demasiado grande.")
    if limpio.startswith(("-", "\u2212")):  # guion o signo menos
        raise ErrorSaldo("El monto no puede ser negativo.")

    coincidencia = _PESOS.fullmatch(limpio)
    if coincidencia is None:
        if _PUNTO_DECIMAL.fullmatch(limpio):
            raise ErrorSaldo(
                "Usa coma para los decimales y punto para los miles "
                "(por ejemplo 1.234,56). El punto solo separa miles."
            )
        if _MUCHOS_DECIMALES.fullmatch(limpio):
            raise ErrorSaldo("El monto admite como máximo 2 decimales.")
        raise ErrorSaldo(MENSAJE_MONTO_INVALIDO)

    enteros = int(coincidencia.group("entero").replace(".", ""))
    decimales = (coincidencia.group("decimales") or "").ljust(2, "0")
    centavos = enteros * 100 + int(decimales)
    if centavos > MAXIMO_CENTAVOS:
        raise ErrorSaldo("El monto es demasiado grande.")
    return centavos


def leer_fecha(texto: str) -> date:
    """``aaaa-mm-dd`` (lo que envía ``<input type="date">``) a ``date``."""
    limpio = texto.strip() if isinstance(texto, str) else ""
    if not _FECHA.fullmatch(limpio):
        raise ErrorSaldo("Fecha no válida. Usa el formato aaaa-mm-dd.")
    try:
        return date.fromisoformat(limpio)
    except ValueError:
        raise ErrorSaldo("Fecha no válida.") from None


def leer_fecha_hora(texto: str) -> datetime:
    """``aaaa-mm-ddThh:mm[:ss]`` (``<input type="datetime-local">``) a ``datetime``.

    Sin zona: se entiende en hora de Colombia.
    """
    limpio = texto.strip() if isinstance(texto, str) else ""
    if not _FECHA_HORA.fullmatch(limpio):
        raise ErrorSaldo("Fecha y hora no válidas.")
    try:
        return datetime.fromisoformat(limpio)
    except ValueError:
        raise ErrorSaldo("Fecha y hora no válidas.") from None
