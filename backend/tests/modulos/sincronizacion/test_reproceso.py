"""Reprocesar los correos no reconocidos (ítem 19), con un Gmail falso y correos inventados.

Fixtures propios en ``tests/fixtures/gmail/reproceso/`` (todo inventado):

- ``encabezado_nuevo_inventado.json`` (``msg-r001``): aviso de compra con un
  encabezado de plantilla que el lector todavía no conoce, así que hoy queda
  como citado (no reconocido). Las pruebas simulan "corregir el lector"
  agregando ese encabezado a la lista permitida.
- ``dmarc_fallido_aviso_valido.json`` (``msg-r002``): texto de aviso válido,
  pero con ``dmarc=fail``: nunca debe crear un movimiento (D15).

``msg-0003`` (``otro_tipo_no_reconocido.json``) sigue sin reconocerse.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from finanzas import db, sincronizacion
from finanzas.modulos.categorias.asignacion import AsignarCategorias
from finanzas.modulos.sincronizacion.adaptadores.avisos import lector
from finanzas.gmail import CorreoGmail, ErrorAutorizacionGmail, correo_desde_mensaje
from finanzas.sincronizacion import ResultadoReproceso, SincronizacionNoConfigurada, reprocesar, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import ClienteFalso, correo_fixture
from tests.soporte.reproceso import _correo, _correos, _no_reconocidos, _sincronizar_inicial, conn, corregir_lector  # ayudas compartidas

REPROCESO = Path(__file__).resolve().parents[2] / "fixtures" / "gmail" / "reproceso"
ENCABEZADO_NUEVO = "Encabezado nuevo de ejemplo inventado"












def _movimientos(conn) -> list[tuple]:
    return sql(
        conn, "SELECT gmail_id, monto_centavos, tipo, descripcion, origen FROM movimientos ORDER BY id"
    ).fetchall()




def test_sin_corregir_el_lector_todo_sigue_en_la_lista(conn):
    cliente = _sincronizar_inicial(conn)
    resultado = reprocesar(conn, cliente)
    assert resultado == ResultadoReproceso(revisados=3, siguen_sin_reconocerse=3)
    assert sorted(_no_reconocidos(conn)) == ["msg-0003", "msg-r001", "msg-r002"]
    assert _movimientos(conn) == []


def test_ahora_reconocido_crea_movimiento_y_sale_de_la_lista(conn, corregir_lector):
    cliente = _sincronizar_inicial(conn)
    corregir_lector()
    cliente.llamadas_obtener.clear()
    resultado = reprocesar(conn, cliente)
    assert resultado == ResultadoReproceso(revisados=3, movimientos_creados=1, siguen_sin_reconocerse=2)
    assert sorted(cliente.llamadas_obtener) == ["msg-0003", "msg-r001", "msg-r002"]  # se descargan otra vez
    assert _movimientos(conn) == [("msg-r001", 1234500, "compra", "TIENDA REPROCESO EJEMPLO", "gmail")]
    # El que sigue sin reconocerse y el de DMARC fallido permanecen, intactos.
    filas = {f["gmail_id"]: dict(f) for f in sincronizacion.listar_no_reconocidos(conn)}
    assert set(filas) == {"msg-0003", "msg-r002"}
    assert filas["msg-r002"]["asunto"] == "Aviso sin DMARC (ejemplo)"
    assert filas["msg-r002"]["fecha"] == "2026-08-13T11:20:00"


def test_dmarc_fallido_sigue_rechazado_aunque_el_texto_sea_valido(conn, corregir_lector):
    correo = _correo("dmarc_fallido_aviso_valido.json")
    # El texto, por sí solo, es un aviso válido...
    assert sincronizacion.clasificar_correo(correo.textos)[0] == sincronizacion.AVISO_VALIDO
    # ...pero la verificación (D15) lo rechaza antes de mirar el cuerpo.
    assert sincronizacion.evaluar_correo(correo, sincronizacion.REMITENTE_POR_DEFECTO) == (
        "sin_pass_alineado", None,
    )
    _sincronizar_inicial(conn)
    corregir_lector()
    resultado = reprocesar(conn, ClienteFalso({"msg-r002": correo}), gmail_id="msg-r002")
    assert resultado == ResultadoReproceso(revisados=1, siguen_sin_reconocerse=1)
    assert "msg-r002" in _no_reconocidos(conn)
    assert _movimientos(conn) == []


def test_remitente_ajeno_sigue_rechazado(conn, corregir_lector):
    from dataclasses import replace

    falso = replace(_correo("encabezado_nuevo_inventado.json"), remitente="alertas@ejemplo-falso.example")
    cliente = _sincronizar_inicial(conn)
    corregir_lector()
    cliente.correos["msg-r001"] = falso
    resultado = reprocesar(conn, cliente, gmail_id="msg-r001")
    assert resultado == ResultadoReproceso(revisados=1, siguen_sin_reconocerse=1)
    assert _movimientos(conn) == []


def test_reprocesar_dos_veces_no_duplica(conn, corregir_lector):
    cliente = _sincronizar_inicial(conn)
    corregir_lector()
    assert reprocesar(conn, cliente).movimientos_creados == 1
    segundo = reprocesar(conn, cliente)
    assert segundo == ResultadoReproceso(revisados=2, siguen_sin_reconocerse=2)
    assert len(_movimientos(conn)) == 1
    # Ni una sincronización posterior lo vuelve a descargar ni a guardar.
    cliente.llamadas_obtener.clear()
    assert sincronizar(conn, cliente).nuevos == 0
    assert cliente.llamadas_obtener == []
    assert len(_movimientos(conn)) == 1


def test_fila_sobrante_con_movimiento_ya_guardado_no_duplica(conn, corregir_lector):
    # Caso raro: el id está a la vez en movimientos y en la lista.
    corregir_lector()
    cliente = ClienteFalso({"msg-r001": _correo("encabezado_nuevo_inventado.json")})
    with db.transaccion(conn):
        sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
            "VALUES ('2026-08-12T10:05:00', 1234500, 'compra', 'TIENDA REPROCESO EJEMPLO', 'gmail', 'msg-r001')",
        )
        sql(conn, "INSERT INTO correos_no_reconocidos VALUES ('msg-r001', '2026-08-12T10:05:00', 'Asunto inventado')")
    resultado = reprocesar(conn, cliente)
    assert resultado == ResultadoReproceso(revisados=1, ya_registrados=1)
    assert _no_reconocidos(conn) == []
    assert len(_movimientos(conn)) == 1


def test_error_al_descargar_deja_el_correo_en_la_lista(conn, corregir_lector):
    cliente = _sincronizar_inicial(conn)
    corregir_lector()
    del cliente.correos["msg-r001"]
    cliente.fallan["msg-r001"] = RuntimeError("fallo inventado con $12.345,00")
    resultado = reprocesar(conn, cliente)
    assert resultado == ResultadoReproceso(revisados=3, siguen_sin_reconocerse=2, errores=1)
    assert "msg-r001" in _no_reconocidos(conn)
    assert _movimientos(conn) == []


def test_error_al_guardar_deja_el_correo_en_la_lista(conn, corregir_lector, monkeypatch):
    cliente = _sincronizar_inicial(conn)
    corregir_lector()

    def falla(*args, **kwargs):
        raise RuntimeError("fallo inventado")

    monkeypatch.setattr(AsignarCategorias, "regla_que_coincide", falla)
    resultado = reprocesar(conn, cliente, gmail_id="msg-r001")
    assert resultado == ResultadoReproceso(revisados=1, errores=1)
    assert "msg-r001" in _no_reconocidos(conn)  # la transacción se deshizo entera
    assert _movimientos(conn) == []


def test_anterior_a_la_fecha_de_inicio_sigue_en_la_lista(conn, corregir_lector):
    cliente = _sincronizar_inicial(conn)
    corregir_lector()
    with db.transaccion(conn):
        sql(conn, "UPDATE configuracion_saldo SET fecha_inicio = '2026-08-20' WHERE id = 1")
    resultado = reprocesar(conn, cliente, gmail_id="msg-r001")
    assert resultado == ResultadoReproceso(revisados=1, siguen_sin_reconocerse=1)
    assert _movimientos(conn) == []


def test_un_solo_correo(conn, corregir_lector):
    cliente = _sincronizar_inicial(conn)
    corregir_lector()
    cliente.llamadas_obtener.clear()
    resultado = reprocesar(conn, cliente, gmail_id="msg-r001")
    assert resultado == ResultadoReproceso(revisados=1, movimientos_creados=1)
    assert cliente.llamadas_obtener == ["msg-r001"]
    # Un id que no está en la lista no se descarga.
    assert reprocesar(conn, cliente, gmail_id="msg-0001") == ResultadoReproceso()
    assert cliente.llamadas_obtener == ["msg-r001"]


def test_aplica_las_reglas_recordadas(conn, corregir_lector):
    cliente = _sincronizar_inicial(conn)
    corregir_lector()
    with db.transaccion(conn):
        sql(
            conn,
            "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', ?, 1)",
            ("tienda reproceso ejemplo",),
        )
    reprocesar(conn, cliente, gmail_id="msg-r001")
    fila = sql(conn, "SELECT categoria_id, origen_categoria FROM movimientos").fetchone()
    assert tuple(fila) == (1, "regla")


def test_autorizacion_revocada_se_propaga(conn):
    cliente = _sincronizar_inicial(conn)
    cliente.fallan["msg-0003"] = ErrorAutorizacionGmail("revocado (inventado)")
    del cliente.correos["msg-0003"]
    with pytest.raises(ErrorAutorizacionGmail):
        reprocesar(conn, cliente)
    assert "msg-0003" in _no_reconocidos(conn)


def test_sin_fecha_de_inicio(tmp_path):
    conexion = db.conectar(str(tmp_path / "vacia.db"))
    db.inicializar(conexion)
    try:
        with pytest.raises(SincronizacionNoConfigurada):
            reprocesar(conexion, ClienteFalso({}))
    finally:
        conexion.close()


def test_los_registros_solo_llevan_conteos(conn, corregir_lector, caplog):
    cliente = _sincronizar_inicial(conn)
    corregir_lector()
    cliente.fallan["msg-0003"] = RuntimeError("detalle inventado $9.999,00")
    del cliente.correos["msg-0003"]
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="finanzas"):
        reprocesar(conn, cliente)
    texto = caplog.text
    assert "Reproceso terminado: 3 revisados, 1 movimientos creados" in texto
    for prohibido in ("msg-", "TIENDA", "12.345", "1234500", "9.999", "ejemplo", "Aviso", "inventado"):
        assert prohibido not in texto


# --- ejecutar_reproceso: los mismos códigos de error que "Sincronizar" -----------------------

class _Fabrica:
    def __init__(self, cliente=None, error=None):
        self.cliente, self.error, self.llamadas = cliente, error, 0

    def __call__(self):
        self.llamadas += 1
        if self.error:
            raise self.error
        return self.cliente


def test_ejecutar_sin_fecha_de_inicio_no_toca_gmail(tmp_path):
    conexion = db.conectar(str(tmp_path / "vacia.db"))
    db.inicializar(conexion)
    fabrica = _Fabrica(ClienteFalso({}))
    try:
        assert sincronizacion.ejecutar_reproceso(conexion, fabrica) == (None, "sin_fecha_inicio")
    finally:
        conexion.close()
    assert fabrica.llamadas == 0


def test_ejecutar_con_la_lista_vacia_no_toca_gmail(conn):
    fabrica = _Fabrica(error=SincronizacionNoConfigurada("sin token (inventado)"))
    assert sincronizacion.ejecutar_reproceso(conn, fabrica) == (ResultadoReproceso(), None)
    assert sincronizacion.ejecutar_reproceso(conn, fabrica, gmail_id="msg-r001") == (ResultadoReproceso(), None)
    assert fabrica.llamadas == 0


@pytest.mark.parametrize(
    "error, codigo",
    [
        (SincronizacionNoConfigurada("sin token (inventado)"), "gmail_no_configurado"),
        (ErrorAutorizacionGmail("revocado (inventado)"), "autorizacion_gmail"),
        (RuntimeError("inesperado (inventado)"), "error_inesperado"),
    ],
)
def test_ejecutar_traduce_los_errores(conn, error, codigo):
    _sincronizar_inicial(conn)
    assert sincronizacion.ejecutar_reproceso(conn, _Fabrica(error=error)) == (None, codigo)
    assert len(_no_reconocidos(conn)) == 3


def test_ejecutar_no_toca_el_estado_de_la_sincronizacion(conn, corregir_lector):
    cliente = _sincronizar_inicial(conn)
    corregir_lector()
    resultado, codigo = sincronizacion.ejecutar_reproceso(conn, _Fabrica(cliente))
    assert codigo is None and resultado.movimientos_creados == 1
    assert sincronizacion.leer_estado(conn) is None
