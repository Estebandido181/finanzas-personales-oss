"""Decodificación MIME/HTML sin red, archivos ni persistencia."""
from __future__ import annotations
import base64
import binascii
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from email.message import Message
from email.utils import getaddresses
from html.parser import HTMLParser
from typing import Any
from finanzas.compartido.hora import ZONA_COLOMBIA
from finanzas.modulos.sincronizacion.contratos import CorreoGmail

# --- Cuerpo del correo -------------------------------------------------------

def decodificar_base64url(datos: str) -> bytes:
    """Decodifica el base64url de la API de Gmail (con o sin relleno ``=``)."""
    limpio = "".join(datos.split())
    try:
        return base64.urlsafe_b64decode(limpio + "=" * (-len(limpio) % 4))
    except (binascii.Error, ValueError) as error:
        raise ValueError("El cuerpo del correo no es base64url válido.") from error


# Etiquetas que separan bloques: se convierten en saltos de línea.
_ETIQUETAS_BLOQUE = frozenset(
    {"p", "div", "br", "td", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
     "table", "tbody", "thead", "tfoot", "ul", "ol", "hr", "th"}
)
# Etiquetas cuyo contenido no es texto visible.
_ETIQUETAS_OCULTAS = frozenset({"script", "style", "head", "title", "template"})
# Espacios del código fuente HTML (no incluye el espacio duro &nbsp;).
_ESPACIOS_HTML = re.compile(r"[ \t\r\n\f]+")


