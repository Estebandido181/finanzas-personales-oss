"""Casos borde de Gmail + sincronización (ítem 03), sin red.

Los correos son respuestas simuladas de ``users.messages.get(format="full")``
guardadas en ``tests/fixtures/gmail/bordes/``. Todo es inventado: montos,
comercios, cuentas y asuntos.
"""

from __future__ import annotations

import json
import logging
import os
import re
import stat
import subprocess
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from finanzas import db, sincronizacion
from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor
from finanzas.gmail import (
    ZONA_COLOMBIA,
    ClienteGmailReal,
    CorreoGmail,
    ErrorAutorizacionGmail,
    REMITENTE_POR_DEFECTO,
    consulta_gmail,
    correo_desde_mensaje,
    guardar_token,
    html_a_texto,
)
from finanzas.sincronizacion import ResultadoSincronizacion, localizar_aviso, sincronizar
from tests.soporte.gmail_falso import LEGITIMO
from tests.soporte.ayudas_db import sql

RAIZ = Path(__file__).resolve().parents[4]
BORDES = Path(__file__).resolve().parents[2] / "fixtures" / "gmail" / "bordes"


def _mensaje(nombre: str) -> dict:
    return json.loads((BORDES / nombre).read_text(encoding="utf-8"))


def _correo(nombre: str) -> CorreoGmail:
    return correo_desde_mensaje(_mensaje(nombre))


class Cliente:
    """``ClienteGmail`` en memoria que registra las llamadas."""

    def __init__(self, correos: list[CorreoGmail], ids: list[str] | None = None):
        self.correos = {c.gmail_id: c for c in correos}
        self.ids = ids if ids is not None else list(self.correos)
        self.llamadas_obtener: list[str] = []

    def listar_ids(self, desde: date) -> list[str]:
        return list(self.ids)

    def obtener(self, gmail_id: str) -> CorreoGmail:
        self.llamadas_obtener.append(gmail_id)
        return self.correos[gmail_id]


@pytest.fixture
def ruta_db(tmp_path):
    return str(tmp_path / "bordes.db")


@pytest.fixture
def conn(ruta_db):
    conexion = db.conectar(ruta_db)
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (100000000, "2026-08-01"),
        )
    yield conexion
    conexion.close()


def _movimiento(conn, gmail_id: str) -> dict:
    fila = sql(
        conn,
        "SELECT tipo, monto_centavos, fecha_hora, descripcion, origen, categoria_id "
        "FROM movimientos WHERE gmail_id = ?",
        (gmail_id,),
    ).fetchone()
    assert fila is not None, f"no se guardó {gmail_id}"
    return dict(fila)


def _no_reconocidos(conn) -> dict[str, dict]:
    return {f["gmail_id"]: dict(f) for f in sql(conn, "SELECT * FROM correos_no_reconocidos")}


