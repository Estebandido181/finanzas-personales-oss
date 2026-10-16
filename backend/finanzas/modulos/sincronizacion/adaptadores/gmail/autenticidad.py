"""Gramática y decisión de autenticidad del correo; falla cerrado."""
from __future__ import annotations
import re
from collections.abc import Sequence
from dataclasses import dataclass
from finanzas.modulos.sincronizacion.contratos import CorreoGmail, como_remitentes

# --- Remitente y autenticación -----------------------------------------------------
#
# El filtro "from:" de la consulta mira el encabezado From, que cualquiera
# puede falsificar. Por eso, tras descargar el correo, se exige:
#
# 1. que From tenga exactamente una dirección y sea una de las dos oficiales
#    (``REMITENTES_OFICIALES``, D30);
# 2. que Gmail (mx.google.com) informe dmarc=pass con header.from alineado
#    con el dominio de ESA dirección oficial. DMARC es obligatorio (D15): DKIM
#    o SPF por sí solos no bastan.
#
# Solo se usa el PRIMER Authentication-Results: Gmail lo añade arriba de
# todo al recibir el correo. Los que vengan más abajo pudo escribirlos el
# remitente (un atacante) y se ignoran.

SERVIDOR_AUTENTICADOR = "mx.google.com"

# --- Analizador estricto de Authentication-Results (RFC 8601) ------------------
#
# Gramática que se acepta (subconjunto estricto de la RFC 8601):
#
#   encabezado  = authserv-id [ versión ] ( "; none" / 1*( ";" resinfo ) )
#   resinfo     = método [ "/" versión ] "=" resultado
#                 [ "reason" "=" valor ] *propiedad
#   propiedad   = ptype "." nombre "=" pvalor
#   pvalor      = token / cadena / [ parte-local ] "@" dominio
#
# Los comentarios "( ... )" (anidables, con "\" como escape) y los espacios se
# descartan. Cualquier cosa fuera de la gramática invalida el encabezado
# COMPLETO (se devuelve ``None``): así nada que escriba el remitente (su MAIL
# FROM, su HELO, su selector DKIM) puede partir el encabezado y fabricar un
# resultado "pass". Si Gmail cambiara el formato, el correo queda como "no
# reconocido" (falla cerrado) y el log lo muestra como ``encabezado_invalido``.

# Resultados válidos (RFC 8601, sección 2.7, y registros de IANA).
RESULTADOS_VALIDOS = frozenset(
    {"pass", "fail", "softfail", "neutral", "none", "temperror", "permerror", "policy", "hardfail"}
)
TIPOS_PROPIEDAD = frozenset({"smtp", "header", "body", "policy"})

_SEPARADORES = frozenset(";=.@/")
_CARACTERES_PALABRA = re.compile(r"[A-Za-z0-9_+\-]+")
# Saltos de línea que no son un plegado (CRLF, CR o LF sin espacio detrás).
_SALTO_SIN_PLEGAR = re.compile(r"\r\n(?![ \t])|\r(?!\n)|(?<!\r)\n(?![ \t])")
# Caracteres de control (C0 salvo tabulador y saltos de línea, DEL y C1).
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

_METODO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
_NOMBRE_PROPIEDAD = re.compile(r"[A-Za-z0-9_-]+")
_VERSION = re.compile(r"[0-9]+")
_VALOR_TOKEN = re.compile(r"[A-Za-z0-9._+-]+")
_VALOR_BASE64 = re.compile(r"[A-Za-z0-9+/=]+")
_DOMINIO = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+\.?"
)


@dataclass(frozen=True)
class PropiedadAutenticacion:
    """Una propiedad ``ptype.nombre=valor`` (``tipo`` y ``nombre`` en minúsculas).

    ``dominio`` es el dominio del valor (en minúsculas y sin punto final) si
    el valor es ``[parte-local]@dominio`` o un token con forma de dominio;
    ``None`` en otro caso (p. ej. una cadena entre comillas sin ``@`` detrás).
    """

    tipo: str
    nombre: str
    valor: str
    dominio: str | None


@dataclass(frozen=True)
class ResultadoAutenticacion:
    """Un ``resinfo``: ``metodo[/version]=resultado`` con sus propiedades."""

    metodo: str
    version: str | None
    resultado: str
    razon: str | None
    propiedades: tuple[PropiedadAutenticacion, ...]


