"""Clasificación de versiones de un aviso, sin SQL ni cliente externo."""
from __future__ import annotations
import re
import unicodedata
from collections.abc import Sequence
from . import extractor

# Encabezados de plantilla que pueden ir ANTES del aviso (ítem 21). Lista
# cerrada: si antes de "Bancolombia: Compraste/Transferiste/..." hay cualquier
# otro texto, el aviso está citado dentro de otro correo (reverso, correo
# educativo, reenvío...) y el correo queda como no reconocido.
#
# Origen de cada encabezado:
# - "¡Listo! Todo salió bien con tus movimientos": sale de la captura del
#   correo real que vio el team leader (aviso Bre-B del 29/09/2026). Los
#   fixtures tests/fixtures/gmail/autenticacion/legitimo_*_real_anonimizado.json
#   reproducen los *encabezados* reales (From, Authentication-Results...), no
#   el cuerpo: el repositorio no tiene el cuerpo real de ningún aviso. Por eso,
#   antes de desplegar un cambio del lector, se corre la prueba en seco
#   (``python -m finanzas.prueba_en_seco``, deploy/GUIA.md 13.2).
#
# La comparación ignora mayúsculas, todos los espacios (el HTML puede dejar
# "¡Listo!Todo salió..." pegado al unir dos <span>) y los caracteres de
# ``_RELLENOS_INVISIBLES``.
#
# Cómo agregar uno nuevo (si un aviso legítimo queda como no reconocido por su
# encabezado): pedir al dueño el cuerpo del correo anonimizado, crear con él
# un fixture en tests/fixtures/gmail/ que lo reproduzca, agregar aquí el
# encabezado (texto exacto, con su origen) y reprocesar los no reconocidos
# (README, "Reprocesar los correos no reconocidos"). Nunca agregar
# encabezados supuestos o inventados.
ENCABEZADOS_PERMITIDOS: tuple[str, ...] = (
    "¡Listo! Todo salió bien con tus movimientos",
)

# Imágenes de la plantilla del banco que pueden ir ANTES del encabezado
# (ítem 21). Lista cerrada, como los encabezados.
#
# Origen: diagnóstico ``python -m finanzas.prueba_en_seco --mostrar-previo`` en
# la VM, 30/09/2026, 6 avisos reales (Compraste, Transferiste y Bre-B): la
# versión HTML queda "valido", pero la versión text/plain lista las imágenes de
# la plantilla como ``alt [url]`` delante del encabezado, por ejemplo
# "Logo Bancolombia [https://bancolombia-email-wsuite.s3.amazonaws.com/templates/<hex>/img/header-logo.png]
# yellow-icon [https://.../templates/<hex>/img/chulo.png] ¡Listo! Todo salió...",
# y con el veto entre versiones eso tumbaba el correo entero. En los reales:
# a veces sin espacio entre "]" y el alt siguiente, la primera URL a veces con
# http://, y el identificador <hex> (dígitos y a-f en minúscula) cambia en cada
# correo.
#
# Qué se acepta, exactamente: una o varias referencias ``alt [url]``, en
# cualquier orden, solo al comienzo del texto previo y seguidas entre sí (con
# un espacio opcional entre ellas), donde:
# - alt es uno de ``IMAGENES_PLANTILLA`` (sin distinguir mayúsculas);
# - url es http(s)://bancolombia-email-wsuite.s3.amazonaws.com/templates/<hex>/img/<archivo>
#   con <hex> solo [0-9a-f] y <archivo> uno de ``ARCHIVOS_IMAGEN_PLANTILLA``.
# Los nombres de archivo van en lista cerrada (no cualquier [a-z0-9_-]+.png)
# porque en los 6 reales fueron siempre los mismos y el alt y el archivo son
# lo único de la referencia que el banco no genera por correo: aceptar otros
# no aporta nada y abre la puerta a imágenes que no conocemos. Tras quitarlas,
# lo que queda se compara con ``ENCABEZADOS_PERMITIDOS`` como antes: cualquier
# otro texto (antes, entre o después de las imágenes) sigue siendo una cita.
# Para agregar una imagen nueva se sigue el mismo procedimiento que para un
# encabezado (cuerpo anonimizado del dueño, fixture, origen aquí).
IMAGENES_PLANTILLA: tuple[str, ...] = ("Logo Bancolombia", "yellow-icon")
ARCHIVOS_IMAGEN_PLANTILLA: tuple[str, ...] = ("header-logo.png", "chulo.png")