def _contar(conn, tabla: str) -> int:
    return sql(conn, f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


# --- HTML y texto del correo -----------------------------------------------------------

def test_html_con_nbsp_entidades_span_b_y_br_en_el_aviso(conn):
    resultado = sincronizar(conn, Cliente([_correo("html_entidades_span_br.json")]))

    assert resultado == ResultadoSincronizacion(nuevos=1)
    assert _movimiento(conn, "borde-0001") == {
        "tipo": "compra",
        "monto_centavos": 6863000,
        "fecha_hora": "2026-08-15T14:32:00",
        "descripcion": "PANADERÍA EJEMPLO",  # &Iacute; y &nbsp; resueltos
        "origen": "gmail",
        "categoria_id": None,
    }


def test_aviso_partido_en_varias_lineas_con_crlf(conn):
    resultado = sincronizar(conn, Cliente([_correo("texto_aviso_varias_lineas.json")]))

    assert resultado == ResultadoSincronizacion(nuevos=1)
    mov = _movimiento(conn, "borde-0002")
    assert (mov["tipo"], mov["monto_centavos"], mov["descripcion"]) == ("transferencia", 600000, "*5678")
    assert mov["fecha_hora"] == "2026-08-16T09:15:00"


def test_correo_sin_parte_de_texto_queda_como_no_reconocido(conn):
    correo = _correo("sin_parte_de_texto.json")
    assert correo.texto == ""

    resultado = sincronizar(conn, Cliente([correo]))

    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _contar(conn, "movimientos") == 0
    assert _no_reconocidos(conn)["borde-0003"]["asunto"] == "Extracto (ejemplo)"


@pytest.mark.parametrize(
    "nombre, gmail_id, hora",
    [
        ("charset_windows1252.json", "borde-0004", "08:05"),
        ("charset_ausente.json", "borde-0005", "08:06"),
        ("charset_desconocido.json", "borde-0006", "08:07"),
    ],
)
def test_charset_declarado_ausente_o_desconocido(conn, nombre, gmail_id, hora):
    resultado = sincronizar(conn, Cliente([_correo(nombre)]))

    assert resultado == ResultadoSincronizacion(nuevos=1)
    mov = _movimiento(conn, gmail_id)
    assert mov["descripcion"] == "CAFÉ ÑANDÚ EJEMPLO"
    assert mov["monto_centavos"] == 4590000
    assert mov["fecha_hora"] == f"2026-08-18T{hora}:00"


def test_base64url_sin_relleno_en_un_correo_completo(conn):
    datos = _mensaje("base64_sin_relleno.json")["payload"]["body"]["data"]
    assert len(datos) % 4 != 0 and not datos.endswith("=")  # el fixture de verdad no trae relleno

    resultado = sincronizar(conn, Cliente([_correo("base64_sin_relleno.json")]))

    assert resultado == ResultadoSincronizacion(nuevos=1)
    mov = _movimiento(conn, "borde-0007")
    assert (mov["monto_centavos"], mov["fecha_hora"]) == (123456700, "2026-08-19T18:40:22")


@pytest.mark.parametrize(
    "html",
    [
        # Entidades numéricas para $ y *.
        "<p>Bancolombia: Compraste &#36;68.630,00 en MERPAGO&#42;TIENDA con tu T.Deb &#x2A;1234, "
        "el 15/08/2026 a las 14:32.</p>",
        # Etiquetas en mayúsculas y un comentario HTML en medio.
        "<P>Bancolombia: <!-- plantilla -->Compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234, "
        "el 15/08/2026 a las 14:32.</P>",
        # &nbsp; al principio y al final del párrafo.
        "<p>&nbsp;Bancolombia:&nbsp;Compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234, "
        "el 15/08/2026 a las 14:32.&nbsp;</p>",
    ],
    ids=["entidades_numericas", "mayusculas_y_comentario", "nbsp_bordes"],
)
def test_variantes_de_html_se_reconocen(html):
    movimiento = extractor.extraer(localizar_aviso(html_a_texto(html)))
    assert movimiento is not None
    assert (movimiento.monto_centavos, movimiento.descripcion) == (6863000, "MERPAGO*TIENDA")


def test_preencabezado_oculto_desconocido_no_se_reconoce():
    """Antes era el caso "preencabezado" de ``test_variantes_de_html_se_reconocen``."""
    html = (
        '<div style="display:none">Resumen de tu movimiento</div>'
        "<p>Bancolombia: Compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234, el 15/08/2026 a las 14:32.</p>"
    )
    # ítem 21: antes se reconocía; ahora queda no reconocido porque "Resumen de
    # tu movimiento" no es un encabezado conocido (no se ha visto en correos
    # reales). Si aparece en uno, se agrega a ENCABEZADOS_PERMITIDOS.
    assert extractor.extraer(localizar_aviso(html_a_texto(html))) is None
    assert sincronizacion.extraer_aviso(html_a_texto(html)) is None


# --- Asunto ------------------------------------------------------------------------------

def test_asunto_con_caracteres_especiales_se_guarda_tal_cual(conn):
    # D12 / ítem 09: el cuerpo es "Recibiste un pago de $150,000.00 en tu cuenta *1234
    # el 20/08/26 ...", otra redacción de "Recibiste": sigue sin reconocerse.
    correo = _correo("asunto_especial.json")
    resultado = sincronizar(conn, Cliente([correo]))

    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _no_reconocidos(conn)["borde-0008"]["asunto"] == correo.asunto
    assert "DROP TABLE" in correo.asunto
    assert _contar(conn, "movimientos") == 0  # la tabla sigue existiendo


def test_correo_sin_asunto_guarda_asunto_vacio(conn):
    resultado = sincronizar(conn, Cliente([_correo("sin_asunto.json")]))

    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _no_reconocidos(conn)["borde-0009"] == {
        "gmail_id": "borde-0009",
        "fecha": "2026-08-20T12:05:00",
        "asunto": "",
    }


# --- Límite de la fecha de inicio (medianoche en Colombia) ------------------------------

MEDIANOCHE_UTC = datetime(2026, 8, 1, 5, 0, tzinfo=timezone.utc)  # 01/08/2026 00:00 en Colombia


def _correo_en(instante: datetime) -> CorreoGmail:
    mensaje = _mensaje("medianoche_colombia.json")
    mensaje["internalDate"] = str(int(instante.timestamp() * 1000))
    return correo_desde_mensaje(mensaje)


def test_fixture_medianoche_esta_justo_en_el_limite():
    assert _correo("medianoche_colombia.json").fecha == MEDIANOCHE_UTC


@pytest.mark.parametrize(
    "instante, se_guarda",
    [
        (MEDIANOCHE_UTC, True),                                   # 00:00:00.000 del día de inicio
        (MEDIANOCHE_UTC + timedelta(milliseconds=1), True),
        (MEDIANOCHE_UTC - timedelta(milliseconds=1), False),      # 31/07 23:59:59.999 en Colombia
        (datetime(2026, 8, 1, 2, 0, tzinfo=timezone.utc), False),  # ya es 1/08 en UTC, pero 31/07 en Colombia
    ],
    ids=["medianoche", "medianoche_mas_1ms", "medianoche_menos_1ms", "dia_utc_distinto"],
)
def test_limite_de_la_fecha_de_inicio_en_hora_de_colombia(conn, instante, se_guarda):
    resultado = sincronizar(conn, Cliente([_correo_en(instante)]))

    assert resultado.nuevos == (1 if se_guarda else 0)
    assert resultado.errores == 0
    assert _contar(conn, "movimientos") == (1 if se_guarda else 0)
    assert _contar(conn, "correos_no_reconocidos") == 0


def test_consulta_after_es_la_medianoche_de_colombia():
    consulta = consulta_gmail("alertas@example.com", date(2026, 8, 1))
    assert consulta.endswith(f"after:{int(MEDIANOCHE_UTC.timestamp())}")


# --- correos_no_reconocidos no guarda el cuerpo ----------------------------------------

def test_no_reconocidos_sin_cuerpo_ni_en_tabla_ni_en_el_archivo(conn, ruta_db):
    correos = [_correo(n) for n in ("asunto_especial.json", "sin_asunto.json", "sin_parte_de_texto.json")]
    sincronizar(conn, Cliente(correos))

    columnas = [fila[1] for fila in sql(conn, "PRAGMA table_info(correos_no_reconocidos)")]
    assert columnas == ["gmail_id", "fecha", "asunto"]
    assert set(_no_reconocidos(conn)) == {"borde-0008", "borde-0009", "borde-0003"}

    sql(conn, "PRAGMA wal_checkpoint(TRUNCATE)")
    contenido = b"".join(p.read_bytes() for p in Path(ruta_db).parent.glob("bordes.db*"))
    for fragmento in ("Recibiste un pago de", "150,000.00", "Texto de ejemplo sin aviso", "*1234"):
        assert fragmento.encode("utf-8") not in contenido, fragmento


# --- Logs sin datos ------------------------------------------------------------------------

PROHIBIDOS_EN_LOGS = (
    "68.630", "6863000", "PANADER", "ÑANDÚ", "CAFÉ", "45.900", "4590000", "6,000.00", "600000",
    "1,234,567", "123456700", "*1234", "*5678", "*0000", "150,000", "Alerta de", "Extracto",
    "DROP TABLE", "Ñandú", "Recibiste", "Bancolombia:", "Texto de ejemplo", "llámanos",
)


def test_logs_de_una_sincronizacion_con_bordes_no_tienen_datos(conn, caplog, monkeypatch):
    nombres = sorted(p.name for p in BORDES.glob("*.json") if p.name != "medianoche_colombia.json")
    correos = [_correo(n) for n in nombres]

    class ConFallos(Cliente):
        def obtener(self, gmail_id):
            if gmail_id == "borde-9999":
                raise ValueError("Compraste $68.630,00 en PANADERÍA EJEMPLO *1234")
            return super().obtener(gmail_id)

    extraer_real = extractor.extraer

    def extraer_que_falla(texto):
        if texto and "ÑANDÚ" in texto and "08:07" in texto:
            raise RuntimeError(f"no pude leer: {texto}")
        return extraer_real(texto)

    monkeypatch.setattr(sincronizacion.extractor, "extraer", extraer_que_falla)
    cliente = ConFallos(correos, ids=[c.gmail_id for c in correos] + ["borde-9999"])
    with caplog.at_level(logging.DEBUG):
        resultado = sincronizar(conn, cliente)

    assert resultado.errores == 2  # uno al descargar y otro al procesar
    texto = caplog.text
    assert "borde-0001" in texto and "borde-9999" in texto  # los ids sí se registran
    for prohibido in PROHIBIDOS_EN_LOGS:
        assert prohibido not in texto, prohibido


# --- Ids repetidos y paginación ------------------------------------------------------------

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
        self.tokens_pedidos: list[str | None] = []
        self.ids_pedidos: list[str] = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kwargs):
        self.tokens_pedidos.append(kwargs.get("pageToken"))
        return _Peticion(self.paginas[kwargs.get("pageToken")])

    def get(self, **kwargs):
        self.ids_pedidos.append(kwargs["id"])
        return _Peticion(self.mensajes[kwargs["id"]])


