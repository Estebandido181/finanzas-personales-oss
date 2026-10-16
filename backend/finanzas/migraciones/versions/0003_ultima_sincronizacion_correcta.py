"""Hora de la última sincronización correcta.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30

Ítem 13: la pantalla de inicio dice cuándo fue la última sincronización que
sí trajo los correos, aunque la más reciente haya fallado. La tabla
``estado_sincronizacion`` (0002) guarda una sola fila que se reemplaza en
cada sincronización, así que al fallar se perdía ese dato. Se añade la
columna ``ultima_correcta_en`` (nullable), en el mismo formato que
``terminada_en``: texto ISO 8601 en hora de Colombia, sin zona.

"Correcta" es toda sincronización que no quedó ``fallida``, es decir,
``ok`` o ``con_errores``: las dos se conectaron a Gmail y terminaron; en
``con_errores`` solo algunos correos fallaron y se reintentan en la
siguiente (el estado lo sigue diciendo).

Relleno al migrar: si ya hay una fila y su estado no es ``fallida``, esa
sincronización fue la última correcta y ``ultima_correcta_en`` toma su
``terminada_en``. Si es ``fallida``, queda ``NULL``: no se sabe cuándo fue
la última correcta (se perdió al reemplazar la fila) y es mejor no mostrar
nada que inventar una fecha; la siguiente sincronización correcta la escribe.

Sin CHECK nuevo: SQLite no permite añadir con ``ALTER TABLE ADD COLUMN`` una
restricción que la fila existente aún no cumple, y reconstruir la tabla por
una columna informativa no compensa. La regla la aplica
``sincronizacion.guardar_estado``.

``downgrade`` quita la columna (se pierde solo esa fecha; el resto de la
fila queda igual). Como toda migración, está escrita sin depender de
``finanzas.db``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("estado_sincronizacion", sa.Column("ultima_correcta_en", sa.Text, nullable=True))
    op.execute(
        "UPDATE estado_sincronizacion SET ultima_correcta_en = terminada_en "
        "WHERE estado <> 'fallida'"
    )


def downgrade() -> None:
    # ALTER TABLE ... DROP COLUMN directo (SQLite >= 3.35), sin recrear la
    # tabla: así se conservan tal cual los CHECK de la 0002.
    op.drop_column("estado_sincronizacion", "ultima_correcta_en")
