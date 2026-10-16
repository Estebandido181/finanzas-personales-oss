"""Reglas con condiciones combinables: texto opcional y monto exacto opcional.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01

Ítem 17 (D21). Hasta la 0006 una regla era siempre "tipo + texto exacto"
(``campo`` dice el tipo: ``comercio`` = compra, ``cuenta_destino`` =
transferencia, ``quien_envia`` = ingreso). Desde aquí una regla combina:

* el tipo de movimiento (``campo``, obligatorio, igual que antes);
* el texto exacto (``texto``, ahora **opcional**);
* el monto exacto en centavos (``monto_centavos``, nuevo y opcional, D8).

Y siempre al menos una condición además del tipo:
``CHECK (texto IS NOT NULL OR monto_centavos IS NOT NULL)``. Así "transferencia
+ $3.200" es una regla válida (el caso del bus), pero "toda transferencia" no.

``upgrade``:

1. ``reglas`` se reconstruye con ``texto`` opcional (si está, no vacío),
   ``monto_centavos`` opcional (entero > 0) y el CHECK de arriba.
2. La unicidad pasa de ``UNIQUE(campo, texto)`` a un índice único sobre
   ``(campo, COALESCE(texto, ''), COALESCE(monto_centavos, 0))``: en SQL dos
   NULL no chocan en un UNIQUE, y sin el ``COALESCE`` se podrían guardar dos
   reglas "transferencia + $3.200" iguales. ``''`` y ``0`` no son valores
   posibles (los CHECK los rechazan), así que no confunden nada.
3. Las reglas existentes se copian **intactas** (mismos ids, campo, texto y
   categoría; ``monto_centavos`` NULL): siguen coincidiendo exactamente igual
   que antes y los movimientos que categorizaron siguen apuntándoles.

La reconstrucción es la misma de la 0005 (``reglas`` está referenciada por
``movimientos.regla_id``): copia temporal -> DROP -> CREATE con el mismo nombre
-> INSERT con los mismos ids -> DROP de la copia, dentro de la transacción de
la migración y con ``PRAGMA defer_foreign_keys`` (``env.py``).

``downgrade``: vuelve a la estructura exacta de la 0006 (``reglas`` no cambió
desde la 0005) **sin perder datos**, o se niega (``CommandError``) sin tocar
nada. La 0006 no puede guardar una regla
con monto ni una sin texto: si hay alguna, hay que restaurar el respaldo previo
a la migración (D26) o borrarla antes desde la app.

Como toda migración, está escrita sin depender de ``finanzas.db``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CAMPOS = "'comercio', 'cuenta_destino', 'quien_envia'"
INDICE_UNICO = "ux_reglas_condiciones"

MENSAJE_NO_SE_PUEDE_BAJAR = (
    "No se puede volver a la revisión 0006 sin perder datos: hay reglas con monto o sin "
    "texto, que la 0006 no puede guardar. No se cambió nada. Bórralas desde la app o "
    "restaura el respaldo previo a la migración (deploy/GUIA.md)."
)


def _crear_reglas_0007() -> None:
    op.create_table(
        "reglas",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("campo", sa.Text, sa.CheckConstraint(f"campo IN ({CAMPOS})"), nullable=False),
        sa.Column("texto", sa.Text, sa.CheckConstraint("texto IS NULL OR texto <> ''")),
        sa.Column("categoria_id", sa.Integer, sa.ForeignKey("categorias.id"), nullable=False),
        sa.Column(
            "monto_centavos",
            sa.Integer,
            sa.CheckConstraint(
                "monto_centavos IS NULL OR typeof(monto_centavos) = 'integer'"
            ).ddl_if(dialect="sqlite"),
            sa.CheckConstraint("monto_centavos IS NULL OR monto_centavos > 0"),
        ),
        sa.CheckConstraint("texto IS NOT NULL OR monto_centavos IS NOT NULL"),
    )
    op.execute(
        f"CREATE UNIQUE INDEX {INDICE_UNICO} ON reglas "
        "(campo, COALESCE(texto, ''), COALESCE(monto_centavos, 0))"
    )


def _crear_reglas_0006() -> None:
    op.create_table(
        "reglas",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("campo", sa.Text, sa.CheckConstraint(f"campo IN ({CAMPOS})"), nullable=False),
        sa.Column("texto", sa.Text, sa.CheckConstraint("texto <> ''"), nullable=False),
        sa.Column("categoria_id", sa.Integer, sa.ForeignKey("categorias.id"), nullable=False),
        sa.UniqueConstraint("campo", "texto"),
    )


def _rehacer(crear) -> None:
    """Reconstruye ``reglas`` con ``crear()`` conservando las filas y sus ids (ver el docstring)."""
    columnas = "id, campo, texto, categoria_id"
    op.execute("CREATE TABLE reglas_copia_0007 AS SELECT id, campo, texto, categoria_id FROM reglas")
    op.drop_table("reglas")
    crear()
    op.execute(f"INSERT INTO reglas ({columnas}) SELECT {columnas} FROM reglas_copia_0007")
    op.drop_table("reglas_copia_0007")


def upgrade() -> None:
    _rehacer(_crear_reglas_0007)


def downgrade() -> None:
    conexion = op.get_bind()
    nuevas = conexion.execute(
        sa.text("SELECT COUNT(*) FROM reglas WHERE monto_centavos IS NOT NULL OR texto IS NULL")
    ).scalar_one()
    if nuevas:
        raise CommandError(MENSAJE_NO_SE_PUEDE_BAJAR)
    _rehacer(_crear_reglas_0006)
