"""Pruebas de ``python -m finanzas.gmail autorizar --sin-navegador``.

Sin red: se reemplaza ``InstalledAppFlow`` por un doble. Una prueba usa la
librería real solo para generar la URL (eso no sale a internet) y comprobar
que lleva PKCE, ``access_type=offline``, ``prompt=consent`` y la redirección a
``localhost:1``. Todos los datos son inventados.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from finanzas import gmail
from finanzas.gmail import ALCANCES

ESTADO = "estado-inventado-123"
CODIGO = "4/0codigo-de-autorizacion-inventado"
TOKEN = "ya29.token-de-acceso-inventado-sin-navegador"
REFRESH = "1//refresh-inventado-sin-navegador"
SECRETO = "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"
CLIENT_ID = "cliente-inventado.apps.googleusercontent.com"
URL_AUTORIZACION = "https://accounts.google.com/o/oauth2/auth?client_id=" + CLIENT_ID


def _url(**params) -> str:
    base = {"state": ESTADO, "code": CODIGO, "scope": " ".join(ALCANCES)}
    base.update(params)
    base = {k: v for k, v in base.items() if v is not None}
    return "http://localhost:1/?" + urlencode(base)


class _Credenciales:
    def __init__(self, refresh_token=REFRESH, scopes=None, granted_scopes=None):
        self.token = TOKEN
        self.refresh_token = refresh_token
        self.scopes = list(ALCANCES) if scopes is None else scopes
        self.granted_scopes = granted_scopes

    def to_json(self):
        return json.dumps({
            "token": self.token,
            "refresh_token": self.refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": CLIENT_ID,
            "client_secret": SECRETO,
            "scopes": self.scopes,
        })


class _Flujo:
    """Doble de ``InstalledAppFlow``: registra las llamadas."""

    llamadas: dict
    credenciales_a_devolver = None
    error_al_canjear = None

    def __init__(self):
        self.client_type = "installed"
        self.client_config = {"client_id": CLIENT_ID, "client_secret": SECRETO}
        self.credentials = None

    @classmethod
    def from_client_secrets_file(cls, ruta, scopes, **kwargs):
        cls.llamadas["crear"] = {"ruta": ruta, "scopes": scopes, **kwargs}
        return cls()

    def authorization_url(self, **kwargs):
        self.llamadas["authorization_url"] = kwargs
        return URL_AUTORIZACION, ESTADO

    def fetch_token(self, **kwargs):
        self.llamadas["fetch_token"] = kwargs
        if self.error_al_canjear is not None:
            raise self.error_al_canjear
        self.credentials = self.credenciales_a_devolver or _Credenciales()
        return {"access_token": TOKEN}

    def run_local_server(self, port):
        self.llamadas["run_local_server"] = port
        return _Credenciales()


@pytest.fixture
def flujo(monkeypatch):
    import google_auth_oauthlib.flow as flujo_mod

    class Flujo(_Flujo):
        llamadas = {}

    monkeypatch.setattr(flujo_mod, "InstalledAppFlow", Flujo)
    return Flujo


@pytest.fixture
def rutas(tmp_path):
    cliente = tmp_path / "client_secret.json"
    cliente.write_text(json.dumps({"installed": {"client_id": CLIENT_ID, "client_secret": SECRETO}}), encoding="utf-8")
    return cliente, tmp_path / "token.json"


def _pegar(monkeypatch, *respuestas):
    pendientes = list(respuestas)

    def falso_input(prompt=""):
        if not pendientes:
            raise AssertionError("se pidió más entrada de la esperada")
        return pendientes.pop(0)

    monkeypatch.setattr("builtins.input", falso_input)
    return pendientes


def _ejecutar(rutas, *extra):
    cliente, token = rutas
    return gmail.main([
        "autorizar", "--sin-navegador", "--credenciales", str(cliente), "--token", str(token), *extra,
    ])


def _sin_secretos(texto: str) -> None:
    for secreto in (CODIGO, TOKEN, REFRESH, SECRETO):
        assert secreto not in texto, secreto


# --- Camino feliz ------------------------------------------------------------------

def test_camino_feliz_guarda_token_0600_sin_imprimir_secretos(flujo, rutas, monkeypatch, capsys):
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas) == 0

    _, token = rutas
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    guardado = json.loads(token.read_text(encoding="utf-8"))
    assert guardado["refresh_token"] == REFRESH
    # El token lleva lo necesario para renovarse sin el JSON del cliente.
    assert guardado["client_id"] == CLIENT_ID and guardado["client_secret"] == SECRETO

    salida = capsys.readouterr()
    assert URL_AUTORIZACION in salida.out  # el enlace sí se muestra
    assert f"Token guardado en {token}" in salida.out
    assert "http://localhost:1/" in salida.out
    _sin_secretos(salida.out + salida.err)


def test_usa_localhost_1_offline_consent_y_pkce(flujo, rutas, monkeypatch):
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas) == 0
    crear = flujo.llamadas["crear"]
    assert crear["scopes"] == ALCANCES
    assert crear["redirect_uri"] == "http://localhost:1"
    assert crear["autogenerate_code_verifier"] is True
    assert flujo.llamadas["authorization_url"] == {"access_type": "offline", "prompt": "consent"}


def test_canjea_con_code_y_no_con_authorization_response(flujo, rutas, monkeypatch):
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas) == 0
    assert flujo.llamadas["fetch_token"] == {"code": CODIGO}
    assert "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ


@pytest.mark.parametrize("pegado", [
    f'  "{_url()}"  ',
    f"'{_url()}'\n",
    f"\t{_url()}  ",
    _url().replace("localhost", "127.0.0.1"),
    _url(scope=None),  # Google puede no devolver scope en la dirección
    _url().removeprefix("http://"),  # Chrome puede ocultar el esquema en la barra
    _url().replace("http://localhost", "127.0.0.1"),
    f"\x1b[200~{_url()}\x1b[201~",  # marcas de "bracketed paste" (Cloud Shell)
    f"  \x1b[200~ '{_url()}' \x1b[201~\n",
    f"^[[200~{_url()}^[[201~",
], ids=["comillas dobles", "comillas simples", "tabulador", "127.0.0.1", "sin scope",
        "sin esquema", "sin esquema 127.0.0.1", "bracketed paste", "paste con comillas",
        "paste visible"])
def test_acepta_comillas_espacios_y_127_0_0_1(flujo, rutas, monkeypatch, pegado):
    _pegar(monkeypatch, pegado)
    assert _ejecutar(rutas) == 0
    assert flujo.llamadas["fetch_token"] == {"code": CODIGO}
    assert rutas[1].exists()


def test_la_libreria_real_genera_pkce_y_la_url_esperada(tmp_path):
    """Con google-auth-oauthlib real (sin red): PKCE S256, offline, consent y localhost:1."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    cliente = tmp_path / "client_secret.json"
    cliente.write_text(json.dumps({"installed": {
        "client_id": CLIENT_ID,
        "client_secret": SECRETO,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }}), encoding="utf-8")
    flujo = InstalledAppFlow.from_client_secrets_file(
        str(cliente), ALCANCES, redirect_uri=gmail.REDIRECCION_SIN_NAVEGADOR,
        autogenerate_code_verifier=True,
    )
    url, estado = flujo.authorization_url(access_type="offline", prompt="consent")
    params = parse_qs(urlsplit(url).query)
    assert params["redirect_uri"] == ["http://localhost:1"]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"][0]
    assert params["scope"] == [" ".join(ALCANCES)]
    assert params["state"] == [estado]
    assert flujo.code_verifier and len(flujo.code_verifier) >= 43
    assert SECRETO not in url
    # Y el extractor acepta la redirección que Google haría con ese estado.
    assert gmail.extraer_codigo(f"http://localhost:1/?state={estado}&code=abc", estado) == "abc"


