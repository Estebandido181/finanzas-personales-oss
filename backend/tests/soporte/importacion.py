"""Ayudas compartidas extraídas de test_importacion; datos inventados."""

from __future__ import annotations


from datetime import date, datetime


import pytest


from sqlalchemy.exc import IntegrityError


from finanzas.modulos.importaciones import motor as c


from finanzas import db, importacion


from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel, leer_excel_movimientos


from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido


from finanzas.gmail import CorreoGmail


from finanzas.compartido.hora import ZONA_COLOMBIA


from finanzas.sincronizacion import sincronizar


from tests.soporte import excel_inventado


from tests.soporte.ayudas_db import sql as _sql


from tests.soporte.gmail_falso import LEGITIMO as autenticacion


from tests.soporte.gmail_falso import ClienteFalso


SALDO_INICIAL = 100_000_000


def sql(conn, texto, parametros=()):
    return _sql(conn, texto, parametros).fetchall()


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "conciliacion.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(conexion, "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (SALDO_INICIAL, "2026-08-01"))
    yield conexion
    conexion.close()


_gmail = iter(range(1, 100_000))


def del_correo(conn, dia, tipo, monto, descripcion="TIENDA EJEMPLO", hora="10:00:00") -> int:
    with db.transaccion(conn):
        resultado = conn.execute(db.movimientos.insert().values(
            fecha_hora=f"2026-08-{dia:02d}T{hora}", monto_centavos=monto, tipo=tipo,
            descripcion=descripcion, origen="gmail", gmail_id=f"id-inventado-{next(_gmail)}",
        ))
    return int(resultado.inserted_primary_key[0])


def ajuste_el_dia(conn, dia, monto) -> int:
    with db.transaccion(conn):
        resultado = conn.execute(db.movimientos.insert().values(
            fecha_hora=f"2026-08-{dia:02d}T18:00:00", monto_centavos=monto, tipo="ajuste",
            descripcion="Ajuste de saldo", origen="manual",
        ))
    return int(resultado.inserted_primary_key[0])


def primer_dia(conn, dia=2):
    """Un correo ya categorizado y su fila, en un día anterior al que se prueba.

    El día más antiguo de un reporte nunca marca "no está en el banco" (D51):
    con esta fila primero, el día que se prueba no es el primero. El correo se
    confirma sin mover el saldo (ya contaba) ni pedir categoría.
    """
    with db.transaccion(conn):
        conn.execute(db.movimientos.insert().values(
            fecha_hora=f"2026-08-{dia:02d}T10:00:00", monto_centavos=777, tipo="compra",
            descripcion="ANCLA INVENTADA", origen="gmail", gmail_id=f"id-ancla-{dia}", categoria_id=1,
        ))
    return fila(dia, -777, "ANCLA INVENTADA")


def fila(dia, monto, descripcion="COMPRA EN  TIENDA EJEMPLO", referencia=None, sin_formato=False):
    return MovimientoExcel(date(2026, 8, dia), monto, descripcion, referencia, sin_formato)


def foto(conn) -> dict:
    """Todo lo que la conciliación puede cambiar (sin el registro de importaciones)."""
    return {
        "movimientos": [tuple(f) for f in sql(conn, "SELECT * FROM movimientos ORDER BY id")],
        "preguntas": [tuple(f) for f in sql(conn, "SELECT * FROM preguntas_conciliacion ORDER BY id")],
        "candidatos": [tuple(f) for f in sql(conn, "SELECT * FROM candidatos_pregunta ORDER BY 1, 2")],
    }


def movimiento(conn, ident):
    return sql(conn, "SELECT * FROM movimientos WHERE id = ?", (ident,))[0]


def _compra(gmail_id, monto_texto, comercio, dia):
    texto = (f"Bancolombia: Compraste ${monto_texto} en {comercio} con tu T.Deb *4321, "
             f"el {dia:02d}/08/2026 a las 19:05. Si tienes dudas, encuentranos aqui.")
    return CorreoGmail(gmail_id, datetime(2026, 8, dia, 19, 6, tzinfo=ZONA_COLOMBIA), "Asunto inventado", texto,
                       **autenticacion)
