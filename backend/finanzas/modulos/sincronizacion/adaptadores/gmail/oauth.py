"""Credenciales OAuth: solo lectura, PKCE y escritura atómica del token."""
from __future__ import annotations
import hmac
import json
import logging
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from finanzas.modulos.sincronizacion.contratos import ALCANCES, ErrorGmail, ErrorAutorizacionGmail

logger = logging.getLogger(__name__)

_MENSAJE_REVOCADO = (
    "Gmail rechazó la autorización: el token caducó o se revocó. "
    "Vuelve a ejecutar 'python -m finanzas.gmail autorizar' y copia el token nuevo al servidor."
)


# --- Token OAuth --------------------------------------------------------------

def guardar_token(credenciales: Any, ruta_token: str | os.PathLike[str]) -> None:
    """Guarda el token con permisos 0600, de forma atómica.

    Escribe primero un archivo temporal en la misma carpeta (``mkstemp`` lo
    crea con 0600) y luego lo mueve con ``os.replace``. Así nunca queda un
    token a medio escribir ni, ni por un instante, legible por otros usuarios.
    """
    destino = Path(ruta_token)
    carpeta = destino.parent if str(destino.parent) else Path(".")
    descriptor, temporal = tempfile.mkstemp(dir=carpeta, prefix=".token-", suffix=".tmp")
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            archivo.write(credenciales.to_json())
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, destino)
    except BaseException:
        try:
            os.unlink(temporal)
        except FileNotFoundError:
            pass
        raise
    os.chmod(destino, 0o600)


def _alcances_son_solo_lectura(alcances: Any) -> bool:
    """``True`` si ``alcances`` (lista o texto separado por espacios) es exactamente ``ALCANCES``."""
    if isinstance(alcances, str):
        alcances = alcances.split()
    if not isinstance(alcances, (list, tuple, set, frozenset)):
        return False
    return set(alcances) == set(ALCANCES)


def cargar_credenciales(ruta_token: str | os.PathLike[str]) -> Any:
    """Carga el token de ``ruta_token`` y lo refresca si caducó.

    Si se refresca, se guarda de nuevo (0600, escritura atómica). Lanza
    ``ErrorAutorizacionGmail`` si falta, no sirve, se revocó o tiene permisos
    distintos de ``ALCANCES``. Los mensajes nunca incluyen el contenido del token.
    """
    from google.auth.exceptions import RefreshError, TransportError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    ruta = Path(ruta_token)
    if not ruta.is_file():
        raise ErrorAutorizacionGmail(
            f"No se encontró el token de Gmail en {ruta} (variable GMAIL_TOKEN). "
            "Genéralo con 'python -m finanzas.gmail autorizar' y cópialo al servidor."
        )
    invalido = ErrorAutorizacionGmail(
        f"El token de Gmail en {ruta} no es válido. "
        "Vuelve a generarlo con 'python -m finanzas.gmail autorizar'."
    )
    try:
        with ruta.open(encoding="utf-8") as archivo:
            info = json.load(archivo)
    except (OSError, ValueError):
        raise invalido from None
    if not isinstance(info, dict):
        raise invalido

    # Regla del dueño: solo gmail.readonly. Un token autorizado con otros
    # alcances (p. ej. uno que permita borrar) se rechaza.
    alcances = info.get("scopes")
    if alcances is not None and not _alcances_son_solo_lectura(alcances):
        raise ErrorAutorizacionGmail(
            "El token de Gmail tiene permisos distintos de gmail.readonly. "
            "Revoca el acceso y vuelve a autorizar con 'python -m finanzas.gmail autorizar'."
        )

    try:
        credenciales = Credentials.from_authorized_user_file(str(ruta), ALCANCES)
    except (ValueError, KeyError, TypeError):
        raise invalido from None

    if credenciales.valid:
        return credenciales
    if not (credenciales.expired and credenciales.refresh_token):
        raise invalido
    try:
        credenciales.refresh(Request())
    except RefreshError:
        raise ErrorAutorizacionGmail(_MENSAJE_REVOCADO) from None
    except TransportError:
        raise ErrorGmail("No se pudo conectar con Google para renovar el token de Gmail.") from None
    try:
        guardar_token(credenciales, ruta)
    except OSError as error:
        # El token renovado sirve en memoria para esta ejecución; el refresh
        # token del archivo sigue siendo válido, así que la próxima vez se
        # renovará de nuevo. No se registra la ruta ni el contenido.
        logger.warning(
            "No se pudo guardar el token de Gmail renovado (%s); se usa en memoria. "
            "Revisa que el archivo y su carpeta pertenezcan al usuario de la app.",
            type(error).__name__,
        )
    return credenciales


