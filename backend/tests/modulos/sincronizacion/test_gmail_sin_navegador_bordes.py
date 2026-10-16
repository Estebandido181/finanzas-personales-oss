"""Casos borde de ``autorizar --sin-navegador`` (``extraer_codigo`` y el flujo).

Intenta romper el extractor con direcciones pegadas raras y comprueba, en cada
caso, que no se guarda nada, que el mensaje no repite lo pegado y que no hay
trazas con el código. También prueba la plantilla JSON de ``deploy/GUIA.md``
(8.2) con la librería real ``google_auth_oauthlib`` (sin red) y simula los
pasos de esa sección en un directorio temporal.

Todos los datos son inventados.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import textwrap
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest

from finanzas import gmail
from finanzas.gmail import ALCANCES

RAIZ = Path(__file__).resolve().parents[4]
GUIA = RAIZ / "deploy" / "GUIA.md"

ESTADO = "estado-bordes-inventado-789"
CODIGO = "4/0codigo-bordes-inventado-XYZ"
TOKEN = "ya29.token-bordes-inventado"
REFRESH = "1//refresh-bordes-inventado"
SECRETO = "GOCSPX-secreto-bordes-inventado"
CLIENT_ID = "cliente-bordes-inventado.apps.googleusercontent.com"
URL_AUTORIZACION = "https://accounts.google.com/o/oauth2/auth?client_id=" + CLIENT_ID


# --- Dobles --------------------------------------------------------------------------

class _Credenciales:
    def __init__(self):
        self.token = TOKEN
        self.refresh_token = REFRESH
        self.scopes = list(ALCANCES)
        self.granted_scopes = None

    def to_json(self):
        return json.dumps({
            "token": TOKEN,
            "refresh_token": REFRESH,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": CLIENT_ID,
            "client_secret": SECRETO,
            "scopes": list(ALCANCES),
            "expiry": "2999-01-01T00:00:00Z",
        })


class _Flujo:
    llamadas: dict
    estado = ESTADO
    error_al_canjear: BaseException | None = None

    def __init__(self):
        self.client_type = "installed"
        self.credentials = None

    @classmethod
    def from_client_secrets_file(cls, ruta, scopes, **kwargs):
        cls.llamadas["crear"] = {"ruta": ruta, "scopes": scopes, **kwargs}
        return cls()

    def authorization_url(self, **kwargs):
        return URL_AUTORIZACION, self.estado

    def fetch_token(self, **kwargs):
        self.llamadas["fetch_token"] = kwargs
        if self.error_al_canjear is not None:
            raise self.error_al_canjear
        self.credentials = _Credenciales()
        return {"access_token": TOKEN}


@pytest.fixture
def flujo(monkeypatch):
    import google_auth_oauthlib.flow as flujo_mod

    class Flujo(_Flujo):
        llamadas = {}

    monkeypatch.setattr(flujo_mod, "InstalledAppFlow", Flujo)
    return Flujo


@pytest.fixture
def rutas(tmp_path):
    carpeta = tmp_path / "gmail"
    carpeta.mkdir()
    cliente = carpeta / "client_secret.json"
    cliente.write_text(json.dumps({"installed": {"client_id": CLIENT_ID, "client_secret": SECRETO}}),
                       encoding="utf-8")
    return cliente, carpeta / "token.json"


def _pegar(monkeypatch, *respuestas):
    pendientes = list(respuestas)

    def falso_input(prompt=""):
        if not pendientes:
            raise EOFError
        valor = pendientes.pop(0)
        if isinstance(valor, BaseException):
            raise valor
        return valor

    monkeypatch.setattr("builtins.input", falso_input)


def _ejecutar(rutas, *extra):
    cliente, token = rutas
    return gmail.main([
        "autorizar", "--sin-navegador", "--credenciales", str(cliente), "--token", str(token), *extra,
    ])


def _archivos(carpeta: Path) -> set[str]:
    return {p.name for p in carpeta.iterdir()}


def _url(estado=ESTADO, codigo=CODIGO, host="localhost:1") -> str:
    return f"http://{host}/?" + urlencode({"state": estado, "code": codigo})


# --- extraer_codigo: aceptadas (normalizaciones inofensivas) -------------------------

@pytest.mark.parametrize("pegado", [
    f"http://LOCALHOST:1/?state={ESTADO}&code={CODIGO}",
    f"http://localhost:01/?state={ESTADO}&code={CODIGO}",
    f"http://127.0.0.1:1/?state={ESTADO}&code={CODIGO}",
    f"HTTP://localhost:1/?state={ESTADO}&code={CODIGO}",
    f"http://localhost:1?state={ESTADO}&code={CODIGO}",
])
def test_variantes_equivalentes_de_localhost_1_se_aceptan(pegado):
    assert gmail.extraer_codigo(pegado, ESTADO) == CODIGO


def test_codigo_doblemente_codificado_se_decodifica_una_sola_vez():
    # %2526 -> "%26" tras una decodificación; no se vuelve a decodificar a "&".
    pegado = f"http://localhost:1/?state={ESTADO}&code=4/0abc%2526def"
    assert gmail.extraer_codigo(pegado, ESTADO) == "4/0abc%26def"


def test_state_unicode_se_compara_bien():
    estado = "estado-ñandú-€-漢字-🔑"
    pegado = "http://localhost:1/?" + urlencode({"state": estado, "code": CODIGO})
    assert gmail.extraer_codigo(pegado, estado) == CODIGO
    # Unicode sin codificar, tal como lo mostraría la barra de algunos navegadores.
    assert gmail.extraer_codigo(f"http://localhost:1/?state={estado}&code={CODIGO}", estado) == CODIGO


def test_state_unicode_parecido_se_rechaza():
    # "n" + tilde combinante no es "ñ" precompuesta: no hay normalización.
    pegado = "http://localhost:1/?" + urlencode({"state": "estado-ñandu", "code": CODIGO})
    with pytest.raises(gmail._DireccionInvalida):
        gmail.extraer_codigo(pegado, "estado-ñandu")


def test_espacios_en_el_codigo_no_rompen_el_extractor():
    # Un espacio o "+" en el código llega tal cual a Google, que lo rechazará.
    assert gmail.extraer_codigo(f"http://localhost:1/?state={ESTADO}&code=4/0a+b", ESTADO) == "4/0a b"
    assert gmail.extraer_codigo(f"http://localhost:1/?state={ESTADO}&code=4/0a b", ESTADO) == "4/0a b"


def test_url_de_1_mb_valida_se_procesa():
    relleno = "x" * (1024 * 1024)
    pegado = f"http://localhost:1/?state={ESTADO}&code={CODIGO}&relleno={relleno}"
    assert gmail.extraer_codigo(pegado, ESTADO) == CODIGO


# --- extraer_codigo: rechazadas, sin repetir lo pegado --------------------------------

RECHAZADAS = {
    "code duplicado a/b": f"http://localhost:1/?code=a{CODIGO}&state={ESTADO}&code=b{CODIGO}",
    "code vacío": f"http://localhost:1/?state={ESTADO}&code=",
    "sin query": "http://localhost:1/",
    "ipv6 ::1": f"http://[::1]:1/?state={ESTADO}&code={CODIGO}",
    "ipv6 sin cerrar": f"http://[::1:1/?state={ESTADO}&code={CODIGO}",
    "usuario@evil": f"http://localhost:1@evil.com/?state={ESTADO}&code={CODIGO}",
    "fragmento@localhost": f"http://evil.com#@localhost:1/?state={ESTADO}&code={CODIGO}",
    "code en el fragmento": f"http://localhost:1/#state={ESTADO}&code={CODIGO}",
    "puerto fuera de rango": f"http://localhost:65536/?state={ESTADO}&code={CODIGO}",
    "puerto 10": f"http://localhost:10/?state={ESTADO}&code={CODIGO}",
    "localhost.evil.com": f"http://localhost.evil.com:1/?state={ESTADO}&code={CODIGO}",
    "0.0.0.0": f"http://0.0.0.0:1/?state={ESTADO}&code={CODIGO}",
    "127.1": f"http://127.1:1/?state={ESTADO}&code={CODIGO}",
    "solo el código": CODIGO,
    "code=... sin url": f"code={CODIGO}&state={ESTADO}",
    "url de autorización de Google": (
        "https://accounts.google.com/o/oauth2/auth?response_type=code&client_id="
        + CLIENT_ID + "&redirect_uri=http%3A%2F%2Flocalhost%3A1&state=" + ESTADO
        + "&code_challenge=abc&code_challenge_method=S256"
    ),
    "state unicode distinto": f"http://localhost:1/?state={ESTADO}é&code={CODIGO}",
    "state con doble codificación": f"http://localhost:1/?state={quote(quote(ESTADO + '&'))}&code={CODIGO}",
    "1 MB de basura": "a" * (1024 * 1024) + CODIGO,
    "1 MB de url a otro host": f"http://evil.com:1/?state={ESTADO}&code={CODIGO}&r=" + "x" * (1024 * 1024),
}


@pytest.mark.parametrize("pegado", RECHAZADAS.values(), ids=RECHAZADAS.keys())
def test_direcciones_raras_se_rechazan_sin_repetir_la_entrada(pegado):
    with pytest.raises(gmail._DireccionInvalida) as info:
        gmail.extraer_codigo(pegado, ESTADO)
    mensaje = str(info.value)
    assert CODIGO not in mensaje
    assert ESTADO not in mensaje
    assert "evil" not in mensaje
    assert len(mensaje) < 300
    # Sin encadenar la excepción original (que podría llevar la entrada).
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ or info.value.__context__ is None


@pytest.mark.parametrize("pegado", RECHAZADAS.values(), ids=RECHAZADAS.keys())
def test_direcciones_raras_en_el_flujo_no_guardan_ni_imprimen(flujo, rutas, monkeypatch, capsys, pegado):
    cliente, token = rutas
    antes = _archivos(token.parent)
    _pegar(monkeypatch, pegado, pegado, pegado)
    assert _ejecutar(rutas, "--borrar-credenciales") == 1
    salida = capsys.readouterr()
    texto = salida.out + salida.err
    assert "fetch_token" not in flujo.llamadas
    assert _archivos(token.parent) == antes
    assert cliente.exists()
    assert CODIGO not in texto
    assert "evil" not in texto
    assert "Traceback" not in texto
    assert "Demasiados intentos" in salida.err


def test_saltos_de_linea_en_medio_los_ignora_urlsplit():
    # urlsplit elimina \n, \r y \t (WHATWG). Con input() no pueden llegar porque
    # lee una sola línea; se documenta el comportamiento si se llama directo.
    pegado = f"http://local\nhost:1/?sta\rte={ESTADO}&co\tde={CODIGO}"
    assert gmail.extraer_codigo(pegado, ESTADO) == CODIGO


def test_url_partida_en_dos_lineas_no_guarda_nada(flujo, rutas, monkeypatch, capsys):
    # Si la terminal parte lo pegado en dos líneas, input() recibe dos trozos.
    url = _url()
    mitad = len(url) // 2
    _pegar(monkeypatch, url[:mitad], url[mitad:], "")
    assert _ejecutar(rutas) == 1
    salida = capsys.readouterr()
    assert CODIGO not in salida.out + salida.err
    assert not rutas[1].exists()


# --- EOF y Ctrl+C ------------------------------------------------------------------------

def test_eof_en_input_cancela_sin_guardar_ni_traza(flujo, rutas, monkeypatch, capsys):
    cliente, token = rutas
    antes = _archivos(token.parent)
    _pegar(monkeypatch, EOFError())
    assert _ejecutar(rutas, "--borrar-credenciales") == 1
    salida = capsys.readouterr()
    assert "No se guardó nada" in salida.err
    assert "Traceback" not in salida.out + salida.err
    assert _archivos(token.parent) == antes


def test_eof_tras_un_intento_fallido_no_repite_la_entrada(flujo, rutas, monkeypatch, capsys):
    pegado = f"http://evil.com:1/?state={ESTADO}&code={CODIGO}"
    _pegar(monkeypatch, pegado, EOFError())
    assert _ejecutar(rutas) == 1
    salida = capsys.readouterr()
    assert CODIGO not in salida.out + salida.err
    assert not rutas[1].exists()


def test_ctrl_c_en_input_no_deja_archivos(flujo, rutas, monkeypatch, capsys):
    cliente, token = rutas
    antes = _archivos(token.parent)
    _pegar(monkeypatch, KeyboardInterrupt())
    assert _ejecutar(rutas, "--borrar-credenciales") == 130
    assert "Se canceló la autorización. No se guardó nada." in capsys.readouterr().err
    assert _archivos(token.parent) == antes
    assert cliente.exists()


def test_ctrl_c_al_canjear_no_deja_archivos(flujo, rutas, monkeypatch, capsys):
    cliente, token = rutas
    antes = _archivos(token.parent)
    flujo.error_al_canjear = KeyboardInterrupt()
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas, "--borrar-credenciales") == 130
    assert "Se canceló la autorización. No se guardó nada." in capsys.readouterr().err
    assert _archivos(token.parent) == antes
    assert cliente.exists()


def test_ctrl_c_al_escribir_el_token_borra_el_temporal(flujo, rutas, monkeypatch, capsys):
    cliente, token = rutas
    antes = _archivos(token.parent)

    def fsync_interrumpido(fd):
        raise KeyboardInterrupt

    monkeypatch.setattr(gmail.os, "fsync", fsync_interrumpido)
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas, "--borrar-credenciales") == 130
    assert "Se canceló la autorización. No se guardó nada." in capsys.readouterr().err
    assert _archivos(token.parent) == antes
    assert cliente.exists()


_GUION_CTRL_C = textwrap.dedent("""
    import builtins, runpy, sys
    import google_auth_oauthlib.flow as flujo_mod

    class Flujo:
        client_type = "installed"
        @classmethod
        def from_client_secrets_file(cls, *a, **k):
            return cls()
        def authorization_url(self, **k):
            return "https://accounts.google.com/o/oauth2/auth?x=1", "estado-sub"
        def fetch_token(self, **k):
            raise KeyboardInterrupt

    flujo_mod.InstalledAppFlow = Flujo
    MODO = sys.argv[1]

    def falso_input(prompt=""):
        if MODO == "input":
            raise KeyboardInterrupt
        return "http://localhost:1/?state=estado-sub&code=4/0codigo-subproceso-inventado"

    builtins.input = falso_input
    sys.argv = ["finanzas.gmail", "autorizar", "--sin-navegador",
                "--credenciales", sys.argv[2], "--token", sys.argv[3], "--borrar-credenciales"]
    runpy.run_module("finanzas.gmail", run_name="__main__", alter_sys=True)
