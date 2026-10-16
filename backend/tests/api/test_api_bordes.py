"""API (ítem 10): casos borde y adversarios. Todos los datos son inventados.

Complementa ``test_api_seguridad.py`` (metapruebas sobre todas las rutas) con
lo que allí no se cubre: ciclo de vida del token CSRF, encabezados raros,
métodos y rutas extrañas, cuerpos malformados o enormes, tipos raros en los
montos, fechas con zona, meses e ids inválidos, concurrencia y que las cifras
de la API cuadren entre sí.
"""

from __future__ import annotations
from finanzas.modulos.saldo import politica as saldo_politica
from finanzas.modulos.saldo.aplicacion import OperarSaldo

import json
import threading

import pytest
from fastapi.testclient import TestClient

from finanzas.api import dependencias

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import (
    CONTRASENA,
    Fabrica,
    configurar_saldo,
    ejecutar_sql,
    insertar_movimiento,
    insertar_regla,
)
from tests.soporte.gmail_falso import ClienteFalso


def _huella(config):
    tablas = ("movimientos", "reglas", "configuracion_saldo", "estado_sincronizacion")
    return {t: ejecutar_sql(config, f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in tablas}


def _ingresos(config):
    return ejecutar_sql(config, "SELECT COUNT(*) FROM movimientos WHERE tipo = 'ingreso'").fetchone()[0]


def _token_ingreso(api):
    return api.get("/api/saldo").json()["token_ingreso"]


def _ingreso(token, **cambios):
    return {"monto_centavos": 5000000, "fecha_hora": "2026-08-15T09:30", "descripcion": "Pago inventado",
            "token": token, **cambios}


def _otro_cliente(app, cookies):
    c = TestClient(app, follow_redirects=False)
    for nombre, valor in cookies.items():
        c.cookies.set(nombre, valor)
    return c


# --- Ciclo de vida del token CSRF ------------------------------------------------------------

def test_token_tras_cerrar_sesion_ya_no_sirve(api, config):
    configurar_saldo(config)
    viejo = api.csrf
    assert api.delete("/api/sesion").status_code == 204
    antes = _huella(config)
    r = api.cliente.post("/api/ajustes", json={"saldo_real_centavos": 1}, headers={"X-CSRF-Token": viejo})
    assert r.status_code == 401
    assert r.json() == {"detalle": dependencias.MENSAJE_SIN_SESION}
    assert _huella(config) == antes


def test_token_de_la_sesion_anterior_no_sirve_tras_volver_a_entrar(api, config):
    configurar_saldo(config)
    viejo = api.csrf
    api.delete("/api/sesion")
    nuevo = api.cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
    assert nuevo != viejo
    antes = _huella(config)
    r = api.cliente.post("/api/ajustes", json={"saldo_real_centavos": 1}, headers={"X-CSRF-Token": viejo})
    assert r.status_code == 403
    assert _huella(config) == antes
    r = api.cliente.post("/api/ajustes", json={"saldo_real_centavos": 1}, headers={"X-CSRF-Token": nuevo})
    assert r.status_code == 200


def test_token_tras_volver_a_entrar_sin_cerrar_sesion_rota(api, config):
    configurar_saldo(config)
    viejo = api.csrf
    nuevo = api.cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
    assert nuevo != viejo
    r = api.cliente.post("/api/ajustes", json={"saldo_real_centavos": 1}, headers={"X-CSRF-Token": viejo})
    assert r.status_code == 403


def test_el_logout_de_la_v1_ya_no_existe_ni_cierra_la_sesion(api, config):
    # Ítem 20: POST /logout se retiró (404). Cerrar sesión es DELETE /api/sesion.
    configurar_saldo(config)
    assert api.cliente.post("/logout").status_code == 404
    assert api.post("/api/ajustes", json={"saldo_real_centavos": 1}).status_code == 200


def test_el_token_es_estable_dentro_de_la_sesion(cliente, config):
    configurar_saldo(config)
    assert cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).status_code == 200
    token = cliente.get("/api/sesion").json()["csrf_token"]
    assert cliente.get("/api/sesion").json()["csrf_token"] == token  # no cambia en cada lectura
    r = cliente.post("/api/ajustes", json={"saldo_real_centavos": 1}, headers={"X-CSRF-Token": token})
    assert r.status_code == 200