@dataclass(frozen=True)
class ResultadosAutenticacion:
    """Encabezado ``Authentication-Results`` ya analizado.

    ``resultados`` está vacío si el encabezado es ``mx.google.com; none``.
    """

    servidor: str
    version: str | None
    resultados: tuple[ResultadoAutenticacion, ...]


@dataclass(frozen=True)
class _Token:
    """Pieza léxica. ``tipo`` es ``"palabra"``, ``"cadena"`` o el separador
    (``;``, ``=``, ``.``, ``@``, ``/``). ``pegado`` indica que no hay espacio
    ni comentario entre este token y el anterior."""

    tipo: str
    texto: str
    pegado: bool


class _ErrorGramatica(Exception):
    """El encabezado se sale de la gramática."""


def _tokenizar(valor: str) -> list[_Token] | None:
    """Divide el encabezado en tokens; ``None`` si hay algo inválido
    (paréntesis o comillas sin cerrar, caracteres de control, saltos de línea
    sin plegar o caracteres fuera de la gramática)."""
    if _CONTROL.search(valor) or _SALTO_SIN_PLEGAR.search(valor):
        return None
    tokens: list[_Token] = []
    pegado = False
    i, n = 0, len(valor)
    while i < n:
        caracter = valor[i]
        if caracter in " \t\r\n":
            pegado = False
            i += 1
        elif caracter == "(":
            # Comentario, con anidamiento y "\" como escape. Se descarta.
            profundidad = 0
            while i < n:
                caracter = valor[i]
                if caracter == "\\":
                    if i + 1 >= n:
                        return None
                    i += 2
                    continue
                if caracter == "(":
                    profundidad += 1
                elif caracter == ")":
                    profundidad -= 1
                    if profundidad == 0:
                        break
                i += 1
            if profundidad != 0:
                return None  # paréntesis sin cerrar
            i += 1
            pegado = False
        elif caracter == '"':
            # Cadena entre comillas, con "\" como escape.
            partes: list[str] = []
            i += 1
            while True:
                if i >= n:
                    return None  # comillas sin cerrar
                caracter = valor[i]
                if caracter == "\\":
                    if i + 1 >= n:
                        return None
                    partes.append(valor[i + 1])
                    i += 2
                elif caracter == '"':
                    i += 1
                    break
                else:
                    partes.append(caracter)
                    i += 1
            tokens.append(_Token("cadena", "".join(partes), pegado))
            pegado = True
        elif caracter in _SEPARADORES:
            tokens.append(_Token(caracter, caracter, pegado))
            pegado = True
            i += 1
        else:
            palabra = _CARACTERES_PALABRA.match(valor, i)
            if palabra is None:
                return None  # ")" suelto, ",", ":", "\", no ASCII...
            tokens.append(_Token("palabra", palabra.group(), pegado))
            pegado = True
            i = palabra.end()
    return tokens