""")


def _ctrl_c_en_subproceso(tmp_path, modo):
    guion = tmp_path / "guion.py"
    guion.write_text(_GUION_CTRL_C, encoding="utf-8")
    carpeta = tmp_path / "gmail"
    carpeta.mkdir()
    cliente = carpeta / "client_secret.json"
    cliente.write_text("{}", encoding="utf-8")
    token = carpeta / "token.json"
    resultado = subprocess.run(
        [sys.executable, str(guion), modo, str(cliente), str(token)],
        capture_output=True, text=True, cwd=RAIZ, timeout=60,
        env={**os.environ, "PYTHONPATH": str(RAIZ / "backend")},
    )
    return resultado, carpeta


@pytest.mark.parametrize("modo", ["input", "canje"])
def test_ctrl_c_real_no_deja_archivos_ni_muestra_el_codigo(tmp_path, modo):
    resultado, carpeta = _ctrl_c_en_subproceso(tmp_path, modo)
    assert resultado.returncode != 0
    assert _archivos(carpeta) == {"client_secret.json"}
    assert "codigo-subproceso-inventado" not in resultado.stdout + resultado.stderr


@pytest.mark.parametrize("modo", ["input", "canje"])
def test_ctrl_c_real_sale_limpio_sin_traza(tmp_path, modo):
    resultado, _ = _ctrl_c_en_subproceso(tmp_path, modo)
    assert "Traceback" not in resultado.stderr, resultado.stderr[-500:]
    assert resultado.returncode == 130
    assert "Se canceló la autorización. No se guardó nada." in resultado.stderr


# --- Plantilla JSON de la guía 8.2 con la librería real (sin red) --------------------------

def _plantilla_de_la_guia() -> str:
    texto = GUIA.read_text(encoding="utf-8")
    inicio = texto.index("### 8.2")
    fin = texto.index("\n## 9.", inicio)
    bloques = re.findall(r"```json\n(.*?)```", texto[inicio:fin], flags=re.S)
    assert len(bloques) == 1, "la sección 8.2 debería tener una sola plantilla JSON"
    return bloques[0]


def _plantilla_rellena() -> str:
    plantilla = _plantilla_de_la_guia()
    assert "TU_ID_DE_CLIENTE" in plantilla and "TU_SECRETO_DE_CLIENTE" in plantilla
    return plantilla.replace("TU_ID_DE_CLIENTE", CLIENT_ID).replace("TU_SECRETO_DE_CLIENTE", SECRETO)


def test_plantilla_de_la_guia_es_json_valido_tipo_instalado():
    datos = json.loads(_plantilla_rellena())
    assert set(datos) == {"installed"}
    instalado = datos["installed"]
    assert instalado["client_id"] == CLIENT_ID
    assert instalado["client_secret"] == SECRETO
    assert instalado["token_uri"] == "https://oauth2.googleapis.com/token"


def test_plantilla_de_la_guia_con_la_libreria_real_genera_pkce_s256(tmp_path):
    from google_auth_oauthlib.flow import InstalledAppFlow

    cliente = tmp_path / "client_secret.json"
    cliente.write_text(_plantilla_rellena(), encoding="utf-8")
    flujo = InstalledAppFlow.from_client_secrets_file(
        str(cliente), ALCANCES, redirect_uri=gmail.REDIRECCION_SIN_NAVEGADOR,
        autogenerate_code_verifier=True,
    )
    assert flujo.client_type == "installed"
    url, estado = flujo.authorization_url(access_type="offline", prompt="consent")
    partes = urlsplit(url)
    assert partes.scheme == "https" and partes.hostname == "accounts.google.com"
    params = parse_qs(partes.query)
    assert params["client_id"] == [CLIENT_ID]
    assert params["redirect_uri"] == ["http://localhost:1"]
    assert params["code_challenge_method"] == ["S256"]
    assert len(params["code_challenge"][0]) >= 43
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["scope"] == [" ".join(ALCANCES)]
    assert SECRETO not in url
    # Pegar la URL de autorización en vez de la de redirección se rechaza.
    with pytest.raises(gmail._DireccionInvalida):
        gmail.extraer_codigo(url, estado)


def test_plantilla_de_la_guia_con_autorizar_sin_navegador_real_hasta_el_canje(tmp_path, monkeypatch, capsys):
    """Usa el flujo real hasta ``fetch_token``, que se sustituye para no salir a la red."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    cliente = tmp_path / "client_secret.json"
    cliente.write_text(_plantilla_rellena(), encoding="utf-8")
    token = tmp_path / "token.json"
    visto = {}

    def fetch_token_falso(self, **kwargs):
        visto["kwargs"] = kwargs
        visto["verifier"] = self.code_verifier
        raise ConnectionError("sin red en pruebas")

    monkeypatch.setattr(InstalledAppFlow, "fetch_token", fetch_token_falso)

    def input_con_estado_real(prompt=""):
        salida = capsys.readouterr().out
        url = re.search(r"https://accounts\.google\.com/\S+", salida).group(0)
        estado = parse_qs(urlsplit(url).query)["state"][0]
        return f"http://localhost:1/?state={estado}&code={CODIGO}&scope={quote(' '.join(ALCANCES))}"

    monkeypatch.setattr("builtins.input", input_con_estado_real)
    assert gmail.main(["autorizar", "--sin-navegador", "--credenciales", str(cliente),
                       "--token", str(token), "--borrar-credenciales"]) == 1
    assert visto["kwargs"] == {"code": CODIGO}
    assert visto["verifier"] and len(visto["verifier"]) >= 43
    assert not token.exists()
    assert cliente.exists()
    err = capsys.readouterr().err
    assert CODIGO not in err and SECRETO not in err


