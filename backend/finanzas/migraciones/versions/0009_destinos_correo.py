"""Ítem 41: destinos del correo y reglas limitados a cuatro dígitos (D45).

No importa código de aplicación: el criterio del recorte queda congelado aquí.
Preflight antes de escribir; la transacción de migrar revierte todo ante fallos.
El recorte es irreversible. La vuelta atrás requiere el respaldo previo.
"""

import re
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _recortar(texto):
    if texto is not None and re.fullmatch(r"\*?[0-9]{4,}", texto):
        return "*" + texto[-4:]
    return texto


@contextmanager
def _borrado_seguro(conn):
    """Limpia celdas SQLite liberadas, solo en esta conexión y durante el recorte.

    No alcanza copias previas, WAL ni journals. No cambia configuración global
    ni ejecuta VACUUM; mantiene la transacción y se restaura incluso ante fallo.
    """
    if conn.dialect.name != "sqlite":
        yield
        return
    anterior = int(conn.exec_driver_sql("PRAGMA secure_delete").scalar_one())
    conn.exec_driver_sql("PRAGMA secure_delete = ON")
    try:
        yield
    finally:
        conn.exec_driver_sql(f"PRAGMA secure_delete = {anterior}")


def upgrade():
    conn = op.get_bind()
    reglas = conn.execute(sa.text(
        "SELECT id, texto, monto_centavos, categoria_id FROM reglas "
        "WHERE campo = 'cuenta_destino' ORDER BY id"
    )).mappings().all()
    por_destino = {}
    por_condiciones = {}
    for regla in reglas:
        destino = _recortar(regla["texto"])
        if destino != regla["texto"] or (destino and re.fullmatch(r"\*[0-9]{4}", destino)):
            por_destino.setdefault(destino, []).append(regla)
        por_condiciones.setdefault((destino, regla["monto_centavos"]), []).append(regla)
    choques = [
        (destino, filas) for destino, filas in sorted(por_destino.items())
        if len({f["categoria_id"] for f in filas}) > 1
    ]
    if choques:
        detalles = "; ".join(
            f"{destino}: " + ", ".join(
                f"regla {f['id']} (categoría {f['categoria_id']})" for f in filas
            ) for destino, filas in choques
        )
        raise CommandError(
            "Choque al recortar destinos: " + detalles + ". No se cambió nada. "
            "Resuelve las categorías de esas reglas antes de volver a migrar."
        )
    # Duplicados de igual categoría y condiciones convergen en el menor id.
    # Se redirigen sus referencias antes de eliminarlos; categorías intactas.
    with _borrado_seguro(conn):
        for (destino, _monto), filas in por_condiciones.items():
            conservada = filas[0]
            for duplicada in filas[1:]:
                conn.execute(sa.text("UPDATE movimientos SET regla_id = :nueva WHERE regla_id = :vieja"),
                             {"nueva": conservada["id"], "vieja": duplicada["id"]})
                conn.execute(sa.text("DELETE FROM reglas WHERE id = :id"), {"id": duplicada["id"]})
            if destino != conservada["texto"]:
                conn.execute(sa.text("UPDATE reglas SET texto = :texto WHERE id = :id"),
                             {"texto": destino, "id": conservada["id"]})
        for tabla, filtro in (
            ("movimientos", "tipo = 'transferencia'"),
            ("preguntas_conciliacion", "fuente = 'correo' AND tipo_movimiento = 'transferencia'"),
        ):
            filas = conn.execute(sa.text(f"SELECT id, descripcion FROM {tabla} WHERE {filtro}")).all()
            for id_, descripcion in filas:
                recortada = _recortar(descripcion)
                if recortada != descripcion:
                    conn.execute(sa.text(f"UPDATE {tabla} SET descripcion = :texto WHERE id = :id"),
                                 {"texto": recortada, "id": id_})
    # referencia y referencia_anterior ya tienen CHECK *dddd desde 0008.
    # Las copias de reglas borradas (38) solo viven en memoria, nunca en SQLite.


def downgrade():
    raise CommandError(
        "La migración 0009 recortó destinos y no se puede deshacer: los dígitos "
        "anteriores no se guardaron. No se cambió nada. Restaura el respaldo "
        "previo a la migración (deploy/GUIA.md)."
    )