class _Analizador:
    """Analizador descendente sobre la lista de tokens. Cualquier desviación
    lanza ``_ErrorGramatica``."""

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    # Utilidades --------------------------------------------------------------

    def _actual(self) -> _Token | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _siguiente(self) -> _Token | None:
        return self._tokens[self._pos + 1] if self._pos + 1 < len(self._tokens) else None

    def _es(self, tipo: str, token: _Token | None = None) -> bool:
        token = self._actual() if token is None else token
        return token is not None and token.tipo == tipo

    def _esperar(self, tipo: str) -> _Token:
        token = self._actual()
        if token is None or token.tipo != tipo:
            raise _ErrorGramatica
        self._pos += 1
        return token

    def _esperar_palabra(self, patron: re.Pattern[str]) -> str:
        texto = self._esperar("palabra").texto
        if not patron.fullmatch(texto):
            raise _ErrorGramatica
        return texto

    def _corrida(self, tipos: frozenset[str]) -> str:
        """Tokens seguidos SIN espacio ni comentario entre ellos, de los tipos
        dados (p. ej. ``an`` ``.`` ``banco`` ``.`` ``com``), unidos en un texto."""
        token = self._actual()
        if token is None or token.tipo not in tipos:
            raise _ErrorGramatica
        partes = [token.texto]
        self._pos += 1
        while (token := self._actual()) is not None and token.pegado and token.tipo in tipos:
            partes.append(token.texto)
            self._pos += 1
        return "".join(partes)

    def _separado(self) -> None:
        """Tras un valor solo puede venir el final, ``;`` o un espacio/comentario.
        Así ``header.s=header.d=banco`` o ``header.d=banco"x"`` no pasan."""
        token = self._actual()
        if token is not None and token.tipo != ";" and token.pegado:
            raise _ErrorGramatica

    # Gramática ---------------------------------------------------------------

    def encabezado(self) -> ResultadosAutenticacion:
        servidor = self._corrida(frozenset({"palabra", "."}))
        if servidor.lower() != SERVIDOR_AUTENTICADOR:
            raise _ErrorGramatica
        version = None
        if self._es("palabra"):
            version = self._esperar_palabra(_VERSION)
        resultados: list[ResultadoAutenticacion] = []
        if self._actual() is None:
            raise _ErrorGramatica  # hace falta "; none" o al menos un resultado
        while self._actual() is not None:
            self._esperar(";")
            token, siguiente = self._actual(), self._siguiente()
            if (
                not resultados and siguiente is None and token is not None
                and token.tipo == "palabra" and token.texto.lower() == "none"
            ):
                self._pos += 1
                break  # "mx.google.com; none": sin resultados
            resultados.append(self._resinfo())
        return ResultadosAutenticacion(servidor.lower(), version, tuple(resultados))

    def _resinfo(self) -> ResultadoAutenticacion:
        metodo = self._esperar_palabra(_METODO).lower()
        version = None
        if self._es("/"):
            self._pos += 1
            version = self._esperar_palabra(_VERSION)
        self._esperar("=")
        resultado = self._esperar("palabra").texto.lower()
        if resultado not in RESULTADOS_VALIDOS:
            raise _ErrorGramatica
        razon = None
        token, siguiente = self._actual(), self._siguiente()
        if (
            token is not None and token.tipo == "palabra" and token.texto.lower() == "reason"
            and self._es("=", siguiente)
        ):
            self._pos += 2
            razon = self._valor_simple()
            self._separado()
        propiedades: list[PropiedadAutenticacion] = []
        while self._actual() is not None and not self._es(";"):
            propiedades.append(self._propiedad())
        return ResultadoAutenticacion(metodo, version, resultado, razon, tuple(propiedades))

    def _valor_simple(self) -> str:
        """Un token ``[A-Za-z0-9._+-]`` o una cadena entre comillas."""
        if self._es("cadena"):
            return self._esperar("cadena").texto
        valor = self._corrida(frozenset({"palabra", "."}))
        if not _VALOR_TOKEN.fullmatch(valor):
            raise _ErrorGramatica
        return valor

    def _propiedad(self) -> PropiedadAutenticacion:
        tipo = self._esperar("palabra").texto.lower()
        if tipo not in TIPOS_PROPIEDAD:
            raise _ErrorGramatica
        self._esperar(".")
        nombre = self._esperar_palabra(_NOMBRE_PROPIEDAD).lower()
        self._esperar("=")
        if (tipo, nombre) == ("header", "b") and not self._es("cadena"):
            # Firma DKIM (base64): es el único valor que admite "=" y "/".
            valor = self._corrida(frozenset({"palabra", "=", "/"}))
            if not _VALOR_BASE64.fullmatch(valor):
                raise _ErrorGramatica
            dominio = None
        else:
            valor, dominio = self._pvalor()
        self._separado()
        return PropiedadAutenticacion(tipo, nombre, valor, dominio)

    def _pvalor(self) -> tuple[str, str | None]:
        """``token``, ``"cadena"`` o ``[parte-local]@dominio``. Devuelve
        ``(valor, dominio)``. La ``@`` que cuenta es la que cierra la parte
        local respetando las comillas: en ``"x@banco"@evil.com`` el dominio
        es ``evil.com``."""
        if self._es("@"):
            local = ""
        elif self._es("cadena"):
            cadena = self._esperar("cadena").texto
            token = self._actual()
            if token is None or token.tipo != "@" or not token.pegado:
                # Cadena suelta: no aporta dominio. Es a propósito también
                # para el MAIL FROM real, que Gmail escribe entero entre
                # comillas (smtp.mailfrom="b-...=gmail.com@trans.an.banco"):
                # su dominio queda en None porque SPF nunca cuenta.
                return cadena, None
            # Sin comillas ni escapes: así lo revisa ``_semantica_valida``.
            local = cadena
        else:
            local = self._valor_simple()
            token = self._actual()
            if token is None or token.tipo != "@" or not token.pegado:
                dominio = local.rstrip(".").lower() if _DOMINIO.fullmatch(local) else None
                return local, dominio
        self._esperar("@")
        token = self._actual()
        if token is None or not token.pegado:
            raise _ErrorGramatica  # "@" sin dominio pegado
        dominio = self._corrida(frozenset({"palabra", "."}))
        if not _DOMINIO.fullmatch(dominio):
            raise _ErrorGramatica
        return f"{local}@{dominio}", dominio.rstrip(".").lower()