def test_nombre_del_encabezado_sin_distinguir_mayusculas(api, config):
    configurar_saldo(config)
    for nombre in ("x-csrf-token", "X-CSRF-TOKEN", "x-CsRf-ToKeN"):
        r = api.cliente.post("/api/ajustes", json={"saldo_real_centavos": 1}, headers={nombre: api.csrf})
        assert r.status_code == 200, nombre


@pytest.mark.parametrize(
    "transformar",
    [str.upper, str.lower, lambda t: t + " ", lambda t: " " + t, lambda t: t[:-1], lambda t: t + "x",
     lambda t: t.encode().hex()],
    ids=["mayusculas", "minusculas", "espacio-final", "espacio-inicial", "truncado", "alargado", "hex"],
)
def test_valor_del_token_debe_ser_exacto(api, config, transformar):
    configurar_saldo(config)
    alterado = transformar(api.csrf)
    if alterado == api.csrf:  # p. ej. un token sin letras (improbable): nada que probar
        pytest.skip("la transformación no cambió el token")
    antes = _huella(config)
    r = api.cliente.post("/api/ajustes", json={"saldo_real_centavos": 1}, headers={"X-CSRF-Token": alterado})
    assert r.status_code == 403
    assert _huella(config) == antes


def test_token_con_caracteres_no_ascii_403_sin_error(api, config):
    configurar_saldo(config)
    r = api.cliente.post(
        "/api/ajustes",
        json={"saldo_real_centavos": 1},
        headers=[("X-CSRF-Token", "tókén-inventado".encode("utf-8"))],
    )
    assert r.status_code == 403


def test_encabezado_duplicado_con_el_primero_falso_403(api, config):
    configurar_saldo(config)
    antes = _huella(config)
    r = api.cliente.post(
        "/api/ajustes",
        json={"saldo_real_centavos": 1},
        headers=[("X-CSRF-Token", "token-inventado"), ("X-CSRF-Token", api.csrf)],
    )
    assert r.status_code == 403
    assert _huella(config) == antes


def test_encabezado_duplicado_con_el_mismo_token_se_acepta(api, config):
    configurar_saldo(config)
    r = api.cliente.post(
        "/api/ajustes",
        json={"saldo_real_centavos": 1},
        headers=[("X-CSRF-Token", api.csrf), ("X-CSRF-Token", api.csrf)],
    )
    assert r.status_code == 200


def test_token_en_el_cuerpo_o_la_url_no_sirve(api, config):
    configurar_saldo(config)
    r = api.cliente.post(f"/api/ajustes?csrf_token={api.csrf}", json={"saldo_real_centavos": 1})
    assert r.status_code == 403
    r = api.cliente.post("/api/ajustes", json={"saldo_real_centavos": 1, "csrf_token": api.csrf})
    assert r.status_code == 403


def test_token_en_una_cookie_no_sirve(api, config):
    configurar_saldo(config)
    api.cliente.cookies.set("X-CSRF-Token", api.csrf)
    r = api.cliente.post("/api/ajustes", json={"saldo_real_centavos": 1})
    assert r.status_code == 403


# --- Cookie manipulada -----------------------------------------------------------------------

def _cookie_sesion(cliente):
    return cliente.cookies.get("sesion")


@pytest.mark.parametrize(
    "alterar",
    [lambda v: v[:-2], lambda v: v[:-5] + ("A" if v[-5] != "A" else "B") + v[-4:], lambda v: "x" + v,
     lambda v: v.split(".")[0], lambda v: ""],
    ids=["firma-truncada", "firma-cambiada", "prefijo", "sin-firma", "vacia"],
)
def test_cookie_alterada_401_aunque_traiga_el_token(api, config, alterar):
    configurar_saldo(config)
    valor = _cookie_sesion(api.cliente)
    api.cliente.cookies.clear()
    api.cliente.cookies.set("sesion", alterar(valor))
    antes = _huella(config)
    assert api.get("/api/sesion").status_code == 401
    r = api.post("/api/ajustes", json={"saldo_real_centavos": 1})
    assert r.status_code == 401
    assert _huella(config) == antes


def test_cookie_firmada_con_otro_secreto_401(config, fabrica, hash_prueba):
    from dataclasses import replace

    from finanzas.web.app import crear_app

    otra = crear_app(replace(config, session_secret="otro-secreto-inventado-de-mas-de-32-caracteres"), fabrica)
    with TestClient(otra) as c:
        c.post("/api/sesion", json={"contrasena": CONTRASENA})
        cookie = c.cookies.get("sesion")
    with TestClient(crear_app(config, fabrica)) as c:
        c.cookies.set("sesion", cookie)
        assert c.get("/api/sesion").status_code == 401