def _mensaje_compra(gmail_id: str, minuto: int) -> dict:
    """Copia del fixture HTML con otro id y otra hora de recepción."""
    mensaje = _mensaje("html_entidades_span_br.json")
    mensaje["id"] = gmail_id
    instante = datetime(2026, 8, 15, 14, 0, tzinfo=ZONA_COLOMBIA) + timedelta(minutes=minuto)
    mensaje["internalDate"] = str(int(instante.timestamp() * 1000))
    return mensaje


def test_id_repetido_dentro_de_la_misma_pagina_de_gmail(conn):
    service = _ServiceFalso(
        paginas={None: {"messages": [{"id": "rep-1"}, {"id": "rep-1"}, {"id": "rep-2"}, {"id": "rep-1"}]}},
        mensajes={"rep-1": _mensaje_compra("rep-1", 1), "rep-2": _mensaje_compra("rep-2", 2)},
    )
    resultado = sincronizar(conn, ClienteGmailReal(service))

    assert resultado == ResultadoSincronizacion(nuevos=2)
    assert service.ids_pedidos == ["rep-1", "rep-2"]
    assert _contar(conn, "movimientos") == 2


def test_paginacion_con_muchas_paginas_e_ids_repetidos_entre_paginas(conn):
    total_paginas = 60
    paginas, mensajes = {}, {}
    for n in range(total_paginas):
        token = None if n == 0 else f"p{n}"
        ids = [f"pag-{n:03d}-a", f"pag-{n:03d}-b"]
        if n > 0:
            ids.append(f"pag-{n - 1:03d}-b")  # Gmail puede repetir un id al cambiar de página
        pagina = {"messages": [{"id": i} for i in ids]}
        if n == 30:
            pagina = {"resultSizeEstimate": 0, "nextPageToken": "p31"}  # página intermedia vacía
            ids = []
        if n < total_paginas - 1:
            pagina["nextPageToken"] = f"p{n + 1}"
        paginas[token] = pagina
        for i in ids:
            mensajes[i] = _mensaje_compra(i, len(mensajes) % 600)

    service = _ServiceFalso(paginas=paginas, mensajes=mensajes)
    # Un solo remitente: el falso devuelve las mismas páginas a cualquier consulta.
    resultado = sincronizar(conn, ClienteGmailReal(service, REMITENTE_POR_DEFECTO))

    assert service.tokens_pedidos == [None] + [f"p{n}" for n in range(1, total_paginas)]
    assert resultado == ResultadoSincronizacion(nuevos=len(mensajes))
    assert sorted(service.ids_pedidos) == sorted(mensajes)  # cada id se descarga una sola vez
    assert _contar(conn, "movimientos") == len(mensajes)

    # Una segunda sincronización no descarga nada.
    service.ids_pedidos.clear()
    assert sincronizar(conn, ClienteGmailReal(service)) == ResultadoSincronizacion()
    assert service.ids_pedidos == []


# --- Error de autorización a mitad de la sincronización ------------------------------------

def _error_401():
    import httplib2
    from googleapiclient.errors import HttpError

    return HttpError(httplib2.Response({"status": 401}), b"{}")


def _error_refresh():
    from google.auth.exceptions import RefreshError

    return RefreshError("invalid_grant: token inventado revocado")


@pytest.mark.parametrize("fabrica_error", [_error_401, _error_refresh], ids=["http_401", "refresh_error"])
def test_error_de_autorizacion_a_mitad_conserva_lo_guardado_y_luego_retoma(conn, fabrica_error):
    ids = [f"aut-{n}" for n in range(5)]
    mensajes = {i: _mensaje_compra(i, n) for n, i in enumerate(ids)}
    buenos = dict(mensajes)
    mensajes["aut-3"] = fabrica_error()  # se revoca el token al llegar al cuarto correo
    paginas = {None: {"messages": [{"id": i} for i in ids]}}

    service = _ServiceFalso(paginas=paginas, mensajes=mensajes)
    with pytest.raises(ErrorAutorizacionGmail):
        sincronizar(conn, ClienteGmailReal(service))

    assert service.ids_pedidos == ["aut-0", "aut-1", "aut-2", "aut-3"]  # se detiene, no sigue con aut-4
    guardados = {f[0] for f in sql(conn, "SELECT gmail_id FROM movimientos")}
    assert guardados == {"aut-0", "aut-1", "aut-2"}

    # Tras volver a autorizar: solo se descargan los que faltaban y no hay duplicados.
    service_nuevo = _ServiceFalso(paginas=paginas, mensajes=buenos)
    resultado = sincronizar(conn, ClienteGmailReal(service_nuevo))
    assert resultado == ResultadoSincronizacion(nuevos=2)
    assert service_nuevo.ids_pedidos == ["aut-3", "aut-4"]
    assert _contar(conn, "movimientos") == 5


def test_error_de_autorizacion_en_la_segunda_pagina_no_guarda_nada_a_medias(conn):
    service = _ServiceFalso(
        paginas={None: {"messages": [{"id": "x-1"}], "nextPageToken": "p2"}, "p2": _error_401()},
        mensajes={"x-1": _mensaje_compra("x-1", 1)},
    )
    with pytest.raises(ErrorAutorizacionGmail):
        sincronizar(conn, ClienteGmailReal(service))
    assert service.ids_pedidos == []
    assert _contar(conn, "movimientos") == 0


# --- Dos sincronizaciones concurrentes -----------------------------------------------------