def analizar_authentication_results(valor: str) -> ResultadosAutenticacion | None:
    """Analiza un ``Authentication-Results`` con la gramática estricta de
    arriba. Devuelve ``None`` si hay CUALQUIER cosa fuera de ella o si el
    ``authserv-id`` no es exactamente ``mx.google.com`` (sin distinguir
    mayúsculas). Función pura: no registra nada."""
    tokens = _tokenizar(valor)
    if tokens is None:
        return None
    try:
        analisis = _Analizador(tokens).encabezado()
    except _ErrorGramatica:
        return None
    return analisis if _semantica_valida(analisis) else None


# Métodos conocidos (registro de IANA). Uno desconocido, p. ej. un "x=none"
# que absorbe la cola de un comentario roto, invalida el encabezado.
METODOS_CONOCIDOS = frozenset(
    {"dkim", "spf", "dmarc", "arc", "bimi", "iprev", "auth", "dkim-atps", "dkim-adsp",
     "sender-id", "rrvs", "vbr", "smime", "dnswl"}
)
# Valor permitido en smtp.* (mailfrom, helo), ya sin comillas ni escapes.
_VALOR_SMTP = re.compile(r"[A-Za-z0-9.=_+@-]+")


def _semantica_valida(analisis: ResultadosAutenticacion) -> bool:
    """Reglas que van después de la gramática. Existen por un caso concreto:
    Gmail copia el MAIL FROM dentro del comentario del SPF, y dentro de un
    comentario las comillas no protegen. Una parte local como
    ``"a) ; dkim=pass header.d=banco; x=none (z"`` cierra el comentario antes
    de tiempo y lo que sigue se lee como resultados. Esas colas siempre dejan
    alguna huella que estas reglas detectan:

    - todo método es conocido (``x=none`` no lo es);
    - todo valor ``smtp.*`` solo lleva ``[A-Za-z0-9.=_+@-]`` (sin ``(``, ``)``,
      comillas, ``\\``, ``;`` ni espacios);
    - todo ``spf`` lleva ``smtp.mailfrom`` o ``smtp.helo`` (el ``spf`` cuyo
      comentario se cortó queda sin ellos);
    - hay como máximo un ``dmarc``, con un solo ``header.from``.
    """
    dmarcs = 0
    for resultado in analisis.resultados:
        if resultado.metodo not in METODOS_CONOCIDOS:
            return False
        for propiedad in resultado.propiedades:
            if propiedad.tipo == "smtp" and not _VALOR_SMTP.fullmatch(propiedad.valor):
                return False
        nombres = [(p.tipo, p.nombre) for p in resultado.propiedades]
        if resultado.metodo == "spf" and not (
            ("smtp", "mailfrom") in nombres or ("smtp", "helo") in nombres
        ):
            return False
        if resultado.metodo == "dmarc":
            dmarcs += 1
            if nombres.count(("header", "from")) > 1:
                return False
    return dmarcs <= 1


# Única propiedad (ptype, nombre) que decide la autenticación (D15): el
# header.from de dmarc=pass. DKIM y SPF por sí solos ya no bastan; sus
# resultados se admiten en el encabezado (y se validan con la gramática
# estricta), pero no deciden nada. Si el banco pasa DKIM o SPF alineado, Gmail
# ya informa dmarc=pass. El ptype cuenta: policy.header.from NO es header.from.
_PROPIEDAD_DMARC_ALINEADA = ("header", "from")

# Categorías genéricas de rechazo para el log (nunca llevan valores).
MOTIVO_REMITENTE = "remitente"
MOTIVO_ENCABEZADO_INVALIDO = "encabezado_invalido"
MOTIVO_SIN_PASS_ALINEADO = "sin_pass_alineado"


