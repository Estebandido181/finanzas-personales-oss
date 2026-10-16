"""Importación interactiva y reglas bancarias; respaldo previo obligatorio.

El diario conserva solo movimientos normalizados y sus cambios. Downgrade
se niega si hay información nueva para no perder borrados, reglas o reversión.
"""
from alembic import op
from alembic.util import CommandError
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("movimientos", sa.Column("borrado_en", sa.Text()))
    op.add_column("movimientos", sa.Column("revisado_no_en_banco", sa.Integer(), sa.CheckConstraint("revisado_no_en_banco IN (0, 1)"), nullable=False, server_default="0"))
    op.add_column("reglas", sa.Column("modo_texto", sa.Text(), sa.CheckConstraint("modo_texto IN ('exacta', 'contiene', 'empieza_por')"), nullable=False, server_default="exacta"))
    op.add_column("reglas", sa.Column("origen_regla", sa.Text(), sa.CheckConstraint("origen_regla IN ('todos', 'extracto')"), nullable=False, server_default="todos"))
    op.add_column("reglas", sa.Column("texto_visible", sa.Text()))
    op.drop_index("ux_reglas_condiciones", table_name="reglas")
    op.execute("CREATE UNIQUE INDEX ux_reglas_condiciones ON reglas (campo, COALESCE(texto, ''), COALESCE(monto_centavos, 0), modo_texto, origen_regla)")
    op.create_table("reversiones_importacion",
        sa.Column("importacion_id", sa.Integer(), sa.ForeignKey("importaciones.id"), primary_key=True),
        sa.Column("diario", sa.Text(), nullable=False),
        sa.Column("conteos", sa.Text(), nullable=False),
        sa.Column("ultimo_movimiento_id", sa.Integer(), nullable=False))


def downgrade():
    conn = op.get_bind()
    usado = conn.execute(sa.text("SELECT 1 FROM reversiones_importacion UNION ALL SELECT 1 FROM movimientos WHERE borrado_en IS NOT NULL OR revisado_no_en_banco <> 0 UNION ALL SELECT 1 FROM reglas WHERE modo_texto <> 'exacta' OR origen_regla <> 'todos' OR texto_visible IS NOT NULL LIMIT 1")).first()
    if usado:
        raise CommandError("La importación interactiva ya tiene datos: restaura el respaldo previo; no se perderán silenciosamente.")
    op.drop_table("reversiones_importacion")
    op.drop_index("ux_reglas_condiciones", table_name="reglas")
    op.drop_column("reglas", "texto_visible")
    op.drop_column("reglas", "origen_regla")
    op.drop_column("reglas", "modo_texto")
    op.execute("CREATE UNIQUE INDEX ux_reglas_condiciones ON reglas (campo, COALESCE(texto, ''), COALESCE(monto_centavos, 0))")
    op.drop_column("movimientos", "revisado_no_en_banco")
    op.drop_column("movimientos", "borrado_en")
