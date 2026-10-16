"""Diario de configuración/historial guiado; respaldo previo obligatorio."""
from alembic import op
from alembic.util import CommandError
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reversiones_importacion", sa.Column("arranque", sa.Text()))


def downgrade():
    usado = op.get_bind().execute(sa.text(
        "SELECT 1 FROM reversiones_importacion WHERE arranque IS NOT NULL LIMIT 1")).first()
    if usado:
        raise CommandError("El arranque guiado ya tiene datos: restaura el respaldo previo; no se perderá su reversión.")
    op.drop_column("reversiones_importacion", "arranque")