# --- Direcciones inválidas: nunca se guarda nada ------------------------------------

INVALIDAS = {
    "state distinto": _url(state="otro-estado"),
    "sin state": _url(state=None),
    "sin code": _url(code=None),
    "code vacío": _url(code=""),
    "code duplicado": _url() + "&code=otro-codigo",
    "state duplicado": _url() + "&state=" + ESTADO,
    "otro host": _url().replace("localhost", "evil.com"),
    "usuario@host": _url().replace("localhost:1", "localhost:1@evil.com"),
    "https": _url().replace("http://", "https://"),
    "otro puerto": _url().replace(":1/", ":8080/"),
    "sin puerto": _url().replace(":1/", "/"),
    "puerto inválido": _url().replace(":1/", ":abc/"),
    "otra ruta": _url().replace(":1/", ":1/otra"),
    "access_denied": f"http://localhost:1/?error=access_denied&state={ESTADO}",
    "otro error": f"http://localhost:1/?error=server_error&state={ESTADO}&code={CODIGO}",
    "scope de más": _url(scope=" ".join(ALCANCES + ["https://www.googleapis.com/auth/gmail.modify"])),
    "sin esquema, otro host": _url().replace("http://localhost", "evil.com"),
    "sin esquema, otro puerto": _url().replace("http://localhost:1", "localhost:8080"),
    "sin esquema ni puerto": _url().replace("http://localhost:1", "localhost"),
    "sin esquema, usuario@host": _url().replace("http://localhost:1", "localhost:1@evil.com"),
    "paste con https": f"\x1b[200~{_url().replace('http://', 'https://')}\x1b[201~",
    "solo marcas de pegado": "\x1b[200~\x1b[201~",
    "basura": "esto no es una dirección",
    "vacío": "   ",
}