# --- Métodos no permitidos y rutas raras -----------------------------------------------------

@pytest.mark.parametrize(
    "metodo, ruta, permitido",
    [
        ("GET", "/api/ingresos", "POST"),
        ("GET", "/api/ajustes", "POST"),
        ("POST", "/api/reporte", "GET"),
        ("PUT", "/api/sincronizacion", "GET, POST"),
        ("DELETE", "/api/categorias", "GET"),
        ("PATCH", "/api/saldo/configuracion", "PUT"),
        ("POST", "/api/reglas/1", "DELETE"),
        ("GET", "/api/movimientos/1/categoria", "PUT"),
    ],
)
def test_metodo_no_permitido_405_json(api, metodo, ruta, permitido):
    kwargs = {"json": {}} if metodo in {"POST", "PUT", "PATCH"} else {}
    r = api.cliente.request(metodo, ruta, headers={"X-CSRF-Token": api.csrf}, **kwargs)
    assert r.status_code == 405
    assert r.json() == {"detalle": "Método no permitido."}
    # Starlette anuncia solo los métodos de la primera ruta que coincide con la
    # URL (con GET y POST en rutas separadas, PUT /api/sincronizacion dice "POST").
    anunciados = {x.strip() for x in r.headers["allow"].split(",")}
    assert anunciados and anunciados <= {x.strip() for x in permitido.split(",")}


def test_metodo_no_permitido_sin_token_sigue_siendo_403(api, config):
    # La comprobación de CSRF va antes que el enrutado: sin token no se revela nada.
    r = api.cliente.post("/api/reporte", json={})
    assert r.status_code == 403


@pytest.mark.parametrize("metodo", ["TRACE", "CONNECT", "FOO"])
def test_metodos_extranos_no_rompen(api, metodo):
    r = api.cliente.request(metodo, "/api/reporte")
    assert r.status_code in (400, 405)
    assert r.status_code != 500


