"""Pruebas de finanzas.gmail, sin red: respuestas simuladas de la API de Gmail."""

from __future__ import annotations

import base64
import json
import os
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from finanzas import gmail
from finanzas.modulos.sincronizacion.adaptadores.gmail import oauth
from finanzas.gmail import (
    ALCANCES,
    REMITENTE_AYN,
    REMITENTE_POR_DEFECTO,
    REMITENTES_OFICIALES,
    ClienteGmailReal,
    ErrorAutorizacionGmail,
    cargar_credenciales,
    correo_desde_mensaje,
    decodificar_base64url,
    guardar_token,
    html_a_texto,
    texto_del_cuerpo,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "gmail"


def _mensaje(nombre: str) -> dict:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


def _b64(texto: str, charset: str = "utf-8") -> str:
    return base64.urlsafe_b64encode(texto.encode(charset)).decode().rstrip("=")


# --- Alcances ------------------------------------------------------------------

def test_alcances_es_exactamente_gmail_readonly():
    assert ALCANCES == ["https://www.googleapis.com/auth/gmail.readonly"]


def test_ningun_otro_alcance_de_google_en_el_codigo():
    # Regla del dueño: solo gmail.readonly. Ningún archivo del paquete menciona otro.
    raiz = Path(gmail.__file__).parent
    for archivo in raiz.rglob("*.py"):
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if "googleapis.com/auth/" in linea:
                assert "googleapis.com/auth/gmail.readonly" in linea, archivo


def test_remitente_por_defecto():
    assert REMITENTE_POR_DEFECTO == "alertasynotificaciones@an.notificacionesbancolombia.com"


# --- base64url -----------------------------------------------------------------

@pytest.mark.parametrize("texto", ["a", "ab", "abc", "abcd", "¿Dudas? ñandú ~~~ ???", ""])
def test_decodifica_base64url_con_y_sin_relleno(texto):
    codificado = base64.urlsafe_b64encode(texto.encode()).decode()
    assert decodificar_base64url(codificado) == texto.encode()
    assert decodificar_base64url(codificado.rstrip("=")) == texto.encode()


def test_base64url_usa_guion_y_guion_bajo():
    datos = bytes([0xFB, 0xFF, 0xBF])  # en base64 normal: "+/+/"
    codificado = base64.urlsafe_b64encode(datos).decode()
    assert "-" in codificado or "_" in codificado
    assert decodificar_base64url(codificado) == datos


def test_base64url_invalido_lanza_value_error():
    with pytest.raises(ValueError):
        decodificar_base64url("a")


# --- Texto del cuerpo ----------------------------------------------------------

def test_html_bloques_a_saltos_de_linea():
    html = (
        "<html><head><style>p {color: red}</style><title>t</title></head><body>"
        "<h1>Título</h1><div>uno<br>dos</div><p>tres <b>negrita</b></p>"
        "<table><tr><td>celda1</td><td>celda2</td></tr></table>"
        "<ul><li>item</li></ul><script>var x = 1;</script></body></html>"
    )
    lineas = [l for l in html_a_texto(html).splitlines() if l]
    assert lineas == ["Título", "uno", "dos", "tres negrita", "celda1", "celda2", "item"]


def test_html_entidades_y_espacios():
    texto = html_a_texto("<p>&iexcl;Listo!&nbsp;Todo   sali&oacute;\n bien</p>")
    assert texto == "¡Listo! Todo salió bien"


def test_html_separa_bloques_con_linea_vacia():
    assert html_a_texto("<p>uno</p><p>dos</p>") == "uno\n\ndos"


def test_texto_plano_simple():
    payload = {
        "mimeType": "text/plain",
        "headers": [{"name": "Content-Type", "value": "text/plain; charset=utf-8"}],
        "body": {"data": _b64("Hola\r\n  mundo  \r\n\r\n\r\nfin")},
    }
    assert texto_del_cuerpo(payload) == "Hola\nmundo\n\nfin"


def test_multipart_prefiere_text_plain():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>desde html</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("desde texto")}},
        ],
    }
    assert texto_del_cuerpo(payload) == "desde texto"


def test_multipart_sin_text_plain_usa_html():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [{"mimeType": "text/html", "body": {"data": _b64("<p>solo html</p>")}}],
    }
    assert texto_del_cuerpo(payload) == "solo html"


