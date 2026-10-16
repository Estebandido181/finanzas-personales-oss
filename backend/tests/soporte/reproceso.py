"""Ayudas compartidas extraídas de test_reproceso; datos inventados."""

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


REPROCESO = Path(__file__).resolve().parents[1] / "fixtures" / "gmail" / "reproceso"


ENCABEZADO_NUEVO = "Encabezado nuevo de ejemplo inventado"


def _correo(nombre: str) -> CorreoGmail:
    return correo_desde_mensaje(json.loads((REPROCESO / nombre).read_text(encoding="utf-8")))


def _correos() -> dict[str, CorreoGmail]:
    return {
        "msg-r001": _correo("encabezado_nuevo_inventado.json"),
        "msg-r002": _correo("dmarc_fallido_aviso_valido.json"),
        "msg-0003": correo_fixture("msg-0003"),
    }


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "reproceso.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (100000000, "2026-08-01"),
        )
    yield conexion
    conexion.close()


@pytest.fixture
def corregir_lector(monkeypatch):
    """Simula el arreglo del lector (tras la primera sincronización): el
    encabezado nuevo pasa a estar permitido."""

    def corregir() -> None:
        claves = lector._CLAVES_ENCABEZADOS | {lector._clave_encabezado(ENCABEZADO_NUEVO)}
        monkeypatch.setattr(lector, "_CLAVES_ENCABEZADOS", claves)

    return corregir


def _no_reconocidos(conn) -> list[str]:
    return [fila["gmail_id"] for fila in sincronizacion.listar_no_reconocidos(conn)]


def _sincronizar_inicial(conn) -> ClienteFalso:
    """Primera sincronización con el lector sin corregir: los tres quedan en la lista."""
    cliente = ClienteFalso(_correos())
    resultado = sincronizar(conn, cliente)
    assert (resultado.nuevos, resultado.no_reconocidos, resultado.rechazados_autenticacion) == (0, 2, 1)
    assert sorted(_no_reconocidos(conn)) == ["msg-0003", "msg-r001", "msg-r002"]
    return cliente