def test_options_no_abre_cors(api):
    r = api.cliente.options(
        "/api/ajustes",
        headers={"Origin": "https://otro.example", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 405
    assert "access-control-allow-origin" not in r.headers


def test_head_no_filtra_nada_sin_sesion(cliente):
    r = cliente.head("/api/reporte")
    assert r.status_code in (401, 405)


@pytest.mark.parametrize("ruta", ["/api/reporte/", "/api/saldo/", "/api/sesion/"])
def test_barra_final_sin_sesion_401(cliente, ruta):
    r = cliente.get(ruta)
    assert r.status_code == 401
    assert r.json() == {"detalle": dependencias.MENSAJE_SIN_SESION}


@pytest.mark.parametrize("ruta", ["/api/reporte/", "/api/saldo/", "/api/categorias/"])
def test_barra_final_con_sesion_no_redirige_fuera_de_la_api(api, ruta):
    r = api.get(ruta)
    # FastAPI redirige a la ruta sin barra (307). Lo que no puede pasar es que
    # redirija a otro host o a /login.
    if r.status_code in (307, 308):
        destino = r.headers["location"]
        assert destino.endswith(ruta.rstrip("/"))
        assert destino.startswith(("http://testserver/api/", "/api/"))
    else:
        assert r.status_code == 404


def test_barra_final_en_post_sin_token_403(api, config):
    configurar_saldo(config)
    antes = _huella(config)
    r = api.cliente.post("/api/ajustes/", json={"saldo_real_centavos": 1})
    assert r.status_code == 403
    assert _huella(config) == antes


@pytest.mark.parametrize("ruta", ["/api//reporte", "/api/./reporte", "/api/../api/reporte", "/API/reporte"])
def test_rutas_raras_sin_sesion_no_dan_datos(cliente, ruta):
    r = cliente.get(ruta)
    assert r.status_code in (303, 401, 404)
    assert "total_gasto_centavos" not in r.text


# --- Cuerpos malformados o enormes -----------------------------------------------------------

@pytest.mark.parametrize(
    "cuerpo",
    [b"", b"{", b"{'saldo_real_centavos': 1}", b"null", b"[]", b"1", b'"texto"',
     b'{"saldo_real_centavos": 1,}', b"\xff\xfe\x00", b'{"saldo_real_centavos": 1}{"x": 2}'],
    ids=["vacio", "abierto", "comillas-simples", "null", "lista", "numero", "texto", "coma-final",
         "bytes-invalidos", "dos-objetos"],
)
def test_json_malformado_422_sin_cambiar_nada(api, config, cuerpo):
    configurar_saldo(config)
    antes = _huella(config)
    r = api.cliente.post(
        "/api/ajustes", content=cuerpo,
        headers={"Content-Type": "application/json", "X-CSRF-Token": api.csrf},
    )
    assert r.status_code in (400, 422), r.text
    assert "detalle" in r.json()
    assert _huella(config) == antes


def test_json_malformado_no_repite_el_cuerpo(api, config):
    configurar_saldo(config)
    secreto = "valor-secreto-inventado"
    r = api.cliente.post(
        "/api/sesion", content=f'{{"contrasena": "{secreto}"'.encode(),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code in (400, 422)
    assert secreto not in r.text


def test_json_muy_anidado_no_da_500(api, config):
    configurar_saldo(config)
    profundo = b"[" * 200_000 + b"]" * 200_000
    r = api.cliente.post(
        "/api/ajustes", content=profundo,
        headers={"Content-Type": "application/json", "X-CSRF-Token": api.csrf},
    )
    assert r.status_code in (400, 413, 422)
    assert "detalle" in r.json()


def test_entero_con_demasiados_digitos_no_da_500(api, config):
    configurar_saldo(config)
    cuerpo = b'{"saldo_real_centavos": ' + b"9" * 5000 + b"}"
    r = api.cliente.post(
        "/api/ajustes", content=cuerpo,
        headers={"Content-Type": "application/json", "X-CSRF-Token": api.csrf},
    )
    assert r.status_code in (400, 413, 422)
    assert "detalle" in r.json()


def test_cuerpo_enorme_con_texto_largo_422(api, config):
    configurar_saldo(config)
    token = _token_ingreso(api)
    r = api.post("/api/ingresos", json=_ingreso(token, descripcion="x" * 2_000_000))
    assert r.status_code == 422
    assert "xxxx" not in r.text
    assert _ingresos(config) == 0
    # El token no se gastó: el mismo ingreso, corregido, entra.
    assert api.post("/api/ingresos", json=_ingreso(token)).status_code == 201


def test_contrasena_enorme_422_sin_contar_como_intento(cliente):
    for _ in range(5):
        r = cliente.post("/api/sesion", json={"contrasena": "x" * 1_000_000})
        assert r.status_code == 422
    assert cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).status_code == 200


def test_campos_duplicados_en_el_json(api, config):
    configurar_saldo(config)
    cuerpo = b'{"saldo_real_centavos": 1, "saldo_real_centavos": 2}'
    r = api.cliente.post(
        "/api/ajustes", content=cuerpo,
        headers={"Content-Type": "application/json", "X-CSRF-Token": api.csrf},
    )
    # json de Python se queda con el último; al menos debe ser coherente.
    assert r.status_code == 200
    assert r.json()["saldo_centavos"] == 2


@pytest.mark.parametrize(
    "tipo",
    ["application/json; charset=utf-8", "APPLICATION/JSON", "application/json ; charset=UTF-8"],
)
def test_variantes_validas_de_content_type(api, config, tipo):
    configurar_saldo(config)
    r = api.cliente.post(
        "/api/ajustes", content=b'{"saldo_real_centavos": 1}',
        headers={"Content-Type": tipo, "X-CSRF-Token": api.csrf},
    )
    assert r.status_code == 200


@pytest.mark.parametrize(
    "tipo", ["application/json-patch+json", "application/jsonx", "text/json", "application/x-json",
             "multipart/form-data; boundary=x", "text/plain; application/json"],
)
def test_variantes_invalidas_de_content_type_415(api, config, tipo):
    configurar_saldo(config)
    r = api.cliente.post(
        "/api/ajustes", content=b'{"saldo_real_centavos": 1}',
        headers={"Content-Type": tipo, "X-CSRF-Token": api.csrf},
    )
    assert r.status_code == 415


# --- Tipos raros en los montos ---------------------------------------------------------------

MONTOS_RAROS = {
    "1e3": b"1e3",
    "1.0": b"1.0",
    "-0.0": b"-0.0",
    "2**63": str(2**63).encode(),
    "2**63-1": str(2**63 - 1).encode(),
    "-2**63": str(-(2**63)).encode(),
    "texto-numerico": b'"100"',
    "texto-vacio": b'""',
    "true": b"true",
    "false": b"false",
    "null": b"null",
    "NaN": b"NaN",
    "Infinity": b"Infinity",
    "-Infinity": b"-Infinity",
    "lista": b"[100]",
    "objeto": b'{"centavos": 100}',
    "negativo": b"-1",
    "maximo+1": str(saldo_politica.MAXIMO_CENTAVOS + 1).encode(),
}


def _post_crudo(api, ruta, cuerpo):
    return api.cliente.post(
        ruta, content=cuerpo, headers={"Content-Type": "application/json", "X-CSRF-Token": api.csrf}
    )


@pytest.mark.parametrize("valor", list(MONTOS_RAROS.values()), ids=list(MONTOS_RAROS))
def test_monto_raro_en_ajuste_422(api, config, valor):
    configurar_saldo(config)
    antes = _huella(config)
    r = _post_crudo(api, "/api/ajustes", b'{"saldo_real_centavos": ' + valor + b"}")
    assert r.status_code == 422, r.text
    assert _huella(config) == antes
    assert valor.decode() not in json.dumps(r.json()["campos"]) or valor in (b"true", b"false", b"null")


@pytest.mark.parametrize("valor", list(MONTOS_RAROS.values()) + [b"0", b"-0"],
                         ids=list(MONTOS_RAROS) + ["cero", "menos-cero"])
def test_monto_raro_en_ingreso_422_y_token_intacto(api, config, valor):
    configurar_saldo(config)
    token = _token_ingreso(api)
    cuerpo = json.dumps(_ingreso(token, monto_centavos="__M__")).encode().replace(b'"__M__"', valor)
    r = _post_crudo(api, "/api/ingresos", cuerpo)
    assert r.status_code == 422, r.text
    assert _ingresos(config) == 0
    assert api.post("/api/ingresos", json=_ingreso(token)).status_code == 201


@pytest.mark.parametrize("valor", list(MONTOS_RAROS.values()), ids=list(MONTOS_RAROS))
def test_monto_raro_en_configuracion_422(api, config, valor):
    antes = _huella(config)
    r = _post_crudo_put(api, b'{"saldo_inicial_centavos": ' + valor + b', "fecha_inicio": "2026-08-01"}')
    assert r.status_code == 422, r.text
    assert _huella(config) == antes


def _post_crudo_put(api, cuerpo):
    return api.cliente.put(
        "/api/saldo/configuracion", content=cuerpo,
        headers={"Content-Type": "application/json", "X-CSRF-Token": api.csrf},
    )


def test_menos_cero_en_ajuste_es_cero(api, config):
    # En JSON "-0" es el entero 0 (no un flotante): se acepta como saldo real de 0.
    configurar_saldo(config, centavos=100)
    r = _post_crudo(api, "/api/ajustes", b'{"saldo_real_centavos": -0}')
    assert r.status_code == 200
    assert r.json() == {"registrado": True, "diferencia_centavos": -100, "saldo_centavos": 0}


def test_monto_en_el_maximo_exacto(api, config):
    configurar_saldo(config, centavos=0)
    r = api.post("/api/ajustes", json={"saldo_real_centavos": saldo_politica.MAXIMO_CENTAVOS})
    assert r.status_code == 200
    assert api.get("/api/saldo").json()["saldo_centavos"] == saldo_politica.MAXIMO_CENTAVOS


@pytest.mark.parametrize("valor", [b"1.0", b'"1"', b"true", b"-1", b"0", str(10**18 + 1).encode(),
                                   str(2**63).encode()])
def test_categoria_id_rara_422(api, config, valor):
    mov = insertar_movimiento(config)
    antes = _huella(config)
    r = api.cliente.put(
        f"/api/movimientos/{mov}/categoria",
        content=b'{"categoria_id": ' + valor + b"}",
        headers={"Content-Type": "application/json", "X-CSRF-Token": api.csrf},
    )
    assert r.status_code == 422
    assert _huella(config) == antes


@pytest.mark.parametrize("valor", [b"1", b'"true"', b"null"])
def test_recordar_no_booleano_422(api, config, valor):
    mov = insertar_movimiento(config)
    r = api.cliente.put(
        f"/api/movimientos/{mov}/categoria",
        content=b'{"categoria_id": 1, "recordar": ' + valor + b"}",
        headers={"Content-Type": "application/json", "X-CSRF-Token": api.csrf},
    )
    assert r.status_code == 422


# --- Fechas con zona y formatos raros --------------------------------------------------------

@pytest.mark.parametrize(
    "fecha_hora",
    ["2026-08-15T09:30:00Z", "2026-08-15T09:30Z", "2026-08-15T09:30+00:00", "2026-08-15T09:30-05:00",
     "2026-08-15T09:30:00-05:00", "2026-08-15 09:30", "2026-08-15", "15/08/2026 09:30",
     "2026-08-15T09:30:00.123", "2026-08-15T24:00", "2026-02-30T10:00", "+2026-08-15T09:30",
     "2026-08-15T09:30\x00", "２０２６-08-15T09:30", "", " ", "2026-08-15T09:30:60"],
)
def test_ingreso_con_fecha_rara_se_rechaza_sin_gastar_el_token(api, config, fecha_hora):
    configurar_saldo(config)
    token = _token_ingreso(api)
    r = api.post("/api/ingresos", json=_ingreso(token, fecha_hora=fecha_hora))
    assert r.status_code in (400, 422), r.text
    assert "detalle" in r.json()
    assert _ingresos(config) == 0
    assert api.post("/api/ingresos", json=_ingreso(token)).status_code == 201


@pytest.mark.parametrize(
    "fecha",
    ["2026-08-01T00:00", "2026-08-01Z", "2026-8-1", "01/08/2026", "2026-02-30", "0000-01-01", "", "２０２６-08-01"],
)
def test_configurar_con_fecha_rara_se_rechaza(api, config, fecha):
    antes = _huella(config)
    r = api.put("/api/saldo/configuracion", json={"saldo_inicial_centavos": 100, "fecha_inicio": fecha})
    assert r.status_code in (400, 422)
    assert _huella(config) == antes


# --- Mes inválido ----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mes",
    ["2026-13", "2026-00", "0000-01", "9999-12", "2026-1", "26-01", "2026/01", "abcd-ef", "-2026-01",
     " 2026-1", "２０２６-01", "2026-01-01", "2026-001", ""],
)
@pytest.mark.parametrize("ruta", ["/api/reporte", "/api/movimientos"])
def test_mes_invalido_se_rechaza_en_json(api, ruta, mes):
    r = api.get(ruta, params={"mes": mes})
    assert r.status_code in (400, 422), (mes, r.status_code)
    assert "detalle" in r.json()


def test_mes_repetido_en_la_url(api):
    r = api.get("/api/reporte?mes=2026-08&mes=2026-13")
    # FastAPI toma el último para un str: debe rechazarse o tomar uno válido, nunca 500.
    assert r.status_code in (200, 400, 422)


# --- Ids no numéricos, negativos o enormes ---------------------------------------------------

@pytest.mark.parametrize(
    "id_", ["abc", "-1", "0", "1.5", "1e3", "0x10", str(10**18 + 1), str(2**63), "%20", "1%00", "１"],
)
def test_id_raro_en_categorizar_422(api, config, id_):
    insertar_movimiento(config)
    antes = _huella(config)
    r = api.put(f"/api/movimientos/{id_}/categoria", json={"categoria_id": 1})
    assert r.status_code in (404, 422), (id_, r.status_code)
    assert _huella(config) == antes


@pytest.mark.parametrize("id_", ["abc", "-1", "0", "1.5", str(10**18 + 1), str(2**63), "１"])
def test_id_raro_en_borrar_regla_422(api, config, id_):
    insertar_regla(config)
    antes = _huella(config)
    r = api.delete(f"/api/reglas/{id_}")
    assert r.status_code in (404, 422), (id_, r.status_code)
    assert _huella(config) == antes


def test_id_en_el_maximo_da_404(api):
    assert api.put(f"/api/movimientos/{10**18}/categoria", json={"categoria_id": 1}).status_code == 404
    assert api.delete(f"/api/reglas/{10**18}").status_code == 404


def test_id_con_ceros_a_la_izquierda(api, config):
    mov = insertar_movimiento(config)
    r = api.put(f"/api/movimientos/000{mov}/categoria", json={"categoria_id": 1})
    assert r.status_code == 200


# --- Concurrencia ----------------------------------------------------------------------------

def test_doble_envio_de_ingreso_en_paralelo_guarda_uno(api, config, monkeypatch):
    configurar_saldo(config)
    token = _token_ingreso(api)
    cookies = dict(api.cliente.cookies.items())
    original = OperarSaldo.registrar_ingreso

    def registrar_lento(*args, **kwargs):
        threading.Event().wait(0.3)  # el otro envío llega mientras este guarda
        return original(*args, **kwargs)

    monkeypatch.setattr(OperarSaldo, "registrar_ingreso", registrar_lento)
    clientes = [_otro_cliente(api.cliente.app, cookies) for _ in range(4)]
    barrera = threading.Barrier(len(clientes))
    respuestas = [None] * len(clientes)

    def enviar(i):
        barrera.wait()
        respuestas[i] = clientes[i].post(
            "/api/ingresos", json=_ingreso(token), headers={"X-CSRF-Token": api.csrf}
        )

    hilos = [threading.Thread(target=enviar, args=(i,)) for i in range(len(clientes))]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=10)
    estados = sorted(r.status_code for r in respuestas)
    assert estados == [201, 409, 409, 409]
    assert _ingresos(config) == 1


