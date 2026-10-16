"""Ayudas compartidas extraídas de test_migracion_0008; datos inventados."""

from __future__ import annotations


import sqlite3


import pytest


from alembic.util import CommandError


from finanzas import db, migrar


from tests.soporte.migracion_0005 import _estructura, _sql, _subir_hasta


from tests.soporte.migraciones import crear_base_v1, revision


def _saldo(ruta):
    # Observación financiera de esta base histórica (sin columnas del0010),
    # independiente de la API actual que exige el esquema más reciente.
    return _sql(ruta, "SELECT c.saldo_inicial_centavos + COALESCE(SUM(CASE "
        "WHEN m.tipo IN ('ingreso','ajuste') THEN m.monto_centavos "
        "WHEN m.tipo IN ('compra','transferencia') THEN -m.monto_centavos ELSE 0 END),0) "
        "FROM configuracion_saldo c LEFT JOIN movimientos m ON m.fecha_hora >= c.fecha_inicio || 'T00:00:00' "
        "WHERE c.id=1 GROUP BY c.id")[0][0]
