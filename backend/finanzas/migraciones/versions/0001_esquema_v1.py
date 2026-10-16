"""Estructura de la v1 y categorías fijas.

Revision ID: 0001
Revises:
Create Date: 2026-09-30

Reproduce exactamente la estructura que creaba ``db.inicializar`` en la v1
(``finanzas/migraciones/esquema_v1.py``): mismas columnas, CHECK, UNIQUE,
DEFAULT, claves foráneas e índice. Una prueba lo compara.

La base de producción, creada por la v1, **no** pasa por aquí: ``finanzas.migrar``
comprueba que su estructura coincide y la marca como ``0001`` (``stamp``).
Esta migración solo corre en bases nuevas.

Está escrita sin depender de ``finanzas.db``: una migración es una foto de su
momento y no debe cambiar cuando cambie el código.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIAS_FIJAS = (
    "Mercado",
    "Restaurantes",
    "Transporte",
    "Vivienda y servicios",
    "Salud",
    "Entretenimiento",
    "Compras",
    "Otros",
)


def _solo_sqlite(restriccion: sa.CheckConstraint) -> sa.CheckConstraint:
    # SQLite guarda cualquier tipo en cualquier columna: sin este CHECK, 12.5
    # o 'abc' se guardarían como monto. En otros motores el tipo ya lo impide.
    return restriccion.ddl_if(dialect="sqlite")


def _ahora_iso() -> sa.TextClause:
    if op.get_bind().dialect.name == "sqlite":
        return sa.text("(strftime('%Y-%m-%dT%H:%M:%S', 'now'))")
    return sa.text("(to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS'))")


def upgrade() -> None:
    # nullable=True en los "id": SQLite recibe "id INTEGER, PRIMARY KEY (id)",
    # igual que el "INTEGER PRIMARY KEY" de la v1 (alias del rowid).
    categorias = op.create_table(
        "categorias",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("nombre", sa.Text, nullable=False, unique=True),
    )
    op.create_table(
        "movimientos",
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
    op.create_index("idx_movimientos_fecha_hora", "movimientos", ["fecha_hora"])
    op.create_table(
        "reglas",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column(
            "campo",
            sa.Text,
            sa.CheckConstraint("campo IN ('comercio', 'cuenta_destino')"),
            nullable=False,
        ),
        sa.Column("texto", sa.Text, sa.CheckConstraint("texto <> ''"), nullable=False),
        sa.Column("categoria_id", sa.Integer, sa.ForeignKey("categorias.id"), nullable=False),
        sa.UniqueConstraint("campo", "texto"),
    )
    op.create_table(
        "configuracion_saldo",
        sa.Column("id", sa.Integer, sa.CheckConstraint("id = 1"), primary_key=True, nullable=True),
        sa.Column(
            "saldo_inicial_centavos",
            sa.Integer,
            _solo_sqlite(sa.CheckConstraint("typeof(saldo_inicial_centavos) = 'integer'")),
            nullable=False,
        ),
        sa.Column("fecha_inicio", sa.Text, nullable=False),
    )
    op.create_table(
        "correos_no_reconocidos",
        sa.Column("gmail_id", sa.Text, primary_key=True, nullable=True),
        sa.Column("fecha", sa.Text),
        sa.Column("asunto", sa.Text),
    )
    # Mismos ids que les daba la v1 (1 a 8, en este orden).
    op.bulk_insert(
        categorias,
        [{"id": i, "nombre": nombre} for i, nombre in enumerate(CATEGORIAS_FIJAS, start=1)],
    )


def downgrade() -> None:
    # Borra todo. "python -m finanzas.migrar" no permite bajar de 0001: para
    # volver atrás se restaura el respaldo previo (deploy/GUIA.md).
    op.drop_table("correos_no_reconocidos")
    op.drop_table("configuracion_saldo")
    op.drop_table("reglas")
    op.drop_index("idx_movimientos_fecha_hora", table_name="movimientos")
    op.drop_table("movimientos")
    op.drop_table("categorias")