@pytest.mark.parametrize("ronda", range(5))
def test_dos_sincronizaciones_concurrentes_con_dos_conexiones_no_duplican(conn, ruta_db, ronda):
    """Temporizador y botón a la vez: cada uno con su conexión, en su hilo,
    y ambos descargan los mismos correos al mismo tiempo."""
    ids = [f"con-{n:02d}" for n in range(20)]
    correos = [correo_desde_mensaje(_mensaje_compra(i, n)) for n, i in enumerate(ids)]
    correos.append(_correo("sin_asunto.json"))  # también un no reconocido
    barrera = threading.Barrier(2, timeout=10)

    class Sincronizado(Cliente):
        def listar_ids(self, desde):
            barrera.wait()  # ambos leen los ids registrados antes de guardar nada
            return super().listar_ids(desde)

    resultados: list[ResultadoSincronizacion] = []
    fallos: list[BaseException] = []

    def trabajar():
        conexion = db.conectar(ruta_db)
        try:
            resultados.append(sincronizar(conexion, Sincronizado(correos)))
        except BaseException as error:  # noqa: BLE001 - se revisa abajo
            fallos.append(error)
        finally:
            conexion.close()

    hilos = [threading.Thread(target=trabajar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)

    assert fallos == []
    assert len(resultados) == 2
    assert sum(r.errores for r in resultados) == 0
    assert sum(r.nuevos for r in resultados) == len(ids)
    assert sum(r.no_reconocidos for r in resultados) == 1
    assert _contar(conn, "movimientos") == len(ids)
    assert _contar(conn, "correos_no_reconocidos") == 1
    duplicados_en_base = sql(
        conn,
        "SELECT COUNT(*) FROM (SELECT gmail_id FROM movimientos GROUP BY gmail_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    assert duplicados_en_base == 0


# --- Token ------------------------------------------------------------------------------

class _CredencialesInventadas:
    def to_json(self) -> str:
        return json.dumps({"token": "ya29.inventado-bordes", "refresh_token": "1//inventado-bordes"})


def _modo(ruta: Path) -> int:
    return stat.S_IMODE(os.stat(ruta).st_mode)


def test_token_nuevo_queda_0600_aunque_la_umask_sea_permisiva(tmp_path):
    anterior = os.umask(0)
    try:
        ruta = tmp_path / "token.json"
        guardar_token(_CredencialesInventadas(), ruta)
    finally:
        os.umask(anterior)
    assert _modo(ruta) == 0o600
    assert json.loads(ruta.read_text(encoding="utf-8"))["token"] == "ya29.inventado-bordes"


def test_token_existente_con_permisos_abiertos_pasa_a_0600(tmp_path):
    ruta = tmp_path / "token.json"
    ruta.write_text("{}", encoding="utf-8")
    os.chmod(ruta, 0o644)
    guardar_token(_CredencialesInventadas(), ruta)
    assert _modo(ruta) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["token.json"]  # sin temporales


def test_token_en_ruta_relativa_de_la_carpeta_actual(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    guardar_token(_CredencialesInventadas(), "token_gmail.json")
    assert _modo(tmp_path / "token_gmail.json") == 0o600


@pytest.mark.parametrize("nombre", ["token.json", "token_gmail.json", "credenciales.json", "client_secret_123.json"])
def test_git_ignora_los_archivos_del_token_y_del_cliente_oauth(nombre):
    salida = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", nombre],
        cwd=RAIZ, capture_output=True, check=False,
    )
    assert salida.returncode == 0, f"{nombre} no está en .gitignore"


def test_ningun_token_versionado_en_el_repositorio():
    archivos = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    sospechosos = [a for a in archivos if Path(a).name.startswith(("token", "client_secret"))
                   and a.endswith(".json")]
    assert sospechosos == []
    # Tokens de Google: de acceso ("ya29." + texto) o de refresco ("1//" + texto),
    # seguidos de muchos caracteres. Los de las pruebas dicen "inventado".
    patron = re.compile(r"(ya29\.|\b1//)[A-Za-z0-9_\-.]{20,}")
    for archivo in archivos:
        ruta = RAIZ / archivo
        if ruta.is_file() and ruta.suffix in {".json", ".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".example"}:
            for coincidencia in patron.finditer(ruta.read_text(encoding="utf-8", errors="ignore")):
                assert "inventad" in coincidencia.group(0), f"{archivo}: posible token real"


# --- Avisos partidos o mezclados con otro texto (correcciones de la ronda 2) -------------

_AVISO_COMPRA = "Compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234, el 15/08/2026 a las 14:32."


@pytest.mark.parametrize(
    "html",
    [
        "<p>Bancolombia: Compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234,<br><br>"
        "el 15/08/2026 a las 14:32.</p>",
        "<p><b>Bancolombia:</b></p><p>" + _AVISO_COMPRA + "</p>",
        "<table><tr><td><b>Bancolombia:</b></td><td>" + _AVISO_COMPRA + "</td></tr></table>",
    ],
    ids=["br_doble", "prefijo_parrafo_aparte", "prefijo_celda_aparte"],
)
def test_aviso_partido_en_bloques_se_lee_con_su_fecha(html):
    # Antes: test_aviso_partido_o_con_texto_oculto_delante_se_reconoce (el caso
    # del texto oculto delante pasó a test_span_oculto_con_otro_aviso_delante_no_se_reconoce).
    movimiento = sincronizacion.extraer_aviso(html_a_texto(html))
    assert movimiento is not None
    assert (movimiento.monto_centavos, movimiento.descripcion) == (6863000, "MERPAGO*TIENDA")
    assert movimiento.fecha_hora == datetime(2026, 8, 15, 14, 32)


def test_span_oculto_con_otro_aviso_delante_no_se_reconoce():
    """Antes era el caso "preencabezado_span_oculto" de
    ``test_aviso_partido_o_con_texto_oculto_delante_se_reconoce`` (hoy
    ``test_aviso_partido_en_bloques_se_lee_con_su_fecha``)."""
    html = (
        '<p><span style="display:none">Bancolombia: Compraste ... ver detalle</span>Bancolombia: '
        + _AVISO_COMPRA + "</p>"
    )
    # ítem 21: antes se reconocía el segundo aviso; ahora queda no reconocido
    # porque el texto oculto delante no es un encabezado conocido y ya no se
    # busca una segunda posición.
    assert sincronizacion.extraer_aviso(html_a_texto(html)) is None


def test_latin1_sin_charset_no_deja_caracter_de_reemplazo():
    import base64

    from finanzas.gmail import texto_del_cuerpo

    aviso = "Bancolombia: Compraste $45.900,00 en CAFÉ EJEMPLO con tu T.Deb *1234, el 18/08/2026 a las 08:05."
    datos = base64.urlsafe_b64encode(aviso.encode("latin-1")).decode().rstrip("=")
    texto = texto_del_cuerpo({"mimeType": "text/plain", "body": {"data": datos}})
    movimiento = sincronizacion.extraer_aviso(texto)
    assert movimiento is not None and movimiento.descripcion == "CAFÉ EJEMPLO"


def test_texto_plano_de_relleno_y_aviso_solo_en_el_html(conn):
    correo = CorreoGmail(
        "relleno-1", datetime(2026, 8, 15, 14, 33, tzinfo=ZONA_COLOMBIA), "Alerta (ejemplo)",
        texto="Tu cliente de correo no muestra HTML. Ingresa a la app para ver el detalle.",
        alternativos=(html_a_texto("<p>Bancolombia: " + _AVISO_COMPRA + "</p>"),),
        **LEGITIMO,
    )
    assert sincronizar(conn, Cliente([correo])) == ResultadoSincronizacion(nuevos=1)


# --- Falsos positivos: correos de Bancolombia que no son avisos ----------------------------

@pytest.mark.parametrize(
    "texto",
    [
        # Publicidad que usa las palabras sin el formato del aviso.
        "¿Compraste algo hoy? Con tu T.Deb acumulas puntos. ¡Transferiste sin costo! "
        "Aprovecha hasta el 31/08/2026 a las 23:59.",
        # Pie de página típico.
        "Bancolombia: Tu extracto está listo. Si compraste con tu tarjeta débito y no reconoces "
        "la compra, llámanos al 000 000 0000. Si transferiste a una cuenta equivocada, escríbenos.",
        # Monto con el formato del otro tipo de aviso.
        "Bancolombia: Compraste $6,000.00 en MERPAGO*TIENDA con tu T.Deb *1234, el 15/08/2026 a las 14:32.",
        # Cita incompleta de un aviso (sin fecha ni hora).
        "Bancolombia: Hace poco compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234. "
        "Califica tu experiencia.",
        # Transferencia a una llave con otro orden ("desde tu cuenta" antes de "a la
        # llave", sin titular ni quien recibe): no es el formato Bre-B conocido.
        "Bancolombia: Transferiste $6,000.00 desde tu cuenta *1234 a la llave 3000000000 el 15/08/26 a las 09:15.",
        # D12 / ítem 09: "Recibiste una transferencia por ... de NOMBRE en tu cuenta
        # **dddd, el dd/mm/aaaa" ya se reconoce como ingreso. Esta es otra redacción
        # ("de" en vez de "por", sin quien envía, cuenta con un asterisco, fecha
        # dd/mm/aa): sigue siendo "no reconocido" a propósito.
        "Bancolombia: Recibiste una transferencia de $6,000.00 en tu cuenta *1234 el 15/08/26 a las 09:15.",
        # Palabras parecidas que no son "Compraste" como palabra.
        "Bancolombia: Recompraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234, el 15/08/2026 a las 14:32.",
    ],
    ids=["publicidad", "pie_de_pagina", "monto_de_otro_tipo", "cita_incompleta", "llave",
         "recibiste", "palabra_parecida"],
)
def test_correo_que_no_es_aviso_no_inventa_movimiento(conn, texto):
    correo = CorreoGmail(
        "fp-1", datetime(2026, 8, 20, 9, 0, tzinfo=ZONA_COLOMBIA), "Novedades (ejemplo)", texto, **LEGITIMO
    )
    assert sincronizar(conn, Cliente([correo])) == ResultadoSincronizacion(no_reconocidos=1)
    assert _contar(conn, "movimientos") == 0


# --- Ataques de remitente y autenticación (fixtures en gmail/autenticacion/) -------------

AUTENTICACION = Path(__file__).resolve().parents[2] / "fixtures" / "gmail" / "autenticacion"
_ATAQUES = sorted(p.name for p in AUTENTICACION.glob("*.json") if not p.name.startswith("legitimo_"))
_LEGITIMOS = sorted(p.name for p in AUTENTICACION.glob("legitimo_*.json"))


def _correo_aut(nombre: str) -> CorreoGmail:
    return correo_desde_mensaje(json.loads((AUTENTICACION / nombre).read_text(encoding="utf-8")))


def test_hay_fixtures_de_ataque_y_legitimos():
    assert len(_ATAQUES) >= 15 and len(_LEGITIMOS) >= 2


@pytest.mark.parametrize("nombre", _ATAQUES)
def test_correo_falsificado_se_rechaza_sin_crear_movimiento(conn, nombre):
    """Todos traen un aviso "Compraste" válido en el cuerpo: si pasaran el
    filtro, se crearía un movimiento."""
    correo = _correo_aut(nombre)
    if nombre == "reenviado_manualmente.json":
        # ítem 21: antes el cuerpo se reconocía como aviso; ahora queda no
        # reconocido porque "---------- Forwarded message ..." no es un
        # encabezado conocido. El rechazo por autenticación se sigue probando.
        assert extractor.extraer(localizar_aviso(correo.texto)) is None
    else:
        assert extractor.extraer(localizar_aviso(correo.texto)) is not None  # el cuerpo sí es un aviso

    resultado = sincronizar(conn, Cliente([correo]))

    assert resultado.rechazados_autenticacion == 1
    assert (resultado.nuevos, resultado.errores) == (0, 0)
    assert _contar(conn, "movimientos") == 0
    assert _no_reconocidos(conn)[correo.gmail_id]["asunto"] == "Alerta de compra (ataque de ejemplo)"


@pytest.mark.parametrize("nombre", _LEGITIMOS)
def test_variantes_legitimas_de_encabezados_se_aceptan(conn, nombre):
    resultado = sincronizar(conn, Cliente([_correo_aut(nombre)]))
    assert resultado.nuevos == 1 and resultado.rechazados_autenticacion == 0


def test_rechazados_no_se_vuelven_a_descargar_ni_dejan_datos_en_logs(conn, ruta_db, caplog):
    correos = [_correo_aut(n) for n in _ATAQUES]
    cliente = Cliente(correos)
    with caplog.at_level(logging.DEBUG):
        primero = sincronizar(conn, cliente)
    assert primero.rechazados_autenticacion == len(correos)

    cliente.llamadas_obtener.clear()
    with caplog.at_level(logging.DEBUG):
        segundo = sincronizar(conn, cliente)
    assert cliente.llamadas_obtener == []
    assert segundo.rechazados_autenticacion == 0 and segundo.nuevos == 0
    assert _contar(conn, "movimientos") == 0
    assert _contar(conn, "correos_no_reconocidos") == len(correos)

    texto = caplog.text
    assert all(c.gmail_id in texto for c in correos)  # los ids sí
    for prohibido in (
        "evil", "example.org", "notificacionesbancolombia", "alertasynotificaciones", "dkim", "spf=",
        "dmarc", "99.999", "9999900", "TIENDA FALSA", "*9999", "ataque de ejemplo", "Forwarded",
        "Persona Ejemplo", "=?UTF-8",
    ):
        assert prohibido not in texto, prohibido

    sql(conn, "PRAGMA wal_checkpoint(TRUNCATE)")
    contenido = b"".join(p.read_bytes() for p in Path(ruta_db).parent.glob("bordes.db*"))
    for fragmento in (b"TIENDA FALSA", b"evil.example", b"dkim=", b"alertasynotificaciones@"):
        assert fragmento not in contenido, fragmento


# --- Valores que controla el atacante dentro del Authentication-Results de Gmail ----------

_BANCO = "notificacionesbancolombia.com"

# D15 (docs/decisiones.md): solo cuenta un dmarc=pass alineado. Estos ataques
# fabricaban antes un dkim=pass, que ahora se rechaza simplemente porque falta
# el dmarc, sin llegar a probar el analizador. Por eso el valor inyectado es
# ahora un dmarc=pass header.from=<banco> fabricado, y cada caso declara el
# motivo esperado: "encabezado_invalido" (ataque sintáctico: además se exige
# analizar_authentication_results(...) is None) o "sin_pass_alineado" (el
# encabezado es válido pero el dominio que extrae el analizador no es el del
# banco). Si el analizador se rompiera, el pass fabricado pasaría y el caso fallaría.
_INVALIDO = "encabezado_invalido"
_SIN_PASS = "sin_pass_alineado"


def _motivo(autenticacion: str) -> str | None:
    from finanzas.gmail import REMITENTE_POR_DEFECTO, motivo_autenticacion_invalida

    correo = CorreoGmail("atq-0", None, "", "", remitente=REMITENTE_POR_DEFECTO, autenticacion=autenticacion)
    return motivo_autenticacion_invalida(correo, REMITENTE_POR_DEFECTO)


def _comprobar_ataque(autenticacion: str, motivo: str) -> None:
    from finanzas.gmail import analizar_authentication_results

    assert _motivo(autenticacion) == motivo
    assert (analizar_authentication_results(autenticacion) is None) == (motivo == _INVALIDO)


@pytest.mark.parametrize(
    "autenticacion, motivo",
    [
        # SPF alineado ya no basta por sí solo (regla de D15, no del analizador).
        (f"mx.google.com; spf=pass smtp.mailfrom=alertasynotificaciones@an.{_BANCO}; dkim=none; dmarc=fail header.from={_BANCO}", _SIN_PASS),
        # Dominio del banco en la parte local (sin comillas): cuenta lo que va tras la última @.
        (f"mx.google.com; dmarc=pass header.from={_BANCO}@evil.example", _SIN_PASS),
        (f"mx.google.com; dmarc=pass header.from=an.{_BANCO}@evil.example", _SIN_PASS),
        (f"mx.google.com; dmarc=pass header.from=header.from={_BANCO}@evil.example", _INVALIDO),
        (f"mx.google.com; dmarc=pass header.from=@evil.example.{_BANCO}.evil.example", _SIN_PASS),
        (f"mx.google.com; spf=pass smtp.mailfrom={_BANCO}@evil.example; dmarc=pass header.from=evil.example", _SIN_PASS),
        # header.from con dos dominios.
        (f"mx.google.com; dmarc=pass header.from={_BANCO},evil.example", _INVALIDO),
        (f"mx.google.com; dmarc=pass header.from=evil.example,{_BANCO}", _INVALIDO),
        (f"mx.google.com; dmarc=pass header.from=evil.example {_BANCO}", _INVALIDO),
        # ";" dentro de un comentario cerrado.
        (f"mx.google.com; dmarc=fail (x; dmarc=pass header.from={_BANCO}) header.from={_BANCO}", _SIN_PASS),
        # Barra invertida fuera de una cadena entre comillas: invalida TODO, también el dmarc=pass.
        # (El caso header.b="AbCd" pasó a test_header_b_entre_comillas_con_dkim_alineado_es_valido.)
        (f"mx.google.com; dmarc=pass header.from={_BANCO}; spf=fail smtp.mailfrom=a\\;b@evil.example", _INVALIDO),
        # Un resultado que empieza por "pass" pero no lo es.
        (f"mx.google.com; dmarc=passed header.from={_BANCO}", _INVALIDO),
    ],
    ids=["spf_solo", "i_local_banco", "i_local_subdominio", "i_local_con_header_d", "i_banco_en_medio",
         "mailfrom_local_banco", "from_coma_1", "from_coma_2", "from_espacio", "pyc_en_comentario",
         "barra_invertida", "passed"],
)
def test_valores_del_atacante_no_fabrican_un_pass(autenticacion, motivo):
    _comprobar_ataque(autenticacion, motivo)


def test_header_b_entre_comillas_con_dkim_alineado_es_valido():
    """Cambio de premisa (decisión del team leader, analizador estricto RFC 8601):
    antes cualquier comilla se rechazaba. Un valor entre comillas es legal según
    la RFC y aquí no aporta dominio; el dkim=pass con header.d del banco es
    auténtico. D15: DKIM solo ya no basta, así que el encabezado lleva además
    el dmarc=pass alineado que Gmail informa para un aviso real."""
    from finanzas.gmail import REMITENTE_POR_DEFECTO, autenticacion_valida

    correo = CorreoGmail(
        "atq-2", datetime(2026, 8, 21, 10, 0, tzinfo=ZONA_COLOMBIA), "", "",
        remitente=REMITENTE_POR_DEFECTO,
        autenticacion=f'mx.google.com; dkim=pass header.d={_BANCO} header.b="AbCd"; dmarc=pass header.from={_BANCO}',
    )
    assert autenticacion_valida(correo, REMITENTE_POR_DEFECTO) is True


# --- Analizador estricto de Authentication-Results (RFC 8601): ataques y bordes -------------

def _valida(autenticacion: str) -> bool:
    from finanzas.gmail import REMITENTE_POR_DEFECTO, autenticacion_valida

    correo = CorreoGmail("atq-3", None, "", "", remitente=REMITENTE_POR_DEFECTO, autenticacion=autenticacion)
    return autenticacion_valida(correo, REMITENTE_POR_DEFECTO)


# D15: el pass fabricado es un dmarc=pass header.from=<banco> (antes, un
# dkim=pass que ahora se rechazaría solo por faltar el dmarc). Ver _comprobar_ataque.
@pytest.mark.parametrize(
    "autenticacion, motivo",
    [
        # Comillas con escapes: \" no cierra la cadena; el dominio es el de tras la @.
        (f'mx.google.com; spf=pass smtp.mailfrom="a\\";dmarc=pass header.from={_BANCO}"@evil.example; dkim=none', _INVALIDO),
        (f'mx.google.com; spf=pass smtp.mailfrom="a\\\\";dmarc=pass header.from={_BANCO}; x="@evil.example', _INVALIDO),
        # ";" dentro de comillas.
        (f'mx.google.com; dmarc=pass header.from="x;dmarc=pass header.from={_BANCO}"@evil.example', _SIN_PASS),
        (f'mx.google.com; dmarc=pass header.from="x;dmarc=pass header.from={_BANCO}"', _SIN_PASS),
        # Salto de línea sin plegar.
        (f"mx.google.com;\r\ndmarc=pass header.from={_BANCO}", _INVALIDO),
        # Unicode y espacios raros fuera de comentarios.
        (f"mx.google.com; dmarc=pass header.from={_BANCO}", _INVALIDO),
        ("mx.google.com; dmarc=pass header.from=notificacionesbancolombiа.com", _INVALIDO),  # 'а' cirílica
        (f"mx.google.com; dmarc＝pass header.from={_BANCO}", _INVALIDO),
        (f"mx.google.com; dmarc=pass header.from=​{_BANCO}", _INVALIDO),
        # header.from con parte local entre comillas que contiene @banco.
        (f'mx.google.com; dmarc=pass header.from="x@{_BANCO}"@evil.example', _SIN_PASS),
        # Dominios mal formados.
        (f"mx.google.com; dmarc=pass header.from=-{_BANCO}", _SIN_PASS),
        (f"mx.google.com; dmarc=pass header.from=@-an.{_BANCO}", _INVALIDO),
        (f"mx.google.com; dmarc=pass header.from=.{_BANCO}", _SIN_PASS),
        (f"mx.google.com; dmarc=pass header.from={_BANCO}..", _SIN_PASS),
        (f'mx.google.com; dmarc=pass header.from="{_BANCO}"', _SIN_PASS),
        # dmarc=pass con header.from de dos dominios en un mismo valor.
        (f"mx.google.com; dmarc=pass header.from=evil.example,{_BANCO}", _INVALIDO),
        (f"mx.google.com; dmarc=pass header.from=evil.example {_BANCO}", _INVALIDO),
        # Versión y servidor.
        (f"mx.google.com 1.0; dmarc=pass header.from={_BANCO}", _INVALIDO),
        (f"mx.google.com v1; dmarc=pass header.from={_BANCO}", _INVALIDO),
        (f"mx.google.com.; dmarc=pass header.from={_BANCO}", _INVALIDO),
        (f"mx.google.com/1; dmarc=pass header.from={_BANCO}", _INVALIDO),
        (f"mx.google.com; none; dmarc=pass header.from={_BANCO}", _INVALIDO),
        # Valores pegados (HELO, selector, firma) y reason.
        (f"mx.google.com; spf=pass smtp.helo=x;dmarc=pass,header.from={_BANCO}", _INVALIDO),
        (f"mx.google.com; dmarc=pass header.from=evil.example header.s=header.from={_BANCO}", _INVALIDO),
        (f"mx.google.com; dmarc=pass header.from=evil.example header.b=abc/header.from={_BANCO}", _INVALIDO),
        (f"mx.google.com; dmarc=pass header.from=evil.example header.b=abc=header.from={_BANCO}", _INVALIDO),
        (f'mx.google.com; dmarc=pass reason="header.from={_BANCO}" header.from=evil.example', _SIN_PASS),
        # Paréntesis escapado que deja el comentario sin cerrar.
        (f"mx.google.com; dmarc=fail (a \\) ; dmarc=pass header.from={_BANCO}", _INVALIDO),
    ],
    ids=["escape_no_cierra", "barra_doble_cola_invalida", "pyc_en_comillas_con_arroba",
         "pyc_en_comillas_sin_arroba", "salto_sin_plegar", "nbsp", "cirilica", "igual_ancho_completo",
         "espacio_ancho_cero", "i_local_comillas_con_banco", "d_guion_inicial", "i_etiqueta_con_guion",
         "d_punto_inicial", "d_doble_punto", "d_entre_comillas", "from_dos_dominios_coma",
         "from_dos_dominios_espacio", "version_decimal", "version_letras", "servidor_punto_final",
         "servidor_barra", "none_con_resultados", "helo_pegado", "selector_pegado", "firma_con_barra",
         "firma_con_igual", "reason_con_propiedad", "parentesis_escapado_sin_cerrar"],
)
def test_analizador_estricto_no_fabrica_un_pass(autenticacion, motivo):
    _comprobar_ataque(autenticacion, motivo)


@pytest.mark.parametrize(
    "autenticacion",
    [
        # D15: DMARC es obligatorio, así que cada variante lleva ahora también un
        # dmarc=pass alineado con la misma rareza (antes bastaba el dkim=pass).
        f"mx.google.com;\r\n\tdkim=pass\r\n\t header.d={_BANCO};\r\n\tdmarc=pass\r\n\t header.from={_BANCO}",  # plegado con tabulaciones
        f"mx.google.com 1; dkim=pass header.d={_BANCO}; dmarc=pass header.from={_BANCO}",  # versión tras el servidor
        f"mx.google.com (x) 1 (y); dkim=pass header.d={_BANCO}; dmarc=pass header.from={_BANCO}",
        f"mx.google.com; dkim=pass (a b) header.d={_BANCO}; dmarc=pass (a b) header.from={_BANCO}",  # rareza solo dentro de un comentario
        f"mx.google.com; dkim=pass header.d={_BANCO}.; dmarc=pass header.from={_BANCO}.",  # punto final del dominio
        f"MX.GOOGLE.COM; DKIM=PASS HEADER.D={_BANCO.upper()}; DMARC=PASS HEADER.FROM={_BANCO.upper()}",
    ],
    ids=["plegado_tab", "version", "version_con_comentarios", "nbsp_en_comentario", "d_punto_final",
         "mayusculas"],
)
def test_analizador_estricto_acepta_variantes_legitimas(autenticacion):
    assert _valida(autenticacion) is True


@pytest.mark.parametrize(
    "entrada",
    [
        "mx.google.com; dkim=pass " + "(" * 100_000 + ")" * 100_000 + f" header.d={_BANCO}",
        "mx.google.com; dkim=pass " + "(" * 100_000 + f" header.d={_BANCO}",
        "mx.google.com" + f"; dkim=fail header.d={_BANCO}" * 30_000,
        'mx.google.com; dkim=pass header.i="' + "a" * 1_000_000 + f'"@{_BANCO}',
        "mx.google.com; dkim=pass header.d=a" + "-" * 1_000_000,
        "mx.google.com; dkim=pass header.d=" + "a-a." * 250_000 + "-",
        "mx.google.com; dkim=pass (" + "\\(" * 500_000 + ")",
        "mx.google.com;" + "\r\n " * 300_000 + f"dkim=pass header.d={_BANCO}",
    ],
    ids=["anidado_profundo", "anidado_sin_cerrar", "muchos_resultados", "cadena_1mb",
         "guiones_1mb", "muchas_etiquetas", "escapes_1mb", "plegados_1mb"],
)
def test_analizador_estricto_es_lineal_con_entradas_enormes(entrada):
    import time

    from finanzas.gmail import analizar_authentication_results

    inicio = time.perf_counter()
    analizar_authentication_results(entrada)
    assert time.perf_counter() - inicio < 5  # ~0,8 s en la máquina de pruebas; sin retroceso catastrófico


# --- Reglas semánticas del analizador (d7a9738): último intento de colar un pass ------------

_DKIM_BANCO = f"dkim=pass header.i=@{_BANCO} header.s=s1 header.b=AbCd"
_DMARC_FAIL = f"dmarc=fail (p=REJECT sp=REJECT dis=NONE) header.from={_BANCO}"
_DMARC_PASS = f"dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from={_BANCO}"


def _spf_con_local(local: str) -> str:
    """Resultado SPF como lo escribe Gmail: el MAIL FROM tal cual en el
    comentario y entre comillas (escapado) en smtp.mailfrom."""
    escapado = local.replace("\\", "\\\\").replace('"', '\\"')
    return (
        f"spf=pass (google.com: domain of {local}@evil.example designates 198.51.100.66 as permitted sender) "
        f'smtp.mailfrom="{escapado}@evil.example"'
    )


@pytest.mark.parametrize(
    "autenticacion",
    [
        # Duplicar el dmarc con otra capitalización o con versión.
        f"mx.google.com; DMARC=pass header.from={_BANCO}; {_DMARC_FAIL}",
        f"mx.google.com; dmarc/1=pass header.from={_BANCO}; {_DMARC_FAIL}",
        f"mx.google.com; dmarc=pass header.from={_BANCO} HEADER.FROM=evil.example",
        # Método conocido para absorber la cola del comentario SPF cortado.
        "mx.google.com; " + _spf_con_local(f"a) ; dmarc=pass header.from={_BANCO}; iprev=pass (z") + f"; {_DMARC_FAIL}",
        # D15: el pass fabricado es un dmarc=pass alineado (antes un dkim=pass, que
        # ahora se rechazaría solo por faltar el dmarc) y no hay dmarc real detrás.
        "mx.google.com; " + _spf_con_local(f"a) ; dmarc=pass header.from={_BANCO}; iprev=pass (z"),
        "mx.google.com; " + _spf_con_local(f"a) ; dmarc=pass header.from={_BANCO}; iprev=pass ((z"),
        "mx.google.com; " + _spf_con_local(f"a) ; dmarc=pass header.from={_BANCO}; arc=none (z"),
        "mx.google.com; " + _spf_con_local(f'a) ; dmarc=pass header.from={_BANCO}; iprev=pass x.y="'),
        # dmarc=pass inyectado desde el comentario de iprev, con el dmarc real de Gmail detrás.
        f"mx.google.com; iprev=pass policy.iprev=198.51.100.66 (x) ; dmarc=pass header.from={_BANCO}; "
        f"arc=none (y); {_DMARC_FAIL}",
        # Un Received no es un Authentication-Results.
        f"from x (x ; dmarc=pass header.from={_BANCO}) by mx.google.com",
    ],
    ids=["dmarc_mayusculas_duplicado", "dmarc_version_duplicado", "dmarc_dos_from_capitalizacion",
         "iprev_absorbe_con_dmarc", "iprev_absorbe_sin_dmarc", "iprev_doble_parentesis",
         "arc_absorbe", "comilla_en_la_cola", "iprev_inyecta_dmarc_con_dmarc_real", "received"],
)
def test_reglas_semanticas_no_dejan_colar_un_pass(autenticacion):
    # D15: además del rechazo, el encabezado entero debe quedar inválido; si no,
    # el caso podría "pasar" solo porque falta un dmarc=pass y no por el analizador.
    _comprobar_ataque(autenticacion, _INVALIDO)


@pytest.mark.parametrize(
    "autenticacion",
    [
        f"mx.google.com; DMARC=PASS HEADER.FROM={_BANCO}",
        f"mx.google.com; {_DKIM_BANCO}; spf=pass smtp.mailfrom=persona+caf_x@example.org; {_DMARC_PASS}",
        f'mx.google.com; {_DKIM_BANCO}; spf=pass smtp.mailfrom="persona+caf_=duenio@example.org"; {_DMARC_PASS}',
        f'mx.google.com; {_DKIM_BANCO}; spf=pass smtp.mailfrom="persona+caf_=duenio"@example.org; {_DMARC_PASS}',
        # D15: antes aceptado solo por el dkim=pass; ahora lleva el dmarc=pass.
        f"mx.google.com; spf=pass smtp.helo=x.example; {_DKIM_BANCO}; {_DMARC_PASS}",
        f"mx.google.com; dkim=fail header.d={_BANCO}; {_DMARC_PASS}",  # dmarc decide
    ],
    ids=["dmarc_mayusculas", "mailfrom_con_mas", "mailfrom_con_igual_entre_comillas",
         "mailfrom_local_con_igual_entre_comillas", "spf_solo_con_helo", "dmarc_pass_decide"],
)
def test_reglas_semanticas_aceptan_variantes_legitimas(autenticacion):
    assert _valida(autenticacion) is True