# --- Comando: python -m finanzas.gmail autorizar ---------------------------------

def autorizar(ruta_credenciales: str, ruta_token: str) -> None:
    """Abre el navegador para autorizar ``gmail.readonly`` y guarda el token (0600)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flujo = InstalledAppFlow.from_client_secrets_file(ruta_credenciales, ALCANCES)
    credenciales = flujo.run_local_server(port=0)
    guardar_token(credenciales, ruta_token)


# Modo sin navegador (--sin-navegador). Google redirige a esta dirección tras
# aceptar. Se usa el puerto 1 a propósito: nada escucha ahí, así que el
# navegador muestra "no se puede acceder" y la persona copia la dirección de la
# barra, que trae el código de autorización. Los clientes "App de escritorio"
# aceptan cualquier puerto de localhost sin registrarlo.
REDIRECCION_SIN_NAVEGADOR = "http://localhost:1"
_HOSTS_LOCALES = ("localhost", "127.0.0.1")
_PUERTO_SIN_NAVEGADOR = 1
INTENTOS_DE_PEGADO = 3

_INSTRUCCIONES_SIN_NAVEGADOR = """\
Autorización de Gmail (solo lectura), sin navegador en este equipo.

  1. Abre este enlace en cualquier navegador (mejor en una ventana privada):

{url}

  2. Elige tu cuenta de Gmail y acepta. Verás la advertencia "Google no
     verificó esta app"; es la que ya conoces (la app es tuya). Pulsa
     "Configuración avanzada" -> "Ir a ... (no seguro)" y acepta el permiso
     de solo lectura.
  3. El navegador irá a una página que empieza por http://localhost:1/ y
     mostrará un error ("ERR_UNSAFE_PORT", "No se puede acceder a este sitio"
     o "Esta dirección está restringida"). Es normal. Copia la dirección
     completa de la barra, que empieza por http://localhost:1/ (si el
     navegador no muestra el "http://", copia igual lo que haya).
  4. Pégala aquí y pulsa Enter.