_IMAGEN_PLANTILLA = re.compile(
    # Solo el alt ignora mayúsculas; el host, la ruta y el hex no.
    r" ?(?i:" + "|".join(re.escape(a) for a in IMAGENES_PLANTILLA) + r") ?"
    r"\[https?://bancolombia-email-wsuite\.s3\.amazonaws\.com/templates/[0-9a-f]+/img/"
    r"(?:" + "|".join(re.escape(a) for a in ARCHIVOS_IMAGEN_PLANTILLA) + r")\] ?",
    re.ASCII,
)

# Único inicio de aviso aceptado: "Bancolombia:" (espacio opcional) seguido de
# Compraste, Transferiste, "Recibiste una transferencia" (ítem 09), Retiraste
# o Pagaste (pago PSE, ítem 27), o bien, en el aviso de transferencia a llave
# (Bre-B), "NOMBRE DEL TITULAR, transferiste" y, en el pago QR (ítem 27),
# "NOMBRE COMPLETO DEL TITULAR pagaste" (los nombres con la misma forma que
# exige el extractor), sobre el texto ya normalizado. Sin \b delante:
# al convertir HTML, "Bancolombia:" puede quedar pegado a la palabra anterior
# (p. ej. tras un <span> sin espacio).
_INICIO_AVISO = re.compile(
    r"bancolombia: ?(?=(?:compraste|transferiste|recibiste una transferencia|retiraste|pagaste)\b"
    r"|(?:" + extractor._TITULAR + r"), transferiste\b"
    r"|(?:" + extractor._TITULAR_QR + r") pagaste\b)",
    # re.ASCII como en el extractor: así el titular se valida exactamente igual.
    re.IGNORECASE | re.ASCII,
)
# Caracteres de relleno que se ven en blanco pero no son de formato (Cf) ni
# espacios Unicode, así que ``extractor._normalizar`` no los quita: los
# preencabezados ocultos de las plantillas de correo los usan. Solo se ignoran
# al comparar el texto previo al aviso, nunca dentro del aviso.
_RELLENOS_INVISIBLES = str.maketrans("", "", "\u115f\u1160\u2800\u3164\uffa0")

# Resultado de revisar una versión del cuerpo (o el correo completo):
AVISO_VALIDO = "valido"  # aviso al comienzo y bien leído
AVISO_CITADO = "citado"  # hay un inicio de aviso con otro texto delante
SIN_AVISO = "sin_aviso"  # no hay aviso que leer (queda no reconocido)

# Otro inicio de aviso dentro de la descripción extraída: señal de que el
# comercio (o quien envía) "cruzó" hasta un segundo aviso (p. ej. una
# promoción delante).
_OTRO_AVISO = re.compile(
    r"bancolombia:|\b(?:compraste|transferiste|recibiste|retiraste|pagaste)\b", re.IGNORECASE
)