# --- Simulación de los pasos de la guía 8.2 ---------------------------------------------

def test_simulacion_de_la_guia_8_2(tmp_path, flujo, monkeypatch, capsys):
    carpeta = tmp_path / "var-lib-finanzas-gmail"
    carpeta.mkdir(mode=0o700)
    cliente = carpeta / "client_secret.json"
    token = carpeta / "token.json"

    # Paso 2: "install -m 0600 /dev/null ..." y luego pegar la plantilla (nano/tee).
    fd = os.open(cliente, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    os.chmod(cliente, 0o600)
    with open(cliente, "w", encoding="utf-8") as archivo:  # tee reescribe sin cambiar permisos
        archivo.write(_plantilla_rellena())
    assert stat.S_IMODE(cliente.stat().st_mode) == 0o600

    # Paso 3 y 4: autorizar --sin-navegador --borrar-credenciales, pegando la redirección.
    _pegar(monkeypatch, "  " + _url() + "&scope=" + quote(" ".join(ALCANCES)) + "  ")
    codigo_salida = gmail.main([
        "autorizar", "--sin-navegador", "--credenciales", str(cliente),
        "--token", str(token), "--borrar-credenciales",
    ])
    salida = capsys.readouterr()
    assert codigo_salida == 0, salida.err
    assert flujo.llamadas["crear"]["ruta"] == str(cliente)
    assert flujo.llamadas["fetch_token"] == {"code": CODIGO}
    assert f"Token guardado en {token} con permisos 0600." in salida.out
    assert "Se borró el archivo de credenciales" in salida.out
    for secreto in (CODIGO, TOKEN, REFRESH, SECRETO):
        assert secreto not in salida.out + salida.err

    # Paso 5: token 0600; el JSON del cliente ya no existe y no quedan temporales.
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    assert not cliente.exists()
    assert _archivos(carpeta) == {"token.json"}

    # La app acepta el token (válido hasta 2999, así que no intenta renovar por red).
    credenciales = gmail.cargar_credenciales(token)
    assert credenciales.valid
    assert credenciales.refresh_token == REFRESH
    assert credenciales.client_id == CLIENT_ID
    assert set(credenciales.scopes) == set(ALCANCES)