def test_partes_anidadas_y_adjuntos_ignorados():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "filename": "adjunto.txt",
             "body": {"attachmentId": "x", "data": _b64("adjunto")}},
            {"mimeType": "multipart/related", "parts": [
                {"mimeType": "multipart/alternative", "parts": [
                    {"mimeType": "text/html", "body": {"data": _b64("<div>anidado</div>")}},
                ]},
            ]},
        ],
    }
    assert texto_del_cuerpo(payload) == "anidado"


def test_charset_latin1():
    payload = {
        "mimeType": "text/plain",
        "headers": [{"name": "Content-Type", "value": "text/plain; charset=ISO-8859-1"}],
        "body": {"data": _b64("salió", "latin-1")},
    }
    assert texto_del_cuerpo(payload) == "salió"


@pytest.mark.parametrize("encabezados", [[], [{"name": "Content-Type", "value": "text/plain"}]])
def test_sin_charset_y_no_utf8_usa_latin1(encabezados):
    payload = {
        "mimeType": "text/plain",
        "headers": encabezados,
        "body": {"data": _b64("Compraste en CAFÉ EJEMPLO", "latin-1")},
    }
    texto = texto_del_cuerpo(payload)
    assert texto == "Compraste en CAFÉ EJEMPLO"
    assert "\ufffd" not in texto


def test_sin_charset_y_utf8_valido_usa_utf8():
    payload = {"mimeType": "text/plain", "body": {"data": _b64("CAFÉ ÑANDÚ")}}
    assert texto_del_cuerpo(payload) == "CAFÉ ÑANDÚ"


def test_charset_desconocido_usa_utf8_o_latin1():
    payload = {
        "mimeType": "text/plain",
        "headers": [{"name": "Content-Type", "value": "text/plain; charset=x-inventado"}],
        "body": {"data": _b64("CAFÉ", "latin-1")},
    }
    assert texto_del_cuerpo(payload) == "CAFÉ"


def test_correo_con_texto_y_html_guarda_ambos_en_memoria():
    correo = correo_desde_mensaje(_mensaje("transferiste_multipart.json"))
    assert len(correo.textos) == 2
    assert correo.textos[0] == correo.texto
    assert "Bancolombia nunca te pedirá" in correo.textos[1]  # el pie solo está en el HTML
    assert "Bancolombia nunca" not in repr(correo)


def test_sin_cuerpo_devuelve_vacio():
    assert texto_del_cuerpo({"mimeType": "multipart/mixed", "parts": []}) == ""


def test_fixture_compraste_html():
    correo = correo_desde_mensaje(_mensaje("compraste_html.json"))
    assert correo.gmail_id == "msg-0001"
    assert correo.asunto == "Alerta de compra (ejemplo)"
    assert correo.fecha == datetime(2026, 8, 7, 16, 42, 30, tzinfo=gmail.ZONA_COLOMBIA)
    assert "¡Listo! Todo salió bien con tus movimientos" in correo.texto
    assert "Bancolombia: Compraste $245.700,00 en MERPAGO*TIENDAEJEMPLO" in correo.texto
    assert "Consejos de seguridad" in correo.texto
    assert "font-family" not in correo.texto  # el <style> no es texto


def test_fixture_transferiste_multipart_usa_text_plain():
    mensaje = _mensaje("transferiste_multipart.json")
    correo = correo_desde_mensaje(mensaje)
    assert correo.gmail_id == "msg-0002"
    # La parte text/plain no tiene el pie con la lista de consejos del HTML.
    assert "Bancolombia nunca te pedirá" not in correo.texto
    assert "Bancolombia: Transferiste $4,500.00 desde tu cuenta *1234" in correo.texto


def test_fixture_html_anidado_en_multipart_mixed():
    correo = correo_desde_mensaje(_mensaje("compraste_html_anidado.json"))
    assert correo.gmail_id == "msg-0004"
    assert "Bancolombia: Compraste $68.630,00 en RESTAURANTE EJEMPLO" in correo.texto
    assert "Todo salió bien" in correo.texto  # decodificado desde ISO-8859-1