class _ConversorHtml(HTMLParser):
    """Convierte HTML en texto: los bloques pasan a saltos de línea y se
    descarta lo que no se ve (``style``, ``script``, ``head``...)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._partes: list[str] = []
        self._oculto = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _ETIQUETAS_OCULTAS:
            self._oculto += 1
        elif tag in _ETIQUETAS_BLOQUE:
            self._partes.append("\n")

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        # <br/>, <hr/>: no abren nada, solo cortan la línea.
        if tag in _ETIQUETAS_BLOQUE:
            self._partes.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _ETIQUETAS_OCULTAS:
            self._oculto = max(0, self._oculto - 1)
        elif tag in _ETIQUETAS_BLOQUE:
            self._partes.append("\n")

    def handle_data(self, data: str) -> None:
        # En HTML, los saltos de línea del código fuente son espacios: solo
        # las etiquetas de bloque cortan líneas.
        if not self._oculto:
            self._partes.append(_ESPACIOS_HTML.sub(" ", data))

    def texto(self) -> str:
        return "".join(self._partes)


def _ordenar_lineas(texto: str) -> str:
    """Limpia espacios de cada línea y deja como máximo una línea vacía seguida.

    Las líneas vacías separan bloques (párrafos, celdas); la sincronización
    las usa para aislar el aviso.
    """
    lineas: list[str] = []
    for linea in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        limpia = " ".join(linea.split())
        if limpia or (lineas and lineas[-1]):
            lineas.append(limpia)
    return "\n".join(lineas).strip("\n")


def html_a_texto(html: str) -> str:
    """Convierte HTML en texto plano con ``html.parser`` de la librería estándar."""
    conversor = _ConversorHtml()
    conversor.feed(html)
    conversor.close()
    return _ordenar_lineas(conversor.texto())


def _encabezado(parte: Mapping[str, Any], nombre: str) -> str:
    for encabezado in parte.get("headers") or ():
        if str(encabezado.get("name", "")).lower() == nombre.lower():
            return str(encabezado.get("value", ""))
    return ""


def _charset(parte: Mapping[str, Any]) -> str | None:
    """Charset declarado en ``Content-Type``; ``None`` si no hay."""
    mensaje = Message()
    mensaje["Content-Type"] = _encabezado(parte, "Content-Type") or "text/plain"
    return mensaje.get_content_charset()


def _decodificar_parte(parte: Mapping[str, Any]) -> str:
    """Decodifica una parte de texto.

    Con charset declarado y conocido, se usa ese. Sin charset (o con uno
    desconocido) se prueba UTF-8 estricto y, si falla, latin-1 como respaldo:
    así "CAFÉ" en latin-1 no sale como "CAF\ufffd".
    """
    datos = (parte.get("body") or {}).get("data")
    if not datos:
        return ""
    crudo = decodificar_base64url(datos)
    charset = _charset(parte)
    if charset:
        try:
            return crudo.decode(charset, errors="replace")
        except LookupError:  # charset desconocido: se trata como no declarado
            pass
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return crudo.decode("latin-1")  # nunca falla: cada byte es un carácter


def _es_adjunto(parte: Mapping[str, Any]) -> bool:
    return bool(parte.get("filename")) or bool((parte.get("body") or {}).get("attachmentId"))


def _buscar_partes(parte: Mapping[str, Any], encontradas: dict[str, str]) -> None:
    """Recorre las partes (``multipart/*`` anidadas) y guarda la primera
    ``text/plain`` y la primera ``text/html`` que no sean adjuntos."""
    tipo = str(parte.get("mimeType", "")).lower()
    if tipo.startswith("multipart/"):
        for hija in parte.get("parts") or ():
            _buscar_partes(hija, encontradas)
        return
    if tipo in ("text/plain", "text/html") and tipo not in encontradas and not _es_adjunto(parte):
        contenido = _decodificar_parte(parte)
        if contenido.strip():
            encontradas[tipo] = contenido


def textos_del_cuerpo(payload: Mapping[str, Any]) -> list[str]:
    """Versiones en texto plano del cuerpo, en orden de preferencia.

    Primero la parte ``text/plain`` y después la ``text/html`` convertida a
    texto. Solo se incluyen las que existen; lista vacía si no hay ninguna.
    """
    encontradas: dict[str, str] = {}
    _buscar_partes(payload, encontradas)
    textos: list[str] = []
    if "text/plain" in encontradas:
        textos.append(_ordenar_lineas(encontradas["text/plain"]))
    if "text/html" in encontradas:
        textos.append(html_a_texto(encontradas["text/html"]))
    return textos


def texto_del_cuerpo(payload: Mapping[str, Any]) -> str:
    """Cuerpo del correo en texto plano.

    Usa la parte ``text/plain`` si existe; si no, la ``text/html`` convertida
    a texto. Devuelve ``""`` si no hay ninguna.
    """
    textos = textos_del_cuerpo(payload)
    return textos[0] if textos else ""


def _encabezados(parte: Mapping[str, Any], nombre: str) -> list[str]:
    """Todos los valores de un encabezado, en el orden del mensaje (de arriba abajo)."""
    return [
        str(encabezado.get("value", ""))
        for encabezado in parte.get("headers") or ()
        if str(encabezado.get("name", "")).lower() == nombre.lower()
    ]


def direccion_remitente(valores_from: Sequence[str]) -> str:
    """La única dirección de los encabezados ``From``; ``""`` si no hay
    exactamente una dirección válida.

    Se analizan todos los ``From`` juntos: dos encabezados o dos direcciones
    en uno cuentan como dos y se rechazan. El nombre visible se ignora
    ("Bancolombia <x@evil.com>" da ``x@evil.com``).
    """
    direcciones = [direccion for _, direccion in getaddresses(list(valores_from))]
    if len(direcciones) != 1:
        return ""
    direccion = direcciones[0].strip()
    local, arroba, dominio = direccion.rpartition("@")
    if not arroba or not local or not dominio or "@" in local or any(c.isspace() for c in direccion):
        return ""
    return direccion


def correo_desde_mensaje(mensaje: Mapping[str, Any]) -> CorreoGmail:
    """Convierte la respuesta de ``messages.get(format="full")`` en ``CorreoGmail``."""
    payload = mensaje.get("payload") or {}
    milisegundos = int(mensaje["internalDate"])
    textos = textos_del_cuerpo(payload)
    resultados_autenticacion = _encabezados(payload, "Authentication-Results")
    return CorreoGmail(
        gmail_id=str(mensaje["id"]),
        fecha=datetime.fromtimestamp(milisegundos / 1000, tz=ZONA_COLOMBIA),
        asunto=_encabezado(payload, "Subject"),
        texto=textos[0] if textos else "",
        alternativos=tuple(textos[1:]),
        remitente=direccion_remitente(_encabezados(payload, "From")),
        autenticacion=resultados_autenticacion[0] if resultados_autenticacion else "",
    )
