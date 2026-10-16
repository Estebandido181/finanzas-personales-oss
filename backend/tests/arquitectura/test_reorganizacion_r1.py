"""Piloto R1: puertos, snapshot y rollback con SQLite y datos inventados."""
from contextlib import contextmanager
from datetime import datetime

import pytest

from finanzas import db
from finanzas.bootstrap.categorias import componer_consulta_categorias
from finanzas.bootstrap.unidad_de_trabajo import UnidadDeTrabajoSQLite
from finanzas.modulos.categorias.aplicacion import ConsultarCategorias
from finanzas.modulos.categorias.contratos import CategoriaConUso, CategoriaConsultada
from finanzas.modulos.categorias.politica import ReglaEvaluable, elegir_regla
from tests.soporte.ayudas_api import *  # noqa: F401,F403

DESDE, HASTA = datetime(2026, 8, 1), datetime(2026, 9, 1)


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "piloto.db"))
    db.inicializar(conexion)
    yield conexion
    conexion.close()


def test_caso_uso_puerto_y_regla_deshacer_sin_infraestructura():
    class UnidadFalsa:
        def __init__(self):
            self.categorias = self
            self.movimientos = self
            self.en_lectura = False

        @contextmanager
        def lectura(self):
            self.en_lectura = True
            try:
                yield
            finally:
                self.en_lectura = False

        def uso_por_categoria(self, desde, hasta):
            assert self.en_lectura
            return {}

        def consultar_con_uso(self, desde, hasta, clase, *, uso):
            assert self.en_lectura
            assert (desde, hasta, clase) == (DESDE, HASTA, "gasto")
            return [CategoriaConUso(1, "Ejemplo", "gasto", "cat-otros", "coins", 0, total, reglas)
                    for total, reglas in ((0, 0), (1, 0), (0, 1))]

    unidad = UnidadFalsa()
    respuesta = ConsultarCategorias(unidad).ejecutar(DESDE, HASTA, "gasto")
    assert [fila.se_puede_deshacer_borrado for fila in respuesta] == [True, False, False]
    assert not unidad.en_lectura


def test_ruta_consume_consulta_compuesta_y_estado_servidor(api, app):
    class ConsultaFalsa:
        def ejecutar(self, desde, hasta, clase):
            assert (desde, hasta, clase) == (DESDE, HASTA, "gasto")
            return [CategoriaConsultada(CategoriaConUso(90, "Ejemplo", "gasto", "cat-otros", "coins", 0, 0, 0), False)]

    app.state.consulta_categorias = lambda conn: ConsultaFalsa()
    respuesta = api.get("/api/categorias?mes=2026-08&clase=gasto")
    assert respuesta.status_code == 200
    categoria = respuesta.json()["categorias"][0]
    assert categoria["id"] == 90
    # HTTP respeta el campo del caso de uso, incluso con todos los conteos en cero.
    assert categoria["se_puede_deshacer_borrado"] is False


def test_uow_rollback_todos_participantes_y_conexion_abierta(conn):
    unidad = UnidadDeTrabajoSQLite(conn)
    with pytest.raises(RuntimeError, match="abortar"):
        with unidad.escritura(inmediata=True):
            conn.exec_driver_sql("UPDATE categorias SET nombre = 'Cambio inventado' WHERE id = 1")
            with unidad.escritura():
                conn.exec_driver_sql("UPDATE categorias SET nombre = 'Otro inventado' WHERE id = 2")
            # Otro participante lee en la misma transacción.
            nombres = [fila.categoria.nombre for fila in componer_consulta_categorias(conn).ejecutar(DESDE, HASTA)]
            assert "Cambio inventado" in nombres and "Otro inventado" in nombres
            raise RuntimeError("abortar")
    nombres = [fila.categoria.nombre for fila in componer_consulta_categorias(conn).ejecutar(DESDE, HASTA)]
    assert "Cambio inventado" not in nombres and "Otro inventado" not in nombres
    assert not conn.closed
    assert not db.en_transaccion(conn)


def test_uow_participante_no_confirma_transaccion_del_dueno(conn):
    unidad = UnidadDeTrabajoSQLite(conn)
    with pytest.raises(RuntimeError):
        with db.transaccion(conn, inmediata=True):
            with unidad.escritura():
                conn.exec_driver_sql("UPDATE categorias SET nombre = 'Cambio inventado' WHERE id = 1")
            assert db.en_transaccion(conn)
            raise RuntimeError()
    assert conn.exec_driver_sql("SELECT nombre FROM categorias WHERE id = 1").scalar_one() == "Mercado"


def test_uow_snapshot_lecturas_anidadas_no_cierra_transaccion(conn):
    conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    conn.commit()
    unidad = UnidadDeTrabajoSQLite(conn)
    with db.conectar(db.ruta_de(conn)) as otra:
        with unidad.lectura():
            inicial = unidad.categorias.consultar_con_uso(DESDE, HASTA, uso=unidad.movimientos.uso_por_categoria(DESDE, HASTA))
            with db.transaccion(otra):
                otra.exec_driver_sql("UPDATE categorias SET nombre = 'Cambio inventado' WHERE id = 1")
            actual = componer_consulta_categorias(conn).ejecutar(DESDE, HASTA)
            assert actual[0].categoria.nombre == inicial[0].nombre == "Mercado"
            assert db.en_transaccion(conn)
        assert not db.en_transaccion(conn)
        assert componer_consulta_categorias(conn).ejecutar(DESDE, HASTA)[0].categoria.nombre == "Cambio inventado"


def test_snapshot_fallido_se_libera_sin_cerrar_conexion(conn):
    with pytest.raises(RuntimeError):
        with UnidadDeTrabajoSQLite(conn).lectura():
            assert db.en_transaccion(conn)
            raise RuntimeError()
    assert not db.en_transaccion(conn) and not conn.closed


@pytest.mark.parametrize("origen,referencia,esperado", [("gmail", None, 1), ("extracto", "*5678", 3), ("extracto", None, 2)])
def test_politica_pura_origen_destino_y_prioridad(origen, referencia, esperado):
    reglas = [
        ReglaEvaluable(1, 1, "cuenta_destino", None, 100, "exacta", "todos"),
        ReglaEvaluable(2, 2, "cuenta_destino", "envio", None, "contiene", "extracto"),
        ReglaEvaluable(3, 3, "cuenta_destino", "*5678", 100, "exacta", "todos"),
    ]
    assert elegir_regla(reglas, "transferencia", "ENVIO INVENTADO", 100, origen, referencia).id == esperado
    assert elegir_regla(reglas, "ajuste", "ENVIO INVENTADO", 100, origen, referencia) is None


def test_politica_empieza_por_desempate_y_monto_opcional():
    reglas = [ReglaEvaluable(id_, id_, "comercio", "tienda", None, "empieza_por", "todos") for id_ in (2, 1)]
    assert elegir_regla(reglas, "compra", "TIENDA INVENTADA", None).id == 2
    assert elegir_regla(reglas, "compra", "OTRA TIENDA", None) is None


def test_importar_politica_no_carga_sql_http_ni_lectores():
    import subprocess
    import sys

    # Proceso limpio: importar el resto de la aplicación en estas pruebas no
    # puede ocultar una dependencia transitiva del dominio.
    codigo = (
        "import sys; import finanzas.modulos.categorias.politica; "
        "prohibidos = ('sqlalchemy', 'fastapi', 'starlette', 'finanzas.db', "
        "'finanzas.extractor', 'finanzas.gmail', 'finanzas.categorizacion'); "
        "assert not any(m == p or m.startswith(p + '.') "
        "for m in sys.modules for p in prohibidos)"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