def test_fecha_desde_internal_date_en_hora_de_colombia():
    mensaje = {"id": "msg-x", "internalDate": "1786752320000", "payload": {}}
    correo = correo_desde_mensaje(mensaje)
    assert correo.fecha.astimezone(timezone.utc) == datetime(2026, 8, 15, 0, 5, 20, tzinfo=timezone.utc)
    assert correo.fecha.utcoffset() == timedelta(hours=-5)
    assert (correo.fecha.date(), correo.fecha.hour) == (date(2026, 8, 14), 19)


def test_repr_del_correo_no_muestra_cuerpo_ni_asunto():
    correo = correo_desde_mensaje(_mensaje("compraste_html.json"))
    assert "MERPAGO" not in repr(correo)
    assert "Alerta de compra" not in repr(correo)
    assert "msg-0001" in repr(correo)


# --- ClienteGmailReal con un service falso -----------------------------------------

class _Peticion:
    def __init__(self, respuesta):
        self._respuesta = respuesta

    def execute(self, **_):
        if isinstance(self._respuesta, Exception):
            raise self._respuesta
        return self._respuesta


class _ServiceFalso:
    """Imita ``service.users().messages().list/get`` de googleapiclient."""

    def __init__(self, paginas=None, mensajes=None):
        self.paginas = paginas or {}
        self.mensajes = mensajes or {}
        self.llamadas_list: list[dict] = []
        self.llamadas_get: list[dict] = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kwargs):
        self.llamadas_list.append(kwargs)
        return _Peticion(self.paginas[kwargs.get("pageToken")])

    def get(self, **kwargs):
        self.llamadas_get.append(kwargs)
        return _Peticion(self.mensajes[kwargs["id"]])


def test_listar_ids_consulta_from_y_after_y_pagina():
    service = _ServiceFalso(paginas={
        None: {"messages": [{"id": "msg-0001"}, {"id": "msg-0002"}], "nextPageToken": "p2"},
        "p2": {"messages": [{"id": "msg-0003"}], "nextPageToken": "p3"},
        "p3": {"resultSizeEstimate": 0},  # última página sin mensajes
    })
    cliente = ClienteGmailReal(service, REMITENTE_POR_DEFECTO)
    ids = cliente.listar_ids(date(2026, 8, 1))

    assert ids == ["msg-0001", "msg-0002", "msg-0003"]
    assert [l.get("pageToken") for l in service.llamadas_list] == [None, "p2", "p3"]
    for llamada in service.llamadas_list:
        assert llamada["userId"] == "me"
        consulta = llamada["q"]
        assert f"from:{REMITENTE_POR_DEFECTO}" in consulta
        # after: con los segundos de la medianoche del 1/08/2026 en Colombia (UTC-5).
        medianoche = datetime(2026, 8, 1, 5, 0, tzinfo=timezone.utc)
        assert f"after:{int(medianoche.timestamp())}" in consulta


def test_listar_ids_con_remitente_configurado():
    service = _ServiceFalso(paginas={None: {}})
    assert ClienteGmailReal(service, "otro@example.com").listar_ids(date(2026, 8, 1)) == []
    assert service.llamadas_list[0]["q"].startswith("from:otro@example.com after:")


def test_listar_ids_por_defecto_consulta_los_dos_remitentes_oficiales():
    # D30: una consulta por remitente (an. y ayn.), mismos after:, ids sin repetir.
    service = _ServiceFalso(paginas={None: {"messages": [{"id": "msg-0001"}, {"id": "msg-0002"}]}})
    assert ClienteGmailReal(service).listar_ids(date(2026, 8, 1)) == ["msg-0001", "msg-0002"]
    consultas = [l["q"] for l in service.llamadas_list]
    assert [q.split()[0] for q in consultas] == [
        "from:alertasynotificaciones@an.notificacionesbancolombia.com",
        "from:alertasynotificaciones@ayn.notificacionesbancolombia.com",
    ]
    assert len({q.split()[1] for q in consultas}) == 1  # el mismo after:
    assert REMITENTES_OFICIALES == (REMITENTE_POR_DEFECTO, REMITENTE_AYN)


def test_obtener_pide_formato_full():
    service = _ServiceFalso(mensajes={"msg-0001": _mensaje("compraste_html.json")})
    correo = ClienteGmailReal(service).obtener("msg-0001")
    assert correo.gmail_id == "msg-0001"
    assert service.llamadas_get == [{"userId": "me", "id": "msg-0001", "format": "full"}]


