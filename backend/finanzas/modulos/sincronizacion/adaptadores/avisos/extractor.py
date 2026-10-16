"""Extractores de avisos de Bancolombia.

Funciones puras: reciben el texto de un aviso y devuelven un
``MovimientoExtraido`` o ``None`` cuando el texto no se reconoce.
No conocen Gmail, la base de datos ni la red.

Formatos reconocidos (el prefijo "Bancolombia:" es opcional):

* Compraste::

    Bancolombia: Compraste $245.700,00 en MERPAGO*TIENDAEJEMPLO con tu T.Deb
    *1234, el 07/08/2026 a las 16:42. Si tienes dudas, encuentranos aqui: ...

  Monto con punto de miles y coma decimal, fecha ``dd/mm/aaaa``.

* Transferiste::

    Bancolombia: Transferiste $4,500.00 desde tu cuenta *1234 a la cuenta
    *3000000000 el 14/08/26 a las 19:05. ¿Dudas? Llamanos al ...

  Monto con coma de miles y punto decimal, fecha ``dd/mm/aa`` (año 20aa).
  La cuenta origen es ``*`` + 4 dígitos; la cuenta destino, ``*`` + 4 a 20
  dígitos; devuelve solo los últimos cuatro, como ``*0000`` (D45, ítem 41).

* Transferiste a una llave (Bre-B, formato nuevo)::

    Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000
    desde tu cuenta *1234 a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28.
    Con Bre-b es de una y gratis. Dudas al 018000000000.

  Monto y fecha como en "Transferiste" (``$6,200.00``, ``dd/mm/aa``, año
  20aa). Devuelve ``tipo="transferencia"`` y como descripción el nombre de
  quien recibe, tal cual. El nombre del titular y la llave se validan pero no
  se devuelven. Reglas propias (nunca adivinar):

  - la llave es numérica, de 4 a 20 dígitos ASCII, o un alias: ``@`` seguido
    de 3 a 30 caracteres ASCII ``[A-Za-z0-9._-]`` (p. ej. ``@ejemplo12``; los
    dos formatos vistos en avisos reales). Llaves de correo, alias sin ``@``,
    con espacio, con caracteres no ASCII, con otros signos o de otro largo
    devuelven ``None``. La llave no lleva espacios, así que no puede comerse
    la cuenta, la fecha ni la hora;
  - el titular va seguido de ", transferiste" (sin la coma devuelve ``None``);
  - el titular es de 1 a 3 palabras de solo letras (A-Z con tildes, ü y ñ,
    en mayúscula o minúscula) separadas por un espacio, máximo 40
    caracteres, sin puntos ni otros signos. Así "Bancolombia:" seguido de
    una frase ("Reversamos esta transferencia. PERSONA, transferiste ...")
    no se toma como aviso;
  - el nombre de quien recibe tiene de 1 a 100 caracteres, empieza por una
    letra y solo puede tener letras, espacios y los signos ``. , ' - & *``;
    termina en letra o en un punto único tras una letra ("S.A.S.");
  - ningún nombre tiene dígitos, ``/``, ``:`` ni ``$``: así no puede
    "comerse" la llave, la cuenta, la fecha ni la hora. Tampoco pueden
    contener "Compraste", "Transferiste" ni "Recibiste". Consecuencia
    aceptada: nombres con dígitos u otros signos, o un titular de más de 3
    palabras, quedan como no reconocidos (se pueden reprocesar);
  - el nombre de quien recibe termina justo antes de " el dd/mm/aa a las";
  - el orden de las partes es fijo: "a la llave" va antes de "desde tu
    cuenta *dddd" y esta antes de "a NOMBRE". Otro orden devuelve ``None``.

* Recibiste una transferencia (ingreso, D12 / ítem 09)::

    Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO
    en tu cuenta **1234, el 29/09/2026 a las 10:00. Si tienes dudas, ...

  Monto con coma de miles, **sin decimales** (``$160,000``) o con exactamente
  2 decimales (``$160,000.00``); fecha ``dd/mm/aaaa`` (año 2000-2099); la
  cuenta es ``**`` + exactamente 4 dígitos (dos asteriscos). Devuelve
  ``tipo="ingreso"`` y como descripción el nombre de quien envía, tal cual.

* Retiraste (retiro en cajero, ítem 27 / D30)::

    Bancolombia: Retiraste $50.000,00 en CAJERO EJEMPLO de tu T.Deb **1234
    el 05/09/2026 a las 10:15. Si tienes dudas, ...

  Monto como "Compraste" (punto de miles, coma decimal), con exactamente 2
  decimales o sin decimales (``$50.000``); fecha ``dd/mm/aaaa``; la tarjeta es
  ``**`` + exactamente 4 dígitos. Devuelve ``tipo="compra"``, el cajero como
  descripción y ``categoria_al_leer="Retiro a efectivo"`` (D30): la
  sincronización se la asigna al guardarlo. El cajero tiene de 1 a 100
  caracteres y no puede contener " de tu T.", un ``*`` seguido de un dígito,
  una fecha ``dd/mm/aa``, una hora ``H:MM``, "Bancolombia:" ni una palabra que
  inicia otro aviso (``_GUARDA_TRAMO``).

* Pago por código QR (ítem 27 / D30)::

    Bancolombia: NOMBRE COMPLETO DEL TITULAR pagaste $12,000.00 por codigo QR
    desde tu cuenta *1234 a la llave 3000000000 el 10/09/2026 a las 11:20. ...

  Monto como "Transferiste" (coma de miles, punto decimal), con 2 decimales
  o sin decimales; fecha ``dd/mm/aaaa``. Devuelve ``tipo="transferencia"``
  con la descripción fija ``DESCRIPCION_PAGO_QR``: el aviso no nombra a quien
  recibe, y la llave, la cuenta origen y el titular se validan pero no se
  devuelven. Reglas propias (no son las de Bre-B, D25):

  - el titular es el nombre completo: de 1 a 10 palabras de solo letras
    **mayúsculas** (A-Z, Á É Í Ó Ú Ü Ñ) separadas por un espacio, máximo 80
    caracteres, sin coma ni otros signos, y ninguna palabra puede ser otra
    palabra de aviso (Compraste, Pagaste...). Las mayúsculas son a propósito
    (revisión del ítem 27): así una frase del banco antes de "pagaste"
    ("Bancolombia: Te recordamos que pagaste ...") no pasa por titular, como
    en D25. Los ejemplos de la especificación y los avisos vistos traen el
    nombre en mayúsculas. Consecuencia aceptada: un titular con minúsculas
    queda no reconocido (la prueba en seco lo mostraría; se puede reprocesar);
  - "por codigo QR" se escribe así (sin tilde, como en el aviso real);
  - la cuenta origen es ``*`` + 4 dígitos y la llave es **solo numérica**,
    de 4 a 20 dígitos ASCII. Otras llaves devuelven ``None``;
  - el orden de las partes es fijo.

* Pago por PSE ("Pagaste ... desde tu producto", ítem 27 / D30)::

    Bancolombia: Pagaste $350,000.00 a EMPRESA EJEMPLO SAS desde tu producto
    1234 el 04/09/2026 08:30:15. Si tienes dudas, ...

  Monto como "Transferiste", con 2 decimales o sin decimales; fecha
  ``dd/mm/aaaa``; la hora va **sin "a las"** (con o sin segundos); el
  producto es exactamente 4 dígitos **sin asterisco**. Devuelve
  ``tipo="compra"`` con la empresa como descripción. La empresa tiene de 1 a
  100 caracteres y la misma guarda que el cajero (no puede contener
  " desde tu producto", ``*`` + dígito, fechas, horas ni otro aviso).

Monto: se devuelve en centavos (``monto_centavos``). En "Compraste" y
"Transferiste" siempre con exactamente 2 decimales en el texto:
``$4,500.00`` -> 450000, ``$1.000,50`` -> 100050. En "Recibiste" y en los tres
avisos del ítem 27 los decimales son opcionales, pero si aparecen son
exactamente 2:
``$160,000`` -> 16000000, ``$160,000.00`` -> 16000000.

Hora (todos los avisos), con o sin cero inicial y ``:SS`` opcional:

* 24 h: ``H:MM`` / ``HH:MM``, hora 0-23;
* 12 h: hora 1-12 seguida de ``a. m.``, ``p. m.``, ``a.m.``, ``p.m.``, ``am``
  o ``pm`` (sin distinguir mayúsculas; espacio opcional entre el número y el
  indicador y entre "a." y "m."). ``12:xx a. m.`` -> 00:xx,
  ``12:xx p. m.`` -> 12:xx, ``1:05 p. m.`` -> 13:05. Hora 0 o 13+ con
  indicador devuelve ``None``.

Tras la hora va el punto final de la oración y puede seguir texto adicional.
Si el indicador termina en punto (``p. m.``), ese punto también cierra la
oración: se aceptan ``8:29 p. m. Si...`` y ``8:29 p. m.. Si...``.

Regla "nunca adivinar": solo se toleran diferencias inocuas (espacios o saltos
de línea repetidos, mayúsculas/minúsculas en las palabras fijas y el prefijo
"Bancolombia:"). Cualquier otra desviación devuelve ``None``. En particular:

* el monto debe tener exactamente el formato de su aviso, con los miles bien
  agrupados (``$500,00`` / ``$500.00`` / ``$500`` sin separador son válidos)
  y exactamente 2 decimales (1 o 3 decimales devuelven ``None``); solo
  "Recibiste" admite el monto sin decimales;
* un monto de 0 (``$0,00``, ``$0``), una fecha u hora imposibles (31/02,
  25:00, 13:00 p. m.) devuelven ``None``; ``$0,50`` es válido (50 centavos);
* en "Compraste" y "Recibiste" el año debe estar entre 2000 y 2099;
* solo se aceptan dígitos ASCII (0-9): otros dígitos Unicode devuelven ``None``;
* el comercio no puede contener "con tu T." en ninguna posición (sin
  distinguir mayúsculas, con o sin espacio delante). Así el comercio termina
  siempre antes de la primera aparición de "con tu T." tras " en ", y si el
  final del aviso no encaja (o el comercio está vacío o pegado a "con") el
  patrón no puede saltar a una repetición en el texto adicional. Consecuencia
  aceptada: un comercio como "TIENDAcon tu T.X" no se reconoce.
* guarda estructural: el comercio tampoco puede contener un ``*`` seguido de
  4 dígitos (``*1234``) ni una fecha ``dd/mm/aa`` (también cubre
  ``dd/mm/aaaa``). Así, aunque el tramo fijo " con tu T.Deb" venga deformado,
  el comercio no puede cruzar la tarjeta ni la fecha del aviso original para
  llegar a una repetición en el texto adicional. Consecuencia aceptada: un
  comercio que contenga ``*`` + 4 dígitos o una fecha no se reconoce.
* "Recibiste": quien envía tiene de 1 a 100 caracteres y la misma clase de
  guarda estructural. No puede contener " en tu cuenta *", un ``*`` seguido
  de un dígito, una fecha con cualquier separador (``d/m/aa``, ``dd-mm-aaaa``,
  ``dd.mm.aa``...), una hora ``H:MM``, ", el " seguido de un dígito,
  " a las " seguido de un dígito, "Bancolombia:" ni las palabras
  "Compraste", "Transferiste" o "Recibiste" (sin distinguir mayúsculas, en
  cualquier posición). Así el nombre termina siempre antes del primer
  " en tu cuenta" y no puede "comerse" la cuenta, la fecha o la hora propias
  (aunque vengan deformadas) ni un segundo aviso en el texto adicional.
  Consecuencia aceptada: un nombre que contenga alguno de esos textos no se
  reconoce (queda para revisión), p. ej. "PERSONA 1-2-2026" o "TIENDA 24:00".
* "Recibiste" con otra redacción ("Recibiste un pago", "Recibiste una
  transferencia de ... por ...", sin "en tu cuenta", cuenta con uno o tres
  asteriscos, fecha ``dd/mm/aa``, monto ``$160.000``) devuelve ``None``.

Antes de aplicar los patrones se eliminan todos los caracteres invisibles de
formato (categoría Unicode "Cf": ancho cero, guion suave, marcas de
dirección, etc.) más U+034F y U+180E, y después se colapsan los espacios.

El aviso debe estar al inicio del texto (tras normalizar espacios) y solo se
toma el primero: lo que siga al punto final se ignora aunque sea otro aviso.
Quien llame (la sincronización con Gmail) debe pasar el texto ya limpio. La
sincronización (``sincronizacion.extraer_aviso``) solo llama al extractor si
antes del aviso no hay nada o hay un encabezado de plantilla conocido; así un
aviso citado dentro de otro correo queda como no reconocido (ítem 21).

Los últimos 4 dígitos de la tarjeta, de la cuenta origen y de la cuenta que
recibe el ingreso, la llave Bre-B o QR, el producto PSE y el nombre del
titular se validan en el patrón pero no se devuelven, porque el modelo de
datos no los guarda.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from finanzas.modulos.sincronizacion.contratos import MovimientoExtraido

TIPO_COMPRA = "compra"
TIPO_TRANSFERENCIA = "transferencia"
TIPO_INGRESO = "ingreso"




# Partes comunes de los patrones. El texto se normaliza antes (un solo espacio
# entre palabras), por eso los patrones usan espacios simples.
# Todos los patrones usan re.ASCII para que \d solo acepte 0-9.
_PREFIJO = r"^(?:bancolombia: )?"
# Hora con o sin cero inicial, segundos opcionales e indicador de 12 h
# opcional. "ap_punto" es un indicador que termina en punto ("p. m.", "a.m.");
# "ap" es uno sin punto ("pm", "AM").
_HORA = (
    r"a las (?P<hora>[0-9]{1,2}):(?P<minuto>[0-9]{2})(?::(?P<segundo>[0-9]{2}))?"
    r"(?: ?(?:(?P<ap_punto>[ap])\. ?m\.|(?P<ap>[ap])m))?"
)
# Punto final de la oración y, opcionalmente, texto adicional. Si el
# indicador de la hora ya terminó en punto, ese punto cierra la oración y un
# segundo punto es opcional.
_FINAL = r"(?(ap_punto)\.?|\.)(?: .*)?$"

# Monto "Compraste": punto de miles, coma decimal. Sin ceros a la izquierda.
_MONTO_COMPRA = r"\$(?P<entero>0|[1-9]\d{0,2}(?:\.\d{3})*),(?P<decimales>\d{2})"
# Monto "Transferiste": coma de miles, punto decimal. Sin ceros a la izquierda.
_MONTO_TRANSFERENCIA = r"\$(?P<entero>0|[1-9]\d{0,2}(?:,\d{3})*)\.(?P<decimales>\d{2})"

_PATRON_COMPRASTE = re.compile(
    _PREFIJO
    + r"compraste "
    + _MONTO_COMPRA
    # El comercio no puede contener "con tu t." en ninguna posición, ni un
    # "*" + 4 dígitos, ni una fecha dd/mm/aa: así no puede cruzar el tramo
    # fijo, la tarjeta ni la fecha del aviso hasta una repetición posterior.
    + r" en (?P<comercio>(?:(?!con tu t\.|\*[0-9]{4}|[0-9]{2}/[0-9]{2}/[0-9]{2}).)+?)"
    + r" con tu t\.deb \*\d{4}, el "
    + r"(?P<dia>\d{2})/(?P<mes>\d{2})/(?P<anio>20\d{2}) "
    + _HORA
    + _FINAL,
    re.IGNORECASE | re.ASCII,
)

# Monto "Recibiste": coma de miles y decimales opcionales (si están, son
# exactamente 2). Sin ceros a la izquierda.
_MONTO_INGRESO = r"\$(?P<entero>0|[1-9]\d{0,2}(?:,\d{3})*)(?:\.(?P<decimales>\d{2}))?"

# Guarda estructural de quien envía (ver el docstring del módulo): en ninguna
# posición puede empezar " en tu cuenta *", un "*" + dígito, una fecha con
# cualquier separador (/, - o .), una hora H:MM, ", el " + dígito,
# " a las " + dígito, otro prefijo "Bancolombia:" ni otro inicio de aviso.
# Así el nombre no puede cruzar la fecha y la hora propias (aunque vengan
# deformadas) hasta una cuenta y una fecha válidas en el texto adicional.
_GUARDA_NOMBRE = (
    r"(?! en tu cuenta \*|\*[0-9]"
    r"|[0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4}|[0-9]{1,2}:[0-9]{2}"
    r"|, el [0-9]| a las [0-9]"
    r"|bancolombia:|compraste|transferiste|recibiste)"
)

_PATRON_RECIBISTE = re.compile(
    _PREFIJO
    + r"recibiste una transferencia por "
    + _MONTO_INGRESO
    + r" de (?P<nombre>(?:" + _GUARDA_NOMBRE + r".){1,100}?)"
    + r" en tu cuenta \*\*[0-9]{4}, el "
    + r"(?P<dia>\d{2})/(?P<mes>\d{2})/(?P<anio>20\d{2}) "
    + _HORA
    + _FINAL,
    re.IGNORECASE | re.ASCII,
)

_PATRON_TRANSFERISTE = re.compile(
    _PREFIJO
    + r"transferiste "
    + _MONTO_TRANSFERENCIA
    + r" desde tu cuenta \*\d{4} a la cuenta (?P<destino>\*[0-9]{4,20}) el "
    + r"(?P<dia>\d{2})/(?P<mes>\d{2})/(?P<anio>\d{2}) "
    + _HORA
    + _FINAL,
    re.IGNORECASE | re.ASCII,
)


# "Transferiste" a llave (Bre-B). Con re.ASCII las letras con tilde van
# explícitas (y en ambos casos, porque IGNORECASE solo pliega ASCII).
#
# Titular: de 1 a 3 palabras de solo letras separadas por un espacio, máximo
# 40 caracteres, sin puntos ni otros signos. En el aviso real es el nombre de
# pila. Tan estricto a propósito: "Bancolombia:" debe ir seguido del aviso y
# no de una frase ("Bancolombia: Reversamos esta transferencia. PERSONA,
# transferiste ..." no es un aviso nuevo). Un titular más largo queda "no
# reconocido" y se puede reprocesar.
#
# Quien recibe: empieza por letra; letras españolas, espacio y . , ' - & *;
# termina en letra o en un punto único tras una letra ("S.A.S."). Sin dígitos
# ni / : $, así no puede cruzar la llave, la cuenta, la fecha ni la hora.
_LETRA = r"A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
_SIN_OTRO_AVISO = r"(?!compraste|transferiste|recibiste)"
_PALABRA_TITULAR = _SIN_OTRO_AVISO + r"[" + _LETRA + r"]+"
_TITULAR = (
    r"(?=[" + _LETRA + r" ]{1,40},)"
    + _PALABRA_TITULAR + r"(?: " + _PALABRA_TITULAR + r"){0,2}"
)
# Llave Bre-B: numérica (4 a 20 dígitos) o alias "@" + 3 a 30 caracteres
# [A-Za-z0-9._-] en ASCII (D25, alias aprobado por el dueño). Ninguna admite
# espacio, "/", ":" ni "$", así que la llave termina justo antes de " desde tu
# cuenta" y no puede comerse la cuenta, la fecha ni la hora. Solo Bre-B: el
# pago QR sigue aceptando solo llaves numéricas.
_LLAVE_BREB = r"(?:[0-9]{4,20}|@[A-Za-z0-9._-]{3,30})"
_QUIEN_RECIBE = _SIN_OTRO_AVISO + r"[" + _LETRA + r"](?:" + _SIN_OTRO_AVISO + r"[" + _LETRA + r" .,'&*-]){0,99}?"

_PATRON_TRANSFERISTE_LLAVE = re.compile(
    _PREFIJO
    + _TITULAR
    # El titular no termina en espacio ("PERSONA , transferiste" no vale).
    + r"(?<! ), transferiste "
    + _MONTO_TRANSFERENCIA
    + r" a la llave " + _LLAVE_BREB + r" desde tu cuenta \*[0-9]{4} a "
    + r"(?P<destino>" + _QUIEN_RECIBE + r")"
    + r"(?:(?<=[" + _LETRA + r"])|(?<=[" + _LETRA + r"]\.)) el "
    + r"(?P<dia>[0-9]{2})/(?P<mes>[0-9]{2})/(?P<anio>[0-9]{2}) "
    + _HORA
    + _FINAL,
    re.IGNORECASE | re.ASCII,
)


# --- Avisos del ítem 27 (D30): retiro, pago QR y pago PSE ---------------------

CATEGORIA_RETIRO = "Retiro a efectivo"
# El aviso de pago QR no nombra a quien recibe y la llave no se guarda (D30):
# todos los pagos QR llevan esta descripción.
DESCRIPCION_PAGO_QR = "Pago por código QR"

# Monto "Retiraste": como "Compraste", pero los decimales son opcionales (si
# están, son exactamente 2).
_MONTO_COMPRA_DECIMALES_OPCIONALES = (
    r"\$(?P<entero>0|[1-9]\d{0,2}(?:\.\d{3})*)(?:,(?P<decimales>\d{2}))?"
)
# Monto de los pagos QR y PSE: como "Transferiste", con decimales opcionales
# (la misma forma que "Recibiste").
_MONTO_PAGO = _MONTO_INGRESO

# Palabras que inician un aviso. Ninguna descripción ni titular nuevo puede
# contenerlas: así no "cruzan" hasta un segundo aviso.
_PALABRAS_AVISO = r"compraste|transferiste|recibiste|retiraste|pagaste"

# Guarda de un tramo libre (cajero, empresa): en ninguna posición puede
# empezar un "*" + dígito, una fecha dd/mm/aa (también dd/mm/aaaa, con / - o
# .), una hora H:MM, "Bancolombia:" ni otra palabra de aviso. Así el tramo
# no puede cruzar la tarjeta, el producto, la fecha ni la hora del aviso
# hasta una repetición en el texto adicional.
_GUARDA_TRAMO = (
    r"\*[0-9]|[0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4}|[0-9]{1,2}:[0-9]{2}"
    r"|bancolombia:|" + _PALABRAS_AVISO
)

# Hora sin "a las" (pago PSE): mismos grupos que _HORA.
_HORA_SIN_A_LAS = _HORA[len("a las "):]

_PATRON_RETIRASTE = re.compile(
    _PREFIJO
    + r"retiraste "
    + _MONTO_COMPRA_DECIMALES_OPCIONALES
    + r" en (?P<cajero>(?:(?! de tu t\.|" + _GUARDA_TRAMO + r").){1,100}?)"
    + r" de tu t\.deb \*\*[0-9]{4} el "
    + r"(?P<dia>[0-9]{2})/(?P<mes>[0-9]{2})/(?P<anio>20[0-9]{2}) "
    + _HORA
    + _FINAL,
    re.IGNORECASE | re.ASCII,
)

# Titular del pago QR: el nombre completo, de 1 a 10 palabras de solo letras
# MAYÚSCULAS, máximo 80 caracteres, seguido de " pagaste ". Ninguna palabra
# puede ser otra palabra de aviso. ``(?-i:...)`` apaga IGNORECASE solo en las
# letras del titular (los patrones que lo usan, aquí y en
# ``sincronizacion._INICIO_AVISO``, ignoran mayúsculas en lo demás).
_MAYUSCULA = r"(?-i:[A-ZÁÉÍÓÚÜÑ])"
_PALABRA_TITULAR_QR = r"(?!(?:" + _PALABRAS_AVISO + r")\b)" + _MAYUSCULA + r"+"
_TITULAR_QR = (
    r"(?=(?:" + _MAYUSCULA + r"| ){1,80}? pagaste )"
    + _PALABRA_TITULAR_QR + r"(?: " + _PALABRA_TITULAR_QR + r"){0,9}"
)

_PATRON_PAGO_QR = re.compile(
    _PREFIJO
    + _TITULAR_QR
    + r" pagaste "
    + _MONTO_PAGO
    + r" por codigo qr desde tu cuenta \*[0-9]{4} a la llave [0-9]{4,20} el "
    + r"(?P<dia>[0-9]{2})/(?P<mes>[0-9]{2})/(?P<anio>20[0-9]{2}) "
    + _HORA
    + _FINAL,
    re.IGNORECASE | re.ASCII,
)

_PATRON_PAGO_PSE = re.compile(
    _PREFIJO
    + r"pagaste "
    + _MONTO_PAGO
    + r" a (?P<empresa>(?:(?! desde tu producto |" + _GUARDA_TRAMO + r").){1,100}?)"
    + r" desde tu producto [0-9]{4} el "
    + r"(?P<dia>[0-9]{2})/(?P<mes>[0-9]{2})/(?P<anio>20[0-9]{2}) "
    + _HORA_SIN_A_LAS
    + _FINAL,
    re.IGNORECASE | re.ASCII,
)


# Invisibles que no son de categoría "Cf" pero también se eliminan:
# U+034F (combining grapheme joiner) y U+180E (separador de vocal mongol).
_INVISIBLES_EXTRA = frozenset("\u034f\u180e")


def _normalizar(texto: str) -> str:
    """Quita los caracteres invisibles de formato (categoría Unicode "Cf",
    U+034F y U+180E) y colapsa espacios, tabulaciones y saltos de línea en un
    solo espacio."""
    visible = "".join(
        c for c in texto
        if unicodedata.category(c) != "Cf" and c not in _INVISIBLES_EXTRA
    )
    return " ".join(visible.split())


def _monto_centavos(entero: str, decimales: str, separador_miles: str) -> int | None:
    """Convierte el monto a centavos; ``None`` si es 0."""
    valor = int(entero.replace(separador_miles, "")) * 100 + int(decimales)
    return valor if valor > 0 else None


def _hora_24(m: re.Match[str]) -> int | None:
    """Hora en formato 0-23; ``None`` si no es válida para su formato."""
    hora = int(m["hora"])
    indicador = m["ap_punto"] or m["ap"]
    if indicador is None:
        return hora if hora <= 23 else None
    if not 1 <= hora <= 12:
        return None
    if indicador.lower() == "a":
        return 0 if hora == 12 else hora
    return 12 if hora == 12 else hora + 12


def _fecha_hora(m: re.Match[str], anio: int) -> datetime | None:
    """Arma la fecha y hora; ``None`` si no existe (p. ej. 31/02 o 25:00)."""
    hora = _hora_24(m)
    if hora is None:
        return None
    try:
        return datetime(
            anio,
            int(m["mes"]),
            int(m["dia"]),
            hora,
            int(m["minuto"]),
            int(m["segundo"] or 0),
        )
    except ValueError:
        return None


def extraer_compraste(texto: str | None) -> MovimientoExtraido | None:
    """Lee un aviso "Compraste". Devuelve ``None`` si no coincide exactamente."""
    m = _PATRON_COMPRASTE.match(_normalizar(texto or ""))
    if m is None:
        return None
    monto = _monto_centavos(m["entero"], m["decimales"], ".")
    fecha_hora = _fecha_hora(m, int(m["anio"]))
    if monto is None or fecha_hora is None:
        return None
    # No hace falta recortar ni revisar si el comercio está vacío: el texto ya
    # está normalizado y el patrón exige al menos un carácter entre " en " y
    # " con tu", así que nunca empieza ni termina en espacio.
    return MovimientoExtraido(TIPO_COMPRA, monto, fecha_hora, m["comercio"])


def extraer_transferiste(texto: str | None) -> MovimientoExtraido | None:
    """Lee un aviso "Transferiste". Devuelve ``None`` si no coincide exactamente.

    El año de dos dígitos se interpreta como 20aa.
    """
    m = _PATRON_TRANSFERISTE.match(_normalizar(texto or ""))
    if m is None:
        return None
    monto = _monto_centavos(m["entero"], m["decimales"], ",")
    fecha_hora = _fecha_hora(m, 2000 + int(m["anio"]))
    if monto is None or fecha_hora is None:
        return None
    return MovimientoExtraido(TIPO_TRANSFERENCIA, monto, fecha_hora, "*" + m["destino"][-4:])


def extraer_transferiste_llave(texto: str | None) -> MovimientoExtraido | None:
    """Lee un aviso "transferiste ... a la llave" (Bre-B).

    Devuelve ``None`` si no coincide exactamente. La descripción es el nombre
    de quien recibe tal como aparece; la llave, la cuenta origen y el nombre
    del titular se validan pero no se devuelven. El año de dos dígitos se
    interpreta como 20aa.
    """
    m = _PATRON_TRANSFERISTE_LLAVE.match(_normalizar(texto or ""))
    if m is None:
        return None
    monto = _monto_centavos(m["entero"], m["decimales"], ",")
    fecha_hora = _fecha_hora(m, 2000 + int(m["anio"]))
    if monto is None or fecha_hora is None:
        return None
    # El texto está normalizado y el nombre empieza por letra y va entre
    # espacios fijos del patrón: no empieza ni termina en espacio.
    return MovimientoExtraido(TIPO_TRANSFERENCIA, monto, fecha_hora, m["destino"])


def extraer_recibiste(texto: str | None) -> MovimientoExtraido | None:
    """Lee un aviso "Recibiste una transferencia" (ingreso).

    Devuelve ``None`` si no coincide exactamente. La descripción es el nombre
    de quien envía tal como aparece; la cuenta ``**dddd`` se valida pero no se
    devuelve.
    """
    m = _PATRON_RECIBISTE.match(_normalizar(texto or ""))
    if m is None:
        return None
    monto = _monto_centavos(m["entero"], m["decimales"] or "00", ",")
    fecha_hora = _fecha_hora(m, int(m["anio"]))
    if monto is None or fecha_hora is None:
        return None
    # Como en "Compraste", el texto normalizado y los espacios fijos del patrón
    # garantizan que el nombre no empieza ni termina en espacio.
    return MovimientoExtraido(TIPO_INGRESO, monto, fecha_hora, m["nombre"])


def _leer_monto_y_fecha(m: re.Match[str], separador_miles: str) -> tuple[int, datetime] | None:
    """Monto (decimales opcionales) y fecha ``dd/mm/aaaa`` de los avisos del ítem 27."""
    monto = _monto_centavos(m["entero"], m["decimales"] or "00", separador_miles)
    fecha_hora = _fecha_hora(m, int(m["anio"]))
    if monto is None or fecha_hora is None:
        return None
    return monto, fecha_hora


def extraer_retiraste(texto: str | None) -> MovimientoExtraido | None:
    """Lee un aviso "Retiraste" (retiro en cajero, D30).

    Devuelve ``None`` si no coincide exactamente. Tipo ``compra``, el cajero
    como descripción y la categoría "Retiro a efectivo" en
    ``categoria_al_leer``. La tarjeta ``**dddd`` se valida pero no se devuelve.
    """
    m = _PATRON_RETIRASTE.match(_normalizar(texto or ""))
    if m is None:
        return None
    leido = _leer_monto_y_fecha(m, ".")
    if leido is None:
        return None
    return MovimientoExtraido(TIPO_COMPRA, leido[0], leido[1], m["cajero"], CATEGORIA_RETIRO)


def extraer_pago_qr(texto: str | None) -> MovimientoExtraido | None:
    """Lee un aviso "NOMBRE pagaste ... por codigo QR" (D30).

    Devuelve ``None`` si no coincide exactamente. Tipo ``transferencia`` con
    la descripción fija ``DESCRIPCION_PAGO_QR``; el titular, la cuenta origen
    y la llave se validan pero no se devuelven.
    """
    m = _PATRON_PAGO_QR.match(_normalizar(texto or ""))
    if m is None:
        return None
    leido = _leer_monto_y_fecha(m, ",")
    if leido is None:
        return None
    return MovimientoExtraido(TIPO_TRANSFERENCIA, leido[0], leido[1], DESCRIPCION_PAGO_QR)


def extraer_pago_pse(texto: str | None) -> MovimientoExtraido | None:
    """Lee un aviso "Pagaste ... desde tu producto" (pago por PSE, D30).

    Devuelve ``None`` si no coincide exactamente. Tipo ``compra`` con la
    empresa como descripción; el producto se valida pero no se devuelve.
    """
    m = _PATRON_PAGO_PSE.match(_normalizar(texto or ""))
    if m is None:
        return None
    leido = _leer_monto_y_fecha(m, ",")
    if leido is None:
        return None
    return MovimientoExtraido(TIPO_COMPRA, leido[0], leido[1], m["empresa"])


_EXTRACTORES = (
    extraer_compraste,
    extraer_transferiste,
    extraer_transferiste_llave,
    extraer_recibiste,
    extraer_retiraste,
    extraer_pago_qr,
    extraer_pago_pse,
)


def extraer(texto: str | None) -> MovimientoExtraido | None:
    """Prueba cada extractor en orden y devuelve el primer movimiento reconocido.

    ``None`` significa "no reconocido": el correo debe registrarse para revisión.
    """
    for extractor in _EXTRACTORES:
        movimiento = extractor(texto)
        if movimiento is not None:
            return movimiento
    return None