@pytest.mark.parametrize("pegado", list(INVALIDAS.values()), ids=list(INVALIDAS))
def test_direccion_invalida_no_canjea_ni_guarda(flujo, rutas, monkeypatch, capsys, pegado):
    _pegar(monkeypatch, *([pegado] * gmail.INTENTOS_DE_PEGADO))
    assert _ejecutar(rutas) == 1
    assert "fetch_token" not in flujo.llamadas
    assert not rutas[1].exists()
    assert rutas[0].exists()
    salida = capsys.readouterr()
    assert "No se guardó nada" in salida.err
    # Los mensajes de error no repiten lo pegado ni el código.
    assert CODIGO not in salida.err
    if pegado.strip():
        assert pegado.strip() not in salida.err


def test_access_denied_da_un_mensaje_claro():
    with pytest.raises(gmail._DireccionInvalida, match="access_denied"):
        gmail.extraer_codigo("http://localhost:1/?error=access_denied", ESTADO)


def test_tres_intentos_fallidos_abortan(flujo, rutas, monkeypatch, capsys):
    pendientes = _pegar(monkeypatch, "basura", _url(state="x"), "http://evil.com:1/", _url())
    assert _ejecutar(rutas) == 1
    assert pendientes == [_url()]  # el cuarto no se llega a pedir
    assert not rutas[1].exists()
    err = capsys.readouterr().err
    assert "Intento 3 de 3" in err and "Demasiados intentos" in err


def test_acierta_al_tercer_intento(flujo, rutas, monkeypatch):
    _pegar(monkeypatch, "basura", _url(state="x"), _url())
    assert _ejecutar(rutas) == 0
    assert rutas[1].exists()


def test_fin_de_entrada_cancela_sin_guardar(flujo, rutas, monkeypatch, capsys):
    def sin_entrada(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", sin_entrada)
    assert _ejecutar(rutas) == 1
    assert not rutas[1].exists()
    assert "cancel" in capsys.readouterr().err


# --- Credenciales obtenidas -------------------------------------------------------

@pytest.mark.parametrize("credenciales", [
    _Credenciales(refresh_token=None),
    _Credenciales(refresh_token=""),
    _Credenciales(scopes=ALCANCES + ["https://www.googleapis.com/auth/gmail.modify"]),
    _Credenciales(scopes=[]),
    _Credenciales(granted_scopes=ALCANCES + ["https://mail.google.com/"]),
    _Credenciales(granted_scopes=[]),
], ids=["sin refresh", "refresh vacío", "scopes de más", "sin scopes", "concedidos de más", "concedidos vacíos"])
def test_credenciales_no_validas_no_se_guardan(flujo, rutas, monkeypatch, capsys, credenciales):
    flujo.credenciales_a_devolver = credenciales
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas, "--borrar-credenciales") == 1
    assert not rutas[1].exists()
    assert rutas[0].exists()  # tampoco se borra el cliente
    salida = capsys.readouterr()
    assert "No se guardó nada" in salida.err
    _sin_secretos(salida.out + salida.err)