class _ClienteLento(ClienteFalso):
    def __init__(self, dentro: threading.Event, soltar: threading.Event):
        super().__init__()
        self.dentro = dentro
        self.soltar = soltar

    def listar_ids(self, desde):
        self.dentro.set()
        assert self.soltar.wait(10)
        return super().listar_ids(desde)


def test_sincronizacion_concurrente_real_409(api, config, app):
    configurar_saldo(config)
    dentro, soltar = threading.Event(), threading.Event()
    app.state.fabrica_cliente_gmail = Fabrica(cliente=_ClienteLento(dentro, soltar))
    cookies = dict(api.cliente.cookies.items())
    primera = {}

    def lanzar():
        with _otro_cliente(app, cookies) as c:
            primera["r"] = c.post("/api/sincronizacion", json={}, headers={"X-CSRF-Token": api.csrf})

    hilo = threading.Thread(target=lanzar)
    hilo.start()
    try:
        assert dentro.wait(10)
        assert api.get("/api/sincronizacion").json()["en_curso"] is True
        r = api.post("/api/sincronizacion")
        assert r.status_code == 409
        assert r.json() == {"detalle": "Ya hay una sincronización en curso."}
        # El botón de la v1 se retiró (ítem 20): no hay otra puerta al candado.
        assert api.cliente.post("/sincronizar", json={}).status_code == 404
    finally:
        soltar.set()
        hilo.join(timeout=10)
    assert primera["r"].status_code == 200
    assert primera["r"].json()["estado"] == "ok"
    assert app.state.fabrica_cliente_gmail.llamadas == 1
    assert api.get("/api/sincronizacion").json()["en_curso"] is False
    assert api.post("/api/sincronizacion").status_code == 200