def remitente_valido(correo: CorreoGmail, remitente_oficial: str) -> bool:
    """``True`` si From tiene exactamente una dirección y es la oficial
    (sin distinguir mayúsculas)."""
    return bool(correo.remitente) and correo.remitente.casefold() == remitente_oficial.strip().casefold()


def remitente_reconocido(correo: CorreoGmail, remitentes: str | Sequence[str]) -> str | None:
    """La dirección oficial de ``remitentes`` que coincide exactamente con el
    From del correo (sin distinguir mayúsculas), o ``None`` si ninguna. Con
    ella se comprueba después la autenticación: el DMARC debe estar alineado
    con el dominio de la dirección que coincidió, no con el de la otra."""
    for remitente in como_remitentes(remitentes):
        if remitente_valido(correo, remitente):
            return remitente.strip()
    return None


def _dominio(valor: str) -> str:
    """Dominio de un valor como ``@dominio``, ``usuario@dominio`` o ``dominio``:
    el texto después de la ÚLTIMA ``@`` del valor completo."""
    return valor.rpartition("@")[2].strip().strip(".").lower()


def dominio_alineado(dominio: str, dominio_oficial: str) -> bool:
    """Alineación relajada, como en DMARC: el mismo dominio, o uno es
    subdominio del otro (termina en "." + el otro).

    Se exige que ambos tengan al menos dos etiquetas: un dominio de primer
    nivel suelto ("com") nunca está alineado.
    """
    dominio = dominio.strip(".").lower()
    dominio_oficial = dominio_oficial.strip(".").lower()
    if "." not in dominio or "." not in dominio_oficial:
        return False
    return (
        dominio == dominio_oficial
        or dominio.endswith("." + dominio_oficial)
        or dominio_oficial.endswith("." + dominio)
    )


def motivo_autenticacion_invalida(correo: CorreoGmail, remitente_oficial: str) -> str | None:
    """``None`` si la autenticación es válida (ver ``autenticacion_valida``);
    si no, la categoría genérica del rechazo: ``encabezado_invalido`` (falta,
    no es de mx.google.com o se sale de la gramática) o ``sin_pass_alineado``."""
    analisis = analizar_authentication_results(correo.autenticacion)
    if analisis is None:
        return MOTIVO_ENCABEZADO_INVALIDO
    dominio_oficial = _dominio(remitente_oficial)
    # D15: DMARC es obligatorio. El analizador garantiza como máximo un dmarc
    # con un solo header.from; aquí se exige que exista, que sea "pass" y que
    # su header.from esté alineado. dkim y spf no cuentan: sin dmarc, o con un
    # dmarc que no pasa, el correo se rechaza aunque haya un dkim=pass alineado.
    dmarc = [r for r in analisis.resultados if r.metodo == "dmarc"]
    if len(dmarc) != 1 or dmarc[0].resultado != "pass":
        return MOTIVO_SIN_PASS_ALINEADO
    if any(
        (p.tipo, p.nombre) == _PROPIEDAD_DMARC_ALINEADA and p.dominio is not None
        and dominio_alineado(p.dominio, dominio_oficial)
        for p in dmarc[0].propiedades
    ):
        return None
    return MOTIVO_SIN_PASS_ALINEADO


def autenticacion_valida(correo: CorreoGmail, remitente_oficial: str) -> bool:
    """``True`` si el primer ``Authentication-Results`` cumple la gramática
    estricta (``analizar_authentication_results``), es de ``mx.google.com`` y
    su autenticación del From es válida con el dominio del remitente oficial:

    DMARC es obligatorio (D15): debe haber exactamente un resultado ``dmarc``,
    en ``pass`` y con ``header.from`` alineado. Sin ``dmarc``, o con un
    ``dmarc`` que no pasa, el correo se rechaza aunque haya un ``dkim=pass``
    o un ``spf=pass`` alineados: DKIM y SPF se admiten en el encabezado, pero
    por sí solos ya no bastan.

    Las comillas ya no se rechazan en bloque: Gmail escribe entre comillas
    el MAIL FROM real del banco (su parte local lleva "="); el analizador
    las interpreta y toma el dominio tras la "@" que cierra la parte local.
    """
    return motivo_autenticacion_invalida(correo, remitente_oficial) is None