def test_concedidos_iguales_como_texto_se_aceptan(flujo, rutas, monkeypatch):
    flujo.credenciales_a_devolver = _Credenciales(granted_scopes=" ".join(ALCANCES))
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas) == 0


@pytest.mark.parametrize("error", [Warning("Scope has changed"), ValueError("invalid_grant " + CODIGO)])
def test_fallo_al_canjear_no_guarda_ni_muestra_el_codigo(flujo, rutas, monkeypatch, capsys, error):
    flujo.error_al_canjear = error
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas, "--borrar-credenciales") == 1
    assert not rutas[1].exists()
    assert rutas[0].exists()
    salida = capsys.readouterr()
    _sin_secretos(salida.out + salida.err)


def test_cliente_que_no_es_de_escritorio_se_rechaza(flujo, rutas, monkeypatch, capsys):
    original = flujo.from_client_secrets_file.__func__

    def crear_web(cls, ruta, scopes, **kwargs):
        instancia = original(cls, ruta, scopes, **kwargs)
        instancia.client_type = "web"
        return instancia

    monkeypatch.setattr(flujo, "from_client_secrets_file", classmethod(crear_web))
    _pegar(monkeypatch)
    assert _ejecutar(rutas) == 1
    assert "App de escritorio" in capsys.readouterr().err
    assert not rutas[1].exists()


def test_json_de_cliente_invalido_da_mensaje_claro(rutas, monkeypatch, capsys):
    # Librería real: el archivo no es un cliente OAuth.
    rutas[0].write_text('{"otro": {"client_secret": "' + SECRETO + '"}}', encoding="utf-8")
    _pegar(monkeypatch)
    assert _ejecutar(rutas) == 1
    salida = capsys.readouterr()
    assert "App de escritorio" in salida.err
    _sin_secretos(salida.out + salida.err)


def test_carpeta_del_token_inexistente_falla_antes_de_pedir_nada(flujo, rutas, monkeypatch, tmp_path):
    _pegar(monkeypatch)
    codigo = gmail.main([
        "autorizar", "--sin-navegador", "--credenciales", str(rutas[0]),
        "--token", str(tmp_path / "no-existe" / "token.json"),
    ])
    assert codigo == 1
    assert "crear" not in flujo.llamadas


# --- --borrar-credenciales ----------------------------------------------------------

def test_borrar_credenciales_tras_exito(flujo, rutas, monkeypatch, capsys):
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas, "--borrar-credenciales") == 0
    assert not rutas[0].exists()
    assert rutas[1].exists()
    assert "Se borró" in capsys.readouterr().out


def test_borrar_credenciales_no_borra_si_falla(flujo, rutas, monkeypatch):
    _pegar(monkeypatch, *(["basura"] * gmail.INTENTOS_DE_PEGADO))
    assert _ejecutar(rutas, "--borrar-credenciales") == 1
    assert rutas[0].exists()


def test_sin_borrar_credenciales_el_archivo_se_queda(flujo, rutas, monkeypatch):
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas) == 0
    assert rutas[0].exists()


def test_borrar_credenciales_en_el_modo_con_navegador(flujo, rutas):
    cliente, token = rutas
    codigo = gmail.main([
        "autorizar", "--credenciales", str(cliente), "--token", str(token), "--borrar-credenciales",
    ])
    assert codigo == 0
    assert not cliente.exists() and token.exists()


# --- Modo por defecto y parser --------------------------------------------------------

def test_sin_la_opcion_sigue_usando_run_local_server(flujo, rutas, monkeypatch):
    _pegar(monkeypatch)  # no debe pedir nada
    cliente, token = rutas
    assert gmail.main(["autorizar", "--credenciales", str(cliente), "--token", str(token)]) == 0
    assert flujo.llamadas["run_local_server"] == 0
    assert flujo.llamadas["crear"] == {"ruta": str(cliente), "scopes": ALCANCES}
    assert "authorization_url" not in flujo.llamadas
    assert cliente.exists()


