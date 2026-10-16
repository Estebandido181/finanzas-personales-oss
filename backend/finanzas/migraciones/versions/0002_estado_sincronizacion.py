"""Estado de la última sincronización.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30

Ítem 10: la API (y el frontend del ítem 13) muestran cuándo terminó la
última sincronización, si falló y por qué, aunque la haya lanzado el
temporizador del sistema. Se guarda en una tabla de una sola fila
(``id = 1``) que ``sincronizacion.ejecutar`` reemplaza cada vez.

Sin datos de correos: solo la hora, el estado, de dónde se lanzó, los
contadores y un código de error de una lista cerrada (nunca un texto libre).

Solo crea una tabla nueva: no toca las demás ni sus datos. ``downgrade`` la
borra (se pierde solo el estado de la última sincronización, que la
siguiente vuelve a escribir).

Como toda migración, está escrita sin depender de ``finanzas.db``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTADORES = ("nuevos", "duplicados", "no_reconocidos", "errores", "rechazados_autenticacion")


def _contador(nombre: str) -> sa.Column:
    return sa.Column(
        nombre,
        sa.Integer,
        sa.CheckConstraint(f"{nombre} IS NULL OR typeof({nombre}) = 'integer'").ddl_if(dialect="sqlite"),
        sa.CheckConstraint(f"{nombre} IS NULL OR {nombre} >= 0"),
    )


def upgrade() -> None:
    op.create_table(
        "estado_sincronizacion",
        sa.Column("id", sa.Integer, sa.CheckConstraint("id = 1"), primary_key=True, nullable=True),
        sa.Column("terminada_en", sa.Text, nullable=False),
        sa.Column(
            "estado",
            sa.Text,
            sa.CheckConstraint("estado IN ('ok', 'con_errores', 'fallida')"),
            nullable=False,
        ),
        sa.Column(
            "origen", sa.Text, sa.CheckConstraint("origen IN ('web', 'comando')"), nullable=False
        ),
        *[_contador(nombre) for nombre in CONTADORES],
        sa.Column(
            "codigo_error",
            sa.Text,
            sa.CheckConstraint(
                "codigo_error IS NULL OR codigo_error IN "
                "('sin_fecha_inicio', 'gmail_no_configurado', 'autorizacion_gmail', 'error_inesperado')"
            ),
        ),
        sa.CheckConstraint("(estado = 'fallida') = (codigo_error IS NOT NULL)"),
        sa.CheckConstraint("(estado = 'fallida') = (nuevos IS NULL)"),
    )


def downgrade() -> None:
    op.drop_table("estado_sincronizacion")