# --- Cifras del reporte, los movimientos y el saldo --------------------------------------------

@pytest.fixture
def datos_mes(config):
    configurar_saldo(config, centavos=123456789, fecha="2026-07-01")
    insertar_movimiento(config, fecha_hora="2026-07-20T10:00:00", monto=1111, descripcion="MES ANTERIOR")
    insertar_movimiento(config, fecha_hora="2026-08-01T00:00:00", monto=6863000, descripcion="COMERCIO A",
                        categoria_id=1)
    insertar_movimiento(config, fecha_hora="2026-08-15T12:30:00", monto=12345, descripcion="COMERCIO B",
                        categoria_id=2)
    insertar_movimiento(config, fecha_hora="2026-08-31T23:59:59", monto=99, tipo="transferencia",
                        descripcion="CUENTA INVENTADA")
    insertar_movimiento(config, fecha_hora="2026-08-10T08:00:00", monto=500000, tipo="ingreso",
                        descripcion="Ingreso inventado", origen="manual")
    insertar_movimiento(config, fecha_hora="2026-08-11T08:00:00", monto=-7777, tipo="ajuste",
                        descripcion="", origen="manual")
    insertar_movimiento(config, fecha_hora="2026-09-01T00:00:00", monto=2222, descripcion="MES SIGUIENTE")