"""


# Marcas de "bracketed paste": algunas terminales (p. ej. Cloud Shell) las
# envuelven alrededor de lo pegado y pueden llegar a ``input()``. También se
# quitan en su forma visible (``^[``) por si se copiaron como texto.
_MARCAS_DE_PEGADO = ("\x1b[200~", "\x1b[201~", "^[[200~", "^[[201~")


class _DireccionInvalida(Exception):
    """La dirección pegada no sirve. El mensaje nunca incluye la dirección ni el código."""


def extraer_codigo(pegado: str, estado_esperado: str) -> str:
    """Valida la dirección pegada y devuelve el código de autorización.

    Es estricta a propósito: solo acepta ``http://localhost:1/`` (o
    ``127.0.0.1``) con exactamente un ``code`` y un ``state`` igual al
    esperado. El ``state`` impide canjear un código que no salió de este
    intento. Lanza ``_DireccionInvalida`` con un mensaje que no repite nada de
    lo pegado.
    """
    texto = pegado
    for marca in _MARCAS_DE_PEGADO:
        texto = texto.replace(marca, "")
    texto = texto.strip().strip("\"'").strip()
    if not texto:
        raise _DireccionInvalida("No pegaste nada.")
    # Chrome puede ocultar el "http://" en la barra: si falta el esquema, se
    # asume http. El resto de la validación (host local y puerto 1) no cambia;
    # "https://..." sigue rechazándose porque ya trae esquema.
    if "://" not in texto:
        texto = "http://" + texto
    try:
        partes = urlsplit(texto)
        puerto = partes.port
    except ValueError:
        raise _DireccionInvalida("Lo pegado no es una dirección válida.") from None
    if (
        partes.scheme != "http"
        or partes.hostname not in _HOSTS_LOCALES
        or puerto != _PUERTO_SIN_NAVEGADOR
        or partes.username is not None
        or partes.password is not None
        or partes.path not in ("", "/")
        or partes.fragment
    ):
        raise _DireccionInvalida(
            "La dirección debe empezar por http://localhost:1/ . Copia la de la barra "
            "del navegador después de aceptar, completa."
        )
    parametros = parse_qs(partes.query, keep_blank_values=True)
    if "error" in parametros:
        if parametros["error"] == ["access_denied"]:
            raise _DireccionInvalida(
                "No se concedió el permiso (access_denied). Abre de nuevo el enlace y "
                "pulsa \"Continuar\"/\"Permitir\"."
            )
        raise _DireccionInvalida("Google devolvió un error en lugar de un código de autorización.")
    codigos = parametros.get("code", [])
    if len(codigos) != 1 or not codigos[0]:
        raise _DireccionInvalida(
            "La dirección no trae un único código de autorización. Copia la dirección completa."
        )
    estados = parametros.get("state", [])
    if len(estados) != 1 or not hmac.compare_digest(
        estados[0].encode("utf-8"), estado_esperado.encode("utf-8")
    ):
        raise _DireccionInvalida(
            "La dirección no corresponde a este intento. Usa el enlace que se acaba de mostrar."
        )
    alcances = parametros.get("scope")
    if alcances is not None and (len(alcances) != 1 or not _alcances_son_solo_lectura(alcances[0])):
        raise _DireccionInvalida(
            "Google concedió permisos distintos de gmail.readonly. Revoca el acceso y "
            "vuelve a autorizar marcando solo el permiso de lectura."
        )
    return codigos[0]


def _pedir_codigo(estado_esperado: str) -> str:
    """Pide la dirección hasta ``INTENTOS_DE_PEGADO`` veces y devuelve el código."""
    for intento in range(1, INTENTOS_DE_PEGADO + 1):
        try:
            pegado = input("Dirección: ")
        except EOFError:
            raise ErrorAutorizacionGmail("Se canceló la autorización. No se guardó nada.") from None
        try:
            return extraer_codigo(pegado, estado_esperado)
        except _DireccionInvalida as error:
            print(f"Intento {intento} de {INTENTOS_DE_PEGADO}: {error}", file=sys.stderr)
    raise ErrorAutorizacionGmail(
        f"Demasiados intentos ({INTENTOS_DE_PEGADO}). No se guardó nada. "
        "Vuelve a ejecutar el comando."
    )


def _verificar_credenciales_nuevas(credenciales: Any) -> None:
    """Exige ``refresh_token`` y exactamente ``ALCANCES`` (pedidos y concedidos)."""
    if not getattr(credenciales, "refresh_token", None):
        raise ErrorAutorizacionGmail(
            "Google no entregó un refresh token, así que el acceso caducaría en una hora. "
            "No se guardó nada. Revoca el acceso de la app en tu cuenta de Google y vuelve a autorizar."
        )
    alcances = getattr(credenciales, "scopes", None)
    concedidos = getattr(credenciales, "granted_scopes", None)
    if not _alcances_son_solo_lectura(alcances) or (
        concedidos is not None and not _alcances_son_solo_lectura(concedidos)
    ):
        raise ErrorAutorizacionGmail(
            "Google concedió permisos distintos de gmail.readonly. No se guardó nada. "
            "Revoca el acceso y vuelve a autorizar marcando solo el permiso de lectura."
        )


def autorizar_sin_navegador(ruta_credenciales: str, ruta_token: str) -> None:
    """Autoriza ``gmail.readonly`` sin abrir un navegador en este equipo.

    Pensado para ejecutarse en el servidor: muestra un enlace, la persona lo
    abre en cualquier navegador y pega la dirección ``http://localhost:1/...``
    a la que la redirige Google. Solo si todo es válido guarda el token (0600,
    escritura atómica). Nunca imprime el token, el código ni el secreto del
    cliente. Lanza ``ErrorAutorizacionGmail`` con un mensaje claro si algo falla.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    carpeta = Path(ruta_token).parent
    if not carpeta.is_dir():
        raise ErrorAutorizacionGmail(f"No existe la carpeta del token: {carpeta}.")

    try:
        # PKCE: se pide explícitamente, aunque la librería ya lo activa por
        # defecto, para no depender de ese valor. El code_verifier solo vive en
        # memoria: sin él, un código copiado por otra persona no sirve.
        flujo = InstalledAppFlow.from_client_secrets_file(
            ruta_credenciales,
            ALCANCES,
            redirect_uri=REDIRECCION_SIN_NAVEGADOR,
            autogenerate_code_verifier=True,
        )
    except (OSError, ValueError, KeyError, TypeError):
        raise ErrorAutorizacionGmail(
            f"El archivo de credenciales {ruta_credenciales} no es un cliente OAuth válido. "
            "Debe ser el JSON de un cliente de tipo 'App de escritorio'."
        ) from None
    if getattr(flujo, "client_type", "installed") != "installed":
        raise ErrorAutorizacionGmail(
            "El cliente OAuth no es de tipo 'App de escritorio'. Crea uno de ese tipo en Google Cloud."
        )
    # Sin esto, un secreto olvidado al copiar la plantilla solo fallaría al
    # canjear el código, con un error confuso. Nunca se muestra su valor.
    configuracion = getattr(flujo, "client_config", None)
    if isinstance(configuracion, Mapping):
        for campo, que in (("client_id", "el ID de cliente"), ("client_secret", "el secreto")):
            valor = configuracion.get(campo)
            if not isinstance(valor, str) or not valor.strip():
                raise ErrorAutorizacionGmail(
                    f"El JSON del cliente no trae {campo}: revisa que copiaste {que}."
                )

    # prompt=consent: Google entrega siempre un refresh_token, aunque ya se
    # hubiera autorizado antes.
    url, estado = flujo.authorization_url(access_type="offline", prompt="consent")
    print(_INSTRUCCIONES_SIN_NAVEGADOR.format(url=url))
    codigo = _pedir_codigo(estado)

    # Se canjea con code= y no con authorization_response=: oauthlib rechaza
    # direcciones http:// salvo con OAUTHLIB_INSECURE_TRANSPORT, que no se activa.
    try:
        flujo.fetch_token(code=codigo)
    except Warning:
        # oauthlib avisa así cuando Google concede permisos distintos de los pedidos.
        raise ErrorAutorizacionGmail(
            "Google concedió permisos distintos de gmail.readonly. No se guardó nada. "
            "Vuelve a autorizar y acepta el permiso de solo lectura."
        ) from None
    except Exception:
        raise ErrorAutorizacionGmail(
            "Google no aceptó el código (quizá caducó o ya se usó). No se guardó nada. "
            "Vuelve a ejecutar el comando y pega la dirección enseguida."
        ) from None
    credenciales = flujo.credentials
    _verificar_credenciales_nuevas(credenciales)
    try:
        guardar_token(credenciales, ruta_token)
    except OSError as error:
        raise ErrorAutorizacionGmail(
            f"No se pudo guardar el token en {ruta_token} ({type(error).__name__}). "
            "Revisa que la carpeta pertenezca al usuario que ejecuta el comando."
        ) from None