def extraer_aviso(texto: str) -> extractor.MovimientoExtraido | None:
    """Busca el aviso al comienzo del cuerpo del correo y lo extrae.

    El extractor exige que el aviso esté al *inicio* del texto, pero los
    correos traen antes un encabezado de plantilla ("¡Listo! Todo salió bien
    con tus movimientos") y el HTML puede partir el aviso en varios bloques
    (``<br><br>`` dentro del párrafo, "Bancolombia:" en su propia celda o
    párrafo). Por eso:

    1. se normaliza el texto completo (sin invisibles, un espacio entre
       palabras), así las líneas y los bloques ya no importan;
    2. solo se acepta como inicio la **primera** posición con
       ``Bancolombia:`` (espacio opcional) seguido de ``Compraste``,
       ``Transferiste``, ``Recibiste una transferencia`` o
       ``NOMBRE, transferiste`` (aviso de transferencia a llave Bre-B), sin
       distinguir mayúsculas. Un "Compraste" (o "Recibiste") suelto no
       basta: así no se inventan movimientos a partir de correos que *citan*
       un aviso ("¿Reconoces este movimiento? Compraste...", "Si no
       compraste...") ni de promociones;
    3. **avisos citados (ítem 21):** todo lo que haya antes de ese inicio,
       tras quitar del comienzo las referencias de imagen de la plantilla
       (``alt [url]`` con alt y url de ``IMAGENES_PLANTILLA``; así llegan en
       la versión text/plain), tiene que ser vacío o exactamente uno de los
       encabezados de ``ENCABEZADOS_PERMITIDOS`` (sin distinguir mayúsculas,
       ignorando todos los espacios y los rellenos invisibles de
       ``_RELLENOS_INVISIBLES``). Cualquier otro texto delante
       ("Reversamos la transacción: Bancolombia: Compraste ...", "Así se ven
       nuestras alertas: ...", un reenvío, una promoción, otro aviso) indica
       que el aviso está citado dentro de otro correo: se devuelve ``None``
       y el correo queda como no reconocido. Nunca se busca una segunda
       posición;
    4. se descarta el candidato si su descripción contiene otro inicio de
       aviso (``Bancolombia:``, "Compraste", "Transferiste" o "Recibiste"):
       significa que el comercio o quien envía se extendió hasta un segundo
       aviso y el monto sería el equivocado.

    Esta función mira un solo texto. La sincronización usa
    ``clasificar_correo``, que revisa todas las versiones del cuerpo: si
    alguna cita el aviso, el correo queda no reconocido aunque otra lo traiga
    limpio.

    Pasar al extractor el resto del correo es seguro: tolera texto adicional
    tras el punto final y sus guardas estructurales impiden que el comercio
    cruce "con tu T.", la tarjeta o la fecha, y que quien envía cruce
    " en tu cuenta *", la cuenta o la fecha.

    Los ingresos ("Recibiste una transferencia") pasan antes por la misma
    verificación de remitente y autenticación (D11) que los demás avisos; si
    una regla de ingreso (por quien envía, ítem 15) coincide, se guardan ya
    categorizados.

    Decisión del dueño (ronda 3): un aviso sin el prefijo "Bancolombia:" queda
    como no reconocido; se registra para revisión y se puede reprocesar.

    Consecuencia aceptada del paso 3: un correo legítimo con un encabezado
    nuevo (o con otro texto delante en el HTML, como un preencabezado oculto)
    queda como no reconocido hasta que el encabezado se agregue a la lista;
    luego se reprocesa (ver el README).

    Riesgo abierto (fuera del ítem 21): lo que va *después* del aviso no se
    mira. Un correo que empiece con el aviso completo y siga con "... fue
    reversado" se lee como movimiento; se corrige con un ajuste.
    """
    return _buscar_aviso(texto)[1]


def localizar_aviso(texto: str) -> str:
    """Envoltorio fino de ``extraer_aviso`` para depurar y probar: el texto
    normalizado desde donde empieza el aviso reconocido, o el texto completo
    normalizado si no hay ninguno."""
    return _buscar_aviso(texto)[0]


def _clave_encabezado(texto: str) -> str:
    """Forma de comparar encabezados: solo sus letras y dígitos, sin tildes y
    sin distinguir mayúsculas.

    Se ignoran espacios, signos (¡ ! . , ...), tildes e invisibles, porque la
    versión en texto plano de un correo puede traer el mismo encabezado sin
    ellos ("Listo! Todo salio bien ..."), y con el veto entre versiones eso
    rechazaría un aviso legítimo. Las letras sí deben coincidir exactamente:
    cualquier palabra de más ("Reversamos", "[Bancolombia]") sigue siendo una
    cita. Una letra de otro alfabeto parecida (una "о" cirílica) no coincide.
    """
    visible = extractor._normalizar(texto).translate(_RELLENOS_INVISIBLES)
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", visible) if unicodedata.category(c) != "Mn"
    )
    return "".join(c for c in sin_tildes.casefold() if c.isalnum())