def test_el_parser_acepta_las_opciones_nuevas(capsys):
    with pytest.raises(SystemExit) as salida:
        gmail.main(["autorizar", "--help"])
    assert salida.value.code == 0
    ayuda = capsys.readouterr().out
    assert "--sin-navegador" in ayuda
    assert "--borrar-credenciales" in ayuda


def test_alcances_siguen_siendo_solo_lectura():
    assert ALCANCES == ["https://www.googleapis.com/auth/gmail.readonly"]


def test_funciona_sin_variables_de_entorno_de_la_app(flujo, rutas, monkeypatch):
    for nombre in list(os.environ):
        if nombre.startswith(("GMAIL_", "DB_", "SECRET", "APP_", "PASSWORD", "USUARIO")):
            monkeypatch.delenv(nombre, raising=False)
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas) == 0


def test_token_generado_lo_carga_cargar_credenciales(flujo, rutas, monkeypatch):
    """El token que se guarda es aceptado por la app (mismo formato y alcances)."""
    from google.oauth2.credentials import Credentials

    class _Reales(_Credenciales):
        def to_json(self):
            return Credentials(
                TOKEN, refresh_token=REFRESH, token_uri="https://oauth2.googleapis.com/token",
                client_id=CLIENT_ID, client_secret=SECRETO, scopes=ALCANCES,
                expiry=(datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None),
            ).to_json()

    flujo.credenciales_a_devolver = _Reales()
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas, "--borrar-credenciales") == 0
    credenciales = gmail.cargar_credenciales(Path(rutas[1]))
    assert credenciales.valid
    assert credenciales.client_secret == SECRETO and credenciales.refresh_token == REFRESH


@pytest.mark.parametrize("campo", ["client_secret", "client_id"])
@pytest.mark.parametrize("valor", [None, "", "   "], ids=["falta", "vacío", "espacios"])
def test_json_sin_client_secret_o_client_id_da_mensaje_claro(flujo, rutas, monkeypatch, capsys, campo, valor):
    original = flujo.from_client_secrets_file.__func__

    def crear(cls, ruta, scopes, **kwargs):
        instancia = original(cls, ruta, scopes, **kwargs)
        if valor is None:
            del instancia.client_config[campo]
        else:
            instancia.client_config[campo] = valor
        return instancia

    monkeypatch.setattr(flujo, "from_client_secrets_file", classmethod(crear))
    _pegar(monkeypatch)  # no llega a pedir la dirección
    assert _ejecutar(rutas, "--borrar-credenciales") == 1
    salida = capsys.readouterr()
    assert f"El JSON del cliente no trae {campo}: revisa que copiaste" in salida.err
    assert "authorization_url" not in flujo.llamadas
    assert not rutas[1].exists() and rutas[0].exists()
    _sin_secretos(salida.out + salida.err)


def test_json_real_sin_client_secret_da_mensaje_claro(rutas, monkeypatch, capsys):
    """Con la librería real: la plantilla sin secreto no llega a un KeyError."""
    rutas[0].write_text(json.dumps({"installed": {
        "client_id": CLIENT_ID,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }}), encoding="utf-8")
    _pegar(monkeypatch)
    assert _ejecutar(rutas) == 1
    salida = capsys.readouterr()
    assert "El JSON del cliente no trae client_secret: revisa que copiaste el secreto" in salida.err
    assert "Traceback" not in salida.err


def test_instrucciones_explican_el_error_del_puerto_1(flujo, rutas, monkeypatch, capsys):
    _pegar(monkeypatch, _url())
    assert _ejecutar(rutas) == 0
    salida = capsys.readouterr().out
    assert "ERR_UNSAFE_PORT" in salida
    assert "restringida" in salida
    assert "http://localhost:1/" in salida


def test_ctrl_c_en_modo_con_navegador_sale_con_130(flujo, rutas, monkeypatch, capsys):
    def interrumpir(self, port):
        raise KeyboardInterrupt

    monkeypatch.setattr(flujo, "run_local_server", interrumpir)
    cliente, token = rutas
    codigo = gmail.main([
        "autorizar", "--credenciales", str(cliente), "--token", str(token), "--borrar-credenciales",
    ])
    assert codigo == 130
    assert "Se canceló la autorización. No se guardó nada." in capsys.readouterr().err
    assert cliente.exists() and not token.exists()