def test_error_401_se_convierte_en_error_de_autorizacion():
    import httplib2
    from googleapiclient.errors import HttpError

    error = HttpError(httplib2.Response({"status": 401}), b"{}")
    service = _ServiceFalso(paginas={None: error}, mensajes={"msg-0001": error})
    with pytest.raises(ErrorAutorizacionGmail):
        ClienteGmailReal(service).listar_ids(date(2026, 8, 1))
    with pytest.raises(ErrorAutorizacionGmail):
        ClienteGmailReal(service).obtener("msg-0001")


def test_otros_errores_http_no_son_de_autorizacion():
    import httplib2
    from googleapiclient.errors import HttpError

    error = HttpError(httplib2.Response({"status": 500}), b"{}")
    with pytest.raises(HttpError):
        ClienteGmailReal(_ServiceFalso(mensajes={"m": error})).obtener("m")


# --- Credenciales y token --------------------------------------------------------

TOKEN_INVENTADO = "ya29.token-de-acceso-inventado-para-pruebas"
REFRESH_INVENTADO = "1//refresh-inventado-para-pruebas"


def _info_token(**cambios):
    info = {
        "token": TOKEN_INVENTADO,
        "refresh_token": REFRESH_INVENTADO,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cliente-inventado.apps.googleusercontent.com",
        "client_secret": "secreto-de-cliente-inventado",
        "scopes": list(ALCANCES),
        "expiry": (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    info.update(cambios)
    return {k: v for k, v in info.items() if v is not None}


def _escribir_token(ruta: Path, **cambios) -> Path:
    ruta.write_text(json.dumps(_info_token(**cambios)), encoding="utf-8")
    os.chmod(ruta, 0o600)
    return ruta


def _permisos(ruta: Path) -> int:
    return stat.S_IMODE(ruta.stat().st_mode)


def test_cargar_credenciales_sin_token_lanza_error_claro(tmp_path):
    ruta = tmp_path / "no-existe.json"
    with pytest.raises(ErrorAutorizacionGmail, match="GMAIL_TOKEN") as error:
        cargar_credenciales(ruta)
    assert "autorizar" in str(error.value)


@pytest.mark.parametrize("contenido", ["no es json", "[]", json.dumps({"token": TOKEN_INVENTADO})])
def test_cargar_credenciales_token_invalido_no_muestra_contenido(tmp_path, contenido):
    ruta = tmp_path / "token.json"
    ruta.write_text(contenido, encoding="utf-8")
    with pytest.raises(ErrorAutorizacionGmail) as error:
        cargar_credenciales(ruta)
    assert TOKEN_INVENTADO not in str(error.value)
    assert error.value.__cause__ is None  # no arrastra la excepción original con datos


def test_cargar_credenciales_rechaza_otros_alcances(tmp_path):
    ruta = _escribir_token(
        tmp_path / "token.json",
        scopes=ALCANCES + ["https://www.googleapis.com/auth/gmail.modify"],
    )
    with pytest.raises(ErrorAutorizacionGmail, match="gmail.readonly"):
        cargar_credenciales(ruta)


def test_cargar_credenciales_vigente_no_refresca(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials

    def no_refrescar(self, request):
        raise AssertionError("no debía refrescar")

    monkeypatch.setattr(Credentials, "refresh", no_refrescar)
    credenciales = cargar_credenciales(_escribir_token(tmp_path / "token.json"))
    assert credenciales.valid
    assert list(credenciales.scopes) == ALCANCES


def test_cargar_credenciales_refresca_y_guarda_con_0600(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials

    def refrescar(self, request):
        self.token = "ya29.token-renovado-inventado"
        self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", refrescar)
    ruta = _escribir_token(tmp_path / "token.json", expiry="2020-01-01T00:00:00Z")
    os.chmod(ruta, 0o644)  # aunque antes tuviera permisos amplios

    credenciales = cargar_credenciales(ruta)

    assert credenciales.token == "ya29.token-renovado-inventado"
    guardado = json.loads(ruta.read_text(encoding="utf-8"))
    assert guardado["token"] == "ya29.token-renovado-inventado"
    assert guardado["refresh_token"] == REFRESH_INVENTADO
    assert _permisos(ruta) == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["token.json"]  # sin temporales


def test_token_renovado_que_no_se_puede_guardar_sigue_en_memoria(tmp_path, monkeypatch, caplog):
    from google.oauth2.credentials import Credentials

    def refrescar(self, request):
        self.token = "ya29.token-renovado-inventado"
        self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    def no_se_puede(credenciales, ruta):
        raise PermissionError(13, "Permission denied", str(ruta))

    monkeypatch.setattr(Credentials, "refresh", refrescar)
    monkeypatch.setattr(oauth, "guardar_token", no_se_puede)
    ruta = _escribir_token(tmp_path / "token.json", expiry="2020-01-01T00:00:00Z")
    original = ruta.read_text(encoding="utf-8")

    with caplog.at_level("DEBUG"):
        credenciales = cargar_credenciales(ruta)

    assert credenciales.valid
    assert credenciales.token == "ya29.token-renovado-inventado"
    assert ruta.read_text(encoding="utf-8") == original
    assert "PermissionError" in caplog.text
    for dato in ("ya29.", REFRESH_INVENTADO, str(tmp_path)):
        assert dato not in caplog.text


def test_cargar_credenciales_revocado(tmp_path, monkeypatch):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    def revocado(self, request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(Credentials, "refresh", revocado)
    ruta = _escribir_token(tmp_path / "token.json", expiry="2020-01-01T00:00:00Z")
    with pytest.raises(ErrorAutorizacionGmail, match="revocó") as error:
        cargar_credenciales(ruta)
    assert REFRESH_INVENTADO not in str(error.value)


def test_guardar_token_queda_0600_y_reemplaza_atomicamente(tmp_path):
    class _Credenciales:
        def to_json(self):
            return json.dumps({"token": "nuevo"})

    ruta = tmp_path / "token.json"
    ruta.write_text("viejo", encoding="utf-8")
    os.chmod(ruta, 0o644)
    guardar_token(_Credenciales(), ruta)
    assert json.loads(ruta.read_text(encoding="utf-8")) == {"token": "nuevo"}
    assert _permisos(ruta) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["token.json"]


def test_guardar_token_si_falla_no_deja_temporales(tmp_path):
    class _Rotas:
        def to_json(self):
            raise RuntimeError("fallo inventado")

    ruta = tmp_path / "token.json"
    ruta.write_text("original", encoding="utf-8")
    with pytest.raises(RuntimeError):
        guardar_token(_Rotas(), ruta)
    assert ruta.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["token.json"]


# --- Comando autorizar --------------------------------------------------------------

def test_comando_autorizar_guarda_token_0600_sin_imprimirlo(tmp_path, monkeypatch, capsys):
    import google_auth_oauthlib.flow as flujo_mod

    llamadas = {}

    class _CredencialesFalsas:
        def to_json(self):
            return json.dumps(_info_token())

    class _FlujoFalso:
        @classmethod
        def from_client_secrets_file(cls, ruta, scopes):
            llamadas["ruta"] = ruta
            llamadas["scopes"] = scopes
            return cls()

        def run_local_server(self, port):
            llamadas["port"] = port
            return _CredencialesFalsas()

    monkeypatch.setattr(flujo_mod, "InstalledAppFlow", _FlujoFalso)
    cliente_json = tmp_path / "client_secret_inventado.json"
    cliente_json.write_text("{}", encoding="utf-8")
    token = tmp_path / "token.json"

    codigo = gmail.main(["autorizar", "--credenciales", str(cliente_json), "--token", str(token)])

    assert codigo == 0
    assert llamadas == {"ruta": str(cliente_json), "scopes": ALCANCES, "port": 0}
    assert _permisos(token) == 0o600
    salida = capsys.readouterr()
    assert TOKEN_INVENTADO not in salida.out + salida.err
    assert REFRESH_INVENTADO not in salida.out + salida.err


def test_comando_autorizar_sin_archivo_de_credenciales(tmp_path):
    codigo = gmail.main([
        "autorizar", "--credenciales", str(tmp_path / "no-existe.json"),
        "--token", str(tmp_path / "token.json"),
    ])
    assert codigo == 2
    assert not (tmp_path / "token.json").exists()