_CLAVES_ENCABEZADOS = frozenset(_clave_encabezado(e) for e in ENCABEZADOS_PERMITIDOS)


def _sin_imagenes_plantilla(previo: str) -> str:
    """El texto previo (ya normalizado) sin las referencias de imagen de la
    plantilla (``IMAGENES_PLANTILLA``) que tenga **al comienzo**. Las que
    vengan después de cualquier otro texto no se quitan."""
    inicio = 0
    while (imagen := _IMAGEN_PLANTILLA.match(previo, inicio)) is not None and imagen.end() > inicio:
        inicio = imagen.end()
    return previo[inicio:]


def _encabezado_permitido(previo: str) -> bool:
    """``True`` si el texto previo al aviso, tras quitar las imágenes de la
    plantilla del comienzo, es vacío o un encabezado conocido."""
    clave = _clave_encabezado(_sin_imagenes_plantilla(previo))
    return clave == "" or clave in _CLAVES_ENCABEZADOS


def _analizar(texto: str) -> tuple[str, str, extractor.MovimientoExtraido | None]:
    """(estado, texto desde el aviso o texto completo normalizado, movimiento).

    - ``AVISO_VALIDO``: el primer inicio de aviso tiene delante solo
      imágenes de la plantilla (``IMAGENES_PLANTILLA``, al comienzo) y un
      encabezado permitido, o parte o nada de eso, y el extractor lo lee;
    - ``AVISO_CITADO``: hay un inicio de aviso con otro texto delante. Es el
      caso del primer inicio con un texto desconocido delante y también el de
      un primer inicio que no se lee seguido de otro más adelante (ese otro
      tiene delante el primero);
    - ``SIN_AVISO``: ningún inicio de aviso, o uno solo que no se lee.
    """
    # Misma normalización que el extractor (invisibles fuera, espacios simples).
    normalizado = extractor._normalizar(texto)
    inicios = list(_INICIO_AVISO.finditer(normalizado))
    if not inicios:
        return SIN_AVISO, normalizado, None
    # Solo la primera posición: si lo previo no es un encabezado conocido, el
    # aviso está citado (ítem 21) y no se busca otro más adelante.
    if not _encabezado_permitido(normalizado[: inicios[0].start()]):
        return AVISO_CITADO, normalizado, None
    resto = normalizado[inicios[0].start():]
    movimiento = extractor.extraer(resto)
    if movimiento is not None and not _OTRO_AVISO.search(movimiento.descripcion):
        return AVISO_VALIDO, resto, movimiento
    return (AVISO_CITADO if len(inicios) > 1 else SIN_AVISO), normalizado, None


def _buscar_aviso(texto: str) -> tuple[str, extractor.MovimientoExtraido | None]:
    """Devuelve (texto desde el aviso reconocido o texto completo, movimiento)."""
    _, resto, movimiento = _analizar(texto)
    return resto, movimiento


def clasificar_correo(textos: Sequence[str]) -> tuple[str, extractor.MovimientoExtraido | None]:
    """Decide sobre todas las versiones del cuerpo (text/plain, HTML).

    Si **alguna** versión cita el aviso (``AVISO_CITADO``), el correo entero
    queda citado y no se lee ninguna: un HTML con "Reversamos..." delante veta
    un text/plain limpio y al revés. Si no, vale la primera versión con un
    aviso válido (el text/plain va primero; si es un relleno sin aviso, se usa
    el HTML). Si ninguna lo tiene, ``SIN_AVISO``.
    """
    analisis = [_analizar(texto) for texto in textos]
    if any(estado == AVISO_CITADO for estado, _, _ in analisis):
        return AVISO_CITADO, None
    for estado, _, movimiento in analisis:
        if estado == AVISO_VALIDO:
            return AVISO_VALIDO, movimiento
    return SIN_AVISO, None