def test_reporte_y_saldo_cuadran(api, datos_mes):
    reporte_api = api.get("/api/reporte", params={"mes": "2026-08"}).json()
    saldo_api = api.get("/api/saldo").json()
    esperado_total = 6863000 + 12345 + 99
    esperado_saldo = 123456789 - (1111 + 6863000 + 12345 + 99 + 2222) + 500000 - 7777
    assert reporte_api["total_gasto_centavos"] == esperado_total
    assert reporte_api["saldo_centavos"] == saldo_api["saldo_centavos"] == esperado_saldo
    # Los tres gastos sin categoría y el ingreso inventado (ítem 15); su monto va aparte.
    assert reporte_api["pendientes"] == 4
    assert reporte_api["pendientes_ingresos_centavos"] == 500000
    assert sum(g["centavos"] for g in reporte_api["por_categoria"]) == esperado_total


def test_movimientos_api_coinciden_con_el_reporte(api, datos_mes):
    movimientos = api.get("/api/movimientos", params={"mes": "2026-08"}).json()["movimientos"]
    assert [m["descripcion"] for m in movimientos] == [
        "CUENTA INVENTADA", "COMERCIO B", "", "Ingreso inventado", "COMERCIO A",
    ]
    gasto = sum(m["monto_centavos"] for m in movimientos if m["es_gasto"])
    assert gasto == api.get("/api/reporte", params={"mes": "2026-08"}).json()["total_gasto_centavos"]


