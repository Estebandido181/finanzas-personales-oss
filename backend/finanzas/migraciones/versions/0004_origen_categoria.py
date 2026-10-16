"""Cómo se categorizó cada movimiento: a mano o por qué regla.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-30

Ítem 14: la lista de movimientos dice cómo se categorizó cada uno (a mano o
por qué regla) y, al corregir a mano uno que categorizó una regla, queda
marcado como manual. Se añaden dos columnas a ``movimientos``:

* ``origen_categoria``: ``'manual'`` (lo categorizó el dueño), ``'regla'``
  (lo categorizó una regla recordada) o ``NULL``. ``NULL`` significa "sin
  categoría" si ``categoria_id`` es ``NULL``, y "no se sabe" si tiene
  categoría: es el caso de todo lo que ya estaba categorizado antes de esta
  migración.
* ``regla_id``: la regla que lo categorizó (solo con ``origen_categoria =
  'regla'``). Clave foránea a ``reglas``: no se puede borrar una regla que
  aún señalan movimientos. ``categorizacion.borrar_regla`` primero los
  desliga (``regla_id = NULL``; conservan su categoría y su origen
  ``'regla'``) y luego la borra. Sin ``ON DELETE SET NULL`` a propósito:
  SQLAlchemy no lee esa opción de un ``REFERENCES`` añadido con ``ADD
  COLUMN`` en SQLite y la comparación con ``finanzas.db.metadata`` fallaría;
  además, hacerlo explícito en el código sirve igual en PostgreSQL. Desligar
  importa porque SQLite puede reutilizar el id de una regla borrada, y el
  movimiento no debe acabar señalando otra.

Relleno al migrar: **ninguno**. Los movimientos ya categorizados quedan con
``origen_categoria`` y ``regla_id`` en ``NULL`` ("desconocido"). No se
adivina: que hoy exista una regla que coincide no prueba que fuera ella
(pudo categorizarlos el dueño a mano antes de crearla, o una regla que ya se
borró o cambió de categoría).

``upgrade``: dos ``ALTER TABLE ... ADD COLUMN`` (SQLite los admite con
``REFERENCES`` y ``CHECK`` si el valor por defecto es ``NULL``), sin
reconstruir la tabla ni tocar los datos. Los CHECK van en cada columna:

* ``origen_categoria IN ('manual', 'regla')`` (``NULL`` pasa);
* ``regla_id IS NULL OR COALESCE(origen_categoria, '') = 'regla'``.

``downgrade``: en otros motores, ``DROP COLUMN`` de las dos columnas. En
SQLite no se puede quitar con ``DROP COLUMN`` una columna con clave
foránea, así que se reconstruye ``movimientos`` con la estructura
exacta de la 0001 (las mismas columnas, CHECK, UNIQUE e índice), se copian
las filas con sus ids y se reemplaza la tabla. Solo se pierden los dos datos
nuevos. Nada referencia a ``movimientos``, así que el reemplazo no rompe
otras tablas.

Como toda migración, está escrita sin depender de ``finanzas.db``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Columnas de "movimientos" como las crea la 0001 (y siguen igual hasta la
# 0003): las que se conservan al bajar.
_COLUMNAS_0001 = (
    "id, fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id, registrado_en"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE movimientos ADD COLUMN origen_categoria TEXT "
        "CHECK (origen_categoria IN ('manual', 'regla'))"
    )
    op.execute(
        "ALTER TABLE movimientos ADD COLUMN regla_id INTEGER "
        "REFERENCES reglas (id) "
        "CHECK (regla_id IS NULL OR COALESCE(origen_categoria, '') = 'regla')"
    )


def _solo_sqlite(restriccion: sa.CheckConstraint) -> sa.CheckConstraint:
    return restriccion.ddl_if(dialect="sqlite")


def _ahora_iso() -> sa.TextClause:
    if op.get_bind().dialect.name == "sqlite":
        return sa.text("(strftime('%Y-%m-%dT%H:%M:%S', 'now'))")
    return sa.text("(to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS'))")


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":  # pragma: no cover - solo cuando haya otro motor
        # Fuera de SQLite, DROP COLUMN quita también la clave foránea y los CHECK.
        op.drop_column("movimientos", "regla_id")
        op.drop_column("movimientos", "origen_categoria")
        return
    # SQLite no quita con DROP COLUMN una columna con clave foránea: se
    # reconstruye la tabla con la misma definición que crea la 0001.
    op.create_table(
        "movimientos_0003",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("fecha_hora", sa.Text, nullable=False),
        sa.Column(
            "monto_centavos",
            sa.Integer,
            _solo_sqlite(sa.CheckConstraint("typeof(monto_centavos) = 'integer'")),
            nullable=False,
        ),
        sa.Column(
            "tipo",
            sa.Text,
            sa.CheckConstraint("tipo IN ('compra', 'transferencia', 'ingreso', 'ajuste')"),
            nullable=False,
        ),
        sa.Column("descripcion", sa.Text, nullable=False, server_default=""),
        sa.Column("categoria_id", sa.Integer, sa.ForeignKey("categorias.id")),
        sa.Column(
            "origen", sa.Text, sa.CheckConstraint("origen IN ('gmail', 'manual')"), nullable=False
        ),
        sa.Column("gmail_id", sa.Text, unique=True),
        sa.Column("registrado_en", sa.Text, nullable=False, server_default=_ahora_iso()),
        sa.CheckConstraint(
            "(tipo = 'ajuste' AND monto_centavos <> 0) "
            "OR (tipo <> 'ajuste' AND monto_centavos > 0)"
        ),
        sa.CheckConstraint("(origen = 'gmail') = (gmail_id IS NOT NULL)"),
    )
    op.execute(
        f"INSERT INTO movimientos_0003 ({_COLUMNAS_0001}) SELECT {_COLUMNAS_0001} FROM movimientos"
    )
    op.drop_index("idx_movimientos_fecha_hora", table_name="movimientos")
    op.drop_table("movimientos")
    op.rename_table("movimientos_0003", "movimientos")
    op.create_index("idx_movimientos_fecha_hora", "movimientos", ["fecha_hora"])