def test_mes_vacio(api, datos_mes):
    r = api.get("/api/reporte", params={"mes": "2026-10"}).json()
    assert r["total_gasto_centavos"] == 0
    assert r["por_categoria"] == []


def test_ajustes_seguidos_por_api(api, config):
    configurar_saldo(config, centavos=100000)
    assert api.post("/api/ajustes", json={"saldo_real_centavos": 250050}).status_code == 200
    assert api.get("/api/saldo").json()["saldo_centavos"] == 250050
    assert api.post("/api/ajustes", json={"saldo_real_centavos": 100001}).status_code == 200
    assert api.get("/api/saldo").json()["saldo_centavos"] == 100001


# --- Defectos de la ronda 1 (tester) y comprobaciones del revisor ----------------------------

# Nota sobre "firma-cambiada" (arriba): el último carácter de la firma (base64
# de 32 bytes) lleva 2 bits de relleno, así que cambiarlo de "A" a "B" puede no
# cambiar la firma decodificada y la prueba fallaba a veces. Ahora se altera un
# carácter interior.


@pytest.mark.parametrize(
    "cuerpo",
    [b"[" * 200_000, b'{"saldo_real_centavos": ' + b"9" * 5000 + b"}"],
    ids=["muy-anidado", "entero-enorme"],
)
def test_errores_de_cuerpo_en_espanol(api, config, cuerpo):
    configurar_saldo(config)
    antes = _huella(config)
    r = api.cliente.post(
        "/api/ajustes", content=cuerpo,
        headers={"Content-Type": "application/json", "X-CSRF-Token": api.csrf},
    )
    assert "There was an error" not in r.text, r.text
    assert r.status_code in (400, 422)
    assert set(r.json()) <= {"detalle", "campos"}
    assert "99999" not in r.text and "[[[" not in r.text  # sin eco del cuerpo
    assert _huella(config) == antes


def test_barra_final_no_redirige_a_un_host_ajeno(api):
    # La API no debería redirigir (307) y menos a lo que diga el encabezado Host.
    r = api.cliente.get("/api/reporte/", headers={"Host": "evil.example"})
    assert r.status_code not in (307, 308) or "evil.example" not in r.headers.get("location", "")


def test_barra_final_con_sesion_404_json(api):
    r = api.get("/api/reporte/")
    assert r.status_code == 404
    assert r.json() == {"detalle": "No encontrado."}


@pytest.mark.parametrize("ruta", ["/api/reporte/", "/api/sesion/", "/api/reglas/1/"])
def test_barra_final_sin_sesion_401_sin_redireccion(cliente, ruta):
    r = cliente.get(ruta, headers={"Host": "evil.example"})
    assert r.status_code == 401
    assert "location" not in r.headers


def test_rutas_de_la_v1_con_barra_final_no_redirigen(api):
    r = api.cliente.get("/saldo/", headers={"Host": "evil.example"})
    assert r.status_code == 404
    assert "location" not in r.headers
    r = api.cliente.get("/saldo", headers={"Host": "evil.example"})
    assert r.status_code == 307
    assert r.headers["location"] == "/app/saldo"  # relativa: nunca usa el Host recibido


def test_422_por_monto_invalido_no_repite_el_valor(api, config):
    configurar_saldo(config)
    r = api.post("/api/ajustes", json={"saldo_real_centavos": 100.5})
    assert r.status_code == 422
    assert "100.5" not in r.text and "100,5" not in r.text
    assert r.json()["campos"][0]["ubicacion"] == ["body", "saldo_real_centavos"]
    r = api.post("/api/ajustes", json={"saldo_real_centavos": "12345,67"})
    assert r.status_code == 422
    assert "12345" not in r.text
